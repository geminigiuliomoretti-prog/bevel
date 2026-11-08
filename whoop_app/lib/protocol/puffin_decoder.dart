import 'dart:math';
import 'dart:typed_data';

class HistoricalRecordV18 {
  final int sequence;
  final int timestampUnix;
  final int primaryHr;
  final int secondaryHr;
  final int rrCount;
  final List<int> rrIntervalsMs;
  final double accelX;
  final double accelY;
  final double accelZ;
  final double accelMagG;
  final double movementDeltaG;
  final int steps;
  final double skinTempC;
  final int sleepState;
  final int opticalBaseline;
  final bool isOnWrist;
  final String rawHex;

  HistoricalRecordV18({
    required this.sequence,
    required this.timestampUnix,
    required this.primaryHr,
    required this.secondaryHr,
    required this.rrCount,
    required this.rrIntervalsMs,
    required this.accelX,
    required this.accelY,
    required this.accelZ,
    required this.accelMagG,
    required this.movementDeltaG,
    required this.steps,
    required this.skinTempC,
    required this.sleepState,
    required this.opticalBaseline,
    required this.isOnWrist,
    required this.rawHex,
  });

  Map<String, dynamic> toMap(String serialNumber) {
    return {
      'serial_number': serialNumber,
      'timestamp_unix': timestampUnix,
      'sequence': sequence,
      'primary_hr': primaryHr,
      'secondary_hr': secondaryHr,
      'rr_count': rrCount,
      'rr_ms_json': rrIntervalsMs.toString(),
      'accel_x': accelX,
      'accel_y': accelY,
      'accel_z': accelZ,
      'accel_mag_g': accelMagG,
      'movement_delta_g': movementDeltaG,
      'steps': steps,
      'skin_temp_c': skinTempC,
      'sleep_state': sleepState,
      'optical_baseline': opticalBaseline,
      'is_on_wrist': isOnWrist ? 1 : 0,
      'raw_hex': rawHex,
    };
  }
}

class CursorMetadata0x31 {
  final String cursorHex;
  final Uint8List cursorBytes;
  final int byteLength;
  final String rawHex;

  CursorMetadata0x31({
    required this.cursorHex,
    required this.cursorBytes,
    required this.byteLength,
    required this.rawHex,
  });
}

class LiveHrRecord {
  final int primaryHr;
  final int secondaryHr;
  final int confidence;
  final int timestampUnix;

  LiveHrRecord({
    required this.primaryHr,
    required this.secondaryHr,
    required this.confidence,
    required this.timestampUnix,
  });
}

class CommandResponse0x24 {
  final int echoSeq;
  final int respCmd;
  final int strapSeq;
  final int statusCode;
  final bool isSuccess;
  final bool isInProgress;
  final Uint8List payload;

  CommandResponse0x24({
    required this.echoSeq,
    required this.respCmd,
    required this.strapSeq,
    required this.statusCode,
    required this.isSuccess,
    required this.isInProgress,
    required this.payload,
  });
}

/// Master decoder for all Puffin and BLE packet streams.
class PuffinDecoder {
  /// Converts Uint8List to uppercase hex string.
  static String bytesToHex(Uint8List bytes) {
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0').toUpperCase()).join();
  }

  /// Decodes Cursor / Metadata 0x31 packet on fd4b0005.
  ///
  /// FW 50.41.1.0 Architecture:
  /// - Wire Frame: Header (8 bytes) + Inner (>=13 bytes) + CRC32 (4 bytes)
  /// - Frame offset for 8-byte cursor: bytes 13..21
  /// - Inner payload offset: inner_offset = frame_offset - 8 = bytes 5..13
  static CursorMetadata0x31? decodeCursor0x31(Uint8List payload) {
    Uint8List inner = payload;
    // Strip outer frame header/CRC if full wire frame was passed
    if (inner.length >= 21 && inner[0] == 0xAA && inner[1] == 0x01) {
      inner = inner.sublist(8, inner.length - 4);
    }

    if (inner.isEmpty || inner[0] != 0x31) {
      return null;
    }

    if (inner.length < 13) {
      return null;
    }

    Uint8List cursorBytes = inner.sublist(5, 13);
    String cursorHex = bytesToHex(cursorBytes);

    return CursorMetadata0x31(
      cursorHex: cursorHex,
      cursorBytes: cursorBytes,
      byteLength: inner.length,
      rawHex: bytesToHex(inner),
    );
  }

