"""Read the local Chiyoda community/circle Open Data CSV for chat Grounding.

`data/tokyo-community/communities.csv` already backs the map's "地域コミュニティ"
layer (see `frontend/lib/osekkai/community-directory.ts`), but nothing on the
Python side ever read it, so the chat LLM had no way to mention it. This
module mirrors the TypeScript loader closely enough that both sides report
the same counts, and both read the same
`data/tokyo-community/chiyoda-facility-directory.json` so the two known
facilities' coordinates never drift apart between the two languages.

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


def _read_facility_directory(root: Path) -> list[dict[str, Any]]:
    path = root / "chiyoda-facility-directory.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    facilities = payload.get("facilities")
    if not isinstance(facilities, list):
        raise ValueError("chiyoda-facility-directory.json is missing a facilities array")
    required = {"key", "match", "name", "address", "latitude", "longitude", "sourceUrl"}
    for index, facility in enumerate(facilities):
        if not isinstance(facility, dict) or not required.issubset(facility):
            raise ValueError(f"chiyoda-facility-directory.json facilities[{index}] is malformed")
    return facilities


def _resolve_facility(
    venue_name: str, facilities: list[dict[str, Any]]
) -> dict[str, Any] | None:
    for facility in facilities:
        if str(facility["match"]) in venue_name:
            return facility
    return None


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
    facility_definitions = _read_facility_directory(root)
    rows = _read_communities_csv(root)

    facilities_by_key: dict[str, dict[str, Any]] = {}
    total_in_ward = 0
    with_known_venue = 0
    without_known_venue = 0

    for row in rows:
        if (row.get("ward_name") or "").strip() != ward:
            continue
        total_in_ward += 1

        venue_name_raw = (row.get("venue_name") or "").strip()
        facility = _resolve_facility(venue_name_raw, facility_definitions)
        if facility is None:
            without_known_venue += 1
            continue
        with_known_venue += 1

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
                "区が公開する地域コミュニティ一覧（Open Data CSV）を、施設名から特定できた拠点"
                "（九段生涯学習館・千代田区立スポーツセンター）単位の目安地点として表示しています。"
                "個々の開催日時・現在の活動有無は確認していません。"
            ),
        },
        "counts": {
            "totalInWard": total_in_ward,
            "withKnownVenue": with_known_venue,
            "withoutKnownVenue": without_known_venue,
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
