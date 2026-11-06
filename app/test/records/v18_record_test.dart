import 'dart:typed_data';

import 'package:beveltry/src/records/record_decode_exception.dart';
import 'package:beveltry/src/records/v18_record.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('decodifica i campi V18 confermati e mantiene il buffer intatto', () {
    final payload = _v18Payload();
    final original = Uint8List.fromList(payload);

    final record = V18Record.decode(payload);

    expect(record.seq, 0x1234);
    expect(
      record.timestamp,
      DateTime.utc(1970).add(const Duration(seconds: 0x04030201)),
    );
    expect(record.hrPrimary, 72);
    expect(record.hrSecondary, 68);
    expect(record.rrCount, 2);
    expect(record.rrIntervalsMs, [850, 860]);
    expect(record.gravityX, closeTo(0.1, 1e-6));
    expect(record.gravityY, closeTo(-0.2, 1e-6));
    expect(record.gravityZ, closeTo(0.9, 1e-6));
    expect(record.quaternionW, 1.0);
    expect(record.quaternionX, 0.0);
    expect(record.quaternionY, 0.0);
    expect(record.quaternionZ, 0.0);
    expect(record.spo2Candidate, 0);
    expect(record.opticalBaseline, 45000);
    expect(record.opticalAmpA, 50);
    expect(record.opticalAmpB, 48);
    expect(payload, original);
  });

  test('HR zero indica off-wrist e rrCount zero produce lista vuota', () {
    final payload = _v18Payload()..[14] = 0;
    ByteData.sublistView(payload).setUint8(15, 0);

    final record = V18Record.decode(payload);

    expect(record.hrPrimary, 0);
    expect(record.rrCount, 0);
    expect(record.rrIntervalsMs, isEmpty);
  });

  test('legge tutti e quattro gli intervalli R-R in millisecondi', () {
    final payload = _v18Payload();
    final data = ByteData.sublistView(payload);
    data.setUint8(15, 4);
    for (var i = 0; i < 4; i++) {
      data.setUint16(16 + i * 2, 800 + i * 10, Endian.little);
    }

    expect(V18Record.decode(payload).rrIntervalsMs, [800, 810, 820, 830]);
  });

  test('i campi sperimentali vengono letti senza interrompere il decode', () {
    final payload = _v18Payload();
    final data = ByteData.sublistView(payload);
    data.setUint16(57, 1234, Endian.little);
    data.setInt16(60, -15, Endian.little);
    data.setUint8(62, 2);
    data.setFloat32(113, -5.125, Endian.little);

    final record = V18Record.decode(payload);

    expect(record.stepCounter, 1234);
    expect(record.skinTempRaw, -15);
    expect(record.sleepState, 2);
    expect(record.unknownF32, -5.125);
  });

  test('un float sperimentale non finito diventa null', () {
    final payload = _v18Payload();
    ByteData.sublistView(payload).setFloat32(113, double.nan, Endian.little);

    expect(V18Record.decode(payload).unknownF32, isNull);
  });

  test('rifiuta type, version, rrCount e payload non validi', () {
    final wrongType = _v18Payload()..[0] = 0x28;
    final wrongVersion = _v18Payload()..[1] = 0x1A;
    final tooManyIntervals = _v18Payload()..[15] = 5;
    final short = Uint8List.fromList(_v18Payload().take(123).toList());

    expect(
      () => V18Record.decode(wrongType),
      throwsA(isA<RecordDecodeException>()),
    );
    expect(
      () => V18Record.decode(wrongVersion),
      throwsA(isA<RecordDecodeException>()),
    );
    expect(
      () => V18Record.decode(tooManyIntervals),
      throwsA(isA<RecordDecodeException>()),
    );
    expect(
      () => V18Record.decode(short),
      throwsA(isA<RecordDecodeException>()),
    );
  });
}

Uint8List _v18Payload() {
  final payload = Uint8List.fromList(List<int>.filled(124, 0));
  final data = ByteData.sublistView(payload);
  payload[0] = 0x2F;
  payload[1] = 0x12;
  data.setUint16(2, 0x1234, Endian.little);
  data.setUint32(7, 0x04030201, Endian.little);
  payload[14] = 72;
  payload[15] = 2;
  data.setUint16(16, 850, Endian.little);
  data.setUint16(18, 860, Endian.little);
  payload[29] = 68;
  data.setFloat32(33, 0.1, Endian.little);
  data.setFloat32(37, -0.2, Endian.little);
  data.setFloat32(41, 0.9, Endian.little);
  data.setFloat32(45, 1.0, Endian.little);
  data.setFloat32(49, 0.0, Endian.little);
  data.setFloat32(53, 0.0, Endian.little);
  data.setFloat32(57, 0.0, Endian.little);
  payload[62] = 2;
  payload[82] = 0;
  payload[104] = 1;
  data.setUint16(106, 45000, Endian.little);
  payload[108] = 50;
  payload[109] = 48;
  data.setFloat32(113, -3.25, Endian.little);
  return payload;
}
