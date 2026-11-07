import 'dart:typed_data';

/// Calcolo CRC conforme al protocollo custom Puffin Gen 5.
class CRC {
  CRC._();

  static final List<int> _crc32Table = List<int>.generate(256, (i) {
    var c = i;
    for (var k = 0; k < 8; k++) {
      c = (c & 1 != 0) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    }
    return c;
  });

  /// CRC-16/MODBUS (polinomio riflesso 0xA001, valore iniziale 0xFFFF).
  static int crc16Modbus(Uint8List bytes) {
    var crc = 0xFFFF;
    for (final byte in bytes) {
      crc ^= (byte & 0xFF);
      for (var i = 0; i < 8; i++) {
        crc = (crc & 1 != 0) ? ((crc >> 1) ^ 0xA001) : (crc >> 1);
      }
    }
    return crc & 0xFFFF;
  }

  /// CRC-32 IEEE 802.3 utilizzato nel trailer dei frame Puffin.
  static int crc32IEEE(Uint8List bytes) {
    var crc = 0xFFFFFFFF;
    for (final byte in bytes) {
      crc = _crc32Table[(crc ^ byte) & 0xFF] ^ (crc >>> 8);
    }
    return (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF;
  }
}
