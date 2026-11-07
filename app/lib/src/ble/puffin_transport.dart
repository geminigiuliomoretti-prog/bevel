import 'dart:typed_data';

/// Characteristic GATT utilizzate dal servizio Puffin Gen 5 (`fd4b`).
enum PuffinCharacteristic {
  cmdToStrap,
  cmdFromStrap,
  eventsFromStrap,
  dataFromStrap,
  memfault,
}

/// Contratto per il trasporto BLE di basso livello verso il WHOOP 5.0.
abstract class PuffinTransport {
  /// Invia un frame binario envelope al cinturino.
  Future<void> write(
    Uint8List frame, {
    PuffinCharacteristic characteristic = PuffinCharacteristic.cmdToStrap,
  });

  /// Indica se il trasporto è connesso e pronto all'invio.
  bool get isConnected;
}

/// Trasporto simulato per test e per esecuzione in ambienti senza hardware connesso.
class SimulatedPuffinTransport implements PuffinTransport {
  SimulatedPuffinTransport({this.isConnected = true});

  @override
  bool isConnected;

  /// Registro dei frame inviati durante la sessione.
  final List<Uint8List> sentFrames = [];

  @override
  Future<void> write(
    Uint8List frame, {
    PuffinCharacteristic characteristic = PuffinCharacteristic.cmdToStrap,
  }) async {
    sentFrames.add(Uint8List.fromList(frame));
  }
}
