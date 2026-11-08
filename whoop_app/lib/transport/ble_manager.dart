import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:universal_ble/universal_ble.dart';
import '../protocol/puffin_framing.dart';
import '../protocol/puffin_commands.dart';
import '../protocol/puffin_decoder.dart';
import '../database/whoop_database.dart';

enum StrapConnectionState {
  disconnected,
  scanning,
  connecting,
  connected,
}

class WhoopBleManager extends ChangeNotifier {
  static final WhoopBleManager _instance = WhoopBleManager._();
  static WhoopBleManager get instance => _instance;

  WhoopBleManager._() {
    _initBle();
  }

  // UUIDs
  static const String puffinServiceUuid = 'fd4b0001-cce1-4033-93ce-002d5875f58a';
  static const String charCmdTx = 'fd4b0002-cce1-4033-93ce-002d5875f58a';
  static const String charCmdRx = 'fd4b0003-cce1-4033-93ce-002d5875f58a';
  static const String charEvents = 'fd4b0004-cce1-4033-93ce-002d5875f58a';
  static const String charDataStream = 'fd4b0005-cce1-4033-93ce-002d5875f58a';
  static const String charExtra = 'fd4b0007-cce1-4033-93ce-002d5875f58a';
  static const String charStandardHr = '00002a37-0000-1000-8000-00805f9b34fb';

  // Protocol & Reassembly
  final PuffinCommandBuilder _cmdBuilder = PuffinCommandBuilder();
  final PuffinStreamReassembler _cmdReassembler = PuffinStreamReassembler();
  final PuffinStreamReassembler _streamReassembler = PuffinStreamReassembler();

  // Command queue & synchronization
  Completer<CommandResponse0x24>? _pendingCmdCompleter;
  final List<Function> _commandQueue = [];
  bool _isSending = false;

  // Cursor Auto-ACK state
  String? _lastAckedCursor;

  // Device Info & Live State
  BleDevice? _targetDevice;
  StrapConnectionState _connectionState = StrapConnectionState.disconnected;
  String _deviceName = 'WHOOP Strap';
  String _serialNumber = '--';
  String _firmwareVersion = '--';
  int _batteryLevel = 0;
  int _liveHr = 0;
  bool _isOnWrist = false;
  int _opticalBaseline = 0;
  double _skinTempC = 0.0;
  List<int> _liveRrMs = [];
  bool _isSyncing = false;
  double _syncProgress = 0.0;
  int _syncTotalPackets = 0;
  int _syncUniqueSaved = 0;
  double _syncSpeed = 0.0;

  // Historical Batch Buffer
  final List<HistoricalRecordV18> _v18Buffer = [];
  Timer? _batchFlushTimer;

  // Public Getters
  StrapConnectionState get connectionState => _connectionState;
  String get deviceName => _deviceName;
  String get serialNumber => _serialNumber;
  String get firmwareVersion => _firmwareVersion;
  int get batteryLevel => _batteryLevel;
  int get liveHr => _liveHr;
  bool get isOnWrist => _isOnWrist;
  int get opticalBaseline => _opticalBaseline;
  double get skinTempC => _skinTempC;
  List<int> get liveRrMs => _liveRrMs;
  bool get isSyncing => _isSyncing;
  double get syncProgress => _syncProgress;
  int get syncTotalPackets => _syncTotalPackets;
  int get syncUniqueSaved => _syncUniqueSaved;
  double get syncSpeed => _syncSpeed;

  void _initBle() {
    UniversalBle.onConnectionChange = (BleConnectionChange change) {
      if (change.isConnected) {
        _setConnectionState(StrapConnectionState.connected);
      } else {
        _liveHr = 0;
        _liveRrMs = [];
        _isOnWrist = false;
        _setConnectionState(StrapConnectionState.disconnected);
        _reconnectWithBackoff();
      }
    };

    UniversalBle.onValueChange = (BleCharacteristicValue charVal) {
      _handleIncomingData(charVal.characteristicId.toLowerCase(), charVal.value);
    };

    // Periodic flush timer for historical batches
    _batchFlushTimer = Timer.periodic(const Duration(milliseconds: 500), (_) {
      _flushV18Buffer();
    });
  }

