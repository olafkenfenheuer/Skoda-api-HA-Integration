# Changelog

[🇬🇧 English](CHANGELOG.md) | [🇳🇱 Nederlands](CHANGELOG.nl.md)

All notable changes to this integration are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
