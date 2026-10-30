"""Client for the MyŠkoda Public API (https://public.api.connect.skoda-auto.cz/docs)."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout

from .const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)

PROBLEM_BASE = f"{API_BASE_URL}/problems/"
REQUEST_TIMEOUT = ClientTimeout(total=30)
# Vehicle sections that carry a carCapturedTimestamp, with the name used for them in attributes.
CAPTURED_SECTIONS = {
    "status": "status",
    "charging": "charging",
    "airConditioning": "air_conditioning",
    "odometer": "odometer",
}


class SkodaApiError(Exception):
    """Base error for the MyŠkoda Public API."""

    def __init__(self, message: str, *, status: int | None = None, problem: str | None = None):
        """Store the HTTP status and RFC 9457 problem type (the part after /problems/)."""
        super().__init__(message)
        self.status = status
        self.problem = problem


class SkodaAuthError(SkodaApiError):
    """The API key is expired, invalid or not authorized for the vehicle."""


class SkodaRateLimitError(SkodaApiError):
    """The request quota was exceeded (HTTP 429)."""

    def __init__(self, message: str, *, retry_after: timedelta | None = None, **kwargs: Any):
        """Store the parsed Retry-After value."""
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class SkodaConnectionError(SkodaApiError):
    """The API could not be reached."""


_RETRY_AFTER_DETAIL_RE = re.compile(r"retry after (\d+) seconds", re.IGNORECASE)


def _rate_limit_wait(headers: Mapping[str, str], detail: str) -> timedelta | None:
    """Return how long to wait after a 429.

    The API sends no Retry-After header; it reports the wait in the RateLimit-Reset
    header (seconds) and in the problem detail ("Retry after N seconds").
    """
    if (wait := _parse_retry_after(headers.get("Retry-After"))) is not None:
        return wait
    reset = (headers.get("RateLimit-Reset") or "").strip()
    if reset.isdigit():
        return timedelta(seconds=int(reset))
    if match := _RETRY_AFTER_DETAIL_RE.search(detail):
        return timedelta(seconds=int(match.group(1)))
    return None


def _parse_retry_after(value: str | None) -> timedelta | None:
    """Parse a Retry-After header (seconds or HTTP-date) into a timedelta."""
    if not value:
        return None
    value = value.strip()
    try:
        return timedelta(seconds=int(value))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return retry_at - datetime.now(UTC)
    except (TypeError, ValueError):
        return None


_VEHICLE_PATH_RE = re.compile(r"/vehicles/([^/]+)")


@dataclass
class RateLimitInfo:
    """The request quota of one vehicle as reported by the RateLimit-* response headers."""

    limit: int | None
    remaining: int | None
    reset_at: datetime | None
    updated: datetime


def _rate_limit_info(headers: Mapping[str, str]) -> RateLimitInfo | None:
    """Parse the RateLimit-Limit/-Remaining/-Reset headers, or None if none is present."""

    def number(name: str) -> int | None:
        value = (headers.get(name) or "").strip()
        return int(value) if value.isdigit() else None

    limit, remaining, reset = (
        number("RateLimit-Limit"),
        number("RateLimit-Remaining"),
        number("RateLimit-Reset"),
    )
    if limit is None and remaining is None and reset is None:
        return None
    now = datetime.now(UTC)
    return RateLimitInfo(
        limit, remaining, now + timedelta(seconds=reset) if reset is not None else None, now
    )


@dataclass
class SkodaVehicle:
    """The state of one vehicle as returned by ``GET /api/v1/vehicles/{vin}``."""

    vin: str
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def get(self, *path: str) -> Any:
        """Return a nested value, or None if any part of the path is missing."""
        node: Any = self.data
        for key in path:
            if not isinstance(node, dict):
                return None
            node = node.get(key)
            if node is None:
                return None
        return node

    def captured(self, section: str) -> datetime | None:
        """Return when the vehicle itself last reported one section (e.g. "charging")."""
        value = self.get(section, "carCapturedTimestamp")
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None

    def captured_at(self) -> dict[str, datetime]:
        """Return when the vehicle itself last reported each section, by attribute name."""
        stamps: dict[str, datetime] = {}
        for section, name in CAPTURED_SECTIONS.items():
            if (stamp := self.captured(section)) is not None:
                stamps[name] = stamp
        return stamps

    def last_captured(self) -> datetime | None:
        """Return the newest time the vehicle reported any section to the Škoda servers."""
        stamps = self.captured_at()
        return max(stamps.values()) if stamps else None

    def has(self, *path: str) -> bool:
        """Return whether a nested value is reported (an omitted value means unknown)."""
        return self.get(*path) is not None

    @property
    def name(self) -> str:
        """Return the user-defined vehicle name."""
        return self.data.get("name") or self.vin

    def supports(self, operation: str) -> bool:
        """Return whether the vehicle lists the given remote operation.

        If the list of operations could not be determined, assume it is supported and
        let the API reject the request.
        """
        operations = self.data.get("operations")
        if operations is None:
            return True
        return any(op.get("name") == operation for op in operations)

    def lists(self, operation: str) -> bool:
        """Return whether the vehicle explicitly lists the given remote operation.

        Unlike ``supports`` this is False when the list of operations is unknown.
        """
        operations = self.data.get("operations")
        return operations is not None and any(op.get("name") == operation for op in operations)


class SkodaApi:
    """Thin async client for the MyŠkoda Public API."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        """Initialize the client."""
        self._session = session
        self._api_key = api_key
        # Latest request quota per VIN, updated from the headers of every response.
        self.rate_limits: dict[str, RateLimitInfo] = {}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        url = f"{API_BASE_URL}{path}"
        try:
            async with self._session.request(
                method,
                url,
                json=json,
                params=params,
                timeout=REQUEST_TIMEOUT,
                headers={"X-API-Key": self._api_key, "Accept": "application/json"},
            ) as response:
                self._record_rate_limit(path, response.headers)
                if response.status < 400:
                    _LOGGER.debug(
                        "%s %s -> %s (rate limit remaining: %s)",
                        method,
                        path,
                        response.status,
                        response.headers.get("RateLimit-Remaining"),
                    )
                    if response.content_length == 0 or response.status == 202:
                        return None
                    try:
                        return await response.json(content_type=None)
                    except ValueError as err:
                        raise SkodaApiError(
                            "The MyŠkoda API returned an invalid response", status=response.status
                        ) from err
                raise await self._error_for(response)
        except (ClientError, TimeoutError) as err:
            raise SkodaConnectionError(f"Cannot reach the MyŠkoda API: {err}") from err

    def _record_rate_limit(self, path: str, headers: Mapping[str, str]) -> None:
        match = _VEHICLE_PATH_RE.search(path)
        if match and (info := _rate_limit_info(headers)):
            self.rate_limits[match.group(1)] = info

    @staticmethod
    async def _error_for(response: ClientResponse) -> SkodaApiError:
        problem: dict[str, Any] = {}
        try:
            body = await response.json(content_type=None)
            if isinstance(body, dict):
                problem = body
        except (ClientError, ValueError):
            pass
        problem_type = str(problem.get("type", ""))
        problem_id = (
            problem_type.removeprefix(PROBLEM_BASE) if problem_type.startswith(PROBLEM_BASE) else None
        )
        detail = problem.get("detail") or problem.get("title") or f"HTTP {response.status}"
        kwargs = {"status": response.status, "problem": problem_id}

        if response.status == 401 or problem_id == "api-key-not-authorized":
            return SkodaAuthError(detail, **kwargs)
        if response.status == 429 and problem_id != "vehicle-not-accepting-requests":
            return SkodaRateLimitError(
                detail,
                retry_after=_rate_limit_wait(response.headers, str(detail)),
                **kwargs,
            )
        return SkodaApiError(detail, **kwargs)

    async def get_vehicle(self, vin: str, include: list[str] | None = None) -> SkodaVehicle:
        """Fetch the vehicle and its current state."""
        params = {"include": ",".join(include)} if include else None
        body = await self._request("GET", f"/api/v1/vehicles/{vin}", params=params)
        body = body or {}
        errors = [e.get("type", "") for e in body.get("errors", []) if isinstance(e, dict)]
        return SkodaVehicle(vin=vin, data=body.get("vehicle") or {}, errors=errors)

    async def _command(
        self, method: str, vin: str, path: str, json: Any = None
    ) -> None:
        await self._request(method, f"/api/v1/vehicles/{vin}/{path}", json=json)

    async def start_charging(self, vin: str) -> None:
        """Start charging."""
        await self._command("POST", vin, "charging/start")

    async def stop_charging(self, vin: str) -> None:
        """Stop charging."""
        await self._command("POST", vin, "charging/stop")

    async def set_charging_limit(self, vin: str, percent: int) -> None:
        """Set the target state of charge."""
        await self._command(
            "PUT", vin, "charging/limit", {"targetStateOfChargeInPercent": percent}
        )

    async def set_charge_mode(self, vin: str, mode: str) -> None:
        """Change the charge mode."""
        await self._command("PUT", vin, "charging/mode", {"chargeMode": mode})

    async def start_air_conditioning(
        self, vin: str, temperature: float | None = None
    ) -> None:
        """Start air conditioning, optionally with a target temperature in °C."""
        body: dict[str, Any] = {}
        if temperature is not None:
            body["targetTemperature"] = {"value": temperature, "unit": "CELSIUS"}
        await self._command("POST", vin, "air-conditioning/start", body)

    async def stop_air_conditioning(self, vin: str) -> None:
        """Stop air conditioning."""
        await self._command("POST", vin, "air-conditioning/stop")

    async def stop_auxiliary_heating(self, vin: str) -> None:
        """Stop the auxiliary heating."""
        await self._command("POST", vin, "auxiliary-heating/stop")

    async def start_active_ventilation(self, vin: str) -> None:
        """Start active ventilation."""
        await self._command("POST", vin, "active-ventilation/start")

    async def stop_active_ventilation(self, vin: str) -> None:
        """Stop active ventilation."""
        await self._command("POST", vin, "active-ventilation/stop")
