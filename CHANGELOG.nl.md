# Changelog

[🇬🇧 English](CHANGELOG.md) | [🇳🇱 Nederlands](CHANGELOG.nl.md)

Alle relevante wijzigingen aan deze integratie staan hier gedocumenteerd. De indeling volgt
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.4.4]

### Toegevoegd

- Het parkeeralarm schrijft in het logboek van de sensor **Geparkeerd, niet beveiligd**: elke wekpoging om een incident te bevestigen (of waarom die werd overgeslagen of mislukte) en elke verstuurde melding, zodat je achteraf ziet waarom een melding kwam wanneer ze kwam. De logberichten over het wekken noemen nu het voertuig.

### Opgelost

- Parkeeralarm werd nooit verstuurd als het incident op een oudere melding begon en het voertuig niet bevestigd kon worden. Het wekken dat een verse melding moet opleveren heeft een bekende laadmodus nodig, en mislukte dus altijd bij voertuigen zonder (zoals de meeste verbrandingsmotoren); in alleen-lezen-modus, tijdens een rate-limit-pauze en bij weinig quotum werd het overgeslagen. De melding wachtte dan tot het voertuig zich uit zichzelf meldde, wat een geparkeerd voertuig urenlang niet kan doen, en toonde die melding het voertuig beveiligd, dan werd er nooit een alarm verstuurd. Nu wordt het alarm toch verstuurd, eindigend met "Not confirmed: last report at …", als het wekken wordt overgeslagen of mislukt of als het voertuig zich niet binnen 5 minuten daarna meldt. Een wekpoging telt pas als gedaan zodra het voertuig die heeft geaccepteerd.

## [0.4.3]

### Toegevoegd

- Zolang de airco of de ventilatie draait, wordt het voertuig met zijn laadinterval gepolld (zoals tijdens het laden). Uitschakelen elders, bijvoorbeeld in de app, wordt zo eerder zichtbaar. Zodra een poll de klimaatregeling uit toont, geldt weer het normale interval.
- `brand/icon@2x.png` (512 x 512) naast `brand/icon.png`, de versie met hoge resolutie die Home Assistant op high-DPI-schermen gebruikt.

### Gewijzigd

- De laadmodus-selectie gebruikt het pictogram `mdi:ev-plug-ccs2` (CCS) in plaats van `mdi:ev-plug-type2`.

### Opgelost

- De airco bood de ventilatiemodus (`fan_only`) voor elk voertuig aan, zodat kiezen op een voertuig zonder actieve ventilatie (zoals een Enyaq) met een fout van de API eindigde. De modus wordt nu alleen aangeboden als het voertuig `startActiveVentilation` bij zijn operaties vermeldt.

## [0.4.2]

### Opgelost

- Parkeeralarm werd nooit verstuurd voor een net geparkeerd voertuig: het meldt zich één keer en slaapt dan, en die melding was ouder dan de poll die het incident opende, dus de melding bleef wachten op een nieuwere (en het wekken wordt vaak overgeslagen, bijv. als het pollen het grootste deel van het quotum gebruikt). Meldde het voertuig het probleem binnen één pollinginterval vóór die poll, dan begint het incident nu bij die melding, wordt het alarm daarop verstuurd en telt de wachttijd vanaf die melding. Oudere meldingen wekken het voertuig nog steeds eerst.

## [0.4.1]

### Gewijzigd

- Pictogrammen voor entiteiten die er geen hadden: de laadlimiet (sensor en number), het brandstofniveau, de laadmodus en de laadschakelaar. De API-statussensor gebruikt nu `mdi:api`, zodat hij zijn pictogram niet meer deelt met "Laatste voertuiggegevens".

## [0.4.0]

### Toegevoegd

