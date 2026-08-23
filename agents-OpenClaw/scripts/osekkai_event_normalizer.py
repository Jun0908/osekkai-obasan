"""Cross-provider Event merge, deduplication, and recommendation freshness gate."""

from __future__ import annotations

import copy
import re
import unicodedata
import urllib.parse
from datetime import datetime
from typing import Any, Iterable, Mapping

from osekkai_contracts import ContractError, validate_schema
from osekkai_source_registry import is_stale, source_by_id


TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
RESTRICTIVE_STATUS = {
    "unknown": 0,
    "scheduled": 1,
    "ended": 2,
    "registration_closed": 3,
    "sold_out": 4,
    "canceled": 5,
}
DERIVED_CATEGORY_MARKERS = {
    "ダンス・健康": (
        "ヨガ", "ピラティス", "ダンス", "ランニング", "ラン", "フィットネス",
        "yoga", "pilates", "dance", "running", "runclub", "workout", "pickleball",
    ),
    "趣味・実用": (
        "ボルダリング", "クライミング", "料理", "工作", "手芸", "写真", "陶芸", "本交換",
        "bouldering", "climbing", "cooking", "craft", "photography", "pottery", "bookswap",
    ),
    "音楽・演劇": ("音楽", "演劇", "ライブ", "合唱", "music", "theater", "theatre", "choir"),
    "文学・歴史": ("読書", "文学", "歴史", "bookclub", "reading", "history"),
    "国際理解・語学": ("英会話", "語学", "国際交流", "languageexchange", "internationalexchange"),
    "区民参加・ボランティア": ("ボランティア", "地域活動", "清掃", "volunteer", "communitycleanup"),
}


def canonical_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ContractError("event sourceUrl must be absolute HTTP(S)")
    host = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = host if port is None or (parsed.scheme == "https" and port == 443) or (parsed.scheme == "http" and port == 80) else f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = [
        (key, val)
        for key, val in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
    ]
    return urllib.parse.urlunsplit((parsed.scheme.lower(), netloc, path, urllib.parse.urlencode(sorted(query)), ""))


def _plain(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"[\s\-‐‑–—―・:：#＃第回]+", "", text)


def _derive_categories(event: Mapping[str, Any], *, captured_at: datetime) -> dict[str, Any]:
    enriched = copy.deepcopy(dict(event))
    searchable = _plain(f"{event.get('title', '')} {event.get('description', '')}")
    derived = [
        category
        for category, markers in DERIVED_CATEGORY_MARKERS.items()
        if any(_plain(marker) in searchable for marker in markers)
    ]
    if not derived:
        return enriched
    enriched["categories"] = list(dict.fromkeys([*event.get("categories", []), *derived]))
    enriched["fieldProvenance"] = {
        **event.get("fieldProvenance", {}),
        "categories": {
            "classification": "ai_derived",
            "sourceUrl": event["sourceUrl"],
            "capturedAt": captured_at.isoformat(),
            "confidence": 0.78,
            "evidenceField": "title,description",
            "evidence": f"公開タイトル・説明のキーワードから派生: {', '.join(derived)}",
        },
    }
    validate_schema(enriched, "event.schema.json")
    return enriched


def _match_keys(event: Mapping[str, Any]) -> set[str]:
    try:
        starts = datetime.fromisoformat(str(event.get("startsAt")).replace("Z", "+00:00")).replace(second=0, microsecond=0)
        occurrence = starts.isoformat()
    except ValueError:
        occurrence = "invalid-time"
    # A public course/series commonly reuses one record ID and URL for every
    # occurrence. Start time is therefore part of identity; otherwise a
    # 12-session class collapses into one marker and violates the all-Event map.
    keys = {f"provider:{event.get('provider')}:{event.get('sourceRecordId')}:{occurrence}"}
    try:
        keys.add(f"url:{canonical_url(str(event.get('sourceUrl')))}:{occurrence}")
    except ContractError:
        pass
    try:
        place = _plain(event.get("venueName") or event.get("address"))
        if place:
            keys.add(f"fact:{_plain(event.get('title'))}:{starts.isoformat()}:{place}")
    except ValueError:
        pass
    return keys


def _source_link(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "provider": event["provider"],
        "sourceRecordId": event["sourceRecordId"],
        "sourceUrl": event["sourceUrl"],
        "fetchedAt": event["fetchedAt"],
        "classification": event["sourceClassification"],
    }


