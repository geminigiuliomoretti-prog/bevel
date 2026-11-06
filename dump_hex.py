import json, glob

jsonl_files = sorted(glob.glob("logs/session_*.jsonl"))
print("=== DETTAGLIO COMPLETO 0x31 E 0x2F NELL'ULTIMA SESSIONE ===")
for jf in reversed(jsonl_files[-3:]):
    print(f"\n--- File: {jf} ---")
    c31, c2f = 0, 0
    with open(jf, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "METADATA_CURSOR" in line and c31 < 3:
                d = json.loads(line).get("details", {})
                print("0x31:", d.get("raw_hex"), "| Decoded:", d.get("decoded_summary"))
                c31 += 1
            elif "RX_STREAM_HISTORICAL" in line and c2f < 3:
                d = json.loads(line).get("details", {})
                print("0x2F:", d.get("raw_hex")[:60], "| Decoded:", str(d.get("decoded_summary"))[:140])
                c2f += 1
