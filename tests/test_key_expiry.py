"""Tests for the API key expiry sensor."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.skoda_api_connect.api import _key_expiry

from .conftest import VIN


def test_key_expiry_header() -> None:
    headers = {"x-api-key-expires-at": "2027-04-06T13:54:21.23Z"}
    assert _key_expiry(headers) == datetime(2027, 4, 6, 13, 54, 21, 230000, tzinfo=UTC)


def test_key_expiry_missing_or_invalid() -> None:
    assert _key_expiry({}) is None
    assert _key_expiry({"x-api-key-expires-at": "soon"}) is None


async def test_key_expiry_sensor(hass: HomeAssistant, mock_entry: MockConfigEntry, mock_get_vehicle):
    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id("sensor", "skoda_api_connect", f"{VIN}_api_key_expires")
    assert hass.states.get(entity_id).state == "unknown"  # no response header seen yet

    mock_entry.runtime_data.api.key_expires_at = datetime(2027, 4, 6, 13, 54, 21, tzinfo=UTC)
    await mock_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == "2027-04-06T13:54:21+00:00"
    assert state.attributes["device_class"] == "timestamp"