  void _setConnectionState(StrapConnectionState state) {
    _connectionState = state;
    notifyListeners();
  }

  /// Scans for and connects to the WHOOP strap.
  Future<void> connect({String? specificAddress}) async {
    if (_connectionState == StrapConnectionState.connected) return;

    _setConnectionState(StrapConnectionState.scanning);

    UniversalBle.onScanResult = (device) {
      String name = device.name ?? '';
      bool matchName = name.toUpperCase().contains('WHOOP');
      bool matchAddress = specificAddress != null &&
          device.deviceId.toUpperCase() == specificAddress.toUpperCase();

      if (matchName || matchAddress) {
        UniversalBle.stopScan();
        _targetDevice = device;
        _connectToDevice(device);
      }
    };

    try {
      await UniversalBle.startScan();
    } catch (e) {
      debugPrint('[BLE] Start scan error: $e');
      _setConnectionState(StrapConnectionState.disconnected);
    }
  }

  /// Disconnects manually, resets live state, and clears target device.
  Future<void> disconnect() async {
    try {
      await UniversalBle.stopScan();
    } catch (_) {}
    if (_targetDevice != null) {
      try {
        await UniversalBle.disconnect(_targetDevice!.deviceId);
      } catch (e) {
        debugPrint('[BLE] Disconnect error: $e');
      }
    }
    _targetDevice = null;
    _liveHr = 0;
    _liveRrMs = [];
    _opticalBaseline = 0;
    _skinTempC = 0.0;
    _isOnWrist = false;
    _setConnectionState(StrapConnectionState.disconnected);
  }

  Future<void> _connectToDevice(BleDevice device) async {
    _setConnectionState(StrapConnectionState.connecting);
    try {
      await UniversalBle.connect(device.deviceId);
      _targetDevice = device;
      _deviceName = device.name ?? 'WHOOP 5WP';

      // Discover services & subscribe
      await UniversalBle.discoverServices(device.deviceId); await Future.delayed(const Duration(milliseconds: 500));
      await _subscribeNotifications(device.deviceId);

      // Perform handshake & unlock session
      await _performUnlockHandshake();
    } catch (e) {
      debugPrint('[BLE] Connect error: $e');
      _setConnectionState(StrapConnectionState.disconnected);
      _reconnectWithBackoff();
    }
  }

  Future<void> _subscribeNotifications(String deviceId) async {
    List<String> charsToSubscribe = [
      charCmdRx,
      charEvents,
      charDataStream,
      charExtra,
      charStandardHr,
    ];

    for (String charId in charsToSubscribe) {
      try {
        await UniversalBle.subscribeNotifications(
          deviceId,
          puffinServiceUuid,
          charId,
        );
      } catch (e) {
        // Characteristic may not be present or already subscribed
      }
    }
  }

  /// Session Unlock Sequence: 0x91 GET_HELLO + 16 Feature Flags (0x78).
  Future<void> _performUnlockHandshake() async {
    try {
      // 1. GET_HELLO (0x91)
      var helloResp = await sendCommand(PuffinOpcodes.getHello);
      if (helloResp != null && helloResp.payload.length >= 24) {
        String raw = String.fromCharCodes(helloResp.payload.where((b) => b >= 32 && b <= 126));
        if (raw.length >= 10) {
          _serialNumber = raw.substring(0, 10);
        }
      }

      // 2. GET_NAME (0x8D)
      var nameResp = await sendCommand(PuffinOpcodes.getAdvertisingName);
      if (nameResp != null && nameResp.payload.isNotEmpty) {
        _deviceName = String.fromCharCodes(nameResp.payload.where((b) => b >= 32 && b <= 126));
      }

      // 3. GET_BATTERY (0x1A)
      var battResp = await sendCommand(PuffinOpcodes.getBattery);
      if (battResp != null && battResp.payload.isNotEmpty) {
        _batteryLevel = battResp.payload[0];
      }

      // 4. Register in database
      await WhoopDatabase.instance.registerDevice(
        serialNumber: _serialNumber,
        macAddress: _targetDevice?.deviceId ?? '',
        model: _deviceName,
        fwRevision: _firmwareVersion,
      );

      // 5. Unlock 16 Feature Flags (0x78)
      for (int flagId in puffin16FeatureFlags) {
        await sendCommand(
          PuffinOpcodes.setFeatureFlag,
          params: Uint8List.fromList([flagId, 0x01]),
        );
      }

      notifyListeners();
    } catch (e) {
      debugPrint('[BLE] Handshake error: $e');
    }
  }

