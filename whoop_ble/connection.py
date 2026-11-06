"""
BLE Connection Manager.
Manages connection lifecycle, timeouts, disconnection events, connection status logging,
and Resilient Auto-Reconnect with Session Recovery.
"""

import asyncio
from typing import Any, Awaitable, Callable, Optional
from bleak import BleakClient, BleakScanner
from whoop_ble.logger import DiagnosticLogger


class BLEConnectionManager:
    def __init__(
        self,
        address_or_device: str,
        logger: DiagnosticLogger,
        disconnected_callback: Optional[Callable[[BleakClient], None]] = None,
        auto_reconnect: bool = False,
        reconnect_callback: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        self.address = address_or_device
        self.logger = logger
        self.external_disconnected_cb = disconnected_callback
        self.auto_reconnect_enabled = auto_reconnect
        self.reconnect_callback = reconnect_callback

        self.client: Optional[BleakClient] = None
        self.is_connected = False
        self._manual_disconnect = False
        self._reconnecting = False
        self._reconnect_task: Optional[asyncio.Task] = None

    def _on_disconnect(self, client: BleakClient):
        self.is_connected = False
        self.logger.log_connection_state(
            device_address=self.address,
            device_name=None,
            state="DISCONNECTED",
        )
        if self.external_disconnected_cb:
            try:
                self.external_disconnected_cb(client)
            except Exception as e:
                self.logger.log_gatt_error("disconnected_callback", str(e))

        # Check if auto-reconnect should trigger
        if self.auto_reconnect_enabled and not self._manual_disconnect and not self._reconnecting:
            self._reconnecting = True
            try:
                loop = asyncio.get_running_loop()
                self._reconnect_task = loop.create_task(self._reconnect_loop())
            except RuntimeError:
                pass

    async def _reconnect_loop(self, max_attempts: int = 5):
        """
        Automatic Reconnect with Exponential Backoff and Session Recovery.
        """
        backoff = 1.5
        attempt = 0
        print(f"\n[!] Connection lost to {self.address}. Starting Auto-Reconnect sequence...")

        while self.auto_reconnect_enabled and not self._manual_disconnect and attempt < max_attempts:
            attempt += 1
            print(f"[*] Reconnect attempt {attempt}/{max_attempts} in {backoff:.1f}s...")
            await asyncio.sleep(backoff)

            success = await self.connect(timeout=10.0)
            if success:
                print(f"[+] Reconnected successfully to {self.address}!")
                self._reconnecting = False
                # Trigger session recovery callback (e.g. re-subscribe & handshake 0x91)
                if self.reconnect_callback:
                    print("[*] Executing Session Recovery callback...")
                    try:
                        await self.reconnect_callback()
                        print("[+] Session recovered and active!")
                    except Exception as rec_err:
                        self.logger.log_gatt_error("session_recovery", str(rec_err))
                        print(f"[!] Warning in session recovery: {rec_err}")
                return

            backoff = min(10.0, backoff * 1.8)

        self._reconnecting = False
        print(f"[!] Auto-Reconnect failed after {attempt} attempts.")

    async def connect(self, timeout: float = 15.0) -> bool:
        """Connect to the BLE peripheral."""
        self._manual_disconnect = False
        self.logger.log_connection_state(
            device_address=self.address,
            device_name=None,
            state="CONNECTING",
        )

        try:
            target = self.address
            if isinstance(target, str):
                dev = await BleakScanner.find_device_by_address(target, timeout=6.0)
                if dev:
                    target = dev

            self.client = BleakClient(
                target,
                disconnected_callback=self._on_disconnect,
                timeout=timeout,
            )
            await self.client.connect()
            self.is_connected = bool(self.client.is_connected)

            if self.is_connected:
                self.logger.log_connection_state(
                    device_address=self.address,
                    device_name=getattr(self.client, "name", None),
                    state="CONNECTED",
                )
                return True
            else:
                self.logger.log_gatt_error("connect", "Client is_connected is False after connect()")
                return False
        except Exception as e:
            self.is_connected = False
            self.logger.log_gatt_error("connect", str(e))
            return False

    async def disconnect(self):
        """Disconnect safely from the peripheral."""
        self._manual_disconnect = True
        self.auto_reconnect_enabled = False
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()

        if self.client and self.client.is_connected:
            try:
                self.logger.log_connection_state(
                    device_address=self.address,
                    device_name=None,
                    state="DISCONNECTING",
                )
                await self.client.disconnect()
            except Exception as e:
                self.logger.log_gatt_error("disconnect", str(e))
            finally:
                self.is_connected = False
                self.client = None
