"""
WHOOP 5.0 BLE Reverse Engineering & Diagnostics Toolkit
Package initialization.
"""

from whoop_ble.puffin_framing import (
    crc16_modbus,
    crc32_ieee,
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
from whoop_ble.puffin_engine import PuffinEngine, PuffinCommandError, PuffinSafetyViolation
from whoop_ble.puffin_commands import PuffinDeviceController
from whoop_ble.database import WhoopDatabase
from whoop_ble.biometrics import BiometricsEngine
from whoop_ble.sync_manager import HistoricalSyncManager

__version__ = "3.0.0"
