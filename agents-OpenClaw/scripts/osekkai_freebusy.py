"""Privacy-minimal Free/Busy provider for the deterministic P0 demo."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

from osekkai_contracts import ContractError, validate_freebusy
from osekkai_google_credentials import (
    GoogleCredentialError,
    GoogleCredentialStore,
    GoogleOAuthConfig,
    access_token,
)


class ProviderError(RuntimeError):
    def __init__(self, message: str, code: str = "PROVIDER_UNAVAILABLE"):
        super().__init__(message)
        self.code = code


def fixture_root() -> Path:
    configured = os.environ.get("OSEKKAI_FIXTURE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / "fixtures" / "osekkai"


def load_freebusy(
    data_mode: str = "demo",
    *,
    user_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if data_mode == "live":
        if not user_id:
            raise ProviderError("live FreeBusy requires an authenticated anonymous session")
        captured = now or datetime.now().astimezone()
        horizon_days = _horizon_days()
        try:
            return query_google_freebusy(
                user_id,
                time_min=captured,
                time_max=captured + timedelta(days=horizon_days),
                generated_at=captured,
            )
        except GoogleCredentialError as exc:
            raise ProviderError(
                "Google Calendar FreeBusy is not connected",
                "CALENDAR_NOT_CONNECTED",
            ) from exc
    if data_mode != "demo":
        raise ProviderError("unsupported FreeBusy data mode")
    path = fixture_root() / "freebusy.json"
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderError("demo FreeBusy fixture could not be loaded") from exc
    try:
        validate_freebusy(value)
    except ContractError as exc:
        raise ProviderError("demo FreeBusy fixture is invalid") from exc
    forbidden = {"title", "summary", "description", "attendees", "location"}
    if forbidden & set(_walk_keys(value)):
        raise ProviderError("demo FreeBusy fixture contains prohibited calendar details")
    return copy.deepcopy(value)


def _horizon_days() -> int:
    raw = os.environ.get("OSEKKAI_FREEBUSY_HORIZON_DAYS", "30").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ProviderError("OSEKKAI_FREEBUSY_HORIZON_DAYS must be an integer") from exc
    if not 1 <= value <= 90:
        raise ProviderError("OSEKKAI_FREEBUSY_HORIZON_DAYS must be between 1 and 90")
    return value


def _google_transport(access_token_value: str, payload: Mapping[str, Any], *, timeout: float = 15.0) -> dict[str, Any]:
    request = urllib.request.Request(
        "https://www.googleapis.com/calendar/v3/freeBusy",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token_value}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read(1024 * 1024).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError("Google Calendar FreeBusy request failed") from exc
    if not isinstance(value, dict):
        raise ProviderError("Google Calendar FreeBusy response is malformed")
    return value


def _parse_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ProviderError(f"Google FreeBusy {field} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProviderError(f"Google FreeBusy {field} is invalid") from exc
    if parsed.tzinfo is None:
        raise ProviderError(f"Google FreeBusy {field} has no timezone")
    return parsed


def free_windows_from_response(
    response: Mapping[str, Any],
    *,
    time_min: datetime,
    time_max: datetime,
    generated_at: datetime,
    minimum_minutes: int = 30,
) -> dict[str, Any]:
    forbidden = {"title", "summary", "description", "attendees", "location"}
    if forbidden & set(_walk_keys(response)):
        raise ProviderError("Google FreeBusy response contains prohibited event details")
    calendars = response.get("calendars")
    primary = calendars.get("primary") if isinstance(calendars, dict) else None
    if not isinstance(primary, dict) or primary.get("errors"):
        raise ProviderError("Google FreeBusy primary calendar is unavailable")
    busy_values = primary.get("busy")
    if not isinstance(busy_values, list):
        raise ProviderError("Google FreeBusy busy list is missing")
    busy: list[tuple[datetime, datetime]] = []
    for item in busy_values:
        if not isinstance(item, dict) or set(item) != {"start", "end"}:
            raise ProviderError("Google FreeBusy interval is malformed")
        start = max(time_min, _parse_datetime(item["start"], "start"))
        end = min(time_max, _parse_datetime(item["end"], "end"))
        if end > start:
            busy.append((start, end))
    busy.sort(key=lambda value: value[0])
    merged: list[tuple[datetime, datetime]] = []
    for start, end in busy:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    windows: list[dict[str, Any]] = []
    cursor = time_min
    for start, end in [*merged, (time_max, time_max)]:
        duration = int((start - cursor).total_seconds() // 60)
        if duration >= minimum_minutes:
            window_id = hashlib.sha256(f"{cursor.isoformat()}|{start.isoformat()}".encode()).hexdigest()[:20]
            windows.append(
                {
                    "id": f"google-free-{window_id}",
                    "start": cursor.isoformat(),
                    "end": start.isoformat(),
                    "durationMinutes": duration,
                    "verificationStatus": "source_verified",
                }
            )
        cursor = max(cursor, end)
    result = {
        "schemaVersion": "1.0",
        "dataMode": "live",
        "generatedAt": generated_at.isoformat(),
        "source": {
            "type": "google_freebusy",
            "notice": "Google Calendar FreeBusyのbusy区間だけを取得し、予定名・説明・場所・参加者は取得していません。",
        },
        "freeWindows": windows,
    }
    validate_freebusy(result)
    return result


def query_google_freebusy(
    user_id: str,
    *,
    time_min: datetime,
    time_max: datetime,
    generated_at: datetime,
    config: GoogleOAuthConfig | None = None,
    credential_store: GoogleCredentialStore | None = None,
    credential_environ: Mapping[str, str] | None = None,
    token_transport: Callable[[str, Mapping[str, str]], Mapping[str, Any]] | None = None,
    api_transport: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if any(value.tzinfo is None for value in (time_min, time_max, generated_at)) or time_max <= time_min:
        raise ProviderError("FreeBusy query interval is invalid")
    oauth_config = config or GoogleOAuthConfig.from_env(credential_environ)
    store = credential_store or GoogleCredentialStore(environ=credential_environ)
    token = access_token(
        user_id,
        now=generated_at,
        config=oauth_config,
        store=store,
        token_transport=token_transport,
    )
    payload = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "timeZone": "Asia/Tokyo",
        "items": [{"id": "primary"}],
    }
    response = dict(api_transport(token, payload)) if api_transport else _google_transport(token, payload)
    return free_windows_from_response(
        response,
        time_min=time_min,
        time_max=time_max,
        generated_at=generated_at,
    )


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(key)
            keys.extend(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_walk_keys(child))
    return keys
