import 'dart:typed_data';

import 'record_decode_exception.dart';

/// Decodifica il payload WHOOP della caratteristica Heart Rate Measurement.
class StandardHrRecord {
  const StandardHrRecord({
    required this.hr,
    required this.energyExpended,
    required this.rrIntervalsMs,
  });

  final int hr;
  final int? energyExpended;
  final List<int> rrIntervalsMs;

  static StandardHrRecord decode(Uint8List payload) {
    if (payload.isEmpty) {
      throw const RecordDecodeException('0x2A37: payload vuoto');
    }

    final flags = payload[0];
    var offset = 1;
    final wideHr = (flags & 0x01) != 0;
    final hrWidth = wideHr ? 2 : 1;
    _requireBytes(payload, offset, hrWidth, 'heart rate');
    final data = ByteData.sublistView(payload);
    final hr = wideHr ? data.getUint16(offset, Endian.little) : payload[offset];
    offset += hrWidth;

    int? energyExpended;
    if ((flags & 0x08) != 0) {
      _requireBytes(payload, offset, 2, 'energy expended');
      energyExpended = data.getUint16(offset, Endian.little);
      offset += 2;
    }

    final rrIntervals = <int>[];
    if ((flags & 0x10) != 0) {
      final remaining = payload.length - offset;
      if (remaining.isOdd) {
        throw const RecordDecodeException('0x2A37: intervallo R-R incompleto');
      }
      while (offset < payload.length) {
        // Nel flusso WHOOP questi u16 sono già millisecondi: nessuna conversione.
        rrIntervals.add(data.getUint16(offset, Endian.little));
        offset += 2;
      }
    } else if (offset != payload.length) {
      throw const RecordDecodeException('0x2A37: byte finali senza flag R-R');
    }

    return StandardHrRecord(
      hr: hr,
      energyExpended: energyExpended,
      rrIntervalsMs: List<int>.unmodifiable(rrIntervals),
    );
  }

  static void _requireBytes(
    Uint8List payload,
    int offset,
    int length,
    String field,
  ) {
    if (payload.length - offset < length) {
      throw RecordDecodeException('0x2A37: $field incompleto');
    }
  }
}
