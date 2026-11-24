# Changelog

[🇬🇧 English](CHANGELOG.md) | [🇩🇪 Deutsch](CHANGELOG.de.md) | [🇳🇱 Nederlands](CHANGELOG.nl.md)

Alle relevanten Änderungen dieser Integration werden hier dokumentiert. Das Format folgt
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.5.11]

### Fixed

- Einige optionale Sensoren, Binärsensoren und Bedienelemente - **Zieltemperatur erreicht um** (Klima und Standheizung), **Ziel Batterieschonung**, **schonendes Laden** und **Lademodus** - wurden nur einmal geprüft, beim Einrichten oder Neuladen der Integration. Meldete das Fahrzeug das zugrunde liegende Feld genau zu diesem Zeitpunkt nicht (z. B. weil die Klimatisierung aus war oder das Fahrzeug eine Ladeeinstellung kurzzeitig nicht meldete), wurde die Entität nie angelegt und blieb für immer nicht verfügbar, selbst wenn das Fahrzeug das Feld später wieder meldete. Diese Entitäten werden jetzt angelegt, sobald das Fahrzeug das Feld zu melden beginnt, ohne dass ein Neuladen nötig ist.

## [0.5.10]

### Added

- Ein neuer Sensor **"Standheizung: Laufzeit (Fahrzeug)"** zeigt `durationInSeconds`, die Zeit, die die Standheizung nach dem Start laufen soll, wie vom Fahrzeug gemeldet. Beim Starten wird diese Laufzeit jetzt außerdem sofort als erwarteter Wert an diesen Sensor gesendet (aus der Zahl "Standheizung: Laufzeit"), genauso wie es der Modus schon tat, statt auf die Meldung des Fahrzeugs zu warten.

## [0.5.9]

### Fixed

