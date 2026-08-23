"""Read the local Tokyo community/circle Open Data CSV for chat Grounding.

`data/tokyo-community/communities.csv` already backs the map's "地域コミュニティ"
layer (see `frontend/lib/osekkai/community-directory.ts`), but nothing on the
Python side ever read it, so the chat LLM had no way to mention it. This
module resolves the same way the TypeScript loader does: a row's own
`latitude`/`longitude` (produced upstream by
https://github.com/Jun0908/tokyo_community_data, grouped by `map_location_id`
when several communities share the same real place) when present, otherwise
the community's ward office, geocoded once via the Geospatial Information
Authority of Japan address-search API and stored in
`data/tokyo-community/ward-geocoding-directory.json`. Both sides read that
same file so coordinates never drift apart between the two languages. Unlike
the Map API, this loader stays scoped to one ward at a time: chat Grounding
only ever needs the facts relevant to what the user just asked about.

This data is `raw_open_data_unverified` per the Provenance table in
Plan2.md §7: it is a directory listing, not a Live Provider event, so it
must never be phrased as confirming that a circle is currently meeting.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


DEFAULT_WARD = "千代田区"
REQUIRED_COLUMNS = (
    "community_id",
    "ward_name",
    "name",
    "name_kana",
    "description",
    "venue_name",
    "venue_address",
    "venue_address_source_url",
    "map_location_id",
    "latitude",
    "longitude",
    "geocoded_address",
    "target_audience",
    "official_url",
    "online_participation",
    "source_updated_at",
    "fetched_at",
)


def _default_data_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "tokyo-community"


def _resolve_data_root(data_root: Path | None) -> Path:
    if data_root is not None:
        return data_root
    configured = os.environ.get("OSEKKAI_COMMUNITY_DATA_ROOT", "").strip()
    return Path(configured) if configured else _default_data_root()


_WARD_OFFICE_FIELDS = {"key", "name", "address", "latitude", "longitude", "sourceUrl"}


def _as_ward_office(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not _WARD_OFFICE_FIELDS.issubset(value):
        raise ValueError(f"{context} is malformed")
    return value


def _read_ward_offices(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "ward-geocoding-directory.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    wards = payload.get("wards")
    if not isinstance(wards, dict):
        raise ValueError("ward-geocoding-directory.json is missing a wards object")
    result: dict[str, dict[str, Any]] = {}
    for ward_name, value in wards.items():
        if not isinstance(value, dict):
            raise ValueError(f"ward-geocoding-directory.json wards.{ward_name} is malformed")
        result[ward_name] = _as_ward_office(
            value.get("wardOffice"), f"ward-geocoding-directory.json wards.{ward_name}.wardOffice"
        )
    return result


def _parse_coordinate(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _resolve_point(
    ward: str,
    csv_row: Mapping[str, str],
    ward_offices: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    latitude = _parse_coordinate(csv_row.get("latitude", ""))
    longitude = _parse_coordinate(csv_row.get("longitude", ""))
    if latitude is not None and longitude is not None:
        location_id = csv_row.get("map_location_id", "").strip() or f"latlng:{latitude:.5f},{longitude:.5f}"
        raw_name = csv_row.get("venue_name", "").strip().split(";")[0].strip()
        address = csv_row.get("geocoded_address", "").strip() or csv_row.get("venue_address", "").strip().split("|")[0].strip()
        name = raw_name or address.removeprefix("東京都") or f"{ward}の活動場所"
        return {
            "key": f"loc:{location_id}",
            "name": name,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "sourceUrl": csv_row.get("venue_address_source_url", "").strip() or csv_row.get("official_url", "").strip(),
            "precise": True,
        }
    office = ward_offices.get(ward)
    if office is None:
        return None
    return {**office, "precise": False}


def _read_communities_csv(root: Path) -> list[dict[str, str]]:
    path = root / "communities.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("communities.csv has no header row")
        missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise ValueError(f"communities.csv is missing expected columns: {', '.join(missing)}")
        return [row for row in reader]


def load_community_directory(
    ward: str = DEFAULT_WARD, *, data_root: Path | None = None
) -> dict[str, Any]:
    """Group a ward's community/circle rows by the real place they resolve to.

    Raises OSError/ValueError on a missing or malformed source file; callers
    that treat this as an enhancement (never block chat on it) should catch
    those and fall back to no community facts.
    """

    root = _resolve_data_root(data_root)
    ward_offices = _read_ward_offices(root)
    rows = _read_communities_csv(root)

    facilities_by_key: dict[str, dict[str, Any]] = {}
    total_in_ward = 0
    with_precise_location = 0
    with_ward_office_fallback = 0

    for row in rows:
        if (row.get("ward_name") or "").strip() != ward:
            continue
        total_in_ward += 1

        point = _resolve_point(ward, row, ward_offices)
        if point is None:
            continue
        if point["precise"]:
            with_precise_location += 1
        else:
            with_ward_office_fallback += 1

        community_id = (row.get("community_id") or "").strip()
        name = (row.get("name") or "").strip()
        if not community_id or not name:
            continue

        entry = {
            "id": community_id,
            "name": name,
            "nameKana": (row.get("name_kana") or "").strip() or None,
            "category": (row.get("description") or "").strip() or None,
            "venueName": (row.get("venue_name") or "").strip() or point["name"],
            "venueAddress": (row.get("venue_address") or "").strip() or point["address"],
            "latitude": point["latitude"],
            "longitude": point["longitude"],
            "targetAudience": (row.get("target_audience") or "").strip() or None,
            "officialUrl": (row.get("official_url") or "").strip() or None,
            "onlineParticipation": (row.get("online_participation") or "").strip() or None,
            "sourceUpdatedAt": (row.get("source_updated_at") or "").strip() or None,
            "fetchedAt": (row.get("fetched_at") or "").strip() or None,
        }

        bucket = facilities_by_key.get(point["key"])
        if bucket is None:
            bucket = {
                "key": point["key"],
                "name": point["name"],
                "address": point["address"],
                "latitude": point["latitude"],
                "longitude": point["longitude"],
                "sourceUrl": point["sourceUrl"],
                "precise": point["precise"],
                "communities": [],
            }
            facilities_by_key[point["key"]] = bucket
        bucket["communities"].append(entry)

    facilities = sorted(
        (
            {**facility, "communities": sorted(facility["communities"], key=lambda item: item["name"])}
            for facility in facilities_by_key.values()
        ),
        key=lambda facility: len(facility["communities"]),
        reverse=True,
    )

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "ward": ward,
        "dataSource": {
            "file": "data/tokyo-community/communities.csv",
            "classification": "raw_open_data_unverified",
            "note": (
                "区が公開する地域コミュニティ一覧（Open Data CSV）を地図・会話へ表示しています。"
                "ジオコーディング済みの活動場所（緯度経度）があればその場所、"
                "無い行は区役所単位の目安地点です。個々の開催日時・現在の活動有無は確認していません。"
            ),
        },
        "counts": {
            "totalInWard": total_in_ward,
            "withPreciseLocation": with_precise_location,
            "withWardOfficeFallback": with_ward_office_fallback,
        },
        "facilities": facilities,
    }


def format_community_facts(directory: Mapping[str, Any], *, limit: int = 6) -> list[str]:
    """Render short, Grounding-safe fact strings for the Dialogue Plan.

    One fact per facility (not per community) keeps this bounded even though
    a facility can list hundreds of circles, and every fact repeats the
    "Open Data・未確認" caveat so the LLM cannot imply a circle is currently
    meeting or accepting members.
    """

    facts: list[str] = []
    for facility in directory.get("facilities", [])[:limit]:
        communities = facility.get("communities", [])
        if not communities:
            continue
        names = "、".join(item["name"] for item in communities[:3])
        more = len(communities) - min(3, len(communities))
        example = f"{names}ほか{more}件" if more > 0 else names
        fact = (
            f"地域コミュニティ(Open Data・活動有無/開催日時は未確認)="
            f"{facility['name']}に{len(communities)}件登録、例: {example}"
        )
        facts.append(fact[:300])
    return facts
