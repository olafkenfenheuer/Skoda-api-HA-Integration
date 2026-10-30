"""Tests for the parking alert, its grace period, targets and sensors."""

from __future__ import annotations

import copy
import time
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.components.logbook import EVENT_LOGBOOK_ENTRY
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.skoda_api_connect.api import (
    RateLimitInfo,
    SkodaApiError,
    SkodaRateLimitError,
    SkodaVehicle,
)
from custom_components.skoda_api_connect.const import (
    CONF_API_KEY,
    CONF_CHARGING_SCAN_INTERVAL,
    CONF_NOTIFY_TARGETS,
    CONF_READ_ONLY,
    CONF_VEHICLE_INTERVALS,
    CONF_VINS,
    DOMAIN,
    KEY_ALERT_GRACE,
)
from custom_components.skoda_api_connect.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.skoda_api_connect.parking_alert import _last_report, unsecured_reasons

from .conftest import VIN

GET = "custom_components.skoda_api_connect.api.SkodaApi.get_vehicle"
SET_MODE = "custom_components.skoda_api_connect.api.SkodaApi.set_charge_mode"
PHONE = "notify.mobile_app_phone"

SECURED = {
    "name": "Car 1",
    "status": {
        "overall": {
            "doorsLocked": "YES",
            "locked": "YES",
            "doors": "CLOSED",
            "windows": "CLOSED",
            "lights": "OFF",
            "reliableLockStatus": "LOCKED",
        }
    },
    "parkingPosition": {"state": "PARKED"},
}


def _data(state: str = "PARKED", **overall: str) -> dict:
    data = copy.deepcopy(SECURED)
    data["parkingPosition"]["state"] = state
    data["status"]["overall"].update(overall)
    return data


UNSECURED = _data(doors="OPEN", windows="OPEN")


def _entry(grace: int | None = 0, targets: list[str] | None = None) -> MockConfigEntry:
    options: dict = {}
    if targets is not None:
        options[CONF_NOTIFY_TARGETS] = targets
    if grace is not None:
        options[CONF_VEHICLE_INTERVALS] = {VIN: {KEY_ALERT_GRACE: grace}}
    return MockConfigEntry(
        domain=DOMAIN, data={CONF_API_KEY: "key", CONF_VINS: [VIN]}, options=options
    )


class _Api:
    """Serves the current payload from get_vehicle.

    While ``fresh`` is set, the status counts as reported by the vehicle after the
    incident began; otherwise the payload's own timestamp is kept.
    """

    def __init__(self, data: dict) -> None:
        self.data = data
        self.fresh = True
        self.mock = AsyncMock(side_effect=self._get)

    async def _get(self, vin, include=None):
        data = copy.deepcopy(self.data)
        if self.fresh and "status" in data:
            data["status"]["carCapturedTimestamp"] = _stamp(timedelta(minutes=1))
        return SkodaVehicle(vin=vin, data=data)


def _stamp(offset: timedelta) -> str:
    return (dt_util.utcnow() + offset).isoformat()


def _stale(data: dict) -> dict:
    """The payload as last reported an hour ago, by a vehicle that can be woken."""
    data = copy.deepcopy(data)
    data["status"]["carCapturedTimestamp"] = _stamp(-timedelta(hours=1))
    data["charging"] = {"settings": {"preferredChargeMode": "MANUAL"}}
    return data


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, data: dict, fresh: bool = True):
    api = _Api(data)
    api.fresh = fresh
    patcher = patch(GET, new=api.mock)
    patcher.start()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return api, patcher


async def _poll(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    coordinator = entry.runtime_data
    coordinator._force.add(VIN)
    await coordinator.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)


async def _tick(hass: HomeAssistant, freezer, minutes: float) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


