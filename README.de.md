# Škoda API Connect für Home Assistant

[🇬🇧 English](README.md) | [🇩🇪 Deutsch](README.de.md) | [🇳🇱 Nederlands](README.nl.md)

Eine mehrsprachige [Home Assistant](https://www.home-assistant.io/)-Custom-Integration für
Škoda-Fahrzeuge auf Basis der offiziellen
[MyŠkoda Public API](https://public.api.connect.skoda-auto.cz/docs). Sie spricht die API
direkt mit einem **API-Schlüssel** an – ohne Benutzername/Passwort und ohne externe
Client-Bibliothek.

> **Inoffizielles Projekt.** Diese Integration steht in keiner Verbindung zu Škoda Auto und wird
> weder von Škoda Auto unterstützt noch empfohlen. Nutzung auf eigene Gefahr.

## Funktionen

Entwickelt nach den aktuellen Best Practices für Home-Assistant-Integrationen: reiner UI-Config-Flow,
`DataUpdateCoordinator` für effizientes Polling, Entity-Beschreibungen, Übersetzungen pro Entity,
Options-Flow, Reauthentifizierung und Diagnose-Download.

| Plattform | Entitäten |
|---|---|
| `sensor` | Batteriestand, Ladeleistung, Ladegrenze (nur lesend), Laderate, verbleibende Ladezeit, Batterie-/Gesamtreichweite, Kraftstoffstand, AdBlue-Reichweite, Kilometerstand, Zieltemperatur, Adresse der Parkposition, Türen verriegelt, zuverlässiger Verriegelungsstatus und Parkstatus (wie von der API gemeldet, z. B. `YES`, `TRUNK_OPENED`, `PARKED`), Name des aktuell aktiven Ladestandort-Profils, API-Status (Ergebnis der letzten Abfrage, Diagnose), Letzter API-Abruf (Datum und Uhrzeit des letzten erfolgreichen Abrufs, Diagnose), Letzte Fahrzeugdaten (wann das Fahrzeug selbst zuletzt Daten an die Škoda-Server gemeldet hat, Diagnose), API-Rate-Limit bis (wann das Anfragekontingent nach einem Rate-Limit wieder verfügbar ist, Diagnose), Verbleibende API-Anfragen (Rest des Stundenkontingents laut letzter Antwort, mit den Attributen `limit` und `reset_at`, Diagnose), Aktuelles Abrufintervall (Minuten, normales oder Ladeintervall, Attribut `mode`, Diagnose) |
| `binary_sensor` | Türen, Fenster, Kofferraum, Motorhaube, Beleuchtung, Zentralverriegelung, Laden, Ladekabel angesteckt, Ladekabel-Verriegelung, Fahrzeug an gespeichertem Ladestandort, Geparkt, nicht gesichert (siehe [Parkalarm](#parkalarm)) |
| `device_tracker` | Parkposition (erscheint auf dem Karten-Dashboard; während der Fahrt unbekannt) |
| `climate` | Standklimatisierung (an/aus, aktive Belüftung wenn das Fahrzeug sie unterstützt, Zieltemperatur) |
| `switch` | Laden starten/stoppen |
| `button` | API jetzt abrufen (ruft die MyŠkoda-API für das Fahrzeug sofort ab; kostet eine Anfrage des API-Kontingents und wird bei aktivem Rate-Limit abgelehnt), Fahrzeug aufwecken (siehe unten) |
| `number` | Ladelimit (Ziel-Ladezustand), Abfrageintervalle pro Fahrzeug (normal / beim Laden), automatisches Wecken eines ladenden Fahrzeugs, Parkalarm-Wartezeit |
| `select` | Lademodus |

Sensoren und Steuerungen werden nur für die Daten und Fernbedienungen angelegt, die dein
Fahrzeug tatsächlich meldet. Die Entitätenliste passt sich also an dein Auto an (Elektro, Plug-in-Hybrid
oder Verbrenner).

In den Optionen der Integration lässt sich ein **Nur-Lese-Modus** aktivieren, der alle
Fernsteuerungen deaktiviert und alle Sensoren aktiv lässt.

### Was die öffentliche API nicht bietet

Die Integration nutzt ausschließlich die öffentliche MyŠkoda-API. Folgende Funktionen sind daher
nicht möglich, weil die öffentliche API dafür keinen Endpunkt hat: Ver-/Entriegeln, Hupen &
Blinken, ein echter Wake-up-Aufruf (der Button „Fahrzeug aufwecken" ist nur ein Umweg, siehe unten), Scheibenheizung, Batterieschonmodus, reduzierter Ladestrom,
Außentemperatur und Softwareversion. Die Verriegelung ist ein reiner `binary_sensor`.

## Unterstützte Sprachen

Die Integration bringt Übersetzungen für Config-Flow, Options-Flow und Entitätsnamen in folgenden
Sprachen mit:

- English (`en`)
- Nederlands (`nl`)
- Deutsch (`de`)
- Français (`fr`)
- Čeština (`cs`)
- Slovenčina (`sk`)
- Español (`es`)
- Lëtzebuergesch (`lb`)

Home Assistant wählt automatisch die zur Spracheinstellung deiner Instanz passende Übersetzung und
fällt sonst auf Englisch zurück. Beiträge für weitere Sprachen sind willkommen – lege einfach eine
neue Datei unter `custom_components/skoda_api_connect/translations/` an.

Diese Dokumentation gibt es auf [Englisch](README.md), [Deutsch](README.de.md) und
[Niederländisch](README.nl.md).

## Installation

### HACS (empfohlen)

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=olafkenfenheuer&repository=Skoda-api-HA-Integration&category=integration)

1. Suche in HACS nach „Škoda API Connect“, klicke auf **Herunterladen** und installiere die Integration.
2. Starte Home Assistant neu.

Falls sie nicht in der Suche auftaucht (z. B. weil HACS die Standardliste noch nicht aktualisiert hat,
oder du eine Vorabversion testen möchtest), füge sie stattdessen als benutzerdefiniertes Repository hinzu:

1. Gehe in HACS zu **Integrationen** → Menü (⋮) → **Benutzerdefinierte Repositories**.
2. Füge die Repository-URL (`https://github.com/olafkenfenheuer/Skoda-api-HA-Integration`) mit der
   Kategorie **Integration** hinzu.
3. Suche in HACS nach „Škoda API Connect“, klicke auf **Herunterladen** und installiere die Integration.
4. Starte Home Assistant neu.

### Manuell

1. Lade dieses Repository herunter oder klone es.
2. Kopiere den Ordner `custom_components/skoda_api_connect` in das Verzeichnis
   `config/custom_components/` deiner Home-Assistant-Installation, sodass
   `config/custom_components/skoda_api_connect/manifest.json` existiert.
3. Starte Home Assistant neu.

## Einrichtung

1. Erstelle in der MyŠkoda-App unter <https://go.skoda.eu/api-keys> einen API-Schlüssel und wähle
   die Fahrzeuge aus, für die er gelten soll. Schlüssel sind an diese Fahrzeuge gebunden und laufen ab.
2. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen** und suche nach „Škoda API Connect“.
3. Gib den API-Schlüssel und die VIN jedes Fahrzeugs ein (mehrere VINs durch Komma getrennt). Die API
   bietet keine Fahrzeugliste, daher müssen die VINs manuell eingegeben werden.
4. Home Assistant prüft den Schlüssel und legt pro Fahrzeug ein Gerät mit allen passenden Entitäten an.
5. Nach der Einrichtung kannst du im Dialog **Konfigurieren** einstellen:
   - das Abfrageintervall (3–1440 Minuten, Standard 10),
   - das kürzere Intervall **während des Ladens** (Standard 5),
   - ob dieses Ladeintervall **auch bei eingestecktem Ladekabel** gilt (Standard aus),
   - den Nur-Lese-Modus,
   - die Benachrichtigungsdienste, die den [Parkalarm](#parkalarm) erhalten.

Den API-Schlüssel (oder die VINs) kannst du jederzeit ersetzen – vor dem Ablauf oder nachdem du einen
neuen erstellt hast – unter **Einstellungen → Geräte & Dienste → Škoda API Connect → ⋮ → Neu konfigurieren**.
Der Eintrag wird neu geladen und behält Entitäten, Verlauf und Optionen.

Läuft der Schlüssel ab (die API meldet `api-key-expired`), zeigt Home Assistant eine
Benachrichtigung zur erneuten Authentifizierung an. Erstelle einen neuen Schlüssel und gib ihn ein,
um die Verbindung wiederherzustellen, ohne den Verlauf der Entitäten zu verlieren.

## Hinweise zur API

Die Integration nutzt ausschließlich die dokumentierten Endpunkte unter
`https://public.api.connect.skoda-auto.cz/api/v1/vehicles/{vin}` und authentifiziert sich über den
Header `X-API-Key`. Die Daten werden per Polling aktualisiert.

### Sofortige Rückmeldung nach Befehlen

Ein Befehl wird von der API nur *angenommen* (HTTP 202); das Fahrzeug führt ihn eventuell viel später
aus, oder gar nicht, wenn es schläft. Damit die Oberfläche in der Zwischenzeit nicht unverändert
aussieht, zeigen Klimaanlage, Ladeschalter, Ladegrenze und Lademodus nach einem angenommenen Befehl
sofort den erwarteten Zustand, mit dem Attribut `pending: true`. Er wird ersetzt, sobald das Fahrzeug
neuere Daten dieses Bereichs meldet (es gilt, was das Fahrzeug sagt, auch wenn es dem Befehl
widerspricht), und nach 3 Minuten (Klimaanlage) bzw. 5 Minuten (die übrigen) verworfen, wenn sich das
Fahrzeug nicht meldet. Ein von der API abgelehnter Befehl ändert nichts. Das kostet keine zusätzlichen
Anfragen.

### Fahrzeug aufwecken

Das Fahrzeug meldet sich nur von Zeit zu Zeit bei den Škoda-Servern. Beim Laden kann es eine Stunde lang
schweigen, und die Abrufe liefern dann alte Werte, obwohl sie erfolgreich sind. Der Sensor **Letzte
Fahrzeugdaten** zeigt, wann sich das Auto zuletzt gemeldet hat; **Letzter Abruf** zeigt nur, wann die
Integration zuletzt Daten geholt hat.

Die API hat keinen Wake-up-Aufruf. Der Button **Fahrzeug aufwecken** sendet deshalb den aktuellen
Lademodus erneut, einen Befehl, der nichts ändert, aber das Fahrzeug erreichen muss; das Fahrzeug meldet
sich meist innerhalb einer Minute. Die Zahl **Ladendes Fahrzeug wecken nach (0 = aus)** macht das
automatisch, solange ein Fahrzeug lädt und sich die angegebene Zahl von Minuten nicht gemeldet hat
(standardmäßig aus, Minimum 10). Jedes Wecken verbraucht zwei Anfragen des Kontingents; es entfällt
während einer Rate-Limit-Pause und wenn weniger als 6 Anfragen übrig sind. Beides gibt es im
Nur-Lesen-Modus nicht.

### Abfrageintervalle pro Fahrzeug

Jedes Fahrzeug hat zwei `number`-Entitäten (Kategorie Konfiguration): **Abfrageintervall** und
**Abfrageintervall beim Laden**. Sie überschreiben für dieses Fahrzeug die Standardwerte aus den
Integrationsoptionen, gelten sofort ohne Neuladen und lassen sich aus Automationen setzen
(`number.set_value`). Ein Fahrzeug wird mit seinem Ladeintervall abgefragt, sobald der zuletzt
abgerufene Zustand `CHARGING` ist oder die Klimaanlage bzw. Lüftung läuft (damit ein Ausschalten an anderer Stelle früher sichtbar wird). Mit der Option „Ladeintervall auch bei eingestecktem Ladekabel
verwenden“ gilt es auch, sobald das Ladekabel eingesteckt ist – praktisch, um den Beginn eines
zeitgesteuerten Ladevorgangs zu erfassen, das schnellere Intervall bleibt dann aber aktiv, solange das Auto
angesteckt ist. Nach dem Start eines Ladevorgangs kann es bis zu ein normales Intervall dauern, bis das
schnellere Polling greift; startest du das Laden über Home Assistant, wird das Fahrzeug nach 30 Sekunden
aktualisiert und schaltet sofort um.

Der Schalter **Wenn eingesteckt schnell abfragen** (Kategorie Konfiguration) macht dasselbe pro
Fahrzeug und überschreibt für dieses Fahrzeug die globale Option.

### Parkalarm

Die Integration kann eine kritische Benachrichtigung senden, wenn ein Fahrzeug geparkt ist
(`parkingPosition.state` ist `PARKED`), aber eine dieser Bedingungen zutrifft:

- Zuverlässiger Verriegelungsstatus ist nicht `LOCKED` (entfällt, wenn das Fahrzeug ihn nicht meldet;
  die API meldet ihn nur für manche Fahrzeuge)
- Türen ist nicht `CLOSED`
- Türen verriegelt ist nicht `YES`
- Verriegelt ist nicht `YES`
- Fenster ist nicht `CLOSED` (entfällt, wenn die API `UNSUPPORTED` meldet, also keine elektrischen Fensterheber)

Ein als `UNKNOWN` gemeldeter Wert oder ein in der Antwort fehlendes anderes Feld gilt ebenfalls als
nicht gesichert.

Zum Einschalten öffnest du **Konfigurieren** und wählst einen oder mehrere **Empfänger des
Parkalarms**, zum Beispiel `notify.mobile_app_mein_telefon`. Die Liste bietet deine vorhandenen
Benachrichtigungsdienste an; du kannst auch einen Namen eintippen. Leer lassen für keine Alarme. Die
Empfänger gelten für alle Fahrzeuge des Eintrags.

Die Zahl **Parkalarm-Wartezeit** jedes Fahrzeugs (ein Regler von 0 bis 30 Minuten, Standard 5,
Kategorie Konfiguration) legt fest, wie lange das Fahrzeug ungesichert bleiben darf, bevor der Alarm
gesendet wird; bei 0 sofort. Die Zeit läuft ab der ersten Abfrage, die das Problem zeigt, oder ab der
Meldung des Fahrzeugs selbst, wenn diese seit der vorigen Abfrage (innerhalb eines Abfrageintervalls) kam, und der
Alarm wird nur gesendet, wenn die letzte Abfrage es noch zeigt. Der Zustand ist nur bei jeder Abfrage
bekannt, daher kann der Alarm bis zu ein Abfrageintervall später kommen, als die Wartezeit allein
vermuten lässt. Vor einem Neustart zwischengespeicherte Daten lösen nie einen Alarm aus; das
Fahrzeug muss erst abgefragt werden.

Pro Vorfall wird ein Alarm gesendet. Sobald eine Abfrage das Fahrzeug gesichert (oder nicht mehr
geparkt) zeigt, beginnt das nächste Problem einen neuen Vorfall. Offene Vorfälle werden gespeichert, daher sendet ein
Neustart von Home Assistant oder ein Neuladen der Integration den Alarm nicht erneut. Der Binärsensor **Geparkt, nicht
gesichert** zeigt dieselbe Bedingung, mit den fehlgeschlagenen Prüfungen im Attribut `reasons`, für
Dashboards und eigene Automationen.

An Companion-App-Empfänger (`notify.mobile_app_*`) wird der Alarm als kritisch gesendet: unter iOS
ertönt er auch im Lautlos- und Fokus-Modus, unter Android nutzt er den Alarm-Kanal. Andere
Benachrichtigungsdienste erhalten eine normale Nachricht. Alle Empfänger werden gleichzeitig
benachrichtigt, und ein fehlerhafter hält die anderen nicht auf. Der Text der Benachrichtigung ist englisch.

Ein Fahrzeug kann sich lange nicht bei den Škoda-Servern melden, und eine Abfrage liefert dann
seine letzte Meldung, egal wie alt. Daher wird der Alarm nur auf Daten gesendet, die das Fahrzeug
bei oder nach Beginn des Vorfalls gemeldet hat (der `carCapturedTimestamp` des Status); eine ältere Meldung
weiß womöglich nicht, dass das Auto inzwischen verriegelt wurde. Ein gerade geparktes Fahrzeug meldet
sich meist einmal und schläft dann; da diese Meldung den Vorfall beginnt, reicht sie für den Alarm. Liegt beim Ende der Wartezeit keine
solche Meldung vor, weckt die Integration das Fahrzeug einmal pro Vorfall, genauso wie der
Button **Fahrzeug aufwecken** (zwei Anfragen des Kontingents), und entscheidet anhand der
folgenden Meldung. Meldet sich das Fahrzeug nicht innerhalb von 5 Minuten nach dem Aufwecken,
schlägt das Aufwecken fehl oder entfällt es (im Nur-Lesen-Modus, während einer Ratenlimit-Pause, wenn
weniger als 6 Anfragen des Stundenkontingents übrig sind, und bei Fahrzeugen ohne bekannten Lademodus,
etwa den meisten Verbrennern), wird der Alarm trotzdem gesendet und endet mit „Not confirmed: last
report at …“: Ein Fahrzeug, das stumm bleibt, darf den Alarm nicht dauerhaft zurückhalten. Abgesehen
davon liest der Alarm nur Daten, die die Abfragen ohnehin geholt haben, und kostet keine Anfragen.

Jedes Aufwecken (oder warum es entfiel oder fehlschlug) und jeder Alarm wird im Logbuch des Sensors
**Geparkt, nicht gesichert** vermerkt, sodass sich später nachvollziehen lässt, warum ein Alarm wann kam.

### Ratenlimit

Die API erlaubt derzeit **20 Anfragen pro Stunde und VIN** (laut Dokumentation noch nicht final).
Ein Poll kostet eine Anfrage pro Fahrzeug, jeder Fernbefehl eine weitere. Deshalb:

- Standardintervall 10 Minuten (6 Anfragen/Stunde) bei 5 Minuten Minimum, und 5 Minuten, solange ein
  Fahrzeug lädt bzw. – mit aktivierter Option – eingesteckt ist (12 Anfragen/Stunde – lass Platz für Befehle).
- Nach Befehlen wird nicht jedes Mal aktualisiert; Befehle werden asynchron angenommen (HTTP 202),
  daher wird 30 Sekunden nach dem letzten Befehl einmal aktualisiert.
- HTTP-429-Antworten werden erkannt und das Polling pausiert, für die von der API genannte Wartezeit
  (`Retry-After`, `RateLimit-Reset` oder Fehlermeldung; zuzüglich 30 Sekunden; höchstens 1 Stunde, 15 Minuten ohne Angabe der API); dabei wird eine Warnung protokolliert.
- Der zuletzt bekannte Zustand eines Fahrzeugs bleibt erhalten, wenn nur seine Anfrage fehlschlägt.

Teile des Fahrzeugs, die die API nicht melden kann (zum Beispiel weil das Fahrzeug schläft), fehlen
in der Antwort einfach; die zugehörigen Entitäten werden angelegt, sobald die Daten verfügbar sind,
was ein Neuladen der Integration erfordern kann.

## Entwicklung

```bash
pip install pytest-homeassistant-custom-component
pytest
```

Einen Überblick über Code-Aufbau und Konventionen gibt [CLAUDE.md](CLAUDE.md).

## Changelog

Die Versionshinweise findest du in [CHANGELOG.md](CHANGELOG.md) (Englisch).

## Haftungsausschluss

Bereitgestellt wie besehen, ohne Gewährleistung. Škoda Auto kann seine API jederzeit ändern, wodurch
diese Integration nicht mehr funktionieren kann. Die Nutzung der MyŠkoda Public API unterliegt den
eigenen Nutzungsbedingungen von Škoda.
