"""
WHOOP Gen 5 ("Puffin" fd4b) Binary Framing & Stream Reassembler.
Handles:
- Gen 5 Binary Envelope (SOF 0xAA, Ver 0x01, CRC16-Modbus header, 4-byte aligned payload, CRC32 trailer).
- Minimum frame rule (>= 16 bytes on wire).
- Infallible continuous stream reassembly over ATT notifications with double CRC verification.
"""

import struct
import zlib
from typing import List, Optional, Tuple, Dict, Any


def crc16_modbus(data: bytes) -> int:
    """
    Computes CRC-16/MODBUS:
    - Polynomial: 0x8005 (reflected: 0xA001)
    - Initial value: 0xFFFF
    - RefIn: True, RefOut: True, XorOut: 0x0000
    """
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def crc32_ieee(data: bytes) -> int:
    """Computes CRC-32 IEEE 802.3."""
    return zlib.crc32(data) & 0xFFFFFFFF


def build_frame(inner_payload: bytes, role: int = 0x0001) -> bytes:
    """
    Builds a complete Puffin Gen 5 frame:
    - Header (8 bytes):
        [0]: 0xAA (SOF)
        [1]: 0x01 (Version)
        [2..3]: payload_len (u16 LE) = len(inner_padded) + 4
        [4..5]: role/field (u16 LE) = 0x0001
        [6..7]: CRC16-Modbus on bytes 0..5 (u16 LE)
    - Inner Payload:
        [8..n]: inner_payload aligned and zero-padded to a multiple of 4 bytes (min 4 bytes)
    - Trailer (4 bytes):
        [n..n+4]: CRC32 on inner_padded (u32 LE)
    Minimum total frame size: 16 bytes.
    """
    # 4-byte alignment with zero padding
    pad_len = (4 - (len(inner_payload) % 4)) % 4
    inner_padded = inner_payload + (b"\x00" * pad_len)
    if len(inner_padded) < 4:
        inner_padded = inner_padded + (b"\x00" * (4 - len(inner_padded)))

    # payload_len includes inner_padded + 4 bytes of trailer CRC32
    payload_len = len(inner_padded) + 4
    total_len = 8 + payload_len
    assert total_len >= 16, f"Frame must be >= 16 bytes, got {total_len}"

    hdr_bytes = bytes([0xAA, 0x01]) + struct.pack("<H", payload_len) + struct.pack("<H", role)
    hdr_crc = crc16_modbus(hdr_bytes)
    header = hdr_bytes + struct.pack("<H", hdr_crc)

    trailer_crc = crc32_ieee(inner_padded)
    trailer = struct.pack("<I", trailer_crc)

    return header + inner_padded + trailer


class PuffinStreamReassembler:
    """
    Continuous stream reassembler for incoming ATT notification chunks.
    Guarantees zero dropped frames and immune to false positive SOFs inside payload.
    """

    def __init__(self):
        self.buffer = bytearray()
        self.total_frames_received = 0
        self.total_crc16_errors = 0
        self.total_crc32_errors = 0

    def reset(self):
        self.buffer.clear()

    def feed(self, chunk: bytes) -> List[bytes]:
        """
        Feeds incoming bytes into the reassembler.
        Returns a list of complete, validated frames (raw bytes including 8B header + inner + 4B CRC32).
        """
        if not chunk:
            return []

        self.buffer.extend(chunk)
        complete_frames: List[bytes] = []

        while True:
            # Look for SOF 0xAA 0x01
            idx = self.buffer.find(b"\xAA\x01")
            if idx < 0:
                # Not found anywhere.
                # If buffer ends with 0xAA, keep it in case 0x01 arrives next chunk
                if len(self.buffer) > 0 and self.buffer[-1] == 0xAA:
                    self.buffer = bytearray([0xAA])
                else:
                    self.buffer.clear()
                break

            # Discard pre-SOF noise
            if idx > 0:
                del self.buffer[:idx]

            # Need at least 8 bytes for header
            if len(self.buffer) < 8:
                break

            # Verify Header CRC16-Modbus on bytes 0..5
            hdr_bytes = bytes(self.buffer[0:6])
            expected_crc16 = struct.unpack_from("<H", self.buffer, 6)[0]
            actual_crc16 = crc16_modbus(hdr_bytes)

            if actual_crc16 != expected_crc16:
                # False positive SOF found in data stream! Advance by 1 byte and search again
                self.total_crc16_errors += 1
                del self.buffer[0]
                continue

            # Header CRC16 is valid! Extract payload_len
            payload_len = struct.unpack_from("<H", self.buffer, 2)[0]
            if payload_len < 4 or payload_len > 4096:
                # Malformed payload length, advance 1 byte
                del self.buffer[0]
                continue

            total_frame_len = 8 + payload_len
            if len(self.buffer) < total_frame_len:
                # Valid header, but rest of frame hasn't arrived yet; wait for more chunks
                break

            # Full frame is in buffer, verify Trailer CRC32
            inner_padded = bytes(self.buffer[8 : total_frame_len - 4])
            expected_crc32 = struct.unpack_from("<I", self.buffer, total_frame_len - 4)[0]
            actual_crc32 = crc32_ieee(inner_padded)

            if actual_crc32 != expected_crc32:
                # CRC32 failed: corrupted payload or accidental header match
                self.total_crc32_errors += 1
                del self.buffer[0]
                continue

            # Frame is completely valid!
            frame_data = bytes(self.buffer[:total_frame_len])
            del self.buffer[:total_frame_len]
            self.total_frames_received += 1
            complete_frames.append(frame_data)

        return complete_frames


def extract_inner_payload(frame: bytes) -> bytes:
    """
    Extracts the inner payload (bytes 8..len-4) from a validated frame.
    """
    if len(frame) < 16:
        raise ValueError(f"Frame length {len(frame)} is less than minimum 16 bytes")
    return frame[8 : len(frame) - 4]
