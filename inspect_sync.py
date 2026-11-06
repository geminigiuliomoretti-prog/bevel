import glob, os, csv

# 1. Vediamo cosa hanno scritto sync_manager.py e puffin_decoder.py per capire il filtro
with open("whoop_ble/sync_manager.py", "r", encoding="utf-8") as f:
    code = f.read()

print("=== RIGHE DI FILTRO IN SYNC_MANAGER.PY ===")
for i, line in enumerate(code.splitlines(), 1):
    if any(k in line for k in ["insert", "on_wrist", "primary_hr", "0x2F", "timestamp_unix", "HISTORICAL"]):
        print(f"L{i}: {line}")

# 2. Controlliamo l'ultimo file di log/pacchetti per vedere il VERO timestamp a cui siamo arrivati
latest_logs = sorted(glob.glob("logs/packets_*.csv"))
if latest_logs:
    last_csv = latest_logs[-1]
    print(f"\n=== ULTIMO LOG PACCHETTI: {last_csv} ===")
    with open(last_csv, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        print(f"Totale righe nel CSV: {len(lines)}")
        for l in lines[-10:]:
            print("  ", l.strip()[:120])
