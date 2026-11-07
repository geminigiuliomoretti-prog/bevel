/// Filtro per artefatti negli intervalli R-R beat-to-beat.
///
/// Rimuove battiti ectopici, mancate rilevazioni o artefatti da movimento
/// prima del calcolo di metriche di variabilità cardiaca (HRV / RMSSD).
class RrArtifactFilter {
  const RrArtifactFilter({
    this.maxRelativeDiff = 0.20,
    this.maxAbsoluteDiffMs,
    this.minPhysiologicalMs = 250,
    this.maxPhysiologicalMs = 2500,
  });

  /// Soglia massima di differenza relativa rispetto al battito valido precedente (default 20%).
  final double maxRelativeDiff;

  /// Soglia massima assoluta in millisecondi (opzionale, es. 200 ms).
  final int? maxAbsoluteDiffMs;

  /// Limite fisiologico inferiore in ms (default 250 ms, pari a 240 bpm).
  final int minPhysiologicalMs;

  /// Limite fisiologico superiore in ms (default 2500 ms, pari a 24 bpm).
  final int maxPhysiologicalMs;

  /// Filtra una sequenza di intervalli R-R grezzi.
  ///
  /// Un intervallo è accettato se:
  /// 1. È compreso nei limiti fisiologici plausibili ([minPhysiologicalMs], [maxPhysiologicalMs]).
  /// 2. La differenza relativa con l'ultimo intervallo valido accettato è `< maxRelativeDiff`.
  /// 3. Se [maxAbsoluteDiffMs] è specificato, la differenza assoluta è `<= maxAbsoluteDiffMs`.
  ///
  /// Gli intervalli non conformi vengono rimossi; il confronto successivo
  /// avviene contro l'ultimo battito valido.
  List<int> filter(List<int> rawRrIntervals) {
    if (rawRrIntervals.isEmpty) return const [];
    final filtered = <int>[];

    for (final rr in rawRrIntervals) {
      if (rr < minPhysiologicalMs || rr > maxPhysiologicalMs) {
        continue;
      }

      if (filtered.isEmpty) {
        filtered.add(rr);
        continue;
      }

      final prev = filtered.last;
      final diff = (rr - prev).abs();
      final relDiff = diff / prev;

      final isRelativeValid = relDiff < maxRelativeDiff;
      final isAbsoluteValid =
          maxAbsoluteDiffMs == null || diff <= maxAbsoluteDiffMs!;

      if (isRelativeValid && isAbsoluteValid) {
        filtered.add(rr);
      }
    }

    return filtered;
  }
}
