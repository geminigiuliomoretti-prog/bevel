"""
Unit tests for WHOOP Gen 5 Puffin Packet Decoder.
"""

import sys
import os
import struct
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from whoop_ble.puffin_framing import build_frame
from whoop_ble.puffin_decoder import (
    decode_puffin_packet,
    decode_live_hr_0x28,
    decode_response_0x24,
    decode_historical_record_0x2F,
    decode_cursor_metadata_0x31,
)


def test_decode_live_hr_0x28():
    # 0x28 packet:
    # byte 0: 0x28
    # byte 1: 0x00
    # bytes 2..5: Unix TS (e.g. 1730000000 -> 0x671C6780 LE)
    # bytes 6..7: 0x00 0x00
    # byte 8: HR = 72
    # byte 9: On-wrist flag = 1 (ON_WRIST_VALID)
    # bytes 10..11: RR ms = 833 (0x0341 LE -> 41 03)
    payload = bytearray(12)
    payload[0] = 0x28
    struct.pack_into("<I", payload, 2, 1730000000)
    payload[8] = 72
    payload[9] = 1
    struct.pack_into("<H", payload, 10, 833)

    res = decode_live_hr_0x28(bytes(payload))
    assert res["type"] == "LIVE_HR"
    assert res["heart_rate_bpm"] == 72
    assert res["on_wrist_state"] == "ON_WRIST_VALID"
    assert res["is_on_wrist"] is True
    assert res["rr_ms"] == 833
    assert res["timestamp_unix"] == 1730000000

    # Off-wrist test
    payload[8] = 0
    payload[9] = 0
    res_off = decode_live_hr_0x28(bytes(payload))
    assert res_off["on_wrist_state"] == "OFF_WRIST"
    assert res_off["is_on_wrist"] is False


def test_decode_response_0x24():
    # Echo seq = 5, resp_cmd = 0x8D (name), strap_seq = 1, status = 0 (success), payload = "WHOOP 5WP\x00"
    name_bytes = b"WHOOP 5WP\x00"
    resp = bytes([0x24, 0x05, 0x8D, 0x01, 0x00]) + name_bytes
    decoded = decode_response_0x24(resp)
    assert decoded["echo_seq"] == 5
    assert decoded["resp_cmd"] == 0x8D
    assert decoded["is_success"] is True
    assert decoded["parsed"]["advertising_name"] == "WHOOP 5WP"

    # Clock test: 0x0B
    clock_resp = bytes([0x24, 0x06, 0x0B, 0x02, 0x00]) + struct.pack("<I", 1730810000)
    dec_clock = decode_response_0x24(clock_resp)
    assert dec_clock["parsed"]["is_clock_latched"] is True
    assert dec_clock["parsed"]["clock_unix"] == 1730810000

    # Data range: 0x22
    range_resp = bytes([0x24, 0x07, 0x22, 0x03, 0x00]) + struct.pack("<IIII", 1000, 1500, 1730000000, 1730050000)
    dec_range = decode_response_0x24(range_resp)
    assert dec_range["parsed"]["start_seq"] == 1000
    assert dec_range["parsed"]["end_seq"] == 1500
    assert dec_range["parsed"]["total_records_available"] == 500


def test_decode_cursor_0x31():
    # 1. Inner payload directly (cursor at inner[5:13])
    inner = bytearray(24)
    inner[0] = 0x31
    cursor_val = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
    inner[5:13] = cursor_val
    dec = decode_cursor_metadata_0x31(bytes(inner))
    assert dec["cursor_hex"] == "0102030405060708"

    # 2. Wire frame with 8-byte envelope header (cursor at frame[13:21])
    frame = build_frame(bytes(inner))
    dec_frame = decode_cursor_metadata_0x31(frame)
    assert dec_frame["cursor_hex"] == "0102030405060708"


def test_decode_historical_v18():
    # Test exact 112-byte inner payload (FW 50.41.1.0)
    inner = bytearray(112)
    inner[0] = 0x2F
    inner[1] = 0x12  # format v18
    struct.pack_into("<H", inner, 2, 42)  # Sequence
    struct.pack_into("<I", inner, 7, 1730000000)  # Timestamp
    inner[14] = 68  # Primary HR
    inner[15] = 2   # rr_count
    struct.pack_into("<H", inner, 16, 880)
    struct.pack_into("<H", inner, 18, 890)
    struct.pack_into("<3f", inner, 37, 0.05, -0.12, 0.98)  # Gravity at inner 37..49 (Frame 45..57)
    struct.pack_into("<H", inner, 57, 120)  # Steps
    struct.pack_into("<h", inner, 61, 335)  # 33.5 C at inner 61..63
    inner[96] = 1   # Sleep state flag
    struct.pack_into("<H", inner, 98, 31000)   # Optical baseline ch1 at inner 98 (Frame 106)
    struct.pack_into("<H", inner, 106, 32500)  # Optical baseline ch2 at inner 106 (Frame 114)

    dec = decode_historical_record_0x2F(bytes(inner))
    assert dec["type"] == "HISTORICAL_RECORD_V18"
    assert dec["sequence"] == 42
    assert dec["primary_hr_bpm"] == 68
    assert dec["rr_count"] == 2
    assert dec["rr_intervals_ms"] == [880, 890]
    assert dec["accel_x"] == 0.05
    assert dec["accel_y"] == -0.12
    assert dec["accel_z"] == 0.98
    assert dec["accel_mag_g"] == round((0.05**2 + (-0.12)**2 + 0.98**2)**0.5, 3)
    assert dec["steps"] == 120
    assert dec["skin_temp_c"] == 33.5
    assert dec["sleep_state"] == 1
    assert dec["optical_baseline"] == 32500
    assert dec["is_on_wrist"] is True


if __name__ == "__main__":
    test_decode_live_hr_0x28()
    test_decode_response_0x24()
    test_decode_cursor_0x31()
    test_decode_historical_v18()
    print("ALL PUFFIN DECODER TESTS PASSED!")
