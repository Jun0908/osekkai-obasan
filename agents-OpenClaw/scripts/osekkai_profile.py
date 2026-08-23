"""Distance Profile defaults and update rules."""

from __future__ import annotations

import copy
import os
import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from osekkai_contracts import ContractError, PUSH_TONES, SCHEMA_VERSION, require_bool, require_int
from osekkai_store import JsonStore


JST = ZoneInfo("Asia/Tokyo")
DEFAULT_MAX_SOCIAL_INTENSITY = 2
DEFAULT_MAX_TRAVEL_MINUTES = 40


def _stored_pre_inference_value(profile: dict[str, Any], key: str, default: Any) -> Any:
    explicit = profile.get("explicitPreferences")
    if not isinstance(explicit, dict):
        return default
    stored = explicit.get(key)
    if isinstance(stored, dict):
        return stored.get("value", default)
    return stored if stored is not None else default


def reconcile_inferred_derived_values(profile: dict[str, Any], keys: set[str]) -> None:
    """Make operational fields agree with the remaining inference provenance."""

    inferred = profile.get("inferredPreferences")
    inferred = inferred if isinstance(inferred, dict) else {}
    if "socialBattery" in keys:
        entry = inferred.get("socialBattery")
        value = entry.get("value") if isinstance(entry, dict) else None
        profile["socialBattery"] = (
            value
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100
            else None
        )
    if "maxSocialIntensity" in keys:
        baseline = _stored_pre_inference_value(
            profile,
            "maxSocialIntensity",
            DEFAULT_MAX_SOCIAL_INTENSITY,
        )
        if not isinstance(baseline, int) or isinstance(baseline, bool) or not 0 <= baseline <= 5:
            baseline = DEFAULT_MAX_SOCIAL_INTENSITY
        entry = inferred.get("maxSocialIntensity")
        inferred_value = entry.get("value") if isinstance(entry, dict) else None
        profile["maxSocialIntensity"] = (
            min(baseline, inferred_value)
            if isinstance(inferred_value, int)
            and not isinstance(inferred_value, bool)
            and 0 <= inferred_value <= 5
            else baseline
        )
    if "preferredCategories" in keys:
        baseline = _stored_pre_inference_value(profile, "preferredCategories", [])
        baseline = _validate_string_list(baseline, "preferredCategories") if isinstance(baseline, list) else []
        entry = inferred.get("preferredCategories")
        inferred_value = entry.get("value") if isinstance(entry, dict) else []
        inferred_categories = (
            _validate_string_list(inferred_value, "preferredCategories")
            if isinstance(inferred_value, list)
            else []
        )
        profile["preferredCategories"] = sorted(set([*baseline, *inferred_categories]))


def parse_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ContractError("datetime must include a timezone offset")
    return parsed.astimezone(JST)


def clock_now() -> datetime:
    fixed = os.environ.get("OSEKKAI_FIXED_NOW")
    production = os.environ.get("NODE_ENV", "").strip().lower() == "production"
    demo_enabled = (
        not production
        and os.environ.get("OSEKKAI_DEMO_MODE", "true").lower() in {"1", "true", "yes"}
    )
    if demo_enabled:
        return parse_datetime(fixed or "2019-02-23T10:00:00+09:00")
    return datetime.now(JST)


def default_profile(user_id: str, now: datetime) -> dict[str, Any]:
    timestamp = now.astimezone(JST).isoformat()
    return {
        "schemaVersion": SCHEMA_VERSION,
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"osekkai-profile:{user_id}")),
        "userId": user_id,
        "memoryConsent": False,
        "pushConsent": False,
        "quietHours": {"start": "21:00", "end": "08:00", "timezone": "Asia/Tokyo"},
        "maxPushesPerWeek": 2,
        "preferredTone": "gentle",
        "maxTravelMinutes": DEFAULT_MAX_TRAVEL_MINUTES,
        "maxBudgetYen": 2000,
        "maxSocialIntensity": DEFAULT_MAX_SOCIAL_INTENSITY,
        "socialBattery": None,
        "preferredCategories": [],
        "avoidedCategories": [],
        "rejectionStreak": 0,
        "cooldownUntil": None,
        "lastPushAt": None,
        "pauseUntil": None,
        "explicitPreferences": {},
        "inferredPreferences": {},
        "currentSignals": {
            "interventionHint": "none",
            "currentReceptivity": None,
            "safety": {"level": "normal", "requiresHumanSupport": False},
            "observedAt": None,
        },
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }


