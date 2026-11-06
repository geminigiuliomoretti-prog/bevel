"""
Diagnostics, Event Logging and Packet Capture Subsystem.
Complies with FASE E requirements:
- UTC and Local timestamps
- Session duration tracking
- Raw BLE packet logging (hex)
- Decoded values logging
- GATT errors and disconnection tracking
- Privacy sanitization (masking serials/personal IDs)
- JSON and CSV exporters
"""

import os
import csv
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def mask_identifier(ident: Optional[str]) -> str:
    """Mask serials and personal IDs for privacy/shareable reports."""
    if not ident:
        return "N/A"
    s = str(ident).strip()
    if len(s) <= 4:
        return "***"
    return f"{s[:2]}***{s[-2:]}"


class DiagnosticLogger:
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

        self.session_start_utc = datetime.now(timezone.utc)
        self.session_id = self.session_start_utc.strftime("%Y%m%d_%H%M%S")
        self.session_file = os.path.join(self.log_dir, f"session_{self.session_id}.jsonl")
        self.csv_packets_file = os.path.join(self.log_dir, f"packets_{self.session_id}.csv")
        self.text_log_file = os.path.join(self.log_dir, f"diagnostics_{self.session_id}.log")

        # Setup python logging to file and console
        self._setup_internal_logging()

        # Initialize CSV file with headers
        with open(self.csv_packets_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "utc_timestamp",
                "local_timestamp",
                "device_id",
                "characteristic_uuid",
                "characteristic_name",
                "raw_hex",
                "byte_length",
                "decoded_summary",
                "rssi",
            ])

        self.events: List[Dict[str, Any]] = []
        self.log_event("SESSION_START", {"session_id": self.session_id})

    def _setup_internal_logging(self):
        self.logger = logging.getLogger(f"whoop_ble_{self.session_id}")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()

        # File handler
        fh = logging.FileHandler(self.text_log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh_fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
        fh.setFormatter(fh_fmt)
        self.logger.addHandler(fh)

        # Stream handler (console)
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh_fmt = logging.Formatter("[%(levelname)s] %(message)s")
        sh.setFormatter(sh_fmt)
        self.logger.addHandler(sh)

    def _timestamps(self) -> Dict[str, str]:
        now_utc = datetime.now(timezone.utc)
        now_local = datetime.now()
        return {
            "utc": now_utc.isoformat(),
            "local": now_local.isoformat(),
        }

    def get_session_duration_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.session_start_utc).total_seconds()

    def log_event(self, event_type: str, details: Optional[Dict[str, Any]] = None):
        ts = self._timestamps()
        payload = {
            "event_type": event_type,
            "timestamp_utc": ts["utc"],
            "timestamp_local": ts["local"],
            "session_duration_seconds": round(self.get_session_duration_seconds(), 2),
            "details": details or {},
        }
        self.events.append(payload)

        # Append to JSONL file
        try:
            with open(self.session_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            self.logger.error(f"Failed to write event to JSONL: {e}")

        # Internal logger log
        self.logger.info(f"[{event_type}] {json.dumps(details, ensure_ascii=False, default=str)}")

    def log_connection_state(self, device_address: str, device_name: Optional[str], state: str, rssi: Optional[int] = None):
        self.log_event("CONNECTION_STATE_CHANGE", {
            "device_address": device_address,
            "device_name": device_name,
            "state": state,
            "rssi": rssi,
        })

    def log_gatt_error(self, operation: str, error_message: str, characteristic_uuid: Optional[str] = None):
        self.logger.error(f"GATT Error during {operation}: {error_message} (Char: {characteristic_uuid})")
        self.log_event("GATT_ERROR", {
            "operation": operation,
            "error": str(error_message),
            "characteristic_uuid": characteristic_uuid,
        })

    def log_packet(
        self,
        device_address: str,
        characteristic_uuid: str,
        characteristic_name: str,
        raw_bytes: bytes,
        decoded_data: Optional[Dict[str, Any]] = None,
        rssi: Optional[int] = None,
    ):
        ts = self._timestamps()
        hex_data = raw_bytes.hex().upper()
        summary = json.dumps(decoded_data, ensure_ascii=False, default=str) if decoded_data else "Raw data"

        entry = {
            "timestamp_utc": ts["utc"],
            "timestamp_local": ts["local"],
            "device_address": device_address,
            "characteristic_uuid": characteristic_uuid,
            "characteristic_name": characteristic_name,
            "raw_hex": hex_data,
            "raw_length": len(raw_bytes),
            "decoded_data": decoded_data,
            "rssi": rssi,
        }

        self.log_event("BLE_PACKET_RECEIVED", entry)

        # Append to CSV
        try:
            with open(self.csv_packets_file, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    ts["utc"],
                    ts["local"],
                    device_address,
                    characteristic_uuid,
                    characteristic_name,
                    hex_data,
                    len(raw_bytes),
                    summary,
                    rssi if rssi is not None else "",
                ])
        except Exception as e:
            self.logger.error(f"Failed to append packet to CSV: {e}")

    def export_summary_json(self, destination_path: str, gatt_structure: Optional[Dict[str, Any]] = None, sanitize: bool = True) -> str:
        """Export comprehensive session log to a single JSON file."""
        duration = self.get_session_duration_seconds()
        export_data = {
            "session_id": self.session_id,
            "start_time_utc": self.session_start_utc.isoformat(),
            "export_time_utc": datetime.now(timezone.utc).isoformat(),
            "session_duration_seconds": round(duration, 2),
            "total_events": len(self.events),
            "gatt_structure": gatt_structure or {},
            "events": self.events,
        }

        if sanitize:
            # Mask sensitive values in export
            export_data = self._sanitize_dict(export_data)

        with open(destination_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Summary JSON exported to {destination_path}")
        return destination_path

    def _sanitize_dict(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            new_dict = {}
            for k, v in obj.items():
                if "serial" in k.lower() or "identifier" in k.lower():
                    new_dict[k] = mask_identifier(str(v))
                else:
                    new_dict[k] = self._sanitize_dict(v)
            return new_dict
        elif isinstance(obj, list):
            return [self._sanitize_dict(item) for item in obj]
        return obj
