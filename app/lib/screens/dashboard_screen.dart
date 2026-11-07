import 'package:flutter/material.dart';

import 'package:beveltry/src/repository/whoop_repository.dart';
import 'package:beveltry/src/services/metrics_service.dart';
import 'package:beveltry/src/services/sync_service.dart';

/// Schermata principale della dashboard funzionale (v0.1).
///
/// Mostra:
/// - Due riquadri per RHR (Resting Heart Rate) ed HRV (RMSSD)
/// - Due pulsanti di azione ("Sincronizza WHOOP" e "Calcola Metriche")
/// - Un log ad elenco con l'avanzamento delle operazioni
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({
    super.key,
    this.repository,
    this.syncService,
    this.metricsService,
  });

  final WhoopRepository? repository;
  final SyncService? syncService;
  final MetricsService? metricsService;

  @override
  State<DashboardScreen> createState() => DashboardScreenState();
}

class DashboardScreenState extends State<DashboardScreen> {
  late final WhoopRepository _repository;
  late final SyncService _syncService;
  late final MetricsService _metricsService;

  DailyMetrics? _latestMetrics;
  bool _isCalculating = false;
  final List<String> _logs = [];
  final ScrollController _logScrollController = ScrollController();

  @visibleForTesting
  bool get isCalculating => _isCalculating;

  @visibleForTesting
  DailyMetrics? get latestMetrics => _latestMetrics;

  @visibleForTesting
  List<String> get logs => List.unmodifiable(_logs);

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? WhoopRepository();
    _syncService = widget.syncService ?? SyncService(repository: _repository);
    _metricsService =
        widget.metricsService ?? MetricsService(repository: _repository);

    _syncService.statusMessageNotifier.addListener(_onSyncStatusChanged);
    _addLog('Sistema inizializzato. Pronto per la sincronizzazione.');
  }

  @override
  void dispose() {
    _syncService.statusMessageNotifier.removeListener(_onSyncStatusChanged);
    _logScrollController.dispose();
    if (widget.repository == null) {
      _repository.close();
    }
    super.dispose();
  }

  void _onSyncStatusChanged() {
    _addLog(_syncService.statusMessageNotifier.value);
  }

  void _addLog(String message) {
    if (!mounted) return;
    final now = DateTime.now();
    final timeStr =
        '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}:${now.second.toString().padLeft(2, '0')}';
    setState(() {
      _logs.add('[$timeStr] $message');
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_logScrollController.hasClients) {
        _logScrollController.jumpTo(_logScrollController.position.maxScrollExtent);
      }
    });
  }

  Future<void> _handleSync() async {
    if (_syncService.isSyncing) {
      _addLog('Attenzione: sincronizzazione già in corso.');
      return;
    }

    _addLog('Avvio sincronizzazione WHOOP...');
    final count = await _syncService.startSync();
    if (count == 0 && _syncService.statusNotifier.value == SyncStatus.error) {
      _addLog('Nessun dato scaricato.');
    }
  }

  Future<void> _handleCalculateMetrics() async {
    setState(() => _isCalculating = true);
    _addLog('Calcolo metriche fisiologiche in corso...');

    try {
      final metrics = await _metricsService.calculateMetricsForLastNight();
      setState(() {
        _latestMetrics = metrics;
      });

      if (metrics.recordCount == 0) {
        _addLog('Nessun dato scaricato: database vuoto per le ultime 24h.');
      } else {
        final rhrStr = metrics.rhr != null ? '${metrics.rhr} bpm' : 'Dati insufficienti';
        final hrvStr = (metrics.hrvRmssd == null ||
                metrics.hrvRmssd == 0.0 ||
                metrics.recordCount < 10)
            ? 'Dati insufficienti'
            : '${metrics.hrvRmssd} ms';
        _addLog(
          'Calcolo completato: ${metrics.recordCount} record analizzati. RHR: $rhrStr, HRV: $hrvStr.',
        );
      }
    } catch (e) {
      _addLog('Errore durante il calcolo: $e');
    } finally {
      if (mounted) {
        setState(() => _isCalculating = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Beveltry'),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // 1. Riquadri principali Metriche (RHR e HRV)
              Row(
                children: [
                  Expanded(
                    child: _buildMetricCard(
                      title: 'RHR',
                      subtitle: 'Frequenza a Riposo',
                      value: _latestMetrics?.rhr != null
                          ? '${_latestMetrics!.rhr} bpm'
                          : 'Dati insufficienti',
                      icon: Icons.favorite,
                      color: Colors.redAccent,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _buildMetricCard(
                      title: 'HRV (RMSSD)',
                      subtitle: 'Variabilità Cardiaca',
                      value: (_latestMetrics == null ||
                              _latestMetrics!.hrvRmssd == null ||
                              _latestMetrics!.hrvRmssd == 0.0 ||
                              _latestMetrics!.recordCount < 10)
                          ? 'Dati insufficienti'
                          : '${_latestMetrics!.hrvRmssd} ms',
                      icon: Icons.timeline,
                      color: Colors.teal,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),

              // 2. Pulsanti di Azione
              ValueListenableBuilder<SyncStatus>(
                valueListenable: _syncService.statusNotifier,
                builder: (context, status, _) {
                  final isSyncing = _syncService.isSyncing;
                  return Row(
                    children: [
                      Expanded(
                        child: ElevatedButton.icon(
                          onPressed: isSyncing ? null : _handleSync,
                          icon: isSyncing
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.sync),
                          label: Text(
                            isSyncing
                                ? 'Sincronizzazione...'
                                : 'Sincronizza WHOOP',
                          ),
                          style: ElevatedButton.styleFrom(
                            padding: const EdgeInsets.symmetric(vertical: 14),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: ElevatedButton.icon(
                          onPressed:
                              _isCalculating ? null : _handleCalculateMetrics,
                          icon: _isCalculating
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.analytics_outlined),
                          label: const Text('Calcola Metriche'),
                          style: ElevatedButton.styleFrom(
                            padding: const EdgeInsets.symmetric(vertical: 14),
                          ),
                        ),
                      ),
                    ],
                  );
                },
              ),
              const SizedBox(height: 16),

              // 3. Log delle Operazioni a schermo
              const Text(
                'Log Operazioni',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
              ),
              const SizedBox(height: 8),
              Expanded(
                child: Container(
                  decoration: BoxDecoration(
                    color: Theme.of(context)
                        .colorScheme
                        .surfaceContainerHighest
                        .withValues(alpha: 0.5),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: Colors.grey.withValues(alpha: 0.3),
                    ),
                  ),
                  child: ListView.builder(
                    controller: _logScrollController,
                    padding: const EdgeInsets.all(8),
                    itemCount: _logs.length,
                    itemBuilder: (context, index) {
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 2.0),
                        child: Text(
                          _logs[index],
                          style: const TextStyle(
                            fontFamily: 'monospace',
                            fontSize: 12,
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildMetricCard({
    required String title,
    required String subtitle,
    required String value,
    required IconData icon,
    required Color color,
  }) {
    final hasData = value != 'Dati insufficienti';
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color, size: 22),
                const SizedBox(width: 8),
                Text(
                  title,
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              subtitle,
              style: TextStyle(color: Colors.grey.shade600, fontSize: 11),
            ),
            const SizedBox(height: 12),
            Text(
              value,
              style: TextStyle(
                fontSize: hasData ? 22 : 14,
                fontWeight: hasData ? FontWeight.bold : FontWeight.w500,
                color: hasData ? color : Colors.grey.shade600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
