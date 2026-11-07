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

Le richieste usano il payload interno `[0x23, seq, opcode, revisione, ...]`. La risposta reale `0x24` ha layout `[0]=0x24, [1]=echo_seq, [2]=resp_cmd, [3]=strap_seq, [4]=status`. Il parser supporta anche la risposta breve senza `strap_seq`, leggendo lo status da byte 3 quando il payload è lungo meno di 5 byte. `status=0x00` e `status=0x01` sono entrambi successi. L'handshake abbina le risposte a sequenza e opcode. Il contatore locale parte da 1 e ricomincia da 1 dopo `0xFF` (scelta implementativa; non è un fatto del firmware). Il timeout del bootstrap è configurabile e predefinito a 3 secondi.

| Passo | Richiesta / comportamento | Risposta e verifica |
|---|---|---|
| CLIENT_HELLO / GET_HELLO `0x91` | Envelope field `0x0100`; payload `[23, seq, 91, 01]` | Attende `0x24`, opcode `0x91`, status `01`. Con `seq=1` produce il frame statico sopra. |
| GET_CLOCK `0x0B` | `[23, seq, 0B, 00]` | Risposta con timestamp u32 LE in `bytes[5..8]`; payload inferiore a 9 byte è inatteso. Timestamp Unix deve essere maggiore di `1_700_000_000`, altrimenti viene sollevato `clockNotLatched`. |
| SET_CLOCK `0x0A` | `[23, seq, 0A, 01, timestamp u32 LE]` | Attende `0x24`, opcode `0A`, status `01`. |
| Verifica clock | GET_CLOCK successivo a SET_CLOCK | La macchina accetta il timestamp impostato o quello successivo di un secondo. È una tolleranza implementativa per il cambio di secondo, da confermare su hardware. |
| KEY_EXCHANGE `0x73` | `[23, seq, 73, 01, 01, materiale casuale di 32 byte]` | Attende ACK `0x24` con status `01`. Il materiale inizializza lo stato applicativo; il bonding è del sistema operativo, non è uno scambio crittografico. |
| SET_FF_VALUE `0x78` | `[23, seq, 78, 01, nome ASCII in 32 byte, valore u8]`; ogni flag viene inviata due volte | Ogni invio attende ACK. In caso di timeout o status negativo è previsto un solo retry. Il payload logico è 37 byte, paddato a 40; `payloadLen=44`, frame totale 52 byte. |
| GET_DATA_RANGE `0x22` | `[23, seq, 22, 00]` | Attende il frame `0x24` corrispondente e lo espone grezzo; il formato del range non viene interpretato. |
| SEND_HISTORICAL `0x16` | `[23, seq, 16, 00]` | Avvia un loop di offload continuo che emette ogni record `0x2F` subito al chiamante. |
| ACK cursore `0x17` | `[23, seq, 17, 01, cursor 8 byte]` | Inviato entro 800 ms per ogni nuovo cursore `0x31`, copiato dall'inner payload `[13..20]`. Cursori consecutivi duplicati non vengono riconfermati. Nessun ACK per `0x2F`. |

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

Il loop di offload termina quando il timestamp supera `endTimestamp`, quando viene invocato `stop()` oppure allo scadere del timeout configurabile. L'handshake torna allo stato `ready` alla chiusura del flusso.

## Layout record dichiarati

- **v18:** 124 byte sul cavo (8 header + 112 inner + 4 CRC32), `payloadLen=116` (112 inner + 4 CRC32). `V18Record.decode` riceve esclusivamente l'inner payload, tra 108 e 112 byte.
- **v26, 88 byte:** buffer PPG a 24 Hz, 24 campioni i16 LE.
- Gli R-R di `0x2A37` e dei record v18 sono riportati direttamente in millisecondi; non applicare conversione da unità 1/1024 s.
- SpO₂ all'offset 82 è riportata come `0x00` senza abbonamento (Entitlement Gate); questo progetto non decodifica SpO₂.

I dettagli non elencati per questi layout restano da determinare su campioni verificati.

## Decoder Dart (Livello 3)

