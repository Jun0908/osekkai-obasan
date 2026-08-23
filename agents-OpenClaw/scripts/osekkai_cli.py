#!/usr/bin/env python3
"""The sole JSON-in/JSON-out process boundary used by Next.js."""

from __future__ import annotations

import copy
import argparse
import json
import os
import sys
from datetime import timedelta
from typing import Any, Callable

from osekkai_chat import process_chat_unlocked
from osekkai_contracts import (
    ContractError,
    SCHEMA_VERSION,
    validate_command_payload,
    validate_envelope,
    validate_profile,
    validate_runtime_result,
)
from osekkai_freebusy import ProviderError, load_freebusy
from osekkai_metrics import calculate_metrics
from osekkai_google_credentials import (
    GoogleCredentialError,
    GoogleCredentialStore,
    GoogleOAuthConfig,
    complete_authorization,
    create_authorization_request,
    disconnect_google,
)
from osekkai_opportunity_sync import load_opportunities
from osekkai_scheduler import load_event_mesh, load_source_status, run_sync
from osekkai_routes import RoutesError, compute_event_route
from osekkai_profile import (
    apply_explicit_patch,
    clock_now,
    default_profile,
    get_or_create_profile_unlocked,
    parse_datetime,
    pause_one_week,
    remove_evidence,
    remove_inferred_preference,
    seed_demo_profile,
)
from osekkai_run import (
    BusinessError,
    decide_unlocked,
    feedback_unlocked,
    list_interventions_unlocked,
    metrics_unlocked,
    record_outcome_unlocked,
)
from osekkai_store import IdempotencyConflict, JsonStore, LockTimeout, StorageError


MAX_STDIN_BYTES = 1024 * 1024


def _data_mode() -> str:
    if os.environ.get("NODE_ENV", "").strip().lower() == "production":
        return "live"
    value = os.environ.get("OSEKKAI_DEMO_MODE", "true").strip().lower()
    return "live" if value in {"false", "0", "no"} else "demo"


def _retention_days() -> int:
    raw = os.environ.get("OSEKKAI_DATA_RETENTION_DAYS", "30").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ContractError("OSEKKAI_DATA_RETENTION_DAYS must be an integer") from exc
    if not 1 <= value <= 365:
        raise ContractError("OSEKKAI_DATA_RETENTION_DAYS must be between 1 and 365")
    return value


def _success(request_id: str, data: Any, replayed: bool = False) -> dict[str, Any]:
    response = {"ok": True, "requestId": request_id, "data": data}
    if replayed:
        response["idempotentReplay"] = True
    return response


def _error(request_id: str, code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "requestId": request_id,
        "error": {"code": code, "message": message},
    }


def _decision_response_from_episode(episode: dict[str, Any]) -> dict[str, Any]:
    notification = episode.get("notification")
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "episodeId": episode["id"],
        "policyVersion": episode["policyVersion"],
        "decision": episode["decision"],
        "shouldPush": episode["shouldPush"],
        "reasonCodes": copy.deepcopy(episode["reasonCodes"]),
        "score": episode.get("score"),
        "selectedOpportunity": copy.deepcopy(episode.get("selectedOpportunity")),
        "excludedCandidates": copy.deepcopy(episode.get("excludedCandidates", [])),
        "notification": (
            {"text": notification["text"], "tone": notification["tone"]}
            if isinstance(notification, dict)
            else None
        ),
        "dataMode": episode["dataMode"],
        "createdAt": episode["createdAt"],
    }
    if episode.get("dataMode") == "live":
        result["rankedOpportunities"] = copy.deepcopy(episode.get("rankedOpportunities", []))
    return result


