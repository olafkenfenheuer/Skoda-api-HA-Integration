"""Base entity for the Škoda API Connect integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SkodaVehicle
from .const import DOMAIN, MANUFACTURER
from .coordinator import SkodaDataUpdateCoordinator


class SkodaVehicleEntity(CoordinatorEntity[SkodaDataUpdateCoordinator]):
    """Base class for all entities tied to a single Škoda vehicle."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the entity for a given vehicle VIN."""
        super().__init__(coordinator)
        self.vin = vin
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vin)},
            manufacturer=MANUFACTURER,
            name=self.vehicle.name,
            serial_number=vin,
        )

    # Key of the state a command of this entity is expected to cause (see Expectation).
    _expected_key: str | None = None

    def _expected(self) -> Any | None:
        """Return the state an accepted command should cause, or None if none is pending."""
        if self._expected_key is None:
            return None
        return self.coordinator.expected(self.vin, self._expected_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Mark a state that is only expected, not yet reported by the vehicle."""
        return {"pending": True} if self._expected() is not None else None

    @property
    def vehicle(self) -> SkodaVehicle:
        """Return the current vehicle data from the coordinator."""
        return self.coordinator.data.vehicles[self.vin]

    @property
    def available(self) -> bool:
        """Return True while there is data for this vehicle.

        A failed poll (e.g. rate limit backoff) keeps the last known state instead of
        turning every entity unavailable; the API status sensor shows the failure.
        """
        data = self.coordinator.data
        return data is not None and self.vin in data.vehicles


class SkodaProfileEntity(SkodaVehicleEntity):
    """Base class for an entity of one charging profile (a saved charging location).

    ``_key`` names the entity, ``_setting`` the field of the profile's ``settings`` it shows
    and changes.
    """

    _key: str
    _setting: str

    def __init__(
        self,
        coordinator: SkodaDataUpdateCoordinator,
        vin: str,
        profile_id: int,
        profile_name: str,
    ) -> None:
        """Initialize the entity for one profile of a vehicle."""
        super().__init__(coordinator, vin)
        self.profile_id = profile_id
        self._attr_unique_id = f"{vin}_profile_{profile_id}_{self._key}"
        self._attr_translation_placeholders = {"profile": profile_name}
        self._expected_key = f"profile_{profile_id}_{self._key}"

    @property
    def available(self) -> bool:
        """Return True while the vehicle reports the profile."""
        return super().available and self.vehicle.charging_profile(self.profile_id) is not None

    @property
    def _value(self) -> Any:
        """Return the reported value of the setting, or the one a command is expected to set."""
        if (expected := self._expected()) is not None:
            return expected
        profile = self.vehicle.charging_profile(self.profile_id)
        settings = profile.get("settings") if profile else None
        return settings.get(self._setting) if isinstance(settings, dict) else None

    async def _async_set(self, value: Any) -> None:
        await self.coordinator.async_set_profile_setting(
            self.vin, self.profile_id, self._key, self._setting, value
        )
