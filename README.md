# Beveltry — monorepo

Il repository contiene l'app Flutter e i moduli nativi, insieme al prototipo Python storico.

- `app/`: scheletro Flutter Android/iOS.
- `native/ios/BeveltryBLE/`: codec e handshake Swift, con trasporto astratto.
- `native/android/beveltry-ble/`: codec e handshake Kotlin, con trasporto astratto.
- `whoop_ble/`, `main.py`, `tests/`: prototipo Python storico, in attesa di essere riordinato sotto `research/`.
- `PROTOCOL_SPEC.md`: note del protocollo e dei formati verificati/ancora sperimentali.

Comandi per i test: `cd native/ios/BeveltryBLE && swift test`; `cd native/android && ./gradlew :beveltry-ble:testDebugUnitTest`; `cd app && flutter test`.
Il workflow GitHub Actions esegue i tre job su ogni push e pull request.
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
