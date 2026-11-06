import 'dart:typed_data';

import 'package:beveltry/src/records/live28_record.dart';
import 'package:beveltry/src/records/record_decode_exception.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('decodifica timestamp, HR e RR in millisecondi', () {
    final payload = _live28Payload(1);
    final original = Uint8List.fromList(payload);

    final record = Live28Record.decode(payload);

    expect(record.timestamp, DateTime.utc(2024, 1, 1));
    expect(record.hr, 65);
    expect(record.validity, Live28Validity.hrAndRr);
    expect(record.rrIntervalMs, 920);
    expect(payload, original);
  });

  test('decodifica validity off-wrist e HR/RR/extra', () {
    expect(
      Live28Record.decode(_live28Payload(0)).validity,
      Live28Validity.offWrist,
    );
    expect(
      Live28Record.decode(_live28Payload(2)).validity,
      Live28Validity.hrRrAndExtra,
    );
  });

  test('rifiuta type, version, validity non riconosciuta e payload corto', () {
    final wrongType = _live28Payload(1)..[0] = 0x2F;
    final wrongVersion = _live28Payload(1)..[1] = 0x12;
    final wrongValidity = _live28Payload(1)..[9] = 3;
    final short = Uint8List.fromList(_live28Payload(1).take(11).toList());

    expect(
      () => Live28Record.decode(wrongType),
      throwsA(isA<RecordDecodeException>()),
    );
    expect(
      () => Live28Record.decode(wrongVersion),
      throwsA(isA<RecordDecodeException>()),
    );
    expect(
      () => Live28Record.decode(wrongValidity),
      throwsA(isA<RecordDecodeException>()),
    );
    expect(
      () => Live28Record.decode(short),
      throwsA(isA<RecordDecodeException>()),
    );
  });
}

Uint8List _live28Payload(int validity) {
  final payload = Uint8List.fromList(List<int>.filled(12, 0));
  final data = ByteData.sublistView(payload);
  payload[0] = 0x28;
  payload[1] = 0x02;
  data.setUint32(2, 0x65920080, Endian.little);
  payload[8] = 65;
  payload[9] = validity;
  data.setUint16(10, 920, Endian.little);
  return payload;
}
