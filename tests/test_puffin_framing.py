"""
Unit tests for WHOOP Gen 5 Puffin Framing and Stream Reassembler.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from whoop_ble.puffin_framing import (
    crc16_modbus,
    crc32_ieee,
    build_frame,
    PuffinStreamReassembler,
    extract_inner_payload,
)


def test_crcs():
    assert crc16_modbus(b"123456789") == 0x4B37
    assert crc32_ieee(b"123456789") == 0xCBF43926


def test_build_minimum_frame():
    # 4 byte inner payload -> 8 header + 4 inner + 4 crc32 = 16 bytes
    inner = bytes([0x23, 0x01, 0x91, 0x01])
    frame = build_frame(inner)
    assert len(frame) == 16
    assert frame[0:2] == bytes([0xAA, 0x01])
    # payload_len = 8 (4 inner + 4 crc32)
    assert frame[2:4] == bytes([0x08, 0x00])
    # field/role = 1
    assert frame[4:6] == bytes([0x01, 0x00])
    # extracted inner payload
    assert extract_inner_payload(frame) == inner


def test_build_padded_frame():
    # 5 byte inner payload -> padded to 8 bytes -> total 20 bytes
    inner = bytes([0x23, 0x02, 0x78, 0x01, 0x55])
    frame = build_frame(inner)
    assert len(frame) == 20
    # payload_len = 12 (8 inner + 4 crc32)
    assert frame[2:4] == bytes([0x0C, 0x00])
    extracted = extract_inner_payload(frame)
    assert extracted[:5] == inner
    assert extracted[5:] == bytes([0x00, 0x00, 0x00])


def test_stream_reassembler_fragmentation():
    reassembler = PuffinStreamReassembler()
    frame1 = build_frame(bytes([0x23, 0x01, 0x91, 0x01]))
    frame2 = build_frame(bytes([0x23, 0x02, 0x0B, 0x01, 0x11, 0x22, 0x33, 0x44]))

    stream = frame1 + frame2
    # Feed in arbitrary 5-byte chunks
    frames_out = []
    chunk_size = 5
    for i in range(0, len(stream), chunk_size):
        chunk = stream[i : i + chunk_size]
        frames_out.extend(reassembler.feed(chunk))

    assert len(frames_out) == 2
    assert frames_out[0] == frame1
    assert frames_out[1] == frame2


def test_stream_reassembler_false_positive_sof():
    reassembler = PuffinStreamReassembler()
    # Garbage containing 0xAA 0x01 with invalid CRC16
    garbage = bytes([0xDE, 0xAD, 0xAA, 0x01, 0x10, 0x00, 0x01, 0x00, 0x99, 0x99, 0xEE, 0xFF])
    valid_frame = build_frame(bytes([0x23, 0x05, 0x1A, 0x01]))
    stream = garbage + valid_frame

    frames = reassembler.feed(stream)
    assert len(frames) == 1
    assert frames[0] == valid_frame
    assert reassembler.total_crc16_errors >= 1


if __name__ == "__main__":
    test_crcs()
    test_build_minimum_frame()
    test_build_padded_frame()
    test_stream_reassembler_fragmentation()
    test_stream_reassembler_false_positive_sof()
    print("ALL PUFFIN FRAMING TESTS PASSED!")
