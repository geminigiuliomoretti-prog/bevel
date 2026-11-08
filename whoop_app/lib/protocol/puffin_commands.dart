import 'dart:typed_data';
import 'puffin_framing.dart';

/// Opcodes allowed for transmission.
class PuffinOpcodes {
  static const int getHello = 0x91;
  static const int getAdvertisingName = 0x8D;
  static const int getClock = 0x0B;
  static const int setClock = 0x0C;
  static const int getBattery = 0x1A;
  static const int setFeatureFlag = 0x78;
  static const int getDataRange = 0x22;
  static const int sendHistorical = 0x16;
  static const int historicalDataResult = 0x17;
  static const int alarmControl = 0x42;
  static const int keyExchange = 0x73;

  // DANGEROUS OPCODES THAT MUST ALWAYS BE BLOCKED
  static const int eraseFlash = 0x19;
  static const int rebootStrap = 0x1D;

  static const Set<int> allowedOpcodes = {
    getHello,
    getAdvertisingName,
    getClock,
    setClock,
    getBattery,
    setFeatureFlag,
    getDataRange,
    sendHistorical,
    historicalDataResult,
    alarmControl,
    keyExchange,
  };
}

/// The 16 Gen 5 Feature Flags required for full telemetry offload.
const List<int> puffin16FeatureFlags = [
  0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
  0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
];

/// Builds validated, safe Puffin command frames.
class PuffinCommandBuilder {
  int _sequence = 0;

  int nextSequence() {
    _sequence = (_sequence + 1) & 0xFF;
    if (_sequence == 0) _sequence = 1;
    return _sequence;
  }

  /// Builds a command frame [0x23, seq, cmd, b3, ...params].
  Uint8List buildCommand({
    required int cmd,
    int b3 = 0x01,
    Uint8List? params,
    int? explicitSeq,
  }) {
    if (cmd == PuffinOpcodes.eraseFlash || cmd == PuffinOpcodes.rebootStrap) {
      throw SecurityException(
        'OPCODE 0x${cmd.toRadixString(16).padLeft(2, '0').toUpperCase()} IS DANGEROUS AND STRICTLY BLOCKED.',
      );
    }

    if (!PuffinOpcodes.allowedOpcodes.contains(cmd)) {
      throw SecurityException(
        'Opcode 0x${cmd.toRadixString(16).padLeft(2, '0').toUpperCase()} not in safety allowlist.',
      );
    }

    int seq = explicitSeq ?? nextSequence();
    int paramLen = params != null ? params.length : 0;
    Uint8List inner = Uint8List(4 + paramLen);
    inner[0] = 0x23; // Command header
    inner[1] = seq & 0xFF;
    inner[2] = cmd & 0xFF;
    inner[3] = b3 & 0xFF;

    if (params != null && params.isNotEmpty) {
      inner.setRange(4, 4 + paramLen, params);
    }

    return buildPuffinFrame(inner);
  }

  /// 0x91 GET_HELLO
  Uint8List buildGetHello({int? seq}) =>
      buildCommand(cmd: PuffinOpcodes.getHello, b3: 0x01, explicitSeq: seq);

  /// 0x8D GET_ADVERTISING_NAME
  Uint8List buildGetName({int? seq}) =>
      buildCommand(cmd: PuffinOpcodes.getAdvertisingName, b3: 0x01, explicitSeq: seq);

  /// 0x0B GET_CLOCK
  Uint8List buildGetClock({int? seq}) =>
      buildCommand(cmd: PuffinOpcodes.getClock, b3: 0x01, explicitSeq: seq);

  /// 0x0C SET_CLOCK
  Uint8List buildSetClock(int unixTimestamp, {int? seq}) {
    ByteData bd = ByteData(4);
    bd.setUint32(0, unixTimestamp, Endian.little);
    return buildCommand(
      cmd: PuffinOpcodes.setClock,
      b3: 0x01,
      params: bd.buffer.asUint8List(),
      explicitSeq: seq,
    );
  }

  /// 0x1A GET_BATTERY
  Uint8List buildGetBattery({int? seq}) =>
      buildCommand(cmd: PuffinOpcodes.getBattery, b3: 0x01, explicitSeq: seq);

  /// 0x78 SET_FEATURE_FLAG
  Uint8List buildSetFeatureFlag(int flagId, int value, {int? seq}) {
    Uint8List params = Uint8List.fromList([flagId & 0xFF, value & 0xFF]);
    return buildCommand(
      cmd: PuffinOpcodes.setFeatureFlag,
      b3: 0x01,
      params: params,
      explicitSeq: seq,
    );
  }

  /// 0x22 GET_DATA_RANGE
  Uint8List buildGetDataRange({int? seq}) =>
      buildCommand(cmd: PuffinOpcodes.getDataRange, b3: 0x00, explicitSeq: seq);

  /// 0x16 SEND_HISTORICAL
  Uint8List buildSendHistorical({int b3 = 0x00, Uint8List? params, int? seq}) =>
      buildCommand(cmd: PuffinOpcodes.sendHistorical, b3: b3, params: params, explicitSeq: seq);

  /// 0x17 HISTORICAL_DATA_RESULT (with 8-byte cursor)
  Uint8List buildHistoricalDataResult(Uint8List cursor8b, {int? seq}) {
    if (cursor8b.length != 8) {
      throw ArgumentError('Cursor must be exactly 8 bytes (received ${cursor8b.length})');
    }
    return buildCommand(
      cmd: PuffinOpcodes.historicalDataResult,
      b3: 0x01,
      params: cursor8b,
      explicitSeq: seq,
    );
  }

  /// 0x42 ALARM_CONTROL
  Uint8List buildAlarmControl({int pattern = 1, int durationMs = 1000, int? seq}) {
    ByteData bd = ByteData(3);
    bd.setUint8(0, pattern & 0xFF);
    bd.setUint16(1, durationMs & 0xFFFF, Endian.little);
    return buildCommand(
      cmd: PuffinOpcodes.alarmControl,
      b3: 0x01,
      params: bd.buffer.asUint8List(),
      explicitSeq: seq,
    );
  }
}

class SecurityException implements Exception {
  final String message;
  SecurityException(this.message);
  @override
  String toString() => 'SecurityException: $message';
}
