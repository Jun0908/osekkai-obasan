"""Google Routes adapter and privacy-minimal event feasibility calculation."""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping, Sequence


ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
FIELD_MASK = "routes.duration,routes.distanceMeters"


class RoutesError(RuntimeError):
    """A safe, classifiable Google Maps provider failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _api_key(environ: Mapping[str, str] | None = None) -> str:
    env = environ or os.environ
    value = str(env.get("GOOGLE_ROUTES_API_KEY") or env.get("GOOGLE_MAPS_API_KEY") or "").strip()
    if not value:
        raise RoutesError("ROUTES_CREDENTIAL_MISSING", "Google Routes API key is not configured")
    return value


def _timeout(environ: Mapping[str, str] | None = None) -> float:
    raw = str((environ or os.environ).get("OSEKKAI_ROUTES_TIMEOUT_SECONDS", "12")).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise RoutesError("ROUTES_CONFIG_INVALID", "Routes timeout must be numeric") from exc
    if not 1 <= value <= 30:
        raise RoutesError("ROUTES_CONFIG_INVALID", "Routes timeout must be between 1 and 30 seconds")
    return value


def _duration_seconds(value: Any) -> int:
    if not isinstance(value, str) or not value.endswith("s"):
        raise RoutesError("ROUTES_RESPONSE_INVALID", "Google Routes duration is missing")
    try:
        seconds = float(value[:-1])
    except ValueError as exc:
        raise RoutesError("ROUTES_RESPONSE_INVALID", "Google Routes duration is invalid") from exc
    if not 0 <= seconds <= 24 * 60 * 60:
        raise RoutesError("ROUTES_RESPONSE_INVALID", "Google Routes duration is outside the supported range")
    return math.ceil(seconds)


def _lat_lng(value: Mapping[str, Any], name: str) -> dict[str, float]:
    try:
        latitude = float(value["latitude"] if "latitude" in value else value["lat"])
        longitude = float(value["longitude"] if "longitude" in value else value["lng"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RoutesError("ROUTES_LOCATION_INVALID", f"{name} coordinates are invalid") from exc
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise RoutesError("ROUTES_LOCATION_INVALID", f"{name} coordinates are outside valid bounds")
    return {"latitude": latitude, "longitude": longitude}


def _waypoint(coordinates: Mapping[str, Any]) -> dict[str, Any]:
    return {"location": {"latLng": _lat_lng(coordinates, "waypoint")}}


def _decode_json_response(response: Any, provider: str) -> dict[str, Any]:
    try:
        value = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RoutesError("ROUTES_RESPONSE_INVALID", f"{provider} response is malformed") from exc
    if not isinstance(value, dict):
        raise RoutesError("ROUTES_RESPONSE_INVALID", f"{provider} response is malformed")
    return value


def _http_error(exc: urllib.error.HTTPError) -> RoutesError:
    if exc.code == 429:
        return RoutesError("ROUTES_QUOTA_EXCEEDED", "Google Routes quota was exceeded")
    if exc.code in {401, 403}:
        return RoutesError("ROUTES_AUTH_FAILED", "Google Routes rejected the configured credential")
    if 500 <= exc.code <= 599:
        return RoutesError("ROUTES_UNAVAILABLE", "Google Routes is temporarily unavailable")
    return RoutesError("ROUTES_REQUEST_FAILED", f"Google Routes request failed with HTTP {exc.code}")


def google_routes_transport(
    api_key: str,
    payload: Mapping[str, Any],
    *,
    timeout: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        ROUTES_URL,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _decode_json_response(response, "Google Routes")
    except urllib.error.HTTPError as exc:
        raise _http_error(exc) from exc
    except (OSError, TimeoutError) as exc:
        raise RoutesError("ROUTES_TIMEOUT", "Google Routes request timed out or could not connect") from exc


def google_geocode_transport(api_key: str, address: str, *, timeout: float) -> dict[str, Any]:
    query = urllib.parse.urlencode({"address": address, "region": "jp", "language": "ja", "key": api_key})
    request = urllib.request.Request(f"{GEOCODE_URL}?{query}", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _decode_json_response(response, "Google Geocoding")
    except urllib.error.HTTPError as exc:
        raise _http_error(exc) from exc
    except (OSError, TimeoutError) as exc:
        raise RoutesError("ROUTES_TIMEOUT", "Google Geocoding request timed out or could not connect") from exc


def resolve_event_location(
    event: Mapping[str, Any],
    *,
    api_key: str,
    timeout: float,
    geocode_transport: Callable[[str, str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if event.get("latitude") is not None and event.get("longitude") is not None:
        coordinates = _lat_lng(event, "event")
        return {
            **coordinates,
            "resolvedAddress": str(event.get("address") or event.get("venueName") or ""),
            "confidence": 1.0,
            "geocoded": False,
        }
    address = str(event.get("address") or event.get("venueName") or "").strip()
    if not address:
        raise RoutesError("ROUTES_LOCATION_MISSING", "Event has neither coordinates nor an address")
    value = dict(geocode_transport(api_key, address)) if geocode_transport else google_geocode_transport(api_key, address, timeout=timeout)
    status = value.get("status")
    if status == "ZERO_RESULTS":
        raise RoutesError("ROUTES_ZERO_RESULTS", "Google Geocoding found no event location")
    if status in {"OVER_DAILY_LIMIT", "OVER_QUERY_LIMIT", "RESOURCE_EXHAUSTED"}:
        raise RoutesError("ROUTES_QUOTA_EXCEEDED", "Google Geocoding quota was exceeded")
    results = value.get("results")
    if status != "OK" or not isinstance(results, list) or not results:
        raise RoutesError("ROUTES_RESPONSE_INVALID", "Google Geocoding response is unavailable")
    first = results[0]
    try:
        coordinates = _lat_lng(first["geometry"]["location"], "geocoded event")
    except (KeyError, TypeError) as exc:
        raise RoutesError("ROUTES_RESPONSE_INVALID", "Google Geocoding coordinates are missing") from exc
    return {
        **coordinates,
        "resolvedAddress": str(first.get("formatted_address") or address),
        "confidence": 0.7 if first.get("partial_match") is True else 0.9,
        "geocoded": True,
    }


def route_from_response(
    response: Mapping[str, Any],
    *,
    mode: str,
    computed_at: datetime,
    location: Mapping[str, Any],
) -> dict[str, Any]:
    routes = response.get("routes")
    if not isinstance(routes, list) or not routes:
        raise RoutesError("ROUTES_ZERO_RESULTS", f"Google Routes returned no {mode} route")
    first = routes[0]
    if not isinstance(first, dict):
        raise RoutesError("ROUTES_RESPONSE_INVALID", "Google Routes route is malformed")
    seconds = _duration_seconds(first.get("duration"))
    distance = first.get("distanceMeters")
    if not isinstance(distance, int) or distance < 0:
        raise RoutesError("ROUTES_RESPONSE_INVALID", "Google Routes distance is invalid")
    return {
        "mode": mode,
        "minutes": max(1, math.ceil(seconds / 60)),
        "source": "maps_verified",
        "computedAt": computed_at.isoformat(),
        "distanceMeters": distance,
        "confidence": float(location["confidence"]),
        "resolvedAddress": location["resolvedAddress"],
        "latitude": location["latitude"],
        "longitude": location["longitude"],
    }


def compute_event_route(
    origin: Mapping[str, Any],
    event: Mapping[str, Any],
    *,
    departure_time: datetime,
    modes: Sequence[str] = ("walk", "transit"),
    environ: Mapping[str, str] | None = None,
    route_transport: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
    geocode_transport: Callable[[str, str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if departure_time.tzinfo is None:
        raise RoutesError("ROUTES_LOCATION_INVALID", "Routes departure time must include a timezone")
    key = _api_key(environ)
    timeout = _timeout(environ)
    origin_coordinates = _lat_lng(origin, "origin")
    location = resolve_event_location(
        event,
        api_key=key,
        timeout=timeout,
        geocode_transport=geocode_transport,
    )
    results: list[dict[str, Any]] = []
    failures: list[RoutesError] = []
    for requested_mode in modes:
        mode = requested_mode.lower()
        if mode not in {"walk", "transit"}:
            raise RoutesError("ROUTES_CONFIG_INVALID", f"Unsupported route mode: {requested_mode}")
        payload: dict[str, Any] = {
            "origin": _waypoint(origin_coordinates),
            "destination": _waypoint(location),
            "travelMode": "WALK" if mode == "walk" else "TRANSIT",
            "languageCode": "ja-JP",
            "units": "METRIC",
        }
        if mode == "transit":
            payload["departureTime"] = departure_time.astimezone().isoformat()
        try:
            response = dict(route_transport(key, payload)) if route_transport else google_routes_transport(key, payload, timeout=timeout)
            results.append(route_from_response(response, mode=mode, computed_at=departure_time, location=location))
        except RoutesError as exc:
            failures.append(exc)
    if not results:
        if failures and any(failure.code == "ROUTES_QUOTA_EXCEEDED" for failure in failures):
            raise RoutesError("ROUTES_QUOTA_EXCEEDED", "All Google route modes failed because quota was exceeded")
        raise failures[0] if failures else RoutesError("ROUTES_ZERO_RESULTS", "No Google route modes were requested")
    return min(results, key=lambda result: (result["minutes"], result["distanceMeters"], result["mode"]))


def feasible_free_windows(
    event: Mapping[str, Any],
    route: Mapping[str, Any],
    free_windows: Sequence[Mapping[str, Any]],
    *,
    buffer_minutes: int = 10,
    minimum_visit_minutes: int = 30,
) -> list[dict[str, Any]]:
    if route.get("source") != "maps_verified" or not isinstance(route.get("minutes"), int):
        return []
    if not 0 <= buffer_minutes <= 120 or not 1 <= minimum_visit_minutes <= 1440:
        raise RoutesError("ROUTES_CONFIG_INVALID", "Route feasibility minutes are invalid")
    try:
        starts_at = datetime.fromisoformat(str(event["startsAt"]).replace("Z", "+00:00"))
        ends_at = datetime.fromisoformat(str(event["endsAt"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise RoutesError("ROUTES_EVENT_TIME_INVALID", "Event time is invalid") from exc
    if starts_at.tzinfo is None or ends_at.tzinfo is None or ends_at <= starts_at:
        raise RoutesError("ROUTES_EVENT_TIME_INVALID", "Event time is invalid")
    visit_minutes = max(minimum_visit_minutes, int((ends_at - starts_at).total_seconds() // 60))
    one_way = int(route["minutes"])
    required = one_way * 2 + visit_minutes + buffer_minutes
    fits: list[dict[str, Any]] = []
    for value in free_windows:
        try:
            window_start = datetime.fromisoformat(str(value["start"]).replace("Z", "+00:00"))
            window_end = datetime.fromisoformat(str(value["end"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if window_start.tzinfo is None or window_end.tzinfo is None:
            continue
        leave_at = starts_at - timedelta(minutes=one_way + buffer_minutes)
        return_at = ends_at + timedelta(minutes=one_way)
        if window_start <= leave_at and return_at <= window_end and int(value.get("durationMinutes", 0)) >= required:
            fits.append(
                {
                    **dict(value),
                    "routeMode": route["mode"],
                    "oneWayMinutes": one_way,
                    "roundTripMinutes": one_way * 2,
                    "bufferMinutes": buffer_minutes,
                    "requiredMinutes": required,
                    "leaveAt": leave_at.isoformat(),
                    "returnAt": return_at.isoformat(),
                }
            )
    return fits
