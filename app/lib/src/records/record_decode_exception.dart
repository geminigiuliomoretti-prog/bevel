/// Errore uniforme per payload record corti, incoerenti o non supportati.
class RecordDecodeException implements Exception {
  const RecordDecodeException(this.message);

  final String message;

  @override
  String toString() => 'RecordDecodeException: $message';
}
