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


_PATCHERS: list = []


@pytest.fixture(autouse=True)
def _stop_patches():
    """Stop the get_vehicle patches the tests start, after each test."""
    yield
    while _PATCHERS:
        _PATCHERS.pop().stop()


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
    # The patch stays active after the setup: commands and polls fetch the vehicle again.
    patcher = patch(GET, new=mock)
    patcher.start()
    _PATCHERS.append(patcher)
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


async def test_minimum_charge_entities(hass: HomeAssistant, mock_entry: MockConfigEntry) -> None:
    c, _ = await _setup(hass, mock_entry, _vehicle(_profile()))
    assert float(hass.states.get(_entity(hass, "number", "min_charge")).state) == 20
    assert hass.states.get(_entity(hass, "switch", "min_charge_enabled")).state == "on"
    with patch(PUT, new=AsyncMock()) as put:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": _entity(hass, "number", "min_charge"), "value": 30},
            blocking=True,
        )
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": _entity(hass, "switch", "min_charge_enabled")},
            blocking=True,
        )
    first, second = (call.args[2]["settings"]["minBatteryStateOfCharge"] for call in put.await_args_list)
    assert first == {"enabled": True, "minimumBatteryStateOfChargeInPercent": 30}
    assert second == {"enabled": False, "minimumBatteryStateOfChargeInPercent": 20}
    c._cancel_refresh()
    await c.async_shutdown()


async def test_switch_for_the_minimum_charge_only_if_the_vehicle_reports_it(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    # Like a vehicle that reports only the value, without "enabled".
    profile = _profile()
    profile["settings"]["minBatteryStateOfCharge"] = {"minimumBatteryStateOfChargeInPercent": 0}
    c, _ = await _setup(hass, mock_entry, _vehicle(profile))
    assert _entity(hass, "number", "min_charge") is not None
    assert _entity(hass, "switch", "min_charge_enabled") is None
    await c.async_shutdown()


async def test_action_changes_the_given_fields_of_the_whole_profile(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    cached = _vehicle(_profile())
    c, _ = await _setup(hass, mock_entry, cached)
    with patch(PUT, new=AsyncMock()) as put:
        await hass.services.async_call(
            "skoda_api_connect",
            "update_charging_profile",
            {
                "entity_id": [_entity(hass, "select", "max_current")],
                "max_charging_current": "REDUCED",
                "preferred_charging_times": [{"id": 1, "enabled": False, "start": "23:00"}],
                "timers": [{"id": 3, "enabled": True, "time": "08:30", "days": ["MONDAY"]}],
            },
            blocking=True,
        )
    body = put.await_args.args[2]
    assert body["settings"]["maxChargingCurrent"] == "REDUCED"
    assert body["settings"]["targetStateOfChargeInPercent"] == 80  # untouched
    assert body["preferredChargingTimes"] == [
        {"id": 1, "enabled": False, "startTime": "23:00", "endTime": "06:00"}
    ]
    assert body["timers"] == [
        {"id": 3, "enabled": True, "time": "08:30", "type": "RECURRING", "recurringOn": ["MONDAY"]}
    ]
    c._cancel_refresh()
    await c.async_shutdown()


async def test_action_refuses_what_it_cannot_apply(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    from homeassistant.exceptions import ServiceValidationError

    c, _ = await _setup(hass, mock_entry, _vehicle(_profile()))
    select = _entity(hass, "select", "max_current")
    refuse = pytest.raises((HomeAssistantError, ServiceValidationError))
    with patch(PUT, new=AsyncMock()) as put:
        with refuse:  # a timer the profile does not have
            await hass.services.async_call(
                "skoda_api_connect",
                "update_charging_profile",
                {"entity_id": [select], "timers": [{"id": 9, "enabled": True}]},
                blocking=True,
            )
        with refuse:  # nothing to change
            await hass.services.async_call(
                "skoda_api_connect", "update_charging_profile", {"entity_id": [select]}, blocking=True
            )
        with refuse:  # not an entity of a charging profile
            await hass.services.async_call(
                "skoda_api_connect",
                "update_charging_profile",
                {"entity_id": ["sensor.auto_enyaq_letzter_abruf"], "target_charge": 90},
                blocking=True,
            )
    put.assert_not_awaited()
    await c.async_shutdown()


async def test_action_counts_slots_by_position_or_by_the_id_of_the_api(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    # A second profile of a vehicle starts at 5: the ids count across all profiles.
    profile = _profile()
    profile["preferredChargingTimes"] = [
        {"id": 5, "enabled": False, "startTime": "22:00", "endTime": "06:00"},
        {"id": 6, "enabled": False, "startTime": "22:00", "endTime": "06:00"},
    ]
    profile["timers"] = [{"id": 4, "enabled": False, "time": "07:00", "type": "RECURRING"}]
    c, _ = await _setup(hass, mock_entry, _vehicle(profile))
    select = _entity(hass, "select", "max_current")
    with patch(PUT, new=AsyncMock()) as put:
        await hass.services.async_call(
            "skoda_api_connect",
            "update_charging_profile",
            {
                "entity_id": [select],
                "preferred_charging_times": [
                    {"number": 2, "enabled": True},  # the second one of the profile: id 6
                    {"id": 5, "end": "05:00"},  # the id the API reports
                ],
                "timers": [{"number": 1, "time": "08:00"}],  # id 4
            },
            blocking=True,
        )
    body = put.await_args.args[2]
    assert body["preferredChargingTimes"] == [
        {"id": 5, "enabled": False, "startTime": "22:00", "endTime": "05:00"},
        {"id": 6, "enabled": True, "startTime": "22:00", "endTime": "06:00"},
    ]
    assert body["timers"][0]["time"] == "08:00"
    c._cancel_refresh()
    await c.async_shutdown()


async def test_action_refuses_a_slot_without_number_or_id_and_one_that_is_not_there(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    import voluptuous as vol

    c, _ = await _setup(hass, mock_entry, _vehicle(_profile()))
    select = _entity(hass, "select", "max_current")
    with patch(PUT, new=AsyncMock()) as put:
        with pytest.raises(vol.Invalid):  # neither number nor id
            await hass.services.async_call(
                "skoda_api_connect",
                "update_charging_profile",
                {"entity_id": [select], "timers": [{"enabled": True}]},
                blocking=True,
            )
        with pytest.raises(HomeAssistantError):  # the profile has no fifth timer
            await hass.services.async_call(
                "skoda_api_connect",
                "update_charging_profile",
                {"entity_id": [select], "timers": [{"number": 5, "enabled": True}]},
                blocking=True,
            )
    put.assert_not_awaited()
    await c.async_shutdown()
