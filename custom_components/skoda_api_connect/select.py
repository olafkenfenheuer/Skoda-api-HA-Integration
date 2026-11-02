"""Select platform for the Škoda API Connect integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import SkodaVehicle
from .coordinator import Expectation, SkodaConfigEntry, SkodaDataUpdateCoordinator
from .entity import SkodaProfileEntity, SkodaVehicleEntity


def _has_charge_modes(vehicle: SkodaVehicle) -> bool:
    return bool(vehicle.get("charging", "settings", "availableChargeModes"))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Škoda API Connect charge mode select from a config entry."""
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = []
    for vin, vehicle in coordinator.data.vehicles.items():
        if _has_charge_modes(vehicle):
            entities.append(SkodaChargeModeSelect(coordinator, vin))
        if vehicle.lists("updateChargingProfile"):
            entities.extend(
                SkodaProfileMaxCurrentSelect(
                    coordinator, vin, profile["id"], str(profile.get("name") or profile["id"])
                )
                for profile in vehicle.charging_profiles()
            )
    async_add_entities(entities)


class SkodaChargeModeSelect(SkodaVehicleEntity, SelectEntity):
    """Represents the preferred charge mode (e.g. MANUAL, TIMER)."""

    _attr_translation_key = "charge_mode"
    _expected_key = "charge_mode"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_charge_mode"

    @property
    def options(self) -> list[str]:
        """Return the charge modes the vehicle offers."""
        return list(self.vehicle.get("charging", "settings", "availableChargeModes") or [])

    @property
    def current_option(self) -> str | None:
        """Return the active charge mode."""
        if (expected := self._expected()) is not None:
            return expected
        return self.vehicle.get("charging", "settings", "preferredChargeMode")

    async def async_select_option(self, option: str) -> None:
        """Change the charge mode."""
        await self.coordinator.async_command(
            self.vin,
            self.coordinator.api.set_charge_mode(self.vin, option),
            Expectation("charge_mode", option, "charging"),
        )


class SkodaProfileMaxCurrentSelect(SkodaProfileEntity, SelectEntity):
    """The maximum charging current of a charging profile (saved charging location)."""

    _attr_translation_key = "profile_max_current"
    _key = "max_current"
    _setting = ("maxChargingCurrent",)
    _attr_options = ["MAXIMUM", "REDUCED"]

    @property
    def options(self) -> list[str]:
        """Return the known values, plus the current one if the vehicle reports another."""
        current = self._value
        if isinstance(current, str) and current not in self._attr_options:
            return [*self._attr_options, current]
        return self._attr_options

    @property
    def current_option(self) -> str | None:
        """Return the maximum charging current of the profile."""
        value = self._value
        return value if isinstance(value, str) else None

    async def async_select_option(self, option: str) -> None:
        """Change the maximum charging current of the profile."""
        await self._async_set(option)
