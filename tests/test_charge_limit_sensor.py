"""Tests for the read-only charge limit sensor."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import VIN, make_vehicle

GET = "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle"


def _entity_id(hass: HomeAssistant, platform: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, "skoda_api_connect", f"{VIN}_charge_limit")


async def test_charge_limit_sensor(hass: HomeAssistant, mock_entry: MockConfigEntry):
    vehicle = make_vehicle()
    vehicle.data["charging"]["settings"]["targetStateOfChargeInPercent"] = 80
    mock_entry.add_to_hass(hass)
    with patch(GET, new=AsyncMock(return_value=vehicle)):
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()
    state = hass.states.get(_entity_id(hass, "sensor"))
    assert state.state == "80"
    assert state.attributes["unit_of_measurement"] == "%"
    assert float(hass.states.get(_entity_id(hass, "number")).state) == 80


async def test_charge_limit_sensor_missing(hass: HomeAssistant, mock_entry: MockConfigEntry):
    vehicle = make_vehicle()
    vehicle.data["charging"].pop("settings", None)
    mock_entry.add_to_hass(hass)
    with patch(GET, new=AsyncMock(return_value=vehicle)):
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()
    assert _entity_id(hass, "sensor") is None


async def test_charge_limit_entities_appear_once_the_vehicle_reports_a_target(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    vehicle = make_vehicle()
    vehicle.data["charging"].pop("settings", None)
    mock_entry.add_to_hass(hass)
    with patch(GET, new=AsyncMock(return_value=vehicle)):
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()
    coordinator = mock_entry.runtime_data
    assert _entity_id(hass, "sensor") is None
    assert _entity_id(hass, "number") is None

    reported = make_vehicle()
    reported.data["charging"]["settings"] = {"targetStateOfChargeInPercent": 80}
    with patch(GET, new=AsyncMock(return_value=reported)):
        coordinator._last_fetch.clear()
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(_entity_id(hass, "sensor")).state == "80"
    assert float(hass.states.get(_entity_id(hass, "number")).state) == 80
    await coordinator.async_shutdown()
