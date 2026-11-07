import 'dart:math' as math;

/// Calcola l'indice HRV RMSSD (Root Mean Square of Successive Differences).
///
/// Formula standard Task Force 1996:
/// ```
/// RMSSD = sqrt( sum( (RR[i] - RR[i-1])^2 ) / (N - 1) )
/// ```
///
/// Richiede almeno 2 intervalli R-R per poter calcolare almeno una differenza.
/// Restituisce `null` se [filteredRrIntervalsMs] ha meno di 2 elementi.
/// Il risultato è espresso in millisecondi (ms).
double? calculateRmssd(List<int> filteredRrIntervalsMs) {
  if (filteredRrIntervalsMs.length < 2) {
    return null;
  }

  var sumSquaredDiffs = 0.0;
  final n = filteredRrIntervalsMs.length;

  for (var i = 1; i < n; i++) {
    final diff = (filteredRrIntervalsMs[i] - filteredRrIntervalsMs[i - 1]).toDouble();
    sumSquaredDiffs += diff * diff;
  }

  final meanSquaredDiff = sumSquaredDiffs / (n - 1);
  return math.sqrt(meanSquaredDiff);
}
