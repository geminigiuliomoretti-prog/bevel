# Specifica di protocollo (note di ricerca)

Questa pagina raccoglie le osservazioni fornite per il progetto. Le caratteristiche proprietarie e i layout dei record sono da trattare come ipotesi di lavoro da confermare con catture ripetibili; non sono una specifica WHOOP pubblica. Il codec e l'handshake implementati qui non aprono connessioni BLE reali.

## GATT

UUID proprietario dichiarato: `fd4b0001-cce1-4033-93ce-002d5875f58a` (short `0xFD4B`). Caratteristiche dichiarate:

| UUID corto | Nome/ruolo dichiarato | Proprietà |
|---|---|---|
| `fd4b0002` | `L_CMD_TO_STRAP` | Write with Response |
| `fd4b0003` | `L_CMD_FROM_STRAP` | Notify |
| `fd4b0004` | `L_EVENTS_FROM_STRAP` | Notify |
| `fd4b0005` | `DATA_FROM_STRAP` | Notify, throughput elevato |
| `fd4b0007` | `MEMFAULT/META` | Notify |

Servizi standard dichiarati: `0x180D` con `0x2A37` (frequenza cardiaca), `0x180F` con `0x2A19` (batteria), `0x180A` (informazioni dispositivo).

## Envelope Puffin

Tutti i campi multi-byte sono little-endian. Il frame ha header da 8 byte, payload interno paddato con zeri a multipli di 4 e trailer CRC32 da 4 byte.

| Offset | Campo | Regola |
|---:|---|---|
| 0 | SOF | `0xAA` |
| 1 | Versione | `0x01` |
| 2–3 | `payloadLen` | byte del payload paddato più 4 byte del CRC32 |
| 4–5 | `field` | u16 little-endian; nel frame CLIENT_HELLO di riferimento vale `0x0100` |
| 6–7 | CRC16 header | CRC-16/MODBUS sui byte 0–5 |
| 8… | payload interno | padding zero fino a multiplo di 4 |
| ultimi 4 | CRC32 | CRC-32 IEEE sul payload paddato soltanto |

CRC16/MODBUS: polinomio riflesso `0xA001`, init `0xFFFF`, xor finale `0`. CRC32 IEEE: polinomio riflesso `0xEDB88320`, init e xor finale `0xFFFFFFFF`. Il frame minimo è di 16 byte; la dimensione totale è `8 + payloadLen` perché `payloadLen` include il trailer. Lo stream parser scarta il byte SOF su CRC header invalido, accumula il frame dichiarato e verifica CRC32 prima di emetterlo.

Il framing non contiene la lunghezza logica prima del padding. Perciò gli zeri finali di un payload logico non possono essere distinti dal padding tramite il solo envelope.

## CLIENT_HELLO

Frame statico riportato come verificato su hardware:

```text
AA 01 08 00 00 01 E6 71 23 01 91 01 36 3E 5C 8D
```

Scomposizione: SOF `AA`, versione `01`, `payloadLen=0x0008`, field wire `00 01` (u16 little-endian `0x0100`), CRC16 `0x71E6` (wire `E6 71`), payload `23 01 91 01`, CRC32 `0x8D5C3E36` (wire `36 3E 5C 8D`). Il frame statico è il riferimento per CLIENT_HELLO: prevale sul valore `0x0001` riportato nel PDF e nelle note precedenti. L'encoder deve produrre questi byte per field `0x0100` e payload `[23, 01, 91, 01]`.

## Opcode e ruoli dichiarati

| Opcode | Ruolo |
|---:|---|
| `0x91` | GET_HELLO |
| `0x0A` | SET_CLOCK |
| `0x0B` | GET_CLOCK |
| `0x42` | SET_ALARM_TIME (non è SET_CLOCK) |
| `0x73` | key exchange |
| `0x78` | SET_FF_VALUE |
| `0x22` | GET_DATA_RANGE |
| `0x16` | SEND_HISTORICAL |
| `0x17` | ACK storico |
| `0x2F` | burst storico |
| `0x28` | HR live compact |

Non inviare opcode distruttivi `0x19` (ERASE) o `0x1D` (REBOOT).

### Bootstrap e handshake

Il trasporto astratto assume che connessione e bonding BLE siano già completati prima di `PuffinHandshake.start()`. Il bootstrap si sottoscrive a `fd4b0003`, `fd4b0004` e `fd4b0005` prima di inviare comandi. Gli stati `connecting` e `bonding` sono riservati al futuro trasporto nativo: questa implementazione non li esegue.

Le richieste usano il payload interno `[0x23, seq, opcode, revisione, ...]`. Le risposte di comando attese iniziano con `[0x24, seq, opcode, status]`; per l'ACK positivo `status=0x01`. L'handshake abbina le risposte a sequenza e opcode. Il contatore locale parte da 1 e ricomincia da 1 dopo `0xFF` (scelta implementativa; non è un fatto del firmware). Il timeout è configurabile e predefinito a 3 secondi.

