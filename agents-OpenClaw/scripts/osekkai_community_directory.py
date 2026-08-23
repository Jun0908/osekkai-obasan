"""Read the local Tokyo community/circle Open Data CSV for chat Grounding.

`data/tokyo-community/communities.csv` already backs the map's "地域コミュニティ"
layer (see `frontend/lib/osekkai/community-directory.ts`), but nothing on the
Python side ever read it, so the chat LLM had no way to mention it. This
module resolves the same way the TypeScript loader does, in priority order:
(1) the row's own `venue_address`, if geocoded in
`venue-address-directory.json` (real per-row precision, mostly 渋谷区);
(2) for 千代田区, a `venue_name` match against one of two real facilities;
(3) otherwise the ward office. Both sides read the same
`data/tokyo-community/{ward-geocoding-directory,venue-address-directory}.json`
so coordinates never drift apart between the two languages. Unlike the Map
API, this loader stays scoped to one ward at a time: chat Grounding only
ever needs the facts relevant to what the user just asked about.

This data is `raw_open_data_unverified` per the Provenance table in
Plan2.md §7: it is a directory listing, not a Live Provider event, so it
must never be phrased as confirming that a circle is currently meeting.
"""

from __future__ import annotations

import csv
import io
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


_FACILITY_FIELDS = {"key", "name", "address", "latitude", "longitude", "sourceUrl"}


def _as_facility(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not _FACILITY_FIELDS.issubset(value):
        raise ValueError(f"{context} is malformed")
    return value


def _read_ward_geocoding_directory(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "ward-geocoding-directory.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    wards = payload.get("wards")
    if not isinstance(wards, dict):
        raise ValueError("ward-geocoding-directory.json is missing a wards object")
    result: dict[str, dict[str, Any]] = {}
    for ward_name, value in wards.items():
        if not isinstance(value, dict):
            raise ValueError(f"ward-geocoding-directory.json wards.{ward_name} is malformed")
        ward_office = _as_facility(value.get("wardOffice"), f"ward-geocoding-directory.json wards.{ward_name}.wardOffice")
        anchors = value.get("anchors")
        if not isinstance(anchors, list):
            raise ValueError(f"ward-geocoding-directory.json wards.{ward_name}.anchors must be a list")
        resolved_anchors = [
            _as_facility(anchor, f"ward-geocoding-directory.json wards.{ward_name}.anchors[{index}]")
            for index, anchor in enumerate(anchors)
        ]
        result[ward_name] = {"wardOffice": ward_office, "anchors": resolved_anchors}
    return result


def _read_venue_address_directory(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "venue-address-directory.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    addresses = payload.get("addresses")
    if not isinstance(addresses, dict):
        raise ValueError("venue-address-directory.json is missing an addresses object")
    for address, value in addresses.items():
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("ward"), str)
            or not isinstance(value.get("latitude"), (int, float))
            or not isinstance(value.get("longitude"), (int, float))
        ):
            raise ValueError(f"venue-address-directory.json addresses.{address} is malformed")
    return addresses


def _address_facility(address: str, entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "key": f"addr:{address}",
        "name": address.removeprefix("東京都"),
        "address": address,
        "latitude": entry["latitude"],
        "longitude": entry["longitude"],
        "sourceUrl": "",
    }


def _resolve_facility(
    ward: str,
    venue_name: str,
    venue_address: str,
    wards: dict[str, dict[str, Any]],
    addresses: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if venue_address:
        known = addresses.get(venue_address)
        if known is not None and known.get("ward") == ward:
            return _address_facility(venue_address, known)
    definition = wards.get(ward)
    if definition is None:
        return None
    for anchor in definition["anchors"]:
        if str(anchor.get("match", "")) and str(anchor["match"]) in venue_name:
            return anchor
    return definition["wardOffice"]


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
    """Group Chiyoda community/circle rows by the facility their venue resolves to.

    Raises OSError/ValueError on a missing or malformed source file; callers
    that treat this as an enhancement (never block chat on it) should catch
    those and fall back to no community facts.
    """

    root = _resolve_data_root(data_root)
    wards = _read_ward_geocoding_directory(root)
    addresses = _read_venue_address_directory(root)
    rows = _read_communities_csv(root)

    facilities_by_key: dict[str, dict[str, Any]] = {}
    total_in_ward = 0
    with_venue_address = 0
    with_known_facility = 0
    with_ward_office_fallback = 0

    for row in rows:
        if (row.get("ward_name") or "").strip() != ward:
            continue
        total_in_ward += 1

        venue_name_raw = (row.get("venue_name") or "").strip()
        venue_address_raw = (row.get("venue_address") or "").strip()
        facility = _resolve_facility(ward, venue_name_raw, venue_address_raw, wards, addresses)
        if facility is None:
            continue
        if str(facility["key"]).startswith("addr:"):
            with_venue_address += 1
        elif facility.get("match"):
            with_known_facility += 1
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
            "venueName": facility["name"],
            "venueAddress": (row.get("venue_address") or "").strip() or facility["address"],
            "latitude": facility["latitude"],
            "longitude": facility["longitude"],
            "targetAudience": (row.get("target_audience") or "").strip() or None,
            "officialUrl": (row.get("official_url") or "").strip() or None,
            "onlineParticipation": (row.get("online_participation") or "").strip() or None,
            "sourceUpdatedAt": (row.get("source_updated_at") or "").strip() or None,
            "fetchedAt": (row.get("fetched_at") or "").strip() or None,
        }

        bucket = facilities_by_key.get(facility["key"])
        if bucket is None:
            bucket = {
                "key": facility["key"],
                "name": facility["name"],
                "address": facility["address"],
                "latitude": facility["latitude"],
                "longitude": facility["longitude"],
                "sourceUrl": facility["sourceUrl"],
                "communities": [],
            }
            facilities_by_key[facility["key"]] = bucket
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
                "活動場所の住所が記載されている行はその住所（主に渋谷区）、"
                "千代田区は施設名から特定できた拠点（九段生涯学習館・千代田区立スポーツセンター）、"
                "それ以外は区役所単位の目安地点です。個々の開催日時・現在の活動有無は確認していません。"
            ),
        },
        "counts": {
            "totalInWard": total_in_ward,
            "withVenueAddress": with_venue_address,
            "withKnownFacility": with_known_facility,
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
