import 'dart:typed_data';

import 'package:beveltry/src/ble/ble.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('PuffinFrameCodec Tests', () {
    final knownHello = Uint8List.fromList([
      0xAA, 0x01, 0x08, 0x00, 0x00, 0x01, 0xE6, 0x71,
      0x23, 0x01, 0x91, 0x01, 0x36, 0x3E, 0x5C, 0x8D,
    ]);

    test('CRC-16/Modbus calcola correttamente il checksum header', () {
      final header6 = Uint8List.fromList([0xAA, 0x01, 0x08, 0x00, 0x00, 0x01]);
      final crc = CRC.crc16Modbus(header6);
      expect(crc, equals(0x71E6)); // little-endian: E6, 71
    });

    test('CRC-32 IEEE calcola correttamente il checksum trailer', () {
      final payload = Uint8List.fromList([0x23, 0x01, 0x91, 0x01]);
      final crc = CRC.crc32IEEE(payload);
      expect(crc, equals(0x8D5C3E36)); // little-endian: 36, 3E, 5C, 8D
    });

    test('Vettore Hello noto da firmware reale codifica e decodifica perfettamente', () {
      final payload = Uint8List.fromList([0x23, 0x01, 0x91, 0x01]);
      final encoded = PuffinFrameCodec.encode(0x0100, payload);
      expect(encoded, equals(knownHello));

      final decoded = PuffinFrameCodec.decode(encoded);
      expect(decoded, equals(payload));
    });

    test('Padding a 4 byte e dimensione minima frame (>= 16 byte)', () {
      final oneByte = Uint8List.fromList([0x23]);
      final encoded = PuffinFrameCodec.encode(1, oneByte);
      expect(encoded.length, equals(16));
      expect(encoded.sublist(8, 12), equals([0x23, 0x00, 0x00, 0x00]));
    });

    test('Regola 4: MAI consentire opcode distruttivi (0x19 ERASE e 0x1D REBOOT)', () {
      final eraseCmd = Uint8List.fromList([0x23, 0x01, 0x19, 0x00]);
      expect(
        () => PuffinFrameCodec.encode(1, eraseCmd),
        throwsA(isA<ArgumentError>()),
      );

      final rebootCmd = Uint8List.fromList([0x23, 0x01, 0x1D, 0x00]);
      expect(
        () => PuffinFrameCodec.encode(1, rebootCmd),
        throwsA(isA<ArgumentError>()),
      );
    });

    test('Rifiuta frame con SOF non valido o CRC errato', () {
      final badSof = Uint8List.fromList(knownHello);
      badSof[0] = 0x00;
      expect(() => PuffinFrameCodec.decode(badSof), throwsA(isA<PuffinFrameException>()));

      final badCrc = Uint8List.fromList(knownHello);
      badCrc[6] = 0x00;
      expect(() => PuffinFrameCodec.decode(badCrc), throwsA(isA<PuffinFrameException>()));
    });
  });
}
