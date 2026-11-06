# Beveltry — monorepo

Il repository conserva il prototipo Python di diagnostica e aggiunge l'app Flutter e i moduli nativi per il framing e il bootstrap Puffin.

- `app/`: scheletro Flutter Android/iOS.
- `native/ios/BeveltryBLE/`: codec e handshake Swift, con trasporto astratto.
- `native/android/beveltry-ble/`: codec e handshake Kotlin, con trasporto astratto.
- `whoop_ble/`, `main.py`, `tests/`: prototipo Python mantenuto dalla storia remota.
- `PROTOCOL_SPEC.md`: note del protocollo e dei formati verificati/ancora sperimentali.

Comandi per i test: `cd native/ios/BeveltryBLE && swift test`; `cd native/android && ./gradlew :beveltry-ble:test`; `cd app && flutter test`.
Il workflow GitHub Actions esegue i tre job su ogni push e pull request.

La documentazione storica del prototipo è conservata sotto.

# WHOOP 5.0 BLE Reverse Engineering & Diagnostics Toolkit
## Workstation: Microsoft Surface Pro / Windows 11 Pro

Prototipo per l'analisi e l'interfacciamento Bluetooth Low Energy con il dispositivo **WHOOP 5.0** (hardware `WHOOP 5WP`), sviluppato per la ricerca e reverse engineering preliminare in vista della futura implementazione su Android (Kotlin) e iOS (Swift).

---

### 1. Requisiti e Vincoli Rispettati

- **Nessuna WHOOP API, OAuth o dipendenza dai server WHOOP.**
- **Nessun dato fittizio / simulato**: tutte le letture e le scansioni sono state eseguite sull'adattatore Bluetooth fisico di Microsoft Surface Pro e sul dispositivo fisico `WHOOP 5WP` (`FD:49:44:66:1D:92`).
- **Nessuna modifica del firmware, reset, o alterazione bonding.**
- **Nessuna scrittura su caratteristiche sconosciute**: le caratteristiche proprietarie sono state auditate rigorosamente in modalità read-only per verificare autorizzazioni e codici di errore GATT, senza inviare payload ciechi.
- **Privacy e Mascheramento**: i numeri seriali e gli identificativi confidenziali sono mascherati nei log esportabili (`5A***75`).

---

### 2. Architettura Software Modulare

Il progetto separa nettamente il livello di trasporto Bluetooth LE dalla logica di parsing/decodifica:

```
Bevel/
├── main.py                     # Entry-point interattivo e CLI diagnostica
├── run.bat                     # Launcher one-click per Windows (cmd)
├── run.ps1                     # Launcher PowerShell per Windows 11
├── requirements.txt            # Dipendenze (Bleak >= 0.22.3)
├── whoop_ble/
│   ├── __init__.py
│   ├── constants.py            # Dizionario UUID Bluetooth SIG e WHOOP Gen 5
│   ├── scanner.py              # Scanner BLE con euristica multi-fattoriale
│   ├── connection.py           # Connection lifecycle e gestione disconnessioni
│   ├── explorer.py             # GATT table discovery e classificazione
│   ├── device_info.py          # Lettore dati standard (0x180A, 0x180F, 0x1800)
│   ├── hr_decoder.py           # Decodificatore Bluetooth SIG HR/RR puro (0x2A37)
│   ├── notification_handler.py # Sottoscrizione notifiche BLE e routing
│   ├── proprietary.py          # Audit del servizio proprietario Gen 5
│   └── logger.py               # Logging strutturato (UTC/Local), export JSON/CSV
├── tests/
│   ├── test_constants.py       # Test unitari normalizzazione e lookup UUID
│   ├── test_hr_decoder.py      # Test unitari decodifica pacchetti HR e RR
│   └── test_scanner_heuristics.py # Test scoring euristico multi-fattore
├── logs/                       # Log di sessione JSONL e dump pacchetti CSV
└── exports/                    # Report diagnostici e alberi GATT JSON
```

---

### 3. Istruzioni di Installazione ed Esecuzione

#### Prerequisiti:
- Windows 11 con adattatore Bluetooth LE abilitato.
- Python 3.10+ (verificato e testato su Python 3.14.0).

#### Avvio Rapido:
È possibile avviare il tool tramite lo script batch o PowerShell:
```powershell
# Da PowerShell:
.\run.ps1
```
oppure con il file batch:
```cmd
run.bat
```

#### Installazione Manuale:
```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
```

