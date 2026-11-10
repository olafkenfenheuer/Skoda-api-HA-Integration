"""Climate platform for the Škoda API Connect integration (air conditioning)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import EXPECTED_CLIMATE_MINUTES
from .coordinator import Expectation, SkodaConfigEntry, SkodaDataUpdateCoordinator
from .entity import SkodaVehicleEntity

DEFAULT_TARGET_TEMPERATURE = 21.0

_STATE_TO_HVAC_ACTION = {
    "OFF": HVACAction.OFF,
    "COMPLETED": HVACAction.IDLE,
    "COOLING": HVACAction.COOLING,
    "HEATING": HVACAction.HEATING,
    "HEATING_AUXILIARY": HVACAction.HEATING,
    "VENTILATION": HVACAction.FAN,
}
_ACTIVE_VENTILATION_STATES = ("VENTILATION", "PREHEATING")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SkodaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Škoda API Connect climate entity from a config entry."""
    coordinator = entry.runtime_data
    entities: list[ClimateEntity] = []
    for vin, vehicle in coordinator.data.vehicles.items():
        if vehicle.has("airConditioning") and vehicle.supports("startAirConditioning"):
            entities.append(SkodaClimate(coordinator, vin))
        # Only for vehicles that have it (and the S-PIN is needed to start it).
        if vehicle.has_auxiliary_heating():
            entities.append(SkodaAuxiliaryHeating(coordinator, vin))
    async_add_entities(entities)


