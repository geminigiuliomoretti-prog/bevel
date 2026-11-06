import 'dart:typed_data';

import 'live28_record.dart';
import 'record_decode_exception.dart';
import 'v18_record.dart';
import 'v26_record.dart';

enum RecordType { v18, v26, live28, unknown }

class RecordDecoder {
  static Object decode(Uint8List payload) {
    if (payload.length < 2) {
      throw const RecordDecodeException(
        'Payload insufficiente per type/version',
      );
    }

    return switch ((payload[0], payload[1])) {
      (0x2F, 0x12) => V18Record.decode(payload),
      (0x2F, 0x1A) => V26Record.decode(payload),
      (0x28, 0x02) => Live28Record.decode(payload),
      (0x2F, _) => throw RecordDecodeException(
        'Version 0x${payload[1].toRadixString(16)} non supportata per type 0x2F',
      ),
      (0x28, _) => throw RecordDecodeException(
        'Version 0x${payload[1].toRadixString(16)} non supportata per type 0x28',
      ),
      _ => throw const RecordDecodeException('Type di record sconosciuto'),
    };
  }
}
