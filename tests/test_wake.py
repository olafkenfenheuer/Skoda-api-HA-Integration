"""Tests for waking the vehicle (button and automatic wake-up of a charging vehicle)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.skoda_api_connect.api import RateLimitInfo, SkodaVehicle
from custom_components.skoda_api_connect.const import KEY_AUTO_WAKE

from .conftest import VIN


def _vehicle(*, charging: bool = True, age: timedelta = timedelta(minutes=45), mode="MANUAL"):
    captured = (dt_util.utcnow() - age).strftime("%Y-%m-%dT%H:%M:%SZ")
    settings = {"preferredChargeMode": mode} if mode else {}
    return SkodaVehicle(
        vin=VIN,
        data={
            "name": "Car 1",
            "charging": {
                "status": {"state": "CHARGING" if charging else "CONNECT_CABLE"},
                "settings": settings,
                "carCapturedTimestamp": captured,
            },
        },
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, vehicle: SkodaVehicle):
    entry.add_to_hass(hass)
    with patch(
        "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle",
        new=AsyncMock(return_value=vehicle),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry.runtime_data


def test_last_captured_is_newest_section() -> None:
    vehicle = SkodaVehicle(
        vin=VIN,
        data={
            "status": {"carCapturedTimestamp": "2026-10-25T10:42:18.935Z"},
            "charging": {"carCapturedTimestamp": "2026-10-25T10:42:21Z"},
            "odometer": {"carCapturedTimestamp": "garbage"},
        },
    )
    assert vehicle.last_captured().isoformat() == "2026-10-25T10:42:21+00:00"
    assert set(vehicle.captured_at()) == {"status", "charging"}
    assert SkodaVehicle(vin=VIN, data={}).last_captured() is None


async def test_wake_button_resends_current_charge_mode(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    coordinator = await _setup(hass, mock_entry, _vehicle())
    button = er.async_get(hass).async_get_entity_id("button", "skoda_api_connect", f"{VIN}_wake")
    with patch(
        "custom_components.skoda_api_connect.api.SkodaApi.set_charge_mode", new=AsyncMock()
    ) as set_mode:
        await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    set_mode.assert_awaited_once_with(VIN, "MANUAL")
    coordinator._cancel_refresh()  # the command schedules a follow-up refresh


async def test_wake_without_known_charge_mode_fails(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    coordinator = await _setup(hass, mock_entry, _vehicle(mode=None))
    with pytest.raises(HomeAssistantError, match="charge mode"):
        await coordinator.async_wake_vehicle(VIN)


async def test_auto_wake_conditions(hass: HomeAssistant, mock_entry: MockConfigEntry) -> None:
    c = await _setup(hass, mock_entry, _vehicle())
    assert not c._should_auto_wake(VIN)  # off by default

    c.set_vehicle_option(VIN, KEY_AUTO_WAKE, 20)
    assert c.auto_wake_minutes(VIN) == 20
    assert c._should_auto_wake(VIN)

    # Not silent long enough.
    c.data.vehicles[VIN] = _vehicle(age=timedelta(minutes=5))
    assert not c._should_auto_wake(VIN)

    # Not charging.
    c.data.vehicles[VIN] = _vehicle(charging=False)
    assert not c._should_auto_wake(VIN)

    # Read-only mode.
    c.data.vehicles[VIN] = _vehicle()
    c.read_only = True
    assert not c._should_auto_wake(VIN)
    c.read_only = False
    assert c._should_auto_wake(VIN)

    # Too little quota left.
    c.api.rate_limits[VIN] = RateLimitInfo(
        limit=20, remaining=5, reset_at=None, updated=dt_util.utcnow()
    )
    assert not c._should_auto_wake(VIN)
    c.api.rate_limits[VIN] = RateLimitInfo(
        limit=20, remaining=6, reset_at=None, updated=dt_util.utcnow()
    )
    assert c._should_auto_wake(VIN)


async def test_auto_wake_waits_between_attempts(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    c = await _setup(hass, mock_entry, _vehicle())
    c.set_vehicle_option(VIN, KEY_AUTO_WAKE, 20)
    with patch(
        "custom_components.skoda_api_connect.api.SkodaApi.set_charge_mode", new=AsyncMock()
    ) as set_mode:
        await c._async_auto_wake(VIN)
    set_mode.assert_awaited_once_with(VIN, "MANUAL")
    assert not c._should_auto_wake(VIN)  # just woken: wait the configured time
    c._cancel_refresh()  # the command schedules a follow-up refresh


async def test_auto_wake_number_enforces_minimum(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    c = await _setup(hass, mock_entry, _vehicle())
    number = er.async_get(hass).async_get_entity_id(
        "number", "skoda_api_connect", f"{VIN}_auto_wake"
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": number, "value": 5}, blocking=True
    )
    assert c.auto_wake_minutes(VIN) == 10
    await hass.services.async_call(
        "number", "set_value", {"entity_id": number, "value": 0}, blocking=True
    )
    assert c.auto_wake_minutes(VIN) == 0


def _no_charge_mode(operations: list[str] | None, **states: str) -> SkodaVehicle:
    """A vehicle without a charge mode (e.g. combustion); ``states`` maps sections to states."""
    data: dict = {"name": "Car 1"}
    if operations is not None:
        data["operations"] = [{"name": name} for name in operations]
    for section, state in states.items():
        data[section] = {"state": state}
    return SkodaVehicle(vin=VIN, data=data)


def _wake_button(hass: HomeAssistant) -> str | None:
    return er.async_get(hass).async_get_entity_id("button", "skoda_api_connect", f"{VIN}_wake")


def test_lists_is_false_when_the_operations_are_unknown() -> None:
    unknown = SkodaVehicle(vin=VIN, data={})
    listed = SkodaVehicle(vin=VIN, data={"operations": [{"name": "stopAirConditioning"}]})
    assert unknown.supports("stopAirConditioning") and not unknown.lists("stopAirConditioning")
    assert listed.lists("stopAirConditioning") and not listed.lists("stopActiveVentilation")


async def test_wake_stops_an_idle_air_conditioning(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    vehicle = _no_charge_mode(["stopAirConditioning"], airConditioning="OFF")
    coordinator = await _setup(hass, mock_entry, vehicle)
    with patch(
        "custom_components.skoda_api_connect.api.SkodaApi.stop_air_conditioning",
        new=AsyncMock(),
    ) as stop:
        await hass.services.async_call(
            "button", "press", {"entity_id": _wake_button(hass)}, blocking=True
        )
    stop.assert_awaited_once_with(VIN)
    coordinator._cancel_refresh()  # the command schedules a follow-up refresh


async def test_wake_prefers_the_charge_mode(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    vehicle = _vehicle()
    vehicle.data["operations"] = [{"name": "setChargeMode"}, {"name": "stopAirConditioning"}]
    vehicle.data["airConditioning"] = {"state": "OFF"}
    coordinator = await _setup(hass, mock_entry, vehicle)
    with (
        patch(
            "custom_components.skoda_api_connect.api.SkodaApi.set_charge_mode", new=AsyncMock()
        ) as set_mode,
        patch(
            "custom_components.skoda_api_connect.api.SkodaApi.stop_air_conditioning",
            new=AsyncMock(),
        ) as stop,
    ):
        await coordinator.async_wake_vehicle(VIN)
    set_mode.assert_awaited_once_with(VIN, "MANUAL")
    stop.assert_not_awaited()
    coordinator._cancel_refresh()


async def test_wake_stops_something_when_the_charge_mode_cannot_be_set(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    vehicle = _vehicle()  # knows its charge mode, but does not list setChargeMode
    vehicle.data["operations"] = [{"name": "stopAirConditioning"}]
    vehicle.data["airConditioning"] = {"state": "COMPLETED"}
    coordinator = await _setup(hass, mock_entry, vehicle)
    with patch(
        "custom_components.skoda_api_connect.api.SkodaApi.stop_air_conditioning",
        new=AsyncMock(),
    ) as stop:
        await coordinator.async_wake_vehicle(VIN)
    stop.assert_awaited_once_with(VIN)
    coordinator._cancel_refresh()


async def test_wake_takes_the_next_command_while_the_air_conditioning_runs(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    vehicle = _no_charge_mode(
        ["stopAirConditioning", "stopAuxiliaryHeating"],
        airConditioning="HEATING",
        auxiliaryHeating="OFF",
    )
    coordinator = await _setup(hass, mock_entry, vehicle)
    with (
        patch(
            "custom_components.skoda_api_connect.api.SkodaApi.stop_air_conditioning",
            new=AsyncMock(),
        ) as stop_ac,
        patch(
            "custom_components.skoda_api_connect.api.SkodaApi.stop_auxiliary_heating",
            new=AsyncMock(),
        ) as stop_aux,
    ):
        await coordinator.async_wake_vehicle(VIN)
    stop_ac.assert_not_awaited()
    stop_aux.assert_awaited_once_with(VIN)
    coordinator._cancel_refresh()


async def test_wake_never_stops_a_running_function(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    vehicle = _no_charge_mode(["stopAirConditioning"], airConditioning="HEATING")
    coordinator = await _setup(hass, mock_entry, vehicle)
    assert not coordinator.supports_wake(VIN)
    with pytest.raises(HomeAssistantError, match="No command to wake"):
        await coordinator.async_wake_vehicle(VIN)


async def test_wake_does_not_guess_without_a_list_of_operations(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    vehicle = _no_charge_mode(None, airConditioning="OFF")
    coordinator = await _setup(hass, mock_entry, vehicle)
    assert not coordinator.supports_wake(VIN)
    with pytest.raises(HomeAssistantError, match="No command to wake"):
        await coordinator.async_wake_vehicle(VIN)


async def test_wake_button_only_if_the_vehicle_can_be_woken(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_entry, _no_charge_mode(["startCharging"], airConditioning="OFF"))
    assert _wake_button(hass) is None
