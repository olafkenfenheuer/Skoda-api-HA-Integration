"""Tests for reloading the entry when the charging profiles of a vehicle change."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.skoda_api_connect.api import SkodaVehicle

from .conftest import VIN

GET = "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle"


def _vehicle(*profiles: tuple[int, str], operations=("updateChargingProfile",)) -> SkodaVehicle:
    return SkodaVehicle(
        vin=VIN,
        data={
            "name": "Car 1",
            "operations": [{"name": name} for name in operations],
            "chargingProfiles": {
                "profiles": [
                    {"id": i, "name": name, "settings": {}, "preferredChargingTimes": [], "timers": []}
                    for i, name in profiles
                ],
            },
        },
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, vehicle: SkodaVehicle):
    mock = AsyncMock(return_value=vehicle)
    entry.add_to_hass(hass)
    with patch(GET, new=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry.runtime_data, mock


async def _poll(coordinator) -> None:
    coordinator._force.add(VIN)
    await coordinator.async_refresh()


async def test_reloads_when_a_profile_is_added_in_two_polls_in_a_row(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    coordinator, mock = await _setup(hass, mock_entry, _vehicle((1, "Home")))
    reload = MagicMock()
    with patch.object(hass.config_entries, "async_schedule_reload", reload):
        mock.return_value = _vehicle((1, "Home"), (2, "Work"))
        await _poll(coordinator)
        reload.assert_not_called()  # one poll is not enough
        await _poll(coordinator)
        reload.assert_called_once_with(mock_entry.entry_id)
    await coordinator.async_shutdown()


async def test_reloads_when_a_profile_is_deleted(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    coordinator, mock = await _setup(hass, mock_entry, _vehicle((1, "Home"), (2, "Work")))
    reload = MagicMock()
    with patch.object(hass.config_entries, "async_schedule_reload", reload):
        mock.return_value = _vehicle((1, "Home"))
        await _poll(coordinator)
        await _poll(coordinator)
        reload.assert_called_once_with(mock_entry.entry_id)
    await coordinator.async_shutdown()


async def test_reloads_when_a_profile_is_renamed(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    # The names of the entities are taken at setup, so a new name needs a reload.
    coordinator, mock = await _setup(hass, mock_entry, _vehicle((1, "Home")))
    reload = MagicMock()
    with patch.object(hass.config_entries, "async_schedule_reload", reload):
        mock.return_value = _vehicle((1, "Zuhause"))
        await _poll(coordinator)
        await _poll(coordinator)
        reload.assert_called_once_with(mock_entry.entry_id)
    await coordinator.async_shutdown()


async def test_a_change_that_goes_away_again_does_not_reload(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    coordinator, mock = await _setup(hass, mock_entry, _vehicle((1, "Home")))
    reload = MagicMock()
    with patch.object(hass.config_entries, "async_schedule_reload", reload):
        for answer in (_vehicle(), _vehicle((1, "Home")), _vehicle(), _vehicle((1, "Home"))):
            mock.return_value = answer
            await _poll(coordinator)
        reload.assert_not_called()
    await coordinator.async_shutdown()


async def test_vehicles_without_the_profile_operation_are_ignored(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    coordinator, mock = await _setup(
        hass, mock_entry, _vehicle((1, "Home"), operations=("startCharging",))
    )
    reload = MagicMock()
    with patch.object(hass.config_entries, "async_schedule_reload", reload):
        mock.return_value = _vehicle((1, "Home"), (2, "Work"), operations=("startCharging",))
        await _poll(coordinator)
        await _poll(coordinator)
        reload.assert_not_called()
    await coordinator.async_shutdown()
