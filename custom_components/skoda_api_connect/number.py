"""Number platform for the Škoda API Connect integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import SkodaVehicle
from .const import (
    AUTO_WAKE_NUMBER_MAX_MINUTES,
    KEY_ALERT_GRACE,
    KEY_AUTO_WAKE,
    KEY_AUX_DURATION,
    MAX_ALERT_GRACE_MINUTES,
    MAX_AUX_DURATION_MINUTES,
    MIN_AUX_DURATION_MINUTES,
    MIN_AUTO_WAKE_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
    POLL_INTERVAL_NUMBER_MAX_MINUTES,
)
from .coordinator import Expectation, SkodaConfigEntry, SkodaDataUpdateCoordinator
from .entity import SkodaProfileEntity, SkodaVehicleEntity


def _has_charge_limit(vehicle: SkodaVehicle) -> bool:
    return vehicle.has("charging", "settings", "targetStateOfChargeInPercent")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Škoda API Connect charge limit number entity from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            SkodaChargeLimitNumber(coordinator, vin)
            for vin, vehicle in coordinator.data.vehicles.items()
            if _has_charge_limit(vehicle)
        ]
        + [
            SkodaPollIntervalNumber(entry, coordinator, vin, kind)
            for vin in coordinator.data.vehicles
            for kind in ("idle", "charging")
        ]
        + [
            SkodaAutoWakeNumber(coordinator, vin)
            for vin, vehicle in coordinator.data.vehicles.items()
            if not coordinator.read_only and vehicle.supports("setChargeMode")
        ]
        + [
            SkodaParkingAlertGraceNumber(coordinator, vin)
            for vin in coordinator.data.vehicles
        ]
        + [
            SkodaAuxDurationNumber(coordinator, vin)
            for vin, vehicle in coordinator.data.vehicles.items()
            if vehicle.has_auxiliary_heating() and not coordinator.read_only
        ]
        + [
            SkodaProfileTargetNumber(
                coordinator, vin, profile["id"], str(profile.get("name") or profile["id"])
            )
            for vin, vehicle in coordinator.data.vehicles.items()
            if vehicle.lists("updateChargingProfile")
            for profile in vehicle.charging_profiles()
        ]
        + [
            SkodaProfileMinChargeNumber(
                coordinator, vin, profile["id"], str(profile.get("name") or profile["id"])
            )
            for vin, vehicle in coordinator.data.vehicles.items()
            if vehicle.lists("updateChargingProfile")
            for profile in vehicle.charging_profiles()
            if "minimumBatteryStateOfChargeInPercent"
            in (profile.get("settings", {}).get("minBatteryStateOfCharge") or {})
        ]
    )


class SkodaChargeLimitNumber(SkodaVehicleEntity, NumberEntity):
    """Represents the target state-of-charge limit."""

    _attr_translation_key = "charge_limit"
    _expected_key = "charge_limit"
    _attr_native_unit_of_measurement = PERCENTAGE
    # Vehicles typically accept 50-100 in steps of 10 and reject other values.
    _attr_native_min_value = 50
    _attr_native_max_value = 100
    _attr_native_step = 10
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_charge_limit"

    @property
    def native_value(self) -> float | None:
        """Return the currently configured charge limit."""
        if (expected := self._expected()) is not None:
            return expected
        return self.vehicle.get("charging", "settings", "targetStateOfChargeInPercent")

    async def async_set_native_value(self, value: float) -> None:
        """Set a new charge limit."""
        await self.coordinator.async_command(
            self.vin,
            self.coordinator.api.set_charging_limit(self.vin, int(value)),
            Expectation("charge_limit", int(value), "charging"),
        )


class SkodaPollIntervalNumber(SkodaVehicleEntity, NumberEntity):
    """Polling interval of one vehicle, for its normal state or while it is charging.

    Stored in the entry options and applied immediately, without reloading the entry.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = MIN_SCAN_INTERVAL_MINUTES
    _attr_native_max_value = POLL_INTERVAL_NUMBER_MAX_MINUTES
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(
        self, entry, coordinator: SkodaDataUpdateCoordinator, vin: str, kind: str
    ) -> None:
        """Initialize the number entity; ``kind`` is "idle" or "charging"."""
        super().__init__(coordinator, vin)
        self._entry = entry
        self._kind = kind
        self._attr_translation_key = f"poll_interval_{kind}"
        self._attr_unique_id = f"{vin}_poll_interval_{kind}"

    @property
    def native_value(self) -> float:
        """Return the configured interval in minutes."""
        return self.coordinator.interval_minutes(self.vin, self._kind)

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new interval; the entry's update listener applies it."""
        self.coordinator.set_vehicle_option(self.vin, self._kind, int(value))
        self.async_write_ha_state()


