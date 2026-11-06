"""
WHOOP BLE Historical Synchronization & Checkpoint Manager.
Handles:
- Reading NAND flash Data Range (0x22)
- Fast batch historical data offload (0x16 SEND_HISTORICAL)
- Automatic ACK dispatch (0x17) on cursor metadata (0x31)
- Real-time deduplication and transactional ingestion into SQLite
- Real-time progress monitoring (records/s, unique saved, duplicates discarded)
- Checkpoint persistence in 'devices' table
"""

import asyncio
import datetime
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from whoop_ble.puffin_engine import PuffinEngine
from whoop_ble.puffin_commands import PuffinDeviceController
from whoop_ble.database import WhoopDatabase


class SyncProgressStats:
    def __init__(self):
        self.start_time: float = time.time()
        self.total_received: int = 0
        self.unique_saved_1hz: int = 0
        self.duplicates_discarded_1hz: int = 0
        self.rr_intervals_saved: int = 0
        self.ppg_waveforms_saved: int = 0
        self.cursor_acks_sent: int = 0
        self.off_wrist_count: int = 0
        self.subtypes_count: Dict[str, int] = {}
        self.latest_timestamp_unix: int = 0
        self.latest_sequence: int = 0
        self.speed_rec_per_sec: float = 0.0

    def record_subtype(self, fmt_hex: str):
        self.subtypes_count[fmt_hex] = self.subtypes_count.get(fmt_hex, 0) + 1

    def update_speed(self):
        elapsed = max(0.1, time.time() - self.start_time)
        self.speed_rec_per_sec = round(self.total_received / elapsed, 1)

    def to_dict(self) -> Dict[str, Any]:
        elapsed = round(time.time() - self.start_time, 1)
        dup_pct = (
            round((self.duplicates_discarded_1hz / float(self.total_received) * 100.0), 1)
            if self.total_received > 0
            else 0.0
        )
        return {
            "elapsed_seconds": elapsed,
            "total_received": self.total_received,
            "unique_saved_1hz": self.unique_saved_1hz,
            "duplicates_discarded_1hz": self.duplicates_discarded_1hz,
            "duplicate_rate_pct": dup_pct,
            "rr_intervals_saved": self.rr_intervals_saved,
            "ppg_waveforms_saved": self.ppg_waveforms_saved,
            "cursor_acks_sent": self.cursor_acks_sent,
            "off_wrist_count": self.off_wrist_count,
            "subtypes_count": self.subtypes_count,
            "speed_rec_per_sec": self.speed_rec_per_sec,
            "latest_timestamp_unix": self.latest_timestamp_unix,
            "latest_sequence": self.latest_sequence,
        }


