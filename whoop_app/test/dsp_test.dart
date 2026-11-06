import 'package:flutter_test/flutter_test.dart';
import 'package:whoop_app/biometrics/dsp_engine.dart';

void main() {
  group('Biometrics DSP Engine Tests', () {
    test('computeRmssd matches Task Force 1996 standard', () {
      List<int> rrs = [800, 810, 790, 820, 805];
      // diffs: 10, -20, 30, -15
      // sqDiffs: 100, 400, 900, 225 = 1625
      // mean: 1625 / 4 = 406.25
      // sqrt(406.25) = 20.1556
      double rmssd = BiometricsDspEngine.computeRmssd(rrs);
      expect(rmssd, closeTo(20.15, 0.05));
    });

    test('computeRhr sustained 5th-10th percentile', () {
      List<int> hrs = List.generate(100, (i) => 50 + (i % 40));
      double rhr = BiometricsDspEngine.computeRhr(hrs);
      expect(rhr, greaterThanOrEqualTo(50.0));
      expect(rhr, lessThanOrEqualTo(56.0));
    });

    test('computeStrain logarithmic accumulation', () {
      // 10 minutes at Zone 2 (Base)
      List<int> hrs = List.filled(600, 140);
      var strain = BiometricsDspEngine.computeStrain(hrs, maxUserHr: 190, restHr: 55);

      expect(strain.score, greaterThan(0.0));
      expect(strain.score, lessThanOrEqualTo(21.0));
      expect(strain.zoneSeconds['zone2'], equals(600));
    });

    test('computeRecovery traffic light and Z-score synthesis', () {
      // Super fit nocturnal markers
      var recovGreen = BiometricsDspEngine.computeRecovery(
        rmssd: 85.0,
        rhr: 48.0,
        sleepEfficiency: 0.92,
      );
      expect(recovGreen.category, equals(RecoveryCategory.green));
      expect(recovGreen.score, greaterThanOrEqualTo(67));

      // Exhausted / low HRV markers
      var recovRed = BiometricsDspEngine.computeRecovery(
        rmssd: 25.0,
        rhr: 68.0,
        sleepEfficiency: 0.55,
      );
      expect(recovRed.category, equals(RecoveryCategory.red));
      expect(recovRed.score, lessThanOrEqualTo(33));
    });

    test('computeRealTimeStress motion decoupling', () {
      // Stationary high heart rate -> high mental/autonomic stress
      var stressStationary = BiometricsDspEngine.computeRealTimeStress(
        currentHr: 95,
        currentRmssd: 30.0,
        motionDeltaG: 0.02,
      );
      expect(stressStationary.motionDecoupled, isFalse);
      expect(stressStationary.stressScore, greaterThan(1.5));

      // Same heart rate while moving (e.g. running 0.45g) -> decoupled from stress
      var stressMoving = BiometricsDspEngine.computeRealTimeStress(
        currentHr: 95,
        currentRmssd: 30.0,
        motionDeltaG: 0.45,
      );
      expect(stressMoving.motionDecoupled, isTrue);
      expect(stressMoving.stressScore, lessThan(1.0));
      expect(stressMoving.label, equals('LOW'));
    });
  });
}