def test_unsecured_reasons() -> None:
    def reasons(data: dict) -> list[str]:
        return unsecured_reasons(SkodaVehicle(vin=VIN, data=data))

    assert reasons(SECURED) == []
    assert reasons(UNSECURED) == ["Doors: OPEN", "Windows: OPEN"]
    assert reasons(_data("IN_MOTION", doors="OPEN")) == []
    assert reasons({"status": SECURED["status"]}) == []  # parking state not reported
    # Without electric windows the window check is skipped.
    assert reasons(_data(windows="UNSUPPORTED")) == []
    # Unknown or missing values cannot be confirmed as secured.
    assert reasons(_data(doorsLocked="TRUNK_OPENED", reliableLockStatus="UNKNOWN")) == [
        "Reliable lock status: UNKNOWN",
        "Doors locked: TRUNK_OPENED",
    ]
    # reliableLockStatus is optional in the API: a vehicle that does not report it is
    # judged by the other checks only.
    without_reliable = _data()
    del without_reliable["status"]["overall"]["reliableLockStatus"]
    assert reasons(without_reliable) == []
    assert reasons({"name": "Car 1", "parkingPosition": {"state": "PARKED"}}) == [
        "Doors: unknown",
        "Doors locked: unknown",
        "Locked: unknown",
        "Windows: unknown",
    ]


async def test_immediate_alert_once_per_incident(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        assert len(calls) == 1
        assert calls[0].data["title"] == "Car 1 is not secured"
        assert calls[0].data["message"] == "Parked, but: Doors: OPEN, Windows: OPEN"
        assert calls[0].data["data"]["push"]["sound"]["critical"] == 1
        assert calls[0].data["data"]["channel"] == "alarm_stream"

        await _poll(hass, entry)  # still unsecured: no repeat
        assert len(calls) == 1

        api.data = SECURED
        await _poll(hass, entry)
        api.data = _data(locked="NO", reliableLockStatus="UNLOCKED")  # new incident
        await _poll(hass, entry)
        assert len(calls) == 2
        assert calls[1].data["message"] == (
            "Parked, but: Reliable lock status: UNLOCKED, Locked: NO"
        )
    finally:
        p.stop()


async def test_grace_period(hass: HomeAssistant, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(grace=7, targets=[PHONE])
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        assert calls == []
        await _tick(hass, freezer, 5)
        await _poll(hass, entry)  # still unsecured, grace not over
        assert calls == []
        await _tick(hass, freezer, 2)
        assert len(calls) == 1
    finally:
        p.stop()


async def test_secured_within_grace_period(hass: HomeAssistant, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(grace=10, targets=[PHONE])
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        await _tick(hass, freezer, 5)
        api.data = SECURED
        await _poll(hass, entry)
        await _tick(hass, freezer, 10)
        assert calls == []
    finally:
        p.stop()


async def test_failed_poll_keeps_incident(hass: HomeAssistant, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(grace=7, targets=[PHONE])
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        api.mock.side_effect = SkodaRateLimitError("slow down", status=429)
        await _poll(hass, entry)
        await _tick(hass, freezer, 7)  # the last known data is still unsecured
        assert len(calls) == 1
    finally:
        p.stop()


async def test_grace_slider_reschedules(hass: HomeAssistant, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(grace=None, targets=[PHONE])  # default: 5 minutes
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        entity_id = er.async_get(hass).async_get_entity_id(
            "number", DOMAIN, f"{VIN}_parking_alert_grace"
        )
        state = hass.states.get(entity_id)
        assert state.state == "5"
        assert (state.attributes["min"], state.attributes["max"], state.attributes["step"]) == (0, 30, 1)
        assert state.attributes["mode"] == "slider"

        await _tick(hass, freezer, 1)
        await hass.services.async_call(
            "number", "set_value", {"entity_id": entity_id, "value": 2}, blocking=True
        )
        await hass.async_block_till_done(wait_background_tasks=True)
        assert entry.options[CONF_VEHICLE_INTERVALS][VIN][KEY_ALERT_GRACE] == 2
        assert entry.options[CONF_NOTIFY_TARGETS] == [PHONE]  # untouched
        assert calls == []
        # Grace counts from when the problem was first seen, so it is due 2 minutes in.
        await _tick(hass, freezer, 1)
        assert len(calls) == 1
    finally:
        p.stop()


async def test_not_parked(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    api, p = await _setup(hass, entry, _data("IN_MOTION", doors="OPEN"))
    try:
        await _poll(hass, entry)
        assert calls == []
    finally:
        p.stop()


async def test_multiple_targets(hass: HomeAssistant) -> None:
    phone = async_mock_service(hass, "notify", "mobile_app_phone")
    telegram = async_mock_service(hass, "notify", "telegram")
    entry = _entry(targets=[PHONE, "notify.telegram"])
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        assert len(phone) == 1 and "data" in phone[0].data
        assert len(telegram) == 1 and "data" not in telegram[0].data  # not critical
    finally:
        p.stop()


async def test_no_alert_from_cached_data(hass: HomeAssistant, hass_storage) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    key = f"{DOMAIN}.{entry.entry_id}"
    hass_storage[key] = {"version": 1, "minor_version": 1, "key": key, "data": {VIN: UNSECURED}}
    entry.add_to_hass(hass)
    with patch(GET, new=AsyncMock(side_effect=SkodaRateLimitError("slow down", status=429))):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
    # Set up from the cache while rate limited, but the cache may be stale.
    assert entry.runtime_data.data.vehicles[VIN].get("status", "overall", "doors") == "OPEN"
    assert calls == []
    sensor = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{VIN}_parked_unsecured"
    )
    assert hass.states.get(sensor).state == "unknown"
    assert "reasons" not in hass.states.get(sensor).attributes

    api = _Api(UNSECURED)
    with (
        patch(GET, new=api.mock),
        patch(
            "custom_components.skoda_api_connect.coordinator.time.monotonic",
            return_value=time.monotonic() + 3700,
        ),
    ):
        await _poll(hass, entry)
    assert len(calls) == 1
    assert hass.states.get(sensor).state == "on"


async def test_options_flow_targets(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    async_mock_service(hass, "notify", "telegram")
    async_mock_service(hass, "notify", "send_message")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "key", CONF_VINS: [VIN]},
        options={**_entry().options, CONF_SCAN_INTERVAL: 15},
    )
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        assert calls == []  # no targets yet: the incident stays open
        result = await hass.config_entries.options.async_init(entry.entry_id)
        key = next(k for k in result["data_schema"].schema if k == CONF_NOTIFY_TARGETS)
        offered = result["data_schema"].schema[key].config["options"]
        assert offered == [PHONE, "notify.telegram"]

        base = {CONF_SCAN_INTERVAL: 15, CONF_CHARGING_SCAN_INTERVAL: 5, CONF_READ_ONLY: False}
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**base, CONF_NOTIFY_TARGETS: ["notify.nope"]}
        )
        assert result["errors"] == {CONF_NOTIFY_TARGETS: "unknown_notify_target"}
        assert result["description_placeholders"]["target"] == "notify.nope"

        # Names are normalised and de-duplicated; the open incident is alerted at once.
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {**base, CONF_NOTIFY_TARGETS: ["mobile_app_phone", PHONE, " notify.telegram "]},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done(wait_background_tasks=True)
        assert entry.options[CONF_NOTIFY_TARGETS] == [PHONE, "notify.telegram"]
        assert entry.options[CONF_VEHICLE_INTERVALS] == {VIN: {KEY_ALERT_GRACE: 0}}
        assert len(calls) == 1

        # The current targets are suggested in the form.
        result = await hass.config_entries.options.async_init(entry.entry_id)
        key = next(k for k in result["data_schema"].schema if k == CONF_NOTIFY_TARGETS)
        assert key.description == {"suggested_value": [PHONE, "notify.telegram"]}

        # Clearing the field removes the targets, whether it is sent empty or left out.
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**base, CONF_NOTIFY_TARGETS: []}
        )
        assert entry.options[CONF_NOTIFY_TARGETS] == []
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_NOTIFY_TARGETS: [PHONE]}
        )
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], base)
        assert entry.options[CONF_NOTIFY_TARGETS] == []
    finally:
        p.stop()


