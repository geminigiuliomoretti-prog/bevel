"""
Bluetooth SIG Standard Heart Rate Measurement Decoder (UUID: 0x2A37).
Pure Python decoder completely decoupled from BLE transport (ready for Kotlin/Swift migration).

Spec: Bluetooth SIG Heart Rate Service (0x180D), Characteristic (0x2A37)
Byte 0: Flags
  - Bit 0: Heart Rate Value Format (0 = UINT8, 1 = UINT16)
  - Bits 1-2: Sensor Contact Status
      0b00: Not Supported
      0b01: Not Supported
      0b10: Supported, Contact NOT detected
      0b11: Supported, Contact detected
  - Bit 3: Energy Expended Status (0 = Not Present, 1 = Present as UINT16)
  - Bit 4: RR-Interval Status (0 = Not Present, 1 = Present as UINT16 values; on WHOOP 5.0 in direct milliseconds)
  - Bits 5-7: Reserved
"""

import struct
from typing import Any, Dict, List, Optional


class DecodedHeartRateMeasurement:
    def __init__(
        self,
        raw_hex: str,
        heart_rate_bpm: Optional[int],
        hr_format: str,
        sensor_contact_supported: bool,
        sensor_contact_detected: Optional[bool],
        energy_expended_kj: Optional[int],
        rr_intervals_raw: List[int],
        rr_intervals_ms: List[float],
        unparsed_remaining_hex: Optional[str] = None,
    ):
        self.raw_hex = raw_hex
        self.heart_rate_bpm = heart_rate_bpm
        self.hr_format = hr_format
        self.sensor_contact_supported = sensor_contact_supported
        self.sensor_contact_detected = sensor_contact_detected
        self.energy_expended_kj = energy_expended_kj
        self.rr_intervals_raw = rr_intervals_raw
        self.rr_intervals_ms = rr_intervals_ms
        self.unparsed_remaining_hex = unparsed_remaining_hex

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "DECODED",
            "raw_hex": self.raw_hex,
            "heart_rate_bpm": self.heart_rate_bpm,
            "hr_format": self.hr_format,
            "sensor_contact": {
                "supported": self.sensor_contact_supported,
                "detected": self.sensor_contact_detected,
            },
            "energy_expended_kj": self.energy_expended_kj if self.energy_expended_kj is not None else "NOT_AVAILABLE",
            "rr_intervals_count": len(self.rr_intervals_raw),
            "rr_intervals_raw_ticks": self.rr_intervals_raw,
            "rr_intervals_ms": self.rr_intervals_ms,
            "unparsed_bytes_hex": self.unparsed_remaining_hex if self.unparsed_remaining_hex else "NONE",
        }


def decode_heart_rate_measurement(data: bytes) -> Dict[str, Any]:
    """
    Decodes GATT 0x2A37 Heart Rate Measurement payload according to standard Bluetooth SIG specs.
    Handles corrupt/partial data safely without raising unhandled exceptions.
    """
    raw_hex = data.hex().upper()

    if not data or len(data) < 2:
        return {
            "status": "INVALID_PACKET_LENGTH",
            "raw_hex": raw_hex,
            "error": f"Packet too short ({len(data)} bytes, expected >= 2)",
            "heart_rate_bpm": None,
        }

    flags = data[0]
    hr_is_uint16 = bool(flags & 0x01)
    sensor_contact_bits = (flags >> 1) & 0x03
    energy_expended_present = bool(flags & 0x08)
    rr_intervals_present = bool(flags & 0x10)

    # Sensor contact status interpretation
    if sensor_contact_bits == 2:
        sensor_contact_supported = True
        sensor_contact_detected = False
    elif sensor_contact_bits == 3:
        sensor_contact_supported = True
        sensor_contact_detected = True
    else:
        sensor_contact_supported = False
        sensor_contact_detected = None

    offset = 1

    # Heart Rate Value
    if hr_is_uint16:
        if len(data) < offset + 2:
            return {
                "status": "TRUNCATED_PACKET",
                "raw_hex": raw_hex,
                "error": "Truncated 16-bit HR field",
                "heart_rate_bpm": None,
            }
        hr_bpm = struct.unpack_from("<H", data, offset)[0]
        hr_format = "UINT16"
        offset += 2
    else:
        hr_bpm = data[offset]
        hr_format = "UINT8"
        offset += 1

    # Energy Expended field (optional)
    energy_kj: Optional[int] = None
    if energy_expended_present:
        if len(data) >= offset + 2:
            energy_kj = struct.unpack_from("<H", data, offset)[0]
            offset += 2
        else:
            energy_kj = None

    # RR-Intervals (optional, 0 or more UINT16 values)
    # FIX TASK 02: On WHOOP 5.0, RR intervals transmitted on 0x2A37 are expressed
    # directly in milliseconds (uint16 LE = direct ms) and NOT in 1/1024s units.
    rr_intervals_raw: List[int] = []
    rr_intervals_ms: List[float] = []

    if rr_intervals_present:
        while offset + 1 < len(data):
            rr_val = struct.unpack_from("<H", data, offset)[0]
            rr_intervals_raw.append(rr_val)
            # WHOOP 5.0 direct millisecond interpretation (eliminates -2.3% error)
            ms = float(rr_val)
            rr_intervals_ms.append(ms)
            offset += 2

    # Check for unparsed remaining bytes
    unparsed_hex: Optional[str] = None
    if offset < len(data):
        unparsed_hex = data[offset:].hex().upper()

    decoded = DecodedHeartRateMeasurement(
        raw_hex=raw_hex,
        heart_rate_bpm=hr_bpm,
        hr_format=hr_format,
        sensor_contact_supported=sensor_contact_supported,
        sensor_contact_detected=sensor_contact_detected,
        energy_expended_kj=energy_kj,
        rr_intervals_raw=rr_intervals_raw,
        rr_intervals_ms=rr_intervals_ms,
        unparsed_remaining_hex=unparsed_hex,
    )

    return decoded.to_dict()
