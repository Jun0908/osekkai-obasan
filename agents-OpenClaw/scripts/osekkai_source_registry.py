"""Single source of truth for live-provider permissions, cadence, and readiness."""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from osekkai_contracts import ContractError, require_iso_datetime, validate_schema


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "osekkai_sources.json"
READY = "ready"
DISABLED = "disabled"
UNAUTHORIZED = "unauthorized"
CREDENTIAL_MISSING = "credential_missing"


def _read_registry(path: Path) -> dict[str, Any]:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"source registry could not be loaded: {path}") from exc
    validate_schema(registry, "source-registry.schema.json")
    ids = [source["id"] for source in registry["sources"]]
    if len(ids) != len(set(ids)):
        raise ContractError("source registry IDs must be unique")
    for source in registry["sources"]:
        if source["staleAfterMinutes"] < source["refreshMinutes"]:
            raise ContractError(f"{source['id']} staleAfterMinutes must be at least refreshMinutes")
        if source["enabled"] and not source["termsUrl"]:
            raise ContractError(f"{source['id']} cannot be enabled without termsUrl")
    return registry


def source_state(source: Mapping[str, Any], environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    missing = [name for name in source["credentialEnv"] if not str(env.get(name, "")).strip()]
    if not source["enabled"]:
        state = DISABLED
    elif not source["authorized"]:
        state = UNAUTHORIZED
    elif missing:
        state = CREDENTIAL_MISSING
    else:
        state = READY
    return {
        "id": source["id"],
        "displayName": source["displayName"],
        "state": state,
        "canSync": state == READY,
        "requiredForDemo": source["requiredForDemo"],
        "missingCredentials": missing,
        "refreshMinutes": source["refreshMinutes"],
        "staleAfterMinutes": source["staleAfterMinutes"],
    }


def load_source_registry(
    path: Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    registry = _read_registry(path or CONFIG_PATH)
    result = copy.deepcopy(registry)
    result["statuses"] = [source_state(source, environ) for source in registry["sources"]]
    return result


def sources_for_sync(
    path: Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    registry = _read_registry(path or CONFIG_PATH)
    status_by_id = {status["id"]: status for status in (source_state(source, environ) for source in registry["sources"])}
    return [copy.deepcopy(source) for source in registry["sources"] if status_by_id[source["id"]]["canSync"]]


def source_by_id(source_id: str, path: Path | None = None) -> dict[str, Any]:
    registry = _read_registry(path or CONFIG_PATH)
    for source in registry["sources"]:
        if source["id"] == source_id:
            return copy.deepcopy(source)
    raise ContractError(f"unknown source: {source_id}")


def stale_at(source: Mapping[str, Any], fetched_at: str) -> str:
    require_iso_datetime(fetched_at, "fetchedAt")
    parsed = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    return (parsed + timedelta(minutes=int(source["staleAfterMinutes"]))).isoformat()


def is_stale(source: Mapping[str, Any], fetched_at: str, now: datetime) -> bool:
    require_iso_datetime(fetched_at, "fetchedAt")
    if now.tzinfo is None:
        raise ContractError("now must be timezone-aware")
    parsed = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    return now >= parsed + timedelta(minutes=int(source["staleAfterMinutes"]))
