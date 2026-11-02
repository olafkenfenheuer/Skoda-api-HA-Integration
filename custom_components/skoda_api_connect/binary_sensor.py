"""Binary sensor platform for the Škoda API Connect integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import SkodaVehicle
from .coordinator import SkodaConfigEntry, SkodaDataUpdateCoordinator
from .entity import SkodaVehicleEntity
from .parking_alert import is_parked, unsecured_reasons

_UNKNOWN = ("UNKNOWN", "UNSUPPORTED")


def _is(*path: str, value: str) -> Callable[[SkodaVehicle], bool | None]:
    """Return a function comparing the value at ``path`` to ``value``.

    Missing or unknown values yield None (unknown) instead of False.
    """

    def check(vehicle: SkodaVehicle) -> bool | None:
        current = vehicle.get(*path)
        if current is None or current in _UNKNOWN:
            return None
        return current == value

    return check


def _reported(*path: str) -> Callable[[SkodaVehicle], bool]:
    return lambda vehicle: vehicle.has(*path)


def _supported(*path: str) -> Callable[[SkodaVehicle], bool]:
    """Return a function that is true if the vehicle reports a value other than UNSUPPORTED."""
    return lambda vehicle: vehicle.get(*path) not in (None, "UNSUPPORTED")


def _flag(*path: str) -> Callable[[SkodaVehicle], bool | None]:
    """Return a function reading a boolean at ``path`` (None if it is not one)."""

    def read(vehicle: SkodaVehicle) -> bool | None:
        value = vehicle.get(*path)
        return value if isinstance(value, bool) else None

    return read


@dataclass(frozen=True, kw_only=True)
class SkodaBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Škoda API Connect binary sensor entity."""

    value_fn: Callable[[SkodaVehicle], bool | None]
    exists_fn: Callable[[SkodaVehicle], bool]
    attrs_fn: Callable[[SkodaVehicle], dict[str, Any]] | None = None
    # Unknown until the vehicle was polled since startup, instead of using cached data.
    requires_poll: bool = False


def _parked_unsecured(vehicle: SkodaVehicle) -> bool | None:
    """Return the parking alert condition; unknown while the parking state is not reported."""
    if is_parked(vehicle) is None:
        return None
    return bool(unsecured_reasons(vehicle))