def _compact_idempotency_result(command: str, payload: dict[str, Any], result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise StorageError("mutation result cannot be replayed")
    if command == "chat":
        if result.get("persisted") is True:
            response = {
                key: copy.deepcopy(result[key])
                for key in (
                    "schemaVersion",
                    "reply",
                    "profileDelta",
                    "interventionHint",
                    "confidence",
                    "safety",
                    "persisted",
                    "conversationId",
                )
            }
            return {"kind": "chat-remembered", "response": response}
        # Do not duplicate a no-memory reply, semantic delta, safety inference,
        # or profile/evidence snapshot in the idempotency ledger.
        return {"kind": "chat-no-memory"}
    if command == "profile-update":
        return {"kind": "profile-current"}
    if command == "decide":
        return {
            "kind": "decide",
            "episodeId": result["episode"]["id"],
            "decision": copy.deepcopy(result["decision"]),
        }
    if command == "feedback":
        return {
            "kind": "feedback",
            "episodeId": result["episode"]["id"],
            "actionResponse": payload.get("actionResponse"),
        }
    if command == "interventions":
        return {
            "kind": "outcome",
            "episodeId": result["episode"]["id"],
            "recordedOutcome": result["recordedOutcome"],
        }
    # Demo initialization/reset results contain fixture-only synthetic state;
    # retaining the exact response keeps retries stable without repeating the
    # state transition.
    return {"kind": "full", "result": copy.deepcopy(result)}


def _replay_idempotency_result(
    command: str,
    store: JsonStore,
    user_id: str,
    metadata: Any,
    now,
) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise StorageError("idempotency replay metadata is invalid")
    kind = metadata.get("kind")
    if kind == "full" and isinstance(metadata.get("result"), dict):
        return metadata["result"]
    if kind in {"profile-current", "chat-remembered", "chat-no-memory", "feedback"}:
        profile = get_or_create_profile_unlocked(store, user_id, now)
        validate_profile(profile)
    else:
        profile = None
    if kind == "profile-current":
        return profile
    if kind == "chat-remembered":
        response = metadata.get("response")
        if not isinstance(response, dict):
            raise StorageError("remembered chat replay metadata is invalid")
        return {**copy.deepcopy(response), "profile": profile}
    if kind == "chat-no-memory":
        signals = profile.get("currentSignals", {}) if isinstance(profile, dict) else {}
        safety_signal = signals.get("safety", {}) if isinstance(signals, dict) else {}
        requires_support = bool(safety_signal.get("requiresHumanSupport"))
        hint = signals.get("interventionHint", "none")
        if hint not in {"none", "do_not_push", "consider_push"}:
            hint = "none"
        safety_message = (
            "今はイベントを提案しません。差し迫った危険がある場合は、"
            "地域の緊急窓口や信頼できる人へ直接連絡してください。"
            "このデモは診断や自動通報を行いません。"
            if requires_support
            else None
        )
        return {
            "schemaVersion": SCHEMA_VERSION,
            "reply": "この操作はすでに受け取りました。記憶しない内容は再保存していません。",
            "profileDelta": {},
            "interventionHint": hint,
            "confidence": 1.0 if hint == "do_not_push" else 0.5,
            "safety": {
                "requiresHumanSupport": requires_support,
                "level": "urgent" if requires_support else "normal",
                "message": safety_message,
                "supportResourcesVerified": False,
            },
            "persisted": False,
            "conversationId": None,
            "profile": profile,
        }
    if kind in {"decide", "feedback", "outcome"}:
        episode_id = metadata.get("episodeId")
        episode = store.load_episode_unlocked(user_id, episode_id)
        if episode is None:
            raise StorageError("idempotency replay episode no longer exists")
        if kind == "decide":
            decision = metadata.get("decision")
            if not isinstance(decision, dict):
                decision = _decision_response_from_episode(episode)
            return {"decision": decision, "episode": episode}
        if kind == "outcome":
            return {"episode": episode, "recordedOutcome": metadata.get("recordedOutcome")}
        action = metadata.get("actionResponse")
        shown = (episode.get("notification") or {}).get("shownOpportunityIds", [])
        alternative = (
            copy.deepcopy(episode.get("selectedOpportunity"))
            if action == "show_another" and len(shown) > 1
            else None
        )
        return {
            "episode": episode,
            "profile": profile,
            "alternativeOpportunity": alternative,
            "message": (
                "別の確認済み候補はありません。"
                if action == "show_another" and alternative is None
                else None
            ),
        }
    raise StorageError("idempotency replay kind is invalid")


def _emit(value: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _profile_update_unlocked(
    store: JsonStore, user_id: str, payload: dict[str, Any], now
) -> dict[str, Any]:
    allowed = {"patch", "removeEvidenceId", "removeInferredPreferenceKey", "pauseOneWeek"}
    unknown = set(payload) - allowed
    if unknown:
        raise ContractError(f"unknown profile update fields: {', '.join(sorted(unknown))}")
    if not payload:
        raise ContractError("profile update requires an operation")
    profile = get_or_create_profile_unlocked(store, user_id, now)
    removed_evidence = None
    removed_preference = None
    if "patch" in payload:
        profile = apply_explicit_patch(profile, payload["patch"], now)
    if "removeEvidenceId" in payload:
        profile, removed_evidence = remove_evidence(profile, payload["removeEvidenceId"], now)
    if "removeInferredPreferenceKey" in payload:
        profile, removed_preference = remove_inferred_preference(
            profile, payload["removeInferredPreferenceKey"], now
        )
    if "pauseOneWeek" in payload:
        if payload["pauseOneWeek"] is not True:
            raise ContractError("pauseOneWeek must be true")
        profile = pause_one_week(profile, now)
    validate_profile(profile)
    store.save_profile_unlocked(user_id, profile)
    if removed_evidence:
        store.scrub_inferred_copies_unlocked(
            user_id,
            evidence_id=payload["removeEvidenceId"],
        )
    if removed_preference:
        store.scrub_inferred_copies_unlocked(
            user_id,
            preference_key=payload["removeInferredPreferenceKey"],
        )
    return profile


def _demo_reset_unlocked(store: JsonStore, user_id: str, now) -> dict[str, Any]:
    if _data_mode() != "demo":
        raise BusinessError("DEMO_MODE_DISABLED", "デモモードは無効です。")
    deleted = store.delete_user_unlocked(user_id)
    profile = seed_demo_profile(user_id, now)
    validate_profile(profile)
    store.save_profile_unlocked(user_id, profile)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "dataMode": "demo",
        "resetAt": now.isoformat(),
        "deleted": deleted,
        "profile": profile,
        "freebusy": load_freebusy("demo"),
        "opportunities": load_opportunities("demo"),
        "interventions": {"schemaVersion": SCHEMA_VERSION, "interventions": []},
        "metrics": calculate_metrics([], "demo", now),
    }


def _is_untouched_default_profile(profile: dict[str, Any], user_id: str) -> bool:
    """Match only the exact privacy-safe default, including its timestamp."""

    try:
        validate_profile(profile)
        created_at = profile.get("createdAt")
        if created_at != profile.get("updatedAt"):
            return False
        return profile == default_profile(user_id, parse_datetime(created_at))
    except (ContractError, TypeError, ValueError):
        return False


def _demo_seed_unlocked(store: JsonStore, user_id: str, now) -> dict[str, Any]:
    """Seed only a completely untouched user while the caller holds user_lock."""

    if _data_mode() != "demo":
        raise BusinessError("DEMO_MODE_DISABLED", "Demo mode is disabled.")
    profile = get_or_create_profile_unlocked(store, user_id, now)
    untouched = (
        _is_untouched_default_profile(profile, user_id)
        and not store.list_conversations_unlocked(user_id)
        and not store.list_episodes_unlocked(user_id)
    )
    if untouched:
        profile = seed_demo_profile(user_id, now)
        validate_profile(profile)
        store.save_profile_unlocked(user_id, profile)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "dataMode": "demo",
        "seeded": untouched,
        "profile": profile,
    }