I decoder puri Dart si trovano in `app/lib/src/records/`. Ricevono il payload interno del frame Puffin, senza l'envelope, e usano offset relativi al byte 0 del payload. I valori multi-byte sono little-endian. Non modificano il buffer ricevuto e rifiutano payload troppo corti o type/version non supportati con `RecordDecodeException`.

### V18Record (`0x2F`, versione `0x12`, 112 byte inner)

| Offset payload | Tipo | Campo | Interpretazione |
|---:|---|---|---|
| 2–3 | u16 | `seq` | Sequenza |
| 7–10 | u32 | `timestampSeconds` | Unix seconds, esposto come `DateTime` UTC |
| 14 | u8 | `hrPrimary` | BPM; `0` indica off-wrist |
| 15 | u8 | `rrCount` | Da 0 a 4 |
| 16–23 | 4×u16 | `rrIntervalsMs` | Millisecondi diretti; sono esposti solo i primi `rrCount` valori |
| 29 | u8 | `hrSecondary` | HR smoothed |
| 37, 41, 45 | 3×f32 | `gravityXyz` | X, Y, Z in g; da Argon, da validare su cattura estesa |
| 57–58 | u16 | `stepCounter` | Da Argon, da validare su cattura estesa |
| 61–62 / 63–64 | i16 | `skinTempRaw` | Prova a @61, fallback a @63 se il primo valore non è plausibile; da Argon |
| 64 | u8 | `activityFlag` | Da Argon, da validare su cattura estesa |
| 82 | u8 | `spo2Candidate` | Byte grezzo candidato; non viene decodificato come SpO₂ |
| 96 | u8 | `sleepState` | Da Argon, da validare su cattura estesa |
| 98–99 | u16 | `opticalBaselineCh1` | Da Argon, da validare su cattura estesa |
| 106–107 | u16 | `opticalBaselineCh2` | Da Argon, da validare su cattura estesa |

La cattura reale dal firmware `50.41.1.0` conferma i campi seq, timestamp, HR primaria e R-R. Gli offset Argon restano sperimentali. Il decoder non interpreta altri offset.

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
- ACK storico `0x17` su `fd4b0002`: per ogni nuovo cursore `0x31`, gli 8 byte vengono copiati da `frame.inner[13..<21]`; ACK entro 800 ms e nessun ACK sui record `0x2F`.

Questi comportamenti sono requisiti/risultati preliminari riportati dal progetto e vanno convalidati prima di essere usati per operazioni che scrivono sul dispositivo.

## Requisiti background per un milestone BLE successivo

- iOS: `UIBackgroundModes` con `bluetooth-central`, `CBCentralManagerOptionRestoreIdentifierKey` e `NSBluetoothAlwaysUsageDescription`. CoreBluetooth non è disponibile nel simulatore.
- Android: `ForegroundService` con `foregroundServiceType="connectedDevice"` e WorkManager per la riconnessione.

## Offset da Argon da validare su cattura estesa

La cattura firmware `50.41.1.0` conferma gli offset seq @2, timestamp @7, HR primaria @14, rrCount @15 e RR @16+ in millisecondi. Restano da validare su cattura estesa: gravity @37/41/45, stepCounter @57, skinTemp @61/63, activityFlag @64, candidato grezzo `spo2Candidate` @82, sleepState @96 e opticalBaseline @98/106. Non vengono assunte semantiche ulteriori.

Il frame v18 è lungo 124 byte sul cavo: 8 header + 112 inner + 4 CRC32. `payloadLen=116` rappresenta 112 byte inner più il CRC32. `V18Record.decode` accetta solo 108–112 byte di inner payload; non interpreta un frame da 124 byte.

Per `0x24`, status è al byte 4 quando il payload ha almeno 5 byte, altrimenti al byte 3. Gli status `0x00` e `0x01` indicano successo. Il clock u32 little-endian è ai byte 5–8 e deve superare `1_700_000_000`.

L'offload `0x16` inoltra in streaming i frame `0x2F`. Per ogni nuovo cursore `0x31` su `fd4b0005`, invia `0x17` su `fd4b0002` entro 800 ms con `inner[13..20]`; cursori consecutivi identici non vengono ri-ACKati. I frame `0x2F` non ricevono ACK. Il flusso termina su `endTimestamp`, `stop()` o timeout.