- Der **Parkalarm** sendet keine kritische, "Nicht stören" umgehende Push-Benachrichtigung mehr, wenn das Fahrzeug seinen Verriegelungsstatus als `UNKNOWN` meldet, während es geparkt und ansonsten unberührt ist - manche Fahrzeuge senden eine solche Meldung im Tiefschlaf (Issue #41). Eine frische Meldung mit nur unbekannten Verriegelungsfeldern löst jetzt dasselbe einmalige Aufwecken aus wie eine zu alte Meldung; der Alarm, einmal gesendet, ist dann eine normale Push-Benachrichtigung, die sagt, dass der Verriegelungsstatus unbekannt ist, statt eine, die eine tatsächlich ungesicherte Meldung behauptet.

## [0.5.8]

### Changed

- Jedes Release enthält die Integration jetzt als `skoda_api_connect.zip`, die HACS installiert. HACS kann dadurch die Zahl der Downloads anzeigen (gezählt erst ab diesem Release). An der Integration selbst ändert sich nichts.

## [0.5.7]

### Fixed

- Die **Standheizung** bietet den Modus "nur Lüfter" (Belüftung) nur an, wenn das Fahrzeug einen Startmodus meldet (oder gerade belüftet). Ein Fahrzeug ohne diesen kann nicht zwischen Heizen und Belüften wählen: Der Benzin-Octavia aus Issue #32 lehnte `VENTILATION` ab, und seine MyŠkoda-App bietet nur An und Aus. Heizen funktioniert dort seit 0.5.6.

### Known risk

- Ein Fahrzeug, das belüften kann, aber keinen Startmodus meldet, verliert den Modus "nur Lüfter". Die API dokumentiert den Startmodus als Unterscheidungsmerkmal, und bisher wurde kein Fahrzeug gemeldet, bei dem Belüftung funktioniert. Falls deins eines ist, bitte ein Issue öffnen.

## [0.5.6]

### Fixed

- Die **Standheizung** sendet den Startmodus `HEATING` nur, wenn das Fahrzeug einen Startmodus meldet; die Belüftung sendet weiterhin immer `VENTILATION`. Der Benzin-Octavia aus Issue #32 meldet keinen, akzeptierte den Start ohne Fehler, heizte aber nicht. Die API verlangt nur die S-PIN.
- Die **S-PIN** wird beim Speichern der Optionen geprüft: Sie muss vier Ziffern haben, Leerzeichen davor und danach werden entfernt. Das Passwortfeld verdeckt Tippfehler, und eine falsche S-PIN wird erst später vom Fahrzeug abgelehnt, ohne Fehler in Home Assistant. Eine mit Leerzeichen gespeicherte S-PIN wird auch ohne sie gesendet.

## [0.5.5]

### Fixed

- Die Standheizung sendet beim Start keine erfundene Zieltemperatur (21 °C) mehr: Sie wird nur gesendet, wenn das Fahrzeug eine meldet oder du eine einstellst. Ein Benzin-Octavia, der keine meldet, beantwortete den Start mit HTTP 500 (Issue #32; ob das die Ursache ist, ist noch nicht bestätigt).
- Die VIN wird auch im Antworttext eines Fehlers, der ins Log geschrieben wird, gekürzt.

## [0.5.4]

### Changed

- Jede Fehlerantwort der API wird jetzt als Warnung ins Log geschrieben: HTTP-Status, Problemtyp, der Antworttext (auf 500 Zeichen gekürzt) und die Trace-ID; die Anfrage selbst (mit der S-PIN) wird nie protokolliert, und die VIN wird gekürzt. Bei Serverfehlern (5xx) zeigt die Fehlermeldung außerdem die Trace-ID, mit der Škoda die fehlgeschlagene Anfrage finden kann (angeregt durch den Bericht in Issue #32).

## [0.5.3]

### Fixed

- Das Icon des Sensors "API-Schlüssel läuft ab" (`mdi:key-clock`) existiert nicht, daher wurde kein Icon angezeigt; es wird jetzt `mdi:key-alert` verwendet.
- Ein unerwarteter Fehler beim Aufwecken des Fahrzeugs für den Parkalarm wird jetzt protokolliert statt als unbehandelter Task-Fehler verworfen zu werden; der Alarm folgt trotzdem beim nächsten Abruf oder nach der Wartezeit.

### Changed

- Die pytest-Suite läuft jetzt im CI-Workflow (mehrere Tests wurden dabei korrigiert, die nie gelaufen waren).

## [0.5.2]

### Added

- Sensor "API-Schlüssel läuft ab" (Diagnose, Datum und Uhrzeit): das Ablaufdatum des API-Schlüssels, aus dem Header `x-api-key-expires-at` der API-Antworten. Damit lässt sich in einer Automatisierung vor dem Ablauf des Schlüssels warnen (angeregt in Issue #26).

### Changed

- README: ein Hinweis, dass die Programmierung der Integration mit Unterstützung von Claude (einem KI-Assistenten von Anthropic) erfolgte.
- Der API-Schlüssel wird in der MyŠkoda-App erstellt (Profil > Smart Home > Schlüssel > Schlüssel erstellen): README und die Texte der Einrichtungs-, Reauthentifizierungs- und Neukonfigurationsdialoge nennen diesen Weg neben dem Link `go.skoda.eu/api-keys`, der nur auf einem Smartphone mit der App funktioniert (der Hinweis auf einen QR-Code ist entfallen).

## [0.5.1]

### Added

- Alle noch fehlenden Werte, die die API meldet, jeweils nur wenn das Fahrzeug sie meldet:
  - Sensoren: Ladeart, voll geladen um (nur beim Laden), Ziel Batterieschonung, maximaler Ladestrom des Fahrzeugs (Text und Ampere), Zieltemperatur erreicht um (Klimaanlage und Standheizung), Fahrzeugtyp und das Kennzeichen (standardmäßig aus, in der Diagnose geschwärzt);
  - Binärsensoren: schonendes Laden, Stecker entriegeln nach dem Laden (die Einstellung des Fahrzeugs), Front- und Heckscheibenheizung, Scheibenheizung aktiviert, Klima beim Entriegeln, Klima ohne externe Stromversorgung, Schiebedach;
  - das Vorschaubild des Fahrzeugs ist das Bild des Parkpositions-Trackers.
  Sie lassen sich über die öffentliche API nicht ändern.

## [0.5.0]

### Added

- Ladeprofile: Für Fahrzeuge, die `updateChargingProfile` als Operation melden und Profile melden (die gespeicherten Ladestandorte der MyŠkoda-App), bekommt jedes Profil ein Auswahlfeld **Ladestrom** (`MAXIMUM`/`REDUCED`), eine Zahl **Ladeziel** und einen Schalter **Stecker nach dem Laden entriegeln**. Das Profil wird unmittelbar vor dem Senden erneut abgerufen, wobei nur die eine Einstellung geändert wird, weil das Fahrzeug ein Profil als Ganzes anwendet. Getestet an einem Enyaq (nicht die einmaligen Timer).
- Standheizung: Fahrzeuge, die `startAuxiliaryHeating` melden und die Funktion unterstützen, bekommen eine `climate`-Entität **Standheizung** (aus, heizen, nur Lüfter) und eine Zahl **Standheizung: Laufzeit**. Zum Starten wird die S-PIN des MyŠkoda-Kontos benötigt, eingetragen in den Optionen (das Feld erscheint nur, wenn ein Fahrzeug eine Standheizung hat); sie wird in der Diagnose geschwärzt. Das Fahrzeug wird während der Heizung schneller abgefragt, und ein Stopp davon wird genutzt, um Fahrzeuge ohne Lademodus aufzuwecken. Ungetestet.
- Blueprint `blueprints/automation/skoda_api_connect/update_charging_profile.yaml`: ändert ein Ladeprofil, wenn dein Trigger auslöst, mit Schutzmaßnahmen (genug API-Anfragen übrig, keine noch ausstehende Änderung, API-Status, eine Pause nach jeder Änderung).
- Ladeprofile: die **minimale Ladegrenze** (das "Mindestladelimit" der App) als Zahl und, bei Fahrzeugen, die es melden, ein Schalter zum Aktivieren. Der Ladestandort-Sensor listet die bevorzugten Ladezeiten und Timer des aktuellen Profils als Attribute, und die neue Aktion `skoda_api_connect.update_charging_profile` ändert jede Einstellung, bevorzugte Ladezeit und jeden Timer eines Profils (benannt über ihre `number` im Profil oder über die `id` der API, die profilübergreifend zählt) in einer Anfrage (zwei Anfragen des Kontingents). Ungetestet.
- Der Ladestandort-Sensor zeigt die ID, das Ladeziel und die nächste Ladezeit des aktuellen Ladeprofils sowie die Liste aller Profile als Attribute.
- Die Integration lädt sich selbst neu, wenn sich die Ladeprofile eines Fahrzeugs ändern (ein Profil wurde hinzugefügt, gelöscht oder umbenannt), weil die Entitäten eines Profils und ihre Namen beim Einrichten angelegt werden. Eine Änderung muss sich in zwei Abrufen in Folge zeigen (eine Löschung in drei). Die Entitäten eines gelöschten Profils werden ebenfalls entfernt, solange das Fahrzeug `updateChargingProfile` noch meldet; das ist die Option **Entitäten gelöschter Ladeprofile entfernen** (standardmäßig an, sichtbar bei Fahrzeugen mit Ladeprofilen). Ungetestet.

### Changed

- README: wo der API-Schlüssel in der MyŠkoda-App erstellt wird (Profil > Smart Home > Schlüssel > Schlüssel erstellen, mit Screenshots) und ein Abschnitt zur Fehlerbehebung.
- Die Diagnose schwärzt die Namen von Ladeprofilen, die meist Adressen sind.

### Fixed

- Ein Teil der Fahrzeugdaten, den die API als `<TEIL>_UNAVAILABLE` meldet (gerade nicht abrufbar), wird jetzt mit den zuletzt bekannten Daten gefüllt, vom vorherigen Abruf oder beim Start aus der gespeicherten Kopie. Vorher wurden die Entitäten dieses Teils (zum Beispiel das Klima und die Zieltemperatur) beim Start von Home Assistant nicht angelegt, wenn die API diesen Teil gerade ausließ, und blieben nicht verfügbar, bis die Integration neu geladen wurde. Der alte Zeitstempel bleibt sichtbar. Nicht unterstützte oder deaktivierte Teile werden nicht aufgefüllt.

## [0.4.5]

### Added

- Ein Fahrzeug ohne Lademodus (etwa ein Verbrenner) kann jetzt auch geweckt werden: Das Aufwecken sendet einen Stopp-Befehl für die erste Funktion aus Klimaanlage, Standheizung und aktiver Belüftung, die das Fahrzeug als Operation meldet und die nicht läuft. Eine laufende Funktion wird nie gestoppt, und bei einem Fahrzeug, das seine Operationen nicht meldet, wird nicht geraten. Fahrzeuge mit Lademodus werden wie bisher geweckt. Dies ist ungetestet: Bisher ist nur bekannt, dass das erneute Senden des Lademodus ein Fahrzeug zum Melden bringt. Der Button "Fahrzeug aufwecken" erscheint jetzt auch für diese Fahrzeuge, und der Parkalarm kann ihn nutzen.

## [0.4.4]

### Added

- Der Parkalarm schreibt ins Logbuch des Sensors **Geparkt, nicht gesichert**: jedes Aufwecken zur Bestätigung eines Vorfalls (oder warum es entfiel oder fehlschlug) und jeden gesendeten Alarm, sodass man danach nachvollziehen kann, warum ein Alarm kam, wann er kam. Die Logmeldungen zum Aufwecken nennen jetzt das Fahrzeug.

### Fixed

- Parkalarm wurde nie gesendet, wenn der Vorfall auf einer älteren Meldung begann und das Fahrzeug nicht bestätigt werden konnte. Das Aufwecken, das eine frische Meldung bringen sollte, braucht einen bekannten Lademodus und schlug deshalb immer fehl bei Fahrzeugen ohne einen (wie den meisten Verbrennern), und es entfiel im Nur-Lesen-Modus, während einer Ratenlimit-Pause und bei wenig verbleibendem Kontingent. Der Alarm wartete dann, bis das Fahrzeug von sich aus meldete, was ein geparktes Fahrzeug stundenlang nicht tun kann, und zeigte diese Meldung dann Sicherheit, wurde nie ein Alarm gesendet. Jetzt wird der Alarm trotzdem gesendet, endend mit "Nicht bestätigt: letzte Meldung um …", wenn das Aufwecken entfällt oder fehlschlägt oder wenn das Fahrzeug nicht innerhalb von 5 Minuten danach meldet. Ein Aufwecken zählt erst als erledigt, wenn das Fahrzeug es angenommen hat.

## [0.4.3]

### Added

- Während die Klimaanlage oder die Belüftung läuft, wird das Fahrzeug im Ladeintervall abgefragt (wie beim Laden). Ein Ausschalten an anderer Stelle, zum Beispiel in der App, zeigt sich dadurch schneller. Es kehrt zum normalen Intervall zurück, sobald ein Abruf das Klima als aus zeigt.
- `brand/icon@2x.png` (512 x 512) neben `brand/icon.png`, die hochauflösende Version, die Home Assistant auf Bildschirmen mit hoher Pixeldichte verwendet.

### Changed

- Das Lademodus-Auswahlfeld verwendet das Icon `mdi:ev-plug-ccs2` (CCS) statt `mdi:ev-plug-type2`.

### Fixed

- Die Klimaanlage bot den Belüftungsmodus (`fan_only`) für jedes Fahrzeug an, sodass die Auswahl bei einem Fahrzeug ohne aktive Belüftung (wie einem Enyaq) in einem Fehler der API endete. Der Modus wird jetzt nur angeboten, wenn das Fahrzeug `startActiveVentilation` unter seinen Operationen meldet.

## [0.4.2]

### Fixed

- Parkalarm wurde für ein gerade erst geparktes Fahrzeug nie gesendet: Es meldet einmal und schläft dann, und diese Meldung war älter als der Abruf, der den Vorfall eröffnete, sodass der Alarm weiter auf eine neuere wartete (und das Aufwecken oft entfällt, z. B. wenn das Abfragen den Großteil des Kontingents verbraucht). Meldete das Fahrzeug das Problem innerhalb eines Abrufintervalls vor diesem Abruf, beginnt der Vorfall jetzt bei dieser Meldung, der Alarm wird darauf gesendet, und die Wartezeit zählt ab ihr. Ältere Meldungen wecken das Fahrzeug weiterhin zuerst.

## [0.4.1]

### Changed

- Icons für Entitäten, die keines hatten: die Ladegrenze (Sensor und Zahl), der Kraftstoffstand, der Lademodus und der Lade-Schalter. Der API-Status-Sensor verwendet jetzt `mdi:api`, sodass er sich das Icon nicht mehr mit "Letzte Fahrzeugdaten" teilt.

## [0.4.0]

### Added

- Parkalarm: eine kritische Benachrichtigung, wenn ein Fahrzeug geparkt, aber nicht gesichert ist (zuverlässiger Verriegelungsstatus nicht `LOCKED`, Türen nicht `CLOSED`, Türen verriegelt nicht `YES`, verriegelt nicht `YES`, oder Fenster nicht `CLOSED`; unbekannte Werte zählen als nicht gesichert, Fenster `UNSUPPORTED` wird übersprungen, und der zuverlässige Verriegelungsstatus wird übersprungen, wenn das Fahrzeug ihn nicht meldet). Die Notify-Dienste, die ihn erhalten, werden in den Optionen gewählt (mehrere sind möglich); Ziele der Companion-App erhalten ihn als kritischen Alarm. Ein Alarm pro Vorfall, auch über Neustarts und Neuladen hinweg. Er wird nur auf Basis von Daten gesendet, die das Fahrzeug nach Beginn des Vorfalls gemeldet hat, sodass eine alte Momentaufnahme keinen Fehlalarm auslösen kann; fehlt am Ende der Wartezeit eine solche Meldung, wird das Fahrzeug einmal pro Vorfall geweckt (zwei Anfragen, entfällt im Nur-Lesen-Modus, während einer Ratenlimit-Pause oder bei weniger als 6 verbleibenden Anfragen). Keine weiteren API-Anfragen.
- Zahl "Parkalarm-Wartezeit" pro Fahrzeug (Regler, 0-30 Minuten, Standard 5): wie lange ein Fahrzeug ungesichert bleiben darf, bevor der Alarm gesendet wird.
- Binärsensor "Geparkt, nicht gesichert" mit den fehlgeschlagenen Prüfungen im Attribut `reasons`.
- Sensoren "Türen verriegelt", "Zuverlässiger Verriegelungsstatus" und "Parkstatus", die die von der API gemeldeten Werte zeigen.

### Changed

- Die Diagnose schwärzt die Benachrichtigungsziele des Parkalarms.

## [0.3.1]

### Added

- Sensor "Aktuelles Abrufintervall" (Diagnose): das Intervall in Minuten, mit dem das Fahrzeug gerade abgefragt wird (normales oder Ladeintervall, Attribut `mode`). Er folgt einer geänderten Einstellung sofort.
- Nach einem angenommenen Befehl zeigen die Klimaanlage, der Lade-Schalter, die Ladegrenze und der Lademodus sofort den erwarteten Zustand (Attribut `pending: true`), statt auf das Fahrzeug zu warten. Er wird ersetzt, wenn das Fahrzeug neuere Daten dieses Abschnitts meldet, und entfällt nach 3 Minuten (Klimaanlage) oder 5 Minuten (die anderen) ohne Meldung. Ein abgelehnter Befehl ändert nichts. Keine zusätzlichen Anfragen.

### Changed

- Die Sensoren "Letzter Abruf" wurden zu "Letzter API-Abruf" und "Rate-Limit bis" zu "API-Rate-Limit bis" umbenannt (Anzeigenamen und Übersetzungen; Entity-IDs bestehender Installationen bleiben gleich).

## [0.3.0]

### Added

- Sensor "Letzte Fahrzeugdaten": wann das Fahrzeug selbst zuletzt Daten an die Škoda-Server gemeldet hat (neuester `carCapturedTimestamp`), mit dem Zeitstempel jedes Abschnitts als Attribute. Anders als "Letzter API-Abruf" zeigt er, wann die Verbindung zwischen Fahrzeug und Server unterbrochen war.
- Button "Fahrzeug aufwecken": Die API hat keinen Wake-up-Aufruf, daher sendet sie erneut den aktuellen Lademodus (ein Befehl, der nichts ändert, aber das Fahrzeug erreichen muss), was ein schlafendes Fahrzeug zum Melden bringt. Kostet zwei Anfragen des API-Kontingents.
- Zahl "Ladendes Fahrzeug wecken nach (0 = aus)" (Konfigurationskategorie, standardmäßig aus): Wenn ein ladendes Fahrzeug so viele Minuten keine Daten gemeldet hat (Schritte von 5 Minuten, Minimum 10), wird es auf dieselbe Weise geweckt. Entfällt während einer Ratenlimit-Pause und wenn weniger als 6 Anfragen des Stundenkontingents übrig sind; nie öfter als das eingestellte Intervall.
- Spanische und luxemburgische Übersetzungen (Dank an janreimen), einschließlich der Aufweck-Entitäten.

### Fixed

- Die luxemburgische Übersetzung heißt jetzt `lb.json`; Home Assistant verwendet den Sprachcode `lb`, daher wurde `lu.json` nie geladen.

## [0.2.1]

### Fixed

- Die Diagnose enthält keine VINs mehr (die Abfrageoptionen pro Fahrzeug werden jetzt als `vehicle_1`, `vehicle_2`, ... aufgeführt) und auch nicht mehr den Fahrzeugnamen.

## [0.2.0]

### Added

- Binärsensor "Ladekabel-Verriegelung" für das neue Feld `plugLockState` der API 1.1.0 (an = entriegelt).

## [0.1.0]

### Added

- Erstveröffentlichung.
