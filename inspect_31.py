import glob, json

# 1. Vediamo dai log JSONL esistenti la struttura esatta in HEX dei pacchetti 0x31 ricevuti!
jsonl_files = sorted(glob.glob("logs/session_*.jsonl"))
print("=== ISPEZIONE PACCHETTI 0x31 REALI DAI LOG ===")
found_31 = 0
for jf in reversed(jsonl_files):
    with open(jf, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "0x31" in line or "METADATA_CURSOR" in line or "RX_STREAM_METADATA_CURSOR" in line:
                print(f"[{jf}] {line.strip()[:220]}")
                found_31 += 1
                if found_31 >= 8:
                    break
    if found_31 >= 8:
        break

# 2. Vediamo anche le righe L305-L345 di puffin_decoder.py
with open("whoop_ble/puffin_decoder.py", "r", encoding="utf-8") as f:
    lines = f.readlines()
print("\n=== PUFFIN_DECODER L245-L255 & L320-L360 ===")
for i in range(244, min(256, len(lines))):
    print(f"L{i+1}: {lines[i]}", end="")
print("-" * 30)
for i in range(320, min(360, len(lines))):
    print(f"L{i+1}: {lines[i]}", end="")
