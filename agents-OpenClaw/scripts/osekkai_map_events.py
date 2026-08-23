"""Build the lightweight, paged event feed used by the Chiyoda map."""

from __future__ import annotations

import math
import unicodedata
from typing import Any, Mapping

from osekkai_contracts import ContractError, validate_schema
from osekkai_freebusy import ProviderError
from osekkai_opportunity_sync import load_opportunities
from osekkai_scheduler import load_event_mesh
from osekkai_store import JsonStore


MAP_SCOPE_ID = "chiyoda_kojimachi"
MAP_WARD = "千代田区"
MAP_CENTER = {"latitude": 35.6840, "longitude": 139.7373}
MAP_ZOOM = 14
MAX_PAGE_SIZE = 250


def _ward_verified(event: Mapping[str, Any]) -> bool:
    """Use an explicit administrative address, not an inferred venue name."""

    address = unicodedata.normalize("NFKC", str(event.get("address") or ""))
    return MAP_WARD in address


def _coordinates(event: Mapping[str, Any]) -> tuple[float, float] | None:
    latitude = event.get("latitude")
    longitude = event.get("longitude")
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        return None
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return None
    latitude_value = float(latitude)
    longitude_value = float(longitude)
    if not math.isfinite(latitude_value) or not math.isfinite(longitude_value):
        return None
    if not -90 <= latitude_value <= 90 or not -180 <= longitude_value <= 180:
        return None
    return latitude_value, longitude_value


def _opportunity_by_event(opportunities: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    values = opportunities.get("opportunities", []) if isinstance(opportunities, Mapping) else []
    return {
        str(item["eventId"]): item
        for item in values
        if isinstance(item, Mapping) and isinstance(item.get("eventId"), str)
    }


def build_map_events_result(
    mesh: Mapping[str, Any],
    query: Mapping[str, Any],
    *,
    opportunities: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validated_query = validate_schema(dict(query), "map-events-query.schema.json")
    events = mesh.get("events", [])
    if not isinstance(events, list):
        raise ContractError("map event mesh must contain an events array")

    evidence_values = mesh.get("connectionEvidence", [])
    evidence_by_event = {
        str(item["eventId"]): item
        for item in evidence_values
        if isinstance(item, Mapping) and isinstance(item.get("eventId"), str)
    } if isinstance(evidence_values, list) else {}
    opportunity_by_event = _opportunity_by_event(opportunities)

    in_ward = [event for event in events if isinstance(event, Mapping) and _ward_verified(event)]
    located = [(event, _coordinates(event)) for event in in_ward]
    located = [(event, point) for event, point in located if point is not None]
    located.sort(key=lambda entry: (str(entry[0].get("startsAt", "")), str(entry[0].get("title", "")), str(entry[0].get("id", ""))))

    offset = int(validated_query["offset"])
    limit = min(int(validated_query["limit"]), MAX_PAGE_SIZE)
    page = located[offset:offset + limit]
    compact_events: list[dict[str, Any]] = []
    for event, point in page:
        event_id = str(event["id"])
        opportunity = opportunity_by_event.get(event_id)
        travel = opportunity.get("travelEstimate", {}) if isinstance(opportunity, Mapping) else {}
        compact_events.append({
            "id": event_id,
            "title": event["title"],
            "startsAt": event["startsAt"],
            "endsAt": event["endsAt"],
            "venueName": event.get("venueName"),
            "address": event.get("address"),
            "latitude": point[0],
            "longitude": point[1],
            "status": event["status"],
            "registrationStatus": event["registrationStatus"],
            "capacity": event.get("capacity"),
            "participants": event.get("participants"),
            "priceYen": event.get("priceYen"),
            "categories": list(event.get("categories", [])),
            "provider": event["provider"],
            "sourceUrl": event["sourceUrl"],
            "sourceClassification": event["sourceClassification"],
            "revalidatedAt": event["revalidatedAt"],
            "seriesId": event.get("seriesId"),
            "opportunityId": opportunity.get("id") if isinstance(opportunity, Mapping) else None,
            "travelMinutes": travel.get("minutes") if isinstance(travel, Mapping) else None,
            "connectionEvidence": evidence_by_event.get(event_id),
        })

    end = offset + len(compact_events)
    result = {
        "schemaVersion": "1.0",
        "dataMode": "live",
        "generatedAt": mesh.get("generatedAt"),
        "scope": {
            "id": MAP_SCOPE_ID,
            "ward": MAP_WARD,
            "center": dict(MAP_CENTER),
            "zoom": MAP_ZOOM,
        },
        "events": compact_events,
        "counts": {
            "totalInMesh": len(events),
            "inWard": len(in_ward),
            "withCoordinates": len(located),
            "missingCoordinates": len(in_ward) - len(located),
            "returned": len(compact_events),
        },
        "nextOffset": end if end < len(located) else None,
    }
    return validate_schema(result, "map-events-result.schema.json")


def load_map_events_result(
    query: Mapping[str, Any],
    *,
    store: JsonStore | None = None,
) -> dict[str, Any]:
    storage = store or JsonStore()
    mesh = load_event_mesh(store=storage)
    try:
        opportunities = load_opportunities("live")
    except (ContractError, ProviderError, OSError, ValueError):
        opportunities = None
    return build_map_events_result(mesh, query, opportunities=opportunities)
