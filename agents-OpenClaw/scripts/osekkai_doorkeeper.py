"""Official Doorkeeper API adapter with pagination and bounded 429 retry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping


API_BASE = "https://api.doorkeeper.jp/"
USER_AGENT = "osekkai-obasan-doorkeeper/1.0"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class DoorkeeperError(RuntimeError):
    pass


class DoorkeeperRateLimitError(DoorkeeperError):
    pass


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


def _iso(value: Any, fallback: datetime) -> str:
    if not isinstance(value, str) or not value.strip():
        return fallback.isoformat()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise DoorkeeperError("Doorkeeper datetime must include a timezone")
    return parsed.isoformat()


def _default_transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise DoorkeeperError("Doorkeeper response exceeds the byte limit")
            return response.status, {key.lower(): value for key, value in response.headers.items()}, body
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_RESPONSE_BYTES)
        return exc.code, {key.lower(): value for key, value in exc.headers.items()}, body
    except OSError as exc:
        raise DoorkeeperError("Doorkeeper request failed") from exc


class DoorkeeperClient:
    def __init__(
        self,
        token: str,
        *,
        transport: Callable[[str, Mapping[str, str], float], tuple[int, dict[str, str], bytes]] = _default_transport,
        sleeper: Callable[[float], None] = time.sleep,
        timeout: float = 15.0,
        max_attempts: int = 3,
    ):
        if not token.strip():
            raise DoorkeeperError("DOORKEEPER_API_TOKEN is not configured")
        self._token = token.strip()
        self._transport = transport
        self._sleeper = sleeper
        self._timeout = timeout
        self._max_attempts = max(1, max_attempts)

    def _page(self, params: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
        url = f"{API_BASE}events?{urllib.parse.urlencode(params)}"
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json", "User-Agent": USER_AGENT}
        for attempt in range(self._max_attempts):
            status, response_headers, body = self._transport(url, headers, self._timeout)
            if status == 429:
                if attempt + 1 == self._max_attempts:
                    raise DoorkeeperRateLimitError("Doorkeeper rate limit retry budget exhausted")
                retry_after = response_headers.get("retry-after")
                delay = min(8.0, float(retry_after)) if retry_after and retry_after.isdigit() else min(8.0, 2**attempt)
                self._sleeper(delay)
                continue
            if status != 200:
                raise DoorkeeperError(f"Doorkeeper returned HTTP {status}")
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise DoorkeeperError("Doorkeeper returned malformed JSON") from exc
            if not isinstance(payload, list):
                raise DoorkeeperError("Doorkeeper events response must be an array")
            return [item for item in payload if isinstance(item, dict)], response_headers
        raise DoorkeeperRateLimitError("Doorkeeper retry loop ended unexpectedly")

    def events(self, *, since: str, until: str, per_page: int = 100) -> list[dict[str, Any]]:
        page = 1
        events: list[dict[str, Any]] = []
        while page <= 50:
            rows, headers = self._page(
                {
                    "prefecture": "tokyo",
                    "since": since,
                    "until": until,
                    "sort": "updated_at",
                    "page": page,
                    "per_page": max(1, min(per_page, 100)),
                }
            )
            events.extend(rows)
            next_page = headers.get("x-next-page", "").strip()
            has_link_next = bool(re.search(r'rel="?next"?', headers.get("link", ""), re.IGNORECASE))
            if next_page:
                page = int(next_page)
            elif has_link_next or len(rows) >= per_page:
                page += 1
            else:
                break
        else:
            raise DoorkeeperError("Doorkeeper pagination exceeded the page limit")
        return events


def _unwrap(value: Mapping[str, Any]) -> dict[str, Any]:
    nested = value.get("event")
    return dict(nested) if isinstance(nested, dict) else dict(value)


def normalize_events(raw_events: list[dict[str, Any]], *, fetched_at: datetime, now: datetime | None = None) -> dict[str, Any]:
    if fetched_at.tzinfo is None:
        raise DoorkeeperError("fetched_at must be timezone-aware")
    current_time = now or fetched_at
    events: list[dict[str, Any]] = []
    groups: dict[str, dict[str, Any]] = {}
    series_buckets: dict[tuple[str, str], list[str]] = {}
    for wrapper in raw_events:
        raw = _unwrap(wrapper)
        if raw.get("id") is None or not raw.get("title") or not raw.get("starts_at"):
            continue
        starts_at = datetime.fromisoformat(_iso(raw.get("starts_at"), fetched_at))
        ends_at = datetime.fromisoformat(_iso(raw.get("ends_at"), starts_at + timedelta(hours=2)))
        if ends_at <= starts_at:
            continue
        source_id = str(raw["id"])
        public_url = str(raw.get("public_url") or f"https://www.doorkeeper.jp/events/{source_id}")
        group = raw.get("group") if isinstance(raw.get("group"), dict) else {}
        group_source_id = str(group.get("id") or f"ungrouped-{source_id}")
        community_id = _stable_id("community-doorkeeper", group_source_id)
        title_key = re.sub(r"[\s#＃第\d０-９回]+", "", str(raw["title"]).lower()) or source_id
        bucket_key = (community_id, title_key)
        event_id = _stable_id("event-doorkeeper", source_id)
        series_buckets.setdefault(bucket_key, []).append(event_id)
        capacity = raw.get("ticket_limit") if isinstance(raw.get("ticket_limit"), int) else None
        participants = raw.get("participants") if isinstance(raw.get("participants"), int) else None
        waitlisted = raw.get("waitlisted") if isinstance(raw.get("waitlisted"), int) else 0
        canceled = bool(raw.get("cancelled") or str(raw.get("status", "")).lower() in {"cancelled", "canceled"})
        if canceled:
            event_status, registration_status = "canceled", "closed"
        elif ends_at < current_time:
            event_status, registration_status = "ended", "closed"
        elif capacity is not None and participants is not None and participants >= capacity:
            event_status = "sold_out"
            registration_status = "waitlist" if waitlisted >= 0 and raw.get("waitlist") is not False else "sold_out"
        else:
            event_status, registration_status = "scheduled", "open"
        updated_at = _iso(raw.get("updated_at"), fetched_at)
        canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        categories = [str(value)[:80] for value in raw.get("topics", []) if isinstance(value, str)]
        event = {
            "schemaVersion": "1.0",
            "id": event_id,
            "provider": "doorkeeper",
            "sourceRecordId": source_id[:200],
            "title": str(raw["title"])[:240],
            "description": str(raw.get("description") or "")[:10000],
            "startsAt": starts_at.isoformat(),
            "endsAt": ends_at.isoformat(),
            "timezone": "Asia/Tokyo",
            "venueName": str(raw.get("venue_name") or "")[:240] or None,
            "address": str(raw.get("address") or "")[:400] or None,
            "latitude": float(raw["lat"]) if raw.get("lat") is not None else None,
            "longitude": float(raw["long"]) if raw.get("long") is not None else None,
            "communityId": community_id,
            "seriesId": None,
            "status": event_status,
            "registrationStatus": registration_status,
            "registrationDeadline": _iso(raw["registration_closes_at"], fetched_at) if raw.get("registration_closes_at") else None,
            "capacity": capacity,
            "participants": participants,
            "priceYen": raw.get("price") if isinstance(raw.get("price"), int) else None,
            "categories": list(dict.fromkeys(categories)),
            "sourceUrl": public_url,
            "sourceDataset": "Doorkeeper Public API",
            "license": "Doorkeeper API and service terms",
            "sourceClassification": "live_provider",
            "sourceUpdatedAt": updated_at,
            "fetchedAt": fetched_at.isoformat(),
            "revalidatedAt": fetched_at.isoformat(),
            "checksum": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "fieldProvenance": {
                "title": {"classification": "source_verified", "sourceUrl": public_url, "capturedAt": fetched_at.isoformat()},
                "capacity": {"classification": "source_verified", "sourceUrl": public_url, "capturedAt": fetched_at.isoformat()},
                "participants": {"classification": "source_verified", "sourceUrl": public_url, "capturedAt": fetched_at.isoformat()},
                "status": {"classification": "source_verified", "sourceUrl": public_url, "capturedAt": fetched_at.isoformat()},
            },
        }
        events.append(event)
        group_url = str(group.get("public_url") or public_url)
        groups.setdefault(
            community_id,
            {
                "schemaVersion": "1.0",
                "id": community_id,
                "provider": "doorkeeper",
                "name": str(group.get("name") or raw["title"])[:240],
                "description": str(group.get("description") or "")[:5000],
                "organizerName": str(group.get("name") or "")[:240] or None,
                "eventSeriesIds": [],
                "futureEventIds": [],
                "communityUrl": group_url,
                "sourceClassification": "live_provider",
                "sourceUpdatedAt": updated_at,
                "fetchedAt": fetched_at.isoformat(),
                "revalidatedAt": fetched_at.isoformat(),
                "evidence": [
                    {
                        "kind": "community_path",
                        "text": "Doorkeeper Groupの公開Event履歴と将来回を同一Communityとして扱います。",
                        "url": group_url,
                        "classification": "live_provider",
                        "capturedAt": fetched_at.isoformat(),
                        "confidence": 1,
                        "evidenceField": "group.id",
                    }
                ],
            },
        )
    event_by_id = {event["id"]: event for event in events}
    series: list[dict[str, Any]] = []
    for (community_id, title_key), event_ids in series_buckets.items():
        future_ids = [
            event_id
            for event_id in event_ids
            if event_by_id[event_id]["status"] not in {"ended", "canceled"}
        ]
        if len(future_ids) < 2:
            continue
        series_id = _stable_id("series-doorkeeper", f"{community_id}:{title_key}")
        for event_id in event_ids:
            event_by_id[event_id]["seriesId"] = series_id
        source_url = event_by_id[future_ids[0]]["sourceUrl"]
        series.append(
            {
                "schemaVersion": "1.0",
                "id": series_id,
                "provider": "doorkeeper",
                "communityId": community_id,
                "title": event_by_id[future_ids[0]]["title"],
                "recurrenceText": f"同じDoorkeeper Groupと題名で将来回が{len(future_ids)}件あります。",
                "futureOccurrenceIds": future_ids,
                "sourceUrl": source_url,
                "sourceClassification": "live_provider",
                "sourceUpdatedAt": max(event_by_id[event_id]["sourceUpdatedAt"] for event_id in future_ids),
                "fetchedAt": fetched_at.isoformat(),
                "revalidatedAt": fetched_at.isoformat(),
                "evidence": [
                    {
                        "kind": "future_occurrence",
                        "text": f"公式APIに将来回が{len(future_ids)}件あります。",
                        "url": source_url,
                        "classification": "live_provider",
                        "capturedAt": fetched_at.isoformat(),
                        "confidence": 1,
                        "evidenceField": "group.id + title",
                    }
                ],
            }
        )
        groups[community_id]["eventSeriesIds"].append(series_id)
    for community_id, community in groups.items():
        community["futureEventIds"] = [
            event["id"]
            for event in events
            if event["communityId"] == community_id and event["status"] not in {"ended", "canceled"}
        ]
    return {
        "schemaVersion": "1.0",
        "provider": "doorkeeper",
        "fetchedAt": fetched_at.isoformat(),
        "events": sorted(events, key=lambda event: (event["startsAt"], event["id"])),
        "series": series,
        "communities": list(groups.values()),
    }


def sync_doorkeeper(
    *,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
    client_factory: Callable[[str], DoorkeeperClient] = DoorkeeperClient,
) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    token = str(env.get("DOORKEEPER_API_TOKEN", "")).strip()
    if not token:
        raise DoorkeeperError("DOORKEEPER_API_TOKEN is not configured")
    captured = now or datetime.now().astimezone()
    until = captured + timedelta(days=120)
    raw = client_factory(token).events(since=captured.date().isoformat(), until=until.date().isoformat())
    return normalize_events(raw, fetched_at=captured, now=captured)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Tokyo events from the official Doorkeeper API")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.smoke:
        parser.error("--smoke is required")
    try:
        result = sync_doorkeeper()
    except DoorkeeperError as exc:
        payload = {"ok": False, "provider": "doorkeeper", "state": "blocked", "message": str(exc)}
        print(json.dumps(payload, ensure_ascii=False) if args.json else payload["message"])
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False) if args.json else f"Doorkeeper: {len(result['events'])} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