BINARY_SENSOR_DESCRIPTIONS: tuple[SkodaBinarySensorEntityDescription, ...] = (
    SkodaBinarySensorEntityDescription(
        key="doors_open",
        translation_key="doors_open",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=_is("status", "overall", "doors", value="OPEN"),
        exists_fn=_reported("status", "overall", "doors"),
    ),
    SkodaBinarySensorEntityDescription(
        key="windows_open",
        translation_key="windows_open",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=_is("status", "overall", "windows", value="OPEN"),
        exists_fn=_reported("status", "overall", "windows"),
    ),
    SkodaBinarySensorEntityDescription(
        key="trunk_open",
        translation_key="trunk_open",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=_is("status", "detail", "trunk", value="OPEN"),
        exists_fn=_reported("status", "detail", "trunk"),
    ),
    SkodaBinarySensorEntityDescription(
        key="bonnet_open",
        translation_key="bonnet_open",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=_is("status", "detail", "bonnet", value="OPEN"),
        exists_fn=_reported("status", "detail", "bonnet"),
    ),
    SkodaBinarySensorEntityDescription(
        key="lights_on",
        translation_key="lights_on",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_fn=_is("status", "overall", "lights", value="ON"),
        exists_fn=_reported("status", "overall", "lights"),
    ),
    SkodaBinarySensorEntityDescription(
        # For the LOCK device class "on" means unlocked.
        key="unlocked",
        translation_key="unlocked",
        device_class=BinarySensorDeviceClass.LOCK,
        value_fn=_is("status", "overall", "locked", value="NO"),
        exists_fn=_reported("status", "overall", "locked"),
    ),
    SkodaBinarySensorEntityDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=_is("charging", "status", "state", value="CHARGING"),
        exists_fn=_reported("charging", "status"),
    ),
    SkodaBinarySensorEntityDescription(
        key="plugged_in",
        translation_key="plugged_in",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=_is("charging", "status", "plugConnectionState", value="CONNECTED"),
        exists_fn=_reported("charging", "status", "plugConnectionState"),
    ),
    SkodaBinarySensorEntityDescription(
        key="plug_lock",
        translation_key="plug_lock",
        device_class=BinarySensorDeviceClass.LOCK,
        value_fn=_is("charging", "status", "plugLockState", value="UNLOCKED"),
        exists_fn=_reported("charging", "status", "plugLockState"),
    ),
    SkodaBinarySensorEntityDescription(
        key="vehicle_in_saved_location",
        translation_key="vehicle_in_saved_location",
        icon="mdi:home-map-marker",
        value_fn=lambda v: v.get("charging", "isVehicleInSavedLocation"),
        exists_fn=_reported("charging", "isVehicleInSavedLocation"),
    ),
    # Settings of the vehicle and states the API only reports, none of them can be changed through it.
    SkodaBinarySensorEntityDescription(
        key="charging_care_mode",
        translation_key="charging_care_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_is("charging", "settings", "chargingCareMode", value="ACTIVATED"),
        exists_fn=_reported("charging", "settings", "chargingCareMode"),
    ),
    SkodaBinarySensorEntityDescription(
        key="vehicle_auto_unlock",
        translation_key="vehicle_auto_unlock",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_is("charging", "settings", "autoUnlockPlugWhenCharged", value="PERMANENT"),
        exists_fn=_reported("charging", "settings", "autoUnlockPlugWhenCharged"),
    ),
    SkodaBinarySensorEntityDescription(
        key="window_heating_front",
        translation_key="window_heating_front",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=_is("airConditioning", "windowHeating", "front", value="ON"),
        exists_fn=_supported("airConditioning", "windowHeating", "front"),
    ),
    SkodaBinarySensorEntityDescription(
        key="window_heating_rear",
        translation_key="window_heating_rear",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=_is("airConditioning", "windowHeating", "rear", value="ON"),
        exists_fn=_supported("airConditioning", "windowHeating", "rear"),
    ),
    SkodaBinarySensorEntityDescription(
        key="window_heating_enabled",
        translation_key="window_heating_enabled",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_flag("airConditioning", "windowHeating", "enabled"),
        exists_fn=_reported("airConditioning", "windowHeating", "enabled"),
    ),
    SkodaBinarySensorEntityDescription(
        key="air_conditioning_at_unlock",
        translation_key="air_conditioning_at_unlock",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_flag("airConditioning", "airConditioningAtUnlock"),
        exists_fn=_reported("airConditioning", "airConditioningAtUnlock"),
    ),
    SkodaBinarySensorEntityDescription(
        key="air_conditioning_without_external_power",
        translation_key="air_conditioning_without_external_power",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_flag("airConditioning", "airConditioningWithoutExternalPower"),
        exists_fn=_reported("airConditioning", "airConditioningWithoutExternalPower"),
    ),
    SkodaBinarySensorEntityDescription(
        key="sunroof_open",
        translation_key="sunroof_open",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=_is("status", "detail", "sunroof", value="OPEN"),
        exists_fn=_supported("status", "detail", "sunroof"),
    ),
    SkodaBinarySensorEntityDescription(
        # The parking alert condition; like the alert, it ignores data cached before a restart.
        key="parked_unsecured",
        translation_key="parked_unsecured",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_parked_unsecured,
        exists_fn=_reported("parkingPosition", "state"),
        attrs_fn=lambda v: {"reasons": unsecured_reasons(v)},
        requires_poll=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Škoda API Connect binary sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        SkodaBinarySensor(coordinator, vin, description)
        for vin, vehicle in coordinator.data.vehicles.items()
        for description in BINARY_SENSOR_DESCRIPTIONS
        if description.exists_fn(vehicle)
    )


class SkodaBinarySensor(SkodaVehicleEntity, BinarySensorEntity):
    """Represents a boolean state of a Škoda vehicle."""

    entity_description: SkodaBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: SkodaDataUpdateCoordinator,
        vin: str,
        description: SkodaBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, vin)
        self.entity_description = description
        self._attr_unique_id = f"{vin}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return true if the condition described is active."""
        if self.entity_description.requires_poll and not self._polled:
            return None
        return self.entity_description.value_fn(self.vehicle)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the extra attributes of the description, if any."""
        attrs_fn = self.entity_description.attrs_fn
        if attrs_fn is None or (self.entity_description.requires_poll and not self._polled):
            return None
        return attrs_fn(self.vehicle)

    @property
    def _polled(self) -> bool:
        return self.coordinator.last_success.get(self.vin) is not None
