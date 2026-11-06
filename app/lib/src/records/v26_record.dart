import 'dart:typed_data';

import 'record_decode_exception.dart';

/// Record V26 con 24 campioni PPG signed a 24 Hz.
class V26Record {
  const V26Record({required this.ppgSamples});

  final List<int> ppgSamples;

  static const int payloadLength = 88;

  static V26Record decode(Uint8List payload) {
    if (payload.length < payloadLength) {
      throw const RecordDecodeException('V26: payload inferiore a 88 byte');
    }
    if (payload[0] != 0x2F) {
      throw const RecordDecodeException('V26: type atteso 0x2F');
    }
    if (payload[1] != 0x1A) {
      throw const RecordDecodeException('V26: version attesa 0x1A');
    }

    final data = ByteData.sublistView(payload);
    return V26Record(
      ppgSamples: List<int>.unmodifiable(
        List<int>.generate(
          24,
          (index) => data.getInt16(27 + index * 2, Endian.little),
        ),
      ),
    );
  }
}