- Parkeeralarm: een kritieke melding als een voertuig geparkeerd staat maar niet beveiligd is (betrouwbare vergrendelingsstatus niet `LOCKED`, deuren niet `CLOSED`, deuren vergrendeld niet `YES`, vergrendeld niet `YES` of ramen niet `CLOSED`; onbekende waarden tellen als niet beveiligd, ramen `UNSUPPORTED` wordt overgeslagen, en de betrouwbare vergrendelingsstatus wordt overgeslagen als het voertuig hem niet meldt). De notify-services die hem krijgen kies je in de opties (meerdere mogelijk); Companion-app-ontvangers krijgen hem als kritieke melding. Eén melding per incident, ook over herstarts en herladen heen. Hij wordt alleen verstuurd op gegevens die het voertuig na het begin van het incident meldde, zodat een oude momentopname geen vals alarm geeft; is er aan het eind van de wachttijd geen zulke melding, dan wordt het voertuig één keer per incident gewekt (twee verzoeken, overgeslagen in alleen-lezen-modus, tijdens een rate-limit-pauze of met minder dan 6 resterende verzoeken). Verder geen API-verzoeken.
- Number "Wachttijd parkeeralarm" per voertuig (schuifregelaar, 0-30 minuten, standaard 5): hoe lang een voertuig onbeveiligd mag blijven voordat de melding wordt verstuurd.
- Binaire sensor "Geparkeerd, niet beveiligd" met de mislukte controles in het attribuut `reasons`.
- Sensors "Deuren vergrendeld", "Betrouwbare vergrendelingsstatus" en "Parkeerstatus", met de waarden zoals de API ze meldt.

### Gewijzigd

- Diagnostics verbergen de ontvangers van het parkeeralarm.

## [0.3.1]

### Toegevoegd

- Sensor "Huidig pollinginterval" (diagnostisch): het interval in minuten waarmee het voertuig nu wordt gepolld (normaal of laadinterval, attribuut `mode`). Volgt een gewijzigde instelling direct.
- Na een geaccepteerd commando tonen de airco, de laadschakelaar, de laadlimiet en de laadmodus direct de verwachte toestand (attribuut `pending: true`) in plaats van op het voertuig te wachten. Die wordt vervangen zodra het voertuig nieuwere gegevens van dat onderdeel meldt en na 3 minuten (airco) of 5 minuten (overige) verworpen zonder melding. Een geweigerd commando verandert niets. Geen extra verzoeken.

### Gewijzigd

- De sensoren "Laatste poll" en "Rate limit tot" heten nu "Laatste API-poll" en "API-rate limit tot" (weergavenamen en vertalingen; entiteits-ID's van bestaande installaties blijven gelijk).

## [0.3.0]

### Toegevoegd

- Sensor "Laatste voertuiggegevens": wanneer het voertuig zelf voor het laatst gegevens naar de Škoda-servers stuurde (nieuwste `carCapturedTimestamp`), met de tijdstempel per onderdeel als attributen. In tegenstelling tot "Laatste poll" laat dit zien wanneer de verbinding tussen auto en servers onderbroken was.
- Knop "Voertuig wakker maken": de API heeft geen wake-up-aanroep, dus de knop stuurt de huidige laadmodus opnieuw (een commando dat niets verandert maar het voertuig moet bereiken), waardoor een slapend voertuig zich meldt. Kost twee verzoeken van het API-quotum.
- Number "Ladend voertuig wekken na (0 = uit)" (configuratiecategorie, standaard uit): als een voertuig laadt en zoveel minuten (stappen van 5, minimaal 10) geen gegevens heeft gemeld, wordt het op dezelfde manier gewekt. Overgeslagen tijdens een rate-limitpauze en als er minder dan 6 verzoeken van het uurquotum over zijn; nooit vaker dan de ingestelde tijd.
- Spaanse en Luxemburgse vertalingen (met dank aan janreimen), inclusief de entiteiten voor het wekken.

### Opgelost

- De Luxemburgse vertaling heet nu `lb.json`; Home Assistant gebruikt de taalcode `lb`, dus `lu.json` werd nooit geladen.

## [0.2.1]

### Opgelost

- Diagnostics bevatten geen VIN's (per-voertuig pollinginstellingen staan nu als `vehicle_1`, `vehicle_2`, ...) en geen voertuignaam meer.

## [0.2.0]

### Toegevoegd

- Binaire sensor "Vergrendeling laadkabel" voor het nieuwe veld `plugLockState` van API 1.1.0 (aan = ontgrendeld).

## [0.1.0]

### Toegevoegd

- Eerste release.
