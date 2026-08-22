"""Canonical contract checks for the Osekkai CLI.

The canonical JSON Schemas live in ``contracts/osekkai``.  This module keeps
the Python process safe even when it is invoked directly. It deliberately
rejects unknown commands, IDs, enum values, and malformed timestamps at the
process boundary, using the pinned ``jsonschema`` runtime for canonical data.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from functools import lru_cache
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "1.0"
POLICY_VERSION = "osekkai-p0-v1"

COMMANDS = {
    "chat",
    "profile-get",
    "profile-update",
    "profile-delete",
    "freebusy",
    "opportunities",
    "decide",
    "interventions",
    "feedback",
    "metrics",
    "demo-seed",
    "demo-reset",
    "cleanup",
}

REASON_CODES = {
    "NO_PUSH_CONSENT",
    "QUIET_HOURS",
    "COOLDOWN_ACTIVE",
    "WEEKLY_LIMIT_REACHED",
    "EXPLICIT_PAUSE",
    "EXPLICIT_NO_ACTION",
    "HUMAN_SUPPORT_REQUIRED",
    "NO_FREE_WINDOW",
    "NO_VERIFIED_OPPORTUNITY",
    "OUTSIDE_FREE_WINDOW",
    "TRAVEL_LIMIT",
    "OVER_BUDGET",
    "SOCIAL_INTENSITY_LIMIT",
    "INVALID_SOURCE",
    "SCORE_BELOW_THRESHOLD",
    "FREE_WINDOW_AVAILABLE",
    "LOW_SOCIAL_BATTERY",
    "LOW_CONVERSATION_REQUIREMENT",
    "WITHIN_TRAVEL_LIMIT",
    "UNDER_BUDGET",
}

ACTION_RESPONSES = {"accepted", "declined", "show_another", "pause_one_week"}
DISTANCE_FEEDBACK = {"too_much", "just_right", "push_more"}
PUSH_TONES = {"gentle", "casual", "direct", "quiet"}
DATA_MODES = {"demo", "live"}
CLASSIFICATIONS = {"measured", "reference_estimate", "demo", "unverified"}
IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


class ContractError(ValueError):
    """Raised when untrusted input violates the CLI contract."""


@lru_cache(maxsize=1)
def _schema_validators() -> dict[str, Any]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource
    except ImportError as exc:
        raise ContractError("jsonschema dependency is required for canonical validation") from exc

    contract_root = Path(__file__).resolve().parents[2] / "contracts" / "osekkai"
    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    for path in sorted(contract_root.glob("*.schema.json")):
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"canonical schema could not be loaded: {path.name}") from exc
        Draft202012Validator.check_schema(schema)
        schemas[path.name] = schema
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return {
        name: Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
        for name, schema in schemas.items()
    }


def validate_schema(instance: Any, schema_name: str) -> Any:
    validator = _schema_validators().get(schema_name)
    if validator is None:
        raise ContractError(f"unknown canonical schema: {schema_name}")
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "$"
        raise ContractError(f"{schema_name} validation failed at {location}: {first.message}")
    return instance


def require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be an object")
    return value


def require_exact_mapping(value: Any, name: str, keys: set[str]) -> dict[str, Any]:
    obj = dict(require_mapping(value, name))
    missing = keys - set(obj)
    unknown = set(obj) - keys
    if missing or unknown:
        detail = []
        if missing:
            detail.append(f"missing {', '.join(sorted(missing))}")
        if unknown:
            detail.append(f"unknown {', '.join(sorted(unknown))}")
        raise ContractError(f"{name} fields are invalid: {'; '.join(detail)}")
    return obj


def require_uuid(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{name} must be a UUID string")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ContractError(f"{name} must be a valid UUID") from exc
    if str(parsed) != value.lower():
        raise ContractError(f"{name} must use canonical UUID form")
    return value.lower()


def require_iso_datetime(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{name} must be an ISO-8601 datetime")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ContractError(f"{name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{name} must include a timezone offset")
    return value


def require_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise ContractError(f"{name} must be between {minimum} and {maximum}")
    return value


def require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{name} must be a boolean")
    return value


def validate_envelope(value: Any) -> dict[str, Any]:
    obj = dict(require_mapping(value, "envelope"))
    allowed = {
        "schemaVersion",
        "requestId",
        "command",
        "userId",
        "idempotencyKey",
        "payload",
    }
    unknown = set(obj) - allowed
    if unknown:
        raise ContractError(f"unknown envelope fields: {', '.join(sorted(unknown))}")
    if obj.get("schemaVersion") != SCHEMA_VERSION:
        raise ContractError(f"schemaVersion must be {SCHEMA_VERSION}")
    request_id = obj.get("requestId")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
        raise ContractError("requestId must be a non-empty string")
    command = obj.get("command")
    if command not in COMMANDS:
        raise ContractError("command is not allowed")
    require_uuid(obj.get("userId"), "userId")
    payload = obj.get("payload", {})
    obj["payload"] = dict(require_mapping(payload, "payload"))
    key = obj.get("idempotencyKey")
    if key is not None and (not isinstance(key, str) or not IDEMPOTENCY_RE.fullmatch(key)):
        raise ContractError("idempotencyKey has an invalid format")
    if command in MUTATION_COMMANDS and command != "cleanup" and key is None:
        raise ContractError("idempotencyKey is required for mutations")
    return obj


def validate_command_payload(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Apply the same canonical mutation schemas used at the HTTP boundary."""

    schema_by_command = {
        "chat": "chat-request.schema.json",
        "profile-update": "profile-update-request.schema.json",
        "profile-delete": "profile-delete-request.schema.json",
        "decide": "decide-request.schema.json",
        "feedback": "feedback-request.schema.json",
        "demo-seed": "demo-reset-request.schema.json",
        "demo-reset": "demo-reset-request.schema.json",
    }
    schema_name = schema_by_command.get(command)
    if command == "interventions" and payload.get("action") == "record":
        schema_name = "intervention-record-request.schema.json"
    if schema_name is not None:
        validate_schema(payload, schema_name)
    return payload


