"""
Unit tests for WhoopDatabase SQLite persistence, deduplication and physiological gate.
"""

import os
import unittest
from whoop_ble.database import WhoopDatabase


class TestWhoopDatabase(unittest.TestCase):
    def setUp(self):
        self.test_db = f"data/test_db_{self._testMethodName}.db"
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception:
                pass
        self.db = WhoopDatabase(self.test_db)

    def tearDown(self):
        if hasattr(self, "db"):
            del self.db
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception:
                pass

    def test_upsert_device(self):
        self.db.upsert_device(
            serial_number="TEST_SN_123",
            mac_address="FD:49:44:66:1D:92",
            model="WHOOP 5WP",
            fw_revision="50.41.1.0",
        )
        dev = self.db.get_device("TEST_SN_123")
        self.assertIsNotNone(dev)
        self.assertEqual(dev["mac_address"], "FD:49:44:66:1D:92")
        self.assertEqual(dev["model"], "WHOOP 5WP")

    def test_deduplication_records_1hz(self):
        records = [
            {
                "timestamp_unix": 1700000000,
                "sequence": 100,
                "primary_hr_bpm": 65,
                "rr_intervals_ms": [920],
                "skin_temp_c": 33.2,
                "is_on_wrist": True,
            },
            # Exact duplicate re-delivery from strap
            {
                "timestamp_unix": 1700000000,
                "sequence": 100,
                "primary_hr_bpm": 65,
                "rr_intervals_ms": [920],
                "skin_temp_c": 33.2,
                "is_on_wrist": True,
            },
            # Next second
            {
                "timestamp_unix": 1700000001,
                "sequence": 101,
                "primary_hr_bpm": 64,
                "rr_intervals_ms": [935],
                "skin_temp_c": 33.2,
                "is_on_wrist": True,
            },
        ]
        ins, dups, rr_cnt = self.db.insert_records_1hz_batch(records, "TEST_SN_123")
        self.assertEqual(ins, 2)
        self.assertEqual(dups, 1)

        db_recs = self.db.get_records_range("TEST_SN_123")
        self.assertEqual(len(db_recs), 2)
        self.assertEqual(db_recs[0]["timestamp_unix"], 1700000000)
        self.assertEqual(db_recs[1]["timestamp_unix"], 1700000001)

    def test_physiological_gate(self):
        records = [
            {
                "timestamp_unix": 1700000010,
                "primary_hr_bpm": 60,
                "rr_intervals_ms": [1000],
            },
            # Normal beat (~1020ms -> delta 2%)
            {
                "timestamp_unix": 1700000011,
                "primary_hr_bpm": 60,
                "rr_intervals_ms": [1020],
            },
            # Ectopic / optical sensor artifact (325ms -> delta > 25%)
            {
                "timestamp_unix": 1700000012,
                "primary_hr_bpm": 60,
                "rr_intervals_ms": [325],
            },
            # Out of bounds (>2000ms)
            {
                "timestamp_unix": 1700000013,
                "primary_hr_bpm": 60,
                "rr_intervals_ms": [2340],
            },
        ]
        self.db.insert_records_1hz_batch(records, "TEST_SN_123")
        rrs = self.db.get_rr_intervals("TEST_SN_123", valid_only=False)
        self.assertEqual(len(rrs), 4)
        self.assertEqual(rrs[0]["is_physiologically_valid"], 1)
        self.assertEqual(rrs[1]["is_physiologically_valid"], 1)
        self.assertEqual(rrs[2]["is_physiologically_valid"], 0)
        self.assertEqual(rrs[3]["is_physiologically_valid"], 0)

        valid_rrs = self.db.get_rr_intervals("TEST_SN_123", valid_only=True)
        self.assertEqual(len(valid_rrs), 2)


if __name__ == "__main__":
    unittest.main()
