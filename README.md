# Beveltry

Beveltry è un'app multipiattaforma in sviluppo per leggere e analizzare localmente i dati di un WHOOP 5.0. Il repository separa l'app Flutter, l'astrazione di trasporto nativa, il bootstrap Puffin e il materiale di ricerca.

## Struttura

- `app/`: scheletro Flutter Android/iOS.
- `native/ios/BeveltryBLE/`: package Swift con codec e handshake Puffin indipendenti da CoreBluetooth.
- `native/android/beveltry-ble/`: modulo Kotlin con codec e handshake Puffin indipendenti da Android BLE.
- `research/`: script e note di esplorazione del protocollo.
- `PROTOCOL_SPEC.md`: appunti sul framing e sui record, con ambito e limiti dichiarati.

Il trasporto BLE reale e l'archivio SQLite non fanno parte di questo milestone. Il trasporto astratto usa mock nei test; l'handshake imposta clock, inizializza i flag e verifica il primo cursore storico `0x31`.

## Test

Da macOS, eseguire i test Swift:

```sh
cd native/ios/BeveltryBLE
swift test
```

Con JDK 17 installato, eseguire i test Kotlin:

```sh
cd native/android
./gradlew :beveltry-ble:test
```

Con Flutter installato, controllare e avviare lo scheletro:

```sh
cd app
flutter pub get
flutter analyze
flutter run
```

Il payload Puffin ha padding con zeri, ma il framing non porta la lunghezza logica originale. In decode il codec rimuove quindi gli zeri finali; `rawPayload` conserva tutti i byte trasmessi. Un payload applicativo che termina con zeri non è distinguibile dalla sua forma paddata senza una lunghezza definita dal messaggio interno.

I test nativi vengono eseguiti anche da GitHub Actions (`.github/workflows/native-tests.yml`).