MUTATION_COMMANDS = {
    "chat",
    "profile-update",
    "profile-delete",
    "decide",
    "feedback",
    "demo-seed",
    "demo-reset",
}


def validate_reason_codes(values: Any) -> list[str]:
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise ContractError("reasonCodes must be a string array")
    unknown = set(values) - REASON_CODES
    if unknown:
        raise ContractError(f"unknown reason code: {', '.join(sorted(unknown))}")
    return values


def validate_profile(profile: Any) -> dict[str, Any]:
    obj = dict(require_mapping(profile, "profile"))
    if obj.get("schemaVersion") != SCHEMA_VERSION:
        raise ContractError("invalid profile schemaVersion")
    require_uuid(obj.get("id"), "profile.id")
    require_uuid(obj.get("userId"), "profile.userId")
    require_iso_datetime(obj.get("createdAt"), "profile.createdAt")
    require_iso_datetime(obj.get("updatedAt"), "profile.updatedAt")
    require_bool(obj.get("memoryConsent"), "profile.memoryConsent")
    require_bool(obj.get("pushConsent"), "profile.pushConsent")
    require_int(obj.get("maxPushesPerWeek"), "profile.maxPushesPerWeek", 0, 14)
    require_int(obj.get("maxTravelMinutes"), "profile.maxTravelMinutes", 0, 240)
    require_int(obj.get("maxBudgetYen"), "profile.maxBudgetYen", 0, 1_000_000)
    require_int(obj.get("maxSocialIntensity"), "profile.maxSocialIntensity", 0, 5)
    battery = obj.get("socialBattery")
    if battery is not None:
        require_int(battery, "profile.socialBattery", 0, 100)
    if obj.get("preferredTone") not in PUSH_TONES:
        raise ContractError("profile.preferredTone is invalid")
    for name in ("preferredCategories", "avoidedCategories"):
        if not isinstance(obj.get(name), list) or not all(isinstance(v, str) for v in obj[name]):
            raise ContractError(f"profile.{name} must be a string array")
    require_mapping(obj.get("explicitPreferences"), "profile.explicitPreferences")
    require_mapping(obj.get("inferredPreferences"), "profile.inferredPreferences")
    validate_schema(obj, "distance-profile.schema.json")
    return obj


