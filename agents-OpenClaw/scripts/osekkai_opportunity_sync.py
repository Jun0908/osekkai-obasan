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
from typing import Any

from osekkai_contracts import ContractError, validate_opportunity
from osekkai_freebusy import ProviderError


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
        return {
            "schemaVersion": "1.0",
            "dataMode": "live",
            "notice": "live Open Data provider is not configured in P0",
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
