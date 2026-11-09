"""Tests for keeping the last known data of sections the API cannot retrieve right now."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.skoda_api_connect.api import SkodaVehicle

from .conftest import VIN

GET = "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle"

_PATCHERS: list = []


@pytest.fixture(autouse=True)
def _stop_patches():
    """Stop the get_vehicle patches the tests start, after each test."""
    yield
    while _PATCHERS:
        _PATCHERS.pop().stop()


CLIMATE = {
    "state": "OFF",
    "targetTemperature": {"value": 21.0, "unit": "CELSIUS"},
    "carCapturedTimestamp": "2026-11-01T10:00:00Z",
}


def _data(*, climate: bool) -> dict:
    data: dict = {
        "name": "Car 1",
        "charging": {"status": {"state": "CONNECT_CABLE"}},
    }
    if climate:
        data["airConditioning"] = dict(CLIMATE)
    return data


def _climate(hass: HomeAssistant) -> str | None:
    return er.async_get(hass).async_get_entity_id(
        "climate", "skoda_api_connect", f"{VIN}_air_conditioning"
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, vehicle: SkodaVehicle):
    entry.add_to_hass(hass)
    mock = AsyncMock(return_value=vehicle)
    # The patch stays active after the setup: later polls fetch the vehicle again.
    patcher = patch(GET, new=mock)
    patcher.start()
    _PATCHERS.append(patcher)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data, mock


async def test_startup_without_the_climate_data_uses_the_stored_copy(
    hass: HomeAssistant, mock_entry: MockConfigEntry, hass_storage
) -> None:
    key = f"skoda_api_connect.{mock_entry.entry_id}"
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {VIN: _data(climate=True)},
    }
    vehicle = SkodaVehicle(
        vin=VIN, data=_data(climate=False), errors=["AIR_CONDITIONING_UNAVAILABLE"]
    )
    coordinator, _ = await _setup(hass, mock_entry, vehicle)
    # The entity exists although the API did not deliver the section, ...
    assert _climate(hass) is not None
    # ... with the last known data, whose timestamp stays the old one.
    kept = coordinator.data.vehicles[VIN].data["airConditioning"]
    assert kept["carCapturedTimestamp"] == "2026-11-01T10:00:00Z"
    # The API status still reports that the part was missing.
    assert coordinator.poll_results[VIN].omitted == ["AIR_CONDITIONING_UNAVAILABLE"]
    await coordinator.async_shutdown()


async def test_a_later_poll_keeps_the_section_of_the_previous_one(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    coordinator, mock = await _setup(
        hass, mock_entry, SkodaVehicle(vin=VIN, data=_data(climate=True))
    )
    mock.return_value = SkodaVehicle(
        vin=VIN, data=_data(climate=False), errors=["AIR_CONDITIONING_UNAVAILABLE"]
    )
    coordinator._force.add(VIN)
    await coordinator.async_refresh()
    assert coordinator.data.vehicles[VIN].data["airConditioning"]["state"] == "OFF"
    await coordinator.async_shutdown()


async def test_unsupported_or_without_a_copy_is_not_filled_in(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    coordinator, mock = await _setup(
        hass, mock_entry, SkodaVehicle(vin=VIN, data=_data(climate=True))
    )
    # Unsupported (not just unavailable): the section stays missing.
    mock.return_value = SkodaVehicle(
        vin=VIN, data=_data(climate=False), errors=["AIR_CONDITIONING_UNSUPPORTED"]
    )
    coordinator._force.add(VIN)
    await coordinator.async_refresh()
    assert "airConditioning" not in coordinator.data.vehicles[VIN].data
    await coordinator.async_shutdown()


async def test_startup_without_a_stored_copy_stays_missing(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    vehicle = SkodaVehicle(
        vin=VIN, data=_data(climate=False), errors=["AIR_CONDITIONING_UNAVAILABLE"]
    )
    coordinator, _ = await _setup(hass, mock_entry, vehicle)
    assert "airConditioning" not in coordinator.data.vehicles[VIN].data
    assert _climate(hass) is None
    await coordinator.async_shutdown()
