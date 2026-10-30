# CLAUDE.md

Home Assistant custom integration `skoda_api_connect` (HACS) for Škoda vehicles. It talks directly to
the official **MyŠkoda Public API** (`https://public.api.connect.skoda-auto.cz`, OpenAPI at
`/v3/api-docs`, human docs at `/docs`) with an API key. There is no third-party client library.
Default branch: `main`. Unofficial project - not affiliated with Škoda Auto.

## Layout

- `custom_components/skoda_api_connect/` - the integration (domain `skoda_api_connect`)
  - `api.py` - `SkodaApi` (aiohttp client, `X-API-Key` header), `SkodaVehicle` (wraps the raw JSON
    response; read values with `vehicle.get("charging", "status", "state")`), error classes
    (`SkodaAuthError`, `SkodaRateLimitError`, `SkodaApiError`, `SkodaConnectionError`)
  - `coordinator.py` - `SkodaDataUpdateCoordinator`: per-vehicle polling schedule, rate-limit backoff,
    `async_command()` (read-only check, error mapping, forced single refresh of the vehicle after 30 s)
  - `config_flow.py` - API key + VIN list (comma separated), reauth and reconfigure (new API key / VINs at any time; both share
    `_async_credentials_step`), options flow (intervals, read-only, parking alert notify targets)
  - `parking_alert.py` - `SkodaParkingAlert`: critical notification when a vehicle is parked but not
    secured (`unsecured_reasons()`), one per incident after the per-vehicle grace period; open incidents
    are kept in their own `Store` so restarts/reloads do not re-alert; an incident begins at the status report
    showing it if that is at most one polling interval old (`_incident_start`), else at the poll; only alerts on a
    status report captured when or after the incident began, otherwise wakes the vehicle once per incident (`coordinator.can_wake()`, the same
    quota guard as the automatic wake-up; `coordinator.supports_wake()` needs a known charge mode) and waits up to
    `WAKE_CONFIRM_TIMEOUT` for a newer report; if the wake-up is skipped or fails, or no report follows, it sends the alert
    anyway, marked "Not confirmed"; wake-ups and alerts go to the logbook of the `{vin}_parked_unsecured` sensor
    (`async_log_entry`, hence `after_dependencies: ["logbook"]`)
  - `entity.py` - `SkodaVehicleEntity` base; platforms: `sensor`, `binary_sensor`, `button`, `device_tracker`,
    `climate`, `switch`, `number`, `select`; `diagnostics.py`
  - `strings.json` is a copy of `translations/en.json`; translations exist for en/de/nl/fr/cs/sk/es/lb
  - `brand/icon.png` - icon shown by Home Assistant 2026.3+
- `tests/` - pytest suite using `pytest-homeassistant-custom-component` (see `pytest.ini`)
- `README.md` / `README.de.md` / `README.nl.md`, `CHANGELOG.md` / `CHANGELOG.nl.md`

## Commands

```bash
pip install pytest-homeassistant-custom-component   # provides Home Assistant + pytest plugins
pytest                                              # run the suite from the repo root
python -m compileall -q custom_components           # quick syntax check
```

## API facts that shape the code

- **Quota: 20 requests/hour/VIN** (documented as not final); every poll *and* every command counts.
  Do not add extra requests (e.g. refresh after every command). 401/403 do not consume quota.
- `GET /api/v1/vehicles/{vin}` returns `{vehicle, errors}`. Parts that are unsupported, disabled or
  failed are **omitted** and listed in `errors` - a missing field means *unknown*, never a value.
  Entities must therefore tolerate missing data (`vehicle.get(...)` returns `None`).
- Commands answer `202 Accepted`; the vehicle state changes later. Available operations are listed in
  `vehicle.operations` (`vehicle.supports("startCharging")`).
- Enum values may gain new members - never assume an exhaustive list; treat `UNKNOWN`/`UNSUPPORTED` as
  unknown.
- There is **no vehicle list**, so VINs are entered by the user. There is **no lock/unlock, honk/flash,
  wakeup (the button "Wake vehicle" is only a workaround that re-sends the current charge mode), window heating, battery care, reduced current**; do not re-add entities for them.
- Errors are RFC 9457 `application/problem+json`; the type suffix (e.g. `api-key-expired`) is kept in
  `SkodaApiError.problem`. 401 -> reauth, 429 -> backoff via `Retry-After`.

## Conventions

- Unique IDs are `{vin}_{key}` (and `{vin}_poll_interval_{idle|charging}`, `{vin}_poll_when_plugged_in`); keep them stable so
  existing entity history survives.
- Options live in `entry.options`: `scan_interval`, `charging_scan_interval`, `plugged_in_fast_polling`, `read_only`, and
  per-vehicle `vehicle_intervals: {vin: {idle, charging, plugged_in}}` (written via
  `coordinator.set_vehicle_option`; `plugged_in` overrides `plugged_in_fast_polling`). The update listener only reloads the entry
  when `read_only` changes; interval changes call `coordinator.reschedule()`.
- `vehicle_intervals: {vin: {..., auto_wake}}` also holds the automatic wake-up time in minutes (0 = off), see
  `coordinator._should_auto_wake`; `SkodaVehicle.last_captured()` is the newest `carCapturedTimestamp`.
- `notify_targets` (list of `notify.<service>`, global) and `vehicle_intervals: {vin: {..., alert_grace}}`
  (minutes, default 5) configure the parking alert; changing them reschedules open incidents without a
  reload. Diagnostics redact `notify_targets`.
- Every remote control goes through `coordinator.async_command(vin, coroutine, expect)`. Pass an `Expectation(key, value,
  section)` so the entity shows the expected state at once (`pending: true`): the entity sets `_expected_key` and
  prefers `self._expected()` over the vehicle data. It is dropped when the vehicle reports a newer
  `carCapturedTimestamp` of `section`, or after its `ttl`. Do not add it for settings stored only in Home Assistant.
- Changing user-facing strings: update **all eight** translation files and copy `en.json` to
  `strings.json`.
- Keep READMEs and changelogs in sync (English is the source; German README, Dutch README/CHANGELOG).
  Bump `version` in `manifest.json` and add a `CHANGELOG` entry for user-visible changes.
- Write code in the existing style: type hints, `from __future__ import annotations`, small
  `SkodaEntityDescription`-style value/exists functions for sensors.