class SkodaAutoWakeNumber(SkodaVehicleEntity, NumberEntity):
    """Minutes without vehicle data after which a charging vehicle is woken (0 = off).

    Stored in the entry options like the polling intervals. Each wake-up costs two
    requests of the API quota, which is why this is off by default.
    """

    _attr_translation_key = "auto_wake"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 0
    _attr_native_max_value = AUTO_WAKE_NUMBER_MAX_MINUTES
    _attr_native_step = 5
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:sleep-off"

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_auto_wake"

    @property
    def native_value(self) -> float:
        """Return the configured time in minutes, 0 if the automatic wake-up is off."""
        return self.coordinator.auto_wake_minutes(self.vin)

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new time, raised to the minimum if it is not 0."""
        minutes = int(value)
        if minutes:
            minutes = max(minutes, MIN_AUTO_WAKE_MINUTES)
        self.coordinator.set_vehicle_option(self.vin, KEY_AUTO_WAKE, minutes)
        self.async_write_ha_state()


class SkodaParkingAlertGraceNumber(SkodaVehicleEntity, NumberEntity):
    """Minutes a parked vehicle may stay unsecured before the parking alert is sent.

    Stored in the entry options like the polling intervals; 0 sends the alert at once.
    """

    _attr_translation_key = "parking_alert_grace"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_ALERT_GRACE_MINUTES
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_parking_alert_grace"

    @property
    def native_value(self) -> float:
        """Return the configured grace period in minutes."""
        return self.coordinator.alert_grace_minutes(self.vin)

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new grace period; the parking alert applies it to an open incident."""
        self.coordinator.set_vehicle_option(self.vin, KEY_ALERT_GRACE, int(value))
        self.async_write_ha_state()


class SkodaAuxDurationNumber(SkodaVehicleEntity, NumberEntity):
    """How long the auxiliary heating runs after it was started, in minutes.

    Stored in the entry options like the polling intervals and sent with every start.
    """

    _attr_translation_key = "aux_duration"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = MIN_AUX_DURATION_MINUTES
    _attr_native_max_value = MAX_AUX_DURATION_MINUTES
    _attr_native_step = 5
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_aux_duration"

    @property
    def native_value(self) -> float:
        """Return the running time in minutes."""
        return self.coordinator.aux_duration_minutes(self.vin)

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new running time."""
        self.coordinator.set_vehicle_option(self.vin, KEY_AUX_DURATION, int(value))
        self.async_write_ha_state()


class SkodaProfileTargetNumber(SkodaProfileEntity, NumberEntity):
    """The target state of charge of a charging profile (saved charging location)."""

    _attr_translation_key = "profile_target_soc"
    _key = "target_soc"
    _setting = ("targetStateOfChargeInPercent",)
    _attr_native_unit_of_measurement = PERCENTAGE
    # Vehicles typically accept 50-100 in steps of 10 and reject other values.
    _attr_native_min_value = 50
    _attr_native_max_value = 100
    _attr_native_step = 10
    _attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> float | None:
        """Return the target state of charge of the profile."""
        value = self._value
        return value if isinstance(value, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        """Change the target state of charge of the profile."""
        await self._async_set(int(value))


class SkodaProfileMinChargeNumber(SkodaProfileEntity, NumberEntity):
    """The minimum charge of a charging profile: below it the vehicle charges at once.

    The app calls it "minimum charging limit". Whether it is active is a separate switch,
    for vehicles that report that.
    """

    _attr_translation_key = "profile_min_charge"
    _key = "min_charge"
    _setting = ("minBatteryStateOfCharge", "minimumBatteryStateOfChargeInPercent")
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 10
    _attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> float | None:
        """Return the minimum charge of the profile."""
        value = self._value
        return value if isinstance(value, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        """Change the minimum charge of the profile."""
        await self._async_set(int(value))
