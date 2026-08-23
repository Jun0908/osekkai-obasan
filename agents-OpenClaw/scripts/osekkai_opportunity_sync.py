"""Load and verify the immutable P0 Open Data source snapshot."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from osekkai_contracts import ContractError, validate_opportunity
from osekkai_freebusy import ProviderError
from osekkai_store import JsonStore


def fixture_root() -> Path:
    configured = os.environ.get("OSEKKAI_FIXTURE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / "fixtures" / "osekkai"


def _read_json(name: str) -> dict[str, Any]:
    try:
        with (fixture_root() / name).open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderError(f"{name} could not be loaded") from exc
    if not isinstance(value, dict):
        raise ProviderError(f"{name} must contain an object")
    return value


def _source_record(raw: dict[str, Any]) -> list[str]:
    row = raw.get("rawCsvRow")
    if not isinstance(row, str) or not row:
        raise ProviderError("raw snapshot does not contain its immutable CSV row")
    digest = hashlib.sha256(row.encode("utf-8")).hexdigest()
    if digest != raw.get("checksum"):
        raise ProviderError("raw snapshot checksum does not match")
    try:
        parsed = next(csv.reader(io.StringIO(row)))
    except (csv.Error, StopIteration) as exc:
        raise ProviderError("raw snapshot CSV row is invalid") from exc
    if len(parsed) < 80:
        raise ProviderError("raw snapshot CSV row is incomplete")
    return parsed


def _source_datetime(date_value: str, time_value: str) -> str:
    return datetime.fromisoformat(f"{date_value}T{time_value}+09:00").isoformat()


def _verify_normalized(opportunity: dict[str, Any], raw: dict[str, Any], row: list[str]) -> None:
    try:
        validate_opportunity(opportunity)
    except ContractError as exc:
        raise ProviderError("normalized opportunity violates its contract") from exc
    direct_expected = {
        "sourceRecordId": row[2],
        "title": row[4],
        "description": row[25],
        "startsAt": _source_datetime(row[16], row[18]),
        "endsAt": _source_datetime(row[17], row[19]),
        "address": row[42],
        "provider": row[3],
        "sourceUrl": raw["sourceUrl"],
        "sourceDataset": raw["dataset"],
        "license": raw["license"],
        "capturedAt": raw["capturedAt"],
        "checksum": raw["checksum"],
    }
    for field, expected in direct_expected.items():
        if opportunity.get(field) != expected:
            raise ProviderError(f"normalized {field} differs from the raw snapshot")
        provenance = opportunity.get("fieldProvenance", {}).get(field)
        if field in {"title", "startsAt", "endsAt", "address"}:
            if not isinstance(provenance, dict) or provenance.get("classification") != "source_snapshot":
                raise ProviderError(f"normalized {field} lacks source provenance")
    if float(opportunity.get("latitude")) != float(row[48]) or float(opportunity.get("longitude")) != float(row[49]):
        raise ProviderError("normalized coordinates differ from the raw snapshot")
    raw_price = int(row[28]) if row[28] else None
    if opportunity.get("priceYen") != raw_price:
        raise ProviderError("normalized price differs from the raw snapshot")
    provenance = opportunity.get("fieldProvenance", {})
    for derived in ("socialIntensity", "conversationRequired", "soloFriendly", "flexibleVisit"):
        info = provenance.get(derived)
        if not isinstance(info, dict) or info.get("classification") != "ai_derived":
            raise ProviderError(f"derived {derived} lacks ai_derived provenance")
        confidence = info.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ProviderError(f"derived {derived} confidence is invalid")
    if opportunity.get("roleAvailable") is not None or opportunity.get("roleDescription") is not None:
        raise ProviderError("the raw record does not support role claims")
    travel = opportunity.get("travelEstimate", {})
    if travel.get("source") != "synthetic_demo":
        raise ProviderError("P0 travel estimate must be marked synthetic_demo")


def load_opportunities(data_mode: str = "demo") -> dict[str, Any]:
    if data_mode == "live":
        configured = os.environ.get("OSEKKAI_LIVE_OPPORTUNITIES_PATH", "").strip()
        default_live = JsonStore().root / "opportunities" / "live-opportunities.json"
        live_path = Path(configured).expanduser().resolve() if configured else default_live
        if live_path.exists():
            try:
                value = json.loads(live_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ProviderError("live opportunities cache could not be loaded") from exc
            if set(value) != {"schemaVersion", "dataMode", "notice", "opportunities"}:
                raise ProviderError("live opportunities cache has invalid fields")
            if value.get("schemaVersion") != "1.0" or value.get("dataMode") != "live" or not isinstance(value.get("opportunities"), list):
                raise ProviderError("live opportunities cache has invalid metadata")
            for opportunity in value["opportunities"]:
                validate_opportunity(opportunity)
                if opportunity.get("verificationStatus") not in {"source_verified", "organizer_verified"}:
                    raise ProviderError("live opportunities cache contains an unverified candidate")
            return copy.deepcopy(value)
        return {
            "schemaVersion": "1.0",
            "dataMode": "live",
            "notice": "Live sync has not produced a verified opportunity cache yet.",
            "opportunities": [],
        }
    if data_mode != "demo":
        raise ProviderError("unsupported opportunity data mode")
    raw = _read_json("opportunities.raw.json")
    normalized = _read_json("opportunities.normalized.json")
    metadata = _read_json("opportunity-source-metadata.json")
    row = _source_record(raw)
    if metadata.get("recordSha256") != raw.get("checksum"):
        raise ProviderError("source metadata checksum differs from raw snapshot")
    opportunities = normalized.get("opportunities")
    if not isinstance(opportunities, list):
        raise ProviderError("normalized opportunities must be an array")
    for opportunity in opportunities:
        if not isinstance(opportunity, dict):
            raise ProviderError("normalized opportunity must be an object")
        _verify_normalized(opportunity, raw, row)
    return copy.deepcopy(normalized)


def normalize_snapshot() -> dict[str, Any]:
    """Validation-only P0 normalizer entrypoint.

    P0 commits the reviewed normalized snapshot and verifies that direct fields
    still match the immutable raw record. It never downloads or rewrites data at
    demo runtime.
    """

    return load_opportunities("demo")


def events_to_opportunities(
    events: list[Mapping[str, Any]],
    *,
    connection_by_event_id: Mapping[str, Mapping[str, Any]],
    route_by_event_id: Mapping[str, Mapping[str, Any]],
    series_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Materialize PUSH candidates only after Evidence and Maps are available."""

    series_map = series_by_id or {}
    event_by_id = {str(event.get("id")): event for event in events}
    opportunities: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for event_value in events:
        event = dict(event_value)
        event_id = str(event.get("id") or "")
        reasons: list[str] = []
        connection = connection_by_event_id.get(event_id)
        route = route_by_event_id.get(event_id)
        if connection is None:
            reasons.append("CONNECTION_EVIDENCE_MISSING")
        if route is None or route.get("source") != "maps_verified" or not isinstance(route.get("minutes"), int):
            reasons.append("MAPS_ROUTE_MISSING")
        elif int(route["minutes"]) > 360:
            reasons.append("MAPS_ROUTE_TOO_LONG")
        address = (route or {}).get("resolvedAddress") or event.get("address") or event.get("venueName")
        if not address:
            reasons.append("LOCATION_MISSING")
        if event.get("status") != "scheduled" or event.get("registrationStatus") not in {"open", "not_required"}:
            reasons.append("REGISTRATION_UNAVAILABLE")
        if reasons:
            excluded.append({"eventId": event_id, "reasons": reasons})
            continue
        series = series_map.get(str(event.get("seriesId"))) if event.get("seriesId") else None
        future_occurrences = []
        for future_id in (series or {}).get("futureOccurrenceIds", []):
            future = event_by_id.get(str(future_id))
            if future and future["id"] != event_id:
                future_occurrences.append(
                    {"eventId": future["id"], "startsAt": future["startsAt"], "endsAt": future["endsAt"], "sourceUrl": future["sourceUrl"]}
                )
        duration = max(1, int((datetime.fromisoformat(event["endsAt"]) - datetime.fromisoformat(event["startsAt"])).total_seconds() // 60))
        classification = event["sourceClassification"]
        source_type = {
            "raw_open_data": "open_data",
            "live_provider": "live_provider",
            "organizer_verified": "organizer_verified",
            "ai_derived": "ai_derived",
            "private_user_data": "private_user_data",
            "synthetic_demo": "ai_derived",
        }[classification]
        level = int(connection["connectionLevel"])
        route_value = {
            "mode": route["mode"],
            "minutes": route["minutes"],
            "source": "maps_verified",
            "computedAt": route.get("computedAt"),
            "distanceMeters": route.get("distanceMeters"),
            "confidence": route.get("confidence", 1),
        }
        opportunity = {
            "schemaVersion": "1.0",
            "id": f"opportunity-{event_id}",
            "sourceRecordId": event["sourceRecordId"],
            "eventId": event_id,
            "communityId": event.get("communityId"),
            "seriesId": event.get("seriesId"),
            "title": event["title"],
            "description": event.get("description", ""),
            "startsAt": event["startsAt"],
            "endsAt": event["endsAt"],
            "address": str(address),
            "latitude": route.get("latitude", event.get("latitude")),
            "longitude": route.get("longitude", event.get("longitude")),
            "priceYen": event.get("priceYen"),
            "socialIntensity": min(5, max(0, level)),
            "conversationRequired": "medium" if connection.get("structuredConversation") == "yes" else "low",
            "soloFriendly": connection.get("soloFriendly") == "yes",
            "recurring": bool(event.get("seriesId")),
            "futureOccurrences": future_occurrences,
            "capacity": event.get("capacity"),
            "participants": event.get("participants"),
            "status": event["status"],
            "registrationStatus": event["registrationStatus"],
            "registrationDeadline": event.get("registrationDeadline"),
            "flexibleVisit": False,
            "visitDurationMinutes": duration,
            "roleAvailable": None if connection.get("roleAvailable") == "unknown" else connection.get("roleAvailable") == "yes",
            "roleDescription": None,
            "categories": event.get("categories", []),
            "provider": event["provider"],
            "sourceType": source_type,
            "sourceClassification": classification,
            "sourceUrl": event["sourceUrl"],
            "sourceDataset": event["sourceDataset"],
            "license": event["license"],
            "capturedAt": event["fetchedAt"],
            "sourceUpdatedAt": event["sourceUpdatedAt"],
            "fetchedAt": event["fetchedAt"],
            "revalidatedAt": event["revalidatedAt"],
            "checksum": event["checksum"],
            "sourceTrust": 0.95,
            "confidence": connection["model"]["confidence"],
            "dataMode": "live",
            "verificationStatus": "organizer_verified" if classification == "organizer_verified" else "source_verified",
            "fieldProvenance": {
                **event["fieldProvenance"],
                "connectionEvidence": {
                    "classification": "ai_derived" if connection["model"]["method"] != "organizer_verified" else "organizer_verified",
                    "confidence": connection["model"]["confidence"],
                    "evidence": connection["evidence"][0]["text"],
                    "sourceUrl": connection["evidence"][0]["url"],
                    "capturedAt": connection["evaluatedAt"],
                },
                "travelEstimate": {
                    "classification": "source_verified",
                    "confidence": route.get("confidence", 1),
                    "evidence": "Google Routes API response",
                    "capturedAt": route.get("computedAt"),
                },
            },
            "connectionEvidence": copy.deepcopy(connection),
            "travelEstimate": route_value,
        }
        validate_opportunity(opportunity)
        opportunities.append(opportunity)
    return opportunities, excluded