def validate_freebusy(value: Any) -> dict[str, Any]:
    obj = dict(require_mapping(value, "freebusy"))
    if obj.get("schemaVersion") != SCHEMA_VERSION or obj.get("dataMode") not in DATA_MODES:
        raise ContractError("invalid freebusy metadata")
    require_iso_datetime(obj.get("generatedAt"), "freebusy.generatedAt")
    windows = obj.get("freeWindows")
    if not isinstance(windows, list):
        raise ContractError("freeWindows must be an array")
    forbidden = {"title", "summary", "description", "attendees", "location"}
    for index, window in enumerate(windows):
        item = require_mapping(window, f"freeWindows[{index}]")
        if forbidden & set(item):
            raise ContractError("freebusy must not contain calendar event details")
        start = require_iso_datetime(item.get("start"), "freeWindow.start")
        end = require_iso_datetime(item.get("end"), "freeWindow.end")
        if datetime.fromisoformat(end) <= datetime.fromisoformat(start):
            raise ContractError("freeWindow.end must be after start")
        require_int(item.get("durationMinutes"), "freeWindow.durationMinutes", 1, 10080)
    validate_schema(obj, "freebusy.schema.json")
    return obj


def validate_opportunity(value: Any) -> dict[str, Any]:
    obj = dict(require_mapping(value, "opportunity"))
    required = {
        "id",
        "title",
        "startsAt",
        "endsAt",
        "address",
        "provider",
        "dataMode",
        "verificationStatus",
        "sourceUrl",
        "sourceDataset",
        "license",
        "capturedAt",
        "checksum",
        "fieldProvenance",
    }
    missing = required - set(obj)
    if missing:
        raise ContractError(f"opportunity missing fields: {', '.join(sorted(missing))}")
    require_iso_datetime(obj["startsAt"], "opportunity.startsAt")
    require_iso_datetime(obj["endsAt"], "opportunity.endsAt")
    require_iso_datetime(obj["capturedAt"], "opportunity.capturedAt")
    if obj["dataMode"] not in DATA_MODES:
        raise ContractError("opportunity.dataMode is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(obj["checksum"])):
        raise ContractError("opportunity.checksum must be sha256 hex")
    require_mapping(obj["fieldProvenance"], "opportunity.fieldProvenance")
    validate_schema(obj, "opportunity.schema.json")
    return obj


def validate_episode(value: Any, *, allow_legacy_sequence: bool = False) -> dict[str, Any]:
    obj = dict(require_mapping(value, "episode"))
    if obj.get("schemaVersion") != SCHEMA_VERSION or obj.get("policyVersion") != POLICY_VERSION:
        raise ContractError("invalid episode version")
    require_uuid(obj.get("id"), "episode.id")
    require_uuid(obj.get("userId"), "episode.userId")
    sequence = obj.get("sequence")
    legacy_without_sequence = sequence is None and allow_legacy_sequence
    if legacy_without_sequence:
        pass
    elif isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ContractError("episode.sequence must be an integer greater than or equal to 1")
    validate_reason_codes(obj.get("reasonCodes"))
    require_bool(obj.get("shouldPush"), "episode.shouldPush")
    if obj.get("metricClassification") not in CLASSIFICATIONS:
        raise ContractError("invalid metricClassification")
    # A legacy record may omit only `sequence`; all its other fields still
    # have to satisfy the canonical contract before it can cross a boundary.
    schema_value = dict(obj)
    if legacy_without_sequence:
        schema_value["sequence"] = 1
    validate_schema(schema_value, "intervention-episode.schema.json")
    return obj


def validate_runtime_result(command: str, data: Any) -> Any:
    """Validate every canonical object before it crosses the Python boundary."""

    if command in {"profile-get", "profile-update"}:
        return validate_schema(data, "distance-profile.schema.json")
    if command == "chat":
        return validate_schema(data, "chat-result.schema.json")
    if command == "freebusy":
        return validate_schema(data, "freebusy.schema.json")
    if command == "opportunities":
        obj = require_exact_mapping(
            data,
            "opportunities result",
            {"schemaVersion", "dataMode", "notice", "opportunities"},
        )
        if obj["schemaVersion"] != SCHEMA_VERSION or obj["dataMode"] not in DATA_MODES:
            raise ContractError("opportunities result version or mode is invalid")
        if not isinstance(obj["notice"], str) or not isinstance(obj["opportunities"], list):
            raise ContractError("opportunities result values are invalid")
        for opportunity in obj["opportunities"]:
            validate_schema(opportunity, "opportunity.schema.json")
        return data
    if command == "decide":
        obj = require_exact_mapping(data, "decide result", {"decision", "episode"})
        validate_schema(obj.get("decision"), "decision.schema.json")
        validate_schema(obj.get("episode"), "intervention-episode.schema.json")
        if obj["decision"]["episodeId"] != obj["episode"]["id"]:
            raise ContractError("decide result episode IDs do not match")
        return data
    if command == "interventions":
        obj = dict(require_mapping(data, "interventions result"))
        if set(obj) == {"schemaVersion", "interventions"}:
            if obj["schemaVersion"] != SCHEMA_VERSION or not isinstance(obj["interventions"], list):
                raise ContractError("interventions list result is invalid")
            items = obj["interventions"]
        elif set(obj) == {"episode", "recordedOutcome"}:
            if obj["recordedOutcome"] not in {"attended", "revisited", "self_initiated"}:
                raise ContractError("recordedOutcome is invalid")
            validate_schema(obj["episode"], "intervention-episode.schema.json")
            return data
        else:
            raise ContractError("interventions result fields are invalid")
        for item in items:
            # Old, pre-sequence records remain readable, but every new record
            # and every record emitted by P0 fixtures must be canonical.
            validate_episode(
                item,
                allow_legacy_sequence=isinstance(item, Mapping) and item.get("sequence") is None,
            )
        return data
    if command == "feedback":
        obj = require_exact_mapping(
            data,
            "feedback result",
            {"episode", "profile", "alternativeOpportunity", "message"},
        )
        validate_schema(obj.get("episode"), "intervention-episode.schema.json")
        validate_schema(obj.get("profile"), "distance-profile.schema.json")
        if obj.get("alternativeOpportunity") is not None:
            validate_schema(obj["alternativeOpportunity"], "opportunity.schema.json")
        if obj["message"] is not None and not isinstance(obj["message"], str):
            raise ContractError("feedback message is invalid")
        return data
    if command == "metrics":
        return validate_schema(data, "metrics.schema.json")
    if command == "demo-seed":
        obj = require_exact_mapping(
            data,
            "demo seed result",
            {"schemaVersion", "dataMode", "seeded", "profile"},
        )
        if (
            obj["schemaVersion"] != SCHEMA_VERSION
            or obj["dataMode"] != "demo"
            or not isinstance(obj["seeded"], bool)
        ):
            raise ContractError("demo seed result is invalid")
        validate_schema(obj.get("profile"), "distance-profile.schema.json")
        return data
    if command == "demo-reset":
        obj = require_exact_mapping(
            data,
            "demo reset result",
            {
                "schemaVersion", "dataMode", "resetAt", "deleted", "profile", "freebusy",
                "opportunities", "interventions", "metrics",
            },
        )
        if obj["schemaVersion"] != SCHEMA_VERSION or obj["dataMode"] != "demo":
            raise ContractError("demo reset version or mode is invalid")
        require_iso_datetime(obj["resetAt"], "demo reset.resetAt")
        deleted = require_mapping(obj["deleted"], "demo reset.deleted")
        if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in deleted.values()):
            raise ContractError("demo reset deleted counts are invalid")
        validate_schema(obj.get("profile"), "distance-profile.schema.json")
        validate_schema(obj.get("freebusy"), "freebusy.schema.json")
        validate_runtime_result("opportunities", obj.get("opportunities"))
        validate_runtime_result("interventions", obj.get("interventions"))
        validate_schema(obj.get("metrics"), "metrics.schema.json")
        return data
    if command == "profile-delete":
        obj = require_exact_mapping(
            data,
            "profile delete result",
            {"schemaVersion", "deleted", "deletedCounts"},
        )
        counts = require_mapping(obj["deletedCounts"], "profile delete.deletedCounts")
        if obj["schemaVersion"] != SCHEMA_VERSION or obj["deleted"] is not True:
            raise ContractError("profile delete result is invalid")
        if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in counts.values()):
            raise ContractError("profile delete counts are invalid")
        return data
    if command == "cleanup":
        obj = require_exact_mapping(
            data,
            "cleanup result",
            {"schemaVersion", "retentionDays", "removed"},
        )
        if obj["schemaVersion"] != SCHEMA_VERSION:
            raise ContractError("cleanup result version is invalid")
        require_int(obj["retentionDays"], "cleanup.retentionDays", 1, 365)
        removed = require_mapping(obj["removed"], "cleanup.removed")
        if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in removed.values()):
            raise ContractError("cleanup removed counts are invalid")
        return data
    return data


