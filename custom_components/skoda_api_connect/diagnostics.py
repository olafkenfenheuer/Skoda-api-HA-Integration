"""Diagnostics support for the Škoda API Connect integration."""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_KEY,
    CONF_NOTIFY_TARGETS,
    CONF_SPIN,
    CONF_VEHICLE_INTERVALS,
    CONF_VINS,
)
from .coordinator import SkodaConfigEntry

TO_REDACT = {
    CONF_API_KEY,
    CONF_VINS,
    "vin",
    "licensePlate",
    "renderUrl",
    "gpsCoordinates",
    "formattedAddress",
}


def _redact_options(options: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
    """Return the options with the VIN keys of the per-vehicle overrides replaced."""
    redacted = dict(options)
    # Notify service names usually contain a person's or phone's name.
    if redacted.get(CONF_NOTIFY_TARGETS):
        redacted[CONF_NOTIFY_TARGETS] = REDACTED
    # The S-PIN is a secret.
    if redacted.get(CONF_SPIN):
        redacted[CONF_SPIN] = REDACTED
    intervals = redacted.get(CONF_VEHICLE_INTERVALS)
    if isinstance(intervals, dict):
        redacted[CONF_VEHICLE_INTERVALS] = {
            aliases.get(vin, f"vehicle_unknown_{index}"): override
            for index, (vin, override) in enumerate(intervals.items(), start=1)
        }
    return redacted


def _redact_vehicle_data(data: dict[str, Any]) -> dict[str, Any]:
    """Return the vehicle data without the user-typed names.

    The name of the vehicle is typed in the MySkoda app, often a person's name. The name of
    a charging profile (a saved charging location) is usually an address.
    """
    redacted = {**data, "name": REDACTED}
    profiles = data.get("chargingProfiles")
    if isinstance(profiles, dict):
        profiles = copy.deepcopy(profiles)
        for profile in profiles.get("profiles") or []:
            if isinstance(profile, dict) and "name" in profile:
                profile["name"] = REDACTED
        current = profiles.get("currentVehiclePositionProfile")
        if isinstance(current, dict) and "name" in current:
            current["name"] = REDACTED
        redacted["chargingProfiles"] = profiles
    return redacted


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SkodaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    vehicles = coordinator.data.vehicles
    aliases = {vin: f"vehicle_{index}" for index, vin in enumerate(vehicles, start=1)}
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": _redact_options(dict(entry.options), aliases),
        "read_only": coordinator.read_only,
        "vehicle_count": len(coordinator.vins),
        "vehicles": {
            aliases[vin]: async_redact_data(
                {
                    "data": _redact_vehicle_data(vehicle.data),
                    "errors": vehicle.errors,
                },
                TO_REDACT,
            )
            for vin, vehicle in vehicles.items()
        },
    }
