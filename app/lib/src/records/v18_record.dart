import 'dart:math' as math;
import 'dart:typed_data';

import 'record_decode_exception.dart';

/// Record storico v18: [payload] è esclusivamente l'inner payload Puffin.
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
    required this.accelMagG,
    required this.stepCounter,
    required this.skinTempRaw,
    required this.skinTempCelsius,
    required this.activityFlag,
    required this.spo2Candidate,
    required this.sleepState,
    required this.opticalBaselineCh1,
    required this.opticalBaselineCh2,
    required this.opticalBaseline,
    required this.isOnWrist,
  });

  static const int minPayloadLength = 108;
  static const int standardInnerLength = 112;

  final int seq;
  final DateTime timestamp;
  final int hrPrimary;
  final int hrSecondary;
  final int rrCount;
  final List<int> rrIntervalsMs;
  final double gravityX;
  final double gravityY;
  final double gravityZ;
  final double accelMagG;
  final int stepCounter;
  final int? skinTempRaw;
  final double? skinTempCelsius;
  final int activityFlag;

  /// Byte grezzo candidato; non viene interpretato come misura SpO2.
  final int spo2Candidate;
  final int sleepState;
  final int opticalBaselineCh1;
  final int? opticalBaselineCh2;
  final int opticalBaseline;
  final bool isOnWrist;

  static V18Record decode(Uint8List payload) {
    if (payload.length < minPayloadLength) {
      throw RecordDecodeException(
        'V18: payload too short (${payload.length} < $minPayloadLength)',
      );
    }
    if (payload.length > standardInnerLength) {
      throw RecordDecodeException(
        'V18: inner payload too long (${payload.length} > $standardInnerLength)',
      );
    }
    if (payload[0] != 0x2F || payload[1] != 0x12) {
      throw RecordDecodeException(
        'V18: invalid type/version ${payload[0]}/${payload[1]}',
      );
    }

    final seq = _u16(payload, 2);
    final timestampSeconds = _u32(payload, 7);
    final hrPrimary = payload[14];
    final rrCount = payload[15].clamp(0, 4).toInt();
    final rrIntervals = List<int>.unmodifiable(
      List<int>.generate(rrCount, (index) => _u16(payload, 16 + index * 2)),
    );
    final hrSecondary = payload[29];
    final gravityX = _f32(payload, 37);
    final gravityY = _f32(payload, 41);
    final gravityZ = _f32(payload, 45);
    final accelMagG = math.sqrt(
      gravityX * gravityX + gravityY * gravityY + gravityZ * gravityZ,
    );
    final stepCounter = _u16(payload, 57);

    int? skinTempRaw;
    double? skinTempCelsius;
    final rawAt61 = _i16(payload, 61);
    if (_isPlausibleSkinTemperature(rawAt61)) {
      skinTempRaw = rawAt61;
    } else if (payload.length >= 65) {
      final rawAt63 = _i16(payload, 63);
      if (_isPlausibleSkinTemperature(rawAt63)) skinTempRaw = rawAt63;
    }
    if (skinTempRaw != null) skinTempCelsius = skinTempRaw / 10.0;

    final activityFlag = payload[64];
    final spo2Candidate = payload[82];
    final sleepState = payload[96];
    final opticalBaselineCh1 = _u16(payload, 98);
    final opticalBaselineCh2 = payload.length >= 108 ? _u16(payload, 106) : null;
    final opticalBaseline = math.max(opticalBaselineCh1, opticalBaselineCh2 ?? 0).toInt();

    return V18Record(
      seq: seq,
      timestamp: DateTime.fromMillisecondsSinceEpoch(
        timestampSeconds * 1000,
        isUtc: true,
      ),
      hrPrimary: hrPrimary,
      hrSecondary: hrSecondary,
      rrCount: rrCount,
      rrIntervalsMs: rrIntervals,
      gravityX: gravityX,
      gravityY: gravityY,
      gravityZ: gravityZ,
      accelMagG: accelMagG,
      stepCounter: stepCounter,
      skinTempRaw: skinTempRaw,
      skinTempCelsius: skinTempCelsius,
      activityFlag: activityFlag,
      spo2Candidate: spo2Candidate,
      sleepState: sleepState,
      opticalBaselineCh1: opticalBaselineCh1,
      opticalBaselineCh2: opticalBaselineCh2,
      opticalBaseline: opticalBaseline,
      isOnWrist: opticalBaseline > 30000 || hrPrimary > 0,
    );
  }

  static bool _isPlausibleSkinTemperature(int value) => value >= 200 && value <= 450;

  static int _u16(Uint8List bytes, int offset) {
    _checkBounds(bytes, offset, 2);
    return ByteData.sublistView(bytes).getUint16(offset, Endian.little);
  }

  static int _i16(Uint8List bytes, int offset) {
    _checkBounds(bytes, offset, 2);
    return ByteData.sublistView(bytes).getInt16(offset, Endian.little);
  }

  static int _u32(Uint8List bytes, int offset) {
    _checkBounds(bytes, offset, 4);
    return ByteData.sublistView(bytes).getUint32(offset, Endian.little);
  }

  static double _f32(Uint8List bytes, int offset) {
    _checkBounds(bytes, offset, 4);
    return ByteData.sublistView(bytes).getFloat32(offset, Endian.little);
  }

  static void _checkBounds(Uint8List bytes, int offset, int width) {
    if (offset < 0 || offset + width > bytes.length) {
      throw RecordDecodeException(
        'V18: campo fuori payload (${offset + width} > ${bytes.length})',
      );
    }
  }
}
