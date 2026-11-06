import 'dart:typed_data';

import 'package:beveltry/src/records/record_decode_exception.dart';
import 'package:beveltry/src/records/v26_record.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('decodifica 24 campioni i16 in ordine little-endian', () {
    final payload = _v26Payload();
    final original = Uint8List.fromList(payload);

    final record = V26Record.decode(payload);

    expect(record.ppgSamples, [for (var i = 0; i < 24; i++) i - 12]);
    expect(record.ppgSamples.first, -12);
    expect(record.ppgSamples.last, 11);
    expect(payload, original);
  });

  test('rifiuta type, version e payload insufficienti', () {
    final wrongType = _v26Payload()..[0] = 0x28;
    final wrongVersion = _v26Payload()..[1] = 0x12;
    final short = Uint8List.fromList(_v26Payload().take(87).toList());

    expect(
      () => V26Record.decode(wrongType),
      throwsA(isA<RecordDecodeException>()),
    );
    expect(
      () => V26Record.decode(wrongVersion),
      throwsA(isA<RecordDecodeException>()),
    );
    expect(
      () => V26Record.decode(short),
      throwsA(isA<RecordDecodeException>()),
    );
  });
}

Uint8List _v26Payload() {
  final payload = Uint8List.fromList(List<int>.filled(88, 0));
  final data = ByteData.sublistView(payload);
  payload[0] = 0x2F;
  payload[1] = 0x1A;
  for (var i = 0; i < 24; i++) {
    data.setInt16(27 + i * 2, i - 12, Endian.little);
  }
  return payload;
}
