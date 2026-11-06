import asyncio
import sqlite3
from datetime import datetime, timezone

# 1. Sistemiamo l'indentazione di sync_manager.py e controlliamo database.py
with open("whoop_ble/sync_manager.py", "r", encoding="utf-8") as f:
    code = f.read()

bad_block = """        if rec_type == "HISTORICAL_RECORD_V18":
            ts = record.get("timestamp_unix", 0)
            if ts > self.stats.latest_timestamp_unix:
                self.stats.latest_timestamp_unix = ts
            if record.get("primary_hr_bpm", 0) == 0 and ts < 1793900000:
                self.stats.off_wrist_count += 1"""

good_block = """        if rec_type == "HISTORICAL_RECORD_V18":
            if record.get("primary_hr_bpm", 0) == 0:
                self.stats.off_wrist_count += 1"""

if bad_block in code:
    code = code.replace(bad_block, good_block, 1)
    with open("whoop_ble/sync_manager.py", "w", encoding="utf-8") as f:
        f.write(code)

# Vediamo le righe finali di sync_manager.py (L175-L280) e insert_records_1hz_batch in database.py
with open("whoop_ble/sync_manager.py", "r", encoding="utf-8") as f:
    sm_lines = f.readlines()
print("=== SYNC_MANAGER L180-L265 ===")
for i in range(179, min(265, len(sm_lines))):
    print(f"L{i+1}: {sm_lines[i]}", end="")

with open("whoop_ble/database.py", "r", encoding="utf-8") as f:
    db_lines = f.readlines()
print("\n=== DATABASE.PY (insert_records_1hz_batch) ===")
for i, line in enumerate(db_lines, 1):
    if "def insert_records_1hz_batch" in line:
        for j in range(i-1, min(i+45, len(db_lines))):
            print(f"L{j+1}: {db_lines[j]}", end="")
        break
