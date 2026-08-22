"""P0 orchestration: provider -> policy -> episode -> feedback/outcomes."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Any

from osekkai_contracts import (
    ACTION_RESPONSES,
    DISTANCE_FEEDBACK,
    POLICY_VERSION,
    SCHEMA_VERSION,
    ContractError,
    require_uuid,
    validate_episode,
)
from osekkai_freebusy import load_freebusy
from osekkai_metrics import calculate_metrics
from osekkai_opportunity_sync import load_opportunities
from osekkai_policy import evaluate_policy
from osekkai_profile import get_or_create_profile_unlocked
from osekkai_store import JsonStore, StorageError


class BusinessError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def decide_unlocked(
    store: JsonStore,
    user_id: str,
    now: datetime,
    data_mode: str = "demo",
) -> dict[str, Any]:
    profile = get_or_create_profile_unlocked(store, user_id, now)
    freebusy = load_freebusy(data_mode)
    opportunities = load_opportunities(data_mode)
    existing = store.list_episodes_unlocked(user_id)
    decision = evaluate_policy(profile, freebusy, opportunities, existing, now)
    sequence = max(
        (
            item["sequence"]
            for item in existing
            if isinstance(item.get("sequence"), int)
            and not isinstance(item.get("sequence"), bool)
            and item["sequence"] >= 1
        ),
        default=0,
    ) + 1
    episode_id = str(uuid.uuid4())
    timestamp = now.isoformat()
    episode: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "id": episode_id,
        "userId": user_id,
        "sequence": sequence,
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "policyVersion": POLICY_VERSION,
        "dataMode": data_mode,
        "metricClassification": "demo" if data_mode == "demo" else "measured",
        "minimalRecord": not profile.get("memoryConsent"),
        "decision": decision["decision"],
        "shouldPush": decision["shouldPush"],
        "reasonCodes": decision["reasonCodes"],
        "score": decision["score"],
        "profileSnapshot": copy.deepcopy(profile) if profile.get("memoryConsent") else None,
        "freeWindowSnapshot": copy.deepcopy(decision.get("selectedFreeWindow")) if profile.get("memoryConsent") else None,
        "candidateIdsBeforeFilter": decision["candidateIdsBeforeFilter"] if profile.get("memoryConsent") else [],
        "candidateIdsAfterFilter": decision["candidateIdsAfterFilter"] if profile.get("memoryConsent") else [],
        "excludedCandidates": [
            {"opportunityId": opportunity_id, "reasonCodes": reasons}
            for opportunity_id, reasons in decision["exclusions"].items()
        ] if profile.get("memoryConsent") else [],
        "selectedOpportunity": copy.deepcopy(decision["selectedOpportunity"]) if profile.get("memoryConsent") else None,
        "notification": (
            {
                "text": decision["message"],
                "tone": decision["tone"],
                "shownOpportunityIds": [decision["selectedOpportunityId"]] if decision["selectedOpportunityId"] else [],
            }
            if decision["message"] and profile.get("memoryConsent")
            else None
        ),
        "pushedAt": timestamp if decision["shouldPush"] else None,
        "noPushAt": None if decision["shouldPush"] else timestamp,
        "actionResponse": None,
        "actionResponseAt": None,
        "distanceFeedback": None,
        "distanceFeedbackAt": None,
        "attendedAt": None,
        "revisitedAt": None,
        "selfInitiatedAt": None,
    }
    validate_episode(episode)
    store.save_episode_unlocked(user_id, episode)
    if decision["shouldPush"]:
        profile["lastPushAt"] = timestamp
        profile["updatedAt"] = timestamp
        store.save_profile_unlocked(user_id, profile)
    api_decision = {
        "schemaVersion": SCHEMA_VERSION,
        "episodeId": episode_id,
        "policyVersion": POLICY_VERSION,
        "decision": decision["decision"],
        "shouldPush": decision["shouldPush"],
        "reasonCodes": decision["reasonCodes"],
        "score": decision["score"],
        "selectedOpportunity": copy.deepcopy(decision["selectedOpportunity"]),
        "excludedCandidates": [
            {"opportunityId": opportunity_id, "reasonCodes": reasons}
            for opportunity_id, reasons in decision["exclusions"].items()
        ],
        "notification": (
            {"text": decision["message"], "tone": decision["tone"]}
            if decision["message"]
            else None
        ),
        "dataMode": data_mode,
        "createdAt": timestamp,
    }
    return {"decision": api_decision, "episode": episode}


def _cooldown_hours(streak: int) -> int:
    if streak <= 1:
        return 24
    if streak == 2:
        return 72
    return 168


def _set_cooldown(profile: dict[str, Any], now: datetime, hours: int) -> None:
    proposed = now + timedelta(hours=hours)
    current = profile.get("cooldownUntil")
    if current:
        try:
            current_value = datetime.fromisoformat(current)
            proposed = max(proposed, current_value)
        except ValueError:
            pass
    profile["cooldownUntil"] = proposed.isoformat()


def _set_cadence_preference(profile: dict[str, Any], value: int, now: datetime) -> None:
    profile.setdefault("inferredPreferences", {})["pushCadenceDelta"] = {
        "value": value,
        "confidence": 1.0,
        "evidence": [
            {
                "id": str(uuid.uuid4()),
                "text": "本人による距離評価",
                "createdAt": now.isoformat(),
            }
        ],
    }


def feedback_unlocked(
    store: JsonStore,
    user_id: str,
    payload: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    episode_id = require_uuid(payload.get("episodeId"), "episodeId")
    action = payload.get("actionResponse")
    distance = payload.get("distanceFeedback")
    if (action is None) == (distance is None):
        raise ContractError("provide exactly one of actionResponse or distanceFeedback")
    if action is not None and action not in ACTION_RESPONSES:
        raise ContractError("actionResponse is invalid")
    if distance is not None and distance not in DISTANCE_FEEDBACK:
        raise ContractError("distanceFeedback is invalid")
    episode = store.load_episode_unlocked(user_id, episode_id)
    if episode is None:
        raise BusinessError("EPISODE_NOT_FOUND", "介入エピソードが見つかりません。")
    if not episode.get("shouldPush"):
        raise ContractError("feedback cannot be attached to a no-PUSH episode")
    profile = get_or_create_profile_unlocked(store, user_id, now)
    alternative = None
    if action is not None:
        existing = episode.get("actionResponse")
        if existing and existing != action and not (existing == "show_another" and action == "accepted"):
            raise BusinessError("FEEDBACK_ALREADY_RECORDED", "行動反応はすでに記録されています。")
        if existing == action:
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
        episode["actionResponse"] = action
        episode["actionResponseAt"] = now.isoformat()
        if action == "accepted":
            pass
        elif action == "declined":
            streak = int(profile.get("rejectionStreak", 0)) + 1
            profile["rejectionStreak"] = streak
            _set_cooldown(profile, now, _cooldown_hours(streak))
        elif action == "pause_one_week":
            profile["pauseUntil"] = (now + timedelta(days=7)).isoformat()
        elif action == "show_another":
            notification = episode.get("notification") or {}
            shown = set(notification.get("shownOpportunityIds", []))
            candidates = load_opportunities(episode.get("dataMode", "demo")).get("opportunities", [])
            remaining = [
                candidate
                for candidate in candidates
                if candidate.get("id") in set(episode.get("candidateIdsAfterFilter", []))
                and candidate.get("id") not in shown
            ]
            if remaining:
                remaining.sort(
                    key=lambda item: (
                        -float(item.get("sourceTrust", 0)),
                        item.get("startsAt", ""),
                        int(item.get("travelEstimate", {}).get("minutes", 10**9)),
                        item.get("id", ""),
                    )
                )
                alternative = remaining[0]
                episode["selectedOpportunity"] = copy.deepcopy(alternative)
                notification.setdefault("shownOpportunityIds", []).append(alternative["id"])
                episode["notification"] = notification
    else:
        existing = episode.get("distanceFeedback")
        if existing and existing != distance:
            raise BusinessError("FEEDBACK_ALREADY_RECORDED", "距離評価はすでに記録されています。")
        if existing == distance:
            return {
                "episode": episode,
                "profile": profile,
                "alternativeOpportunity": None,
                "message": None,
            }
        episode["distanceFeedback"] = distance
        episode["distanceFeedbackAt"] = now.isoformat()
        if distance == "too_much":
            _set_cooldown(profile, now, 72)
            if profile.get("memoryConsent"):
                _set_cadence_preference(profile, -1, now)
        elif distance == "just_right":
            profile["rejectionStreak"] = max(0, int(profile.get("rejectionStreak", 0)) - 1)
            current = profile.get("cooldownUntil")
            if current:
                try:
                    if datetime.fromisoformat(current) <= now:
                        profile["cooldownUntil"] = None
                except ValueError:
                    profile["cooldownUntil"] = None
        elif distance == "push_more":
            if profile.get("memoryConsent"):
                _set_cadence_preference(profile, 1, now)
    episode["updatedAt"] = now.isoformat()
    profile["updatedAt"] = now.isoformat()
    validate_episode(episode, allow_legacy_sequence=True)
    store.save_episode_unlocked(user_id, episode)
    store.save_profile_unlocked(user_id, profile)
    return {
        "episode": episode,
        "profile": profile,
        "alternativeOpportunity": alternative,
        "message": "別の確認済み候補はありません。" if action == "show_another" and alternative is None else None,
    }


def record_outcome_unlocked(
    store: JsonStore,
    user_id: str,
    payload: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    episode_id = require_uuid(payload.get("episodeId"), "episodeId")
    event_type = payload.get("eventType") or payload.get("outcome")
    aliases = {
        "attendance": "attended",
        "attended": "attended",
        "revisit": "revisited",
        "revisited": "revisited",
        "selfInitiated": "self_initiated",
        "self_initiated": "self_initiated",
    }
    outcome = aliases.get(event_type)
    if outcome is None:
        raise ContractError("outcome/eventType is invalid")
    status = payload.get("status")
    if status is not None and status not in {outcome, "attended", "revisited", "recorded"}:
        raise ContractError("outcome status is invalid")
    episode = store.load_episode_unlocked(user_id, episode_id)
    if episode is None:
        raise BusinessError("EPISODE_NOT_FOUND", "介入エピソードが見つかりません。")
    if not episode.get("shouldPush"):
        raise ContractError("outcome cannot be attached to a no-PUSH episode")
    if outcome == "attended":
        if episode.get("actionResponse") != "accepted":
            raise ContractError("attendance requires accepted actionResponse")
        field = "attendedAt"
    elif outcome == "revisited":
        if not episode.get("attendedAt"):
            raise ContractError("revisit requires attendance")
        field = "revisitedAt"
    else:
        field = "selfInitiatedAt"
    if episode.get(field) is None:
        episode[field] = now.isoformat()
        episode["updatedAt"] = now.isoformat()
        validate_episode(episode, allow_legacy_sequence=True)
        store.save_episode_unlocked(user_id, episode)
    return {"episode": episode, "recordedOutcome": outcome}


def list_interventions_unlocked(store: JsonStore, user_id: str) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "interventions": store.list_episodes_unlocked(user_id),
    }


def metrics_unlocked(
    store: JsonStore, user_id: str, data_mode: str = "demo", now: datetime | None = None
) -> dict[str, Any]:
    return calculate_metrics(store.list_episodes_unlocked(user_id), data_mode, now)


def run_demo_scenario(
    store: JsonStore,
    user_id: str,
    now: datetime,
    *,
    reset: bool,
) -> dict[str, Any]:
    """Run the reproducible P0 path without any external provider calls."""

    from osekkai_chat import process_chat_unlocked
    from osekkai_profile import seed_demo_profile

    require_uuid(user_id, "userId")
    steps: list[dict[str, Any]] = []
    with store.user_lock(user_id):
        if reset:
            store.delete_user_unlocked(user_id)
        profile = seed_demo_profile(user_id, now)
        store.save_profile_unlocked(user_id, profile)
        first_chat = process_chat_unlocked(
            store,
            user_id,
            {"message": "今週疲れた。何もしたくない", "remember": True},
            now,
        )
        steps.append({"step": 1, "name": "chat-no-action", "result": first_chat})
        steps.append({"step": 2, "name": "profile-low-battery", "result": first_chat["profile"]})
        first_decision = decide_unlocked(store, user_id, now, "demo")
        steps.append({"step": 3, "name": "no-push", "result": first_decision})
        second_chat = process_chat_unlocked(
            store,
            user_id,
            {"message": "少し外に出たいが、話したくない", "remember": True},
            now,
        )
        steps.append({"step": 4, "name": "chat-low-conversation", "result": second_chat})
        freebusy = load_freebusy("demo")
        steps.append({"step": 5, "name": "freebusy", "result": freebusy})
        opportunities = load_opportunities("demo")
        steps.append({"step": 6, "name": "opportunities", "result": opportunities})
        second_decision = decide_unlocked(store, user_id, now, "demo")
        steps.append({"step": 7, "name": "push-one", "result": second_decision})
        episode_id = second_decision["episode"]["id"]
        accepted = feedback_unlocked(
            store,
            user_id,
            {"episodeId": episode_id, "actionResponse": "accepted"},
            now,
        )
        steps.append({"step": 8, "name": "accepted", "result": accepted})
        just_right = feedback_unlocked(
            store,
            user_id,
            {"episodeId": episode_id, "distanceFeedback": "just_right"},
            now,
        )
        steps.append({"step": 9, "name": "just-right", "result": just_right})
        attended = record_outcome_unlocked(
            store,
            user_id,
            {"episodeId": episode_id, "eventType": "attended"},
            now,
        )
        steps.append({"step": 10, "name": "attended", "result": attended})
        revisited = record_outcome_unlocked(
            store,
            user_id,
            {"episodeId": episode_id, "eventType": "revisited"},
            now,
        )
        steps.append({"step": 11, "name": "revisited", "result": revisited})
        metrics = metrics_unlocked(store, user_id, "demo", now)
        steps.append({"step": 12, "name": "metrics", "result": metrics})
    return {
        "schemaVersion": SCHEMA_VERSION,
        "dataMode": "demo",
        "fixedClock": now.isoformat(),
        "completedSteps": len(steps),
        "steps": steps,
        "summary": {
            "firstDecision": first_decision["decision"]["decision"],
            "secondDecision": second_decision["decision"]["decision"],
            "opportunityId": second_decision["decision"]["selectedOpportunity"]["id"],
            "socialBattery": second_chat["profile"]["socialBattery"],
            "episodeCount": len(store.list_episodes(user_id)),
        },
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run the offline Osekkai P0 demo")
    parser.add_argument("--demo", action="store_true", help="run the offline fixed-fixture demo")
    parser.add_argument("--reset", action="store_true", help="delete only the selected demo user's prior data")
    parser.add_argument("--user-id", required=True, help="canonical UUID for the isolated demo namespace")
    parser.add_argument("--json", action="store_true", help="emit compact JSON")
    args = parser.parse_args(argv)
    if not args.demo:
        parser.error("--demo is required for the P0 runner")
    if os.environ.get("NODE_ENV", "").strip().lower() == "production":
        print("offline demo is disabled when NODE_ENV=production", file=sys.stderr)
        return 1
    try:
        now = datetime.fromisoformat("2019-02-23T10:00:00+09:00")
        result = run_demo_scenario(JsonStore(), args.user_id, now, reset=args.reset)
    except (ContractError, BusinessError, StorageError) as exc:
        print(f"demo failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
