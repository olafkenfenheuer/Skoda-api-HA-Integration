"""Tests for the values the API reports that only matter for a closer look."""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.skoda_api_connect.api import SkodaVehicle

from .conftest import VIN

GET = "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle"
URL = "https://example.test/render.png"

DATA = {
    "name": "Car 1",
    "licensePlate": "AB1234",
    "renderUrl": URL,
    "charging": {
        "status": {
            "state": "CHARGING",
            "chargeType": "AC",
            "fullyChargedAt": "2026-11-02T20:00:00Z",
        },
        "settings": {
            "batteryCareModeTargetValueInPercent": 80,
            "chargingCareMode": "ACTIVATED",
            "maxChargeCurrentAc": "REDUCED",
            "maxChargeCurrentAcAmpere": 10,
            "autoUnlockPlugWhenCharged": "PERMANENT",
        },
    },
    "airConditioning": {
        "state": "OFF",
        "estimatedReachOfTargetTemperatureAt": "2026-11-02T08:00:00Z",
        "airConditioningAtUnlock": True,
        "airConditioningWithoutExternalPower": False,
        "windowHeating": {"enabled": True, "front": "ON", "rear": "OFF"},
    },
    "auxiliaryHeating": {
        "state": "OFF",
        "estimatedReachOfTargetTemperatureAt": "2026-11-02T09:00:00Z",
    },
    "fuelStatus": {"carType": "HYBRID"},
    "status": {"detail": {"sunroof": "OPEN", "trunk": "CLOSED", "bonnet": "CLOSED"}},
    "parkingPosition": {
        "state": "PARKED",
        "gpsCoordinates": {"latitude": 50.0, "longitude": 7.0},
    },
}


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, data: dict):
    entry.add_to_hass(hass)
    with patch(GET, new=AsyncMock(return_value=SkodaVehicle(vin=VIN, data=data))):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry.runtime_data


def _state(hass: HomeAssistant, domain: str, key: str) -> str | None:
    entity_id = er.async_get(hass).async_get_entity_id(
        domain, "skoda_api_connect", f"{VIN}_{key}"
    )
    state = hass.states.get(entity_id) if entity_id else None
    return state.state if state else None


@pytest.mark.parametrize(
    ("domain", "key", "expected"),
    [
        ("sensor", "charge_type", "AC"),
        ("sensor", "battery_care_target", "80"),
        ("sensor", "max_charge_current_ac", "REDUCED"),
        ("sensor", "max_charge_current_ac_ampere", "10"),
        ("sensor", "fully_charged_at", "2026-11-02T20:00:00+00:00"),
        ("sensor", "air_conditioning_reach", "2026-11-02T08:00:00+00:00"),
        ("sensor", "aux_heating_reach", "2026-11-02T09:00:00+00:00"),
        ("sensor", "fuel_car_type", "HYBRID"),
        ("binary_sensor", "charging_care_mode", "on"),
        ("binary_sensor", "vehicle_auto_unlock", "on"),
        ("binary_sensor", "window_heating_front", "on"),
        ("binary_sensor", "window_heating_rear", "off"),
        ("binary_sensor", "window_heating_enabled", "on"),
        ("binary_sensor", "air_conditioning_at_unlock", "on"),
        ("binary_sensor", "air_conditioning_without_external_power", "off"),
        ("binary_sensor", "sunroof_open", "on"),
    ],
)
async def test_values_are_shown(
    hass: HomeAssistant, mock_entry: MockConfigEntry, domain: str, key: str, expected: str
) -> None:
    coordinator = await _setup(hass, mock_entry, DATA)
    assert _state(hass, domain, key) == expected
    await coordinator.async_shutdown()


async def test_the_license_plate_is_off_by_default(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    coordinator = await _setup(hass, mock_entry, DATA)
    entry = er.async_get(hass).async_get(
        er.async_get(hass).async_get_entity_id(
            "sensor", "skoda_api_connect", f"{VIN}_license_plate"
        )
    )
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    await coordinator.async_shutdown()


async def test_fully_charged_at_only_while_charging(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    data = copy.deepcopy(DATA)
    data["charging"]["status"]["state"] = "CONNECT_CABLE"
    coordinator = await _setup(hass, mock_entry, data)
    assert _state(hass, "sensor", "fully_charged_at") == "unknown"
    await coordinator.async_shutdown()


async def test_nothing_for_values_the_vehicle_does_not_report(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    data = copy.deepcopy(DATA)
    data["airConditioning"]["windowHeating"] = {"enabled": False, "front": "UNSUPPORTED"}
    data["status"]["detail"]["sunroof"] = "UNSUPPORTED"
    del data["fuelStatus"], data["auxiliaryHeating"], data["charging"]["settings"]
    coordinator = await _setup(hass, mock_entry, data)
    for domain, key in (
        ("binary_sensor", "window_heating_front"),
        ("binary_sensor", "window_heating_rear"),
        ("binary_sensor", "sunroof_open"),
        ("binary_sensor", "charging_care_mode"),
        ("sensor", "fuel_car_type"),
        ("sensor", "aux_heating_reach"),
        ("sensor", "max_charge_current_ac"),
    ):
        assert (
            er.async_get(hass).async_get_entity_id(domain, "skoda_api_connect", f"{VIN}_{key}")
            is None
        ), key
    assert _state(hass, "binary_sensor", "window_heating_enabled") == "off"
    await coordinator.async_shutdown()


async def test_the_render_is_the_picture_of_the_tracker(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    coordinator = await _setup(hass, mock_entry, DATA)
    tracker = er.async_get(hass).async_get_entity_id(
        "device_tracker", "skoda_api_connect", f"{VIN}_location"
    )
    assert hass.states.get(tracker).attributes["entity_picture"] == URL
    await coordinator.async_shutdown()
