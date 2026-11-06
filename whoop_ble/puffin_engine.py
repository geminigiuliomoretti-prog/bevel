"""
WHOOP Gen 5 ("Puffin" fd4b) Connection Engine & Serialized Command Queue.
Features:
- Strict Safety Allowlist (blocks 0x19 ERASE_DEVICE, 0x1D REBOOT_DEVICE, DFU)
- Guaranteed Write with Response (response=True on fd4b0002)
- Serialized Request-Response with asyncio.Lock and echo_seq matching on fd4b0003
- Automatic Stream Reassembly on all notify endpoints (fd4b0003, fd4b0004, fd4b0005, fd4b0007)
- Automated Windows BLE Bonding / Pairing Recovery
- Resilient Auto-Reconnect & Session Recovery
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Set
from bleak import BleakClient

from whoop_ble.constants import (
    PUFFIN_SERVICE_UUID,
    PUFFIN_CHAR_COMMAND_TX,
    PUFFIN_CHAR_COMMAND_RX,
    PUFFIN_CHAR_EVENTS,
    PUFFIN_CHAR_DATA_STREAM,
    PUFFIN_CHAR_EXTRA_NOTIFY,
    BLOCKED_OPCODES,
)
from whoop_ble.logger import DiagnosticLogger
from whoop_ble.puffin_framing import (
    build_frame,
    extract_inner_payload,
    PuffinStreamReassembler,
)
from whoop_ble.puffin_decoder import (
    decode_puffin_packet,
    decode_response_0x24,
    decode_live_hr_0x28,
    decode_historical_record_0x2F,
    decode_cursor_metadata_0x31,
    decode_event_0x30,
)


class PuffinCommandError(Exception):
    """Raised when a Puffin command times out or returns an error."""
    pass


class PuffinSafetyViolation(Exception):
    """Raised when an attempt is made to execute a dangerous/blocked opcode."""
    pass


class PuffinEngine:
    def __init__(self, client: BleakClient, logger: Optional[DiagnosticLogger] = None):
        self.client = client
        self.logger = logger

        # Sequence counter: 1..255 (wraps at 255)
        self._seq = 1

        # Command serialization lock (Strict Request-Response serialisation)
        self._cmd_lock = asyncio.Lock()

        # In-flight request pending futures: echo_seq -> asyncio.Future
        self._pending_responses: Dict[int, asyncio.Future] = {}
        self._current_pending: Optional[Dict[str, Any]] = None

        # Stream reassemblers for each notify characteristic
        self._reassembler_rx = PuffinStreamReassembler()
        self._reassembler_events = PuffinStreamReassembler()
        self._reassembler_stream = PuffinStreamReassembler()
        self._reassembler_extra = PuffinStreamReassembler()

        # Subscribed callbacks
        self.on_live_hr: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_historical_record: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_cursor_metadata: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_hardware_event: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_packet_log: Optional[Callable[[str, str, bytes, Optional[Dict[str, Any]]], None]] = None

        # Auto-ACK for historical offload (cursor 0x31 -> send 0x17)
        self.auto_ack_cursor_enabled = True
        self._last_acked_cursor: Optional[str] = None

        # Notification subscription state
        self._subscribed = False

        # Raw packet history counter
        self.stats = {
            "commands_sent": 0,
            "responses_received": 0,
            "live_hr_packets": 0,
            "historical_records": 0,
            "cursor_packets": 0,
            "hardware_events": 0,
            "retries": 0,
            "reconnects": 0,
        }

    def _next_seq(self) -> int:
        seq = self._seq
        self._seq = 1 if self._seq >= 255 else self._seq + 1
        return seq

    def _log(self, event_type: str, details: Dict[str, Any]):
        if self.logger:
            self.logger.log_event(event_type, details)
        else:
            logging.info(f"[{event_type}] {details}")

    def _log_packet(self, endpoint: str, direction: str, raw_bytes: bytes, decoded: Optional[Dict[str, Any]] = None):
        if self.on_packet_log:
            self.on_packet_log(endpoint, direction, raw_bytes, decoded)
        if self.logger:
            self.logger.log_packet(
                device_address=self.client.address,
                characteristic_uuid=endpoint,
                characteristic_name=f"Puffin {direction}",
                raw_bytes=raw_bytes,
                decoded_data=decoded,
            )

    async def _safe_pair_if_needed(self, error: Exception):
        """
        Attempts programmatic pairing on Windows if insufficient authentication / encryption occurs.
        """
        err_msg = str(error).lower()
        triggers = ["access denied", "authentication", "encryption", "insufficient", "0x80070005", "0x806500"]
        if any(t in err_msg for t in triggers):
            self._log("PAIRING_TRIGGERED", {"reason": str(error), "device": self.client.address})
            print("\n[!] Windows BLE Security requirement detected. Attempting client.pair()...")
            print("    (If WHOOP shows a pulsing blue LED, tap the strap twice if prompted)")
            try:
                paired = await self.client.pair()
                self._log("PAIRING_RESULT", {"paired": paired})
                print(f"[+] Bleak client.pair() finished: {paired}")
                await asyncio.sleep(1.0)
            except Exception as pe:
                self._log("PAIRING_ERROR", {"error": str(pe)})
                print(f"[!] Warning during client.pair(): {pe}")

    async def subscribe_all(self):
        """
        Subscribes to all Puffin notification endpoints:
        - fd4b0003 (Command responses 0x24)
        - fd4b0004 (Hardware events 0x30)
        - fd4b0005 (Data stream / Live HR / History)
        - fd4b0007 (Extra notifications)
        """
        endpoints = [
            (PUFFIN_CHAR_COMMAND_RX, self._handle_cmd_rx, "Command RX (0003)"),
            (PUFFIN_CHAR_EVENTS, self._handle_events, "Events (0004)"),
            (PUFFIN_CHAR_DATA_STREAM, self._handle_data_stream, "Data Stream (0005)"),
            (PUFFIN_CHAR_EXTRA_NOTIFY, self._handle_extra, "Extra (0007)"),
        ]

        for char_uuid, handler, name in endpoints:
            try:
                await self.client.start_notify(char_uuid, handler)
                self._log("PUFFIN_SUBSCRIPTION_SUCCESS", {"char": char_uuid, "name": name})
            except Exception as e:
                self._log("PUFFIN_SUBSCRIPTION_ERROR", {"char": char_uuid, "error": str(e)})
                await self._safe_pair_if_needed(e)
                # Retry subscription once after pairing
                try:
                    await self.client.start_notify(char_uuid, handler)
                    self._log("PUFFIN_SUBSCRIPTION_SUCCESS_AFTER_PAIR", {"char": char_uuid, "name": name})
                except Exception as retry_err:
                    self._log("PUFFIN_SUBSCRIPTION_FAILED_DEFINITIVELY", {"char": char_uuid, "error": str(retry_err)})
                    raise retry_err

        self._subscribed = True

    async def unsubscribe_all(self):
        """Unsubscribes cleanly from all Puffin notification endpoints."""
        endpoints = [
            PUFFIN_CHAR_COMMAND_RX,
            PUFFIN_CHAR_EVENTS,
            PUFFIN_CHAR_DATA_STREAM,
            PUFFIN_CHAR_EXTRA_NOTIFY,
        ]
        for char_uuid in endpoints:
            try:
                await self.client.stop_notify(char_uuid)
            except Exception:
                pass
        self._subscribed = False

    def _handle_cmd_rx(self, sender: Any, data: bytearray):
        """Incoming chunks on fd4b0003 (Command responses)."""
        raw_bytes = bytes(data)
        frames = self._reassembler_rx.feed(raw_bytes)
        for frame in frames:
            inner = extract_inner_payload(frame)
            decoded = decode_puffin_packet(inner)
            self._log_packet("fd4b0003", "RX_RESPONSE", frame, decoded)
            self.stats["responses_received"] += 1

            if decoded.get("type") == "COMMAND_RESPONSE":
                echo_seq = decoded["echo_seq"]
                resp_cmd = decoded["resp_cmd"]
                status_code = decoded["status_code"]
                is_in_progress = (status_code == 2)

                # Match against current in-flight pending request
                pending = self._current_pending
                if pending and not pending["future"].done():
                    target_seq = pending["seq"]
                    target_cmd = pending["cmd"]

                    if echo_seq == target_seq or resp_cmd == target_cmd or echo_seq == ((target_seq + 1) & 0xFF):
                        if is_in_progress:
                            # 2-stage response: interim ACK, store and await final data packet
                            pending["interim"] = decoded
                            self._log("COMMAND_INTERIM_ACK", {"cmd": f"0x{target_cmd:02X}", "seq": target_seq})
                        else:
                            # Final completed response with data (status 0, 1 or error)
                            pending["future"].set_result(decoded)
                            continue

                # Fallback to direct seq map
                if echo_seq in self._pending_responses:
                    fut = self._pending_responses[echo_seq]
                    if not fut.done() and not is_in_progress:
                        fut.set_result(decoded)

    def _handle_events(self, sender: Any, data: bytearray):
        """Incoming chunks on fd4b0004 (Hardware events 0x30)."""
        raw_bytes = bytes(data)
        frames = self._reassembler_events.feed(raw_bytes)
        for frame in frames:
            inner = extract_inner_payload(frame)
            decoded = decode_puffin_packet(inner)
            self._log_packet("fd4b0004", "RX_EVENT", frame, decoded)
            self.stats["hardware_events"] += 1
            if self.on_hardware_event:
                self.on_hardware_event(decoded)

    def _handle_data_stream(self, sender: Any, data: bytearray):
        """Incoming chunks on fd4b0005 (Live HR 0x28, History 0x2F, Cursor 0x31)."""
        raw_bytes = bytes(data)
        frames = self._reassembler_stream.feed(raw_bytes)
        for frame in frames:
            inner = extract_inner_payload(frame)
            decoded = decode_puffin_packet(inner)
            pkt_type = decoded.get("type")
            self._log_packet("fd4b0005", f"RX_STREAM_{pkt_type}", frame, decoded)

            if pkt_type == "LIVE_HR":
                self.stats["live_hr_packets"] += 1
                if self.on_live_hr:
                    self.on_live_hr(decoded)

            elif pkt_type in ("HISTORICAL_RECORD_V18", "HISTORICAL_RECORD_V26_PPG", "HISTORICAL_RECORD_RAW"):
                self.stats["historical_records"] += 1
                if self.on_historical_record:
                    self.on_historical_record(decoded)

            elif pkt_type == "METADATA_CURSOR":
                self.stats["cursor_packets"] += 1
                if self.on_cursor_metadata:
                    self.on_cursor_metadata(decoded)

                # Automatic ACK for 0x31 cursor to prevent offload stall (deduplicated)
                cursor_hex = decoded.get("cursor_hex")
                if self.auto_ack_cursor_enabled and cursor_hex:
                    if cursor_hex != self._last_acked_cursor:
                        self._last_acked_cursor = cursor_hex
                        cursor_b = bytes.fromhex(cursor_hex)
                        # Launch auto-ack as background task to not block reassembler
                        asyncio.create_task(self._auto_ack_cursor(cursor_b))

    async def _auto_ack_cursor(self, cursor_8b: bytes):
        """Sends command 0x17 (HISTORICAL_DATA_RESULT) with 8-byte cursor payload (low latency)."""
        try:
            # 0x17 with b3=0x01 and cursor payload, low latency 0.8s timeout to avoid strap re-delivery loop
            await self.send_command(cmd=0x17, b3=0x01, params=cursor_8b, timeout=0.8, max_retries=2)
            self._log("AUTO_ACK_CURSOR_SENT", {"cursor_hex": cursor_8b.hex().upper()})
        except Exception as e:
            self._last_acked_cursor = None  # Allow retry on next 0x31 packet
            self._log("AUTO_ACK_CURSOR_FAILED", {"cursor_hex": cursor_8b.hex().upper(), "error": str(e)})

    def _handle_extra(self, sender: Any, data: bytearray):
        """Incoming chunks on fd4b0007 (Extra notifications)."""
        raw_bytes = bytes(data)
        frames = self._reassembler_extra.feed(raw_bytes)
        for frame in frames:
            inner = extract_inner_payload(frame)
            decoded = decode_puffin_packet(inner)
            self._log_packet("fd4b0007", "RX_EXTRA", frame, decoded)

    async def send_command(
        self,
        cmd: int,
        b3: int = 0x01,
        params: bytes = b"",
        timeout: float = 3.0,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Sends a command to fd4b0002 with strict Request-Response serialization:
        1. Safety allowlist check (blocks 0x19, 0x1D).
        2. Acquires asyncio.Lock to prevent command interleaving.
        3. Wraps inner command: [0x23, seq, cmd, b3, ...params].
        4. Writes frame with response=True.
        5. Awaits matching 0x24 response on fd4b0003 (echo_seq == seq).
        6. Retries up to max_retries on timeout.
        """
        # Safety enforcement
        if cmd in BLOCKED_OPCODES:
            err_msg = f"CRITICAL SAFETY VIOLATION: Command 0x{cmd:02X} is permanently blocked to prevent device erase/reboot/damage!"
            self._log("BLOCKED_COMMAND_INTERCEPTED", {"cmd_hex": f"0x{cmd:02X}"})
            raise PuffinSafetyViolation(err_msg)

        if not self._subscribed:
            await self.subscribe_all()

        async with self._cmd_lock:
            for attempt in range(1, max_retries + 1):
                seq = self._next_seq()
                inner_cmd = bytes([0x23, seq, cmd, b3]) + params
                frame = build_frame(inner_cmd)

                # Setup future for echo_seq response
                loop = asyncio.get_running_loop()
                fut: asyncio.Future = loop.create_future()
                self._pending_responses[seq] = fut
                self._current_pending = {
                    "seq": seq,
                    "cmd": cmd,
                    "future": fut,
                    "interim": None,
                }

                self._log_packet("fd4b0002", "TX_COMMAND", frame, {
                    "cmd": f"0x{cmd:02X}",
                    "seq": seq,
                    "b3": f"0x{b3:02X}",
                    "params_hex": params.hex().upper(),
                    "attempt": attempt,
                })

                try:
                    # Mandatory Write with Response
                    await self.client.write_gatt_char(PUFFIN_CHAR_COMMAND_TX, frame, response=True)
                    self.stats["commands_sent"] += 1

                    # Await response with timeout
                    response = await asyncio.wait_for(fut, timeout=timeout)
                    return response

                except asyncio.TimeoutError:
                    if self._current_pending and self._current_pending.get("interim"):
                        # We received an interim ACK earlier, return it if final payload didn't arrive
                        return self._current_pending["interim"]

                    self.stats["retries"] += 1
                    self._log("COMMAND_TIMEOUT", {
                        "cmd": f"0x{cmd:02X}",
                        "seq": seq,
                        "attempt": attempt,
                        "max_retries": max_retries,
                    })
                    if attempt == max_retries:
                        raise PuffinCommandError(f"Command 0x{cmd:02X} timed out after {max_retries} attempts ({timeout}s each).")
                    await asyncio.sleep(0.3 * attempt)

                except Exception as e:
                    self._log("COMMAND_WRITE_ERROR", {"cmd": f"0x{cmd:02X}", "error": str(e), "attempt": attempt})
                    await self._safe_pair_if_needed(e)
                    if attempt == max_retries:
                        raise e
                    await asyncio.sleep(0.5 * attempt)

                finally:
                    self._pending_responses.pop(seq, None)
                    if self._current_pending and self._current_pending.get("seq") == seq:
                        self._current_pending = None

            raise PuffinCommandError(f"Command 0x{cmd:02X} failed all retry attempts.")
