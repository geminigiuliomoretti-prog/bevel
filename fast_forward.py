import asyncio
import sqlite3
from datetime import datetime, timezone

ADDRESS = "FD:49:44:66:1D:92"
SERIAL = "5AG0558675"

async def run_fast_forward():
    with sqlite3.connect("data/whoop_local.db") as conn:
        conn.execute("DELETE FROM devices WHERE serial_number != ?", (SERIAL,))
        conn.commit()

    print("=== AVVIO FAST-FORWARD FINO A OGGI (06/11/2026) ===")
    prev_max_ts = 0

    for round_idx in range(1, 15):
        with sqlite3.connect("data/whoop_local.db") as conn:
            row = conn.execute("SELECT MAX(timestamp_unix), COUNT(*) FROM records_1hz").fetchone()
            max_ts = row[0] or 0
            total_rec = row[1] or 0
        
        dt_str = datetime.fromtimestamp(max_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC') if max_ts else "N/A"
        print(f"\n[CICLO {round_idx}] Ultimo dato salvato nel DB: {dt_str} (Totale record: {total_rec})")
        
        if max_ts >= 1793944000:
            print(">>> NOTTE DEL 6 NOVEMBRE RAGGIUNTA! <<<")
            break

        if round_idx > 1 and max_ts == prev_max_ts:
            print("\n[!] ATTENZIONE: Il timestamp nel DB non e' avanzato durante l'ultimo ciclo!")
            print("    Significa che sync_manager.py sta filtrando i record off-wrist del 3-5 novembre.")
            break
        prev_max_ts = max_ts
            
        proc = await asyncio.create_subprocess_exec(
            ".venv\\Scripts\\python.exe", "main.py",
            "--address", ADDRESS, "--sync-db", "120"
        )
        await proc.wait()

    print("\n=== CALCOLO BIOMETRICO DELLA NOTTE ===")
    proc_an = await asyncio.create_subprocess_exec(
        ".venv\\Scripts\\python.exe", "main.py", "--analyze"
    )
    await proc_an.wait()

asyncio.run(run_fast_forward())
