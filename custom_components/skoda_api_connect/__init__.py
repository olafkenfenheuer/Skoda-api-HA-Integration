"""The Škoda API Connect integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SkodaApi
from .const import (
    CONF_API_KEY,
    CONF_READ_ONLY,
    CONF_REMOVE_DELETED_PROFILES,
    CONF_VINS,
    DOMAIN,
)
from .coordinator import SkodaConfigEntry, SkodaDataUpdateCoordinator
from .parking_alert import SkodaParkingAlert
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# The entities of a charging profile are created at setup, so the entry is reloaded when the
# profiles the vehicle reports change. A change has to show in this many polls in a row, so that
# an answer that is wrong for a moment does not reload the entry.
PROFILE_CHANGE_CONFIRMATIONS = 2
# The entities of a deleted profile are removed for good, so a deletion has to show in one more poll.
PROFILE_REMOVAL_CONFIRMATIONS = 3

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.DEVICE_TRACKER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions of the integration."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SkodaConfigEntry) -> bool:
    """Set up Škoda API Connect from a config entry."""
    api = SkodaApi(async_get_clientsession(hass), entry.data[CONF_API_KEY])
    coordinator = SkodaDataUpdateCoordinator(hass, entry, api, list(entry.data[CONF_VINS]))
    coordinator.read_only = entry.options.get(CONF_READ_ONLY, False)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _async_reload_on_profile_change(hass, entry, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # After the platforms, so the logbook entries of the alert find the "Parked
    # unsecured" sensor even on the first setup.
    await SkodaParkingAlert(hass, entry, coordinator).async_start()

    return True


def _profiles(coordinator: SkodaDataUpdateCoordinator) -> dict[str, frozenset[tuple[int, str]]]:
    """Return (id, name) of the charging profiles per vehicle that has entities for them."""
    if not coordinator.data:
        return {}
    return {
        vin: frozenset((p["id"], str(p.get("name") or "")) for p in vehicle.charging_profiles())
        for vin, vehicle in coordinator.data.vehicles.items()
        if vehicle.lists("updateChargingProfile")
    }


@callback
def _async_reload_on_profile_change(
    hass: HomeAssistant, entry: SkodaConfigEntry, coordinator: SkodaDataUpdateCoordinator
) -> None:
    """Reload the entry when a charging profile was added, deleted or renamed.

    Profiles get their entities (and their names) when the entry is set up. A change has to
    show in several polls in a row; the count restarts when it is gone again. The entities of
    a deleted profile are removed as well (an option, on by default), one poll later than a
    reload alone would happen, and only while the vehicle still lists the operation, so a vehicle
    whose operations are missing for a moment does not lose its entities.
    """
    known = _profiles(coordinator)
    last_data = coordinator.data
    confirmations = 0
    scheduled = False

    @callback
    def _check() -> None:
        nonlocal last_data, confirmations, scheduled
        data = coordinator.data
        if scheduled or data is None or data is last_data:
            return  # no new poll (the listeners are also called for other reasons)
        last_data = data
        current = _profiles(coordinator)
        if current == known:
            confirmations = 0
            return
        confirmations += 1
        removed = {
            (vin, profile_id)
            for vin, profiles in known.items()
            if vin in current
            for profile_id, _name in profiles
            if profile_id not in {i for i, _ in current[vin]}
        }
        # The option may be changed at any time, so it is read when a change is confirmed.
        remove = entry.options.get(CONF_REMOVE_DELETED_PROFILES, True) and bool(removed)
        needed = PROFILE_REMOVAL_CONFIRMATIONS if remove else PROFILE_CHANGE_CONFIRMATIONS
        if confirmations < needed:
            return
        scheduled = True
        if remove:
            _async_remove_profile_entities(hass, entry, removed)
        _LOGGER.info("The charging profiles of a vehicle changed; reloading the integration")
        hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(coordinator.async_add_listener(_check))


@callback
def _async_remove_profile_entities(
    hass: HomeAssistant, entry: SkodaConfigEntry, removed: set[tuple[str, int]]
) -> None:
    """Remove the entities of charging profiles that no longer exist."""
    registry = er.async_get(hass)
    for vin, profile_id in removed:
        prefix = f"{vin}_profile_{profile_id}_"
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if entity.unique_id.startswith(prefix):
                registry.async_remove(entity.entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: SkodaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: SkodaConfigEntry) -> None:
    """Apply changed options; only reload when something other than the interval changed."""
    coordinator = entry.runtime_data
    if entry.options.get(CONF_READ_ONLY, False) == coordinator.read_only:
        coordinator.reschedule()
        return
    await hass.config_entries.async_reload(entry.entry_id)
