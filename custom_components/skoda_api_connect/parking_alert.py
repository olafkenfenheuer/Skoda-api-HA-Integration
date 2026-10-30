"""Critical notification when a vehicle is parked but not secured."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.components.logbook import async_log_entry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import SkodaVehicle
from .const import CONF_NOTIFY_TARGETS, DOMAIN, PARKED_STATE
from .coordinator import SkodaConfigEntry, SkodaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

# A woken vehicle usually reports within a minute. Without a new report this long after
# the wake-up, the alert is sent anyway, marked as not confirmed.
WAKE_CONFIRM_TIMEOUT = timedelta(minutes=5)

# (field in vehicle.status.overall, label, value that counts as secured, required).
# The API always reports the required fields; reliableLockStatus is optional and only
# checked when the vehicle reports it.
SECURED_CHECKS: tuple[tuple[str, str, str, bool], ...] = (
    ("reliableLockStatus", "Reliable lock status", "LOCKED", False),
    ("doors", "Doors", "CLOSED", True),
    ("doorsLocked", "Doors locked", "YES", True),
    ("locked", "Locked", "YES", True),
    ("windows", "Windows", "CLOSED", True),
)
# Reported for vehicles without electric windows; such a check is skipped.
_UNSUPPORTED = "UNSUPPORTED"

# Makes the Companion app alert even in silent / Do Not Disturb mode.
# "push" is read by iOS, the other keys by Android; each ignores the other's.
CRITICAL_PUSH_DATA: dict[str, Any] = {
    "push": {"sound": {"name": "default", "critical": 1, "volume": 1.0}},
    "ttl": 0,
    "priority": "high",
    "channel": "alarm_stream",
}


def is_parked(vehicle: SkodaVehicle) -> bool | None:
    """Return whether the vehicle is parked, or None if the API did not report it."""
    state = vehicle.get("parkingPosition", "state")
    return None if state is None else state == PARKED_STATE


def unsecured_reasons(vehicle: SkodaVehicle) -> list[str]:
    """Return what is not secured, or an empty list if not parked or all secured.

    An UNKNOWN value, or a missing required one, counts as not secured, since it
    cannot be confirmed.
    """
    if not is_parked(vehicle):
        return []
    reasons = []
    for field_name, label, secured, required in SECURED_CHECKS:
        value = vehicle.get("status", "overall", field_name)
        if value is None and not required:
            continue
        if value != secured and value != _UNSUPPORTED:
            reasons.append(f"{label}: {value or 'unknown'}")
    return reasons


def _last_report(stamp: datetime | None) -> str:
    """Describe the last report: its time, plus the date if it was not today."""
    if stamp is None:
        return "time of the last report unknown"
    local = dt_util.as_local(stamp)
    if local.date() == dt_util.now().date():
        return f"last report at {local:%H:%M}"
    return f"last report at {local:%Y-%m-%d %H:%M}"


@dataclass
class _Incident:
    """A vehicle that was seen parked and not secured."""

    since: datetime
    notified: bool = False
    # When the vehicle accepted the wake-up sent to confirm the incident with a fresh report.
    woken_at: datetime | None = None
    # A wake-up command is on its way (not stored).
    waking: bool = False
    cancel_timer: CALLBACK_TYPE | None = None


class SkodaParkingAlert:
    """Sends one notification per incident and vehicle, after the grace period.

    An incident starts at the first poll that shows the vehicle parked and not secured,
    and ends at the first poll that shows it secured or not parked. Failed polls neither
    start nor end an incident. Incidents are stored, so a restart or reload does not
    send the alert again.

    If the vehicle reported the problem within one polling interval before that poll
    (it parked since the previous poll), the incident begins at that report instead.
    The vehicle usually sleeps right after parking and reports nothing newer, so this
    report is as current as the data gets.

    The alert is confirmed by data the vehicle reported when or after the incident
    began: an older snapshot may miss that the vehicle was secured without reporting
    it. If there is no such report when the grace period ends, the vehicle is woken
    once (two requests), and the alert waits up to ``WAKE_CONFIRM_TIMEOUT`` for the
    report that follows. If the vehicle cannot be woken (no known charge mode, read-only
    mode, rate limit pause, low quota), the wake-up fails or no report follows, the alert
    is sent anyway and says that it is not confirmed: a vehicle that stays silent must
    not keep the alert back for good.

    Wake-ups and alerts are written to the logbook of the "Parked unsecured" sensor.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SkodaConfigEntry,
        coordinator: SkodaDataUpdateCoordinator,
    ) -> None:
        """Initialize the alert."""
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._incidents: dict[str, _Incident] = {}
        self._store: Store[dict[str, dict[str, Any]]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.parking_alert"
        )
        self._unloaded = False

    async def async_start(self) -> None:
        """Restore open incidents, then watch the polls and the options."""
        stored = await self._store.async_load() or {}
        for vin, incident in stored.items():
            since = dt_util.parse_datetime(str(incident.get("since")))
            if vin in self._coordinator.vins and since is not None:
                woken_at = dt_util.parse_datetime(str(incident.get("woken_at")))
                if woken_at is None and incident.get("woken"):
                    # Stored by an older version without the time: the wake-up is long
                    # past, so do not wait for its report any more.
                    woken_at = since
                self._incidents[vin] = _Incident(
                    since, bool(incident.get("notified")), woken_at
                )
        entry = self._entry
        entry.async_on_unload(self._coordinator.async_add_listener(self._async_check))
        # The grace period or the notification targets changed.
        entry.async_on_unload(entry.add_update_listener(self._async_options_updated))
        entry.async_on_unload(self._async_unload)
        self._async_check()

    @callback
    def _async_unload(self) -> None:
        # An update listener task may still run after a reload has unloaded the entry.
        self._unloaded = True
        for incident in self._incidents.values():
            self._async_cancel_timer(incident)

    @callback
    def _async_save(self) -> None:
        data = {
            vin: {
                "since": incident.since.isoformat(),
                "notified": incident.notified,
                # Kept for older versions, which only read "woken".
                "woken": incident.woken_at is not None,
                "woken_at": incident.woken_at and incident.woken_at.isoformat(),
            }
            for vin, incident in self._incidents.items()
        }
        # Unloading the entry waits for this task, so a reload reads the latest state.
        self._entry.async_create_task(self._hass, self._store.async_save(data))

    @callback
    def _async_check(self) -> None:
        coordinator = self._coordinator
        if self._unloaded or not coordinator.last_update_success or not coordinator.data:
            return
        for vin, vehicle in coordinator.data.vehicles.items():
            # Data cached from before a restart may be stale; wait for a real poll.
            if coordinator.last_success.get(vin) is None:
                continue
            incident = self._incidents.get(vin)
            if not unsecured_reasons(vehicle):
                if incident is not None:
                    self._async_cancel_timer(incident)
                    del self._incidents[vin]
                    self._async_save()
                continue
            if incident is None:
                self._incidents[vin] = _Incident(since=self._incident_start(vin, vehicle))
                self._async_save()
                self._async_schedule(vin)
            elif not incident.notified:
                # Restored after a restart, or still waiting for notification targets
                # or a fresh report, which this poll may have brought.
                self._async_schedule(vin)

    def _incident_start(self, vin: str, vehicle: SkodaVehicle) -> datetime:
        """Return when a new incident began: the report showing it, if it is recent."""
        now = dt_util.utcnow()
        reported = vehicle.captured("status")
        coordinator = self._coordinator
        interval = timedelta(
            minutes=coordinator.interval_minutes(vin, coordinator.active_interval_kind(vin))
        )
        if reported is not None and now - interval <= reported <= now:
            return reported
        return now

    async def _async_options_updated(
        self, hass: HomeAssistant, entry: SkodaConfigEntry
    ) -> None:
        if self._unloaded:
            return
        for vin in list(self._incidents):
            self._async_schedule(vin)

    @callback
    def _async_schedule(self, vin: str) -> None:
        """(Re)arm the timer of an open incident."""
        incident = self._incidents[vin]
        self._async_cancel_timer(incident)
        if incident.notified:
            return
        grace = timedelta(minutes=self._coordinator.alert_grace_minutes(vin))
        delay = (incident.since + grace - dt_util.utcnow()).total_seconds()
        if delay <= 0:
            self._async_fire(vin)
        else:
            incident.cancel_timer = async_call_later(
                self._hass, delay, partial(self._async_fire, vin)
            )

    @staticmethod
    @callback
    def _async_cancel_timer(incident: _Incident) -> None:
        if incident.cancel_timer is not None:
            incident.cancel_timer()
            incident.cancel_timer = None

    @callback
    def _async_fire(self, vin: str, _now: datetime | None = None) -> None:
        incident = self._incidents.get(vin)
        if self._unloaded or incident is None:
            return
        incident.cancel_timer = None
        if incident.waking:
            # The wake-up reschedules once the vehicle accepted or refused it.
            return
        # Use the latest known data; it may have changed since the incident began.
        vehicle = self._coordinator.data.vehicles[vin]
        if not unsecured_reasons(vehicle) or not self._entry.options.get(CONF_NOTIFY_TARGETS):
            # Without targets nothing is sent, and the incident stays open so
            # targets added later still get notified.
            return
        captured = vehicle.captured("status")
        if captured is not None and captured >= incident.since:
            self._async_alert(vin, confirmed=True)
            return
        # The vehicle may have been secured since without reporting it: wake it once to
        # get a newer report, which every later poll checks for.
        if incident.woken_at is None:
            self._async_wake_once(vin, incident)
            return
        deadline = incident.woken_at + WAKE_CONFIRM_TIMEOUT
        delay = (deadline - dt_util.utcnow()).total_seconds()
        if delay > 0:
            incident.cancel_timer = async_call_later(
                self._hass, delay, partial(self._async_fire, vin)
            )
            return
        self._async_log(vin, "did not report after the wake-up")
        self._async_alert(vin, confirmed=False)

    @callback
    def _async_wake_once(self, vin: str, incident: _Incident) -> None:
        coordinator = self._coordinator
        if not coordinator.supports_wake(vin):
            blocked: str | None = "the current charge mode of the vehicle is unknown"
        else:
            blocked = coordinator.wake_blocked_reason(vin)
        if blocked is not None:
            self._async_log(vin, f"was not woken to confirm the parking alert: {blocked}")
            self._async_alert(vin, confirmed=False)
            return
        incident.waking = True
        self._entry.async_create_background_task(
            self._hass, self._async_wake(vin, incident), f"{DOMAIN}_parking_alert_wake_{vin}"
        )

    async def _async_wake(self, vin: str, incident: _Incident) -> None:
        name = self._coordinator.data.vehicles[vin].name
        _LOGGER.info("Waking %s to confirm that it is parked but not secured", name)
        try:
            # The follow-up refresh of the command brings the new report.
            await self._coordinator.async_wake_vehicle(vin)
        except HomeAssistantError as err:
            if self._unloaded or self._incidents.get(vin) is not incident:
                return
            _LOGGER.warning("Could not wake %s for the parking alert: %s", name, err)
            self._async_log(vin, f"could not be woken to confirm the parking alert: {err}")
            self._async_alert(vin, confirmed=False)
            return
        finally:
            # Also on unexpected errors: a stuck flag would hold the alert back for good.
            incident.waking = False
        if self._unloaded or self._incidents.get(vin) is not incident:
            # Secured or no longer parked meanwhile.
            return
        incident.woken_at = dt_util.utcnow()
        self._async_save()
        self._async_log(vin, "was woken to confirm that it is parked but not secured")
        # Waits for the report, or sends the alert if a poll already brought it.
        self._async_schedule(vin)

    @callback
    def _async_alert(self, vin: str, confirmed: bool) -> None:
        """Send the alert of an open incident on the latest data, and mark it as sent."""
        incident = self._incidents[vin]
        vehicle = self._coordinator.data.vehicles[vin]
        reasons = unsecured_reasons(vehicle)
        targets: list[str] = self._entry.options.get(CONF_NOTIFY_TARGETS, [])
        if not reasons or not targets:
            return
        self._async_cancel_timer(incident)
        incident.notified = True
        self._async_save()
        last_report = _last_report(vehicle.captured("status"))
        message = "Parked, but: " + ", ".join(reasons)
        if confirmed:
            self._async_log(vin, f"parking alert sent ({last_report})")
        else:
            message += f". Not confirmed: {last_report}."
            self._async_log(vin, f"parking alert sent, not confirmed ({last_report})")
        # Not a background task: those are cancelled on unload, which would lose an
        # alert that is already stored as sent.
        self._entry.async_create_task(
            self._hass,
            self._async_send(targets, vehicle.name, message),
            f"{DOMAIN}_parking_alert_{vin}",
        )

    @callback
    def _async_log(self, vin: str, message: str) -> None:
        """Write to the logbook of the vehicle's "Parked unsecured" sensor."""
        entity_id = er.async_get(self._hass).async_get_entity_id(
            "binary_sensor", DOMAIN, f"{vin}_parked_unsecured"
        )
        name = self._coordinator.data.vehicles[vin].name
        async_log_entry(self._hass, name, message, DOMAIN, entity_id)

    async def _async_send(self, targets: list[str], name: str, message: str) -> None:
        title = f"{name} is not secured"
        await asyncio.gather(
            *(self._async_send_one(target, title, message) for target in targets)
        )

    async def _async_send_one(self, target: str, title: str, message: str) -> None:
        domain, _, service = target.partition(".")
        service_data: dict[str, Any] = {"title": title, "message": message}
        if service.startswith("mobile_app_"):
            service_data["data"] = CRITICAL_PUSH_DATA
        try:
            await self._hass.services.async_call(domain, service, service_data, blocking=True)
        except Exception:  # noqa: BLE001 - one failing target must not stop the others
            _LOGGER.exception("Could not send the parking alert to %s", target)
