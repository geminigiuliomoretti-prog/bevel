import 'package:flutter_test/flutter_test.dart';
import 'package:whoop_app/ui/theme.dart';
import 'package:whoop_app/biometrics/dsp_engine.dart';
import 'package:whoop_app/ui/home_tab.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:whoop_app/transport/ble_manager.dart';

void main() {
  testWidgets('HomeTab UI components smoke test', (WidgetTester tester) async {
    final recovery = BiometricsDspEngine.computeRecovery(
      rmssd: 78.4,
      rhr: 50.6,
      sleepEfficiency: 0.85,
    );
    final strain = BiometricsDspEngine.computeStrain([50, 55, 60]);
    final sleep = BiometricsDspEngine.computeSleep([], [800, 820]);
    final stress = BiometricsDspEngine.computeRealTimeStress(
      currentHr: 54,
      currentRmssd: 78.4,
      motionDeltaG: 0.02,
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: buildWhoopTheme(),
        home: Scaffold(
          body: ChangeNotifierProvider.value(
            value: WhoopBleManager.instance,
            child: HomeTab(
              recovery: recovery,
              strain: strain,
              sleep: sleep,
              stress: stress,
              onSyncPressed: () {},
            ),
          ),
        ),
      ),
    );

    expect(find.text('RECOVERY'), findsOneWidget);
    expect(find.text('DAY STRAIN'), findsOneWidget);
    expect(find.text('LIVE HEART RATE'), findsOneWidget);
    expect(find.text('SYNC FLASH DATA'), findsOneWidget);
    expect(find.text('VIBRATE'), findsOneWidget);

    WhoopBleManager.instance.cancelTimers();
  });
}
