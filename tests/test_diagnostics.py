"""Tests for the diagnostics download."""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.skoda_api_connect.const import KEY_PLUGGED_IN
from custom_components.skoda_api_connect.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import VIN


async def test_diagnostics_do_not_leak_identifiers(
    hass: HomeAssistant, mock_entry: MockConfigEntry, mock_get_vehicle
) -> None:
    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    mock_entry.runtime_data.set_vehicle_option(VIN, KEY_PLUGGED_IN, True)

    result = await async_get_config_entry_diagnostics(hass, mock_entry)

    assert result["options"]["vehicle_intervals"] == {"vehicle_1": {KEY_PLUGGED_IN: True}}
    assert result["vehicles"]["vehicle_1"]["data"]["name"] == "**REDACTED**"
    dump = json.dumps(result)
    assert VIN not in dump
    assert f"Car {VIN[-1]}" not in dump


async def test_diagnostics_redact_charging_profile_names(hass: HomeAssistant, mock_entry) -> None:
    from unittest.mock import AsyncMock, patch

    from custom_components.skoda_api_connect.api import SkodaVehicle

    vehicle = SkodaVehicle(
        vin=VIN,
        data={
            "name": "Car 1",
            "chargingProfiles": {
                "profiles": [{"id": 1, "name": "Musterweg 1", "settings": {}}],
                "currentVehiclePositionProfile": {"id": 1, "name": "Musterweg 1"},
            },
        },
    )
    mock_entry.add_to_hass(hass)
    with patch(
        "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle",
        new=AsyncMock(return_value=vehicle),
    ):
        await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, mock_entry)

    profiles = result["vehicles"]["vehicle_1"]["data"]["chargingProfiles"]
    assert profiles["profiles"][0]["name"] == "**REDACTED**"
    assert profiles["profiles"][0]["id"] == 1
    assert profiles["currentVehiclePositionProfile"]["name"] == "**REDACTED**"
    assert "Musterweg" not in json.dumps(result)
    await mock_entry.runtime_data.async_shutdown()
