# Changelog

[🇬🇧 English](CHANGELOG.md) | [🇳🇱 Nederlands](CHANGELOG.nl.md)

All notable changes to this integration are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- The API key is created in the MyŠkoda app (Profile > Smart home > Keys > Create key): the README and the texts of the setup, reauthentication and reconfiguration dialogs name that path instead of the web link `go.skoda.eu/api-keys`, and the remark about a QR code is gone.

## [0.5.1]

### Added

- All the values the API reports that were still missing, each only if the vehicle reports it:
  - sensors: charging type, fully charged at (only while charging), battery care target, maximum charging current of the vehicle (text and ampere), target temperature reached at (air conditioning and auxiliary heating), vehicle type, and the license plate (off by default, redacted in the diagnostics);
  - binary sensors: charging care mode, plug unlock after charging (the vehicle setting), front and rear window heating, window heating enabled, air conditioning at unlock, air conditioning without external power, sunroof;
  - the render of the vehicle is the picture of the parking position tracker.
  They cannot be changed through the public API.

## [0.5.0]

### Added

- Charging profiles: for vehicles that list `updateChargingProfile` and report profiles (the saved charging locations of the MyŠkoda app), every profile gets a select **charging current** (`MAXIMUM`/`REDUCED`), a number **target charge** and a switch **unlock plug after charging**. The profile is fetched again right before it is sent, with only the one setting changed, because the vehicle applies a profile as a whole. Tested on an Enyaq (not the one-off timers).
- Auxiliary heating: vehicles that list `startAuxiliaryHeating` and report the function get a `climate` entity **Auxiliary heating** (off, heat, fan only) and a number **Auxiliary heating duration**. Starting it needs the S-PIN of the MyŠkoda account, entered in the options (the field only appears if a vehicle has an auxiliary heating); it is redacted in the diagnostics. The vehicle polls faster while the heating runs, and a stop of it is used to wake vehicles without a charge mode. Untested.
- Blueprint `blueprints/automation/skoda_api_connect/update_charging_profile.yaml`: changes a charging profile when your trigger fires, with safeguards (enough API requests left, no change still waiting for the vehicle, API status, a pause after each change).
- Charging profiles: the **minimum charge** ("minimum charging limit" of the app) as a number and, for vehicles that report it, a switch to activate it. The charging location sensor lists the preferred charging times and timers of the current profile as attributes, and the new action `skoda_api_connect.update_charging_profile` changes any setting, preferred charging time and timer of a profile (named by their `number` in the profile, or by the `id` of the API, which counts across all profiles) in one request (two requests of the quota). Untested.
- The charging location sensor shows the id, the target charge and the next charging time of the current charging profile, and the list of all profiles, as attributes.
- The integration reloads itself when the charging profiles of a vehicle change (a profile was added, deleted or renamed), because the entities of a profile and their names are created at setup. A change has to show in two polls in a row (a deletion in three). The entities of a deleted profile are removed as well, as long as the vehicle still lists `updateChargingProfile`; this is the option **Remove the entities of deleted charging profiles** (on by default, shown for vehicles with charging profiles). Untested.

### Changed

- README: where to create the API key in the MyŠkoda app (Profile > Smart home > Keys > Create key, with screenshots) and a troubleshooting section.
- The diagnostics redact the names of charging profiles, which are usually addresses.

### Fixed

- A part of the vehicle data that the API reports as `<PART>_UNAVAILABLE` (could not be retrieved right now) is now filled in with its last known data, from the previous poll or, at startup, from the stored copy. Before, the entities of that part (the climate and the target temperature, for example) were not created when Home Assistant started while the API left that part out, and stayed unavailable until the integration was reloaded. The old timestamp stays visible. Unsupported or disabled parts are not filled in.

## [0.4.5]

### Added

- A vehicle without a charge mode (such as a combustion vehicle) can now be woken too: the wake-up sends a stop command for the first of air conditioning, auxiliary heating and active ventilation that the vehicle lists as an operation and that is not running. A running function is never stopped, and a vehicle that does not list its operations is not guessed at. Vehicles with a charge mode are woken as before. This is untested: only re-sending the charge mode is known to make a vehicle report. The "Wake vehicle" button now appears for these vehicles as well, and the parking alert can use it.

## [0.4.4]

### Added

- The parking alert writes to the logbook of the **Parked unsecured** sensor: each wake-up to confirm an incident (or why it was skipped or failed) and each alert sent, so you can see afterwards why an alert came when it did. The log messages about the wake-up now name the vehicle.

### Fixed

- Parking alert never sent when the incident began on an older report and the vehicle could not be confirmed. The wake-up that should bring a fresh report needs a known charge mode, so it always failed for vehicles without one (such as most combustion vehicles), and it was skipped in read-only mode, during a rate limit pause and with little quota left. The alert then waited until the vehicle reported on its own, which a parked vehicle may not do for hours, and if that report showed it secured no alert was ever sent. Now the alert is sent anyway, ending with "Not confirmed: last report at …", when the wake-up is skipped or fails or when the vehicle does not report within 5 minutes of it. A wake-up only counts as done once the vehicle accepted it.