  /// Serialized command dispatch with response Completer.
  Future<CommandResponse0x24?> sendCommand(
    int cmd, {
    int b3 = 0x01,
    Uint8List? params,
    Duration timeout = const Duration(seconds: 3),
  }) async {
    if (_targetDevice == null || _connectionState != StrapConnectionState.connected) {
      return null;
    }

    Completer<CommandResponse0x24?> execCompleter = Completer();

    _commandQueue.add(() async {
      try {
        _pendingCmdCompleter = Completer<CommandResponse0x24>();

        Uint8List frame = _cmdBuilder.buildCommand(
          cmd: cmd,
          b3: b3,
          params: params,
        );

        // Write with response (withoutResponse: false) on fd4b0002
        await UniversalBle.write(
          _targetDevice!.deviceId,
          puffinServiceUuid,
          charCmdTx,
          frame,
          withoutResponse: false,
        );

        var result = await _pendingCmdCompleter!.future.timeout(timeout);
        execCompleter.complete(result);
      } catch (e) {
        execCompleter.complete(null);
      } finally {
        _pendingCmdCompleter = null;
      }
    });

    _processQueue();
    return execCompleter.future;
  }

  void _processQueue() async {
    if (_isSending || _commandQueue.isEmpty) return;
    _isSending = true;
    var task = _commandQueue.removeAt(0);
    try {
      await task();
    } finally {
      _isSending = false;
      if (_commandQueue.isNotEmpty) {
        _processQueue();
      }
    }
  }

  /// Starts high-speed historical offload (0x16) with progress monitoring.
  Future<void> startHistoricalSync({int durationSeconds = 30}) async {
    if (_isSyncing) return;
    _isSyncing = true;
    _syncProgress = 0.0;
    _syncTotalPackets = 0;
    _syncUniqueSaved = 0;
    _syncSpeed = 0.0;
    notifyListeners();

    try {
      // 1. Query Range 0x22
      await sendCommand(PuffinOpcodes.getDataRange, b3: 0x00);

      // 2. Trigger offload 0x16
      await sendCommand(PuffinOpcodes.sendHistorical, b3: 0x00);

      // Progress countdown
      int elapsed = 0;
      DateTime start = DateTime.now();

      while (elapsed < durationSeconds && _isSyncing) {
        await Future.delayed(const Duration(seconds: 1));
        elapsed++;
        _syncProgress = elapsed / durationSeconds;
        double sec = DateTime.now().difference(start).inMilliseconds / 1000.0;
        if (sec > 0) {
          _syncSpeed = (_syncTotalPackets / sec * 10).round() / 10.0;
        }
        notifyListeners();
      }
    } finally {
      await _flushV18Buffer();
      _isSyncing = false;
      _syncProgress = 1.0;
      notifyListeners();
    }
  }

  /// Sends 0x42 ALARM_CONTROL vibration test to the physical strap.
  Future<bool> sendAlarmVibration({int pattern = 1, int durationMs = 1000}) async {
    try {
      Uint8List frame = _cmdBuilder.buildAlarmControl(pattern: pattern, durationMs: durationMs);
      if (_targetDevice != null) {
        await UniversalBle.write(
          _targetDevice!.deviceId,
          puffinServiceUuid,
          charCmdTx,
          frame,
          withoutResponse: false,
        );
        return true;
      }
    } catch (e) {
      debugPrint('[BLE] Alarm vibration error: $e');
    }
    return false;
  }

