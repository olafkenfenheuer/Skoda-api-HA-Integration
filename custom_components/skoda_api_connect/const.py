"""Constants for the Škoda API Connect integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "skoda_api_connect"

API_BASE_URL: Final = "https://public.api.connect.skoda-auto.cz"

CONF_API_KEY: Final = "api_key"
CONF_VINS: Final = "vins"
CONF_READ_ONLY: Final = "read_only"
CONF_CHARGING_SCAN_INTERVAL: Final = "charging_scan_interval"
# Also use the charging interval while the charging cable is plugged in (not only while charging).
CONF_PLUGGED_IN_FAST_POLLING: Final = "plugged_in_fast_polling"
# Per-vehicle overrides in the entry options: {vin: {"idle": minutes, "charging": minutes}}
CONF_VEHICLE_INTERVALS: Final = "vehicle_intervals"
# Key of the per-vehicle override of CONF_PLUGGED_IN_FAST_POLLING inside CONF_VEHICLE_INTERVALS[vin].
KEY_PLUGGED_IN: Final = "plugged_in"
# Key of the per-vehicle auto-wake time (minutes, 0 = off) inside CONF_VEHICLE_INTERVALS[vin].
KEY_AUTO_WAKE: Final = "auto_wake"

# Notify services ("notify.<service>") that receive the parking alert.
CONF_NOTIFY_TARGETS: Final = "notify_targets"
NOTIFY_DOMAIN: Final = "notify"
# Key of the per-vehicle parking alert grace period (minutes) inside CONF_VEHICLE_INTERVALS[vin].
KEY_ALERT_GRACE: Final = "alert_grace"
DEFAULT_ALERT_GRACE_MINUTES: Final = 5
MAX_ALERT_GRACE_MINUTES: Final = 30
PARKED_STATE: Final = "PARKED"

# A charging vehicle that has not reported for the auto-wake time gets a harmless command that
# makes it report. Never wake more often than this, and only with this much quota left.
MIN_AUTO_WAKE_MINUTES: Final = 10
AUTO_WAKE_MIN_REQUESTS_REMAINING: Final = 6
AUTO_WAKE_NUMBER_MAX_MINUTES: Final = 120

# The public API allows 20 requests per hour and VIN (the limit is documented as not
# final), and every command counts against the same quota. One poll costs a single
# request per vehicle, so 10 minutes leaves roughly half of the quota for commands.
# MIN_SCAN_INTERVAL_MINUTES is a hard floor (3 min = 20 requests/hour, i.e. the whole quota
# without any room for commands) for the options flow and the polling interval numbers.
DEFAULT_SCAN_INTERVAL_MINUTES: Final = 10
# Polling interval while a vehicle is charging (state changes are what you want to see).
DEFAULT_CHARGING_SCAN_INTERVAL_MINUTES: Final = 5
MIN_SCAN_INTERVAL_MINUTES: Final = 3
MAX_SCAN_INTERVAL_MINUTES: Final = 1440
# Upper end of the sliders of the per-vehicle polling interval number entities.
POLL_INTERVAL_NUMBER_MAX_MINUTES: Final = 120

# Commands are accepted asynchronously (HTTP 202); refresh once shortly afterwards so the
# new state shows up without waiting for the next poll.
POST_COMMAND_REFRESH_DELAY: Final = 30

# After an accepted command (HTTP 202) the entity shows the expected state until the vehicle
# reports newer data of that section, but no longer than this: the API only says "accepted",
# not "done", and a sleeping vehicle may never execute the command.
EXPECTED_STATE_MINUTES: Final = 5
EXPECTED_CLIMATE_MINUTES: Final = 3

# Remove the entities of a charging profile that was deleted in the vehicle (default on).
CONF_REMOVE_DELETED_PROFILES: Final = "remove_deleted_profiles"

# S-PIN of the MyŠkoda account: the API needs it to start the auxiliary heating. Stored in the
# entry options (like the API key it is a secret) and never logged.
CONF_SPIN: Final = "spin"
# Key of the per-vehicle running time of the auxiliary heating (minutes) inside CONF_VEHICLE_INTERVALS[vin].
KEY_AUX_DURATION: Final = "aux_duration"
DEFAULT_AUX_DURATION_MINUTES: Final = 30
MIN_AUX_DURATION_MINUTES: Final = 10
MAX_AUX_DURATION_MINUTES: Final = 60

MANUFACTURER: Final = "Škoda"
