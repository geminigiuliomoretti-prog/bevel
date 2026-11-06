import 'dart:typed_data';

import 'record_decode_exception.dart';

enum Live28Validity { offWrist, hrAndRr, hrRrAndExtra }

/// Pacchetto compatto di frequenza cardiaca in tempo reale.
class Live28Record {
  const Live28Record({
    required this.timestamp,
    required this.hr,
    required this.validity,
    required this.rrIntervalMs,
  });

  final DateTime timestamp;
  final int hr;
  final Live28Validity validity;
  final int rrIntervalMs;

  static const int payloadLength = 12;

  static Live28Record decode(Uint8List payload) {
    if (payload.length < payloadLength) {
      throw const RecordDecodeException('Live28: payload inferiore a 12 byte');
    }
    if (payload[0] != 0x28) {
      throw const RecordDecodeException('Live28: type atteso 0x28');
    }
    if (payload[1] != 0x02) {
      throw const RecordDecodeException('Live28: version attesa 0x02');
    }

    final validity = switch (payload[9]) {
      0 => Live28Validity.offWrist,
      1 => Live28Validity.hrAndRr,
      2 => Live28Validity.hrRrAndExtra,
      _ => throw const RecordDecodeException('Live28: validity sconosciuta'),
    };
    final data = ByteData.sublistView(payload);
    final timestampSeconds = data.getUint32(2, Endian.little);

    return Live28Record(
      timestamp: DateTime.fromMillisecondsSinceEpoch(
        timestampSeconds * 1000,
        isUtc: true,
      ),
      hr: payload[8],
      validity: validity,
      rrIntervalMs: data.getUint16(10, Endian.little),
    );
  }
}
