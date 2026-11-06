with open("whoop_ble/puffin_decoder.py", "r", encoding="utf-8") as f:
    code = f.read()

# Vecchia funzione errata basata su inner[5:13]
old_func = """def decode_cursor_metadata_0x31(inner: bytes) -> Dict[str, Any]:
    \"\"\"
    Decodes Cursor / Metadata 0x31 packet on fd4b0005:
    FW 50.41.1.0 Frame vs Inner Payload Architecture:
    - Frame on wire: Header (8 bytes) + Inner (>=13 bytes) + Trailer CRC32 (4 bytes)
    - Frame Offset for 8-byte cursor: bytes 13..21
    - Inner Payload Offset: inner_offset = frame_offset - 8 = bytes 5..13
    Extracts the 8-byte cursor at inner[5:13] (or frame[13:21]) to return with 0x17.
    \"\"\"
    if len(inner) >= 21 and inner[0] == 0xAA and inner[1] == 0x01:
        inner = inner[8 : len(inner) - 4]

    cursor_hex: Optional[str] = None
    if len(inner) >= 13:
        cursor_bytes = inner[5:13]
        cursor_hex = cursor_bytes.hex().upper()

    return {
        "type": "METADATA_CURSOR",
        "opcode": "0x31",
        "cursor_hex": cursor_hex,
        "byte_length": len(inner),
        "raw_hex": inner.hex().upper(),
    }"""

# Nuova funzione corretta basata sull'offset reale del cursore a 8 byte nel pacchetto 0x31 (inner[12:20] o inner[16:24])
new_func = """def decode_cursor_metadata_0x31(inner: bytes) -> Dict[str, Any]:
    \"\"\"
    Decodes Cursor / Metadata 0x31 packet on fd4b0005 (FW 50.41.1.0).
    Extracts the correct 8-byte NAND flash cursor for 0x17 auto-ACK.
    \"\"\"
    if len(inner) >= 124 and inner[0] == 0xAA and inner[1] == 0x01:
        inner = inner[8 : len(inner) - 4]

    cursor_hex: Optional[str] = None
    # Il cursore reale a 8 byte nel pacchetto 0x31 si trova all'offset inner[12:20]
    if len(inner) >= 20:
        cursor_bytes = inner[12:20]
        cursor_hex = cursor_bytes.hex().upper()

    return {
        "type": "METADATA_CURSOR",
        "opcode": "0x31",
        "cursor_hex": cursor_hex,
        "byte_length": len(inner),
        "raw_hex": inner.hex().upper(),
    }"""

if old_func in code:
    code = code.replace(old_func, new_func, 1)
    with open("whoop_ble/puffin_decoder.py", "w", encoding="utf-8") as f:
        f.write(code)
    print("[+] PUFFIN_DECODER.PY AGGIORNATO CON IL CURSORE 0x31 CORRETTO!")
else:
    print("[!] Impossibile trovare esattamente old_func, applico sostituzione mirata.")
    # Sostituzione di sicurezza per inner[5:13] con inner[12:20]
    code = code.replace("inner[5:13]", "inner[12:20]")
    with open("whoop_ble/puffin_decoder.py", "w", encoding="utf-8") as f:
        f.write(code)
    print("[+] Sostituzione mirata inner[12:20] applicata!")