def _validate_all() -> dict[str, int]:
    import tempfile

    from osekkai_chat import process_chat_unlocked
    from osekkai_freebusy import load_freebusy
    from osekkai_metrics import calculate_metrics
    from osekkai_opportunity_sync import load_opportunities
    from osekkai_profile import seed_demo_profile
    from osekkai_run import decide_unlocked
    from osekkai_store import JsonStore

    now = datetime.fromisoformat("2019-02-23T10:00:00+09:00")
    user_id = "00000000-0000-4000-8000-000000000001"
    validated = 0
    validators = _schema_validators()
    profile = seed_demo_profile(user_id, now)
    validate_schema(profile, "distance-profile.schema.json")
    validated += 1
    freebusy = load_freebusy("demo")
    validate_schema(freebusy, "freebusy.schema.json")
    validated += 1
    opportunities = load_opportunities("demo")
    for opportunity in opportunities["opportunities"]:
        validate_schema(opportunity, "opportunity.schema.json")
        validated += 1
    with tempfile.TemporaryDirectory() as directory:
        store = JsonStore(directory)
        with store.user_lock(user_id):
            store.save_profile_unlocked(user_id, profile)
            chat = process_chat_unlocked(
                store,
                user_id,
                {"message": "少し外に出たいが、話したくない", "remember": True},
                now,
            )
            conversations = store.list_conversations_unlocked(user_id)
        validate_schema(chat, "chat-result.schema.json")
        validated += 1
        for conversation in conversations:
            validate_schema(conversation, "conversation.schema.json")
            validated += 1
        with store.user_lock(user_id):
            decision = decide_unlocked(store, user_id, now, "demo")
        validate_schema(decision["decision"], "decision.schema.json")
        validate_schema(decision["episode"], "intervention-episode.schema.json")
        validated += 2
        metrics = calculate_metrics([decision["episode"]], "demo", now)
        validate_schema(metrics, "metrics.schema.json")
        validated += 1
    return {"schemas": len(validators), "instances": validated}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Osekkai canonical JSON contracts")
    parser.add_argument("--validate-all", action="store_true", help="validate schemas and P0 fixtures")
    args = parser.parse_args(argv)
    if not args.validate_all:
        parser.error("--validate-all is required")
    try:
        result = _validate_all()
    except (ContractError, OSError) as exc:
        print(f"contract validation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
