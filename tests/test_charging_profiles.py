"""Tests for the entities of the charging profiles (saved charging locations)."""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.skoda_api_connect.api import SkodaVehicle

from .conftest import VIN

GET = "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle"
PUT = "custom_components.skoda_api_connect.api.SkodaApi.update_charging_profile"


def _profile(**settings) -> dict:
    return {
        "id": 7,
        "name": "Home",
        "settings": {
            "maxChargingCurrent": "MAXIMUM",
            "targetStateOfChargeInPercent": 80,
            "autoUnlockPlugWhenCharged": "OFF",
            "minBatteryStateOfCharge": {"enabled": True, "minimumBatteryStateOfChargeInPercent": 20},
            **settings,
        },
        "preferredChargingTimes": [
            {"id": 1, "enabled": True, "startTime": "22:00", "endTime": "06:00"}
        ],
        "timers": [{"id": 3, "enabled": False, "time": "07:00", "type": "ONE_OFF"}],
    }


def _vehicle(profile: dict | None, *, operations=("updateChargingProfile",)) -> SkodaVehicle:
    data: dict = {
        "name": "Car 1",
        "operations": [{"name": name} for name in operations],
        "chargingProfiles": {
            "profiles": [profile] if profile else [],
            "carCapturedTimestamp": "2026-11-01T10:00:00Z",
        },
    }
    return SkodaVehicle(vin=VIN, data=data)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, cached: SkodaVehicle, fresh=None):
    """Set up; ``fresh`` is what a request for the charging profiles returns."""
    fresh = fresh or cached

    async def _get(vin, include=None):
        return fresh if include else cached

    mock = AsyncMock(side_effect=_get)
    entry.add_to_hass(hass)
    with patch(GET, new=mock):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry.runtime_data, mock


def _entity(hass: HomeAssistant, domain: str, key: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(
        domain, "skoda_api_connect", f"{VIN}_profile_7_{key}"
    )


async def test_entities_of_each_profile(hass: HomeAssistant, mock_entry: MockConfigEntry) -> None:
    c, _ = await _setup(hass, mock_entry, _vehicle(_profile()))
    assert hass.states.get(_entity(hass, "select", "max_current")).state == "MAXIMUM"
    assert float(hass.states.get(_entity(hass, "number", "target_soc")).state) == 80
    assert hass.states.get(_entity(hass, "switch", "auto_unlock")).state == "off"
    await c.async_shutdown()


@pytest.mark.parametrize(
    "vehicle",
    [
        _vehicle(_profile(), operations=("startCharging",)),  # does not list the operation
        _vehicle(None),  # no saved charging location
    ],
)
async def test_no_entities_without_operation_or_profile(
    hass: HomeAssistant, mock_entry: MockConfigEntry, vehicle: SkodaVehicle
) -> None:
    c, _ = await _setup(hass, mock_entry, vehicle)
    assert _entity(hass, "select", "max_current") is None
    assert _entity(hass, "number", "target_soc") is None
    assert _entity(hass, "switch", "auto_unlock") is None
    await c.async_shutdown()


async def test_a_change_sends_the_whole_fresh_profile(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    # The profile changed in the app since the last poll: the fresh copy must be sent.
    fresh = _vehicle(_profile(targetStateOfChargeInPercent=90))
    c, mock = await _setup(hass, mock_entry, _vehicle(_profile()), fresh)
    select = _entity(hass, "select", "max_current")
    with patch(PUT, new=AsyncMock()) as put:
        await hass.services.async_call(
            "select", "select_option", {"entity_id": select, "option": "REDUCED"}, blocking=True
        )
    expected = copy.deepcopy(fresh.charging_profile(7))
    expected["settings"]["maxChargingCurrent"] = "REDUCED"
    put.assert_awaited_once_with(VIN, 7, expected)
    assert mock.await_args_list[-1].kwargs.get("include") == ["chargingProfiles"] or any(
        call.kwargs.get("include") == ["chargingProfiles"] or call.args[1:] == (["chargingProfiles"],)
        for call in mock.await_args_list
    )
    state = hass.states.get(select)
    assert state.state == "REDUCED"
    assert state.attributes["pending"] is True
    c._cancel_refresh()
    await c.async_shutdown()


async def test_target_and_auto_unlock_change_their_own_setting(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    cached = _vehicle(_profile())
    c, _ = await _setup(hass, mock_entry, cached)
    with patch(PUT, new=AsyncMock()) as put:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": _entity(hass, "number", "target_soc"), "value": 100},
            blocking=True,
        )
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": _entity(hass, "switch", "auto_unlock")}, blocking=True
        )
    first, second = (call.args[2]["settings"] for call in put.await_args_list)
    assert first["targetStateOfChargeInPercent"] == 100
    assert second["autoUnlockPlugWhenCharged"] == "PERMANENT"
    # Everything else of the profile is kept as it was.
    assert second["minBatteryStateOfCharge"] == cached.charging_profile(7)["settings"][
        "minBatteryStateOfCharge"
    ]
    c._cancel_refresh()
    await c.async_shutdown()


async def test_profile_gone_in_the_fresh_data_sends_nothing(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    c, _ = await _setup(hass, mock_entry, _vehicle(_profile()), _vehicle(None))
    select = _entity(hass, "select", "max_current")
    with patch(PUT, new=AsyncMock()) as put, pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": select, "option": "REDUCED"}, blocking=True
        )
    put.assert_not_awaited()
    assert c.expected(VIN, "profile_7_max_current") is None
    await c.async_shutdown()


async def test_charging_location_sensor_shows_the_current_profile(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    vehicle = _vehicle(_profile())
    vehicle.data["charging"] = {"isVehicleInSavedLocation": True}
    vehicle.data["chargingProfiles"]["currentVehiclePositionProfile"] = {
        "id": 7,
        "name": "Home",
        "targetStateOfChargeInPercent": 80,
        "nextChargingTime": "22:00",
    }
    c, _ = await _setup(hass, mock_entry, vehicle)
    sensor = er.async_get(hass).async_get_entity_id(
        "sensor", "skoda_api_connect", f"{VIN}_charging_location_profile"
    )
    state = hass.states.get(sensor)
    assert state.state == "Home"
    assert state.attributes["profile_id"] == 7
    assert state.attributes["target_state_of_charge"] == 80
    assert state.attributes["next_charging_time"] == "22:00"
    assert state.attributes["profiles"] == [{"id": 7, "name": "Home"}]
    await c.async_shutdown()