  /// Decodes historical record 0x2F (FW 50.41.1.0 112-byte inner payload).
  static HistoricalRecordV18? decodeHistoricalV18(Uint8List inner) {
    if (inner.length < 24 || inner[0] != 0x2F) {
      return null;
    }

    // int formatId = inner[1]; // 0x12 = v18
    ByteData bd = ByteData.sublistView(inner);

    int sequence = bd.getUint16(2, Endian.little);
    int timestampUnix = bd.getUint32(7, Endian.little);
    int primaryHr = inner.length > 14 ? inner[14] : 0;
    int secondaryHr = inner.length > 13 ? inner[13] : 0;
    int rrCount = inner.length > 15 ? inner[15] : 0;

    List<int> rrIntervals = [];
    int maxRr = min(rrCount, 4);
    for (int i = 0; i < maxRr; i++) {
      int offset = 16 + (i * 2);
      if (offset + 2 <= inner.length) {
        int rrVal = bd.getUint16(offset, Endian.little);
        if (rrVal > 0) {
          rrIntervals.add(rrVal);
        }
      }
    }

    // Accelerometer / Gravity vector at inner[37..49] (Frame 45..57)
    double accelX = 0.0, accelY = 0.0, accelZ = 1.0;
    if (inner.length >= 49) {
      accelX = bd.getFloat32(37, Endian.little);
      accelY = bd.getFloat32(41, Endian.little);
      accelZ = bd.getFloat32(45, Endian.little);
    }
    double accelMagG = sqrt(accelX * accelX + accelY * accelY + accelZ * accelZ);
    double movementDeltaG = (accelMagG - 1.0).abs();

    // Skin temperature at inner[61..63]
    double skinTempC = 0.0;
    if (inner.length >= 63) {
      int rawTemp = bd.getInt16(61, Endian.little);
      skinTempC = rawTemp / 10.0;
    }

    // Steps at inner[73..75]
    int steps = 0;
    if (inner.length >= 75) {
      steps = bd.getUint16(73, Endian.little);
    }

    // Sleep state at inner[96]
    int sleepState = inner.length > 96 ? inner[96] : 0;

    // Optical baseline at inner[98..100] (and secondary at 106..108)
    int opticalBaseline = 0;
    if (inner.length >= 100) {
      opticalBaseline = bd.getUint16(98, Endian.little);
    }
    bool isOnWrist = opticalBaseline > 30000;

    return HistoricalRecordV18(
      sequence: sequence,
      timestampUnix: timestampUnix,
      primaryHr: primaryHr,
      secondaryHr: secondaryHr,
      rrCount: rrCount,
      rrIntervalsMs: rrIntervals,
      accelX: accelX,
      accelY: accelY,
      accelZ: accelZ,
      accelMagG: accelMagG,
      movementDeltaG: movementDeltaG,
      steps: steps,
      skinTempC: skinTempC,
      sleepState: sleepState,
      opticalBaseline: opticalBaseline,
      isOnWrist: isOnWrist,
      rawHex: bytesToHex(inner),
    );
  }

  /// Decodes Command Response 0x24.
  static CommandResponse0x24? decodeResponse0x24(Uint8List inner) {
    if (inner.length < 5 || inner[0] != 0x24) {
      return null;
    }
    int echoSeq = inner[1];
    int respCmd = inner[2];
    int strapSeq = inner[3];
    int statusCode = inner[4];
    Uint8List payload = inner.length > 5 ? inner.sublist(5) : Uint8List(0);

    return CommandResponse0x24(
      echoSeq: echoSeq,
      respCmd: respCmd,
      strapSeq: strapSeq,
      statusCode: statusCode,
      isSuccess: statusCode == 1,
      isInProgress: statusCode == 2,
      payload: payload,
    );
  }

  /// Decodes Live HR 0x28 packet.
  static LiveHrRecord? decodeLiveHr0x28(Uint8List inner) {
    if (inner.length < 6 || inner[0] != 0x28) {
      return null;
    }
    int primaryHr = inner[4];
    int secondaryHr = inner[5];
    int confidence = inner.length > 6 ? inner[6] : 100;
    int nowTs = DateTime.now().millisecondsSinceEpoch ~/ 1000;

    return LiveHrRecord(
      primaryHr: primaryHr,
      secondaryHr: secondaryHr,
      confidence: confidence,
      timestampUnix: nowTs,
    );
  }

  /// Decodes Standard BLE Heart Rate 0x2A37.
  static Map<String, dynamic> decodeStandardHr0x2A37(Uint8List value) {
    if (value.isEmpty) return {'hr': 0, 'rr_ms': <int>[]};

    int flags = value[0];
    bool is16Bit = (flags & 0x01) != 0;
    bool hasRr = (flags & 0x10) != 0;

    int offset = 1;
    int hr = 0;
    if (is16Bit) {
      if (value.length >= 3) {
        ByteData bd = ByteData.sublistView(value);
        hr = bd.getUint16(offset, Endian.little);
        offset += 2;
      }
    } else {
      if (value.length >= 2) {
        hr = value[offset];
        offset += 1;
      }
    }

    if ((flags & 0x08) != 0) {
      offset += 2; // skip energy expended
    }

    List<int> rrMs = [];
    if (hasRr) {
      ByteData bd = ByteData.sublistView(value);
      while (offset + 1 < value.length) {
        int rawRr = bd.getUint16(offset, Endian.little);
        int ms = (rawRr * 1000) ~/ 1024;
        rrMs.add(ms);
        offset += 2;
      }
    }

    return {'hr': hr, 'rr_ms': rrMs};
  }
}
