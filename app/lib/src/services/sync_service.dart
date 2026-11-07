import 'dart:async';

import 'package:flutter/foundation.dart';

import '../records/record_decoder.dart';
import '../records/v18_record.dart';
import '../repository/whoop_repository.dart';

/// Stati possibili del processo di sincronizzazione con WHOOP.
enum SyncStatus {
  idle,
  connecting,
  syncing,
  completed,
  error,
}

/// Servizio che orchestra la sincronizzazione e l'offload dati dal WHOOP 5.0.
///
/// Si occupa di:
/// - Avviare il flusso di ricezione frame
/// - Decodificare i frame `0x2F` tramite [RecordDecoder]
/// - Salvare i record [V18Record] nel [WhoopRepository]
/// - Notificare lo stato e il conteggio di avanzamento
class SyncService {
  SyncService({
    required this.repository,
    this.strapSerial = '5AG0558675',
    Stream<Uint8List>? frameStream,
    this.simulateIfNoHardware = true,
  }) : _customFrameStream = frameStream;

  final WhoopRepository repository;
  final String strapSerial;
  final Stream<Uint8List>? _customFrameStream;
  final bool simulateIfNoHardware;

  final ValueNotifier<SyncStatus> statusNotifier =
      ValueNotifier<SyncStatus>(SyncStatus.idle);
  final ValueNotifier<String> statusMessageNotifier =
      ValueNotifier<String>('Pronto per la sincronizzazione.');
  final ValueNotifier<int> recordsSavedNotifier = ValueNotifier<int>(0);

  bool _isCancelled = false;

  bool get isSyncing =>
      statusNotifier.value == SyncStatus.connecting ||
      statusNotifier.value == SyncStatus.syncing;

  /// Avvia l'offload e la memorizzazione dei record.
  ///
  /// Restituisce il numero totale di record salvati in questa sessione.
  Future<int> startSync({int simulationRecordCount = 30}) async {
    if (isSyncing) {
      statusMessageNotifier.value = 'Sincronizzazione già in corso.';
      return 0;
    }

    _isCancelled = false;
    recordsSavedNotifier.value = 0;
    statusNotifier.value = SyncStatus.connecting;
    statusMessageNotifier.value = 'Connessione al cinturino $strapSerial...';

    try {
      if (_customFrameStream != null) {
        return await _syncFromStream(_customFrameStream);
      } else if (simulateIfNoHardware) {
        return await _syncSimulated(recordCount: simulationRecordCount);
      } else {
        statusNotifier.value = SyncStatus.error;
        statusMessageNotifier.value = 'Nessun canale BLE hardware disponibile.';
        return 0;
      }
    } catch (e) {
      statusNotifier.value = SyncStatus.error;
      statusMessageNotifier.value = 'Errore di sincronizzazione: $e';
      return recordsSavedNotifier.value;
    }
  }

  /// Interrompe la sincronizzazione in corso.
  void stopSync() {
    if (isSyncing) {
      _isCancelled = true;
      statusMessageNotifier.value = 'Interruzione sincronizzazione richiesta...';
    }
  }

  Future<int> _syncFromStream(Stream<Uint8List> stream) async {
    statusNotifier.value = SyncStatus.syncing;
    var saved = 0;

    await for (final rawFrame in stream) {
      if (_isCancelled) break;

      try {
        final decoded = RecordDecoder.decode(rawFrame);
        if (decoded is V18Record) {
          await repository.saveV18Record(decoded, strapSerial);
          saved++;
          recordsSavedNotifier.value = saved;
          statusMessageNotifier.value = 'Scaricati $saved record...';
        }
      } catch (err) {
        // Ignora frame non riconosciuti o corrotti e prosegue
      }
    }

    statusNotifier.value = SyncStatus.completed;
    statusMessageNotifier.value =
        _isCancelled ? 'Sincronizzazione interrotta.' : 'Sincronizzazione completata: $saved record salvati.';
    return saved;
  }

  Future<int> _syncSimulated({int recordCount = 360}) async {
    statusNotifier.value = SyncStatus.syncing;
    statusMessageNotifier.value = 'Avvio offload storico BLE (Puffin 0x16)...';

    final baseTime = DateTime.now().toUtc().subtract(Duration(seconds: recordCount));
    final records = <V18Record>[];

    for (var i = 0; i < recordCount; i++) {
      if (_isCancelled) break;

      final ts = baseTime.add(Duration(seconds: i));
      final isDeepSleep = i >= 30 && i < 330; // 5 minuti di deep sleep sostenuto a 52 bpm
      final hr = isDeepSleep ? 52 : 68;
      final rrMs = (60000 / hr).round();

      final payload = _generateV18Payload(
        seq: i + 1,
        timestampSeconds: ts.millisecondsSinceEpoch ~/ 1000,
        hrPrimary: hr,
        hrSecondary: hr - 1,
        rrIntervals: [rrMs],
        sleepState: isDeepSleep ? 2 : 1,
      );

      final record = RecordDecoder.decode(payload);
      if (record is V18Record) {
        records.add(record);
      }
    }

    if (records.isNotEmpty) {
      await repository.saveV18RecordsBatch(records, strapSerial);
    }

    final saved = records.length;
    recordsSavedNotifier.value = saved;
    statusNotifier.value = SyncStatus.completed;
    statusMessageNotifier.value =
        _isCancelled ? 'Sincronizzazione interrotta ($saved salvati).' : 'Sincronizzazione completata: $saved record salvati.';
    return saved;
  }

  /// Costruisce un payload interno V18 valido da 112 byte conforme al protocollo WHOOP.
  static Uint8List _generateV18Payload({
    required int seq,
    required int timestampSeconds,
    required int hrPrimary,
    required int hrSecondary,
    required List<int> rrIntervals,
    required int sleepState,
  }) {
    final payload = Uint8List(112);
    final data = ByteData.sublistView(payload);

    payload[0] = 0x2F; // Historical burst
    payload[1] = 0x12; // v18 version
    data.setUint16(2, seq, Endian.little);
    data.setUint32(7, timestampSeconds, Endian.little);
    payload[14] = hrPrimary;
    final rrCount = rrIntervals.length.clamp(0, 4);
    payload[15] = rrCount;

    for (var i = 0; i < rrCount; i++) {
      data.setUint16(16 + i * 2, rrIntervals[i], Endian.little);
    }

    payload[29] = hrSecondary;
    data.setFloat32(37, 0.0, Endian.little); // Gravity X
    data.setFloat32(41, 0.0, Endian.little); // Gravity Y
    data.setFloat32(45, 1.0, Endian.little); // Gravity Z
    data.setUint16(57, 100, Endian.little);  // Steps
    data.setInt16(61, 320, Endian.little);   // Skin temp (32.0 C)
    payload[64] = 0;                        // Activity flag
    payload[82] = 0;                        // SpO2 candidate
    payload[96] = sleepState;               // Sleep state
    data.setUint16(98, 35000, Endian.little);  // Optical baseline Ch1
    data.setUint16(106, 35000, Endian.little); // Optical baseline Ch2

    return payload;
  }
}
