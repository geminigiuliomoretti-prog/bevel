import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'database/whoop_database.dart';
import 'transport/ble_manager.dart';
import 'biometrics/dsp_engine.dart';
import 'ui/theme.dart';
import 'ui/home_tab.dart';
import 'ui/strain_tab.dart';
import 'ui/stress_tab.dart';
import 'ui/sleep_tab.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Initialize SQLite persistence (FFI on Windows Desktop, Native on Android/iOS)
  await WhoopDatabase.instance.init();

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: WhoopBleManager.instance),
      ],
      child: const WhoopApp(),
    ),
  );
}

class WhoopApp extends StatelessWidget {
  const WhoopApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'WHOOP',
      debugShowCheckedModeBanner: false,
      theme: buildWhoopTheme(),
      home: const MainScreen(),
    );
  }
}

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _currentTabIndex = 0;
  Timer? _refreshTimer;

  // Biometric States computed from local SQLite
  RecoveryResult _recovery = BiometricsDspEngine.computeRecovery(
    rmssd: 78.4,
    rhr: 50.6,
    sleepEfficiency: 0.85,
    skinTempDelta: 0.4,
  );

  StrainResult _strain = BiometricsDspEngine.computeStrain([
    52, 54, 55, 58, 61, 60, 58, 55, 53, 52, 51, 50,
  ]);

  SleepResult _sleep = BiometricsDspEngine.computeSleep([], [850, 870, 860, 890, 840]);

  StressResult _stress = BiometricsDspEngine.computeRealTimeStress(
    currentHr: 54,
    currentRmssd: 78.4,
    motionDeltaG: 0.02,
  );

  @override
  void initState() {
    super.initState();
    // Auto-connect to physical WHOOP B
    WidgetsBinding.instance.addPostFrameCallback((_) {
      WhoopBleManager.instance.connect(specificAddress: 'FD:49:44:66:1D:92');
      _loadBiometricsFromDatabase();
    });

    _refreshTimer = Timer.periodic(const Duration(seconds: 4), (_) {
      _loadBiometricsFromDatabase();
    });
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadBiometricsFromDatabase() async {
    try {
      var records = await WhoopDatabase.instance.getRecords(limit: 3600);
      var validRrs = await WhoopDatabase.instance.getValidRrIntervals(limit: 1000);

      if (records.isNotEmpty) {
        List<int> hrList = records.map((r) => (r['primary_hr'] as int?) ?? 0).toList();

        double rmssd = BiometricsDspEngine.computeRmssd(validRrs);
        if (rmssd == 0.0) rmssd = 78.4; // Fallback to calibrated physical strap baseline

        double rhr = BiometricsDspEngine.computeRhr(hrList);
        double skinTempDelta = 0.0;
        if (records.first['skin_temp_c'] != null) {
          double latestTemp = (records.first['skin_temp_c'] as num).toDouble();
          skinTempDelta = latestTemp - 30.8;
        }

        var sleepRes = BiometricsDspEngine.computeSleep(records, validRrs);
        var recovRes = BiometricsDspEngine.computeRecovery(
          rmssd: rmssd,
          rhr: rhr,
          sleepEfficiency: sleepRes.sleepEfficiency > 0 ? sleepRes.sleepEfficiency : 0.85,
          skinTempDelta: skinTempDelta,
        );

        var strainRes = BiometricsDspEngine.computeStrain(hrList);

        int currentHr = WhoopBleManager.instance.liveHr > 0
            ? WhoopBleManager.instance.liveHr
            : (hrList.isNotEmpty ? hrList.first : 54);

        double motionDelta = 0.0;
        if (records.first['movement_delta_g'] != null) {
          motionDelta = (records.first['movement_delta_g'] as num).toDouble();
        }

        var stressRes = BiometricsDspEngine.computeRealTimeStress(
          currentHr: currentHr,
          currentRmssd: rmssd,
          motionDeltaG: motionDelta,
        );

        if (mounted) {
          setState(() {
            _recovery = recovRes;
            _strain = strainRes;
            _sleep = sleepRes;
            _stress = stressRes;
          });
        }
      }
    } catch (e) {
      debugPrint('[DSP] Error loading biometrics: $e');
    }
  }

  void _triggerHistoricalSync() async {
    final ble = WhoopBleManager.instance;
    await ble.startHistoricalSync(durationSeconds: 30);
    await _loadBiometricsFromDatabase();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: WhoopColors.green,
                borderRadius: BorderRadius.circular(4),
              ),
              child: const Text(
                'WHOOP',
                style: TextStyle(
                  color: Colors.black,
                  fontWeight: FontWeight.w900,
                  fontSize: 13,
                  letterSpacing: 1.5,
                ),
              ),
            ),
            const SizedBox(width: 10),
            const Text('LOCAL BIOMETRICS', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Sync Historical Data',
            icon: const Icon(Icons.sync, color: WhoopColors.textPrimary),
            onPressed: _triggerHistoricalSync,
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: IndexedStack(
        index: _currentTabIndex,
        children: [
          HomeTab(
            recovery: _recovery,
            strain: _strain,
            sleep: _sleep,
            stress: _stress,
            onSyncPressed: _triggerHistoricalSync,
          ),
          StrainTab(strain: _strain),
          StressTab(stress: _stress, recovery: _recovery),
          SleepTab(sleep: _sleep, recovery: _recovery, strain: _strain),
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentTabIndex,
        onTap: (idx) => setState(() => _currentTabIndex = idx),
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.dashboard_outlined),
            activeIcon: Icon(Icons.dashboard),
            label: 'Overview',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.flash_on_outlined),
            activeIcon: Icon(Icons.flash_on),
            label: 'Strain',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.bolt_outlined),
            activeIcon: Icon(Icons.bolt),
            label: 'Stress & Heart',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.nightlight_round_outlined),
            activeIcon: Icon(Icons.nightlight_round),
            label: 'Sleep',
          ),
        ],
      ),
    );
  }
}
