import 'dart:typed_data';

import 'crc.dart';

/// Eccezioni sollevate durante la codifica o decodifica dei frame Puffin.
class PuffinFrameException implements Exception {
  PuffinFrameException(this.message);
  final String message;

  @override
  String toString() => 'PuffinFrameException: $message';
}

/// Codec binario per l'envelope custom del WHOOP 5.0 (Puffin Gen 5).
///
/// Struttura:
/// - Header (8 byte): `[0xAA, 0x01, len_u16, field_u16, crc16_u16]`
/// - Payload paddato: multiplo di 4 byte (minimo 4 byte)
/// - Trailer (4 byte): `crc32_u32` (IEEE 802.3 su payload paddato)
class PuffinFrameCodec {
  PuffinFrameCodec._();

  static const int headerSize = 8;
  static const Set<int> blockedOpcodes = {0x19, 0x1D};

  /// Codifica un comando o payload nel frame binario conforme al protocollo.
  static Uint8List encode(int field, Uint8List payload) {
    if (payload.isEmpty) {
      throw PuffinFrameException('Il payload non può essere vuoto (minimo 16 byte su cavo)');
    }

    // Regola di sicurezza: MAI inviare comandi distruttivi (0x19 ERASE, 0x1D REBOOT)
    if (payload.length >= 3 && payload[0] == 0x23) {
      final opcode = payload[2];
      if (blockedOpcodes.contains(opcode)) {
        throw ArgumentError(
          'CRITICAL SAFETY VIOLATION: Opcode 0x${opcode.toRadixString(16).padLeft(2, '0')} '
          'bloccato per prevenire bricking o cancellazione del dispositivo.',
        );
      }
    }

    final padLen = (4 - (payload.length % 4)) % 4;
    final paddedLength = payload.length + padLen;
    final payloadLength = paddedLength + 4; // Include 4 byte di CRC32 trailer

    if (headerSize + payloadLength < 16) {
      throw PuffinFrameException('Frame troppo corto (minimo 16 byte)');
    }

    final rawPayload = Uint8List(paddedLength);
    rawPayload.setRange(0, payload.length, payload);

    final frame = Uint8List(headerSize + payloadLength);
    frame[0] = 0xAA;
    frame[1] = 0x01;
    _putU16(frame, 2, payloadLength);
    _putU16(frame, 4, field);

    final headerCrc = CRC.crc16Modbus(Uint8List.sublistView(frame, 0, 6));
    _putU16(frame, 6, headerCrc);

    frame.setRange(headerSize, headerSize + paddedLength, rawPayload);

    final trailerCrc = CRC.crc32IEEE(rawPayload);
    _putU32(frame, headerSize + paddedLength, trailerCrc);

    return frame;
  }

  /// Decodifica e verifica un frame Puffin ricevuto.
  static Uint8List decode(Uint8List frame) {
    if (frame.length < 16) {
      throw PuffinFrameException('Frame troppo corto: ${frame.length} byte');
    }
    if (frame[0] != 0xAA || frame[1] != 0x01) {
      throw PuffinFrameException('SOF o versione non validi: 0x${frame[0].toRadixString(16)}, 0x${frame[1].toRadixString(16)}');
    }

    final payloadLength = _readU16(frame, 2);
    if (frame.length != headerSize + payloadLength) {
      throw PuffinFrameException('Lunghezza frame incoerente con l\'header: ${frame.length} != ${headerSize + payloadLength}');
    }

    final expectedHeaderCrc = CRC.crc16Modbus(Uint8List.sublistView(frame, 0, 6));
    final actualHeaderCrc = _readU16(frame, 6);
    if (expectedHeaderCrc != actualHeaderCrc) {
      throw PuffinFrameException('CRC16 header non valido: atteso $expectedHeaderCrc, ottenuto $actualHeaderCrc');
    }

    final paddedLength = payloadLength - 4;
    final rawPayload = Uint8List.sublistView(frame, headerSize, headerSize + paddedLength);
    final expectedTrailerCrc = CRC.crc32IEEE(rawPayload);
    final actualTrailerCrc = _readU32(frame, headerSize + paddedLength);
    if (expectedTrailerCrc != actualTrailerCrc) {
      throw PuffinFrameException('CRC32 payload non valido');
    }

    return rawPayload;
  }

  static void _putU16(Uint8List bytes, int offset, int value) {
    bytes[offset] = value & 0xFF;
    bytes[offset + 1] = (value >> 8) & 0xFF;
  }

  static int _readU16(Uint8List bytes, int offset) {
    return bytes[offset] | (bytes[offset + 1] << 8);
  }

  static void _putU32(Uint8List bytes, int offset, int value) {
    bytes[offset] = value & 0xFF;
    bytes[offset + 1] = (value >> 8) & 0xFF;
    bytes[offset + 2] = (value >> 16) & 0xFF;
    bytes[offset + 3] = (value >> 24) & 0xFF;
  }

  static int _readU32(Uint8List bytes, int offset) {
    return bytes[offset] |
        (bytes[offset + 1] << 8) |
        (bytes[offset + 2] << 16) |
        (bytes[offset + 3] << 24);
  }
}
