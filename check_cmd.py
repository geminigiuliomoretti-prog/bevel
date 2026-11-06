with open("whoop_ble/puffin_decoder.py", "r", encoding="utf-8") as f:
    dec_lines = f.readlines()
print("=== PUFFIN_DECODER.PY L235-L305 ===")
for j in range(234, min(305, len(dec_lines))):
    print(f"L{j+1}: {dec_lines[j]}", end="")

with open("whoop_ble/puffin_commands.py", "r", encoding="utf-8") as f:
    cmd_lines = f.readlines()
print("\n=== PUFFIN_COMMANDS.PY (0x16 & 0x17) ===")
for j, line in enumerate(cmd_lines, 1):
    if any(k in line for k in ["0x16", "0x17", "cursor", "historical", "HISTORICAL"]):
        for k in range(max(0, j-3), min(len(cmd_lines), j+15)):
            print(f"L{k+1}: {cmd_lines[k]}", end="")
        print("-" * 40)

with open("whoop_ble/puffin_engine.py", "r", encoding="utf-8") as f:
    eng_lines = f.readlines()
print("\n=== PUFFIN_ENGINE.PY (0x31 / auto_ack) ===")
for j, line in enumerate(eng_lines, 1):
    if any(k in line for k in ["0x31", "0x17", "cursor", "auto_ack"]):
        for k in range(max(0, j-3), min(len(eng_lines), j+20)):
            print(f"L{k+1}: {eng_lines[k]}", end="")
        print("-" * 40)
