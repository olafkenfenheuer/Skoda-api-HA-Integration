"""Device tracker platform for the Škoda API Connect integration."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SkodaConfigEntry, SkodaDataUpdateCoordinator
from .entity import SkodaVehicleEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Škoda API Connect device tracker from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        SkodaDeviceTracker(coordinator, vin)
        for vin, vehicle in coordinator.data.vehicles.items()
        if vehicle.has("parkingPosition")
    )


class SkodaDeviceTracker(SkodaVehicleEntity, TrackerEntity):
    """Represents the parking position of a Škoda vehicle."""

    _attr_translation_key = "vehicle_location"
    _attr_icon = "mdi:car"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the device tracker."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_location"

    @property
    def entity_picture(self) -> str | None:
        """Return the render of the vehicle, shown as its marker on the map."""
        url = self.vehicle.get("renderUrl")
        return url if isinstance(url, str) and url.startswith("https://") else None

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device tracker."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return the latitude of the vehicle (unknown while driving)."""
        return self.vehicle.get("parkingPosition", "gpsCoordinates", "latitude")

    @property
    def longitude(self) -> float | None:
        """Return the longitude of the vehicle (unknown while driving)."""
        return self.vehicle.get("parkingPosition", "gpsCoordinates", "longitude")
