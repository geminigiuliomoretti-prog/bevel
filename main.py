"""
WHOOP 5.0 BLE Reverse Engineering & Diagnostics CLI Interface.
Task 02: Deep Strap Connection & Full Hardware Unlock ("Puffin" fd4b).
"""

import argparse
import asyncio
import datetime
import json
import os
import sys
from typing import Any, Dict, List, Optional

from whoop_ble.logger import DiagnosticLogger
from whoop_ble.scanner import BLEDeviceScanner, DiscoveredBLEDevice
from whoop_ble.connection import BLEConnectionManager
from whoop_ble.explorer import GATTExplorer
from whoop_ble.device_info import StandardDataReader
from whoop_ble.notification_handler import NotificationHandler
from whoop_ble.proprietary import ProprietaryServiceInspector
from whoop_ble.puffin_engine import PuffinEngine, PuffinCommandError, PuffinSafetyViolation
from whoop_ble.puffin_commands import PuffinDeviceController
from whoop_ble.database import WhoopDatabase
from whoop_ble.biometrics import BiometricsEngine
from whoop_ble.sync_manager import HistoricalSyncManager
from whoop_ble.constants import (
    PUFFIN_SERVICE_UUID,
    PUFFIN_CHAR_COMMAND_TX,
    PUFFIN_CHAR_COMMAND_RX,
    PUFFIN_CHAR_DATA_STREAM,
    PUFFIN_CHAR_EVENTS,
    PUFFIN_16_FEATURE_FLAGS,
)


