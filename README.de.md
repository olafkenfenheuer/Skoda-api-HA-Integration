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
| `sensor` | Batteriestand, Ladeleistung, Ladegrenze (nur lesend), Laderate, verbleibende Ladezeit, Batterie-/Gesamtreichweite, Kraftstoffstand, AdBlue-Reichweite, Kilometerstand, Zieltemperatur, Adresse der Parkposition, Türen verriegelt, zuverlässiger Verriegelungsstatus und Parkstatus (wie von der API gemeldet, z. B. `YES`, `TRUNK_OPENED`, `PARKED`), Name des aktuell aktiven Ladestandort-Profils (mit ID, Ladeziel, nächster Ladezeit und der Liste aller Profile als Attribute), API-Status (Ergebnis der letzten Abfrage, Diagnose), Letzter API-Abruf (Datum und Uhrzeit des letzten erfolgreichen Abrufs, Diagnose), Letzte Fahrzeugdaten (wann das Fahrzeug selbst zuletzt Daten an die Škoda-Server gemeldet hat, Diagnose), API-Rate-Limit bis (wann das Anfragekontingent nach einem Rate-Limit wieder verfügbar ist, Diagnose), Verbleibende API-Anfragen (Rest des Stundenkontingents laut letzter Antwort, mit den Attributen `limit` und `reset_at`, Diagnose), Aktuelles Abrufintervall (Minuten, normales oder Ladeintervall, Attribut `mode`, Diagnose) |
| `binary_sensor` | Türen, Fenster, Kofferraum, Motorhaube, Beleuchtung, Zentralverriegelung, Laden, Ladekabel angesteckt, Ladekabel-Verriegelung, Fahrzeug an gespeichertem Ladestandort, Geparkt, nicht gesichert (siehe [Parkalarm](#parkalarm)) |
| `device_tracker` | Parkposition (erscheint auf dem Karten-Dashboard; während der Fahrt unbekannt) |
| `climate` | Standklimatisierung (an/aus, aktive Belüftung wenn das Fahrzeug sie unterstützt, Zieltemperatur), Standheizung (nur bei Fahrzeugen, die sie haben, siehe [Standheizung](#standheizung)) |
| `switch` | Laden starten/stoppen, Stecker nach dem Laden entriegeln pro Ladeprofil (siehe [Ladeprofile](#ladeprofile)) |
| `button` | API jetzt abrufen (ruft die MyŠkoda-API für das Fahrzeug sofort ab; kostet eine Anfrage des API-Kontingents und wird bei aktivem Rate-Limit abgelehnt), Fahrzeug aufwecken (siehe unten) |
| `number` | Ladelimit (Ziel-Ladezustand), Abfrageintervalle pro Fahrzeug (normal / beim Laden), automatisches Wecken eines ladenden Fahrzeugs, Parkalarm-Wartezeit, Laufzeit der Standheizung, Ladeziel pro Ladeprofil |
| `select` | Lademodus (nur wenn das Fahrzeug seine verfügbaren Lademodi meldet), Ladestrom pro Ladeprofil |

Sensoren und Steuerungen werden nur für die Daten und Fernbedienungen angelegt, die dein
Fahrzeug tatsächlich meldet. Die Entitätenliste passt sich also an dein Auto an (Elektro, Plug-in-Hybrid
oder Verbrenner).

In den Optionen der Integration lässt sich ein **Nur-Lese-Modus** aktivieren, der alle
Fernsteuerungen deaktiviert und alle Sensoren aktiv lässt.

### Was die öffentliche API nicht bietet

Die Integration nutzt ausschließlich die öffentliche MyŠkoda-API. Folgende Funktionen sind daher
nicht möglich, weil die öffentliche API dafür keinen Endpunkt hat: Ver-/Entriegeln, Hupen &
Blinken, ein echter Wake-up-Aufruf (der Button „Fahrzeug aufwecken" ist nur ein Umweg, siehe unten), Scheibenheizung, Batterieschonmodus,
Außentemperatur und Softwareversion. Der maximale Ladestrom lässt sich nur pro Ladeprofil ändern (siehe unten), nicht als allgemeine Einstellung. Die Verriegelung ist ein reiner `binary_sensor`.

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

Die API lässt einen Teil der Daten weg, wenn sie ihn gerade nicht abrufen kann (gemeldet als
`<TEIL>_UNAVAILABLE`, sichtbar in den Attributen des API-Status-Sensors). Für einen solchen Teil behält die
Integration die zuletzt bekannten Daten mit ihrem alten Zeitstempel, statt sie zu verwerfen: Sonst würden die
Entitäten dieses Teils nach einem Neustart von Home Assistant im ungünstigen Moment fehlen. Nicht unterstützte
oder deaktivierte Teile werden nicht aufgefüllt.

### Ladeprofile

Ein Ladeprofil ist ein gespeicherter Ladestandort der MyŠkoda-App. Bei Fahrzeugen, die die Operation
`updateChargingProfile` nennen und mindestens ein Profil melden, bekommt jedes Profil drei Steuerungen mit
dem Namen des Profils: **Ladestrom** (`MAXIMUM` oder `REDUCED`, die „Strombegrenzung“ der App), **Ladeziel** (50 bis 100 %) und
**Stecker nach dem Laden entriegeln**, dazu die **minimale Ladegrenze** (darunter lädt das Fahrzeug sofort) und,
wenn das Fahrzeug es meldet, ein Schalter zum Aktivieren. Ein Fahrzeug übernimmt ein Profil als Ganzes, deshalb holt die Integration das
Profil unmittelbar vor dem Senden neu und ändert nur die eine Einstellung; Timer und bevorzugte Ladezeiten
bleiben unverändert. Eine Änderung kostet zwei Anfragen des Kontingents plus das Nachladen. Nicht erprobt.

**Wann die Profile in Home Assistant erscheinen**

- Ein Profil erscheint erst, wenn das **Fahrzeug es den Škoda-Servern gemeldet** hat. Nach dem Anlegen in der
  App braucht das Fahrzeug eventuell einen Moment oder einen Anstoß: **Fahrzeug aufwecken** drücken, danach
  **API jetzt abrufen**. Der Sensor **Ladestandort** (Attribut `profiles`) listet, was die API meldet; solange
  die Liste leer ist, gibt es nichts anzuzeigen. Ein Fahrzeug ohne gespeicherte Ladestandorte hat keine Profile
  und deshalb keine dieser Entitäten.
- Die Entitäten eines Profils werden beim Einrichten der Integration angelegt, deshalb **lädt sich die
  Integration selbst neu**, wenn sich die Profile eines Fahrzeugs ändern: ein Profil wurde hinzugefügt,
  gelöscht oder umbenannt (die Namen der Entitäten werden beim Einrichten übernommen). Eine Änderung muss in
  **zwei Abrufen hintereinander** auftauchen (ein Löschen in drei), damit eine kurz falsche Antwort kein Neuladen
  auslöst; bei normalem Abfrageintervall dauert das 10 bis 30 Minuten. Beobachtet werden nur Fahrzeuge, die
  `updateChargingProfile` nennen. Du kannst auch von Hand neu laden (Einstellungen > Geräte & Dienste > Škoda
  API Connect > die drei Punkte > Neu laden).

**Wenn ein Profil im Fahrzeug oder in der App gelöscht wird**

- Seine Entitäten werden **nicht verfügbar**, sobald das Fahrzeug das Profil nicht mehr meldet. An ein
  gelöschtes Profil wird nichts gesendet: Die Aktion `update_charging_profile` lehnt es ab („The vehicle does
  not report this charging profile (any more)“), bevor sie etwas schreibt.
- Ein Löschen muss in **drei Abrufen hintereinander** auftauchen. Dann entfernt die Integration die Entitäten des
  gelöschten Profils aus Home Assistant und lädt sich selbst neu. Das Entfernen ist eine Option (**Konfigurieren** >
  **Entitäten gelöschter Ladeprofile entfernen**, standardmäßig an, nur bei Fahrzeugen mit Ladeprofilen sichtbar); ist
  sie aus, bleiben die Entitäten als nicht verfügbare Entitäten stehen, die du von Hand löschst, und das Neuladen
  geschieht nach zwei Abrufen. Das geschieht nur, solange das Fahrzeug
  `updateChargingProfile` noch nennt, damit ein Fahrzeug, dessen Operationen kurz fehlen, seine Entitäten nicht
  verliert. Hast du Name oder Bereich einer solchen Entität geändert, ist das damit weg.
- Legst du danach ein neues Profil an, kann es die ID des gelöschten bekommen; es bekommt dann frische
  Entitäten mit denselben IDs.

Timer und bevorzugte Ladezeiten sind keine Entitäten (ein Profil hat bis zu 4 bevorzugte Ladezeiten und 3
Timer). Der Sensor **Ladestandort** zeigt die des Profils, in dem das Fahrzeug steht, als Attribute, und die
Aktion `skoda_api_connect.update_charging_profile` ändert beliebige Einstellungen, bevorzugte Ladezeiten und
Timer eines Profils: Als Ziel eine Entität des Profils wählen und nur angeben, was sich ändern soll. Ein Timer (die App
nennt sie „Abfahrtszeiten“) oder eine bevorzugte Ladezeit wird über ihre `number` im Profil benannt (die erste ist 1)
oder über die `id`, die die API meldet; diese IDs zählen über alle Profile hinweg, das zweite Profil eines
Fahrzeugs kann also bei 5 beginnen (siehe das Beispiel in der englischen README).

### Standheizung

Fahrzeuge mit Standheizung (das Fahrzeug nennt `startAuxiliaryHeating` und meldet ihren Zustand) bekommen
eine `climate`-Entität **Standheizung** (aus, Heizen, nur Lüften für die Belüftung) und eine Zahl
**Standheizung: Laufzeit** (10 bis 60 Minuten, Standard 30). Fahrzeuge ohne Standheizung bekommen beides nicht.

Die API startet die Heizung nur mit der **S-PIN** deines MyŠkoda-Kontos. Trage sie unter **Konfigurieren**
ein (das Feld erscheint nur, wenn ein Fahrzeug eine Standheizung hat). Sie wird wie der API-Schlüssel in
Home Assistant gespeichert, in der Diagnose geschwärzt und nie protokolliert. Ohne sie wird das Starten
abgelehnt, bevor etwas gesendet wird. Eine falsche S-PIN kann die S-PIN sperren, prüfe sie deshalb zuerst in
der App. Die Zieltemperatur wird bei jedem Start mitgesendet. Nicht erprobt.

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
sich meist innerhalb einer Minute. Ein Fahrzeug ohne Lademodus (etwa ein Verbrenner) bekommt stattdessen
einen Stop-Befehl, und zwar für die erste Funktion aus Klimaanlage, Standheizung und aktiver Belüftung,
die es als Operation nennt und die nicht läuft; eine laufende Funktion wird nie gestoppt. Das ist nicht
erprobt: Nur das erneute Senden des Lademodus bringt nachweislich ein Fahrzeug zum Melden. Die Zahl **Ladendes Fahrzeug wecken nach (0 = aus)** macht das
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
weniger als 6 Anfragen des Stundenkontingents übrig sind, und wenn es keinen Befehl zum Aufwecken gibt:
kein bekannter Lademodus und keine Klimaanlage, Standheizung oder Belüftung, die das Fahrzeug nennt und
die nicht läuft), wird der Alarm trotzdem gesendet und endet mit „Not confirmed: last
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