def _dispatch_unlocked(
    command: str,
    store: JsonStore,
    user_id: str,
    payload: dict[str, Any],
    now,
) -> Any:
    if command == "chat":
        return process_chat_unlocked(store, user_id, payload, now)
    if command == "profile-update":
        return _profile_update_unlocked(store, user_id, payload, now)
    if command == "decide":
        if payload:
            raise ContractError("decide does not accept browser-supplied decision inputs")
        return decide_unlocked(store, user_id, now, _data_mode())
    if command == "feedback":
        return feedback_unlocked(store, user_id, payload, now)
    if command == "demo-seed":
        if payload:
            raise ContractError("demo-seed payload must be empty")
        return _demo_seed_unlocked(store, user_id, now)
    if command == "demo-reset":
        if payload:
            raise ContractError("demo-reset payload must be empty")
        return _demo_reset_unlocked(store, user_id, now)
    if command == "interventions" and payload.get("action") == "record":
        clean = {key: value for key, value in payload.items() if key != "action"}
        return record_outcome_unlocked(store, user_id, clean, now)
    if command == "calendar-connect":
        if payload:
            raise ContractError("calendar-connect payload must be empty")
        return create_authorization_request(
            user_id,
            now=now,
            config=GoogleOAuthConfig.from_env(),
            store=GoogleCredentialStore(store.root),
        )
    if command == "calendar-callback":
        return complete_authorization(
            user_id,
            state=payload["state"],
            code=payload["code"],
            now=now,
            config=GoogleOAuthConfig.from_env(),
            store=GoogleCredentialStore(store.root),
        )
    if command == "calendar-disconnect":
        if payload:
            raise ContractError("calendar-disconnect payload must be empty")
        return disconnect_google(user_id, GoogleCredentialStore(store.root))
    if command == "sources-sync":
        unknown = set(payload) - {"force", "sourceIds"}
        if unknown or not isinstance(payload.get("force", False), bool):
            raise ContractError("sources-sync payload is invalid")
        source_ids = payload.get("sourceIds")
        if source_ids is not None and (
            not isinstance(source_ids, list)
            or not all(isinstance(value, str) and 1 <= len(value) <= 80 for value in source_ids)
        ):
            raise ContractError("sources-sync sourceIds are invalid")
        return run_sync(
            store=store,
            now=now,
            force=payload.get("force", False),
            source_ids=source_ids,
        )
    raise ContractError("command is not a mutation or has an invalid action")