class SkodaClimate(SkodaVehicleEntity, ClimateEntity):
    """Represents the remote air conditioning of a Škoda vehicle."""

    _attr_translation_key = "air_conditioning"
    _expected_key = "hvac_mode"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    _attr_min_temp = 16
    _attr_max_temp = 29.5
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_air_conditioning"
        # The API has no "set temperature" call: the target is sent when climate starts.
        self._requested_temperature: float | None = None
        # Target temperature reported by the vehicle when the request was made; a different
        # value later means it was changed elsewhere (e.g. in the app) and wins.
        self._requested_from: float | None = None

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the modes the vehicle offers: ventilation only if it supports it."""
        modes = [HVACMode.OFF, HVACMode.HEAT_COOL]
        if self.vehicle.supports("startActiveVentilation"):
            modes.append(HVACMode.FAN_ONLY)
        return modes

    def _handle_coordinator_update(self) -> None:
        """Drop the requested temperature once the vehicle reports a different target."""
        reported = self.vehicle.get("airConditioning", "targetTemperature", "value")
        if self._requested_temperature is not None and reported != self._requested_from:
            self._requested_temperature = None
        super()._handle_coordinator_update()

    @property
    def _state(self) -> str | None:
        return self.vehicle.get("airConditioning", "state")

    @property
    def _ventilating(self) -> bool:
        return self.vehicle.get("activeVentilation", "state") in _ACTIVE_VENTILATION_STATES

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        if (expected := self._expected()) is not None:
            return expected
        state = self._state
        if state in ("COOLING", "HEATING", "HEATING_AUXILIARY"):
            return HVACMode.HEAT_COOL
        if state == "VENTILATION" or self._ventilating:
            return HVACMode.FAN_ONLY
        return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current HVAC action."""
        if (expected := self._expected()) is not None:
            # Only the on/off state is known until the vehicle reports what it is doing.
            return {HVACMode.OFF: HVACAction.OFF, HVACMode.FAN_ONLY: HVACAction.FAN}.get(expected)
        if self._ventilating and self._state in (None, "OFF"):
            return HVACAction.FAN
        return _STATE_TO_HVAC_ACTION.get(self._state)

    @property
    def native_target_temperature(self) -> float | None:
        """Return the target cabin temperature."""
        if self._requested_temperature is not None:
            return self._requested_temperature
        return self.vehicle.get("airConditioning", "targetTemperature", "value")

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature, restarting the climate if it is running."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        if self.hvac_mode == HVACMode.HEAT_COOL:
            await self.coordinator.async_command(
                self.vin,
                self.coordinator.api.start_air_conditioning(self.vin, temperature)
            )
        self._requested_from = self.vehicle.get("airConditioning", "targetTemperature", "value")
        self._requested_temperature = temperature
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Turn the air conditioning on, off, or into ventilation mode."""
        api = self.coordinator.api
        if hvac_mode == HVACMode.OFF:
            if self.hvac_mode == HVACMode.OFF:
                return
            if self._ventilating and self._state in (None, "OFF"):
                command = api.stop_active_ventilation(self.vin)
            else:
                command = api.stop_air_conditioning(self.vin)
        elif hvac_mode == HVACMode.FAN_ONLY:
            command = api.start_active_ventilation(self.vin)
        else:
            command = api.start_air_conditioning(
                self.vin, self.target_temperature or DEFAULT_TARGET_TEMPERATURE
            )
        await self.coordinator.async_command(
            self.vin,
            command,
            Expectation(
                "hvac_mode",
                hvac_mode,
                "airConditioning",
                timedelta(minutes=EXPECTED_CLIMATE_MINUTES),
            ),
        )

    async def async_turn_on(self) -> None:
        """Turn the air conditioning on."""
        await self.async_set_hvac_mode(HVACMode.HEAT_COOL)

    async def async_turn_off(self) -> None:
        """Turn the air conditioning off."""
        await self.async_set_hvac_mode(HVACMode.OFF)


_AUX_STATE_TO_MODE = {
    "PREHEATING": HVACMode.HEAT,
    "HEATING_AUXILIARY": HVACMode.HEAT,
    "VENTILATION": HVACMode.FAN_ONLY,
}
_AUX_STATE_TO_ACTION = {
    "OFF": HVACAction.OFF,
    "PREHEATING": HVACAction.HEATING,
    "HEATING_AUXILIARY": HVACAction.HEATING,
    "VENTILATION": HVACAction.FAN,
}
_AUX_MODE_TO_ACTION = {
    HVACMode.OFF: HVACAction.OFF,
    HVACMode.HEAT: HVACAction.HEATING,
    HVACMode.FAN_ONLY: HVACAction.FAN,
}
_AUX_START_MODE = {HVACMode.HEAT: "HEATING", HVACMode.FAN_ONLY: "VENTILATION"}


class SkodaAuxiliaryHeating(SkodaVehicleEntity, ClimateEntity):
    """The auxiliary heating of a Škoda vehicle (fuel-operated or electric).

    Starting it needs the S-PIN from the integration options. It runs for the time set with
    the "Auxiliary heating duration" number. A target temperature is only sent with the start if
    the vehicle reports one or it was set here: not every vehicle accepts it.
    """

    _attr_translation_key = "auxiliary_heating"
    _expected_key = "aux_mode"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.FAN_ONLY]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    _attr_min_temp = 16
    _attr_max_temp = 29.5
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator: SkodaDataUpdateCoordinator, vin: str) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, vin)
        self._attr_unique_id = f"{vin}_auxiliary_heating"
        # The API has no "set temperature" call: the target is sent when the heating starts.
        self._requested_temperature: float | None = None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current mode."""
        if (expected := self._expected()) is not None:
            return expected
        return _AUX_STATE_TO_MODE.get(
            self.vehicle.get("auxiliaryHeating", "state"), HVACMode.OFF
        )

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return what the auxiliary heating is doing."""
        if (expected := self._expected()) is not None:
            return _AUX_MODE_TO_ACTION.get(expected)
        return _AUX_STATE_TO_ACTION.get(self.vehicle.get("auxiliaryHeating", "state"))

    @property
    def native_target_temperature(self) -> float | None:
        """Return the target cabin temperature."""
        if self._requested_temperature is not None:
            return self._requested_temperature
        return self.vehicle.get("auxiliaryHeating", "targetTemperature", "value")

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Remember the target temperature; it is sent the next time the heating starts."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        self._requested_temperature = temperature
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Start the auxiliary heating (heating or ventilation) or stop it."""
        coordinator = self.coordinator
        expect = Expectation(
            "aux_mode",
            hvac_mode,
            "auxiliaryHeating",
            timedelta(minutes=EXPECTED_CLIMATE_MINUTES),
        )
        if hvac_mode == HVACMode.OFF:
            if self.hvac_mode == HVACMode.OFF:
                return
            await coordinator.async_command(
                self.vin, coordinator.api.stop_auxiliary_heating(self.vin), expect
            )
            return
        # Check the S-PIN before anything is sent: a wrong one could lock the S-PIN.
        spin = coordinator.spin()
        await coordinator.async_command(
            self.vin,
            coordinator.api.start_auxiliary_heating(
                self.vin,
                spin,
                mode=_AUX_START_MODE[hvac_mode],
                duration_seconds=coordinator.aux_duration_minutes(self.vin) * 60,
                temperature=self.target_temperature,
            ),
            expect,
        )

    async def async_turn_on(self) -> None:
        """Start the auxiliary heating (heating)."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Stop the auxiliary heating."""
        await self.async_set_hvac_mode(HVACMode.OFF)
