import 'dart:typed_data';

import 'package:beveltry/src/records/v18_record.dart';
import 'package:beveltry/src/records/v26_record.dart';
import 'package:beveltry/src/repository/whoop_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  group('WhoopRepository & SQLite Persistence Tests', () {
    late WhoopRepository repository;

    setUp(() async {
      repository = WhoopRepository.inMemory();
    });

    tearDown(() async {
      await repository.close();
    });

    V18Record createSampleRecord({
      int seq = 100,
      DateTime? timestamp,
      int hrPrimary = 65,
      int hrSecondary = 64,
      List<int> rrIntervals = const [920, 930],
      double gravityX = 0.05,
      double gravityY = 0.10,
      double gravityZ = 0.98,
      int stepCounter = 1250,
      int? skinTempRaw = 315,
      int activityFlag = 1,
      int spo2Candidate = 0,
      int sleepState = 1,
      int opticalBaseline = 35000,
      bool isOnWrist = true,
    }) {
      return V18Record(
        seq: seq,
        timestamp: timestamp ?? DateTime.utc(2026, 11, 7, 12, 0, 0),
        hrPrimary: hrPrimary,
        hrSecondary: hrSecondary,
        rrCount: rrIntervals.length,
        rrIntervalsMs: rrIntervals,
        gravityX: gravityX,
        gravityY: gravityY,
        gravityZ: gravityZ,
        accelMagG: 0.986,
        stepCounter: stepCounter,
        skinTempRaw: skinTempRaw,
        skinTempCelsius: skinTempRaw != null ? skinTempRaw / 10.0 : null,
        activityFlag: activityFlag,
        spo2Candidate: spo2Candidate,
        sleepState: sleepState,
        opticalBaselineCh1: opticalBaseline,
        opticalBaselineCh2: opticalBaseline - 500,
        opticalBaseline: opticalBaseline,
        isOnWrist: isOnWrist,
      );
    }

    test('Salvataggio doppio dello stesso record scarta il duplicato (vincolo UNIQUE)', () async {
      final record = createSampleRecord(
        seq: 42,
        timestamp: DateTime.utc(2026, 11, 7, 10, 30, 0),
      );
      const strapSerial = '5AG0558675';

      // Primo salvataggio
      await repository.saveV18Record(record, strapSerial);
      expect(await repository.countV18Records(strapSerial: strapSerial), equals(1));
      expect(await repository.countRrIntervals(), equals(2));

      // Secondo salvataggio con lo stesso (strap_serial, seq) - re-delivery hardware
      await repository.saveV18Record(record, strapSerial);

      // Nel database deve esserci ancora ESATTAMENTE 1 riga in v18_records e 2 righe in rr_intervals
      expect(await repository.countV18Records(strapSerial: strapSerial), equals(1));
      expect(await repository.countRrIntervals(), equals(2));
    });

    test('Salvataggio di 1 record con 2 R-R crea 2 righe collegate in rr_intervals', () async {
      final record = createSampleRecord(
        seq: 55,
        timestamp: DateTime.utc(2026, 11, 7, 11, 0, 0),
        rrIntervals: const [880, 895],
      );
      const strapSerial = '5AG0558675';

      await repository.saveV18Record(record, strapSerial);

      // Verifica che la tabella rr_intervals contenga 2 righe
      expect(await repository.countRrIntervals(), equals(2));

      final records = await repository.getRecordsInRange(
        DateTime.utc(2026, 11, 7, 10, 59, 0),
        DateTime.utc(2026, 11, 7, 11, 1, 0),
      );

      expect(records.length, equals(1));
      final loaded = records.first;
      expect(loaded.seq, equals(55));
      expect(loaded.rrCount, equals(2));
      expect(loaded.rrIntervalsMs, equals([880, 895]));
      expect(loaded.hrPrimary, equals(65));
      expect(loaded.hrSecondary, equals(64));
      expect(loaded.opticalBaseline, equals(35000));
      expect(loaded.isOnWrist, isTrue);
    });

    test('Lettura per range temporale restituisce solo i record nell\'intervallo specificato', () async {
      const strapSerial = '5AG0558675';

      final r1 = createSampleRecord(
        seq: 1,
        timestamp: DateTime.utc(2026, 11, 7, 12, 0, 0),
        hrPrimary: 60,
      );
      final r2 = createSampleRecord(
        seq: 2,
        timestamp: DateTime.utc(2026, 11, 7, 12, 0, 10),
        hrPrimary: 65,
      );
      final r3 = createSampleRecord(
        seq: 3,
        timestamp: DateTime.utc(2026, 11, 7, 12, 0, 20),
        hrPrimary: 70,
      );
      final r4 = createSampleRecord(
        seq: 4,
        timestamp: DateTime.utc(2026, 11, 7, 12, 0, 30),
        hrPrimary: 75,
      );

      await repository.saveV18RecordsBatch([r1, r2, r3, r4], strapSerial);
      expect(await repository.countV18Records(), equals(4));

      // Range che include solo r2 ed r3 (12:00:05 - 12:00:25)
      final results = await repository.getRecordsInRange(
        DateTime.utc(2026, 11, 7, 12, 0, 5),
        DateTime.utc(2026, 11, 7, 12, 0, 25),
      );

      expect(results.length, equals(2));
      expect(results[0].seq, equals(2));
      expect(results[0].hrPrimary, equals(65));
      expect(results[1].seq, equals(3));
      expect(results[1].hrPrimary, equals(70));

      // Range vuoto
      final emptyResults = await repository.getRecordsInRange(
        DateTime.utc(2026, 11, 7, 13, 0, 0),
        DateTime.utc(2026, 11, 7, 14, 0, 0),
      );
      expect(emptyResults, isEmpty);
    });

    test('Persistenza del cursore offload (saveCursor e getLastCursor)', () async {
      final initialCursor = await repository.getLastCursor();
      expect(initialCursor, isNull);

      final cursorData = Uint8List.fromList([0x0D, 0x2C, 0xCC, 0x6A, 0xEC, 0x00, 0x00, 0x00]);
      await repository.saveCursor(cursorData);

      final loadedCursor = await repository.getLastCursor();
      expect(loadedCursor, isNotNull);
      expect(loadedCursor, equals(cursorData));

      // Aggiornamento del cursore
      final updatedCursor = Uint8List.fromList([0x3C, 0x02, 0x8F, 0x6A, 0xEC, 0x00, 0x00, 0x00]);
      await repository.saveCursor(updatedCursor);

      final currentCursor = await repository.getLastCursor();
      expect(currentCursor, equals(updatedCursor));
    });

    test('Salvataggio di V26Record e deduplicazione su (strap_serial, seq)', () async {
      const strapSerial = '5AG0558675';
      final ppg = List<int>.generate(24, (i) => (i * 10) - 100);
      final v26 = V26Record(ppgSamples: ppg);

      await repository.saveV26Record(v26, strapSerial, seq: 10);
      expect(await repository.countV26Records(strapSerial: strapSerial), equals(1));

      // Re-delivery con stessa sequenza
      await repository.saveV26Record(v26, strapSerial, seq: 10);

      // Verifichiamo che il vincolo UNIQUE mantenga 1 solo record
      expect(await repository.countV26Records(strapSerial: strapSerial), equals(1));
    });

    test('Dati salvati mantengono integrità fisiologica e R-R in millisecondi diretti', () async {
      const strapSerial = '5AG0558675';
      final record = createSampleRecord(
        seq: 77,
        timestamp: DateTime.utc(2026, 11, 7, 15, 30, 45),
        hrPrimary: 72,
        hrSecondary: 71,
        rrIntervals: const [833, 840, 825],
        gravityX: 0.12,
        gravityY: -0.05,
        gravityZ: 0.99,
        stepCounter: 3400,
        skinTempRaw: 322,
        activityFlag: 2,
        spo2Candidate: 0,
        sleepState: 0,
        opticalBaseline: 42000,
        isOnWrist: true,
      );

      await repository.saveV18Record(record, strapSerial);

      final loaded = await repository.getRecordsInRange(
        DateTime.utc(2026, 11, 7, 15, 0, 0),
        DateTime.utc(2026, 11, 7, 16, 0, 0),
      );

      expect(loaded.length, equals(1));
      final rec = loaded.first;
      expect(rec.seq, equals(77));
      expect(rec.timestamp, equals(DateTime.utc(2026, 11, 7, 15, 30, 45)));
      expect(rec.hrPrimary, equals(72));
      expect(rec.hrSecondary, equals(71));
      expect(rec.rrCount, equals(3));
      expect(rec.rrIntervalsMs, equals([833, 840, 825]));
      expect(rec.gravityX, closeTo(0.12, 0.001));
      expect(rec.gravityY, closeTo(-0.05, 0.001));
      expect(rec.gravityZ, closeTo(0.99, 0.001));
      expect(rec.stepCounter, equals(3400));
      expect(rec.skinTempRaw, equals(322));
      expect(rec.skinTempCelsius, closeTo(32.2, 0.01));
      expect(rec.activityFlag, equals(2));
      expect(rec.spo2Candidate, equals(0));
      expect(rec.sleepState, equals(0));
      expect(rec.opticalBaseline, equals(42000));
      expect(rec.isOnWrist, isTrue);

      final rrs = await repository.getRrIntervalsInRange(
        DateTime.utc(2026, 11, 7, 15, 0, 0),
        DateTime.utc(2026, 11, 7, 16, 0, 0),
      );
      expect(rrs, equals([833, 840, 825]));
    });
  });
}
