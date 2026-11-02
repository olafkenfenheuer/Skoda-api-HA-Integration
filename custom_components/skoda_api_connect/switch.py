"""Switch platform for the Škoda API Connect integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KEY_PLUGGED_IN
from .coordinator import Expectation, SkodaConfigEntry, SkodaDataUpdateCoordinator
from .entity import SkodaProfileEntity, SkodaVehicleEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Škoda API Connect switches from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            SkodaChargingSwitch(coordinator, vin)
            for vin, vehicle in coordinator.data.vehicles.items()
            if vehicle.has("charging", "status") and vehicle.supports("startCharging")
        ]
        + [SkodaPluggedInPollingSwitch(coordinator, vin) for vin in coordinator.data.vehicles]
        + [
            SkodaProfileAutoUnlockSwitch(
                coordinator, vin, profile["id"], str(profile.get("name") or profile["id"])
            )
            for vin, vehicle in coordinator.data.vehicles.items()
            if vehicle.lists("updateChargingProfile")
            for profile in vehicle.charging_profiles()
        ]
    )


class SkodaChargingSwitch(SkodaVehicleEntity, SwitchEntity):
    """Starts and stops charging."""

    _attr_translation_key = "charging"
    _expected_key = "charging"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_charging"

    @property
    def is_on(self) -> bool | None:
        """Return true if the vehicle is currently charging."""
        if (expected := self._expected()) is not None:
            return expected
        state = self.vehicle.get("charging", "status", "state")
        return None if state is None else state == "CHARGING"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start charging."""
        await self.coordinator.async_command(
            self.vin,
            self.coordinator.api.start_charging(self.vin),
            Expectation("charging", True, "charging"),
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop charging."""
        await self.coordinator.async_command(
            self.vin,
            self.coordinator.api.stop_charging(self.vin),
            Expectation("charging", False, "charging"),
        )


class SkodaPluggedInPollingSwitch(SkodaVehicleEntity, SwitchEntity):
    """Use the charging polling interval while the cable is plugged in (per vehicle).

    Overrides the global option of the integration for this vehicle.
    """

    _attr_translation_key = "poll_when_plugged_in"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_poll_when_plugged_in"

    @property
    def is_on(self) -> bool:
        """Return whether a plugged-in cable selects the charging interval."""
        return self.coordinator.plugged_in_fast_polling(self.vin)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the faster interval while plugged in."""
        self.coordinator.set_vehicle_option(self.vin, KEY_PLUGGED_IN, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the faster interval while plugged in."""
        self.coordinator.set_vehicle_option(self.vin, KEY_PLUGGED_IN, False)
        self.async_write_ha_state()


class SkodaProfileAutoUnlockSwitch(SkodaProfileEntity, SwitchEntity):
    """Whether the plug is unlocked when charging with a charging profile has finished."""

    _attr_translation_key = "profile_auto_unlock"
    _key = "auto_unlock"
    _setting = "autoUnlockPlugWhenCharged"

    @property
    def is_on(self) -> bool | None:
        """Return true if the plug is unlocked automatically (the API calls it PERMANENT)."""
        value = self._value
        return None if value is None else value == "PERMANENT"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Unlock the plug automatically when charging has finished."""
        await self._async_set("PERMANENT")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Do not unlock the plug automatically."""
        await self._async_set("OFF")
