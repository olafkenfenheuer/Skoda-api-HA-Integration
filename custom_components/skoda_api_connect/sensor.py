"""Sensor platform for the Škoda API Connect integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfTime,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .api import RateLimitInfo, SkodaVehicle as Vehicle
from .coordinator import POLL_STATUSES, STATUS_RATE_LIMITED, PollResult, SkodaConfigEntry, SkodaDataUpdateCoordinator
from .entity import SkodaVehicleEntity


@dataclass(frozen=True, kw_only=True)
class SkodaSensorEntityDescription(SensorEntityDescription):
    """Describes a Škoda API Connect sensor entity."""

    value_fn: Callable[[Vehicle], StateType]
    exists_fn: Callable[[Vehicle], bool] = lambda vehicle: True
    attrs_fn: Callable[[Vehicle], dict[str, Any]] | None = None


def _battery_percent(vehicle: Vehicle) -> StateType:
    value = vehicle.get("charging", "status", "battery", "stateOfChargeInPercent")
    if value is None:
        for engine in ("primaryEngineRange", "secondaryEngineRange"):
            if vehicle.get("fuelStatus", engine, "engineType") == "ELECTRIC":
                return vehicle.get("fuelStatus", engine, "currentSoCInPercent")
    return value


def _battery_range_km(vehicle: Vehicle) -> StateType:
    meters = vehicle.get("charging", "status", "battery", "remainingCruisingRangeInMeters")
    return None if meters is None else round(meters / 1000)


def _fuel_level(vehicle: Vehicle) -> StateType:
    for engine in ("primaryEngineRange", "secondaryEngineRange"):
        value = vehicle.get("fuelStatus", engine, "currentFuelLevelInPercent")
        if value is not None:
            return value
    return None


def _path(*path: str) -> Callable[[Vehicle], StateType]:
    return lambda vehicle: vehicle.get(*path)


def _exists(*path: str) -> Callable[[Vehicle], bool]:
    return lambda vehicle: vehicle.has(*path)


def _datetime(*path: str) -> Callable[[Vehicle], datetime | None]:
    """Return a function reading an ISO 8601 timestamp at ``path`` as a datetime."""

    def read(vehicle: Vehicle) -> datetime | None:
        value = vehicle.get(*path)
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    return read


def _fully_charged_at(vehicle: Vehicle) -> datetime | None:
    """Return when the vehicle is expected to be fully charged, only while it charges.

    The API reports a time for the other states as well, which means nothing then.
    """
    if vehicle.get("charging", "status", "state") != "CHARGING":
        return None
    return _datetime("charging", "status", "fullyChargedAt")(vehicle)


def _charging_location_profile(vehicle: Vehicle) -> StateType:
    """Return the name of the saved charging location the vehicle is currently at.

    Only meaningful while the vehicle is actually at a saved location -
    ``currentVehiclePositionProfile`` can otherwise still carry a stale name.
    """
    if not vehicle.get("charging", "isVehicleInSavedLocation"):
        return None
    return vehicle.get("chargingProfiles", "currentVehiclePositionProfile", "name")


def _charging_location_attributes(vehicle: Vehicle) -> dict[str, Any]:
    """Return the details of the current charging profile, and which profiles exist."""
    attributes: dict[str, Any] = {
        "profiles": [
            {"id": profile["id"], "name": profile.get("name")}
            for profile in vehicle.charging_profiles()
        ]
    }
    if _charging_location_profile(vehicle) is None:
        return attributes
    current = vehicle.get("chargingProfiles", "currentVehiclePositionProfile") or {}
    for key, name in (
        ("id", "profile_id"),
        ("targetStateOfChargeInPercent", "target_state_of_charge"),
        ("nextChargingTime", "next_charging_time"),
    ):
        if current.get(key) is not None:
            attributes[name] = current[key]
    if profile := vehicle.charging_profile(current.get("id")):
        attributes["preferred_charging_times"] = [
            {
                "id": slot.get("id"),
                "enabled": slot.get("enabled"),
                "start": slot.get("startTime"),
                "end": slot.get("endTime"),
            }
            for slot in profile.get("preferredChargingTimes") or []
        ]
        attributes["timers"] = [
            {
                "id": timer.get("id"),
                "enabled": timer.get("enabled"),
                "type": timer.get("type"),
                "time": timer.get("time"),
                "days": timer.get("recurringOn") or timer.get("oneOffDay"),
            }
            for timer in profile.get("timers") or []
        ]
    return attributes


SENSOR_DESCRIPTIONS: tuple[SkodaSensorEntityDescription, ...] = (
    SkodaSensorEntityDescription(
        key="battery_level",
        translation_key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_battery_percent,
        exists_fn=lambda v: _battery_percent(v) is not None,
    ),
    SkodaSensorEntityDescription(
        key="charge_power",
        translation_key="charge_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        value_fn=_path("charging", "status", "chargePowerInKw"),
        exists_fn=_exists("charging", "status"),
    ),
    SkodaSensorEntityDescription(
        key="charge_limit",
        translation_key="charge_limit",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_path("charging", "settings", "targetStateOfChargeInPercent"),
        exists_fn=_exists("charging", "settings", "targetStateOfChargeInPercent"),
    ),
    SkodaSensorEntityDescription(
        key="charging_rate",
        translation_key="charging_rate",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        value_fn=_path("charging", "status", "chargingRateInKilometersPerHour"),
        exists_fn=_exists("charging", "status"),
    ),
    SkodaSensorEntityDescription(
        key="remaining_charging_time",
        translation_key="remaining_charging_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement="min",
        value_fn=_path("charging", "status", "remainingTimeToFullyChargedInMinutes"),
        exists_fn=_exists("charging", "status"),
    ),
    SkodaSensorEntityDescription(
        key="battery_range",
        translation_key="battery_range",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=_battery_range_km,
        exists_fn=lambda v: _battery_range_km(v) is not None,
    ),
    SkodaSensorEntityDescription(
        key="total_range",
        translation_key="total_range",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=_path("fuelStatus", "totalRangeInKm"),
        exists_fn=_exists("fuelStatus", "totalRangeInKm"),
    ),
    SkodaSensorEntityDescription(
        key="fuel_level",
        translation_key="fuel_level",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_fuel_level,
        exists_fn=lambda v: _fuel_level(v) is not None,
    ),
    SkodaSensorEntityDescription(
        key="ad_blue_range",
        translation_key="ad_blue_range",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=_path("fuelStatus", "adBlueRange"),
        exists_fn=_exists("fuelStatus", "adBlueRange"),
    ),
    SkodaSensorEntityDescription(
        key="mileage",
        translation_key="mileage",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=_path("odometer", "mileageInKm"),
        exists_fn=_exists("odometer", "mileageInKm"),
    ),
    SkodaSensorEntityDescription(
        key="target_temperature",
        translation_key="target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_registry_enabled_default=False,
        value_fn=_path("airConditioning", "targetTemperature", "value"),
        exists_fn=_exists("airConditioning", "targetTemperature", "value"),
    ),
    SkodaSensorEntityDescription(
        key="location_address",
        translation_key="location_address",
        icon="mdi:map-marker",
        value_fn=_path("parkingPosition", "formattedAddress"),
        exists_fn=_exists("parkingPosition", "formattedAddress"),
    ),
    # The lock and parking states are shown as reported (e.g. YES, TRUNK_OPENED, PARKED);
    # the API may add values, so they are plain text rather than enum sensors.
    SkodaSensorEntityDescription(
        key="doors_locked",
        translation_key="doors_locked",
        value_fn=_path("status", "overall", "doorsLocked"),
        exists_fn=_exists("status", "overall", "doorsLocked"),
    ),
    SkodaSensorEntityDescription(
        key="reliable_lock_status",
        translation_key="reliable_lock_status",
        value_fn=_path("status", "overall", "reliableLockStatus"),
        exists_fn=_exists("status", "overall", "reliableLockStatus"),
    ),
    SkodaSensorEntityDescription(
        key="parking_state",
        translation_key="parking_state",
        value_fn=_path("parkingPosition", "state"),
        exists_fn=_exists("parkingPosition", "state"),
    ),
    # Values the API reports that only matter for a closer look: diagnostics, or settings
    # of the vehicle that cannot be changed through the public API. Like the lock values they
    # are plain text, since the API may add values.
    SkodaSensorEntityDescription(
        key="charge_type",
        translation_key="charge_type",
        value_fn=_path("charging", "status", "chargeType"),
        exists_fn=_exists("charging", "status", "chargeType"),
    ),
    SkodaSensorEntityDescription(
        key="fully_charged_at",
        translation_key="fully_charged_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_fully_charged_at,
        exists_fn=_exists("charging", "status", "fullyChargedAt"),
    ),
    SkodaSensorEntityDescription(
        key="battery_care_target",
        translation_key="battery_care_target",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=_path("charging", "settings", "batteryCareModeTargetValueInPercent"),
        exists_fn=_exists("charging", "settings", "batteryCareModeTargetValueInPercent"),
    ),
    SkodaSensorEntityDescription(
        key="max_charge_current_ac",
        translation_key="max_charge_current_ac",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_path("charging", "settings", "maxChargeCurrentAc"),
        exists_fn=_exists("charging", "settings", "maxChargeCurrentAc"),
    ),
    SkodaSensorEntityDescription(
        key="max_charge_current_ac_ampere",
        translation_key="max_charge_current_ac_ampere",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=_path("charging", "settings", "maxChargeCurrentAcAmpere"),
        exists_fn=_exists("charging", "settings", "maxChargeCurrentAcAmpere"),
    ),
    SkodaSensorEntityDescription(
        key="air_conditioning_reach",
        translation_key="air_conditioning_reach",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_datetime("airConditioning", "estimatedReachOfTargetTemperatureAt"),
        exists_fn=_exists("airConditioning", "estimatedReachOfTargetTemperatureAt"),
    ),
    SkodaSensorEntityDescription(
        key="aux_heating_reach",
        translation_key="aux_heating_reach",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_datetime("auxiliaryHeating", "estimatedReachOfTargetTemperatureAt"),
        exists_fn=_exists("auxiliaryHeating", "estimatedReachOfTargetTemperatureAt"),
    ),
    SkodaSensorEntityDescription(
        key="fuel_car_type",
        translation_key="fuel_car_type",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_path("fuelStatus", "carType"),
        exists_fn=_exists("fuelStatus", "carType"),
    ),
    SkodaSensorEntityDescription(
        # Personal data: off by default, and redacted in the diagnostics.
        key="license_plate",
        translation_key="license_plate",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_path("licensePlate"),
        exists_fn=_exists("licensePlate"),
    ),
    SkodaSensorEntityDescription(
        key="charging_location_profile",
        translation_key="charging_location_profile",
        icon="mdi:map-marker-radius",
        value_fn=_charging_location_profile,
        exists_fn=_exists("chargingProfiles"),
        attrs_fn=_charging_location_attributes,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Škoda API Connect sensors from a config entry."""
    coordinator = entry.runtime_data
    entities: list[SkodaSensor] = []
    for vin, vehicle in coordinator.data.vehicles.items():
        for description in SENSOR_DESCRIPTIONS:
            if description.exists_fn(vehicle):
                entities.append(SkodaSensor(coordinator, vin, description))
        entities.append(SkodaApiStatusSensor(coordinator, vin))
        entities.append(SkodaLastPollSensor(coordinator, vin))
        entities.append(SkodaCarLastSeenSensor(coordinator, vin))
        entities.append(SkodaRateLimitUntilSensor(coordinator, vin))
        entities.append(SkodaApiRequestsRemainingSensor(coordinator, vin))
        entities.append(SkodaApiKeyExpirySensor(coordinator, vin))
        entities.append(SkodaPollIntervalSensor(coordinator, vin))
    async_add_entities(entities)