async def test_sensors(hass: HomeAssistant) -> None:
    entry = _entry()
    api, p = await _setup(
        hass, entry, _data(doors="OPEN", doorsLocked="OPENED", reliableLockStatus="UNLOCKED")
    )
    try:
        registry = er.async_get(hass)

        def state(platform: str, key: str):
            entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{VIN}_{key}")
            return hass.states.get(entity_id)

        assert state("sensor", "doors_locked").state == "OPENED"
        assert state("sensor", "reliable_lock_status").state == "UNLOCKED"
        assert state("sensor", "parking_state").state == "PARKED"
        unsecured = state("binary_sensor", "parked_unsecured")
        assert unsecured.state == "on"
        assert unsecured.attributes["device_class"] == "problem"
        assert unsecured.attributes["reasons"] == [
            "Reliable lock status: UNLOCKED",
            "Doors: OPEN",
            "Doors locked: OPENED",
        ]

        api.data = _data("IN_MOTION", doors="OPEN")
        await _poll(hass, entry)
        assert state("binary_sensor", "parked_unsecured").state == "off"
        assert state("sensor", "parking_state").state == "IN_MOTION"
    finally:
        p.stop()


async def test_sensors_not_created_without_data(hass: HomeAssistant) -> None:
    entry = _entry()
    api, p = await _setup(hass, entry, {"name": "Car 1"})
    try:
        registry = er.async_get(hass)
        for platform, key in (
            ("sensor", "doors_locked"),
            ("sensor", "reliable_lock_status"),
            ("sensor", "parking_state"),
            ("binary_sensor", "parked_unsecured"),
        ):
            assert registry.async_get_entity_id(platform, DOMAIN, f"{VIN}_{key}") is None
    finally:
        p.stop()


