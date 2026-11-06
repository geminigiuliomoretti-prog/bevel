import 'dart:typed_data';

import 'package:beveltry/src/records/live28_record.dart';
import 'package:beveltry/src/records/record_decode_exception.dart';
import 'package:beveltry/src/records/record_decoder.dart';
import 'package:beveltry/src/records/v18_record.dart';
import 'package:beveltry/src/records/v26_record.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('dispatcha i tre type/version supportati', () {
    expect(RecordDecoder.decode(_payload(0x2F, 0x12, 124)), isA<V18Record>());
    expect(RecordDecoder.decode(_payload(0x2F, 0x1A, 88)), isA<V26Record>());
    expect(RecordDecoder.decode(_payload(0x28, 0x02, 12)), isA<Live28Record>());
  });

  test(
    'type sconosciuto, payload vuoto e version non supportata falliscono',
    () {
      expect(
        () => RecordDecoder.decode(_payload(0x33, 0x01, 12)),
        throwsA(isA<RecordDecodeException>()),
      );
      expect(
        () => RecordDecoder.decode(Uint8List(0)),
        throwsA(isA<RecordDecodeException>()),
      );
      expect(
        () => RecordDecoder.decode(_payload(0x2F, 0x13, 124)),
        throwsA(isA<RecordDecodeException>()),
      );
    },
  );
}

Uint8List _payload(int type, int version, int length) {
  final payload = Uint8List.fromList(List<int>.filled(length, 0));
  payload[0] = type;
  payload[1] = version;
  return payload;
}
