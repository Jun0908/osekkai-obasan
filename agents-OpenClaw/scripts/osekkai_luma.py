"""Lu.ma iCal adapter.

Only a calendar URL explicitly supplied by the user/organizer is fetched.  It
does not claim to enumerate every Lu.ma event and does not scrape city pages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo


MAX_ICAL_BYTES = 5 * 1024 * 1024
TOKYO = ZoneInfo("Asia/Tokyo")
USER_AGENT = "osekkai-obasan-luma-ical/1.0"


class LumaError(RuntimeError):
    pass


def _safe_calendar_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise LumaError("LUMA_ICAL_URL must be an absolute HTTPS URL without embedded credentials")
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        raise LumaError("LUMA_ICAL_URL cannot target localhost")
    return parsed.geturl()


def fetch_ical(url: str, *, timeout: float = 15.0) -> bytes:
    safe_url = _safe_calendar_url(url)
    request = urllib.request.Request(safe_url, headers={"User-Agent": USER_AGENT, "Accept": "text/calendar"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_ICAL_BYTES:
                raise LumaError("Lu.ma iCal exceeds the byte limit")
            body = response.read(MAX_ICAL_BYTES + 1)
    except OSError as exc:
        raise LumaError("Lu.ma iCal request failed") from exc
    if len(body) > MAX_ICAL_BYTES:
        raise LumaError("Lu.ma iCal exceeds the byte limit")
    return body


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _property(line: str) -> tuple[str, dict[str, str], str] | None:
    if ":" not in line:
        return None
    head, value = line.split(":", 1)
    parts = head.split(";")
    name = parts[0].upper()
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            key, param_value = part.split("=", 1)
            params[key.upper()] = param_value.strip('"')
    return name, params, _unescape(value)


def parse_ical(body: bytes | str) -> list[dict[str, Any]]:
    try:
        text = body.decode("utf-8-sig") if isinstance(body, bytes) else body
    except UnicodeDecodeError as exc:
        raise LumaError("Lu.ma iCal must be UTF-8") from exc
    events: list[dict[str, Any]] = []
    current: dict[str, list[tuple[dict[str, str], str]]] | None = None
    for line in _unfold(text):
        if line.upper() == "BEGIN:VEVENT":
            current = {}
            continue
        if line.upper() == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None:
            continue
        parsed = _property(line)
        if parsed:
            name, params, value = parsed
            current.setdefault(name, []).append((params, value))
    return events


def _first(event: Mapping[str, list[tuple[dict[str, str], str]]], name: str) -> tuple[dict[str, str], str] | None:
    values = event.get(name)
    return values[0] if values else None


def _datetime_value(prop: tuple[dict[str, str], str] | None, *, default: datetime | None = None) -> datetime:
    if prop is None:
        if default is None:
            raise LumaError("VEVENT is missing a required datetime")
        return default
    params, value = prop
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", value):
        parsed_date = datetime.strptime(value[:8], "%Y%m%d").date()
        return datetime.combine(parsed_date, time.min, TOKYO)
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(TOKYO)
    parsed = datetime.strptime(value, "%Y%m%dT%H%M%S" if len(value) >= 15 else "%Y%m%dT%H%M")
    timezone_name = params.get("TZID", "Asia/Tokyo")
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = TOKYO
    return parsed.replace(tzinfo=zone).astimezone(TOKYO)


def _nullable_int(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", value.replace(",", ""))
    return int(match.group()) if match else None


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


def _status(event: Mapping[str, list[tuple[dict[str, str], str]]], description: str) -> tuple[str, str]:
    raw_status = (_first(event, "STATUS") or ({}, "CONFIRMED"))[1].upper()
    text = description.lower()
    if raw_status == "CANCELLED" or any(word in text for word in ("開催中止", "cancelled", "canceled")):
        return "canceled", "closed"
    if any(word in text for word in ("満席", "sold out")):
        return "sold_out", "sold_out"
    if any(word in text for word in ("募集終了", "受付終了", "registration closed")):
        return "registration_closed", "closed"
    if any(word in text for word in ("waitlist", "キャンセル待ち")):
        return "scheduled", "waitlist"
    if any(word in text for word in ("申込不要", "registration not required")):
        return "scheduled", "not_required"
    return "scheduled", "open"


def normalize_ical(
    body: bytes | str,
    *,
    calendar_url: str,
    fetched_at: datetime,
    now: datetime | None = None,
) -> dict[str, Any]:
    if fetched_at.tzinfo is None:
        raise LumaError("fetched_at must be timezone-aware")
    safe_url = _safe_calendar_url(calendar_url)
    current_time = now or fetched_at
    community_id = _stable_id("community-luma", safe_url)
    normalized: dict[str, dict[str, Any]] = {}
    series_by_id: dict[str, dict[str, Any]] = {}
    for raw in parse_ical(body):
        uid_entry = _first(raw, "UID")
        title_entry = _first(raw, "SUMMARY")
        if uid_entry is None or title_entry is None or _first(raw, "DTSTART") is None:
            continue
        uid = uid_entry[1].strip()
        title = title_entry[1].strip()
        if not uid or not title:
            continue
        starts_at = _datetime_value(_first(raw, "DTSTART"))
        ends_at = _datetime_value(_first(raw, "DTEND"), default=starts_at + timedelta(hours=2))
        if ends_at <= starts_at:
            continue
        description = (_first(raw, "DESCRIPTION") or ({}, ""))[1]
        event_status, registration_status = _status(raw, description)
        if ends_at < current_time and event_status == "scheduled":
            event_status = "ended"
        source_url = (_first(raw, "URL") or ({}, safe_url))[1]
        if not source_url.startswith(("https://", "http://")):
            source_url = safe_url
        location = (_first(raw, "LOCATION") or ({}, ""))[1].strip()
        last_modified = _datetime_value(_first(raw, "LAST-MODIFIED"), default=fetched_at)
        event_id = _stable_id("event-luma", uid)
        rrule = (_first(raw, "RRULE") or ({}, ""))[1].strip()
        series_id = _stable_id("series-luma", uid) if rrule else None
        geo = (_first(raw, "GEO") or ({}, ""))[1].split(";")
        try:
            latitude, longitude = (float(geo[0]), float(geo[1])) if len(geo) == 2 else (None, None)
        except ValueError:
            latitude, longitude = None, None
        deadline_prop = _first(raw, "X-LUMA-REGISTRATION-DEADLINE")
        deadline = _datetime_value(deadline_prop).isoformat() if deadline_prop else None
        categories = [item.strip() for _params, value in raw.get("CATEGORIES", []) for item in value.split(",") if item.strip()]
        canonical = "\n".join(f"{name}:{values}" for name, values in sorted(raw.items()))
        event = {
            "schemaVersion": "1.0",
            "id": event_id,
            "provider": "luma_tokyo",
            "sourceRecordId": uid[:200],
            "title": title[:240],
            "description": description[:10000],
            "startsAt": starts_at.isoformat(),
            "endsAt": ends_at.isoformat(),
            "timezone": "Asia/Tokyo",
            "venueName": location[:240] or None,
            "address": location[:400] or None,
            "latitude": latitude,
            "longitude": longitude,
            "communityId": community_id,
            "seriesId": series_id,
            "status": event_status,
            "registrationStatus": registration_status,
            "registrationDeadline": deadline,
            "capacity": _nullable_int((_first(raw, "X-LUMA-CAPACITY") or ({}, None))[1]),
            "participants": _nullable_int((_first(raw, "X-LUMA-PARTICIPANTS") or ({}, None))[1]),
            "priceYen": _nullable_int((_first(raw, "X-LUMA-PRICE-YEN") or ({}, None))[1]),
            "categories": list(dict.fromkeys(categories)),
            "sourceUrl": source_url,
            "sourceDataset": "Lu.ma iCal (user/organizer supplied calendar)",
            "license": "Lu.ma terms and organizer-owned event metadata",
            "sourceClassification": "live_provider",
            "sourceUpdatedAt": last_modified.isoformat(),
            "fetchedAt": fetched_at.isoformat(),
            "revalidatedAt": fetched_at.isoformat(),
            "checksum": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "fieldProvenance": {
                "title": {"classification": "source_verified", "sourceUrl": source_url, "capturedAt": fetched_at.isoformat()},
                "startsAt": {"classification": "source_verified", "sourceUrl": source_url, "capturedAt": fetched_at.isoformat()},
                "status": {"classification": "source_verified", "sourceUrl": source_url, "capturedAt": fetched_at.isoformat()},
            },
        }
        # Highest SEQUENCE wins if an iCal feed repeats the UID during an update.
        sequence = _nullable_int((_first(raw, "SEQUENCE") or ({}, "0"))[1]) or 0
        previous = normalized.get(event_id)
        if previous is None or sequence >= previous["_sequence"]:
            normalized[event_id] = {**event, "_sequence": sequence}
        if series_id:
            evidence = {
                "kind": "recurrence",
                "text": f"公開iCalのRRULE: {rrule}"[:500],
                "url": source_url,
                "classification": "live_provider",
                "capturedAt": fetched_at.isoformat(),
                "confidence": 1,
                "evidenceField": "RRULE",
            }
            series_by_id[series_id] = {
                "schemaVersion": "1.0",
                "id": series_id,
                "provider": "luma_tokyo",
                "communityId": community_id,
                "title": title[:240],
                "recurrenceText": rrule[:500],
                "futureOccurrenceIds": [],
                "sourceUrl": source_url,
                "sourceClassification": "live_provider",
                "sourceUpdatedAt": last_modified.isoformat(),
                "fetchedAt": fetched_at.isoformat(),
                "revalidatedAt": fetched_at.isoformat(),
                "evidence": [evidence],
            }
    events = []
    for value in normalized.values():
        value.pop("_sequence", None)
        events.append(value)
    future_ids = [event["id"] for event in events if event["status"] == "scheduled" and datetime.fromisoformat(event["startsAt"]) >= current_time]
    for series in series_by_id.values():
        series["futureOccurrenceIds"] = [event["id"] for event in events if event["seriesId"] == series["id"] and event["id"] in future_ids]
    community = {
        "schemaVersion": "1.0",
        "id": community_id,
        "provider": "luma_tokyo",
        "name": "Lu.ma curated calendar",
        "description": "利用者または主催者が許可したLu.ma iCal calendar。",
        "organizerName": None,
        "eventSeriesIds": sorted(series_by_id),
        "futureEventIds": future_ids,
        "communityUrl": safe_url,
        "sourceClassification": "live_provider",
        "sourceUpdatedAt": fetched_at.isoformat(),
        "fetchedAt": fetched_at.isoformat(),
        "revalidatedAt": fetched_at.isoformat(),
        "evidence": [
            {
                "kind": "community_path",
                "text": "許可された同一Calendarから継続してEventを取得します。",
                "url": safe_url,
                "classification": "live_provider",
                "capturedAt": fetched_at.isoformat(),
                "confidence": 1,
                "evidenceField": "VCALENDAR",
            }
        ],
    }
    return {
        "schemaVersion": "1.0",
        "provider": "luma_tokyo",
        "scope": "configured_calendar_only",
        "fetchedAt": fetched_at.isoformat(),
        "events": sorted(events, key=lambda item: (item["startsAt"], item["id"])),
        "series": list(series_by_id.values()),
        "communities": [community],
    }


def sync_configured_calendar(
    *,
    environ: Mapping[str, str] | None = None,
    fetched_at: datetime | None = None,
    fetcher: Callable[[str], bytes] = fetch_ical,
) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    url = str(env.get("LUMA_ICAL_URL", "")).strip()
    if not url:
        raise LumaError("LUMA_ICAL_URL is not configured")
    captured = fetched_at or datetime.now().astimezone()
    return normalize_ical(fetcher(_safe_calendar_url(url)), calendar_url=url, fetched_at=captured)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync an authorized Lu.ma iCal")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.smoke:
        parser.error("--smoke is required")
    try:
        result = sync_configured_calendar()
    except LumaError as exc:
        payload = {"ok": False, "provider": "luma_tokyo", "state": "blocked", "message": str(exc)}
        print(json.dumps(payload, ensure_ascii=False) if args.json else payload["message"])
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False) if args.json else f"Lu.ma: {len(result['events'])} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