def _dispatch_read(
    command: str,
    store: JsonStore,
    user_id: str,
    payload: dict[str, Any],
    now,
) -> Any:
    if command == "profile-get":
        if payload:
            raise ContractError("profile-get payload must be empty")
        with store.user_lock(user_id):
            profile = get_or_create_profile_unlocked(store, user_id, now)
            validate_profile(profile)
            return profile
    if command == "freebusy":
        if payload:
            raise ContractError("freebusy payload must be empty")
        return load_freebusy(_data_mode(), user_id=user_id, now=now)
    if command == "opportunities":
        if payload:
            raise ContractError("opportunities payload must be empty")
        return load_opportunities(_data_mode())
    if command == "interventions":
        if payload != {"action": "list"}:
            raise ContractError("interventions action must be list or record")
        with store.user_lock(user_id):
            return list_interventions_unlocked(store, user_id)
    if command == "metrics":
        if payload:
            raise ContractError("metrics payload must be empty")
        with store.user_lock(user_id):
            return metrics_unlocked(store, user_id, _data_mode(), now)
    if command == "cleanup":
        unknown = set(payload) - {"retentionDays"}
        if unknown:
            raise ContractError("cleanup payload is invalid")
        days = payload.get("retentionDays", _retention_days())
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365:
            raise ContractError("retentionDays must be between 1 and 365")
        with store.user_lock(user_id):
            return {
                "schemaVersion": SCHEMA_VERSION,
                "retentionDays": days,
                "removed": store.cleanup_unlocked(user_id, now, days),
            }
    if command == "sources-status":
        if payload:
            raise ContractError("sources-status payload must be empty")
        return load_source_status(store=store)
    if command == "events":
        if payload:
            raise ContractError("events payload must be empty")
        return load_event_mesh(store=store)
    if command == "event-route":
        mesh = load_event_mesh(store=store)
        event = next((item for item in mesh["events"] if item.get("id") == payload["eventId"]), None)
        if event is None:
            raise BusinessError("EVENT_NOT_FOUND", "指定したEventは現在のLive Event Meshにありません。")
        starts_at = parse_datetime(event["startsAt"])
        result = compute_event_route(
            payload["origin"],
            event,
            departure_time=max(now, starts_at - timedelta(hours=1)),
        )
        return {"eventId": event["id"], **result}
    raise ContractError("command must be handled as a mutation")


