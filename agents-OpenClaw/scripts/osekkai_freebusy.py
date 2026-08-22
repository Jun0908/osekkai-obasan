"""Privacy-minimal Free/Busy provider for the deterministic P0 demo."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from osekkai_contracts import ContractError, validate_freebusy


class ProviderError(RuntimeError):
    pass


def fixture_root() -> Path:
    configured = os.environ.get("OSEKKAI_FIXTURE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / "fixtures" / "osekkai"


def load_freebusy(data_mode: str = "demo") -> dict[str, Any]:
    if data_mode != "demo":
        raise ProviderError("live FreeBusy provider is not configured in P0")
    path = fixture_root() / "freebusy.json"
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderError("demo FreeBusy fixture could not be loaded") from exc
    try:
        validate_freebusy(value)
    except ContractError as exc:
        raise ProviderError("demo FreeBusy fixture is invalid") from exc
    forbidden = {"title", "summary", "description", "attendees", "location"}
    if forbidden & set(_walk_keys(value)):
        raise ProviderError("demo FreeBusy fixture contains prohibited calendar details")
    return copy.deepcopy(value)


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(key)
            keys.extend(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_walk_keys(child))
    return keys

