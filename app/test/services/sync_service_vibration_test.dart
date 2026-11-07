import 'package:beveltry/src/ble/ble.dart';
import 'package:beveltry/src/repository/whoop_repository.dart';
import 'package:beveltry/src/services/sync_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('SyncService Vibration Tests', () {
    late WhoopRepository repository;
    late SimulatedPuffinTransport transport;
    late SyncService syncService;

    setUp(() {
      repository = WhoopRepository.inMemory();
      transport = SimulatedPuffinTransport();
      syncService = SyncService(
        repository: repository,
        transport: transport,
      );
    });

    tearDown(() async {
      await repository.close();
    });

    test('sendVibration invia il comando 0x42 con envelope Puffin e parametri corretti', () async {
      expect(transport.sentFrames, isEmpty);

      final success = await syncService.sendVibration(
        slot: 1,
        pattern: 1,
        durationMs: 1000,
      );

      expect(success, isTrue);
      expect(transport.sentFrames.length, equals(1));

      final frame = transport.sentFrames.first;
      // Verifica Header Envelope: SOF=0xAA, Ver=0x01
      expect(frame[0], equals(0xAA));
      expect(frame[1], equals(0x01));

      // Decodifica il frame per verificare il comando interno
      final innerPayload = PuffinFrameCodec.decode(frame);
      expect(innerPayload[0], equals(0x23)); // Command prefix
      expect(innerPayload[1], equals(1));    // Sequence 1
      expect(innerPayload[2], equals(0x42)); // Opcode SET_ALARM_TIME / ALARM_CONTROL
      expect(innerPayload[3], equals(0x01)); // Slot 1
      expect(innerPayload[4], equals(0x01)); // Pattern 1
      expect(innerPayload[5], equals(0xE8)); // 1000 ms lower byte
      expect(innerPayload[6], equals(0x03)); // 1000 ms upper byte
    });

    test('sendVibration incrementa il sequence number per chiamate successive', () async {
      await syncService.sendVibration(slot: 1);
      await syncService.sendVibration(slot: 1);

      expect(transport.sentFrames.length, equals(2));
      final inner1 = PuffinFrameCodec.decode(transport.sentFrames[0]);
      final inner2 = PuffinFrameCodec.decode(transport.sentFrames[1]);

      expect(inner1[1], equals(1));
      expect(inner2[1], equals(2));
    });

    test('sendVibration fallisce se il trasporto non è connesso', () async {
      transport.isConnected = false;
      final success = await syncService.sendVibration(slot: 1);
      expect(success, isFalse);
      expect(transport.sentFrames, isEmpty);
      expect(
        syncService.statusMessageNotifier.value,
        contains('cinturino non connesso'),
      );
    });
  });
}
