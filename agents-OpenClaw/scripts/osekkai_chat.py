"""P0 deterministic conversation learning and explicit-control parser."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from osekkai_contracts import ContractError, SCHEMA_VERSION
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


def _contains(message: str, markers: tuple[str, ...]) -> bool:
    normalized = message.casefold()
    return any(marker.casefold() in normalized for marker in markers)


def process_chat_unlocked(
    store: JsonStore,
    user_id: str,
    payload: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ContractError("message must be a non-empty string")
    if len(message) > 2000:
        raise ContractError("message must be at most 2000 characters")
    remember_value = payload.get("remember", True)
    if not isinstance(remember_value, bool):
        raise ContractError("remember must be a boolean")

    profile = get_or_create_profile_unlocked(store, user_id, now)
    remember = remember_value and profile["memoryConsent"] and not _contains(message, DO_NOT_REMEMBER_MARKERS)
    safety = assess_safety(message)
    explicit_pause = _contains(message, PAUSE_MARKERS)
    explicit_no_action = _contains(message, DO_NOT_PUSH_MARKERS)
    tired = _contains(message, TIRED_MARKERS)
    wants_outside = _contains(message, OUTSIDE_MARKERS)
    no_talk = _contains(message, NO_TALK_MARKERS)

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
    if explicit_no_action:
        current_receptivity = 0.0
        intervention_hint = "do_not_push"
        confidence = max(confidence, 0.95)
    if explicit_pause:
        intervention_hint = "do_not_push"
        current_receptivity = 0.0
        confidence = 1.0
    if safety["requiresHumanSupport"]:
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

    if safety["requiresHumanSupport"]:
        reply = safety["message"]
    elif explicit_pause:
        reply = "わかったわ。今週はおっせかいを休むね。話した内容は、記憶しない指定なら保存しないよ。"
    elif explicit_no_action:
        reply = "今日は何かさせる日じゃなさそうね。提案はせず、ここでは話すだけにしておくわ。"
    elif wants_outside and no_talk:
        reply = "少し外へ出たい気持ちは受け取ったよ。会話がほとんど要らない場所だけ、条件が合う時に一件まで探すね。"
    elif tired:
        reply = "疲れているのね。今日は距離を詰めず、無理に予定を増やさないでおくわ。"
    else:
        reply = "話してくれてありがとう。近づきすぎないよう、希望がはっきりした範囲だけ受け取るね。"

    public_delta = delta if remember else {}
    return {
        "schemaVersion": SCHEMA_VERSION,
        "reply": reply,
        "profileDelta": public_delta,
        "interventionHint": intervention_hint,
        "confidence": confidence,
        "safety": safety,
        "persisted": remember,
        "conversationId": conversation_id,
        "profile": profile,
    }
