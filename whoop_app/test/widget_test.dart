import 'package:flutter_test/flutter_test.dart';
import 'package:whoop_app/ui/theme.dart';
import 'package:whoop_app/biometrics/dsp_engine.dart';
import 'package:whoop_app/ui/home_tab.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:whoop_app/transport/ble_manager.dart';

void main() {
  test('WhoopBleManager zero mock values and disconnect() verification', () async {
    final ble = WhoopBleManager.instance;

    expect(ble.batteryLevel, equals(0));
    expect(ble.opticalBaseline, equals(0));
    expect(ble.skinTempC, equals(0.0));
    expect(ble.liveRrMs, isEmpty);
    expect(ble.liveHr, equals(0));
    expect(ble.isOnWrist, isFalse);
    expect(ble.connectionState, equals(StrapConnectionState.disconnected));

    await ble.disconnect();
    expect(ble.connectionState, equals(StrapConnectionState.disconnected));
  });

  testWidgets('HomeTab UI components smoke test and connect button', (WidgetTester tester) async {
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
    expect(find.text('CONNECT STRAP'), findsOneWidget);
    expect(find.text('DISCONNECTED'), findsOneWidget);
    expect(find.text('OFFLINE'), findsOneWidget);

    WhoopBleManager.instance.cancelTimers();
  });
}