  void _handleIncomingData(String charId, Uint8List rawChunk) {
    if (charId.contains('fd4b0003')) {
      // Command Response RX
      List<Uint8List> frames = _cmdReassembler.feed(rawChunk);
      for (var f in frames) {
        Uint8List inner = extractInnerPayload(f);
        var resp = PuffinDecoder.decodeResponse0x24(inner);
        if (resp != null && !resp.isInProgress) {
          if (_pendingCmdCompleter != null && !_pendingCmdCompleter!.isCompleted) {
            _pendingCmdCompleter!.complete(resp);
          }
        }
      }
    } else if (charId.contains('fd4b0005')) {
      // Data Stream (0x28 live, 0x2F v18, 0x31 cursor)
      List<Uint8List> frames = _streamReassembler.feed(rawChunk);
      for (var f in frames) {
        Uint8List inner = extractInnerPayload(f);
        if (inner.isEmpty) continue;
        int opcode = inner[0];

        if (opcode == 0x28) {
          // Live Heart Rate
          var live = PuffinDecoder.decodeLiveHr0x28(inner);
          if (live != null) {
            _liveHr = live.primaryHr;
            notifyListeners();
          }
        } else if (opcode == 0x2F) {
          // Historical Record v18
          _syncTotalPackets++;
          var v18 = PuffinDecoder.decodeHistoricalV18(inner);
          if (v18 != null) {
            _isOnWrist = v18.isOnWrist;
            _opticalBaseline = v18.opticalBaseline;
            _skinTempC = v18.skinTempC;
            if (v18.primaryHr > 0) _liveHr = v18.primaryHr;
            if (v18.rrIntervalsMs.isNotEmpty) _liveRrMs = v18.rrIntervalsMs;
            _v18Buffer.add(v18);
            if (_v18Buffer.length >= 25) {
              _flushV18Buffer();
            }
            notifyListeners();
          }
        } else if (opcode == 0x31) {
          // Cursor metadata -> Deduplicated Auto-ACK
          var cursorMeta = PuffinDecoder.decodeCursor0x31(inner);
          if (cursorMeta != null) {
            String cHex = cursorMeta.cursorHex;
            if (cHex != _lastAckedCursor) {
              _lastAckedCursor = cHex;
              _sendCursorAck(cursorMeta.cursorBytes);

              // Update DB checkpoint
              if (_v18Buffer.isNotEmpty) {
                WhoopDatabase.instance.updateSyncCheckpoint(
                  serialNumber: _serialNumber,
                  syncTimestampUnix: _v18Buffer.last.timestampUnix,
                  cursorHex: cHex,
                );
              }
            }
          }
        }
      }
    } else if (charId.contains('2a37')) {
      // Standard BLE Heart Rate
      var stdHr = PuffinDecoder.decodeStandardHr0x2A37(rawChunk);
      int hr = stdHr['hr'] as int;
      if (hr > 0) {
        _liveHr = hr;
        var rrs = stdHr['rr_ms'];
        if (rrs is List<int> && rrs.isNotEmpty) {
          _liveRrMs = List<int>.from(rrs);
        }
        notifyListeners();
      }
    }
  }

  void _sendCursorAck(Uint8List cursor8b) {
    // Send single 0x17 ACK with 8-byte cursor (low latency 800ms)
    sendCommand(
      PuffinOpcodes.historicalDataResult,
      b3: 0x01,
      params: cursor8b,
      timeout: const Duration(milliseconds: 800),
    );
  }

  Future<void> _flushV18Buffer() async {
    if (_v18Buffer.isEmpty) return;

    List<HistoricalRecordV18> batch = List.from(_v18Buffer);
    _v18Buffer.clear();

    try {
      var stats = await WhoopDatabase.instance.ingestRecordsBatch(_serialNumber, batch);
      _syncUniqueSaved += stats['records_inserted'] ?? 0;
    } catch (e) {
      debugPrint('[DB] Batch flush error: $e');
    }
  }

  void _reconnectWithBackoff() async {
    if (_targetDevice == null) return;
    await Future.delayed(const Duration(seconds: 3));
    if (_connectionState == StrapConnectionState.disconnected) {
      _connectToDevice(_targetDevice!);
    }
  }

  void cancelTimers() {
    _batchFlushTimer?.cancel();
    _batchFlushTimer = null;
  }

  @override
  void dispose() {
    cancelTimers();
    super.dispose();
  }
}