async def test_diagnostics_redact_targets(hass: HomeAssistant) -> None:
    async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    api, p = await _setup(hass, entry, SECURED)
    try:
        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result["options"][CONF_NOTIFY_TARGETS] == "**REDACTED**"
        assert "mobile_app_phone" not in str(result)
    finally:
        p.stop()


async def test_reload_does_not_repeat_alert(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        assert len(calls) == 1
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
        await _poll(hass, entry)
        assert len(calls) == 1  # same incident, already notified

        api.data = SECURED  # the incident ends ...
        await _poll(hass, entry)
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
        api.data = UNSECURED  # ... so this is a new one
        await _poll(hass, entry)
        assert len(calls) == 2
    finally:
        p.stop()


async def test_read_only_reload_with_new_targets_alerts_once(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry()  # no targets yet: the incident stays open
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        assert calls == []
        # Adding targets and switching read-only mode reloads the entry while the old
        # alert also sees the new targets.
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_NOTIFY_TARGETS: [PHONE], CONF_READ_ONLY: True}
        )
        await hass.async_block_till_done(wait_background_tasks=True)
        await _poll(hass, entry)
        assert len(calls) == 1
    finally:
        p.stop()


def _stored(entry: MockConfigEntry, since, notified: bool) -> tuple[str, dict]:
    key = f"{DOMAIN}.{entry.entry_id}.parking_alert"
    return key, {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {VIN: {"since": since.isoformat(), "notified": notified}},
    }


async def test_restart_keeps_notified_incident(hass: HomeAssistant, hass_storage) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    key, stored = _stored(entry, dt_util.utcnow() - timedelta(hours=1), notified=True)
    hass_storage[key] = stored
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        assert calls == []
    finally:
        p.stop()


async def test_restart_resumes_grace_period(hass: HomeAssistant, hass_storage) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(grace=5, targets=[PHONE])
    key, stored = _stored(entry, dt_util.utcnow() - timedelta(minutes=10), notified=False)
    hass_storage[key] = stored
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        assert len(calls) == 1  # the grace period ran out during the restart
    finally:
        p.stop()


async def test_failing_target_does_not_stop_others(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")

    async def _broken(call) -> None:
        raise ValueError("boom")

    hass.services.async_register("notify", "broken", _broken)
    entry = _entry(targets=["notify.broken", PHONE])
    api, p = await _setup(hass, entry, UNSECURED)
    try:
        assert len(calls) == 1
    finally:
        p.stop()


async def test_options_error_keeps_entered_values(hass: HomeAssistant) -> None:
    entry = _entry()
    api, p = await _setup(hass, entry, SECURED)
    try:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_SCAN_INTERVAL: 20,
                CONF_CHARGING_SCAN_INTERVAL: 7,
                CONF_READ_ONLY: True,
                CONF_NOTIFY_TARGETS: ["notify.nope"],
            },
        )
        assert result["errors"] == {CONF_NOTIFY_TARGETS: "unknown_notify_target"}
        defaults = {
            str(key): key.default() if callable(key.default) else key.description
            for key in result["data_schema"].schema
        }
        assert defaults[CONF_SCAN_INTERVAL] == 20
        assert defaults[CONF_CHARGING_SCAN_INTERVAL] == 7
        assert defaults[CONF_READ_ONLY] is True
        assert defaults[CONF_NOTIFY_TARGETS] == {"suggested_value": ["notify.nope"]}
    finally:
        p.stop()


