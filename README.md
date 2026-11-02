# Škoda API Connect for Home Assistant

[🇬🇧 English](README.md) | [🇩🇪 Deutsch](README.de.md) | [🇳🇱 Nederlands](README.nl.md)

A multi-language [Home Assistant](https://www.home-assistant.io/) custom integration for
Škoda vehicles, built on the official
[MyŠkoda Public API](https://public.api.connect.skoda-auto.cz/docs). It talks to the API
directly with an **API key** - no username/password and no third-party client library.

> **Unofficial project.** This integration is not affiliated with, endorsed by, or associated
> with Škoda Auto. Use at your own risk.

## Features

Built following Home Assistant's current integration best practices: a UI-only config flow,
a `DataUpdateCoordinator` for efficient polling, entity descriptions, per-entity translations,
an options flow, reauthentication support, and a diagnostics download.

| Platform | Entities |
|---|---|
| `sensor` | Battery level, charging power, charge limit (read-only), charging rate, remaining charging time, battery/total range, fuel level, AdBlue range, mileage, target temperature, address of the parking position, doors locked, reliable lock status and parking state (as reported by the API, e.g. `YES`, `TRUNK_OPENED`, `PARKED`), name of the charging location profile currently active (with its id, target charge, next charging time and the list of all profiles as attributes), API status (result of the last poll, diagnostic), last API poll (date and time of the last successful poll, diagnostic), last vehicle data (when the vehicle itself last reported data to the Škoda servers, diagnostic), API rate limit until (when the request quota is available again after a rate limit, diagnostic), API requests remaining (left of the hourly quota according to the last response, with the attributes `limit` and `reset_at`, diagnostic), current polling interval (minutes, normal or charging interval, attribute `mode`, diagnostic) |
| `binary_sensor` | Doors, windows, trunk, bonnet, lights, central locking, charging, charging cable plugged in, charging cable lock, vehicle at saved charging location, parked unsecured (see [Parking alert](#parking-alert)) |
| `device_tracker` | Parking position (shows on the Map dashboard; unknown while driving) |
| `climate` | Remote air conditioning (on/off, active ventilation if the vehicle supports it, target temperature), auxiliary heating (only for vehicles that have it, see [Auxiliary heating](#auxiliary-heating)) |
| `switch` | Start/stop charging, unlock the plug after charging per charging profile (see [Charging profiles](#charging-profiles)) |
| `button` | Poll API now (queries the MyŠkoda API for the vehicle immediately; costs one request of the API quota and is refused while the API is rate limited), Wake vehicle (see below) |
| `number` | Charge limit (target state of charge), per-vehicle polling intervals (normal / while charging), automatic wake-up of a charging vehicle, parking alert grace period, auxiliary heating duration, target charge per charging profile |
| `select` | Charge mode (only if the vehicle reports its available charge modes), charging current per charging profile |

Sensors and controls are only created for the data and remote operations your specific vehicle
reports, so the entity list adapts to your car (EV, PHEV, or combustion).

A **read-only mode** can be enabled in the integration options to disable all remote controls
while keeping all sensors active.

### What the public API does not offer

This integration uses only the public MyŠkoda API. The following are therefore not possible,
because the public API has no endpoint for them: locking/unlocking, honk & flash, a real wake-up
call (the button "Wake vehicle" is only a workaround, see below), window heating, battery care mode, outside temperature and software version. The maximum
charging current can only be changed per charging profile (see below), not as a general setting. The lock is a read-only `binary_sensor`.

## Supported languages

The integration ships translations for its config flow, options flow, and entity names in:

- English (`en`)
- Nederlands (`nl`)
- Deutsch (`de`)
- Français (`fr`)
- Čeština (`cs`)
- Slovenčina (`sk`)
- Español (`es`)
- Lëtzebuergesch (`lb`)

Home Assistant automatically picks the translation matching your instance's language setting,
falling back to English. Contributions for additional languages are welcome — add a new file
under `custom_components/skoda_api_connect/translations/`.

This documentation itself is available in [English](README.md),
[Deutsch](README.de.md) and [Nederlands](README.nl.md).

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=olafkenfenheuer&repository=Skoda-api-HA-Integration&category=integration)

1. In HACS, search for "Škoda API Connect", click **Download**, and install it.
2. Restart Home Assistant.

If it does not show up in the search (e.g. your HACS has not refreshed the default list yet, or you
want to try a pre-release), add it as a custom repository instead:

1. In HACS, go to **Integrations** → menu (⋮) → **Custom repositories**.
2. Add this repository URL (`https://github.com/olafkenfenheuer/Skoda-api-HA-Integration`) with
   category **Integration**.
3. Search for "Škoda API Connect" in HACS, click **Download**, and install it.
4. Restart Home Assistant.

### Manual

1. Download or clone this repository.
2. Copy the `custom_components/skoda_api_connect` folder into your Home Assistant
   `config/custom_components/` directory, so you end up with
   `config/custom_components/skoda_api_connect/manifest.json`.
3. Restart Home Assistant.

## Configuration

1. In the MyŠkoda app, create an API key at <https://go.skoda.eu/api-keys> and select the
   vehicle(s) it should be valid for. Keys are bound to those vehicles and expire.
2. Go to **Settings → Devices & Services → Add Integration** and search for "Škoda API Connect".
3. Enter the API key and the VIN of each vehicle (several VINs separated by commas). The API
   has no vehicle list endpoint, so the VINs have to be entered manually.
4. Home Assistant validates the key and creates one device per vehicle with all applicable
   entities.
5. After setup, open the integration's **Configure** dialog to change:
   - the polling interval (3-1440 minutes, default 10),
   - the shorter polling interval used **while charging** (default 5),
   - whether that charging interval is **also used while the cable is plugged in** (default off),
   - read-only mode,
   - the notify services that get the [parking alert](#parking-alert).

You can replace the API key (or change the VINs) at any time - before it expires, or after creating a
new one - via **Settings → Devices & Services → Škoda API Connect → ⋮ → Reconfigure**. The entry is reloaded
and keeps its entities, history and options.

When the key expires (the API reports `api-key-expired`) Home Assistant shows a
"reauthenticate" notification - create a new key and enter it to restore the connection
without losing entity history.

## Notes on the API

The integration only uses the documented endpoints under
`https://public.api.connect.skoda-auto.cz/api/v1/vehicles/{vin}` and authenticates with the
`X-API-Key` header. Data is refreshed by polling.

The API leaves out a part of the data when it cannot retrieve it right now (reported as
`<PART>_UNAVAILABLE`, shown in the attributes of the API status sensor). For such a part the integration
keeps the last known data, with its old timestamp, instead of dropping it: otherwise the entities of that part
would be missing after a Home Assistant restart that happens at the wrong moment. Unsupported or disabled
parts are not filled in.

### Charging profiles

A charging profile is a saved charging location of the MyŠkoda app. For vehicles that list the operation
`updateChargingProfile` and report at least one profile, every profile gets three controls, named after
the profile: **charging current** (`MAXIMUM` or `REDUCED`, the "current limit" of the app), **target charge**
(50 to 100 %) and **unlock plug after charging**, plus the **minimum charge** (below it the vehicle charges at once) and,
if the vehicle reports it, a switch to activate it. A vehicle applies a profile as a whole, so the integration fetches the
profile again right before it sends it, with only the one setting changed; timers and preferred charging
times stay as they are. A change costs two requests of the quota plus the follow-up refresh. Untested.

**When the profiles show up in Home Assistant**

- A profile only appears once the **vehicle has reported it** to the Škoda servers. After you create one in
  the app, the vehicle may need a moment, or a nudge: press **Wake vehicle**, then **Poll API now**. The
  sensor **Charging location** (attribute `profiles`) lists what the API reports; as long as the list is
  empty there is nothing to show. A vehicle without saved charging locations has no profiles and therefore none
  of these entities.
- The entities of a profile are created when the integration is set up, so the integration **reloads itself**
  when the profiles of a vehicle change: a profile that was added, deleted or renamed (the names of the
  entities are taken at setup). A change has to show in **two polls in a row**, so an answer that is wrong
  for a moment does not cause a reload; with the normal polling interval that takes 10 to 20 minutes. Only
  vehicles that list `updateChargingProfile` are watched. You can also reload by hand (Settings > Devices &
  services > Škoda API Connect > the three dots > Reload).

**When a profile is deleted in the vehicle or the app**

- Its entities become **unavailable** as soon as the vehicle no longer reports the profile. Nothing is sent
  to the vehicle for a profile that is gone: the action `update_charging_profile` refuses it ("The vehicle does
  not report this charging profile (any more)") before it writes anything.
- The integration reloads itself, and no entities are created for the deleted profile any more, but the old ones
  **stay in Home Assistant** as unavailable entities. They are not removed automatically, because they may
  carry your own settings (name, area, history); delete them under Settings > Devices & services >
  Entities when the profile is really gone.
- If you create a new profile afterwards it may get the id of the deleted one. Its entities are then the old
  ones again (the same ids), under the name taken at the reload.

Timers and preferred charging times are not entities (a profile has up to 4 preferred charging times and 3
timers). The sensor **Charging location** shows those of the profile the vehicle is at as attributes, and the
action `skoda_api_connect.update_charging_profile` changes any of the settings, preferred charging times and
timers of a profile: pick an entity of the profile as the target and name only what should change, for example

```yaml
action: skoda_api_connect.update_charging_profile
target:
  entity_id: select.my_car_home_charging_current
data:
  max_charging_current: REDUCED
  timers:
    - id: 1
      enabled: true
      time: "07:30"
      days: [MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY]
  preferred_charging_times:
    - id: 1
      enabled: true
      start: "22:00"
      end: "06:00"
```

### Auxiliary heating

Vehicles with an auxiliary heating (the vehicle lists `startAuxiliaryHeating` and reports its state) get a
`climate` entity **Auxiliary heating** (off, heat, fan only for ventilation), and a number **Auxiliary
heating duration** (10 to 60 minutes, default 30). Vehicles without one get neither.

The API only starts the heating with the **S-PIN** of your MyŠkoda account. Enter it under
**Configure** (the field only appears if a vehicle has an auxiliary heating). It is stored in Home Assistant
like the API key, redacted in the diagnostics and never logged. Without it, starting is refused before
anything is sent. A wrong S-PIN can lock the S-PIN, so check it in the app first. The target temperature is
sent with each start. Untested.

### Immediate feedback after commands

A command is only *accepted* by the API (HTTP 202); the vehicle may execute it much later, or never if
it is asleep. So that the interface does not look unchanged in the meantime, the air conditioning, the
charging switch, the charge limit and the charge mode show the expected state right after an accepted
command, with the attribute `pending: true`. It is replaced as soon as the vehicle reports newer data
of that section (what the vehicle says wins, even if it contradicts the command), and dropped after
3 minutes (air conditioning) or 5 minutes (the others) if the vehicle does not report. A command the
API rejects changes nothing. This costs no additional requests.

### Waking a vehicle

The vehicle only reports to the Škoda servers from time to time. While charging it can stay silent for
an hour, and the polls then return old values although they succeed. The sensor **Last vehicle data**
shows when the car last reported; **Last poll** only shows when the integration last fetched data.

The API has no wake-up call. The button **Wake vehicle** therefore re-sends the current charge mode,
a command that changes nothing but has to reach the vehicle; the vehicle usually reports within a minute.
A vehicle without a charge mode (such as a combustion vehicle) gets a stop command instead, for the
first of air conditioning, auxiliary heating and active ventilation that it lists as an operation and
that is not running; a running function is never stopped. This is untested: only re-sending the charge
mode is known to make a vehicle report. The number **Wake charging vehicle after (0 = off)** does this automatically while a vehicle is charging
and has not reported for the given number of minutes (off by default, minimum 10). Each wake-up uses two
requests of the quota; it is skipped during a rate limit pause and when fewer than 6 requests are left.
Both are unavailable in read-only mode.

### Per-vehicle polling intervals

Every vehicle has two `number` entities (configuration category): **Polling interval** and
**Polling interval while charging**. They override the defaults from the integration options for
that vehicle, apply immediately without reloading, and can be set from automations
(`number.set_value`). A vehicle is polled at its charging interval as soon as the last fetched
state is `CHARGING`, or the air conditioning or ventilation is running (so that switching it off elsewhere shows up sooner). With the option "Use the charging interval while the cable is plugged in" it
is also used as soon as the charging cable is plugged in - useful to catch the start of a
timer-controlled charge, but the faster interval then stays active for as long as the car remains
plugged in. After a charge starts it can take up to one normal interval until the faster polling kicks
in; starting charging from Home Assistant refreshes the vehicle after 30 seconds, so it switches over
right away.

The switch **Fast polling while plugged in** (configuration category) does the same per vehicle:
it overrides the global option for that vehicle.

### Parking alert

The integration can send a critical notification when a vehicle is parked
(`parkingPosition.state` is `PARKED`) but any of these is true:

- Reliable lock status is not `LOCKED` (skipped when the vehicle does not report it; the API only
  reports it for some vehicles)
- Doors is not `CLOSED`
- Doors locked is not `YES`
- Locked is not `YES`
- Windows is not `CLOSED` (skipped when the API reports `UNSUPPORTED`, i.e. no electric windows)

A value reported as `UNKNOWN`, or one of the other fields missing from the response, also counts as
not secured.

To turn it on, open **Configure** and pick one or more **Parking alert notification targets**, for
example `notify.mobile_app_my_phone`. The list offers your existing notify services; you can also
type a name. Leave it empty for no alerts. The targets apply to all vehicles of the entry.

The **Parking alert grace period** number of each vehicle (a slider from 0 to 30 minutes, default 5,
configuration category) sets how long the vehicle may stay unsecured before the alert goes out; 0
sends it at once. The clock starts at the first poll that shows the problem, or at the vehicle's own
report of it if that came in since the previous poll (within one polling interval), and the alert is only
sent if the latest poll still shows it. The state is only known at each poll, so the alert can come
up to one polling interval later than the grace period alone suggests. Data cached from before a
restart never triggers an alert; the vehicle has to be polled first.

One alert is sent per incident. Once a poll shows the vehicle secured (or no longer parked), the
next problem starts a new incident. Open incidents are stored, so restarting Home Assistant or
reloading the integration does not send the alert again. The binary sensor **Parked unsecured** shows the same condition,
with the failing checks in its `reasons` attribute, for dashboards and your own automations.

For Companion app targets (`notify.mobile_app_*`) the alert is sent as critical: on iOS it plays
even in silent mode and Focus, and on Android it uses the alarm stream. Other notify services get a
normal message. All targets are notified at the same time, and a failing one does not stop the
others. The notification text is in English.

A vehicle can stay silent towards the Škoda servers for a long time, and a poll then returns its
last report, however old. So the alert is only sent on data the vehicle reported (the
`carCapturedTimestamp` of the status) when or after the incident began; an older report may miss that the
car was locked meanwhile. A vehicle that was just parked usually reports once and then sleeps; since
that report starts the incident, it is enough for the alert. If there is no such report when the grace period ends, the integration
wakes the vehicle once per incident, the same way as the **Wake vehicle** button (two requests of
the quota), and decides on the report that follows. If the vehicle does not report within 5 minutes
of the wake-up, the wake-up fails, or it is skipped (in read-only mode, during a rate limit pause, when
fewer than 6 requests of the hourly quota are left and when there is no command to wake the vehicle with:
no known charge mode, and no air conditioning, auxiliary heating or ventilation that the vehicle lists and
that is not running), the alert is sent anyway and ends with "Not confirmed: last report at
…": a vehicle that stays silent must not hold the alert back for good. Apart from that wake-up the
alert only reads data the polls already fetched and costs no requests.

Each wake-up (or why it was skipped or failed) and each alert is written to the logbook of the
**Parked unsecured** sensor, so you can see afterwards why an alert came when it did.

### Rate limits

The API currently allows **20 requests per hour per VIN** (documented as not final). A poll
costs one request per vehicle, and every remote command costs one more. Therefore this
integration:

- Defaults to a 10-minute polling interval (6 requests/hour) with a 3-minute minimum (3 minutes alone use the whole quota of 20 requests/hour, leaving no room for
  commands), and to 5 minutes
  while a vehicle is charging, or plugged in if you enable that option (12 requests/hour - leave room
  for commands).
- Does not refresh after every command; commands are accepted asynchronously (HTTP 202), so
  it schedules a single refresh 30 seconds after the last command.
- Detects HTTP 429 responses and pauses polling, for the wait time reported by the API (`Retry-After`, `RateLimit-Reset` or the error
  message, plus 30 seconds; at most 1 hour, 15 minutes if the API gives no wait time), and logs a warning when this happens.
- Keeps the last known state of a vehicle if only its request failed.

Parts of the vehicle the API cannot report (for example because the vehicle is asleep) are
simply omitted from its response; the corresponding entities are created once the data is
available, which can require reloading the integration.

## Development

```bash
pip install pytest-homeassistant-custom-component
pytest
```

See [CLAUDE.md](CLAUDE.md) for an overview of the code layout and conventions.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Disclaimer

Provided as-is, without warranty. Škoda Auto may change its API at any time, which can break
this integration. Use of the MyŠkoda Public API is subject to Škoda's own terms of service.