def _merge(primary: dict[str, Any], duplicate: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(primary)
    duplicate_links = duplicate.get("sourceLinks") if isinstance(duplicate.get("sourceLinks"), list) else [_source_link(duplicate)]
    primary_links = merged.get("sourceLinks") if isinstance(merged.get("sourceLinks"), list) else [_source_link(merged)]
    unique_links: dict[tuple[str, str, str], dict[str, Any]] = {}
    for link in [*primary_links, *duplicate_links]:
        unique_links[(link["provider"], link["sourceRecordId"], canonical_url(link["sourceUrl"]))] = copy.deepcopy(link)
    merged["sourceLinks"] = list(unique_links.values())
    merged["duplicateEventIds"] = list(
        dict.fromkeys([*merged.get("duplicateEventIds", []), duplicate["id"], *duplicate.get("duplicateEventIds", [])])
    )
    if RESTRICTIVE_STATUS.get(str(duplicate.get("status")), 0) > RESTRICTIVE_STATUS.get(str(merged.get("status")), 0):
        merged["status"] = duplicate["status"]
        merged["registrationStatus"] = duplicate["registrationStatus"]
    if str(duplicate.get("revalidatedAt", "")) > str(merged.get("revalidatedAt", "")):
        for field in ("sourceUpdatedAt", "fetchedAt", "revalidatedAt", "capacity", "participants", "registrationDeadline"):
            if duplicate.get(field) is not None:
                merged[field] = duplicate[field]
    for field in ("description", "address", "venueName", "latitude", "longitude", "capacity", "participants", "audience", "priceYen"):
        if merged.get(field) in {None, ""} and duplicate.get(field) not in {None, ""}:
            merged[field] = duplicate[field]
    merged["categories"] = list(dict.fromkeys([*merged.get("categories", []), *duplicate.get("categories", [])]))
    merged["fieldProvenance"] = {**duplicate.get("fieldProvenance", {}), **merged.get("fieldProvenance", {})}
    return merged


def deduplicate_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    keys_by_index: list[set[str]] = []
    for raw in events:
        event = copy.deepcopy(dict(raw))
        validate_schema(event, "event.schema.json")
        keys = _match_keys(event)
        matching = next((index for index, existing in enumerate(keys_by_index) if existing & keys), None)
        if matching is None:
            event.setdefault("sourceLinks", [_source_link(event)])
            event.setdefault("duplicateEventIds", [])
            groups.append(event)
            keys_by_index.append(keys)
        else:
            groups[matching] = _merge(groups[matching], event)
            keys_by_index[matching] |= keys
    for event in groups:
        validate_schema(event, "event.schema.json")
    return groups


def gate_event(event: Mapping[str, Any], *, now: datetime) -> list[str]:
    reasons: list[str] = []
    try:
        source = source_by_id(str(event.get("provider")))
        if not source["enabled"] or not source["authorized"]:
            reasons.append("SOURCE_NOT_AUTHORIZED")
        if is_stale(source, str(event.get("fetchedAt")), now):
            reasons.append("STALE")
    except (ContractError, KeyError):
        reasons.append("INVALID_SOURCE")
    try:
        starts_at = datetime.fromisoformat(str(event.get("startsAt")).replace("Z", "+00:00"))
        ends_at = datetime.fromisoformat(str(event.get("endsAt")).replace("Z", "+00:00"))
        if ends_at <= now or starts_at < now:
            reasons.append("ENDED_OR_STARTED")
    except ValueError:
        reasons.append("INVALID_TIME")
    status = event.get("status")
    if status in {"ended", "canceled", "sold_out", "registration_closed", "unknown"}:
        reasons.append(str(status).upper())
    registration = event.get("registrationStatus")
    if registration in {"sold_out", "closed", "unknown"}:
        reasons.append(f"REGISTRATION_{str(registration).upper()}")
    deadline = event.get("registrationDeadline")
    if isinstance(deadline, str):
        try:
            if datetime.fromisoformat(deadline.replace("Z", "+00:00")) <= now:
                reasons.append("DEADLINE_PASSED")
        except ValueError:
            reasons.append("INVALID_DEADLINE")
    if not event.get("sourceUrl") or not event.get("revalidatedAt"):
        reasons.append("MISSING_PROVENANCE")
    if not (event.get("address") or event.get("venueName") or (event.get("latitude") is not None and event.get("longitude") is not None)):
        reasons.append("LOCATION_MISSING")
    return list(dict.fromkeys(reasons))


def normalize_event_mesh(provider_results: Iterable[Mapping[str, Any]], *, now: datetime) -> dict[str, Any]:
    if now.tzinfo is None:
        raise ContractError("now must be timezone-aware")
    raw_events: list[Mapping[str, Any]] = []
    series_by_id: dict[str, dict[str, Any]] = {}
    communities_by_id: dict[str, dict[str, Any]] = {}
    provider_errors: list[dict[str, Any]] = []
    for result in provider_results:
        provider = str(result.get("provider") or "unknown")
        if isinstance(result.get("errors"), list):
            provider_errors.extend({"provider": provider, **dict(error)} for error in result["errors"] if isinstance(error, dict))
        raw_events.extend(event for event in result.get("events", []) if isinstance(event, Mapping))
        for series in result.get("series", []):
            if isinstance(series, dict):
                series_by_id[series["id"]] = copy.deepcopy(series)
        for community in result.get("communities", []):
            if isinstance(community, dict):
                communities_by_id[community["id"]] = copy.deepcopy(community)
    invalid: list[dict[str, Any]] = []
    valid: list[Mapping[str, Any]] = []
    for event in raw_events:
        try:
            validate_schema(event, "event.schema.json")
            valid.append(event)
        except ContractError as exc:
            invalid.append({"eventId": event.get("id"), "provider": event.get("provider"), "reasons": ["CONTRACT_INVALID"], "detail": str(exc)})
    merged = [_derive_categories(event, captured_at=now) for event in deduplicate_events(valid)]
    excluded: list[dict[str, Any]] = list(invalid)
    eligible: list[dict[str, Any]] = []
    for event in merged:
        reasons = gate_event(event, now=now)
        if reasons:
            excluded.append({"eventId": event["id"], "provider": event["provider"], "reasons": reasons})
        else:
            eligible.append(event)
    return {
        "schemaVersion": "1.0",
        "dataMode": "live",
        "generatedAt": now.isoformat(),
        "events": merged,
        "eligibleEvents": eligible,
        "excludedEvents": excluded,
        "series": list(series_by_id.values()),
        "communities": list(communities_by_id.values()),
        "providerErrors": provider_errors,
        "counts": {"received": len(raw_events), "merged": len(merged), "eligible": len(eligible), "excluded": len(excluded)},
    }