def get_or_create_profile_unlocked(store: JsonStore, user_id: str, now: datetime) -> dict[str, Any]:
    profile = store.load_profile_unlocked(user_id)
    if profile is None:
        profile = default_profile(user_id, now)
        store.save_profile_unlocked(user_id, profile)
    elif (
        profile.get("maxTravelMinutes") == 30
        and "maxTravelMinutes" not in profile.get("explicitPreferences", {})
    ):
        # The original demo default was 30 minutes. Move untouched profiles to
        # the current Tokyo standard while preserving every explicit setting.
        profile["maxTravelMinutes"] = DEFAULT_MAX_TRAVEL_MINUTES
        profile["updatedAt"] = now.isoformat()
        store.save_profile_unlocked(user_id, profile)
    return profile


def seed_demo_profile(user_id: str, now: datetime) -> dict[str, Any]:
    profile = default_profile(user_id, now)
    profile.update(
        {
            "memoryConsent": True,
            "pushConsent": True,
            "socialBattery": 55,
            "maxSocialIntensity": 2,
            "explicitPreferences": {
                "demoSeed": {
                    "value": True,
                    "notice": "デモ用に記憶とPUSHへの同意を有効化しています。",
                }
            },
        }
    )
    return profile


def _validate_string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 50:
        raise ContractError(f"{name} must be an array")
    result = []
    for item in value:
        if not isinstance(item, str) or not 1 <= len(item.strip()) <= 80:
            raise ContractError(f"{name} contains an invalid value")
        result.append(item.strip())
    return sorted(set(result))


