with open("whoop_ble/database.py", "r", encoding="utf-8") as f:
    db_lines = f.readlines()
print("=== DATABASE.PY L294-L360 ===")
for j in range(293, min(365, len(db_lines))):
    print(f"L{j+1}: {db_lines[j]}", end="")

with open("whoop_ble/puffin_decoder.py", "r", encoding="utf-8") as f:
    dec_lines = f.readlines()
print("\n=== PUFFIN_DECODER.PY (0x2F & 0x31) ===")
for j, line in enumerate(dec_lines, 1):
    if any(k in line for k in ["0x2F", "0x31", "0x12", "HISTORICAL", "cursor", "def decode"]):
        for k in range(max(0, j-2), min(len(dec_lines), j+18)):
            print(f"L{k+1}: {dec_lines[k]}", end="")
        print("-" * 40)