## [0.4.3]

### Added

- While the air conditioning or the ventilation runs, the vehicle is polled at its charging interval (like while charging). Switching it off elsewhere, for example in the app, then shows up sooner. It goes back to the normal interval once a poll shows the climate off.
- `brand/icon@2x.png` (512 x 512) next to `brand/icon.png`, the high-resolution version Home Assistant uses on high-DPI screens.

### Changed

- The charge mode select uses the icon `mdi:ev-plug-ccs2` (CCS) instead of `mdi:ev-plug-type2`.

### Fixed

- The air conditioning offered the ventilation mode (`fan_only`) for every vehicle, so choosing it on a vehicle without active ventilation (such as an Enyaq) ended in an error from the API. The mode is now only offered when the vehicle lists `startActiveVentilation` among its operations.

## [0.4.2]

### Fixed

- Parking alert never sent for a vehicle that was just parked: it reports once and then sleeps, and that report was older than the poll that opened the incident, so the alert kept waiting for a newer one (and the wake-up is often skipped, e.g. when polling uses most of the quota). If the vehicle reported the problem within one polling interval before that poll, the incident now begins at that report, the alert is sent on it, and the grace period counts from it. Older reports still wake the vehicle first.

## [0.4.1]

### Changed

- Icons for entities that had none: the charge limit (sensor and number), the fuel level, the charge mode and the charging switch. The API status sensor now uses `mdi:api`, so it no longer shares its icon with "Last vehicle data".

## [0.4.0]

### Added

- Parking alert: a critical notification when a vehicle is parked but not secured (reliable lock status not `LOCKED`, doors not `CLOSED`, doors locked not `YES`, locked not `YES`, or windows not `CLOSED`; unknown values count as not secured, windows `UNSUPPORTED` is skipped, and reliable lock status is skipped when the vehicle does not report it). The notify services that receive it are chosen in the options (several are possible); Companion app targets get it as a critical alert. One alert per incident, also across restarts and reloads. It is only sent on data the vehicle reported after the incident began, so an old snapshot cannot raise a false alarm; without such a report at the end of the grace period the vehicle is woken once per incident (two requests, skipped in read-only mode, during a rate limit pause or with fewer than 6 requests left). No other API requests.
- Number "Parking alert grace period" per vehicle (slider, 0-30 minutes, default 5): how long a vehicle may stay unsecured before the alert is sent.
- Binary sensor "Parked unsecured" with the failing checks in the attribute `reasons`.
- Sensors "Doors locked", "Reliable lock status" and "Parking state", showing the values reported by the API.

### Changed

- Diagnostics redact the parking alert notification targets.

## [0.3.1]

### Added

- Sensor "Current polling interval" (diagnostic): the interval in minutes the vehicle is polled at right now (normal or charging interval, attribute `mode`). It follows a changed setting at once.
- After an accepted command the air conditioning, the charging switch, the charge limit and the charge mode show the expected state immediately (attribute `pending: true`) instead of waiting for the vehicle. It is replaced when the vehicle reports newer data of that section and dropped after 3 minutes (air conditioning) or 5 minutes (others) without a report. A rejected command changes nothing. No additional requests.

### Changed

- Renamed the sensors "Last poll" to "Last API poll" and "Rate limit until" to "API rate limit until" (display names and translations; entity IDs of existing installations stay the same).

## [0.3.0]

### Added

- Sensor "Last vehicle data": when the vehicle itself last reported data to the Škoda servers (newest `carCapturedTimestamp`), with the timestamp of each section as attributes. Unlike "Last poll" it shows when the connection between car and servers was interrupted.
- Button "Wake vehicle": the API has no wake-up call, so it re-sends the current charge mode (a command that changes nothing but has to reach the vehicle), which makes a sleeping vehicle report. Costs two requests of the API quota.
- Number "Wake charging vehicle after (0 = off)" (configuration category, off by default): while a vehicle is charging and has not reported data for this many minutes (5-minute steps, minimum 10), it is woken the same way. Skipped during a rate limit pause and when fewer than 6 requests of the hourly quota are left; never more often than the configured time.
- Spanish and Luxembourgish translations (thanks to janreimen), including the wake-up entities.

### Fixed

- The Luxembourgish translation is now `lb.json`; Home Assistant uses the language code `lb`, so `lu.json` was never loaded.

## [0.2.1]

### Fixed

- Diagnostics no longer contain VINs (per-vehicle polling options are now listed as `vehicle_1`, `vehicle_2`, ...) or the vehicle name.

## [0.2.0]

### Added

- Binary sensor "Charging cable lock" for the new `plugLockState` field of API 1.1.0 (on = unlocked).

## [0.1.0]

### Added

- Initial release.
