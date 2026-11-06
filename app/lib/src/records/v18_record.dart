import 'dart:typed_data';

import 'record_decode_exception.dart';

/// Record storico V18 secondo la mappatura Beveltry.
///
/// Il campo quaternion Z copre i byte 57-60, condivisi dagli offset
/// sperimentali [stepCounter] e [skinTempRaw]. Entrambe le letture sono
/// mantenute separatamente e non vanno usate per logica critica.
class V18Record {
  const V18Record({
    required this.seq,
    required this.timestamp,
    required this.hrPrimary,
    required this.hrSecondary,
    required this.rrCount,
    required this.rrIntervalsMs,
    required this.gravityX,
    required this.gravityY,
    required this.gravityZ,
    required this.quaternionW,
    required this.quaternionX,
    required this.quaternionY,
    required this.quaternionZ,
    required this.stepCounter,
    required this.skinTempRaw,
    required this.sleepState,
    required this.spo2Candidate,
    required this.opticalBaseline,
    required this.opticalAmpA,
    required this.opticalAmpB,
    required this.unknownF32,
  });

  final int seq;
  final DateTime timestamp;
  final int hrPrimary;
  final int hrSecondary;
  final int rrCount;
  final List<int> rrIntervalsMs;
  final double gravityX;
  final double gravityY;
  final double gravityZ;
  final double quaternionW;
  final double quaternionX;
  final double quaternionY;
  final double quaternionZ;

  /// Lettura u16 @57: sperimentale e sovrapposta al quaternion Z.
  final int? stepCounter;

  /// Valore grezzo i16 @60: sperimentale e non calibrato.
  final int? skinTempRaw;

  /// Valore grezzo u8 @62: sperimentale, senza semantica confermata.
  final int? sleepState;

  /// Byte grezzo @82; non è una misura SpO2.
  final int spo2Candidate;
  final int opticalBaseline;
  final int opticalAmpA;
  final int opticalAmpB;

  /// Campo sperimentale @113, nullo se il float non è finito.
  final double? unknownF32;

  static const int payloadLength = 124;

  static V18Record decode(Uint8List payload) {
    if (payload.length < payloadLength) {
      throw const RecordDecodeException('V18: payload inferiore a 124 byte');
    }
    if (payload[0] != 0x2F) {
      throw const RecordDecodeException('V18: type atteso 0x2F');
    }
    if (payload[1] != 0x12) {
      throw const RecordDecodeException('V18: version attesa 0x12');
    }

    final data = ByteData.sublistView(payload);
    final rrCount = payload[15];
    if (rrCount > 4) {
      throw const RecordDecodeException('V18: rrCount fuori intervallo 0-4');
    }

    final rrIntervals = List<int>.unmodifiable(
      List<int>.generate(
        rrCount,
        (index) => data.getUint16(16 + index * 2, Endian.little),
      ),
    );
    final timestampSeconds = data.getUint32(7, Endian.little);
    final unknown = data.getFloat32(113, Endian.little);

    return V18Record(
      seq: data.getUint16(2, Endian.little),
      timestamp: DateTime.fromMillisecondsSinceEpoch(
        timestampSeconds * 1000,
        isUtc: true,
      ),
      hrPrimary: payload[14],
      hrSecondary: payload[29],
      rrCount: rrCount,
      rrIntervalsMs: rrIntervals,
      gravityX: data.getFloat32(33, Endian.little),
      gravityY: data.getFloat32(37, Endian.little),
      gravityZ: data.getFloat32(41, Endian.little),
      quaternionW: data.getFloat32(45, Endian.little),
      quaternionX: data.getFloat32(49, Endian.little),
      quaternionY: data.getFloat32(53, Endian.little),
      quaternionZ: data.getFloat32(57, Endian.little),
      stepCounter: data.getUint16(57, Endian.little),
      skinTempRaw: data.getInt16(60, Endian.little),
      sleepState: payload[62],
      spo2Candidate: payload[82],
      opticalBaseline: data.getUint16(106, Endian.little),
      opticalAmpA: payload[108],
      opticalAmpB: payload[109],
      unknownF32: unknown.isFinite ? unknown : null,
    );
  }
}