| Passo | Richiesta / comportamento | Risposta e verifica |
|---|---|---|
| CLIENT_HELLO / GET_HELLO `0x91` | Envelope field `0x0100`; payload `[23, seq, 91, 01]` | Attende `0x24`, opcode `0x91`, status `01`. Con `seq=1` produce il frame statico sopra. |
| GET_CLOCK `0x0B` | `[23, seq, 0B, 00]` | `0x24, seq, 0B, status=01, timestamp u32 LE`; eventuale byte flags successivo ignorato. Timestamp Unix in secondi. |
| SET_CLOCK `0x0A` | `[23, seq, 0A, 01, timestamp u32 LE]` | Attende `0x24`, opcode `0A`, status `01`. |
| Verifica clock | GET_CLOCK successivo a SET_CLOCK | La macchina accetta il timestamp impostato o quello successivo di un secondo. È una tolleranza implementativa per il cambio di secondo, da confermare su hardware. |
| KEY_EXCHANGE `0x73` | `[23, seq, 73, 01, 01, materiale casuale di 32 byte]` | Attende ACK `0x24` con status `01`. Il materiale inizializza lo stato applicativo; il bonding è del sistema operativo, non è uno scambio crittografico. |
| SET_FF_VALUE `0x78` | `[23, seq, 78, 01, nome ASCII in 32 byte, valore u8]`; ogni flag viene inviata due volte | Ogni invio attende ACK. In caso di timeout o status negativo è previsto un solo retry. Il payload logico è 37 byte, paddato a 40; `payloadLen=44`, frame totale 52 byte. |
| GET_DATA_RANGE `0x22` | `[23, seq, 22, 00]` | Attende il frame `0x24` corrispondente e lo espone grezzo; il formato del range non viene interpretato. |
| SEND_HISTORICAL `0x16` | `[23, seq, 16, 00]` | Avvia il flusso; questa milestone attende solo il primo `0x31` su `fd4b0005`. |
| ACK cursore `0x17` | `[23, seq, 17, 01, cursor 8 byte]` | Inviato solo dopo aver ricevuto il primo `0x31`; cursor copiato da `rawPayload[13..<21]`. Non viene inviato per i frame `0x2F`. |

Le 16 flag SET_FF_VALUE impostate, con valore, sono:

| Nome | Valore | Nome | Valore |
|---|---:|---|---:|
| `enable_r22_packets` | 2 | `enable_r22_v2_packets` | 2 |
| `enable_r22_v3_packets` | 2 | `enable_r22_v4_packets` | 1 |
| `enable_r22_v5_packets` | 2 | `enable_r22_v6_packets` | 2 |
| `enable_r22_v8_packets` | 2 | `make_hrfm_visible` | 2 |
| `disable_pip_r26_packets` | 2 | `wear_detect_bias` | 2 |
| `hr_ch_switching` | 2 | `ir_hw_switching` | 2 |
| `enable_passive_strap_fit_gen5` | 1 | `enable_sig11_during_sleep` | 2 |
| `dorset_inhibit_wpt` | 2 | `enable_sig12` | 2 |

La gestione termina nello stato `offloadStarted` dopo l'ACK `0x17` del primo `0x31`; non implementa la ricezione e persistenza dell'offload storico.

## Layout record dichiarati

- **v18, 124 byte:** HR primaria; intervallo R-R u16 LE in millisecondi; vettore gravità 3×f32; quaternioni; contatore passi; temperatura divisa per 10; `sleep_state`; candidato SpO₂ all'offset 82.
- **v26, 88 byte:** buffer PPG a 24 Hz, 24 campioni i16 LE.
- Gli R-R di `0x2A37` e dei record v18 sono riportati direttamente in millisecondi; non applicare conversione da unità 1/1024 s.
- SpO₂ all'offset 82 è riportata come `0x00` senza abbonamento (Entitlement Gate); questo progetto non decodifica SpO₂.

I dettagli non elencati per questi layout restano da determinare su campioni verificati.

## Decoder Dart (Livello 3)

I decoder puri Dart si trovano in `app/lib/src/records/`. Ricevono il payload interno del frame Puffin, senza l'envelope, e usano offset relativi al byte 0 del payload. I valori multi-byte sono little-endian. Non modificano il buffer ricevuto e rifiutano payload troppo corti o type/version non supportati con `RecordDecodeException`.

### V18Record (`0x2F`, versione `0x12`, 124 byte)