def _operator_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Operate the Osekkai live event mesh")
    parser.add_argument("command", choices=("sources-sync", "sources-status", "opportunities", "events"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--source", action="append", dest="source_ids")
    args = parser.parse_args(argv)
    store = JsonStore()
    if args.command == "sources-sync":
        value = run_sync(store=store, force=args.force, source_ids=args.source_ids)
    elif args.command == "sources-status":
        value = load_source_status(store=store)
    elif args.command == "events":
        value = load_event_mesh(store=store)
    else:
        if not args.live:
            parser.error("opportunities requires --live")
        value = load_opportunities("live")
    validate_runtime_result("sources-status" if args.command == "sources-status" else args.command, value)
    if args.json:
        print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    else:
        counts = value.get("counts") if isinstance(value, dict) else None
        print(f"{args.command}: {counts or 'ok'}")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1:
        return _operator_main(sys.argv[1:])
    request_id = "invalid-request"
    command = "unknown"
    try:
        raw = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
        if len(raw) > MAX_STDIN_BYTES:
            raise ContractError("request is too large")
        try:
            decoded = raw.decode("utf-8-sig")
            parsed = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError("stdin must contain one UTF-8 JSON object") from exc
        if isinstance(parsed, dict) and isinstance(parsed.get("requestId"), str):
            request_id = parsed["requestId"][:128]
        envelope = validate_envelope(parsed)
        request_id = envelope["requestId"]
        command = envelope["command"]
        user_id = envelope["userId"]
        payload = validate_command_payload(command, envelope["payload"])
        key = envelope.get("idempotencyKey")
        now = clock_now()
        store = JsonStore()
        # A bounded daily scan also applies the 30-day policy to namespaces
        # whose browser cookie has expired and therefore make no more requests.
        store.cleanup_all_if_due(now, _retention_days())
        if command not in {"profile-delete", "demo-reset", "cleanup"}:
            with store.user_lock(user_id):
                store.cleanup_unlocked(user_id, now, _retention_days())
        is_record = command == "interventions" and payload.get("action") == "record"
        mutation = command in {
            "chat", "profile-update", "decide", "feedback", "demo-seed", "demo-reset",
            "calendar-connect", "calendar-callback", "calendar-disconnect"
            , "sources-sync"
        } or is_record
        if is_record and key is None:
            raise ContractError("idempotencyKey is required for interventions record")
        if command == "profile-delete":
            if payload != {"confirm": True}:
                raise ContractError("profile-delete requires confirm=true")
            with store.user_lock(user_id):
                if os.environ.get("OSEKKAI_CREDENTIAL_ENCRYPTION_KEY", "").strip():
                    disconnect_google(user_id, GoogleCredentialStore(store.root))
                result = {
                    "schemaVersion": SCHEMA_VERSION,
                    "deleted": True,
                    "deletedCounts": store.delete_user_unlocked(user_id),
                }
            replayed = False
        elif mutation:
            request_fingerprint = store.idempotency_fingerprint(user_id, command, payload)

            def perform_mutation() -> Any:
                value = _dispatch_unlocked(command, store, user_id, payload, now)
                # Validate before compact replay metadata is committed. This
                # keeps an invalid internal result out of the durable ledger.
                validate_runtime_result(command, value)
                return value

            result, replayed = store.execute_idempotent(
                user_id,
                command,
                key,
                now,
                perform_mutation,
                request_fingerprint=request_fingerprint,
                compact_result=lambda value: _compact_idempotency_result(command, payload, value),
                replay_operation=lambda metadata: _replay_idempotency_result(
                    command,
                    store,
                    user_id,
                    metadata,
                    now,
                ),
            )
        else:
            result = _dispatch_read(command, store, user_id, payload, now)
            replayed = False
        validate_runtime_result(command, result)
        _emit(_success(request_id, result, replayed))
        print(f"osekkai request={request_id} command={command} status=ok", file=sys.stderr)
        return 0
    except ContractError:
        _emit(_error(request_id, "VALIDATION_ERROR", "リクエスト内容を確認してください。"))
        print(f"osekkai request={request_id} command={command} status=invalid", file=sys.stderr)
        return 2
    except IdempotencyConflict:
        _emit(_error(request_id, "IDEMPOTENCY_CONFLICT", "同じ操作キーを別の内容には使えません。"))
        print(f"osekkai request={request_id} command={command} status=idempotency_conflict", file=sys.stderr)
        return 0
    except BusinessError as exc:
        _emit(_error(request_id, exc.code, exc.message))
        print(f"osekkai request={request_id} command={command} status=business_error", file=sys.stderr)
        return 0
    except (LockTimeout, StorageError):
        _emit(_error(request_id, "STORAGE_UNAVAILABLE", "保存領域を利用できません。"))
        print(f"osekkai request={request_id} command={command} status=storage_error", file=sys.stderr)
        return 3
    except RoutesError as exc:
        _emit(_error(request_id, exc.code, "Google Routesから実移動時間を取得できません。"))
        print(f"osekkai request={request_id} command={command} status=routes_error code={exc.code}", file=sys.stderr)
        return 4
    except ProviderError as exc:
        _emit(_error(request_id, exc.code, "候補または空き時間を取得できません。"))
        print(f"osekkai request={request_id} command={command} status=provider_error", file=sys.stderr)
        return 4
    except GoogleCredentialError:
        _emit(_error(request_id, "CALENDAR_CONNECTION_FAILED", "Google Calendarを接続できません。"))
        print(f"osekkai request={request_id} command={command} status=calendar_error", file=sys.stderr)
        return 4
    except Exception:
        _emit(_error(request_id, "INTERNAL_ERROR", "おっせかいエンジンを実行できませんでした。"))
        print(f"osekkai request={request_id} command={command} status=internal_error", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
