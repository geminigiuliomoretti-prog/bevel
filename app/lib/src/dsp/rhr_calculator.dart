import '../records/v18_record.dart';

/// Calcola la frequenza cardiaca a riposo (RHR - Resting Heart Rate).
///
/// Utilizza l'euristica della finestra mobile di 5 minuti (300 secondi)
/// con la frequenza cardiaca media più bassa registrata durante il periodo notturno.
int calculateRhr(
  List<V18Record> nightRecords, {
  int windowSeconds = 300,
}) {
  final validHrs = nightRecords
      .where((r) => r.hrPrimary > 0 && r.hrPrimary <= 240)
      .map((r) => r.hrPrimary)
      .toList();

  return calculateRhrFromHrValues(validHrs, windowSize: windowSeconds);
}

/// Calcola l'RHR direttamente da una serie temporale 1Hz di battiti cardiaci (BPM).
///
/// Identifica la finestra continua di ampiezza [windowSize] con la media
/// cardiaca minima e ne restituisce il valore arrotondato.
int calculateRhrFromHrValues(
  List<int> hrValues, {
  int windowSize = 300,
}) {
  final valid = hrValues.where((hr) => hr > 0 && hr <= 240).toList();
  if (valid.isEmpty) return 0;

  if (valid.length <= windowSize) {
    final sum = valid.fold<int>(0, (acc, hr) => acc + hr);
    return (sum / valid.length).round();
  }

  var currentSum = 0;
  for (var i = 0; i < windowSize; i++) {
    currentSum += valid[i];
  }
  var minSum = currentSum;

  for (var i = windowSize; i < valid.length; i++) {
    currentSum += valid[i] - valid[i - windowSize];
    if (currentSum < minSum) {
      minSum = currentSum;
    }
  }

  return (minSum / windowSize).round();
}

/// Helper opzionale per filtrare record appartenenti alla finestra notturna
/// (stato di sonno `sleep_state == 2` o fascia oraria 00:00 - 06:00).
List<V18Record> filterNightRecords(List<V18Record> records) {
  return records.where((r) {
    if (r.hrPrimary <= 0) return false;
    final hour = r.timestamp.toUtc().hour;
    final isNightHours = hour >= 0 && hour < 6;
    final isDeepSleep = r.sleepState == 2;
    return isNightHours || isDeepSleep;
  }).toList();
}
