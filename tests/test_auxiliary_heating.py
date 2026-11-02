"""Tests for the auxiliary heating (climate entity, S-PIN, duration)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.skoda_api_connect.api import SkodaVehicle
from custom_components.skoda_api_connect.const import (
    CONF_API_KEY,
    CONF_SPIN,
    CONF_VINS,
    DOMAIN,
    KEY_AUX_DURATION,
)
from custom_components.skoda_api_connect.diagnostics import async_get_config_entry_diagnostics

from .conftest import VIN

GET = "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle"
API = "custom_components.skoda_api_connect.api.SkodaApi"


def _vehicle(*, state: str = "OFF", operations=("startAuxiliaryHeating", "stopAuxiliaryHeating")):
    return SkodaVehicle(
        vin=VIN,
        data={
            "name": "Car 1",
            "operations": [{"name": name} for name in operations],
            "auxiliaryHeating": {"state": state, "targetTemperature": {"value": 20.0}},
        },
    )


def _entry(spin: str | None = "1234") -> MockConfigEntry:
    options = {CONF_SPIN: spin} if spin else {}
    return MockConfigEntry(
        domain=DOMAIN, data={CONF_API_KEY: "key", CONF_VINS: [VIN]}, options=options
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, vehicle: SkodaVehicle):
    entry.add_to_hass(hass)
    with patch(GET, new=AsyncMock(return_value=vehicle)):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry.runtime_data


def _climate(hass: HomeAssistant) -> str | None:
    return er.async_get(hass).async_get_entity_id(
        "climate", "skoda_api_connect", f"{VIN}_auxiliary_heating"
    )


async def test_only_created_if_the_vehicle_lists_the_operation(hass: HomeAssistant) -> None:
    c = await _setup(hass, _entry(), _vehicle(operations=("stopAuxiliaryHeating",)))
    assert _climate(hass) is None
    await c.async_shutdown()


async def test_start_heating_sends_spin_duration_and_temperature(hass: HomeAssistant) -> None:
    c = await _setup(hass, _entry(), _vehicle())
    with patch(f"{API}.start_auxiliary_heating", new=AsyncMock()) as start:
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": _climate(hass), "hvac_mode": "heat"},
            blocking=True,
        )
    start.assert_awaited_once_with(
        VIN, "1234", mode="HEATING", duration_seconds=30 * 60, temperature=20.0
    )
    state = hass.states.get(_climate(hass))
    assert state.state == "heat"
    assert state.attributes["pending"] is True
    c._cancel_refresh()
    await c.async_shutdown()


async def test_ventilation_mode_and_configured_duration(hass: HomeAssistant) -> None:
    c = await _setup(hass, _entry(), _vehicle())
    c.set_vehicle_option(VIN, KEY_AUX_DURATION, 45)
    with patch(f"{API}.start_auxiliary_heating", new=AsyncMock()) as start:
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": _climate(hass), "hvac_mode": "fan_only"},
            blocking=True,
        )
    assert start.await_args.kwargs["mode"] == "VENTILATION"
    assert start.await_args.kwargs["duration_seconds"] == 45 * 60
    c._cancel_refresh()
    await c.async_shutdown()


async def test_start_without_spin_sends_nothing(hass: HomeAssistant) -> None:
    c = await _setup(hass, _entry(spin=None), _vehicle())
    with (
        patch(f"{API}.start_auxiliary_heating", new=AsyncMock()) as start,
        pytest.raises(HomeAssistantError, match="S-PIN"),
    ):
        await hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": _climate(hass), "hvac_mode": "heat"},
            blocking=True,
        )
    start.assert_not_awaited()
    await c.async_shutdown()


async def test_stop_while_running(hass: HomeAssistant) -> None:
    c = await _setup(hass, _entry(), _vehicle(state="HEATING_AUXILIARY"))
    assert hass.states.get(_climate(hass)).state == "heat"
    with patch(f"{API}.stop_auxiliary_heating", new=AsyncMock()) as stop:
        await hass.services.async_call(
            "climate", "set_hvac_mode", {"entity_id": _climate(hass), "hvac_mode": "off"}, blocking=True
        )
    stop.assert_awaited_once_with(VIN)
    c._cancel_refresh()
    await c.async_shutdown()


async def test_polls_faster_while_it_runs(hass: HomeAssistant) -> None:
    c = await _setup(hass, _entry(), _vehicle(state="PREHEATING"))
    assert c.is_climate_active(VIN)
    await c.async_shutdown()


async def test_diagnostics_do_not_contain_the_spin(hass: HomeAssistant) -> None:
    entry = _entry()
    c = await _setup(hass, entry, _vehicle())
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert "1234" not in json.dumps(result)
    assert result["options"][CONF_SPIN] == "**REDACTED**"
    await c.async_shutdown()


async def test_not_offered_if_the_function_is_unsupported(hass: HomeAssistant) -> None:
    c = await _setup(hass, _entry(), _vehicle(state="UNSUPPORTED"))
    assert _climate(hass) is None
    number = er.async_get(hass).async_get_entity_id(
        "number", "skoda_api_connect", f"{VIN}_aux_duration"
    )
    assert number is None
    await c.async_shutdown()


async def test_spin_field_only_if_a_vehicle_has_the_heating(hass: HomeAssistant) -> None:
    with_heating = _entry()
    c = await _setup(hass, with_heating, _vehicle())
    result = await hass.config_entries.options.async_init(with_heating.entry_id)
    assert CONF_SPIN in [str(key) for key in result["data_schema"].schema]
    await c.async_shutdown()


async def test_no_spin_field_without_a_heating(hass: HomeAssistant) -> None:
    without = _entry()
    c = await _setup(hass, without, _vehicle(operations=("startCharging",)))
    result = await hass.config_entries.options.async_init(without.entry_id)
    assert CONF_SPIN not in [str(key) for key in result["data_schema"].schema]
    await c.async_shutdown()