| Offset payload | Tipo | Campo | Interpretazione |
|---:|---|---|---|
| 2–3 | u16 | `seq` | Sequenza |
| 7–10 | u32 | `timestampSeconds` | Unix seconds, esposto come `DateTime` UTC |
| 14 | u8 | `hrPrimary` | BPM; `0` indica off-wrist |
| 15 | u8 | `rrCount` | Da 0 a 4 |
| 16–23 | 4×u16 | `rrIntervalsMs` | Millisecondi diretti; sono esposti solo i primi `rrCount` valori |
| 29 | u8 | `hrSecondary` | HR smoothed |
| 33–44 | 3×f32 | `gravityXyz` | X, Y, Z in g |
| 45–60 | 4×f32 | `quaternionWxyz` | Ordine W, X, Y, Z |
| 57–58 | u16 | `stepCounter` | Sperimentale e nullable; ricade nei byte del quaternion Z |
| 60–61 | i16 | `skinTempRaw` | Sperimentale e nullable; valore grezzo, `/10` °C è un'interpretazione da verificare |
| 62 | u8 | `sleepState` | Sperimentale e nullable; `2` è la lettura proposta per asleep |
| 82 | u8 | `spo2Candidate` | Byte grezzo, non è una misura SpO₂ |
| 104 | u8 | marker | Valore riportato `0x01` |
| 106–107 | u16 | `opticalBaseline` | Grezzo |
| 108–109 | 2×u8 | `opticalAmpA/B` | Grezzi |
| 113–116 | f32 | `unknownF32` | Sperimentale e nullable; valore non finito esposto come `null` |

La sovrapposizione tra quaternion (45–60), `stepCounter` (57–58) e `skinTempRaw` (60–61) è ambigua e va verificata su hardware. `stepCounter`, `skinTempRaw`, `sleepState` e `unknownF32` non sono validati byte-per-byte e non vanno usati per logica critica. I test ancorano il quaternion e la gravità e controllano separatamente che le letture sperimentali non causino errori. La mappatura usata qui è relativa al payload interno e segue la specifica Beveltry; mappe pubbliche con offset del frame completo o layout differenti non vanno trasposte senza una cattura di riferimento.

`spo2Candidate` all'offset 82 è `0x00` senza entitlement. Il decoder lo conserva come byte grezzo e non tenta di ricavarne SpO₂.

### V26Record (`0x2F`, versione `0x1A`, 88 byte)

| Offset payload | Tipo | Campo | Interpretazione |
|---:|---|---|---|
| 27–74 | 24×i16 | `ppgSamples` | Campioni signed little-endian di un singolo canale PPG AC-coupled a 24 Hz |

Il buffer non rappresenta canali Red/IR intercalati e non consente di calcolare SpO₂.

### Live28Record (`0x28`, versione `0x02`, 12 byte)

| Offset payload | Tipo | Campo | Interpretazione |
|---:|---|---|---|
| 2–5 | u32 | `timestampSeconds` | Unix seconds, esposto come `DateTime` UTC |
| 8 | u8 | `hr` | BPM |
| 9 | u8 | `validity` | `0` off-wrist, `1` HR+RR, `2` HR+RR+extra |
| 10–11 | u16 | `rrIntervalMs` | Millisecondi diretti |

### StandardHrRecord (`0x2A37`)

Il payload non contiene type/version. Byte 0 è `flags`; bit 0 seleziona HR u8/u16, bit 3 indica il campo energy-expended u16, bit 4 indica gli intervalli R-R u16 successivi. I valori u16 sono letti little-endian. Per il profilo WHOOP usato da questo progetto, gli R-R vengono esposti in millisecondi senza conversione `1/1024 s`.

`RecordDecoder` instrada `0x2F/0x12` a V18, `0x2F/0x1A` a V26 e `0x28/0x02` a Live28. `0x2A37` viene decodificato chiamando direttamente `StandardHrRecord.decode` sulla caratteristica standard.

## Note operative e mitigazioni future

- Deduplicare con `(record_index, timestamp_epoch, beat_ordinal)`; deduplicare solo per timestamp è stato associato a re-delivery e over-count riportato di 2,53×.
- Dopo batteria a 0%, il clock latching richiede un SET_CLOCK prima che il cinturino persista nuovi dati.
- È riportato un solo bond attivo, in conflitto con l'app ufficiale.
- ACK storico `0x17` su `fd4b0002`: per ogni frame `0x31`, il cursore di 8 byte è riportato agli offset `frame.inner[13..<21]`.

Questi comportamenti sono requisiti/risultati preliminari riportati dal progetto e vanno convalidati prima di essere usati per operazioni che scrivono sul dispositivo.

## Requisiti background per un milestone BLE successivo

- iOS: `UIBackgroundModes` con `bluetooth-central`, `CBCentralManagerOptionRestoreIdentifierKey` e `NSBluetoothAlwaysUsageDescription`. CoreBluetooth non è disponibile nel simulatore.
- Android: `ForegroundService` con `foregroundServiceType="connectedDevice"` e WorkManager per la riconnessione.
