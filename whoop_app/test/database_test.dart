import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:whoop_app/database/whoop_database.dart';
import 'package:whoop_app/protocol/puffin_decoder.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  group('WhoopDatabase FFI Tests', () {
    test('Database initializes in-memory and enforces deduplication', () async {
      await WhoopDatabase.instance.init(customPath: inMemoryDatabasePath);

      // Register device
      await WhoopDatabase.instance.registerDevice(
        serialNumber: '5AG0558675',
        macAddress: 'FD:49:44:66:1D:92',
      );

      // Create dummy records with duplicate timestamps
      HistoricalRecordV18 rec1 = HistoricalRecordV18(
        sequence: 1,
        timestampUnix: 1793000000,
        primaryHr: 65,
        secondaryHr: 64,
        rrCount: 1,
        rrIntervalsMs: [920],
        accelX: 0.0,
        accelY: 0.0,
        accelZ: 1.0,
        accelMagG: 1.0,
        movementDeltaG: 0.0,
        steps: 100,
        skinTempC: 31.0,
        sleepState: 1,
        opticalBaseline: 35000,
        isOnWrist: true,
        rawHex: '2F12...',
      );

      // Same timestamp, lower rr_count
      HistoricalRecordV18 rec1Duplicate = HistoricalRecordV18(
        sequence: 1,
        timestampUnix: 1793000000,
        primaryHr: 65,
        secondaryHr: 64,
        rrCount: 1,
        rrIntervalsMs: [920],
        accelX: 0.0,
        accelY: 0.0,
        accelZ: 1.0,
        accelMagG: 1.0,
        movementDeltaG: 0.0,
        steps: 100,
        skinTempC: 31.0,
        sleepState: 1,
        opticalBaseline: 35000,
        isOnWrist: true,
        rawHex: '2F12...',
      );

      // Next second record
      HistoricalRecordV18 rec2 = HistoricalRecordV18(
        sequence: 2,
        timestampUnix: 1793000001,
        primaryHr: 66,
        secondaryHr: 65,
        rrCount: 1,
        rrIntervalsMs: [910],
        accelX: 0.0,
        accelY: 0.0,
        accelZ: 1.0,
        accelMagG: 1.0,
        movementDeltaG: 0.0,
        steps: 102,
        skinTempC: 31.0,
        sleepState: 1,
        opticalBaseline: 35000,
        isOnWrist: true,
        rawHex: '2F12...',
      );

      await WhoopDatabase.instance.ingestRecordsBatch(
        '5AG0558675',
        [rec1, rec1Duplicate, rec2],
      );

      int totalStored = await WhoopDatabase.instance.getRecordCount();
      expect(totalStored, equals(2)); // Exact deduplication (rec1Duplicate was ignored/updated without creating row 3)

      var records = await WhoopDatabase.instance.getRecords();
      expect(records.length, equals(2));

      var validRrs = await WhoopDatabase.instance.getValidRrIntervals();
      expect(validRrs.length, equals(2));
      expect(validRrs, contains(920));
      expect(validRrs, contains(910));

      await WhoopDatabase.instance.close();
    });
  });
}
