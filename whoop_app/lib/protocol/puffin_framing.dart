import 'dart:typed_data';

/// CRC-16 Modbus (Polynomial 0xA001, Initial 0xFFFF).
int calcCrc16Modbus(Uint8List data) {
  int crc = 0xFFFF;
  for (int b in data) {
    crc ^= (b & 0xFF);
    for (int i = 0; i < 8; i++) {
      if ((crc & 1) != 0) {
        crc = (crc >> 1) ^ 0xA001;
      } else {
        crc = crc >> 1;
      }
    }
  }
  return crc & 0xFFFF;
}

/// CRC-32 IEEE 802.3 standard (Polynomial 0xEDB88320).
int calcCrc32Ieee(Uint8List data) {
  int crc = 0xFFFFFFFF;
  for (int b in data) {
    crc ^= (b & 0xFF);
    for (int i = 0; i < 8; i++) {
      if ((crc & 1) != 0) {
        crc = (crc >>> 1) ^ 0xEDB88320;
      } else {
        crc = crc >>> 1;
      }
    }
  }
  return (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF;
}

/// Builds a valid Puffin Gen 5 binary envelope.
///
/// Envelope layout:
/// - Header (8 bytes):
///   - 0xAA, 0x01 (Sync / Protocol ID)
///   - Length of inner payload (uint16 LE)
///   - 0x01, 0x00 (Sequence / constant)
///   - CRC16-Modbus over bytes 0..5 (uint16 LE)
/// - Inner payload:
///   - Original payload padded with 0x00 to a multiple of 4 bytes (min 4 bytes)
/// - Trailer (4 bytes):
///   - CRC32 over Header + Padded Inner Payload (uint32 LE)
Uint8List buildPuffinFrame(Uint8List innerPayload) {
  int innerLen = innerPayload.length;
  int padLen = (4 - (innerLen % 4)) % 4;
  if (innerLen + padLen < 4) {
    padLen = 4 - innerLen;
  }
  int paddedInnerLen = innerLen + padLen;

  // Header 8 bytes
  Uint8List header = Uint8List(8);
  header[0] = 0xAA;
  header[1] = 0x01;
  header[2] = innerLen & 0xFF;
  header[3] = (innerLen >> 8) & 0xFF;
  header[4] = 0x01;
  header[5] = 0x00;

  int crc16 = calcCrc16Modbus(header.sublist(0, 6));
  header[6] = crc16 & 0xFF;
  header[7] = (crc16 >> 8) & 0xFF;

  // Padded inner
  Uint8List paddedInner = Uint8List(paddedInnerLen);
  paddedInner.setRange(0, innerLen, innerPayload);

  // Buffer for header + paddedInner
  Uint8List body = Uint8List(8 + paddedInnerLen);
  body.setRange(0, 8, header);
  body.setRange(8, 8 + paddedInnerLen, paddedInner);

  int crc32 = calcCrc32Ieee(body);

  // Full Frame
  Uint8List fullFrame = Uint8List(body.length + 4);
  fullFrame.setRange(0, body.length, body);
  fullFrame[body.length] = crc32 & 0xFF;
  fullFrame[body.length + 1] = (crc32 >> 8) & 0xFF;
  fullFrame[body.length + 2] = (crc32 >> 16) & 0xFF;
  fullFrame[body.length + 3] = (crc32 >> 24) & 0xFF;

  return fullFrame;
}

/// Extracts the raw inner payload from a valid Puffin frame.
Uint8List extractInnerPayload(Uint8List frame) {
  if (frame.length < 16) {
    throw ArgumentError('Frame too short: ${frame.length} bytes (min 16)');
  }
  if (frame[0] != 0xAA || frame[1] != 0x01) {
    throw ArgumentError('Invalid Puffin sync header: 0x${frame[0].toRadixString(16)} 0x${frame[1].toRadixString(16)}');
  }

  ByteData bd = ByteData.sublistView(frame);
  int innerLen = bd.getUint16(2, Endian.little);
  if (8 + innerLen > frame.length - 4) {
    // If length field is corrupted or larger than available payload, use frame without padding
    return frame.sublist(8, frame.length - 4);
  }
  return frame.sublist(8, 8 + innerLen);
}

/// Anti-fragmentation streaming reassembler for incoming BLE notifications.
class PuffinStreamReassembler {
  final List<int> _buffer = [];

  List<Uint8List> feed(Uint8List chunk) {
    _buffer.addAll(chunk);
    List<Uint8List> frames = [];

    while (true) {
      if (_buffer.length < 8) break;

      // Look for sync header 0xAA 0x01
      int syncIdx = -1;
      for (int i = 0; i <= _buffer.length - 2; i++) {
        if (_buffer[i] == 0xAA && _buffer[i + 1] == 0x01) {
          syncIdx = i;
          break;
        }
      }

      if (syncIdx == -1) {
        // Keep last byte in case 0xAA is split
        int lastByte = _buffer.isNotEmpty ? _buffer.last : 0;
        _buffer.clear();
        if (lastByte == 0xAA) _buffer.add(lastByte);
        break;
      }

      if (syncIdx > 0) {
        _buffer.removeRange(0, syncIdx);
      }

      if (_buffer.length < 8) break;

      // Validate header CRC16
      Uint8List header = Uint8List.fromList(_buffer.sublist(0, 8));
      int calcHdrCrc = calcCrc16Modbus(header.sublist(0, 6));
      ByteData bd = ByteData.sublistView(header);
      int wireHdrCrc = bd.getUint16(6, Endian.little);
      if (calcHdrCrc != wireHdrCrc) {
        // Discard 0xAA and re-seek
        _buffer.removeAt(0);
        continue;
      }

      int innerLen = bd.getUint16(2, Endian.little);
      int padLen = (4 - (innerLen % 4)) % 4;
      if (innerLen + padLen < 4) {
        padLen = 4 - innerLen;
      }
      int totalFrameLen = 8 + innerLen + padLen + 4;

      if (_buffer.length < totalFrameLen) {
        // Awaiting remaining fragments
        break;
      }

      Uint8List frameBytes = Uint8List.fromList(_buffer.sublist(0, totalFrameLen));

      // Validate CRC32
      Uint8List body = frameBytes.sublist(0, totalFrameLen - 4);
      int calcBodyCrc = calcCrc32Ieee(body);
      ByteData fbd = ByteData.sublistView(frameBytes);
      int wireBodyCrc = fbd.getUint32(totalFrameLen - 4, Endian.little);

      if (calcBodyCrc == wireBodyCrc) {
        frames.add(frameBytes);
        _buffer.removeRange(0, totalFrameLen);
      } else {
        // Corrupt frame CRC32, advance 1 byte
        _buffer.removeAt(0);
      }
    }

    return frames;
  }

  void clear() {
    _buffer.clear();
  }
}
