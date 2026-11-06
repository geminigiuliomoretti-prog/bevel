with open("whoop_ble/sync_manager.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Vediamo le righe 90-120 per sicurezza e applichiamo la patch
print("=== PRIMA DELLA PATCH (L95-L110) ===")
for i in range(94, min(112, len(lines))):
    print(f"L{i+1}: {lines[i]}", end="")

code = "".join(lines)
old_block = """        if rec_type == "HISTORICAL_RECORD_V18":
            if record.get("primary_hr_bpm", 0) == 0:"""

new_block = """        if rec_type == "HISTORICAL_RECORD_V18":
            ts = record.get("timestamp_unix", 0)
            if ts > self.stats.latest_timestamp_unix:
                self.stats.latest_timestamp_unix = ts
            if record.get("primary_hr_bpm", 0) == 0 and ts < 1793900000:"""

if old_block in code:
    code = code.replace(old_block, new_block, 1)
    with open("whoop_ble/sync_manager.py", "w", encoding="utf-8") as f:
        f.write(code)
    print("\n[+] PATCH APPLICATA CON SUCCESSO A sync_manager.py!")
else:
    print("\n[!] Blocco diverso, stampo L90-L115 per verifica.")
