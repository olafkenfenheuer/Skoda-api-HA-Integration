"""Actions of the Škoda API Connect integration."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

SERVICE_UPDATE_CHARGING_PROFILE = "update_charging_profile"

# The unique id of the entity of a charging profile: "<vin>_profile_<id>_<key>".
_PROFILE_UNIQUE_ID = re.compile(r"^(?P<vin>.+)_profile_(?P<id>\d+)_[a-z_]+$")
_TIME = vol.All(cv.string, vol.Match(r"^([01]\d|2[0-3]):[0-5]\d$"))
_DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
_SLOT_ID = vol.All(vol.Coerce(int), vol.Range(min=1))

UPDATE_CHARGING_PROFILE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional("max_charging_current"): vol.In(["MAXIMUM", "REDUCED"]),
        vol.Optional("target_charge"): vol.All(vol.Coerce(int), vol.Range(min=50, max=100)),
        vol.Optional("auto_unlock_plug"): cv.boolean,
        vol.Optional("min_charge"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        vol.Optional("min_charge_enabled"): cv.boolean,
        vol.Optional("preferred_charging_times"): [
            vol.Schema(
                {
                    vol.Required("id"): _SLOT_ID,
                    vol.Optional("enabled"): cv.boolean,
                    vol.Optional("start"): _TIME,
                    vol.Optional("end"): _TIME,
                }
            )
        ],
        vol.Optional("timers"): [
            vol.Schema(
                {
                    vol.Required("id"): _SLOT_ID,
                    vol.Optional("enabled"): cv.boolean,
                    vol.Optional("time"): _TIME,
                    vol.Optional("days"): vol.All(cv.ensure_list, [vol.In(_DAYS)]),
                    vol.Optional("one_off_day"): vol.In(_DAYS),
                }
            )
        ],
    }
)

_SETTINGS = (
    ("max_charging_current", ("maxChargingCurrent",)),
    ("target_charge", ("targetStateOfChargeInPercent",)),
    ("auto_unlock_plug", ("autoUnlockPlugWhenCharged",)),
    ("min_charge", ("minBatteryStateOfCharge", "minimumBatteryStateOfChargeInPercent")),
    ("min_charge_enabled", ("minBatteryStateOfCharge", "enabled")),
)


def _find(items: list[dict[str, Any]], item_id: int, what: str) -> dict[str, Any]:
    for item in items:
        if item.get("id") == item_id:
            return item
    raise HomeAssistantError(f"The charging profile has no {what} with the id {item_id}")


def apply_changes(body: dict[str, Any], data: dict[str, Any]) -> None:
    """Edit a charging profile ``body`` as the action data asks, leaving the rest as it is."""
    settings = body.setdefault("settings", {})
    for field, path in _SETTINGS:
        if field not in data:
            continue
        value = data[field]
        if field == "auto_unlock_plug":
            value = "PERMANENT" if value else "OFF"
        node = settings
        for name in path[:-1]:
            node = node.setdefault(name, {})
        node[path[-1]] = value
    for change in data.get("preferred_charging_times", []):
        slot = _find(body.get("preferredChargingTimes", []), change["id"], "preferred charging time")
        for field, key in (("enabled", "enabled"), ("start", "startTime"), ("end", "endTime")):
            if field in change:
                slot[key] = change[field]
    for change in data.get("timers", []):
        timer = _find(body.get("timers", []), change["id"], "timer")
        if "enabled" in change:
            timer["enabled"] = change["enabled"]
        if "time" in change:
            timer["time"] = change["time"]
        if "days" in change:
            timer["type"] = "RECURRING"
            timer["recurringOn"] = change["days"]
            timer.pop("oneOffDay", None)
        if "one_off_day" in change:
            timer["type"] = "ONE_OFF"
            timer["oneOffDay"] = change["one_off_day"]
            timer.pop("recurringOn", None)


def _changes(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key != ATTR_ENTITY_ID}


async def _async_update_charging_profile(hass: HomeAssistant, call: ServiceCall) -> None:
    changes = _changes(call.data)
    if not changes:
        raise ServiceValidationError("Name at least one thing to change")
    registry = er.async_get(hass)
    targets: dict[tuple[str, str, int], None] = {}
    for entity_id in call.data[ATTR_ENTITY_ID]:
        entry = registry.async_get(entity_id)
        match = _PROFILE_UNIQUE_ID.match(entry.unique_id) if entry else None
        if entry is None or entry.platform != DOMAIN or match is None:
            raise ServiceValidationError(f"{entity_id} is not an entity of a charging profile")
        targets[(entry.config_entry_id, match["vin"], int(match["id"]))] = None
    mutate: Callable[[dict[str, Any]], None] = lambda body: apply_changes(body, call.data)  # noqa: E731
    for entry_id, vin, profile_id in targets:
        config_entry = hass.config_entries.async_get_entry(entry_id)
        if config_entry is None or not hasattr(config_entry, "runtime_data"):
            raise HomeAssistantError("The integration is not loaded")
        await config_entry.runtime_data.async_update_profile(vin, profile_id, mutate)


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions of the integration."""

    async def handle(call: ServiceCall) -> None:
        await _async_update_charging_profile(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_CHARGING_PROFILE,
        handle,
        schema=UPDATE_CHARGING_PROFILE_SCHEMA,
    )