class HistoricalSyncManager:
    def __init__(
        self,
        engine: PuffinEngine,
        controller: PuffinDeviceController,
        db: WhoopDatabase,
        serial_number: str = "WHOOP_GEN5",
        batch_size: int = 40,
    ):
        self.engine = engine
        self.controller = controller
        self.db = db
        self.serial_number = serial_number
        self.batch_size = batch_size

        self.stats = SyncProgressStats()
        self._v18_buffer: List[Dict[str, Any]] = []
        self._v26_buffer: List[Dict[str, Any]] = []
        self._is_syncing = False
        self._sync_task: Optional[asyncio.Task] = None

    def _on_historical_record(self, record: Dict[str, Any]):
        if not self._is_syncing:
            return

        self.stats.total_received += 1
        rec_type = record.get("type")
        fmt = record.get("format_hex", "unknown")
        self.stats.record_subtype(fmt)

        if rec_type == "HISTORICAL_RECORD_V18":
            if record.get("primary_hr_bpm", 0) == 0:
                self.stats.off_wrist_count += 1
            self._v18_buffer.append(record)
            ts = record.get("timestamp_unix", 0)
            seq = record.get("sequence", 0)
            if ts > self.stats.latest_timestamp_unix:
                self.stats.latest_timestamp_unix = ts
            self.stats.latest_sequence = seq

        elif rec_type == "HISTORICAL_RECORD_V26_PPG":
            self._v26_buffer.append(record)

        # Batch flush if buffer size reached
        if len(self._v18_buffer) >= self.batch_size:
            self._flush_v18_buffer()

        if len(self._v26_buffer) >= self.batch_size:
            self._flush_v26_buffer()

    def _flush_v18_buffer(self):
        if not self._v18_buffer:
            return
        batch = list(self._v18_buffer)
        self._v18_buffer.clear()

        ins, dups, rr_cnt = self.db.insert_records_1hz_batch(batch, self.serial_number)
        self.stats.unique_saved_1hz += ins
        self.stats.duplicates_discarded_1hz += dups
        self.stats.rr_intervals_saved += rr_cnt

    def _flush_v26_buffer(self):
        if not self._v26_buffer:
            return
        batch = list(self._v26_buffer)
        self._v26_buffer.clear()

        ins, dups = self.db.insert_ppg_waveforms_batch(
            batch, self.serial_number, sample_timestamp_unix=self.stats.latest_timestamp_unix
        )
        self.stats.ppg_waveforms_saved += ins

    def _on_cursor_metadata(self, meta: Dict[str, Any]):
        if not self._is_syncing:
            return

        cursor_hex = meta.get("cursor_hex")
        if cursor_hex:
            self.stats.cursor_acks_sent += 1
            if self.stats.latest_timestamp_unix > 0:
                self.db.update_sync_checkpoint(
                    serial_number=self.serial_number,
                    sync_timestamp_unix=self.stats.latest_timestamp_unix,
                    cursor_hex=cursor_hex,
                )

    async def run_sync(
        self,
        duration_seconds: int = 60,
        max_chunks: Optional[int] = None,
        progress_interval: float = 1.0,
        status_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a high-speed historical offload into SQLite:
        1. Reads NAND flash range (0x22)
        2. Configures auto-ACK cursor handling
        3. Sends 0x16 SEND_HISTORICAL
        4. Ingests and deduplicates 0x2F records in real-time
        5. Flushes on finish and updates database checkpoint
        """
        print("\n" + "=" * 75)
        print(f"[*] STARTING HISTORICAL SYNC & SQLITE INGESTION (Target: {self.serial_number})")
        print(f"    Sync Duration: {duration_seconds}s | Max Chunks: {max_chunks or 'Unlimited'}")
        print("=" * 75)

        # 0. Ensure all endpoints are subscribed
        await self.engine.subscribe_all()

        # 1. Check Data Range
        try:
            range_info = await self.controller.get_data_range(b3=0x00)
            avail = range_info.get("total_records_available", 0)
            print(f"[+] Flash Range: {avail} total records available ({range_info.get('start_utc')} -> {range_info.get('end_utc')})")
        except Exception as e:
            print(f"[!] Warning reading data range: {e}")
            range_info = {}

        # 2. Check Device Checkpoint in DB
        device_row = self.db.get_device(self.serial_number)
        last_sync_ts = device_row.get("last_sync_timestamp_unix", 0) if device_row else 0
        if last_sync_ts > 0:
            last_sync_dt = datetime.datetime.fromtimestamp(last_sync_ts, tz=datetime.timezone.utc).isoformat()
            print(f"[+] Existing Local Sync Checkpoint: {last_sync_dt} (Unix {last_sync_ts})")
        else:
            print("[*] No prior local sync checkpoint found. Starting full offload.")

        # 3. Setup Listeners
        self.stats = SyncProgressStats()
        self._v18_buffer.clear()
        self._v26_buffer.clear()
        self._is_syncing = True

        prev_hist_cb = self.engine.on_historical_record
        prev_cursor_cb = self.engine.on_cursor_metadata

        self.engine.on_historical_record = self._on_historical_record
        self.engine.on_cursor_metadata = self._on_cursor_metadata

        # 4. Trigger 0x16 SEND_HISTORICAL
        print(f"[*] Triggering 0x16 SEND_HISTORICAL (listening on fd4b0005)...")
        try:
            resp_16 = await self.controller.trigger_historical_offload(b3=0x00)
            print(f"[+] 0x16 Command Accepted! Response: {resp_16.get('is_success')}")
        except Exception as e:
            print(f"[!] Warning triggering 0x16: {e}")

        # 5. Polling Loop with Live Progress Display
        start_t = time.time()
        last_progress_t = start_t

        try:
            while True:
                now = time.time()
                elapsed = now - start_t
                if elapsed >= duration_seconds:
                    break

                if max_chunks and self.stats.total_received >= max_chunks:
                    print(f"\n[+] Reached target chunk count ({self.stats.total_received}). Stopping sync.")
                    break

                if (now - last_progress_t) >= progress_interval:
                    self.stats.update_speed()
                    st = self.stats.to_dict()
                    rem_sec = max(0, int(duration_seconds - elapsed))
                    print(
                        f"  [SYNC] Rcvd: {st['total_received']:<5} | "
                        f"Unique: {st['unique_saved_1hz']:<5} | "
                        f"Duplicates Filtered: {st['duplicates_discarded_1hz']:<5} ({st['duplicate_rate_pct']}%) | "
                        f"RR: {st['rr_intervals_saved']:<4} | "
                        f"Speed: {st['speed_rec_per_sec']} rec/s | "
                        f"Remaining: {rem_sec}s",
                        end="\r",
                    )
                    if status_callback:
                        status_callback(st)
                    last_progress_t = now

                await asyncio.sleep(0.2)

        finally:
            self._is_syncing = False
            self.engine.on_historical_record = prev_hist_cb
            self.engine.on_cursor_metadata = prev_cursor_cb

            # Final Flush
            self._flush_v18_buffer()
            self._flush_v26_buffer()
            self.stats.update_speed()

            # Final Checkpoint Save
            if self.stats.latest_timestamp_unix > 0:
                self.db.update_sync_checkpoint(
                    serial_number=self.serial_number,
                    sync_timestamp_unix=self.stats.latest_timestamp_unix,
                )

        print("\n" + "-" * 75)
        final_summary = self.stats.to_dict()
        print(f"[+] SYNC COMPLETED SUCCESSFULLY!")
        print(f"    Total Packets Received    : {final_summary['total_received']}")
        print(f"    Unique Records Saved (1Hz): {final_summary['unique_saved_1hz']}")
        print(f"    Duplicates Filtered       : {final_summary['duplicates_discarded_1hz']} ({final_summary['duplicate_rate_pct']}%)")
        print(f"    Valid RR Intervals Saved  : {final_summary['rr_intervals_saved']}")
        print(f"    PPG Waveforms Saved (24Hz): {final_summary['ppg_waveforms_saved']}")
        print(f"    Subtypes Received (0x2F)  : {final_summary['subtypes_count']}")
        print(f"    Off-Wrist Packets (HR=0)  : {final_summary['off_wrist_count']}")
        print(f"    Average Offload Speed     : {final_summary['speed_rec_per_sec']} records/sec")
        print(f"    Cursor ACKs Dispatched    : {final_summary['cursor_acks_sent']}")
        print("-" * 75)

        return {
            "serial_number": self.serial_number,
            "range_info": range_info,
            "sync_stats": final_summary,
            "db_stats": self.db.get_db_stats(self.serial_number),
        }
