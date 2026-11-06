"""
WHOOP BLE SQLite Persistence & Deduplication Engine.
Stores raw 1Hz v18/0x28 biometrics, v26 24Hz PPG waveforms, beat-by-beat RR intervals,
daily cycles (Recovery, Strain, Sleep), and workouts in WAL mode.
Provides strict deduplication to eliminate re-deliveries from hardware.
"""

import contextlib
import datetime
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


class WhoopDatabase:
    def __init__(self, db_path: str = "data/whoop_local.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL (Write-Ahead Logging) mode and high performance PRAGMAs
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            # 1. Devices
            conn.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                serial_number TEXT PRIMARY KEY,
                mac_address TEXT,
                model TEXT,
                hw_revision TEXT,
                fw_revision TEXT,
                last_sync_timestamp_unix INTEGER DEFAULT 0,
                last_cursor_hex TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            """)

            # 2. records_1hz (v18 historical and 0x28 live 1Hz telemetry)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS records_1hz (
                serial_number TEXT NOT NULL,
                timestamp_unix INTEGER NOT NULL,
                sequence INTEGER,
                primary_hr INTEGER,
                secondary_hr INTEGER,
                rr_count INTEGER DEFAULT 0,
                rr_ms_json TEXT,
                accel_x REAL,
                accel_y REAL,
                accel_z REAL,
                accel_mag_g REAL,
                movement_delta_g REAL DEFAULT 0.0,
                steps INTEGER DEFAULT 0,
                skin_temp_c REAL,
                sleep_state INTEGER DEFAULT 0,
                optical_baseline INTEGER DEFAULT 0,
                is_on_wrist INTEGER DEFAULT 0,
                raw_hex TEXT,
                created_at TEXT,
                UNIQUE(serial_number, timestamp_unix)
            );
            """)

            # Index for fast time-series queries
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_records_1hz_ts 
            ON records_1hz(serial_number, timestamp_unix);
            """)

            # 3. rr_intervals (beat-by-beat deduplicated with physiological gate)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS rr_intervals (
                serial_number TEXT NOT NULL,
                timestamp_unix INTEGER NOT NULL,
                beat_ordinal INTEGER NOT NULL,
                rr_ms INTEGER NOT NULL,
                is_physiologically_valid INTEGER NOT NULL DEFAULT 1,
                created_at TEXT,
                UNIQUE(serial_number, timestamp_unix, beat_ordinal)
            );
            """)

            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rr_intervals_ts 
            ON rr_intervals(serial_number, timestamp_unix, is_physiologically_valid);
            """)

            # 4. ppg_waveforms (v26 24Hz raw PPG signals)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS ppg_waveforms (
                serial_number TEXT NOT NULL,
                timestamp_unix INTEGER NOT NULL,
                samples_24hz_json TEXT NOT NULL,
                sample_count INTEGER DEFAULT 24,
                raw_hex TEXT,
                created_at TEXT,
                UNIQUE(serial_number, timestamp_unix)
            );
            """)

            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ppg_waveforms_ts 
            ON ppg_waveforms(serial_number, timestamp_unix);
            """)

            # 5. daily_cycles (Recovery, Strain, Sleep summary)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                serial_number TEXT NOT NULL,
                date TEXT NOT NULL,
                recovery_score REAL,
                recovery_state TEXT,
                hrv_rmssd_ms REAL,
                resting_hr_bpm REAL,
                day_strain REAL,
                sleep_performance_pct REAL,
                sleep_duration_seconds INTEGER,
                respiratory_rate_rpm REAL,
                skin_temp_c REAL,
                avg_stress REAL,
                metrics_json TEXT,
                created_at TEXT,
                UNIQUE(serial_number, date)
            );
            """)

            # 6. workouts
            conn.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                serial_number TEXT,
                start_timestamp_unix INTEGER,
                end_timestamp_unix INTEGER,
                duration_seconds INTEGER,
                workout_strain REAL,
                avg_hr_bpm REAL,
                max_hr_bpm INTEGER,
                calories_kcal REAL DEFAULT 0,
                kilojoules REAL DEFAULT 0,
                zone_durations_json TEXT,
                sport_name TEXT,
                auto_detected INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(serial_number, start_timestamp_unix)
            );
            """)

            # 7. calibrations (WHOOP A vs WHOOP B ground truth comparison)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS calibrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_unix INTEGER NOT NULL,
                date TEXT NOT NULL,
                whoop_a_hrv REAL,
                whoop_b_hrv REAL,
                delta_hrv_pct REAL,
                whoop_a_rhr REAL,
                whoop_b_rhr REAL,
                delta_rhr_pct REAL,
                whoop_a_strain REAL,
                whoop_b_strain REAL,
                delta_strain_pct REAL,
                whoop_a_recovery INTEGER,
                whoop_b_recovery INTEGER,
                delta_recovery_pct REAL,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.commit()

    # -------------------------------------------------------------------------
    # Devices
    # -------------------------------------------------------------------------

    def upsert_device(
        self,
        serial_number: str,
        mac_address: Optional[str] = None,
        model: Optional[str] = None,
        hw_revision: Optional[str] = None,
        fw_revision: Optional[str] = None,
        last_sync_timestamp_unix: Optional[int] = None,
        last_cursor_hex: Optional[str] = None,
    ):
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO devices (
                serial_number, mac_address, model, hw_revision, fw_revision,
                last_sync_timestamp_unix, last_cursor_hex, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, COALESCE(?, 0), ?, ?, ?)
            ON CONFLICT(serial_number) DO UPDATE SET
                mac_address = COALESCE(excluded.mac_address, devices.mac_address),
                model = COALESCE(excluded.model, devices.model),
                hw_revision = COALESCE(excluded.hw_revision, devices.hw_revision),
                fw_revision = COALESCE(excluded.fw_revision, devices.fw_revision),
                last_sync_timestamp_unix = CASE 
                    WHEN excluded.last_sync_timestamp_unix > devices.last_sync_timestamp_unix 
                    THEN excluded.last_sync_timestamp_unix 
                    ELSE devices.last_sync_timestamp_unix 
                END,
                last_cursor_hex = COALESCE(excluded.last_cursor_hex, devices.last_cursor_hex),
                updated_at = excluded.updated_at;
            """, (
                serial_number, mac_address, model, hw_revision, fw_revision,
                last_sync_timestamp_unix, last_cursor_hex, now_iso, now_iso
            ))
            conn.commit()

    def get_device(self, serial_number: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM devices WHERE serial_number = ?", (serial_number,))
            row = cur.fetchone()
            return dict(row) if row else None

    def update_sync_checkpoint(self, serial_number: str, sync_timestamp_unix: int, cursor_hex: Optional[str] = None):
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
            UPDATE devices SET
                last_sync_timestamp_unix = MAX(last_sync_timestamp_unix, ?),
                last_cursor_hex = COALESCE(?, last_cursor_hex),
                updated_at = ?
            WHERE serial_number = ?;
            """, (sync_timestamp_unix, cursor_hex, now_iso, serial_number))
            conn.commit()

    # -------------------------------------------------------------------------
    # Records 1Hz & RR Intervals Batch Ingestion with Deduplication
    # -------------------------------------------------------------------------

    def insert_records_1hz_batch(
        self,
        records: List[Dict[str, Any]],
        serial_number: str,
    ) -> Tuple[int, int, int]:
        """
        Inserts a batch of 1Hz records (v18 or 0x28 live) and extracts RR intervals.
        Applies UNIQUE(serial_number, timestamp_unix) deduplication.
        
        Returns:
            Tuple[int, int, int]: (inserted_1hz, duplicates_1hz, inserted_rr)
        """
        if not records:
            return (0, 0, 0)

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        inserted_1hz = 0
        duplicates_1hz = 0
        rr_to_insert: List[Tuple[str, int, int, int, int, str]] = []

        # Maintain previous accel vector and previous valid RR for delta / physiological gate
        prev_accel: Optional[Tuple[float, float, float]] = None
        last_valid_rr: Optional[int] = None

        with self._get_connection() as conn:
            # Check last record in DB to seed prev_accel and last_valid_rr
            cur = conn.execute("""
                SELECT accel_x, accel_y, accel_z, primary_hr 
                FROM records_1hz 
                WHERE serial_number = ? 
                ORDER BY timestamp_unix DESC LIMIT 1
            """, (serial_number,))
            last_row = cur.fetchone()
            if last_row and last_row["accel_x"] is not None:
                prev_accel = (last_row["accel_x"], last_row["accel_y"], last_row["accel_z"])

            cur_rr = conn.execute("""
                SELECT rr_ms FROM rr_intervals 
                WHERE serial_number = ? AND is_physiologically_valid = 1 
                ORDER BY timestamp_unix DESC, beat_ordinal DESC LIMIT 1
            """, (serial_number,))
            last_rr_row = cur_rr.fetchone()
            if last_rr_row:
                last_valid_rr = last_rr_row["rr_ms"]

            for rec in records:
                ts = rec.get("timestamp_unix")
                if not ts or ts <= 0:
                    continue

                seq = rec.get("sequence")
                p_hr = rec.get("primary_hr_bpm") or rec.get("heart_rate_bpm") or 0
                s_hr = rec.get("secondary_hr_bpm") or p_hr
                rr_list = rec.get("rr_intervals_ms") or []
                if not rr_list and rec.get("rr_ms"):
                    rr_list = [rec["rr_ms"]]

                rr_count = len(rr_list)
                rr_json = json.dumps(rr_list)

                # Accel & Gravity
                gx = rec.get("accel_x")
                gy = rec.get("accel_y")
                gz = rec.get("accel_z")
                if gx is None and "gravity_g" in rec and rec["gravity_g"]:
                    gx = rec["gravity_g"].get("x")
                    gy = rec["gravity_g"].get("y")
                    gz = rec["gravity_g"].get("z")

                accel_mag = None
                movement_delta = 0.0
                if gx is not None and gy is not None and gz is not None:
                    accel_mag = round((gx ** 2 + gy ** 2 + gz ** 2) ** 0.5, 3)
                    if prev_accel is not None:
                        movement_delta = round(
                            ((gx - prev_accel[0]) ** 2 + (gy - prev_accel[1]) ** 2 + (gz - prev_accel[2]) ** 2) ** 0.5,
                            4
                        )
                    prev_accel = (gx, gy, gz)

                steps = rec.get("steps") or 0
                temp_c = rec.get("skin_temp_c")
                sleep_state = rec.get("sleep_state") or 0
                opt_base = rec.get("optical_baseline") or rec.get("optical_baseline_106") or 0
                on_wrist = 1 if rec.get("is_on_wrist") else 0
                raw_hex = rec.get("raw_hex", "")

                # Deduplication Insert:
                # If timestamp already exists for device:
                # - If new packet has greater rr_count, update it
                # - Otherwise IGNORE
                cursor = conn.execute("""
                INSERT INTO records_1hz (
                    serial_number, timestamp_unix, sequence, primary_hr, secondary_hr,
                    rr_count, rr_ms_json, accel_x, accel_y, accel_z, accel_mag_g,
                    movement_delta_g, steps, skin_temp_c, sleep_state, optical_baseline,
                    is_on_wrist, raw_hex, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(serial_number, timestamp_unix) DO UPDATE SET
                    sequence = COALESCE(excluded.sequence, records_1hz.sequence),
                    primary_hr = CASE WHEN excluded.primary_hr > 0 THEN excluded.primary_hr ELSE records_1hz.primary_hr END,
                    rr_count = excluded.rr_count,
                    rr_ms_json = excluded.rr_ms_json,
                    accel_x = COALESCE(excluded.accel_x, records_1hz.accel_x),
                    accel_y = COALESCE(excluded.accel_y, records_1hz.accel_y),
                    accel_z = COALESCE(excluded.accel_z, records_1hz.accel_z),
                    accel_mag_g = COALESCE(excluded.accel_mag_g, records_1hz.accel_mag_g),
                    movement_delta_g = excluded.movement_delta_g,
                    steps = CASE WHEN excluded.steps > records_1hz.steps THEN excluded.steps ELSE records_1hz.steps END,
                    skin_temp_c = COALESCE(excluded.skin_temp_c, records_1hz.skin_temp_c),
                    sleep_state = COALESCE(excluded.sleep_state, records_1hz.sleep_state),
                    optical_baseline = CASE WHEN excluded.optical_baseline > records_1hz.optical_baseline THEN excluded.optical_baseline ELSE records_1hz.optical_baseline END,
                    is_on_wrist = MAX(excluded.is_on_wrist, records_1hz.is_on_wrist)
                WHERE excluded.rr_count > records_1hz.rr_count;
                """, (
                    serial_number, ts, seq, p_hr, s_hr, rr_count, rr_json,
                    gx, gy, gz, accel_mag, movement_delta, steps, temp_c,
                    sleep_state, opt_base, on_wrist, raw_hex, now_iso
                ))

                if cursor.rowcount > 0:
                    inserted_1hz += 1
                else:
                    duplicates_1hz += 1

                # Extract beat-by-beat RR intervals with Physiological Gate
                for idx, rr_val in enumerate(rr_list[:4]):
                    # Physiological Gate:
                    # 1. 250 <= rr_ms <= 2000 ms (corresponds to 30..240 BPM)
                    # 2. Delta from previous valid beat < 25% (ectopic beat / optical artifact filter)
                    is_valid = 1
                    if not (250 <= rr_val <= 2000):
                        is_valid = 0
                    elif last_valid_rr is not None:
                        ratio = abs(rr_val - last_valid_rr) / float(last_valid_rr)
                        if ratio >= 0.25:
                            is_valid = 0

                    if is_valid == 1:
                        last_valid_rr = rr_val

                    rr_to_insert.append((serial_number, ts, idx, rr_val, is_valid, now_iso))

            # Batch insert RR intervals
            inserted_rr = 0
            if rr_to_insert:
                cur_rr = conn.executemany("""
                INSERT OR IGNORE INTO rr_intervals (
                    serial_number, timestamp_unix, beat_ordinal, rr_ms, is_physiologically_valid, created_at
                ) VALUES (?, ?, ?, ?, ?, ?);
                """, rr_to_insert)
                inserted_rr = cur_rr.rowcount if cur_rr.rowcount >= 0 else len(rr_to_insert)

            conn.commit()

        return (inserted_1hz, duplicates_1hz, inserted_rr)

    def insert_ppg_waveforms_batch(
        self,
        ppg_records: List[Dict[str, Any]],
        serial_number: str,
        sample_timestamp_unix: Optional[int] = None,
    ) -> Tuple[int, int]:
        """
        Inserts v26 PPG waveforms (24 samples at 24Hz).
        """
        if not ppg_records:
            return (0, 0)

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        inserted = 0
        duplicates = 0

        with self._get_connection() as conn:
            for rec in ppg_records:
                samples = rec.get("ppg_samples_24hz", [])
                if not samples:
                    continue
                ts = rec.get("timestamp_unix") or sample_timestamp_unix
                if not ts:
                    continue

                samples_json = json.dumps(samples)
                raw_hex = rec.get("raw_hex", "")

                cur = conn.execute("""
                INSERT OR IGNORE INTO ppg_waveforms (
                    serial_number, timestamp_unix, samples_24hz_json, sample_count, raw_hex, created_at
                ) VALUES (?, ?, ?, ?, ?, ?);
                """, (serial_number, ts, samples_json, len(samples), raw_hex, now_iso))

                if cur.rowcount > 0:
                    inserted += 1
                else:
                    duplicates += 1

            conn.commit()

        return (inserted, duplicates)

    # -------------------------------------------------------------------------
    # Queries & Biometrics Data Retrieval
    # -------------------------------------------------------------------------

    def get_records_range(
        self,
        serial_number: str,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        on_wrist_only: bool = False,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM records_1hz WHERE serial_number = ?"
        params: List[Any] = [serial_number]

        if start_ts is not None:
            query += " AND timestamp_unix >= ?"
            params.append(start_ts)
        if end_ts is not None:
            query += " AND timestamp_unix <= ?"
            params.append(end_ts)
        if on_wrist_only:
            query += " AND is_on_wrist = 1"

        query += " ORDER BY timestamp_unix ASC"

        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            return [dict(r) for r in cur.fetchall()]

    def get_rr_intervals(
        self,
        serial_number: str,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        valid_only: bool = True,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM rr_intervals WHERE serial_number = ?"
        params: List[Any] = [serial_number]

        if start_ts is not None:
            query += " AND timestamp_unix >= ?"
            params.append(start_ts)
        if end_ts is not None:
            query += " AND timestamp_unix <= ?"
            params.append(end_ts)
        if valid_only:
            query += " AND is_physiologically_valid = 1"

        query += " ORDER BY timestamp_unix ASC, beat_ordinal ASC"

        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            return [dict(r) for r in cur.fetchall()]

    def get_db_stats(self, serial_number: Optional[str] = None) -> Dict[str, Any]:
        with self._get_connection() as conn:
            where_clause = "WHERE serial_number = ?" if serial_number else ""
            params = (serial_number,) if serial_number else ()

            # 1Hz count
            r1 = conn.execute(f"SELECT COUNT(*), MIN(timestamp_unix), MAX(timestamp_unix) FROM records_1hz {where_clause}", params).fetchone()
            total_1hz = r1[0] or 0
            min_ts = r1[1] or 0
            max_ts = r1[2] or 0

            # Valid on-wrist
            r_wrist = conn.execute(f"SELECT COUNT(*) FROM records_1hz {where_clause} {'AND' if where_clause else 'WHERE'} is_on_wrist = 1", params).fetchone()
            on_wrist_count = r_wrist[0] or 0

            # RR stats
            r_rr = conn.execute(f"SELECT COUNT(*), SUM(is_physiologically_valid) FROM rr_intervals {where_clause}", params).fetchone()
            total_rr = r_rr[0] or 0
            valid_rr = r_rr[1] or 0

            # PPG count
            r_ppg = conn.execute(f"SELECT COUNT(*) FROM ppg_waveforms {where_clause}", params).fetchone()
            total_ppg = r_ppg[0] or 0

            # Devices
            devices_cur = conn.execute("SELECT * FROM devices").fetchall()
            devices_list = [dict(d) for d in devices_cur]

            span_sec = max(0, max_ts - min_ts) if max_ts > min_ts else 0

            min_utc = datetime.datetime.fromtimestamp(min_ts, tz=datetime.timezone.utc).isoformat() if min_ts > 0 else None
            max_utc = datetime.datetime.fromtimestamp(max_ts, tz=datetime.timezone.utc).isoformat() if max_ts > 0 else None

            return {
                "db_path": os.path.abspath(self.db_path),
                "total_1hz_records": total_1hz,
                "on_wrist_records": on_wrist_count,
                "off_wrist_records": total_1hz - on_wrist_count,
                "total_rr_intervals": total_rr,
                "valid_rr_intervals": valid_rr or 0,
                "invalid_rr_intervals": total_rr - (valid_rr or 0),
                "rr_physiological_acceptance_rate_pct": round((valid_rr / total_rr * 100.0), 2) if total_rr > 0 else 0.0,
                "total_ppg_waveforms": total_ppg,
                "earliest_timestamp_unix": min_ts,
                "earliest_timestamp_utc": min_utc,
                "latest_timestamp_unix": max_ts,
                "latest_timestamp_utc": max_utc,
                "timespan_seconds": span_sec,
                "timespan_hours": round(span_sec / 3600.0, 2),
                "registered_devices": devices_list,
            }

    # -------------------------------------------------------------------------
    # Daily Cycles & Workouts Storage
    # -------------------------------------------------------------------------

    def save_daily_cycle(self, cycle_data: Dict[str, Any]):
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        metrics_json = json.dumps(cycle_data.get("metrics", {}))
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO daily_cycles (
                serial_number, date, recovery_score, recovery_state, hrv_rmssd_ms,
                resting_hr_bpm, day_strain, sleep_performance_pct, sleep_duration_seconds,
                respiratory_rate_rpm, skin_temp_c, avg_stress, metrics_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(serial_number, date) DO UPDATE SET
                recovery_score = excluded.recovery_score,
                recovery_state = excluded.recovery_state,
                hrv_rmssd_ms = excluded.hrv_rmssd_ms,
                resting_hr_bpm = excluded.resting_hr_bpm,
                day_strain = excluded.day_strain,
                sleep_performance_pct = excluded.sleep_performance_pct,
                sleep_duration_seconds = excluded.sleep_duration_seconds,
                respiratory_rate_rpm = excluded.respiratory_rate_rpm,
                skin_temp_c = excluded.skin_temp_c,
                avg_stress = excluded.avg_stress,
                metrics_json = excluded.metrics_json,
                created_at = excluded.created_at;
            """, (
                cycle_data["serial_number"],
                cycle_data["date"],
                cycle_data.get("recovery_score"),
                cycle_data.get("recovery_state"),
                cycle_data.get("hrv_rmssd_ms"),
                cycle_data.get("resting_hr_bpm"),
                cycle_data.get("day_strain"),
                cycle_data.get("sleep_performance_pct"),
                cycle_data.get("sleep_duration_seconds"),
                cycle_data.get("respiratory_rate_rpm"),
                cycle_data.get("skin_temp_c"),
                cycle_data.get("avg_stress"),
                metrics_json,
                now_iso
            ))
            conn.commit()

    def save_workout(self, workout_data: Dict[str, Any]):
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        zones_json = json.dumps(workout_data.get("zone_durations", {}))
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO workouts (
                serial_number, start_timestamp_unix, end_timestamp_unix, duration_seconds,
                workout_strain, avg_hr_bpm, max_hr_bpm, calories_kcal, kilojoules,
                zone_durations_json, auto_detected, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(serial_number, start_timestamp_unix) DO UPDATE SET
                end_timestamp_unix = excluded.end_timestamp_unix,
                duration_seconds = excluded.duration_seconds,
                workout_strain = excluded.workout_strain,
                avg_hr_bpm = excluded.avg_hr_bpm,
                max_hr_bpm = excluded.max_hr_bpm,
                calories_kcal = excluded.calories_kcal,
                kilojoules = excluded.kilojoules,
                zone_durations_json = excluded.zone_durations_json,
                auto_detected = excluded.auto_detected,
                created_at = excluded.created_at;
            """, (
                workout_data["serial_number"],
                workout_data["start_timestamp_unix"],
                workout_data["end_timestamp_unix"],
                workout_data["duration_seconds"],
                workout_data["workout_strain"],
                workout_data["avg_hr_bpm"],
                workout_data["max_hr_bpm"],
                workout_data["calories_kcal"],
                workout_data["kilojoules"],
                zones_json,
                workout_data.get("auto_detected", 1),
                now_iso
            ))
            conn.commit()
