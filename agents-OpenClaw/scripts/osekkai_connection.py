"""Evidence-first Connection Level extraction for normalized Events."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from osekkai_contracts import ContractError, validate_schema


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "osekkai_connection_policy.json"


def load_connection_config(path: Path | None = None) -> dict[str, Any]:
    target = path or Path(os.environ.get("OSEKKAI_CONNECTION_POLICY_PATH", str(CONFIG_PATH))).expanduser().resolve()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError("connection policy could not be loaded") from exc
    expected = {
        "soloFriendly",
        "beginnerFriendly",
        "recurring",
        "structuredConversation",
        "sharedMeal",
        "groupWork",
        "roleAvailable",
        "solicitationRiskHigh",
        "solicitationRiskMedium",
    }
    if value.get("schemaVersion") != "1.0" or value.get("policyVersion") != "connection-v1":
        raise ContractError("connection policy version is invalid")
    patterns = value.get("patterns")
    if not isinstance(patterns, dict) or set(patterns) != expected:
        raise ContractError("connection policy patterns are invalid")
    for key, entries in patterns.items():
        if not isinstance(entries, list) or not entries or not all(isinstance(entry, str) and entry for entry in entries):
            raise ContractError(f"connection policy {key} must contain patterns")
        for entry in entries:
            re.compile(entry, re.IGNORECASE)
    return value


def _text_fields(event: Mapping[str, Any]) -> list[tuple[str, str]]:
    values = [
        ("title", str(event.get("title") or "")),
        ("description", str(event.get("description") or "")),
        ("audience", str(event.get("audience") or "")),
        ("categories", " ".join(str(value) for value in event.get("categories", []))),
    ]
    return [(field, value) for field, value in values if value]


def _match(event: Mapping[str, Any], patterns: list[str]) -> tuple[str, str] | None:
    for field, text in _text_fields(event):
        for pattern in patterns:
            found = re.search(pattern, text, re.IGNORECASE)
            if found:
                start = max(0, found.start() - 35)
                end = min(len(text), found.end() + 70)
                return field, text[start:end].strip()[:220]
    return None


def _evidence(
    *,
    kind: str,
    text: str,
    source_url: str,
    classification: str,
    captured_at: str,
    evidence_field: str,
    confidence: float = 1.0,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "text": text[:500],
        "url": source_url,
        "classification": classification,
        "capturedAt": captured_at,
        "confidence": confidence,
        "evidenceField": evidence_field[:160],
    }


def extract_connection_evidence(
    event: Mapping[str, Any],
    *,
    evaluated_at: datetime,
    series: Mapping[str, Any] | None = None,
    community: Mapping[str, Any] | None = None,
    organizer_evidence: list[Mapping[str, Any]] | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validate_schema(dict(event), "event.schema.json")
    if evaluated_at.tzinfo is None:
        raise ContractError("evaluated_at must be timezone-aware")
    policy = dict(config or load_connection_config())
    patterns = policy["patterns"]
    source_url = str(event["sourceUrl"])
    captured_at = str(event["fetchedAt"])
    classification = str(event["sourceClassification"])
    evidence: list[dict[str, Any]] = []
    states: dict[str, str] = {}
    evidence_kind = {
        "soloFriendly": "solo_friendly",
        "beginnerFriendly": "beginner_friendly",
        "recurring": "recurrence",
        "structuredConversation": "structured_conversation",
        "sharedMeal": "shared_meal",
        "groupWork": "group_work",
        "roleAvailable": "role_available",
    }
    for key, kind in evidence_kind.items():
        matched = _match(event, patterns[key])
        if matched:
            field, excerpt = matched
            states[key] = "yes"
            evidence.append(
                _evidence(
                    kind=kind,
                    text=excerpt,
                    source_url=source_url,
                    classification=classification,
                    captured_at=captured_at,
                    evidence_field=field,
                )
            )
        else:
            states[key] = "unknown"

    future_ids = [str(value) for value in (series or {}).get("futureOccurrenceIds", []) if value]
    if series and future_ids:
        states["recurring"] = "yes"
        series_evidence = (series.get("evidence") or [{}])[0]
        evidence.append(
            _evidence(
                kind="future_occurrence",
                text=str(series_evidence.get("text") or f"同じSeriesに将来回が{len(future_ids)}件あります。"),
                source_url=str(series_evidence.get("url") or series.get("sourceUrl") or source_url),
                classification=str(series_evidence.get("classification") or classification),
                captured_at=str(series_evidence.get("capturedAt") or captured_at),
                evidence_field=str(series_evidence.get("evidenceField") or "futureOccurrenceIds"),
                confidence=float(series_evidence.get("confidence", 1)),
            )
        )

    high_risk = _match(event, patterns["solicitationRiskHigh"])
    medium_risk = _match(event, patterns["solicitationRiskMedium"])
    if high_risk or medium_risk:
        field, excerpt = high_risk or medium_risk
        solicitation_risk = "high" if high_risk else "medium"
        evidence.append(
            _evidence(
                kind="risk",
                text=excerpt,
                source_url=source_url,
                classification=classification,
                captured_at=captured_at,
                evidence_field=field,
            )
        )
    else:
        solicitation_risk = "unknown"

    for item in organizer_evidence or []:
        kind = str(item.get("kind") or "community_path")
        text = str(item.get("text") or "").strip()
        url = str(item.get("url") or "").strip()
        if not text or not url:
            continue
        evidence.append(
            _evidence(
                kind=kind,
                text=text,
                source_url=url,
                classification="organizer_verified",
                captured_at=str(item.get("capturedAt") or evaluated_at.isoformat()),
                evidence_field=str(item.get("evidenceField") or "organizer_confirmation"),
            )
        )
        state_key = next((key for key, value in evidence_kind.items() if value == kind), None)
        if state_key:
            states[state_key] = "yes"

    interaction = any(states[key] == "yes" for key in ("structuredConversation", "sharedMeal", "groupWork", "roleAvailable"))
    welcoming = any(states[key] == "yes" for key in ("soloFriendly", "beginnerFriendly"))
    recurring = states["recurring"] == "yes" or bool(future_ids)
    community_path = bool(community and community.get("futureEventIds"))
    if solicitation_risk == "high":
        level = 0
    elif interaction and recurring and welcoming:
        level = 3
    elif interaction and (recurring or community_path or welcoming):
        level = 2
    elif interaction or recurring:
        level = 1
    else:
        level = 0

    if not evidence:
        excerpt = next((value for _field, value in _text_fields(event) if value), str(event["title"]))[:220]
        evidence.append(
            _evidence(
                kind="risk",
                text=f"公開説明: {excerpt}",
                source_url=source_url,
                classification=classification,
                captured_at=captured_at,
                evidence_field="description",
            )
        )
    confidence = min(1.0, 0.55 + min(len(evidence), 5) * 0.08)
    result = {
        "schemaVersion": "1.0",
        "eventId": event["id"],
        "connectionLevel": level,
        "soloFriendly": states["soloFriendly"],
        "beginnerFriendly": states["beginnerFriendly"],
        "recurring": states["recurring"],
        "structuredConversation": states["structuredConversation"],
        "sharedMeal": states["sharedMeal"],
        "groupWork": states["groupWork"],
        "roleAvailable": states["roleAvailable"],
        "futureOccurrenceCount": len(future_ids),
        "solicitationRisk": solicitation_risk,
        "evidence": evidence,
        "model": {"method": "rules", "version": policy["policyVersion"], "confidence": round(confidence, 2)},
        "evaluatedAt": evaluated_at.isoformat(),
    }
    validate_schema(result, "connection-evidence.schema.json")
    return result
