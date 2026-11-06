"""
Unit tests for Bluetooth SIG 0x2A37 Heart Rate Measurement Decoder.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from whoop_ble.hr_decoder import decode_heart_rate_measurement


def test_standard_uint8_hr():
    # Flags = 0x00 (UINT8, contact not supported, no energy, no RR), HR = 75 (0x4B)
    raw = bytes([0x00, 0x4B])
    result = decode_heart_rate_measurement(raw)
    assert result["status"] == "DECODED"
    assert result["heart_rate_bpm"] == 75
    assert result["hr_format"] == "UINT8"
    assert result["sensor_contact"]["supported"] is False
    assert result["energy_expended_kj"] == "NOT_AVAILABLE"
    assert result["rr_intervals_count"] == 0


def test_hr_with_contact_and_rr():
    # Flags:
    # Bit 0 = 0 (UINT8)
    # Bit 1-2 = 0b11 (Contact detected, 0x06)
    # Bit 4 = 1 (RR-intervals present, 0x10)
    # Flags = 0x16 (22)
    # HR = 80 (0x50)
    # On WHOOP 5.0, RR intervals are direct milliseconds (uint16 LE)
    # RR1 = 1000 ms -> 0x03E8 -> LE: [0xE8, 0x03]
    # RR2 = 898 ms  -> 0x0382 -> LE: [0x82, 0x03]
    raw = bytes([0x16, 0x50, 0xE8, 0x03, 0x82, 0x03])
    result = decode_heart_rate_measurement(raw)
    assert result["status"] == "DECODED"
    assert result["heart_rate_bpm"] == 80
    assert result["sensor_contact"]["supported"] is True
    assert result["sensor_contact"]["detected"] is True
    assert result["rr_intervals_count"] == 2
    assert result["rr_intervals_raw_ticks"] == [1000, 898]
    assert result["rr_intervals_ms"] == [1000.0, 898.0]


def test_uint16_hr():
    # Flags: Bit 0 = 1 (UINT16 -> 0x01)
    # HR = 280 (0x0118 -> LE: [0x18, 0x01])
    raw = bytes([0x01, 0x18, 0x01])
    result = decode_heart_rate_measurement(raw)
    assert result["status"] == "DECODED"
    assert result["heart_rate_bpm"] == 280
    assert result["hr_format"] == "UINT16"


if __name__ == "__main__":
    test_standard_uint8_hr()
    test_hr_with_contact_and_rr()
    test_uint16_hr()
    print("ALL HR DECODER UNIT TESTS PASSED!")
