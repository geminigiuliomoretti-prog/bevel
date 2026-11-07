import 'package:beveltry/screens/dashboard_screen.dart';
import 'package:beveltry/src/repository/whoop_repository.dart';
import 'package:beveltry/src/services/metrics_service.dart';
import 'package:beveltry/src/services/sync_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfiNoIsolate;
  });

  Widget createTestWidget({
    required WhoopRepository repository,
  }) {
    final syncService = SyncService(
      repository: repository,
      simulateIfNoHardware: true,
    );
    final metricsService = MetricsService(repository: repository);

    return MaterialApp(
      home: DashboardScreen(
        repository: repository,
        syncService: syncService,
        metricsService: metricsService,
      ),
    );
  }

  testWidgets('Dashboard UI: mostra titolo, pulsanti e card RHR/HRV', (tester) async {
    final repository = WhoopRepository.inMemory();

    await tester.pumpWidget(createTestWidget(repository: repository));
    await tester.pumpAndSettle();

    // 1. Titolo AppBar
    expect(find.text('Beveltry'), findsOneWidget);

    // 2. Card RHR e HRV
    expect(find.text('RHR'), findsOneWidget);
    expect(find.text('HRV (RMSSD)'), findsOneWidget);
    expect(find.text('Dati insufficienti'), findsNWidgets(2));

    // 3. Due pulsanti
    expect(find.text('Sincronizza WHOOP'), findsOneWidget);
    expect(find.text('Calcola Metriche'), findsOneWidget);

    // 4. Sezione log
    expect(find.text('Log Operazioni'), findsOneWidget);
    expect(
      find.textContaining('Sistema inizializzato'),
      findsOneWidget,
    );

    await repository.close();
  });

  testWidgets('Dashboard UI: flusso completo Sincronizza e poi Calcola Metriche', (tester) async {
    final repository = WhoopRepository.inMemory();
    final syncService = SyncService(
      repository: repository,
      simulateIfNoHardware: true,
    );
    final metricsService = MetricsService(repository: repository);

    await tester.pumpWidget(MaterialApp(
      home: DashboardScreen(
        repository: repository,
        syncService: syncService,
        metricsService: metricsService,
      ),
    ));
    await tester.pump();

    // Click su "Sincronizza WHOOP"
    final syncButton = find.text('Sincronizza WHOOP');
    expect(syncButton, findsOneWidget);

    await tester.runAsync(() async {
      await tester.tap(syncButton);
      while (syncService.isSyncing) {
        await Future.delayed(const Duration(milliseconds: 20));
      }
    });
    await tester.pump();

    // Verifica che il log riporti il completamento del sync
    expect(find.textContaining('Sincronizzazione completata'), findsOneWidget);

    // Click su "Calcola Metriche"
    final calcButton = find.text('Calcola Metriche');
    expect(calcButton, findsOneWidget);

    final state = tester.state<DashboardScreenState>(find.byType(DashboardScreen));
    await tester.runAsync(() async {
      await tester.tap(calcButton);
      for (var i = 0; i < 50; i++) {
        if (!state.isCalculating && state.latestMetrics != null) break;
        await Future.delayed(const Duration(milliseconds: 20));
      }
    });
    await tester.pump();

    // Verifica che la card RHR sia valorizzata e che la card HRV mostri "Dati insufficienti"
    // (a causa di HRV = 0.0 su 30 record a frequenza costante)
    expect(find.textContaining('bpm'), findsAtLeastNWidgets(1));
    expect(find.text('Dati insufficienti'), findsAtLeastNWidgets(1));
    expect(state.latestMetrics, isNotNull);
    expect(state.latestMetrics!.rhr, isNotNull);
    expect(state.latestMetrics!.hrvRmssd, equals(0.0));
    expect(state.latestMetrics!.isHrvValid, isFalse);

    // Verifica che il log indichi il calcolo avvenuto
    expect(find.textContaining('Calcolo completato'), findsOneWidget);

    // Smonta il widget per invocare dispose() prima di chiudere il repository
    await tester.pumpWidget(const SizedBox());
    await repository.close();
  });
}
