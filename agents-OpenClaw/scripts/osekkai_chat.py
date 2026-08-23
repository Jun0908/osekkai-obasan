"""P0 deterministic conversation learning and explicit-control parser."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime
from typing import Any

from osekkai_contracts import ContractError, SCHEMA_VERSION
from osekkai_conversation import (
    handle_check_in_unlocked,
    handle_conversation_message_unlocked,
    move_to_safety_handoff_unlocked,
    select_opportunity_unlocked,
    start_user_episode_unlocked,
)
from osekkai_profile import apply_inferred_delta, get_or_create_profile_unlocked, pause_one_week
from osekkai_safety import assess_safety
from osekkai_store import JsonStore


DO_NOT_PUSH_MARKERS = (
    "何もしたくない",
    "今日は放っておいて",
    "今は放っておいて",
    "今日はそっとしておいて",
    "今はそっとしておいて",
    "leave me alone",
)
PAUSE_MARKERS = ("今週は放っておいて", "今週は休む", "一週間放っておいて", "pause for a week")
TIRED_MARKERS = ("疲れた", "つかれた", "しんどい", "exhausted", "tired")
OUTSIDE_MARKERS = ("少し外に出たい", "外に出たい", "散歩したい", "go outside")
NO_TALK_MARKERS = ("話したくない", "会話したくない", "喋りたくない", "don't want to talk")
DO_NOT_REMEMBER_MARKERS = ("これは覚えないで", "覚えないで", "don't remember")
INTEREST_CUES = ("好き", "したい", "やりたい", "始めたい", "興味", "行きたい", "参加したい")
INTEREST_NEGATIONS = ("嫌い", "興味ない", "したくない", "やりたくない", "行きたくない")
INTEREST_GROUPS = (
    ("ダンス・健康", ("ヨガ", "ピラティス", "ダンス", "フィットネス", "ランニング", "運動")),
    ("趣味・実用", ("ボルダリング", "クライミング", "料理", "手芸", "クラフト", "写真", "陶芸", "diy")),
    ("音楽・演劇", ("音楽", "演奏", "ライブ", "楽器", "演劇", "舞台")),
    ("文学・歴史", ("読書", "本", "文学", "歴史", "俳句", "短歌")),
    ("国際理解・語学", ("英語", "語学", "国際交流", "海外", "中国語", "韓国語")),
    ("区民参加・ボランティア", ("ボランティア", "地域活動", "まちづくり", "地域交流")),
)


def _contains(message: str, markers: tuple[str, ...]) -> bool:
    normalized = message.casefold()
    return any(marker.casefold() in normalized for marker in markers)


def _interest_categories(message: str) -> tuple[list[str], list[str]]:
    normalized = " ".join(message.casefold().split())
    if _contains(normalized, INTEREST_NEGATIONS):
        return [], []
    has_interest_cue = _contains(normalized, INTEREST_CUES)
    categories: list[str] = []
    labels: list[str] = []
    for category, markers in INTEREST_GROUPS:
        matched = next((marker for marker in markers if marker.casefold() in normalized), None)
        if matched and (has_interest_cue or len(normalized) <= 30):
            categories.append(category)
            labels.append(matched)
    return categories, labels


def process_chat_unlocked(
    store: JsonStore,
    user_id: str,
    payload: dict[str, Any],
    now: datetime,
    data_mode: str = "demo",
) -> dict[str, Any]:
    action = payload.get("action", "message")
    if action not in {"start", "message", "select", "check_in"}:
        raise ContractError("chat action is invalid")
    message = payload.get("message", "")
    if action in {"message", "check_in"}:
        if not isinstance(message, str) or not message.strip():
            raise ContractError("message must be a non-empty string")
        if len(message) > 2000:
            raise ContractError("message must be at most 2000 characters")
    remember_value = payload.get("remember", True)
    if not isinstance(remember_value, bool):
        raise ContractError("remember must be a boolean")

    profile = get_or_create_profile_unlocked(store, user_id, now)
    remember = (
        remember_value
        and profile["memoryConsent"]
        and not _contains(message, DO_NOT_REMEMBER_MARKERS)
    )
    safety = assess_safety(message or "こんにちは")

    if action == "start":
        conversation = start_user_episode_unlocked(store, user_id, profile, now, data_mode)
        return _chat_result(
            conversation,
            profile=profile,
            profile_delta={},
            friction_delta=[],
            intervention_hint="none",
            confidence=1.0,
            safety=safety,
            persisted=False,
            conversation_id=None,
        )

    if safety["requiresHumanSupport"]:
        episode = move_to_safety_handoff_unlocked(store, user_id, now)
        profile["currentSignals"] = {
            "interventionHint": "do_not_push",
            "currentReceptivity": 0.0,
            "safety": {"level": "urgent", "requiresHumanSupport": True},
            "observedAt": now.isoformat(),
        }
        profile["updatedAt"] = now.isoformat()
        store.save_profile_unlocked(user_id, profile)
        return _chat_result(
            {
                "episode": episode,
                "reply": safety["message"],
                "context": {
                    "schemaVersion": SCHEMA_VERSION,
                    "episodeId": episode["id"],
                    "state": "safety_handoff",
                    "trigger": episode["trigger"],
                    "quickReplies": [],
                    "recommendations": [],
                    "calendarSummary": None,
                    "selectedOpportunityId": episode.get("selectedOpportunityId"),
                    "checkInDueAt": episode.get("checkInDueAt"),
                    "canSendMessage": False,
                    "notice": "Event推薦を止め、人の支えにつながる案内を優先しています。",
                },
            },
            profile=profile,
            profile_delta={},
            friction_delta=[],
            intervention_hint="do_not_push",
            confidence=1.0,
            safety=safety,
            persisted=False,
            conversation_id=None,
        )

    if action == "select":
        opportunity_id = payload.get("opportunityId")
        if not isinstance(opportunity_id, str) or not opportunity_id.strip():
            raise ContractError("opportunityId must be a non-empty string")
        conversation = select_opportunity_unlocked(
            store, user_id, profile, opportunity_id, now, data_mode
        )
        return _chat_result(
            conversation,
            profile=conversation["profile"],
            profile_delta={},
            friction_delta=[],
            intervention_hint="none",
            confidence=1.0,
            safety=safety,
            persisted=False,
            conversation_id=None,
        )

    explicit_pause = _contains(message, PAUSE_MARKERS)
    explicit_no_action = _contains(message, DO_NOT_PUSH_MARKERS)
    tired = _contains(message, TIRED_MARKERS)
    wants_outside = _contains(message, OUTSIDE_MARKERS)
    no_talk = _contains(message, NO_TALK_MARKERS)
    interest_categories, interest_labels = _interest_categories(message)

    delta: dict[str, Any] = {}
    confidence = 0.55
    intervention_hint = "none"
    current_receptivity: float | None = None
    if tired:
        delta["socialBattery"] = 20
        confidence = 0.82
    if no_talk:
        delta["maxSocialIntensity"] = 1
        delta["conversationPreference"] = "none"
        confidence = max(confidence, 0.9)
    if wants_outside:
        current_receptivity = 0.8
        intervention_hint = "consider_push"
        confidence = max(confidence, 0.88)
    if interest_categories:
        delta["preferredCategories"] = interest_categories
        current_receptivity = 0.85
        intervention_hint = "consider_push"
        confidence = max(confidence, 0.86)
    if explicit_no_action:
        current_receptivity = 0.0
        intervention_hint = "do_not_push"
        confidence = max(confidence, 0.95)
    if explicit_pause:
        intervention_hint = "do_not_push"
        current_receptivity = 0.0
        confidence = 1.0
    if explicit_pause:
        profile = pause_one_week(profile, now)
    if remember and delta:
        profile = apply_inferred_delta(profile, delta, confidence, message, now)
    operational_hint = intervention_hint if (remember or explicit_no_action or explicit_pause or safety["requiresHumanSupport"]) else "none"
    profile["currentSignals"] = {
        "interventionHint": operational_hint,
        "currentReceptivity": current_receptivity if remember else (0.0 if operational_hint == "do_not_push" else None),
        "safety": {
            "level": safety["level"],
            "requiresHumanSupport": safety["requiresHumanSupport"],
        },
        "observedAt": now.isoformat(),
    }
    profile["updatedAt"] = now.isoformat()
    store.save_profile_unlocked(user_id, profile)
    conversation_profile = (
        profile
        if remember or not delta
        else apply_inferred_delta(copy.deepcopy(profile), delta, confidence, message, now)
    )

    if action == "check_in":
        conversation = handle_check_in_unlocked(
            store,
            user_id,
            conversation_profile,
            message,
            now,
            data_mode,
            remember=remember,
        )
    else:
        conversation = handle_conversation_message_unlocked(
            store,
            user_id,
            conversation_profile,
            message,
            now,
            data_mode,
            remember=remember,
            attraction_changed=bool(interest_categories),
        )
    if not remember:
        # The current reply may use the unsaved preference, but only operational
        # controls (for example cooldown) may cross the no-memory boundary.
        changed = conversation.get("profile")
        if isinstance(changed, dict):
            for key in ("cooldownUntil", "pauseUntil", "currentSignals"):
                profile[key] = copy.deepcopy(changed.get(key))
            profile["updatedAt"] = now.isoformat()
            store.save_profile_unlocked(user_id, profile)
        conversation["profile"] = profile

    conversation_id: str | None = None
    if remember:
        conversation_id = str(uuid.uuid4())
        store.save_conversation_unlocked(
            user_id,
            {
                "schemaVersion": SCHEMA_VERSION,
                "id": conversation_id,
                "userId": user_id,
                "role": "user",
                "text": message,
                "remember": True,
                "createdAt": now.isoformat(),
            },
        )
        assistant_id = str(uuid.uuid4())
        store.save_conversation_unlocked(
            user_id,
            {
                "schemaVersion": SCHEMA_VERSION,
                "id": assistant_id,
                "userId": user_id,
                "role": "assistant",
                "text": conversation["reply"],
                "remember": True,
                "createdAt": now.isoformat(),
            },
        )
        episode = conversation.get("episode")
        if isinstance(episode, dict):
            episode["turnIds"] = list(
                dict.fromkeys([*episode.get("turnIds", []), conversation_id, assistant_id])
            )
            episode["updatedAt"] = now.isoformat()
            store.save_conversation_episode_unlocked(user_id, episode)

    public_delta = delta if remember else {}
    return _chat_result(
        conversation,
        profile=conversation.get("profile", profile),
        profile_delta=public_delta,
        friction_delta=conversation.get("frictionDelta", []),
        intervention_hint=intervention_hint,
        confidence=confidence,
        safety=safety,
        persisted=remember,
        conversation_id=conversation_id,
    )


def _chat_result(
    conversation: dict[str, Any],
    *,
    profile: dict[str, Any],
    profile_delta: dict[str, Any],
    friction_delta: list[str],
    intervention_hint: str,
    confidence: float,
    safety: dict[str, Any],
    persisted: bool,
    conversation_id: str | None,
) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "reply": conversation["reply"],
        "profileDelta": profile_delta,
        "frictionDelta": friction_delta,
        "interventionHint": intervention_hint,
        "confidence": confidence,
        "safety": safety,
        "persisted": persisted,
        "conversationId": conversation_id,
        "profile": profile,
        "context": conversation["context"],
    }
