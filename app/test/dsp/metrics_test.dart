import 'package:beveltry/src/dsp/dsp.dart';
import 'package:beveltry/src/records/v18_record.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('RrArtifactFilter Tests', () {
    const filter = RrArtifactFilter();

    test('Filtro: scarta picchi anomali > 20% (es. 2000 ms tra battiti a ~800 ms)', () {
      final raw = [800, 810, 820, 2000, 830];
      final filtered = filter.filter(raw);

      // Il 2000 viene scartato, 830 viene confrontato con 820 ed è accettato
      expect(filtered, equals([800, 810, 820, 830]));
    });

    test('Filtro: lista vuota restituisce lista vuota', () {
      expect(filter.filter([]), isEmpty);
    });

    test('Filtro: scarta battiti fuori limiti fisiologici (< 250 ms o > 2500 ms)', () {
      final raw = [150, 800, 810, 3000, 820];
      final filtered = filter.filter(raw);
      expect(filtered, equals([800, 810, 820]));
    });

    test('Filtro: rispetta soglia assoluta configurabile maxAbsoluteDiffMs', () {
      const strictFilter = RrArtifactFilter(
        maxRelativeDiff: 0.50,
        maxAbsoluteDiffMs: 50,
      );
      // 800 -> 870: diff è 70 ms (> 50 ms), viene scartato
      final raw = [800, 870, 820];
      final filtered = strictFilter.filter(raw);
      expect(filtered, equals([800, 820]));
    });
  });

  group('HRV RMSSD Tests', () {
    test('RMSSD: sequenza costante ha variabilità zero', () {
      final intervals = [1000, 1000, 1000, 1000];
      final rmssd = calculateRmssd(intervals);
      expect(rmssd, isNotNull);
      expect(rmssd, equals(0.0));
    });

    test('RMSSD: sequenza alternata [800, 900, 800, 900] produce esattamente 100.0 ms', () {
      // Differenze successive: [900-800, 800-900, 900-800] = [100, -100, 100]
      // Quadrati: [10000, 10000, 10000]
      // Media quadrati: 30000 / 3 = 10000
      // sqrt(10000) = 100.0
      final intervals = [800, 900, 800, 900];
      final rmssd = calculateRmssd(intervals);
      expect(rmssd, isNotNull);
      expect(rmssd, closeTo(100.0, 0.001));
    });

    test('RMSSD con pochi dati: lista vuota o con 1 solo elemento restituisce null', () {
      expect(calculateRmssd([]), isNull);
      expect(calculateRmssd([850]), isNull);
    });

    test('RMSSD con 2 elementi: calcola la differenza assoluta esatta', () {
      // Differenza = 880 - 800 = 80. sqrt(80^2 / 1) = 80.0
      final rmssd = calculateRmssd([800, 880]);
      expect(rmssd, isNotNull);
      expect(rmssd, closeTo(80.0, 0.001));
    });
  });

  group('RHR (Resting Heart Rate) Tests', () {
    V18Record createSyntheticRecord({
      required int seq,
      required DateTime timestamp,
      required int hr,
      int sleepState = 1,
    }) {
      return V18Record(
        seq: seq,
        timestamp: timestamp,
        hrPrimary: hr,
        hrSecondary: hr,
        rrCount: 1,
        rrIntervalsMs: [hr > 0 ? (60000 ~/ hr) : 0],
        gravityX: 0.0,
        gravityY: 0.0,
        gravityZ: 1.0,
        accelMagG: 1.0,
        stepCounter: 0,
        skinTempRaw: 320,
        skinTempCelsius: 32.0,
        activityFlag: 0,
        spo2Candidate: 0,
        sleepState: sleepState,
        opticalBaselineCh1: 35000,
        opticalBaselineCh2: 35000,
        opticalBaseline: 35000,
        isOnWrist: hr > 0,
      );
    }

    test('RHR: identifica la finestra di 5 minuti (300s) con media più bassa', () {
      final baseTime = DateTime.utc(2026, 11, 7, 1, 0, 0);
      final records = <V18Record>[];
      var seq = 1;

      // 1. 10 minuti (600 secondi) a 70 bpm
      for (var s = 0; s < 600; s++) {
        records.add(createSyntheticRecord(
          seq: seq++,
          timestamp: baseTime.add(Duration(seconds: s)),
          hr: 70,
        ));
      }

      // 2. 5 minuti (300 secondi) in cui l'HR scende a 50 bpm
      for (var s = 600; s < 900; s++) {
        records.add(createSyntheticRecord(
          seq: seq++,
          timestamp: baseTime.add(Duration(seconds: s)),
          hr: 50,
          sleepState: 2, // deep sleep
        ));
      }

      // 3. 10 minuti (600 secondi) in cui risale a 70 bpm
      for (var s = 900; s < 1500; s++) {
        records.add(createSyntheticRecord(
          seq: seq++,
          timestamp: baseTime.add(Duration(seconds: s)),
          hr: 70,
        ));
      }

      // Calcola l'RHR sulla serie notturna
      final rhr = calculateRhr(records, windowSeconds: 300);

      // La finestra di 5 minuti con media minima ha esattamente 50 bpm
      expect(rhr, equals(50));
    });

    test('RHR: ignora i campioni off-wrist (hrPrimary == 0)', () {
      final baseTime = DateTime.utc(2026, 11, 7, 2, 0, 0);
      final records = <V18Record>[
        // Alcuni zeri da off-wrist
        createSyntheticRecord(seq: 1, timestamp: baseTime, hr: 0),
        createSyntheticRecord(seq: 2, timestamp: baseTime.add(const Duration(seconds: 1)), hr: 0),
      ];

      // Aggiungi 300 secondi a 54 bpm
      for (var s = 2; s < 302; s++) {
        records.add(createSyntheticRecord(
          seq: s + 1,
          timestamp: baseTime.add(Duration(seconds: s)),
          hr: 54,
        ));
      }

      final rhr = calculateRhr(records, windowSeconds: 300);
      expect(rhr, equals(54));
    });

    test('RHR: con meno di 300 campioni calcola la media su tutti i campioni validi', () {
      final baseTime = DateTime.utc(2026, 11, 7, 3, 0, 0);
      final records = [
        createSyntheticRecord(seq: 1, timestamp: baseTime, hr: 50),
        createSyntheticRecord(seq: 2, timestamp: baseTime.add(const Duration(seconds: 1)), hr: 60),
      ];

      final rhr = calculateRhr(records, windowSeconds: 300);
      expect(rhr, equals(55)); // (50 + 60) / 2 = 55
    });

    test('RHR: lista vuota restituisce 0', () {
      expect(calculateRhr([]), equals(0));
    });

    test('filterNightRecords: filtra per ore notturne (00:00-06:00 UTC) o deep sleep', () {
      final recDay = createSyntheticRecord(
        seq: 1,
        timestamp: DateTime.utc(2026, 11, 7, 14, 0, 0),
        hr: 75,
        sleepState: 0,
      );
      final recNight = createSyntheticRecord(
        seq: 2,
        timestamp: DateTime.utc(2026, 11, 7, 3, 0, 0),
        hr: 52,
        sleepState: 1,
      );
      final recDeepSleepDay = createSyntheticRecord(
        seq: 3,
        timestamp: DateTime.utc(2026, 11, 7, 15, 0, 0),
        hr: 50,
        sleepState: 2,
      );

      final filtered = filterNightRecords([recDay, recNight, recDeepSleepDay]);
      expect(filtered.length, equals(2));
      expect(filtered.map((r) => r.seq), containsAll([2, 3]));
    });
  });
}