async def test_stale_data_wakes_vehicle_once(hass: HomeAssistant, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    with patch(SET_MODE, new=AsyncMock()) as set_mode:
        api, p = await _setup(hass, entry, _stale(UNSECURED), fresh=False)
        try:
            # The data predates the incident: wake the vehicle instead of alerting.
            assert calls == []
            set_mode.assert_awaited_once_with(VIN, "MANUAL")
            await _tick(hass, freezer, 1)  # the follow-up refresh brings no new report
            await _poll(hass, entry)
            assert calls == []
            assert set_mode.await_count == 1  # no second wake for the same incident

            api.fresh = True  # the vehicle reports at last, still not secured
            await _poll(hass, entry)
            assert len(calls) == 1
        finally:
            p.stop()


async def test_stale_data_secured_after_wake(hass: HomeAssistant, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    with patch(SET_MODE, new=AsyncMock()) as set_mode:
        api, p = await _setup(hass, entry, _stale(UNSECURED), fresh=False)
        try:
            # It was locked meanwhile, which the wake-up brings to light.
            api.data, api.fresh = _stale(SECURED), True
            await _tick(hass, freezer, 1)
            assert calls == []

            api.data, api.fresh = _stale(UNSECURED), False  # a new incident wakes again
            await _poll(hass, entry)
            assert set_mode.await_count == 2
            await _tick(hass, freezer, 1)
            assert calls == []
        finally:
            p.stop()


async def test_stale_data_read_only_alerts_unconfirmed(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "key", CONF_VINS: [VIN]},
        options={**_entry(targets=[PHONE]).options, CONF_READ_ONLY: True},
    )
    logbook = async_capture_events(hass, EVENT_LOGBOOK_ENTRY)
    with patch(SET_MODE, new=AsyncMock()) as set_mode:
        api, p = await _setup(hass, entry, _stale(UNSECURED), fresh=False)
        try:
            # Read-only mode sends no commands, so the alert cannot be confirmed.
            set_mode.assert_not_awaited()
            assert len(calls) == 1
            assert calls[0].data["message"].startswith(
                "Parked, but: Doors: OPEN, Windows: OPEN. Not confirmed: last report at "
            )
            assert [event.data["message"] for event in logbook] == [
                "was not woken to confirm the parking alert: read-only mode",
                _unconfirmed_entry(api),
            ]
            api.fresh = True
            await _poll(hass, entry)
            assert len(calls) == 1  # one alert per incident
        finally:
            p.stop()


async def test_vehicle_that_cannot_be_woken_alerts_unconfirmed(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    logbook = async_capture_events(hass, EVENT_LOGBOOK_ENTRY)
    stale = _stale(UNSECURED)
    del stale["charging"]  # e.g. a combustion vehicle: no charge mode to re-send
    with patch(SET_MODE, new=AsyncMock()) as set_mode:
        api, p = await _setup(hass, entry, stale, fresh=False)
        try:
            set_mode.assert_not_awaited()
            assert len(calls) == 1
            assert "Not confirmed: last report at " in calls[0].data["message"]
            sensor = er.async_get(hass).async_get_entity_id(
                "binary_sensor", DOMAIN, f"{VIN}_parked_unsecured"
            )
            assert [(e.data["entity_id"], e.data["name"]) for e in logbook] == [
                (sensor, "Car 1"),
                (sensor, "Car 1"),
            ]
            assert logbook[0].data["message"] == (
                "was not woken to confirm the parking alert: "
                "the current charge mode of the vehicle is unknown"
            )
        finally:
            p.stop()


async def test_low_quota_alerts_unconfirmed(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    logbook = async_capture_events(hass, EVENT_LOGBOOK_ENTRY)
    with (
        patch(SET_MODE, new=AsyncMock()) as set_mode,
        patch(
            "custom_components.skoda_api_connect.coordinator.SkodaDataUpdateCoordinator"
            ".wake_blocked_reason",
            return_value="only 3 requests of the quota left",
        ),
    ):
        api, p = await _setup(hass, entry, _stale(UNSECURED), fresh=False)
        try:
            set_mode.assert_not_awaited()
            assert len(calls) == 1
            assert logbook[0].data["message"] == (
                "was not woken to confirm the parking alert: only 3 requests of the quota left"
            )
        finally:
            p.stop()


async def test_failed_wake_alerts_unconfirmed(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    logbook = async_capture_events(hass, EVENT_LOGBOOK_ENTRY)
    error = SkodaApiError("vehicle unreachable", status=500)
    with patch(SET_MODE, new=AsyncMock(side_effect=error)) as set_mode:
        api, p = await _setup(hass, entry, _stale(UNSECURED), fresh=False)
        try:
            set_mode.assert_awaited_once()
            assert len(calls) == 1
            assert "Not confirmed" in calls[0].data["message"]
            assert logbook[0].data["message"].startswith(
                "could not be woken to confirm the parking alert: "
            )
            await _poll(hass, entry)
            assert set_mode.await_count == 1 and len(calls) == 1
        finally:
            p.stop()


async def test_no_report_after_wake_alerts_unconfirmed(hass: HomeAssistant, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    logbook = async_capture_events(hass, EVENT_LOGBOOK_ENTRY)
    with patch(SET_MODE, new=AsyncMock()) as set_mode:
        api, p = await _setup(hass, entry, _stale(UNSECURED), fresh=False)
        try:
            assert logbook[0].data["message"] == (
                "was woken to confirm that it is parked but not secured"
            )
            await _tick(hass, freezer, 4)  # the follow-up refresh brings no new report
            assert calls == []
            await _tick(hass, freezer, 1)
            assert set_mode.await_count == 1
            assert len(calls) == 1
            assert "Not confirmed" in calls[0].data["message"]
            assert [event.data["message"] for event in logbook][1:] == [
                "did not report after the wake-up",
                _unconfirmed_entry(api),
            ]
        finally:
            p.stop()


async def test_report_after_wake_alerts_at_once(hass: HomeAssistant, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    logbook = async_capture_events(hass, EVENT_LOGBOOK_ENTRY)
    with patch(SET_MODE, new=AsyncMock()):
        api, p = await _setup(hass, entry, _stale(UNSECURED), fresh=False)
        try:
            # The vehicle reports in time for the follow-up refresh, still not secured.
            api.fresh = True
            await _tick(hass, freezer, 1)
            assert len(calls) == 1
            assert calls[0].data["message"] == "Parked, but: Doors: OPEN, Windows: OPEN"
            assert logbook[-1].data["message"].startswith("parking alert sent (last report at ")
        finally:
            p.stop()


async def test_report_since_last_poll_alerts_without_wake(hass: HomeAssistant, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(grace=3, targets=[PHONE])
    with patch(SET_MODE, new=AsyncMock()) as set_mode:
        api, p = await _setup(hass, entry, _stale(_data("IN_MOTION")), fresh=False)
        try:
            # The vehicle parked a minute before this poll, reported once and went to
            # sleep: no newer report will follow.
            await _tick(hass, freezer, 5)
            parked = _stale(UNSECURED)
            parked["status"]["carCapturedTimestamp"] = _stamp(-timedelta(minutes=1))
            api.data = parked
            await _poll(hass, entry)
            assert calls == []
            await _tick(hass, freezer, 2)  # the grace period counts from the report
            assert len(calls) == 1
            set_mode.assert_not_awaited()
        finally:
            p.stop()


async def test_report_older_than_interval_still_wakes(hass: HomeAssistant, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    with patch(SET_MODE, new=AsyncMock()) as set_mode:
        api, p = await _setup(hass, entry, _stale(_data("IN_MOTION")), fresh=False)
        try:
            # Reported before the previous poll (default interval: 10 minutes), so it
            # may be outdated: wake the vehicle instead of alerting.
            parked = _stale(UNSECURED)
            parked["status"]["carCapturedTimestamp"] = _stamp(-timedelta(minutes=11))
            api.data = parked
            await _poll(hass, entry)
            assert calls == []
            set_mode.assert_awaited_once_with(VIN, "MANUAL")
        finally:
            p.stop()


async def test_restart_keeps_wake_state(hass: HomeAssistant, hass_storage, freezer) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    key, stored = _stored(entry, dt_util.utcnow() - timedelta(minutes=10), notified=False)
    woken_at = dt_util.utcnow() - timedelta(minutes=2)
    stored["data"][VIN].update(woken=True, woken_at=woken_at.isoformat())
    hass_storage[key] = stored
    with patch(SET_MODE, new=AsyncMock()) as set_mode:
        api, p = await _setup(hass, entry, _stale(UNSECURED), fresh=False)
        try:
            set_mode.assert_not_awaited()  # already woken for this incident
            assert calls == []  # still waiting for the report
            await _tick(hass, freezer, 3)
            assert len(calls) == 1
            assert "Not confirmed" in calls[0].data["message"]
            data = hass_storage[key]["data"][VIN]
            assert data["notified"] and data["woken"]
            assert data["woken_at"] == woken_at.isoformat()
        finally:
            p.stop()


async def test_restart_with_wake_state_of_older_version(hass: HomeAssistant, hass_storage) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    key, stored = _stored(entry, dt_util.utcnow() - timedelta(minutes=10), notified=False)
    stored["data"][VIN]["woken"] = True  # no wake-up time: woken long ago
    hass_storage[key] = stored
    with patch(SET_MODE, new=AsyncMock()) as set_mode:
        api, p = await _setup(hass, entry, _stale(UNSECURED), fresh=False)
        try:
            set_mode.assert_not_awaited()
            assert len(calls) == 1
            assert "Not confirmed" in calls[0].data["message"]
        finally:
            p.stop()


def _unconfirmed_entry(api: _Api) -> str:
    reported = dt_util.parse_datetime(api.data["status"]["carCapturedTimestamp"])
    return f"parking alert sent, not confirmed ({_last_report(reported)})"


def test_last_report(freezer) -> None:
    freezer.move_to("2026-10-30 12:00:00+00:00")
    assert _last_report(None) == "time of the last report unknown"
    hour_ago = dt_util.utcnow() - timedelta(hours=1)
    assert _last_report(hour_ago) == f"last report at {dt_util.as_local(hour_ago):%H:%M}"
    yesterday = dt_util.utcnow() - timedelta(days=1)
    assert _last_report(yesterday) == (
        f"last report at {dt_util.as_local(yesterday):%Y-%m-%d %H:%M}"
    )


async def test_wake_blocked_reason(hass: HomeAssistant) -> None:
    entry = _entry()
    api, p = await _setup(hass, entry, SECURED)
    try:
        coordinator = entry.runtime_data
        assert coordinator.wake_blocked_reason(VIN) is None
        now = dt_util.utcnow()
        coordinator.api.rate_limits[VIN] = RateLimitInfo(20, 6, None, now)
        assert coordinator.wake_blocked_reason(VIN) is None
        coordinator.api.rate_limits[VIN] = RateLimitInfo(20, 5, None, now)
        assert coordinator.wake_blocked_reason(VIN) == "only 5 requests of the quota left"
        coordinator._paused_until[VIN] = time.monotonic() + 60
        assert coordinator.wake_blocked_reason(VIN) == "rate limit pause"
        coordinator.read_only = True
        assert coordinator.wake_blocked_reason(VIN) == "read-only mode"
        assert not coordinator.can_wake(VIN)
    finally:
        p.stop()


async def test_secured_while_waking(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    logbook = async_capture_events(hass, EVENT_LOGBOOK_ENTRY)
    api = None

    async def _locked_meanwhile(vin, mode) -> None:
        # A poll during the command shows the vehicle locked: the incident ends.
        api.data, api.fresh = _stale(SECURED), True
        await _poll(hass, entry)

    with patch(SET_MODE, new=AsyncMock(side_effect=_locked_meanwhile)) as set_mode:
        api, p = await _setup(hass, entry, _stale(UNSECURED), fresh=False)
        try:
            set_mode.assert_awaited_once()
            assert calls == []
            assert [event.data["message"] for event in logbook] == []
        finally:
            p.stop()


async def test_unexpected_wake_error_does_not_hold_alert_back(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "mobile_app_phone")
    entry = _entry(targets=[PHONE])
    with patch(SET_MODE, new=AsyncMock(side_effect=RuntimeError("boom"))):
        api, p = await _setup(hass, entry, _stale(UNSECURED), fresh=False)
        try:
            assert calls == []
            api.fresh = True  # the vehicle reports on its own later
            await _poll(hass, entry)
            assert len(calls) == 1
        finally:
            p.stop()
