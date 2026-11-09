"""Tests for reloading the entry when the charging profiles of a vehicle change."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.skoda_api_connect.api import SkodaVehicle
from custom_components.skoda_api_connect.const import (
    CONF_API_KEY,
    CONF_REMOVE_DELETED_PROFILES,
    CONF_VINS,
    DOMAIN,
)

from .conftest import VIN

GET = "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle"


_PATCHERS: list = []


@pytest.fixture(autouse=True)
def _stop_patches():
    """Stop the get_vehicle patches the tests start, after each test."""
    yield
    while _PATCHERS:
        _PATCHERS.pop().stop()


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
    # The patch stays active after the setup: later polls fetch the vehicle again.
    patcher = patch(GET, new=mock)
    patcher.start()
    _PATCHERS.append(patcher)
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
        reload.assert_not_called()  # a deletion has to show one poll longer
        await _poll(coordinator)
        reload.assert_called_once_with(mock_entry.entry_id)
    await coordinator.async_shutdown()


async def test_the_entities_of_a_deleted_profile_are_removed(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    coordinator, mock = await _setup(hass, mock_entry, _vehicle((1, "Home"), (2, "Work")))
    registry = er.async_get(hass)

    def select(profile_id: int) -> str | None:
        return registry.async_get_entity_id(
            "select", "skoda_api_connect", f"{VIN}_profile_{profile_id}_max_current"
        )

    assert select(1) and select(2)
    with patch.object(hass.config_entries, "async_schedule_reload", MagicMock()):
        mock.return_value = _vehicle((1, "Home"))
        for _ in range(3):
            await _poll(coordinator)
    assert select(1) is not None  # the profile that is still there keeps its entities
    assert select(2) is None
    await coordinator.async_shutdown()


async def test_nothing_is_removed_if_the_vehicle_stops_listing_the_operation(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    coordinator, mock = await _setup(hass, mock_entry, _vehicle((1, "Home")))
    reload = MagicMock()
    with patch.object(hass.config_entries, "async_schedule_reload", reload):
        mock.return_value = _vehicle((1, "Home"), operations=("startCharging",))
        for _ in range(3):
            await _poll(coordinator)
    reload.assert_called_once_with(mock_entry.entry_id)
    assert er.async_get(hass).async_get_entity_id(
        "select", "skoda_api_connect", f"{VIN}_profile_1_max_current"
    )
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


async def test_with_the_option_off_a_deleted_profile_only_reloads(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "key", CONF_VINS: [VIN]},
        options={CONF_REMOVE_DELETED_PROFILES: False},
    )
    coordinator, mock = await _setup(hass, entry, _vehicle((1, "Home"), (2, "Work")))
    reload = MagicMock()
    with patch.object(hass.config_entries, "async_schedule_reload", reload):
        mock.return_value = _vehicle((1, "Home"))
        await _poll(coordinator)
        await _poll(coordinator)
        reload.assert_called_once_with(entry.entry_id)  # no third poll needed
    assert er.async_get(hass).async_get_entity_id(
        "select", "skoda_api_connect", f"{VIN}_profile_2_max_current"
    )  # the entities of the deleted profile stay
    await coordinator.async_shutdown()


async def test_the_option_is_only_offered_for_vehicles_with_charging_profiles(
    hass: HomeAssistant,
) -> None:
    with_profiles = MockConfigEntry(
        domain=DOMAIN, data={CONF_API_KEY: "key", CONF_VINS: [VIN]}
    )
    coordinator, _ = await _setup(hass, with_profiles, _vehicle((1, "Home")))
    result = await hass.config_entries.options.async_init(with_profiles.entry_id)
    assert CONF_REMOVE_DELETED_PROFILES in [str(key) for key in result["data_schema"].schema]
    await coordinator.async_shutdown()


async def test_no_option_without_the_profile_operation(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: "key", CONF_VINS: [VIN]})
    coordinator, _ = await _setup(hass, entry, _vehicle(operations=("startCharging",)))
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert CONF_REMOVE_DELETED_PROFILES not in [str(key) for key in result["data_schema"].schema]
    await coordinator.async_shutdown()
