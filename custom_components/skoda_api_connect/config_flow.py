"""Config flow for the Škoda API Connect integration."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import SkodaApi, SkodaApiError, SkodaAuthError, SkodaRateLimitError
from .const import (
    API_KEYS_URL,
    CONF_API_KEY,
    CONF_CHARGING_SCAN_INTERVAL,
    CONF_NOTIFY_TARGETS,
    CONF_PLUGGED_IN_FAST_POLLING,
    CONF_READ_ONLY,
    CONF_SPIN,
    CONF_VINS,
    DEFAULT_CHARGING_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
    NOTIFY_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_VINS): str,
    }
)


def _parse_vins(raw: str) -> list[str]:
    """Split a comma/space separated VIN list, de-duplicated and upper-cased."""
    vins = [v.strip().upper() for v in re.split(r"[,\s;]+", raw) if v.strip()]
    return list(dict.fromkeys(vins))


async def _validate(hass, api_key: str, vins: list[str]) -> None:
    """Check that the API key can read every VIN (one cheap request per vehicle)."""
    api = SkodaApi(async_get_clientsession(hass), api_key)
    for vin in vins:
        await api.get_vehicle(vin, include=["info"])


def _error_for(err: Exception) -> str:
    if isinstance(err, SkodaAuthError):
        return "invalid_auth"
    if isinstance(err, SkodaRateLimitError):
        return "rate_limited"
    return "cannot_connect"


class SkodaConnectConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Škoda API Connect."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._reauth_entry: ConfigEntry | None = None

    async def _validate_input(self, user_input: dict[str, Any]) -> tuple[list[str], str | None]:
        vins = _parse_vins(user_input[CONF_VINS])
        if not vins or not all(VIN_RE.match(v) for v in vins):
            return vins, "invalid_vin"
        try:
            await _validate(self.hass, user_input[CONF_API_KEY].strip(), vins)
        except SkodaApiError as err:
            _LOGGER.debug("Validation failed: %s", err)
            return vins, _error_for(err)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error validating Škoda API key")
            return vins, "cannot_connect"
        return vins, None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step, asking for an API key and the VIN(s)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            vins, error = await self._validate_input(user_input)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(",".join(sorted(vins)))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=", ".join(vins),
                    data={
                        CONF_API_KEY: user_input[CONF_API_KEY].strip(),
                        CONF_VINS: vins,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
            description_placeholders={"api_keys_url": API_KEYS_URL},
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle an expired/invalid API key."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key (and the VINs)."""
        assert self._reauth_entry is not None
        return await self._async_credentials_step(
            "reauth_confirm", self._reauth_entry, user_input
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user enter a new API key (or change the VINs) at any time."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None
        return await self._async_credentials_step("reconfigure", entry, user_input)

    async def _async_credentials_step(
        self, step_id: str, entry: ConfigEntry, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Validate a new API key / VIN list and store it on an existing entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            vins, error = await self._validate_input(user_input)
            unique_id = ",".join(sorted(vins))
            if not error and any(
                other.entry_id != entry.entry_id and other.unique_id == unique_id
                for other in self._async_current_entries(include_ignore=False)
            ):
                error = "already_configured"
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=unique_id,
                    title=", ".join(vins),
                    data={
                        CONF_API_KEY: user_input[CONF_API_KEY].strip(),
                        CONF_VINS: vins,
                    },
                )

        schema = vol.Schema(
            {vol.Required(CONF_API_KEY): str, vol.Required(CONF_VINS): str}
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                schema,
                user_input or {CONF_VINS: ", ".join(entry.data[CONF_VINS])},
            ),
            errors=errors,
            description_placeholders={"api_keys_url": API_KEYS_URL},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> SkodaConnectOptionsFlow:
        """Return the options flow for this handler."""
        return SkodaConnectOptionsFlow()


class SkodaConnectOptionsFlow(OptionsFlow):
    """Handle options for an existing Škoda API Connect entry."""

    def _has_auxiliary_heating(self) -> bool:
        """Return whether a vehicle of the loaded entry has an auxiliary heating."""
        coordinator = getattr(self.config_entry, "runtime_data", None)
        if coordinator is None or not coordinator.data:
            return False
        return any(v.has_auxiliary_heating() for v in coordinator.data.vehicles.values())

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage polling intervals, read-only mode and parking alert targets."""
        errors: dict[str, str] = {}
        placeholders = {"target": ""}
        if user_input is not None:
            targets, unknown = _normalize_notify_targets(
                self.hass, user_input.get(CONF_NOTIFY_TARGETS, [])
            )
            if unknown is None:
                # Keep the per-vehicle overrides, which are edited via number entities.
                # The targets are always written, so clearing the field removes them.
                return self.async_create_entry(
                    data={
                        **self.config_entry.options,
                        **user_input,
                        CONF_NOTIFY_TARGETS: targets,
                        # Always written when the field is shown, so clearing it removes the S-PIN.
                        **(
                            {CONF_SPIN: user_input.get(CONF_SPIN, "")}
                            if self._has_auxiliary_heating()
                            else {}
                        ),
                    }
                )
            errors[CONF_NOTIFY_TARGETS] = "unknown_notify_target"
            placeholders["target"] = unknown

        # After an error, show what the user entered rather than the stored options.
        values = {**self.config_entry.options, **(user_input or {})}
        current_targets = values.get(CONF_NOTIFY_TARGETS, [])
        current_interval = values.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
        current_charging = values.get(
            CONF_CHARGING_SCAN_INTERVAL, DEFAULT_CHARGING_SCAN_INTERVAL_MINUTES
        )
        current_plugged = values.get(CONF_PLUGGED_IN_FAST_POLLING, False)
        current_read_only = values.get(CONF_READ_ONLY, False)

        spin_field: dict[Any, Any] = {}
        if self._has_auxiliary_heating():
            # Only needed to start the auxiliary heating; kept as a password field.
            spin_field[
                vol.Optional(
                    CONF_SPIN, description={"suggested_value": values.get(CONF_SPIN, "")}
                )
            ] = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=current_interval
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_MINUTES,
                        max=MAX_SCAN_INTERVAL_MINUTES,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
                vol.Required(
                    CONF_CHARGING_SCAN_INTERVAL, default=current_charging
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_MINUTES,
                        max=MAX_SCAN_INTERVAL_MINUTES,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
                vol.Required(CONF_PLUGGED_IN_FAST_POLLING, default=current_plugged): bool,
                vol.Required(CONF_READ_ONLY, default=current_read_only): bool,
                # A suggested value, not a default: an emptied field must clear the targets.
                vol.Optional(
                    CONF_NOTIFY_TARGETS, description={"suggested_value": current_targets}
                ): _notify_target_selector(self.hass, current_targets),
                **spin_field,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
        )


def _notify_target_selector(hass: HomeAssistant, current: list[str]) -> SelectSelector:
    """Dropdown of the existing notify services; other names can be typed."""
    available = {
        f"{NOTIFY_DOMAIN}.{service}"
        for service in hass.services.async_services_for_domain(NOTIFY_DOMAIN)
        # Entity based; needs an entity_id instead of a service name.
        if service != "send_message"
    }
    return SelectSelector(
        SelectSelectorConfig(
            options=sorted(available | set(current)),
            multiple=True,
            custom_value=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _normalize_notify_targets(
    hass: HomeAssistant, targets: list[str]
) -> tuple[list[str], str | None]:
    """Return the targets as "notify.<service>" and the first unknown one, if any."""
    normalized: list[str] = []
    for target in targets:
        service = target.strip().removeprefix(f"{NOTIFY_DOMAIN}.")
        if not service:
            continue
        if not hass.services.has_service(NOTIFY_DOMAIN, service):
            return normalized, target
        if (name := f"{NOTIFY_DOMAIN}.{service}") not in normalized:
            normalized.append(name)
    return normalized, None