def _validate_quiet_hours(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ContractError("quietHours must be an object")
    start = value.get("start")
    end = value.get("end")
    timezone = value.get("timezone", "Asia/Tokyo")
    for name, part in (("start", start), ("end", end)):
        if not isinstance(part, str):
            raise ContractError(f"quietHours.{name} is invalid")
        try:
            datetime.strptime(part, "%H:%M")
        except ValueError as exc:
            raise ContractError(f"quietHours.{name} is invalid") from exc
    if timezone != "Asia/Tokyo":
        raise ContractError("P0 quietHours timezone must be Asia/Tokyo")
    return {"start": start, "end": end, "timezone": timezone}


def apply_explicit_patch(profile: dict[str, Any], patch: Any, now: datetime) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise ContractError("patch must be an object")
    allowed = {
        "memoryConsent",
        "pushConsent",
        "quietHours",
        "maxPushesPerWeek",
        "preferredTone",
        "maxTravelMinutes",
        "maxBudgetYen",
        "maxSocialIntensity",
        "preferredCategories",
        "avoidedCategories",
    }
    unknown = set(patch) - allowed
    if unknown:
        raise ContractError(f"profile fields are not editable: {', '.join(sorted(unknown))}")
    result = copy.deepcopy(profile)
    for key, value in patch.items():
        if key in {"memoryConsent", "pushConsent"}:
            result[key] = require_bool(value, key)
        elif key == "quietHours":
            result[key] = _validate_quiet_hours(value)
        elif key == "maxPushesPerWeek":
            result[key] = require_int(value, key, 0, 14)
        elif key == "preferredTone":
            if value not in PUSH_TONES:
                raise ContractError("preferredTone is invalid")
            result[key] = value
        elif key == "maxTravelMinutes":
            validated = require_int(value, key, 0, 240)
            result[key] = validated
            result.setdefault("explicitPreferences", {})[key] = {
                "value": validated,
                "source": "user_setting",
            }
        elif key == "maxBudgetYen":
            result[key] = require_int(value, key, 0, 1_000_000)
        elif key == "maxSocialIntensity":
            validated = require_int(value, key, 0, 5)
            result[key] = validated
            result.setdefault("explicitPreferences", {})[key] = {
                "value": validated,
                "source": "user_setting",
            }
        elif key in {"preferredCategories", "avoidedCategories"}:
            validated = _validate_string_list(value, key)
            if key == "preferredCategories":
                result.setdefault("explicitPreferences", {})[key] = {
                    "value": validated,
                    "source": "user_setting",
                }
                inferred_entry = result.get("inferredPreferences", {}).get(key, {})
                inferred_value = inferred_entry.get("value", []) if isinstance(inferred_entry, dict) else []
                inferred_categories = (
                    _validate_string_list(inferred_value, key)
                    if isinstance(inferred_value, list)
                    else []
                )
                result[key] = sorted(set([*validated, *inferred_categories]))
            else:
                result[key] = validated
    result["updatedAt"] = now.isoformat()
    return result


def remove_evidence(profile: dict[str, Any], evidence_id: str, now: datetime) -> tuple[dict[str, Any], bool]:
    if not isinstance(evidence_id, str) or not evidence_id:
        raise ContractError("removeEvidenceId must be a non-empty string")
    result = copy.deepcopy(profile)
    removed = False
    changed_keys: set[str] = set()
    inferred = result.get("inferredPreferences", {})
    for key in list(inferred):
        before = inferred[key].get("evidence", [])
        after = [item for item in before if not (isinstance(item, dict) and item.get("id") == evidence_id)]
        if len(after) != len(before):
            removed = True
            changed_keys.add(key)
            inferred[key]["evidence"] = after
            if not after:
                del inferred[key]
    if removed:
        reconcile_inferred_derived_values(result, changed_keys)
        result["updatedAt"] = now.isoformat()
    return result, removed


def remove_inferred_preference(
    profile: dict[str, Any], preference_key: str, now: datetime
) -> tuple[dict[str, Any], bool]:
    if not isinstance(preference_key, str) or not 1 <= len(preference_key) <= 128:
        raise ContractError("removeInferredPreferenceKey is invalid")
    result = copy.deepcopy(profile)
    inferred = result.get("inferredPreferences", {})
    removed = preference_key in inferred
    if removed:
        del inferred[preference_key]
        reconcile_inferred_derived_values(result, {preference_key})
        result["updatedAt"] = now.isoformat()
    return result, removed


def apply_inferred_delta(
    profile: dict[str, Any],
    delta: dict[str, Any],
    confidence: float,
    evidence_text: str,
    now: datetime,
) -> dict[str, Any]:
    result = copy.deepcopy(profile)
    safe_evidence = " ".join(evidence_text.strip().split())[:120]
    evidence_id = str(uuid.uuid4())
    for key, value in delta.items():
        if key == "socialBattery":
            result[key] = require_int(value, key, 0, 100)
        elif key == "maxSocialIntensity":
            explicit = result.setdefault("explicitPreferences", {})
            if key not in explicit:
                explicit[key] = {
                    "value": result.get(key, DEFAULT_MAX_SOCIAL_INTENSITY),
                    "source": "pre_inference",
                }
            result[key] = min(result.get(key, 5), require_int(value, key, 0, 5))
        elif key == "preferredCategories":
            categories = _validate_string_list(value, key)
            explicit = result.setdefault("explicitPreferences", {})
            if key not in explicit:
                explicit[key] = {
                    "value": _validate_string_list(result.get(key, []), key),
                    "source": "pre_inference",
                }
            existing = result.get(key, [])
            result[key] = sorted(set([*_validate_string_list(existing, key), *categories]))
        inferred = result.setdefault("inferredPreferences", {})
        entry = inferred.setdefault(key, {"value": value, "confidence": confidence, "evidence": []})
        if key == "preferredCategories":
            previous = entry.get("value", [])
            previous = _validate_string_list(previous, key) if isinstance(previous, list) else []
            entry["value"] = sorted(set([*previous, *_validate_string_list(value, key)]))
        else:
            entry["value"] = value
        entry["confidence"] = max(float(entry.get("confidence", 0.0)), confidence)
        entry.setdefault("evidence", []).append(
            {"id": evidence_id, "text": safe_evidence, "createdAt": now.isoformat()}
        )
    result["updatedAt"] = now.isoformat()
    return result


def pause_one_week(profile: dict[str, Any], now: datetime) -> dict[str, Any]:
    result = copy.deepcopy(profile)
    result["pauseUntil"] = (now + timedelta(days=7)).isoformat()
    result["currentSignals"] = {
        "interventionHint": "do_not_push",
        "currentReceptivity": None,
        "safety": {"level": "normal", "requiresHumanSupport": False},
        "observedAt": now.isoformat(),
    }
    result["updatedAt"] = now.isoformat()
    return result
