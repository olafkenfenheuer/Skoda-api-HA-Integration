"""The Škoda API Connect integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SkodaApi
from .const import CONF_API_KEY, CONF_READ_ONLY, CONF_VINS
from .coordinator import SkodaConfigEntry, SkodaDataUpdateCoordinator
from .parking_alert import SkodaParkingAlert

_LOGGER = logging.getLogger(__name__)

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


async def async_setup_entry(hass: HomeAssistant, entry: SkodaConfigEntry) -> bool:
    """Set up Škoda API Connect from a config entry."""
    api = SkodaApi(async_get_clientsession(hass), entry.data[CONF_API_KEY])
    coordinator = SkodaDataUpdateCoordinator(hass, entry, api, list(entry.data[CONF_VINS]))
    coordinator.read_only = entry.options.get(CONF_READ_ONLY, False)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # After the platforms, so the logbook entries of the alert find the "Parked
    # unsecured" sensor even on the first setup.
    await SkodaParkingAlert(hass, entry, coordinator).async_start()

    return True


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
