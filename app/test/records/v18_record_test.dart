import 'dart:typed_data';

import 'package:beveltry/src/records/record_decode_exception.dart';
import 'package:beveltry/src/records/v18_record.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('decodifica l’inner payload della cattura firmware reale', () {
    final payload = _realCaptureInner();

    final record = V18Record.decode(payload);

    expect(payload, hasLength(112));
    expect(record.seq, 9856);
    expect(record.timestamp, DateTime.utc(2026, 11, 3, 4, 15, 44));
    expect(record.hrPrimary, 51);
    expect(record.rrCount, 1);
    expect(record.rrIntervalsMs, [1145]);
  });

  test('un inner payload valido da 112 byte legge tutti i campi', () {
    final record = V18Record.decode(_innerPayload());

    expect(record.seq, 0);
    expect(record.hrPrimary, 0);
    expect(record.hrSecondary, 0);
    expect(record.rrIntervalsMs, isEmpty);
    expect(record.gravityX, 0);
    expect(record.gravityY, 0);
    expect(record.gravityZ, 0);
    expect(record.accelMagG, 0);
    expect(record.stepCounter, 0);
    expect(record.skinTempRaw, isNull);
    expect(record.activityFlag, 0);
    expect(record.spo2Candidate, 0);
    expect(record.sleepState, 0);
    expect(record.opticalBaselineCh1, 0);
    expect(record.opticalBaselineCh2, 0);
    expect(record.opticalBaseline, 0);
    expect(record.isOnWrist, isFalse);
  });

  test('accetta 108 byte e legge il secondo optical baseline disponibile', () {
    final payload = _innerPayload(length: 108);
    ByteData.sublistView(payload).setUint16(106, 45678, Endian.little);

    final record = V18Record.decode(payload);

    expect(record.opticalBaselineCh2, 45678);
    expect(record.opticalBaseline, 45678);
  });

  test('rifiuta un inner payload da 107 byte e un buffer da 124 byte', () {
    expect(
      () => V18Record.decode(_innerPayload(length: 107)),
      throwsA(isA<RecordDecodeException>()),
    );
    expect(
      () => V18Record.decode(_innerPayload(length: 124)),
      throwsA(isA<RecordDecodeException>()),
    );
  });

  test('rifiuta type e version errati', () {
    final wrongType = _innerPayload()..[0] = 0x28;
    final wrongVersion = _innerPayload()..[1] = 0x1A;

    expect(() => V18Record.decode(wrongType), throwsA(isA<RecordDecodeException>()));
    expect(() => V18Record.decode(wrongVersion), throwsA(isA<RecordDecodeException>()));
  });

  test('usa il fallback @63 quando la temperatura @61 non è plausibile', () {
    final payload = _innerPayload();
    final data = ByteData.sublistView(payload);
    data.setInt16(61, 100, Endian.little);
    data.setInt16(63, 320, Endian.little);

    final record = V18Record.decode(payload);

    expect(record.skinTempRaw, 320);
    expect(record.skinTempCelsius, 32.0);
  });

  test('opticalBaseline è il massimo dei due canali', () {
    final payload = _innerPayload();
    final data = ByteData.sublistView(payload);
    data.setUint16(98, 40000, Endian.little);
    data.setUint16(106, 50000, Endian.little);

    final record = V18Record.decode(payload);

    expect(record.opticalBaselineCh1, 40000);
    expect(record.opticalBaselineCh2, 50000);
    expect(record.opticalBaseline, 50000);
  });

  test('isOnWrist segue HR primaria o optical baseline', () {
    final offWrist = _innerPayload();
    final onWristByHeartRate = _innerPayload()..[14] = 1;
    final onWristByOptical = _innerPayload();
    ByteData.sublistView(onWristByOptical).setUint16(98, 30001, Endian.little);

    expect(V18Record.decode(offWrist).isOnWrist, isFalse);
    expect(V18Record.decode(onWristByHeartRate).isOnWrist, isTrue);
    expect(V18Record.decode(onWristByOptical).isOnWrist, isTrue);
  });

  test('calcola gravità e mantiene gli RR in millisecondi senza conversione', () {
    final payload = _innerPayload();
    final data = ByteData.sublistView(payload);
    payload[15] = 2;
    data.setUint16(16, 850, Endian.little);
    data.setUint16(18, 860, Endian.little);
    data.setFloat32(37, 0.0, Endian.little);
    data.setFloat32(41, 0.0, Endian.little);
    data.setFloat32(45, 1.0, Endian.little);

    final record = V18Record.decode(payload);

    expect(record.rrIntervalsMs, [850, 860]);
    expect(record.accelMagG, closeTo(1.0, 1e-6));
  });
}

Uint8List _innerPayload({int length = 112}) {
  final payload = Uint8List(length);
  payload[0] = 0x2F;
  payload[1] = 0x12;
  return payload;
}

Uint8List _realCaptureInner() {
  final payload = _innerPayload();
  const capturedPrefix = <int>[
    0x2F, 0x12, 0x80, 0x26, 0x31, 0x14, 0x02, 0xF0, 0x5F,
    0xE9, 0x6A, 0xEB, 0x11, 0x00, 0x33, 0x01, 0x79, 0x04,
  ];
  payload.setRange(0, capturedPrefix.length, capturedPrefix);
  return payload;
}