#### Modalità Interattiva (Menu CLI):
```powershell
$env:PYTHONPATH="."
.venv\Scripts\python.exe main.py
```

#### Modalità Automatica / Argomenti CLI:
- **Scansione ambientale:**
  ```powershell
  .venv\Scripts\python.exe main.py --scan --scan-duration 6.0
  ```
- **Connessione ed esplorazione rapida del target:**
  ```powershell
  .venv\Scripts\python.exe main.py --address "FD:49:44:66:1D:92"
  ```
- **Suite diagnostica completa automatizzata con streaming HR:**
  ```powershell
  .venv\Scripts\python.exe main.py --address "FD:49:44:66:1D:92" --auto --hr-duration 15
  ```

---

### 4. Risultati Sperimentali — Dispositivo WHOOP B (Fisico)

- **Device Name:** `WHOOP 5WP`
- **Bluetooth Address (BLE):** `FD:49:44:66:1D:92`
- **RSSI Rilevato:** `-66 dBm`

#### Dati Standard Rilevati (FASE C):
| Caratteristica | UUID | Valore Decodificato | Pacchetto Hex Originale |
| :--- | :--- | :--- | :--- |
| **Battery Level** | `00002A19` | `67%` | `0x43` |
| **Device Name** | `00002A00` | `WHOOP 5WP` | `0x57484F4F502035575000` |
| **Appearance** | `00002A01` | `0000` (Generic) | `0x0000` |
| **Central Address Res.** | `00002AA6` | `00` (Disabled) | `0x00` |
| **Manufacturer Name** | `00002A29` | `WHOOP Inc.` | `0x57484F4F5020496E632E` |
| **Model Number** | `00002A24` | `5.0` | `0x352E3000` |
| **Serial Number** | `00002A25` | `5A***75` *(mascherato)* | `0x3541473035353836373500` |
| **Hardware Revision** | `00002A27` | `WG50_r52` | `0x574735305F723532` |
| **Firmware Revision** | `00002A26` | `50.41.1.0` | `0x35302E34312E312E30` |

---

### 5. Struttura Completa GATT (FASE B)

Totale Servizi: **6** (5 Standard SIG, 1 Proprietario)  
Totale Caratteristiche: **16**

#### 1. Generic Access (`00001800-0000-1000-8000-00805f9b34fb`)
- `00002a00-0000-1000-8000-00805f9b34fb` (Device Name) — `[READ]` (Handle: 0x0002)
- `00002a01-0000-1000-8000-00805f9b34fb` (Appearance) — `[READ]` (Handle: 0x0004)
- `00002aa6-0000-1000-8000-00805f9b34fb` (Central Address Resolution) — `[READ]` (Handle: 0x0006)

#### 2. Generic Attribute (`00001801-0000-1000-8000-00805f9b34fb`)
- `00002a05-0000-1000-8000-00805f9b34fb` (Service Changed) — `[INDICATE]` (Handle: 0x0011, CCCD: 0x0013)

#### 3. Heart Rate Service (`0000180d-0000-1000-8000-00805f9b34fb`)
- `00002a37-0000-1000-8000-00805f9b34fb` (Heart Rate Measurement) — `[NOTIFY]` (Handle: 0x0021, CCCD: 0x0023)

#### 4. Device Information Service (`0000180a-0000-1000-8000-00805f9b34fb`)
- `00002a29-0000-1000-8000-00805f9b34fb` (Manufacturer Name) — `[READ]` (Handle: 0x0031)
- `00002a24-0000-1000-8000-00805f9b34fb` (Model Number) — `[READ]` (Handle: 0x0033)
- `00002a25-0000-1000-8000-00805f9b34fb` (Serial Number) — `[READ]` (Handle: 0x0035)
- `00002a26-0000-1000-8000-00805f9b34fb` (Firmware Revision) — `[READ]` (Handle: 0x0037)
- `00002a27-0000-1000-8000-00805f9b34fb` (Hardware Revision) — `[READ]` (Handle: 0x0039)

#### 5. Battery Service (`0000180f-0000-1000-8000-00805f9b34fb`)
- `00002a19-0000-1000-8000-00805f9b34fb` (Battery Level) — `[READ, NOTIFY]` (Handle: 0x0089, CCCD: 0x008B)