class SkodaSensor(SkodaVehicleEntity, SensorEntity):
    """Represents a single data point of a Škoda vehicle."""

    entity_description: SkodaSensorEntityDescription

    def __init__(
        self,
        coordinator: SkodaDataUpdateCoordinator,
        vin: str,
        description: SkodaSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, vin)
        self.entity_description = description
        self._attr_unique_id = f"{vin}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the current value, tolerating missing upstream data."""
        try:
            return self.entity_description.value_fn(self.vehicle)
        except (KeyError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the extra attributes of the description, if any."""
        attrs_fn = self.entity_description.attrs_fn
        if attrs_fn is None:
            return super().extra_state_attributes
        try:
            return attrs_fn(self.vehicle)
        except (KeyError, TypeError):
            return None


class SkodaApiStatusSensor(SkodaVehicleEntity, SensorEntity):
    """Shows the result of the last API request that polled the vehicle."""

    _attr_translation_key = "api_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = POLL_STATUSES
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:api"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_api_status"

    @property
    def available(self) -> bool:
        """Stay available while polling fails - that is when the status matters most."""
        return True

    @property
    def _result(self) -> PollResult | None:
        return self.coordinator.poll_results.get(self.vin)

    @property
    def native_value(self) -> str | None:
        """Return the outcome of the last poll."""
        result = self._result
        return result.status if result else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return when the last poll happened and what went wrong, if anything."""
        attributes: dict[str, Any] = {}
        if (last_success := self.coordinator.last_success.get(self.vin)) is not None:
            attributes["last_success"] = last_success
        if (result := self._result) is None:
            return attributes
        attributes["last_poll"] = result.time
        if result.error:
            attributes["error"] = result.error
        if result.http_status is not None:
            attributes["http_status"] = result.http_status
        if result.problem:
            attributes["problem"] = result.problem
        if result.retry_at:
            attributes["retry_at"] = result.retry_at
        if result.omitted:
            attributes["omitted_parts"] = result.omitted
        return attributes


class SkodaLastPollSensor(SkodaVehicleEntity, SensorEntity):
    """Shows when the vehicle was last polled successfully (a date and time)."""

    _attr_translation_key = "last_poll"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_last_poll"

    @property
    def available(self) -> bool:
        """Stay available while polling fails, so the age of the data stays visible."""
        return True

    @property
    def native_value(self) -> datetime | None:
        """Return the time of the last successful poll."""
        return self.coordinator.last_success.get(self.vin)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the time of the last attempt, which differs after a failed poll."""
        result = self.coordinator.poll_results.get(self.vin)
        return {"last_attempt": result.time} if result else {}


class SkodaCarLastSeenSensor(SkodaVehicleEntity, SensorEntity):
    """Shows when the vehicle last reported data to the Škoda servers (a date and time)."""

    _attr_translation_key = "car_last_seen"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:car-connected"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_car_last_seen"

    @property
    def available(self) -> bool:
        """Stay available while polling fails, so the age of the data stays visible."""
        return True

    @property
    def _timestamps(self) -> dict[str, datetime]:
        vehicle = self.coordinator.data.vehicles.get(self.vin) if self.coordinator.data else None
        return vehicle.captured_at() if vehicle else {}

    @property
    def native_value(self) -> datetime | None:
        """Return the newest timestamp the vehicle reported in any section."""
        stamps = self._timestamps
        return max(stamps.values()) if stamps else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the timestamp of each section, to show which part stopped reporting."""
        return self._timestamps


class SkodaRateLimitUntilSensor(SkodaVehicleEntity, SensorEntity):
    """Shows when the request quota is available again after a rate limit (HTTP 429)."""

    _attr_translation_key = "rate_limit_until"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_rate_limit_until"

    @property
    def available(self) -> bool:
        """Stay available while polling fails, which is when this sensor matters."""
        return True

    @property
    def native_value(self) -> datetime | None:
        """Return when the quota is back, or None unless the last poll was rate limited."""
        result = self.coordinator.poll_results.get(self.vin)
        return result.retry_at if result and result.status == STATUS_RATE_LIMITED else None


class SkodaApiKeyExpirySensor(SkodaVehicleEntity, SensorEntity):
    """Shows when the API key expires (a date and time), to warn before it does."""

    _attr_translation_key = "api_key_expires"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:key-alert"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_api_key_expires"

    @property
    def available(self) -> bool:
        """Stay available while polling fails; an expired key is one possible reason."""
        return True

    @property
    def native_value(self) -> datetime | None:
        """Return the expiry reported with the last response, or None until one arrived."""
        return self.coordinator.api.key_expires_at


class SkodaApiRequestsRemainingSensor(SkodaVehicleEntity, SensorEntity):
    """Shows how many requests of the hourly API quota are left (from the last response)."""

    _attr_translation_key = "api_requests_remaining"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_api_requests_remaining"

    @property
    def available(self) -> bool:
        """Stay available while polling fails, which is when the quota matters."""
        return True

    @property
    def _info(self) -> RateLimitInfo | None:
        return self.coordinator.api.rate_limits.get(self.vin)

    @property
    def native_value(self) -> int | None:
        """Return the remaining requests reported with the last response."""
        info = self._info
        return info.remaining if info else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the quota limit, when it resets and when the value was reported."""
        if (info := self._info) is None:
            return {}
        attributes: dict[str, Any] = {"updated": info.updated}
        if info.limit is not None:
            attributes["limit"] = info.limit
        if info.reset_at is not None:
            attributes["reset_at"] = info.reset_at
        return attributes


class SkodaPollIntervalSensor(SkodaVehicleEntity, SensorEntity):
    """Shows the polling interval the vehicle currently uses, in minutes."""

    _attr_translation_key = "poll_interval"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer-cog-outline"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_poll_interval"

    @property
    def available(self) -> bool:
        """Stay available while polling fails, which is when the interval matters."""
        return True

    @property
    def native_value(self) -> int:
        """Return the interval of the vehicle's current state (normal or charging)."""
        kind = self.coordinator.active_interval_kind(self.vin)
        return self.coordinator.interval_minutes(self.vin, kind)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return which of the two configured intervals is in use."""
        return {"mode": self.coordinator.active_interval_kind(self.vin)}
