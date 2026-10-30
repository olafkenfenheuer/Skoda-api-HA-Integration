"""Button platform for the Škoda API Connect integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import WAKE_STOP_COMMANDS, SkodaConfigEntry, SkodaDataUpdateCoordinator
from .entity import SkodaVehicleEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Škoda API Connect refresh button from a config entry."""
    coordinator = entry.runtime_data
    entities: list[SkodaVehicleEntity] = []
    for vin, vehicle in coordinator.data.vehicles.items():
        entities.append(SkodaRefreshButton(coordinator, vin))
        if vehicle.supports("setChargeMode") or any(
            vehicle.lists(operation) for operation, *_ in WAKE_STOP_COMMANDS
        ):
            entities.append(SkodaWakeButton(coordinator, vin))
    async_add_entities(entities)


class SkodaRefreshButton(SkodaVehicleEntity, ButtonEntity):
    """Polls the vehicle immediately (one request of the API quota)."""

    _attr_translation_key = "refresh"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the button."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_refresh"

    @property
    def available(self) -> bool:
        """Stay available while polling fails, so a refresh can be retried."""
        return True

    async def async_press(self) -> None:
        """Refresh the vehicle."""
        await self.coordinator.async_refresh_vehicle(self.vin)


class SkodaWakeButton(SkodaVehicleEntity, ButtonEntity):
    """Tries to wake the vehicle, see ``SkodaDataUpdateCoordinator.async_wake_vehicle``."""

    _attr_translation_key = "wake"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the button."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_wake"

    @property
    def available(self) -> bool:
        """Stay available while polling fails, which is when the car may need waking."""
        return True

    async def async_press(self) -> None:
        """Wake the vehicle."""
        await self.coordinator.async_wake_vehicle(self.vin)