#### 6. WHOOP Gen 5 Proprietary Service (`fd4b0001-cce1-4033-93ce-002d5875f58a`)
- `fd4b0002-cce1-4033-93ce-002d5875f58a` — `[WRITE, WRITE-WITHOUT-RESPONSE]` (Handle: 0x099A)
  - Endpoint di comando/trasmissione verso il dispositivo (Host -> Device).
- `fd4b0003-cce1-4033-93ce-002d5875f58a` — `[NOTIFY]` (Handle: 0x099C, CCCD: 0x099E)
  - Canale notifiche / stream di risposta dati.
- `fd4b0004-cce1-4033-93ce-002d5875f58a` — `[NOTIFY]` (Handle: 0x099F, CCCD: 0x09A1)
  - Canale notifiche secondario / streaming telemetrico.
- `fd4b0005-cce1-4033-93ce-002d5875f58a` — `[NOTIFY]` (Handle: 0x09A2, CCCD: 0x09A4)
  - Canale eventi asincroni / transfer pacchetti.
- `fd4b0007-cce1-4033-93ce-002d5875f58a` — `[NOTIFY]` (Handle: 0x09A5, CCCD: 0x09A7)
  - Canale dati diagnostici / storici.

---

### 6. Matrice di Test e Validazione

| Test ID | Descrizione Funzionalità | Risultato Atteso | Risultato Effettivo | Evidenza nei Log | Stato |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TEST-01** | Verifica ambiente Python e BLE su Surface Pro | Python 3.10+ presente, servizio `bthserv` e radio BLE attivi | Python 3.14.0 rilevato, Intel Wireless BT attivo | Registro servizi di sistema Windows | **PASS** |
| **TEST-02** | Scansione BLE e rilevamento WHOOP 5.0 (FASE A) | Rilevamento WHOOP senza dipendere esclusivamente dal nome | Dispositivo `FD:49:44:66:1D:92` identificato con score 70/100 (Nome + Servizio HR 0x180D + Servizio Gen 5 `fd4b0001`) | `logs/diagnostics_*.log` e log CLI | **PASS** |
| **TEST-03** | Connessione BLE e gestione stato (FASE B) | Connessione pulita, gestione stato CONNECTED e disconnessione controllata | Connessione stabilita con successo su Surface Pro, disconnessione pulita | `logs/diagnostics_*.log` event `CONNECTION_STATE_CHANGE` | **PASS** |
| **TEST-04** | GATT Table Discovery completa (FASE B) | Mappatura di 100% di servizi, caratteristiche, descrittori e proprietà | 6 servizi e 16 caratteristiche mappati e salvati in JSON | `exports/gatt_*.json` | **PASS** |
| **TEST-05** | Lettura Battery Level (FASE C) | Lettura valore percentuale 0-100% | Batteria letta: `67%` (hex `0x43`) | `logs/packets_*.csv` | **PASS** |
| **TEST-06** | Lettura Device Information (FASE C) | Lettura stringhe produttore, modello, firmware, hardware e seriale mascherato | `WHOOP Inc.`, Model `5.0`, FW `50.41.1.0`, HW `WG50_r52`, SN `5A***75` | `logs/packets_*.csv` | **PASS** |
| **TEST-07** | Sottoscrizione Notifiche HR (FASE C) | Abilitazione CCCD per 0x2A37 Heart Rate Measurement | CCCD sottoscritto regolarmente | `HR_STREAM_STARTED` in `logs/session_*.jsonl` | **PASS** |
| **TEST-08** | Decodifica pacchetti HR & RR (FASE C) | Decodifica conforme specifiche standard Bluetooth SIG (BPM, Contact, RR ms) | 3 unit test passati con successo (UINT8, UINT16, Sensor Contact, RR intervals 1/1024s) | `tests/test_hr_decoder.py` -> ALL PASSED | **PASS** |
| **TEST-09** | Audit Proprietary Service Gen 5 (FASE D) | Verifica proprietà senza scritture cieche e documentazione endpoint | Rilevate caratteristiche Write `0x0002` e 4 canali Notify (`0x0003`, `0x0004`, `0x0005`, `0x0007`). Zero scritture eseguite. | `exports/diagnostic_report_*.json` | **PASS** |
| **TEST-10** | Ricezione continua campioni biometrici live da polso | Ricezione live continua durante indosso | La sottoscrizione 0x2A37 è operativa; il sensore PPG WHOOP richiede il rilevamento di contatto cutaneo (on-body detection) per attivare l'emissione dei campioni ottici | In attesa di sessione con dispositivo indossato al polso | **NOT TESTED (On-body pending)** |