class WhoopDiagnosticApp:
    def __init__(self):
        self.logger = DiagnosticLogger(log_dir="logs")
        self.scanner = BLEDeviceScanner(self.logger)
        self.connection_mgr: Optional[BLEConnectionManager] = None
        self.explorer: Optional[GATTExplorer] = None
        self.standard_reader: Optional[StandardDataReader] = None
        self.notif_handler: Optional[NotificationHandler] = None
        self.proprietary_inspector: Optional[ProprietaryServiceInspector] = None

        # Puffin Engine & Controller
        self.puffin_engine: Optional[PuffinEngine] = None
        self.puffin_controller: Optional[PuffinDeviceController] = None

        # Task 03 Persistence & DSP
        self.db = WhoopDatabase("data/whoop_local.db")
        self.biometrics = BiometricsEngine()
        self.sync_mgr: Optional[HistoricalSyncManager] = None

        self.last_discovered_devices: List[DiscoveredBLEDevice] = []
        self.selected_device: Optional[DiscoveredBLEDevice] = None
        self.latest_gatt_tree: Optional[dict] = None
        self.hr_streaming_active = False
        self.puffin_streaming_active = False

        # Collected telemetry
        self.collected_live_hr_packets: List[Dict[str, Any]] = []
        self.collected_historical_records: List[Dict[str, Any]] = []
        self.collected_events: List[Dict[str, Any]] = []

    def print_banner(self):
        print("=" * 75)
        print(" WHOOP 5.0 BLE REVERSE ENGINEERING & DIAGNOSTIC TOOLKIT (GEN 5 PUFFIN)")
        print(" Workstation: Windows 11 / Microsoft Surface Pro")
        print(f" Session ID:  {self.logger.session_id}")
        print("=" * 75)

    async def run_scan(self, duration: float = 6.0):
        print(f"\n[*] Scanning for BLE devices nearby ({duration:.1f}s)...")
        print("    (Filtering heuristic: checks name, manufacturer ID, advertised services)")
        devices = await self.scanner.scan(duration_seconds=duration)
        self.last_discovered_devices = devices

        if not devices:
            print("[!] No BLE devices detected. Check Bluetooth is enabled and devices are in range.")
            return

        print(f"\n[+] Found {len(devices)} device(s):")
        print("-" * 75)
        print(f"{'#':<3} | {'Device Name':<24} | {'Address / ID':<22} | {'RSSI':<5} | {'Score'}")
        print("-" * 75)

        for i, dev in enumerate(devices):
            score_str = f"{dev.whoop_heuristic_score}/100"
            tag = ""
            if dev.whoop_heuristic_score >= 50:
                tag = " <-- [POTENTIAL WHOOP]"
            print(f"{i+1:<3} | {dev.name[:24]:<24} | {dev.address:<22} | {dev.rssi or 'N/A':<5} | {score_str}{tag}")

            if dev.whoop_heuristic_score > 0:
                for reason in dev.whoop_heuristic_reasons:
                    print(f"      * {reason}")
                if dev.service_uuids:
                    print(f"      * Services: {', '.join(dev.service_uuids)}")

        print("-" * 75)

    def select_device(self, index: int) -> bool:
        if 1 <= index <= len(self.last_discovered_devices):
            self.selected_device = self.last_discovered_devices[index - 1]
            print(f"\n[+] Selected Device: {self.selected_device.name} ({self.selected_device.address})")
            print(f"    WHOOP Heuristic Score: {self.selected_device.whoop_heuristic_score}/100")
            return True
        else:
            print("[!] Invalid index.")
            return False

    async def connect(self) -> bool:
        if not self.selected_device:
            print("[!] No device selected. Run scan and select a device first.")
            return False

        if self.connection_mgr and self.connection_mgr.is_connected:
            print(f"[*] Already connected to {self.selected_device.address}")
            return True

        print(f"\n[*] Establishing BLE connection to {self.selected_device.address} ({self.selected_device.name})...")
        self.connection_mgr = BLEConnectionManager(
            self.selected_device.address,
            self.logger,
            disconnected_callback=self._handle_disconnection,
            auto_reconnect=True,
            reconnect_callback=self._handle_session_recovery,
        )

        success = await self.connection_mgr.connect(timeout=15.0)
        if success:
            print("[+] Connected successfully!")
            client = self.connection_mgr.client
            self.explorer = GATTExplorer(client, self.logger)
            self.standard_reader = StandardDataReader(client, self.logger)
            self.notif_handler = NotificationHandler(client, self.logger)
            self.proprietary_inspector = ProprietaryServiceInspector(client, self.logger)

            # Initialize Puffin Gen 5 Engine & Controller
            self.puffin_engine = PuffinEngine(client, self.logger)
            self.puffin_controller = PuffinDeviceController(self.puffin_engine)

            # Wire telemetry callbacks
            self.puffin_engine.on_live_hr = self._on_live_hr_telemetry
            self.puffin_engine.on_historical_record = self._on_historical_record_telemetry
            self.puffin_engine.on_hardware_event = self._on_hardware_event_telemetry
            return True
        else:
            print("[!] Connection failed. Ensure the device is awake, not connected to another host, and in range.")
            return False

    def _handle_disconnection(self, client):
        print(f"\n[!] BLE Peripheral disconnected: {client.address}")
        self.hr_streaming_active = False
        self.puffin_streaming_active = False

    async def _handle_session_recovery(self):
        """Called automatically by BLEConnectionManager when connection is restored."""
        if self.puffin_controller and self.connection_mgr and self.connection_mgr.client:
            print("[*] Performing Session Recovery: re-subscribing notifications and executing GET_HELLO 0x91...")
            self.puffin_engine.client = self.connection_mgr.client
            await self.puffin_engine.subscribe_all()
            try:
                hello_res = await self.puffin_controller.get_hello(b3=0x01)
                print(f"[+] Session Recovery successful! Hello status: {hello_res.get('is_success')}")
            except Exception as e:
                print(f"[!] Warning during session recovery hello: {e}")

    async def disconnect(self):
        if self.connection_mgr and self.connection_mgr.is_connected:
            if self.puffin_engine:
                try:
                    await self.puffin_engine.unsubscribe_all()
                except Exception:
                    pass
            if self.notif_handler:
                await self.notif_handler.stop_all_notifications()
            await self.connection_mgr.disconnect()
            print("[+] Disconnected cleanly.")
        else:
            print("[*] No active connection.")

    def _on_live_hr_telemetry(self, pkt: Dict[str, Any]):
        self.collected_live_hr_packets.append(pkt)
        bpm = pkt.get("heart_rate_bpm")
        state = pkt.get("on_wrist_state")
        flag = pkt.get("on_wrist_flag")
        rr = pkt.get("rr_ms")
        rr_str = f"{rr} ms" if rr else "None"
        ts_str = pkt.get("timestamp_utc", "N/A")
        print(f"  [PUFFIN 0x28 LIVE] BPM: {bpm:<3} | State: {state:<15} (Flag: {flag}) | RR: {rr_str:<10} | Time: {ts_str}")

    def _on_historical_record_telemetry(self, pkt: Dict[str, Any]):
        self.collected_historical_records.append(pkt)
        pkt_type = pkt.get("type")
        seq = pkt.get("sequence")
        if pkt_type == "HISTORICAL_RECORD_V18":
            hr = pkt.get("primary_hr_bpm")
            steps = pkt.get("steps")
            temp = pkt.get("skin_temp_c")
            opt_base = pkt.get("optical_baseline_106")
            on_wrist = "YES" if pkt.get("is_on_wrist") else "NO"
            print(f"  [HIST 0x2F v18] Seq: {seq:<5} | HR: {hr:<3} | Steps: {steps:<4} | Temp: {temp}°C | Baseline: {opt_base:<5} | Wrist: {on_wrist}")
        elif pkt_type == "HISTORICAL_RECORD_V26_PPG":
            count = pkt.get("sample_count", 0)
            print(f"  [HIST 0x2F v26] Seq: {seq:<5} | PPG Wave: {count} samples at 24Hz")
        else:
            print(f"  [HIST 0x2F] Seq: {seq} | Type: {pkt_type} | Length: {pkt.get('raw_byte_length')}B")

    def _on_hardware_event_telemetry(self, pkt: Dict[str, Any]):
        self.collected_events.append(pkt)
        print(f"  [PUFFIN EVENT 0x30] Event ID: {pkt.get('event_id_hex')} | Payload: {pkt.get('payload_hex')}")

    async def explore_gatt(self):
        if not self.connection_mgr or not self.connection_mgr.is_connected:
            print("[!] Must be connected to explore GATT.")
            return None

        print("\n[*] Discovering GATT Services, Characteristics, and Descriptors...")
        tree = await self.explorer.explore()
        self.latest_gatt_tree = tree

        print("\n" + "=" * 75)
        print(f" GATT DISCOVERY REPORT: {tree['device_address']}")
        print(f" Total Services: {tree['total_services']} ({tree['standard_services_count']} Standard, {tree['proprietary_services_count']} Proprietary)")
        print(f" Total Characteristics: {tree['total_characteristics']}")
        print("=" * 75)

        for svc in tree["services"]:
            type_tag = "[STD]" if svc["is_standard"] else "[PROPRIETARY]"
            print(f"\nService: {svc['uuid']} {type_tag}")
            print(f"  Name: {svc['name']}")
            print(f"  Handle: 0x{svc['handle']:04X} ({svc['handle']})")
            print(f"  Characteristics ({len(svc['characteristics'])}):")

            for char in svc["characteristics"]:
                c_tag = "[STD]" if char["is_standard"] else "[PROPRIETARY]"
                props_str = ", ".join(char["properties"]).upper()
                print(f"    - {char['uuid']} {c_tag}")
                print(f"      Name:       {char['name']}")
                print(f"      Handle:     0x{char['handle']:04X}")
                print(f"      Properties: [{props_str}]")

        os.makedirs("exports", exist_ok=True)
        export_file = os.path.join("exports", f"gatt_{self.logger.session_id}.json")
        self.logger.export_summary_json(export_file, gatt_structure=tree, sanitize=True)
        print(f"\n[+] Full GATT tree exported to: {export_file}")
        return tree

    async def read_standard_data(self):
        if not self.connection_mgr or not self.connection_mgr.is_connected:
            print("[!] Must be connected to read standard data.")
            return

        print("\n[*] Reading Standard GATT Information (Battery 0x180F & Device Info 0x180A)...")
        bat = await self.standard_reader.read_battery_level()
        print("\n--- BATTERY STATUS ---")
        if bat["status"] == "DECODED":
            print(f"  Battery Level: {bat['battery_level_percent']}% (Raw Hex: 0x{bat['raw_hex']})")
        else:
            print(f"  Battery Level: {bat['status']} ({bat.get('error', 'Not exposed')})")

        dev_info = await self.standard_reader.read_device_information()
        print("\n--- DEVICE INFORMATION (0x180A) ---")
        for k, v in dev_info.items():
            field_name = v.get("name", k)
            status = v["status"]
            if status == "DECODED":
                print(f"  {field_name:<28}: {v['value']} (Hex: 0x{v['raw_hex']})")
            else:
                print(f"  {field_name:<28}: [{status}]")

    async def stream_heart_rate_standard(self, duration_seconds: int = 10):
        if not self.connection_mgr or not self.connection_mgr.is_connected:
            print("[!] Must be connected to stream standard heart rate.")
            return

        print(f"\n[*] Subscribing to Standard Heart Rate Measurement (0x2A37) for {duration_seconds} seconds...")
        print("    [NOTE: WHOOP 5.0 RR values decoded directly in ms]")

        def on_hr_packet(decoded: dict):
            bpm = decoded.get("heart_rate_bpm")
            contact = decoded.get("sensor_contact", {}).get("detected")
            rr_ms = decoded.get("rr_intervals_ms", [])
            raw_hex = decoded.get("raw_hex", "")
            contact_str = "YES" if contact is True else ("NO" if contact is False else "N/A")
            rr_str = f"{rr_ms} ms" if rr_ms else "None"
            print(f"  [SIG 0x2A37] BPM: {bpm:<3} | Contact: {contact_str:<3} | RR: {rr_str:<16} | Hex: {raw_hex}")

        started = await self.notif_handler.start_heart_rate_stream(callback=on_hr_packet)
        if not started:
            print("[!] Could not start standard HR stream.")
            return

        self.hr_streaming_active = True
        try:
            for _ in range(duration_seconds):
                if not self.hr_streaming_active or not self.connection_mgr.is_connected:
                    break
                await asyncio.sleep(1.0)
        finally:
            await self.notif_handler.stop_heart_rate_stream()
            self.hr_streaming_active = False
            print("[+] Standard HR stream stopped.")

    # -------------------------------------------------------------------------
    # TASK 02 DEEP CONNECTION & HARDWARE UNLOCK METHODS
    # -------------------------------------------------------------------------

    async def run_deep_connect(self) -> Dict[str, Any]:
        """
        Executes Task 02 Deep Strap Connection & Full Hardware Unlock on Puffin fd4b:
        1. Subscribes to fd4b0003, fd4b0004, fd4b0005, fd4b0007.
        2. 0x91 GET_HELLO: Opens authenticated session.
        3. 0x8D GET_ADVERTISING_NAME: Internal strap name.
        4. 0x0B GET_CLOCK: Checks RTC Unix timestamp and latched state.
        5. 0x1A GET_BATTERY: Proprietary battery metrics.
        6. 0x78 SET_FF_VALUE: Activates all 16 Gen 5 Feature Flags.
        7. 0x22 GET_DATA_RANGE: Reads NAND Flash 512MB historical data range.
        """
        if not self.connection_mgr or not self.connection_mgr.is_connected:
            print("[!] Must be connected to execute Deep Connection.")
            return {}

        print("\n" + "=" * 75)
        print(" [TASK 02] EXECUTING DEEP STRAP CONNECTION & FULL HARDWARE UNLOCK (fd4b)")
        print("=" * 75)

        unlock_report = await self.puffin_controller.run_full_bootstrap_unlock()

        print("\n--- [STEP 1] AUTHENTICATED SESSION HANDSHAKE (0x91 GET_HELLO) ---")
        if unlock_report.get("session_opened"):
            hello_resp = unlock_report.get("hello_response", {})
            print(f"  [+] Session Opened: SUCCESS (Status: 0x{hello_resp.get('status_code', 0):02X})")
            print(f"      Payload Hex: {hello_resp.get('payload_hex')}")
        else:
            print(f"  [!] Session Open Failed: {unlock_report.get('hello_error')}")

        print("\n--- [STEP 2] INTERNAL BROADCAST NAME (0x8D) ---")
        name = unlock_report.get("advertising_name")
        print(f"  Internal Advertising Name: {name or 'N/A'}")

        print("\n--- [STEP 3] RTC CLOCK CHECK (0x0B) ---")
        clk = unlock_report.get("clock", {})
        if clk:
            ts = clk.get("clock_unix")
            utc_str = clk.get("clock_utc")
            is_latched = clk.get("is_clock_latched")
            latched_str = "YES (Year Current / Latched)" if is_latched else "NO (Reset to Epoch 1970/1979)"
            print(f"  RTC Unix Timestamp : {ts} ({utc_str})")
            print(f"  Clock Latched State : {latched_str}")
        else:
            print(f"  [!] Clock read failed or empty: {unlock_report.get('clock_error')}")

        print("\n--- [STEP 4] PROPRIETARY BATTERY STATUS (0x1A) ---")
        bat = unlock_report.get("battery", {})
        if bat:
            pct = bat.get("battery_percent")
            mv = bat.get("battery_millivolts")
            charging = bat.get("charging_state")
            print(f"  Battery Level: {pct}% | Voltage: {mv} mV | Charging State: {charging}")
        else:
            print(f"  [!] Battery read failed: {unlock_report.get('battery_error')}")

        print("\n--- [STEP 5] 16 GEN 5 FEATURE FLAGS ACTIVATION (0x78) ---")
        ff = unlock_report.get("feature_flags", {})
        total_ff = ff.get("total_flags", 0)
        applied_ff = ff.get("successfully_applied", 0)
        print(f"  Applied {applied_ff}/{total_ff} Feature Flags:")
        for flag_name, flag_data in ff.get("flags", {}).items():
            st = "OK" if flag_data.get("applied") else f"FAIL ({flag_data.get('error') or flag_data.get('status_code')})"
            val = flag_data.get("value")
            print(f"    - {flag_name:<30} = {val} -> [{st}]")

        print("\n--- [STEP 6] 512MB NAND FLASH DATA RANGE (0x22) ---")
        dr = unlock_report.get("data_range", {})
        if dr:
            avail = dr.get("total_records_available")
            print(f"  Total Historical Records : {avail}")
            if "start_timestamp_unix" in dr:
                print(f"  Flash Memory Range       : {dr.get('start_utc')} -> {dr.get('end_utc')}")
                print(f"  Last Cloud Sync Point    : {dr.get('last_sync_utc')}")
                print(f"  Flash Storage Hardware   : {dr.get('flash_storage')}")
        else:
            print(f"  [!] Data Range read failed: {unlock_report.get('data_range_error')}")

        print("\n--- [STEP 7] STRAP VIBRATION & ALARM TEST (0x42) ---")
        try:
            alarm_res = await self.puffin_controller.send_alarm_vibration(pattern=1, duration_ms=400)
            st_ok = alarm_res.get("is_success", False)
            print(f"  0x42 Vibration Trigger: {'SUCCESS' if st_ok else 'FAILED'} (Status: 0x{alarm_res.get('status_code', 0):02X})")
            unlock_report["alarm_vibration"] = alarm_res
        except Exception as e:
            print(f"  [!] Vibration test note: {e}")
            unlock_report["alarm_vibration"] = {"error": str(e)}

        # Export result
        os.makedirs("exports", exist_ok=True)
        export_path = os.path.join("exports", f"deep_connect_{self.logger.session_id}.json")
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(unlock_report, f, indent=2, default=str)
        print(f"\n[+] Deep Connect & Unlock report exported to: {export_path}")

        return unlock_report

    async def stream_puffin_live(self, duration_seconds: int = 15):
        """
        Subscribes to fd4b0005 and monitors live HR (0x28 packets) with
        true ON-WRIST vs OFF-WRIST detection.
        """
        if not self.connection_mgr or not self.connection_mgr.is_connected:
            print("[!] Must be connected to stream live Puffin data.")
            return

        print(f"\n[*] Starting Proprietary Live Monitoring (fd4b0005, 0x28) for {duration_seconds}s...")
        print("    [ON-WRIST vs OFF-WRIST real hardware state detection active]")
        print("-" * 75)

        self.puffin_streaming_active = True
        self.collected_live_hr_packets.clear()

        # Ensure notification endpoints are subscribed
        await self.puffin_engine.subscribe_all()

        # Also subscribe standard 0x2A37 to awaken PPG optical sensor
        def on_sig_hr(decoded: dict):
            bpm = decoded.get("heart_rate_bpm")
            rr = decoded.get("rr_intervals_ms", [])
            rr_str = f"{rr} ms" if rr else "None"
            print(f"  [SIG 0x2A37 RAW] BPM: {bpm:<3} | Direct ms RR: {rr_str:<16} (Sensor PPG Active)")

        if self.notif_handler:
            await self.notif_handler.start_heart_rate_stream(callback=on_sig_hr)

        try:
            for elapsed in range(duration_seconds):
                if not self.puffin_streaming_active or not self.connection_mgr.is_connected:
                    break
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        finally:
            self.puffin_streaming_active = False
            if self.notif_handler:
                await self.notif_handler.stop_heart_rate_stream()
            print("-" * 75)
            print(f"[+] Live monitoring ended. Received {len(self.collected_live_hr_packets)} live HR packet(s).")

            # Summarize wrist detection results
            if self.collected_live_hr_packets:
                on_wrist_count = sum(1 for p in self.collected_live_hr_packets if p.get("is_on_wrist"))
                off_wrist_count = len(self.collected_live_hr_packets) - on_wrist_count
                print(f"    On-Wrist Valid Packets : {on_wrist_count}")
                print(f"    Off-Wrist Packets      : {off_wrist_count}")
                if on_wrist_count > 0:
                    print("    >>> HARDWARE STATUS: DEVICE IS CURRENTLY WORN ON BODY (ON-WRIST) <<<")
                else:
                    print("    >>> HARDWARE STATUS: DEVICE IS OFF BODY (FLAT SURFACE / OFF-WRIST) <<<")

    async def test_historical_offload(self, duration_seconds: int = 10):
        """
        Tests reading flash Data Range (0x22) and initiates historical offload batch (0x16/0x17).
        """
        if not self.connection_mgr or not self.connection_mgr.is_connected:
            print("[!] Must be connected to test historical offload.")
            return

        print(f"\n[*] Testing NAND Flash Historical Offload (0x22 -> 0x16 -> 0x17 Auto-ACK)...")

        # Step 1: Query Range
        dr = await self.puffin_controller.get_data_range(b3=0x00)
        avail = dr.get("total_records_available")
        print(f"[+] Flash Data Range: Available Records: {avail} | Range: {dr.get('start_utc')} -> {dr.get('end_utc')}")

        # Step 2: Trigger offload
        self.collected_historical_records.clear()
        print(f"[*] Sending 0x16 SEND_HISTORICAL and listening on fd4b0005 for {duration_seconds}s...")
        try:
            resp_16 = await self.puffin_controller.trigger_historical_offload(b3=0x00)
            print(f"    0x16 Response Status: {resp_16.get('is_success')}")
        except Exception as e:
            print(f"    [!] Note on 0x16: {e}")

        for _ in range(duration_seconds):
            if not self.connection_mgr.is_connected:
                break
            await asyncio.sleep(1.0)

        print(f"[+] Historical offload batch finished. Received {len(self.collected_historical_records)} record(s).")
        print(f"    Cursor ACK packets sent: {self.puffin_engine.stats.get('cursor_packets', 0)}")

    async def run_full_task02_suite(self, duration_live: int = 15, duration_hist: int = 8):
        """
        Runs the full automated test suite for Task 02:
        1. Connects to device
        2. GATT exploration & standard data
        3. Deep Strap Connection & Full Hardware Unlock (0x91, 0x8D, 0x0B, 0x1A, 16 FF, 0x22)
        4. Proprietary Live Stream (0x28) with true ON-WRIST / OFF-WRIST verification
        5. Historical Data Offload test (0x16/0x17 Auto-ACK)
        6. Clean disconnect & Comprehensive report export
        """
        print("\n" + "=" * 75)
        print(" [TASK 02] STARTING FULL AUTOMATED DEEP CONNECTION & UNLOCK SUITE")
        print("=" * 75)

        if not await self.connect():
            print("[!] Could not connect to target device.")
            return

        # 1. Standard Info & GATT
        await self.explore_gatt()
        await self.read_standard_data()

        # 2. Deep Connection & Unlock
        unlock_report = await self.run_deep_connect()

        # 3. Live Puffin Monitoring
        await self.stream_puffin_live(duration_seconds=duration_live)

        # 4. Historical Offload Test
        await self.test_historical_offload(duration_seconds=duration_hist)

        # 5. Export Task 02 Complete Report
        summary_data = {
            "task": "TASK_02_DEEP_STRAP_CONNECTION_AND_FULL_HARDWARE_UNLOCK",
            "device_address": self.selected_device.address,
            "session_id": self.logger.session_id,
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "unlock_report": unlock_report,
            "live_monitoring": {
                "total_packets": len(self.collected_live_hr_packets),
                "packets_sample": self.collected_live_hr_packets[:10],
            },
            "historical_offload": {
                "total_records": len(self.collected_historical_records),
                "records_sample": self.collected_historical_records[:5],
            },
            "puffin_engine_stats": self.puffin_engine.stats if self.puffin_engine else {},
        }

        os.makedirs("exports", exist_ok=True)
        report_path = os.path.join("exports", f"task02_full_report_{self.logger.session_id}.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2, default=str)

        print("\n" + "=" * 75)
        print(f"[+] TASK 02 COMPLETE REPORT EXPORTED TO: {report_path}")
        print(f"[+] Raw Hex Packets CSV: {self.logger.csv_packets_file}")
        print("=" * 75)

        await self.disconnect()

    # -------------------------------------------------------------------------
    # TASK 03 SQLITE SYNC & ON-DEVICE BIOMETRIC DSP METHODS
    # -------------------------------------------------------------------------

    async def run_sync_db(self, duration_seconds: int = 45, max_chunks: Optional[int] = None) -> Dict[str, Any]:
        """
        Executes Task 03 Historical Sync directly into data/whoop_local.db:
        1. Connects to device
        2. Unlocks device session & clock
        3. Initializes HistoricalSyncManager with SQLite database
        4. Runs high-speed historical offload with live deduplication stats
        5. Updates checkpoints in 'devices' table
        6. Clean disconnect
        """
        if not await self.connect():
            print("[!] Could not connect to target device.")
            return {}

        # Ensure session is opened & feature flags unlocked
        print("\n[*] Performing Hardware Unlock and Session Handshake...")
        sn = "5A00479315"
        try:
            unlock_report = await self.puffin_controller.run_full_bootstrap_unlock()
            parsed_sn = unlock_report.get("hello_response", {}).get("parsed", {}).get("serial_number")
            if parsed_sn:
                sn = parsed_sn
            print(f"[+] Bootstrap Unlock Complete. Serial: {sn} | Clock: {unlock_report.get('clock', {}).get('clock_utc')}")
        except Exception as e:
            print(f"[!] Warning during bootstrap unlock: {e}")

        # Register / update device in DB
        self.db.upsert_device(
            serial_number=sn,
            mac_address=self.selected_device.address,
            model="WHOOP 5WP",
            fw_revision="50.41.1.0",
        )

        # Initialize Sync Manager
        self.sync_mgr = HistoricalSyncManager(
            engine=self.puffin_engine,
            controller=self.puffin_controller,
            db=self.db,
            serial_number=sn,
        )

        sync_result = await self.sync_mgr.run_sync(
            duration_seconds=duration_seconds,
            max_chunks=max_chunks,
        )

        await self.disconnect()
        return sync_result

    def run_analyze_local_db(self, serial_number: Optional[str] = None) -> Dict[str, Any]:
        """
        Runs on-device Biometrics DSP Engine on records stored in data/whoop_local.db:
        - Recovery (0-100%)
        - Strain (0.0-21.0)
        - HRV RMSSD (Task Force 1996 standard)
        - RHR (5-10th percentile sustained)
        - Sleep Staging & Performance (0-100%)
        - Respiratory Rate (RSA in 0.15-0.40 Hz band)
        - Real-Time Stress Monitor (0.0-3.0 with movement decoupling)
        - Full Database & Deduplication metrics
        """
        db_stats = self.db.get_db_stats(serial_number)
        devices = db_stats.get("registered_devices", [])
        sn = serial_number or (devices[0]["serial_number"] if devices else "5A00479315")

        records_1hz = self.db.get_records_range(sn)
        valid_rrs = self.db.get_rr_intervals(sn, valid_only=True)

        if not records_1hz:
            print(f"\n[!] No records found in {self.db.db_path} for device {sn}.")
            print("    Run '--sync-db' first to offload historical records from the strap.")
            return {"status": "NO_DATA", "db_stats": db_stats}

        # Run Biometrics Pipeline
        bio_result = self.biometrics.run_full_pipeline(
            serial_number=sn,
            records_1hz=records_1hz,
            rr_intervals_valid=valid_rrs,
        )

        # Print Biometrics Dashboard
        rec = bio_result["recovery"]
        strain_info = bio_result["strain"]
        sleep_info = bio_result["sleep"]
        stress_info = bio_result["stress"]

        print("\n" + "=" * 78)
        print("          ON-DEVICE BIOMETRIC DSP DASHBOARD (WHOOP LOCAL SQLITE)          ")
        print("=" * 78)
        print(f" Target Device Serial       : {sn}")
        print(f" Database Storage Engine    : {db_stats['db_path']} (WAL Mode)")
        print(f" Total Records Analyzed     : {len(records_1hz)} samples ({db_stats['timespan_seconds']}s / {db_stats['timespan_hours']}h)")
        print("-" * 78)

        # 1. Recovery
        rec_color_tag = f"[{rec['recovery_state']}]"
        print(f" >>> RECOVERY SCORE         : {rec['recovery_score']}% {rec_color_tag:<8} (Autonomic Readiness)")
        print(f"     - Nocturnal HRV (RMSSD): {rec['hrv_rmssd_ms']} ms (Task Force 1996 standard, Z-score: {rec['factors']['hrv_z_score']:+.2f})")
        print(f"     - Resting HR (RHR)     : {rec['resting_hr_bpm']} BPM (5-10th percentile sustained, Z-score: {rec['factors']['rhr_z_score']:+.2f})")
        print(f"     - Sleep Performance    : {rec['sleep_performance_pct']}% (Efficiency: {sleep_info['sleep_efficiency_pct']}%)")
        print(f"     - Skin Temperature     : {rec['skin_temp_c']} deg C (Baseline Delta: {rec['factors']['temp_delta_c']:+.2f} deg C)")
        print("-" * 78)

        # 2. Cardiovascular Strain
        print(f" >>> DAY STRAIN             : {strain_info['day_strain']} / 21.0 (Logarithmic Cardiovascular Load)")
        print(f"     - Max Heart Rate       : {strain_info['max_hr_bpm']} BPM | Average HR: {strain_info['avg_hr_bpm']} BPM")
        zones = strain_info["zone_durations_seconds"]
        z1_m, z2_m, z3_m, z4_m, z5_m = [round(zones.get(f"zone{i}", 0) / 60.0, 1) for i in range(1, 6)]
        print(f"     - Zone 1 (Recovery 50-60%): {z1_m:<5} min | Zone 2 (Base 60-70%): {z2_m:<5} min")
        print(f"     - Zone 3 (Endurance 70-80%): {z3_m:<5} min | Zone 4 (Threshold 80-90%): {z4_m:<5} min | Zone 5: {z5_m} min")
        print(f"     - Auto-Detected Workouts: {strain_info['workouts_detected_count']} session(s)")
        for idx, w in enumerate(strain_info["workouts"]):
            print(f"       * Workout #{idx+1}: {w['duration_seconds']//60}m | Strain: {w['workout_strain']} | {w['calories_kcal']} kcal ({w['kilojoules']} kJ) | Avg HR: {w['avg_hr_bpm']} BPM")
        print("-" * 78)

        # 3. Sleep & Respiratory Rate
        st_pct = sleep_info["stage_percentages"]
        print(f" >>> SLEEP & RECOVERY PHYSIOLOGY:")
        print(f"     - Total Sleep Time (TST): {sleep_info['sleep_duration_hours']}h / Need: {sleep_info['sleep_need_hours']}h (Performance: {sleep_info['sleep_performance_pct']}%)")
        print(f"     - Sleep Efficiency     : {sleep_info['sleep_efficiency_pct']}%")
        print(f"     - Deep Sleep (SWS)     : {st_pct.get('deep', 0.0)}% | REM Sleep: {st_pct.get('rem', 0.0)}% | Light: {st_pct.get('light', 0.0)}% | Awake: {st_pct.get('awake', 0.0)}%")
        print(f"     - Respiratory Rate     : {bio_result['respiratory_rate_rpm']} breaths/min (RSA Autocorrelation, 0.15-0.40 Hz band)")
        print("-" * 78)

        # 4. Stress
        print(f" >>> REAL-TIME STRESS MONITOR:")
        print(f"     - Average Stress Score : {stress_info['avg_stress_score']} / 3.0 [{stress_info['stress_category']}]")
        print(f"     - Movement Decoupling  : ACTIVE (Motion-induced HR surges filtered from autonomic score)")
        print("-" * 78)

        # 5. Database & Deduplication
        total_1hz = db_stats.get("total_1hz_records", 0)
        tot_rr = db_stats.get("total_rr_intervals", 0)
        valid_rr = db_stats.get("valid_rr_intervals", 0)
        invalid_rr = db_stats.get("invalid_rr_intervals", 0)
        acc_rate = db_stats.get("rr_physiological_acceptance_rate_pct", 0.0)
        print(f" >>> DATABASE & DEDUPLICATION METRICS:")
        print(f"     - Total 1Hz Records    : {total_1hz} unique records stored (1 per second guaranteed)")
        print(f"     - On-Wrist Valid Samples: {db_stats['on_wrist_records']} | Off-Wrist: {db_stats['off_wrist_records']}")
        print(f"     - Beat-by-Beat RR Count: {tot_rr} intervals stored")
        print(f"     - Valid Physiological  : {valid_rr} beats ({acc_rate}% acceptance rate)")
        print(f"     - Ectopic/Noise Gated  : {invalid_rr} beats ({round(100.0 - acc_rate, 2)}% rejected by Physiological Gate)")
        print(f"     - 24Hz PPG Waveforms   : {db_stats['total_ppg_waveforms']} packets")
        print("=" * 78)

        # Save daily cycle into DB
        today_str = datetime.date.today().isoformat()
        cycle_payload = {
            "serial_number": sn,
            "date": today_str,
            "recovery_score": rec["recovery_score"],
            "recovery_state": rec["recovery_state"],
            "hrv_rmssd_ms": rec["hrv_rmssd_ms"],
            "resting_hr_bpm": rec["resting_hr_bpm"],
            "day_strain": strain_info["day_strain"],
            "sleep_performance_pct": sleep_info["sleep_performance_pct"],
            "sleep_duration_seconds": sleep_info["total_sleep_time_seconds"],
            "respiratory_rate_rpm": bio_result["respiratory_rate_rpm"],
            "skin_temp_c": rec["skin_temp_c"],
            "avg_stress": stress_info["avg_stress_score"],
            "metrics": bio_result,
        }
        self.db.save_daily_cycle(cycle_payload)

        # Save workouts into DB
        for w in strain_info["workouts"]:
            self.db.save_workout(w)

        # Export JSON
        os.makedirs("exports", exist_ok=True)
        export_file = os.path.join("exports", f"biometrics_report_{self.logger.session_id}.json")
        full_report = {
            "task": "TASK_03_SQLITE_PERSISTENCE_DEDUPLICATION_AND_ON_DEVICE_BIOMETRIC_DSP",
            "session_id": self.logger.session_id,
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "serial_number": sn,
            "biometrics": bio_result,
            "db_stats": db_stats,
        }
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(full_report, f, indent=2, default=str)
        print(f"\n[+] Full Biometrics Report exported to: {export_file}")

        return full_report

    async def interactive_menu(self):
        self.print_banner()

        while True:
            conn_status = "CONNECTED" if (self.connection_mgr and self.connection_mgr.is_connected) else "DISCONNECTED"
            dev_str = f"{self.selected_device.name} ({self.selected_device.address})" if self.selected_device else "None"

            print("\n" + "-" * 60)
            print(f" TARGET: {dev_str} | STATUS: {conn_status}")
            print("-" * 60)
            print(" 1. Scan for BLE devices")
            print(" 2. Select device to analyze")
            print(" 3. Connect to selected device")
            print(" 4. Disconnect")
            print(" 5. Explore GATT Table")
            print(" 6. Read Battery & Device Info (Standard)")
            print(" 7. Stream Standard Heart Rate (0x2A37, Direct ms RR)")
            print(" 8. [TASK 02] Deep Connect & Hardware Unlock (fd4b: Hello, Clock, Battery, 16 FF, Range)")
            print(" 9. [TASK 02] Proprietary Live Stream (0x28: Real On-Wrist / Off-Wrist)")
            print("10. [TASK 02] Flash Historical Range (0x22) & Batch Offload Test (0x16/0x17)")
            print("11. [TASK 02] RUN FULL AUTOMATED TASK 02 SUITE")
            print("12. Export Logs & Session Summary")
            print("13. [TASK 03] Sync Historical Data into SQLite DB (with Deduplication)")
            print("14. [TASK 03] Run On-Device Biometric DSP Analysis (Recovery, Strain, Sleep, Stress)")
            print(" 0. Exit")
            print("-" * 60)

            choice = input("Enter choice [0-14]: ").strip()

            if choice == "1":
                await self.run_scan(duration=6.0)
            elif choice == "2":
                if not self.last_discovered_devices:
                    print("[!] Run a scan first (Option 1).")
                    continue
                idx_str = input(f"Enter device number (1-{len(self.last_discovered_devices)}): ").strip()
                if idx_str.isdigit():
                    self.select_device(int(idx_str))
            elif choice == "3":
                await self.connect()
            elif choice == "4":
                await self.disconnect()
            elif choice == "5":
                await self.explore_gatt()
            elif choice == "6":
                await self.read_standard_data()
            elif choice == "7":
                dur_str = input("Stream duration in seconds (default 10): ").strip()
                dur = int(dur_str) if dur_str.isdigit() else 10
                await self.stream_heart_rate_standard(duration_seconds=dur)
            elif choice == "8":
                await self.run_deep_connect()
            elif choice == "9":
                dur_str = input("Live stream duration in seconds (default 15): ").strip()
                dur = int(dur_str) if dur_str.isdigit() else 15
                await self.stream_puffin_live(duration_seconds=dur)
            elif choice == "10":
                dur_str = input("Offload test duration in seconds (default 10): ").strip()
                dur = int(dur_str) if dur_str.isdigit() else 10
                await self.test_historical_offload(duration_seconds=dur)
            elif choice == "11":
                if not self.selected_device:
                    print("[!] Please select a target device first.")
                    continue
                await self.run_full_task02_suite()
            elif choice == "12":
                os.makedirs("exports", exist_ok=True)
                summary_path = os.path.join("exports", f"summary_{self.logger.session_id}.json")
                self.logger.export_summary_json(summary_path, gatt_structure=self.latest_gatt_tree, sanitize=True)
                print(f"[+] Summary JSON exported to: {summary_path}")
            elif choice == "13":
                if not self.selected_device:
                    print("[!] Please select a target device first.")
                    continue
                dur_str = input("Sync duration in seconds (default 45): ").strip()
                dur = int(dur_str) if dur_str.isdigit() else 45
                await self.run_sync_db(duration_seconds=dur)
            elif choice == "14":
                self.run_analyze_local_db()
            elif choice == "0":
                print("[*] Exiting toolkit...")
                await self.disconnect()
                break
            else:
                print("[!] Unknown option, please try again.")


async def main_cli():
    parser = argparse.ArgumentParser(description="WHOOP 5.0 BLE Reverse Engineering & Diagnostics Toolkit")
    parser.add_argument("--scan", action="store_true", help="Scan for BLE devices and list them")
    parser.add_argument("--scan-duration", type=float, default=6.0, help="Scan duration in seconds")
    parser.add_argument("--address", type=str, help="Target device Bluetooth Address / UUID to connect directly")
    parser.add_argument("--deep-connect", action="store_true", help="Execute Task 02 Deep Strap Connection & Full Hardware Unlock")
    parser.add_argument("--puffin-live", action="store_true", help="Monitor proprietary Live HR (0x28) with on-wrist detection")
    parser.add_argument("--puffin-duration", type=int, default=15, help="Proprietary live stream duration in seconds")
    parser.add_argument("--history-test", action="store_true", help="Test Flash Data Range (0x22) and batch historical offload")
    parser.add_argument("--auto", action="store_true", help="Run full automated Task 02 suite")
    parser.add_argument("--sync-db", type=int, nargs="?", const=45, default=None, help="Sync historical records directly into SQLite DB for N seconds (default 45s)")
    parser.add_argument("--max-chunks", type=int, default=None, help="Optional maximum historical records/chunks to offload during sync")
    parser.add_argument("--analyze", action="store_true", help="Run on-device Biometrics DSP Engine on records stored in SQLite DB")

    args = parser.parse_args()
    app = WhoopDiagnosticApp()

    # Offline analysis requested
    if args.analyze and args.sync_db is None and not args.auto and not args.deep_connect and not args.puffin_live:
        app.print_banner()
        app.run_analyze_local_db()
        return

    if args.scan and not args.address and not args.deep_connect and not args.auto and args.sync_db is None:
        app.print_banner()
        await app.run_scan(duration=args.scan_duration)
        return

    # Default target if requested
    target_addr = args.address or ("FD:49:44:66:1D:92" if (args.deep_connect or args.auto or args.puffin_live or args.history_test or args.sync_db is not None) else None)

    if target_addr:
        app.print_banner()
        from bleak.backends.device import BLEDevice
        mock_dev = BLEDevice(address=target_addr, name="Target Device", details=None)
        app.selected_device = DiscoveredBLEDevice(mock_dev, None)

        if args.sync_db is not None:
            await app.run_sync_db(duration_seconds=args.sync_db, max_chunks=args.max_chunks)
            if args.analyze:
                app.run_analyze_local_db()
            return

        if args.auto:
            await app.run_full_task02_suite(duration_live=args.puffin_duration)
            return

        if args.deep_connect:
            if await app.connect():
                await app.run_deep_connect()
                if args.puffin_live:
                    await app.stream_puffin_live(duration_seconds=args.puffin_duration)
                if args.history_test:
                    await app.test_historical_offload(duration_seconds=10)
                await app.disconnect()
            return

        if args.puffin_live:
            if await app.connect():
                await app.stream_puffin_live(duration_seconds=args.puffin_duration)
                await app.disconnect()
            return

        if args.history_test:
            if await app.connect():
                await app.test_historical_offload(duration_seconds=10)
                await app.disconnect()
            return

        # Direct explore if just address
        if await app.connect():
            await app.explore_gatt()
            await app.read_standard_data()
            await app.disconnect()
        return

    # Interactive menu
    await app.interactive_menu()


if __name__ == "__main__":
    try:
        asyncio.run(main_cli())
    except KeyboardInterrupt:
        print("\n[*] Interrupted by user. Exiting.")
