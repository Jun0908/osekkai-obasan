"""P0 deterministic conversation learning and explicit-control parser."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime
from typing import Any

from osekkai_contracts import ContractError, SCHEMA_VERSION
from osekkai_dialogue_plan import build_dialogue_plan
from osekkai_conversation import (
    NOT_ATTENDED_MARKERS,
    POSITIVE_CHECK_IN_MARKERS,
    classify_participation_frictions,
    handle_check_in_unlocked,
    handle_conversation_message_unlocked,
    move_to_safety_handoff_unlocked,
    select_opportunity_unlocked,
    start_user_episode_unlocked,
)
from osekkai_profile import apply_inferred_delta, get_or_create_profile_unlocked, pause_one_week
from osekkai_llm import LLMError
from osekkai_llm_renderer import render_conversation_reply
from osekkai_llm_understanding import understand_message
from osekkai_memory_retrieval import retrieve_relevant_memories
from osekkai_memory_vault import ObsidianMemoryVault, build_episode_memory_note, build_memory_notes
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


def _memory_evidence_ids(profile: dict[str, Any], now: datetime) -> list[str]:
    timestamp = now.isoformat()
    values: list[str] = []
    for entry in profile.get("inferredPreferences", {}).values():
        if not isinstance(entry, dict):
            continue
        for evidence in entry.get("evidence", []):
            if (
                isinstance(evidence, dict)
                and evidence.get("createdAt") == timestamp
                and isinstance(evidence.get("id"), str)
            ):
                values.append(evidence["id"])
    for entry in profile.get("participationFriction", {}).values():
        if not isinstance(entry, dict):
            continue
        for evidence in entry.get("evidence", []):
            if (
                isinstance(evidence, dict)
                and evidence.get("observedAt") == timestamp
                and isinstance(evidence.get("id"), str)
            ):
                values.append(evidence["id"])
    return list(dict.fromkeys(values))[:20]


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
        if remember:
            try:
                vault = ObsidianMemoryVault(data_root=store.root)
                vault.write_note(
                    build_episode_memory_note(
                        user_id=user_id,
                        reference_id=conversation["episode"]["id"],
                        opportunity_id=opportunity_id,
                        now=now,
                    )
                )
                vault.write_profile_projection(conversation["profile"])
            except (ContractError, OSError):
                pass
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

    recent_turns = (
        store.list_conversations_unlocked(user_id)[-6:]
        if profile.get("memoryConsent")
        else []
    )
    vault = ObsidianMemoryVault(data_root=store.root)
    if profile.get("memoryConsent"):
        try:
            retrieval = retrieve_relevant_memories(vault, user_id, message, now)
            relevant_memories = retrieval["notes"]
        except (ContractError, OSError):
            relevant_memories = []
    else:
        relevant_memories = []
    episodes = store.list_conversation_episodes_unlocked(user_id)
    episode_state = str(episodes[0].get("state", "getting_to_know")) if episodes else "getting_to_know"
    llm_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{user_id}:{now.isoformat()}:{message}"))
    understanding: dict[str, Any] | None = None
    try:
        understanding = understand_message(
            message,
            memories=relevant_memories,
            recent_turns=recent_turns,
            episode_state=episode_state,
            idempotency_key=f"osekkai-understand-{llm_id}",
        )
    except LLMError:
        understanding = None
    if understanding and understanding.get("doNotRemember") is True:
        remember = False

    explicit_pause = _contains(message, PAUSE_MARKERS)
    explicit_no_action = _contains(message, DO_NOT_PUSH_MARKERS)
    tired = _contains(message, TIRED_MARKERS)
    wants_outside = _contains(message, OUTSIDE_MARKERS)
    no_talk = _contains(message, NO_TALK_MARKERS)
    interest_categories, interest_labels = _interest_categories(message)
    understood_frictions: list[str] = []
    if understanding is not None:
        interest_categories = list(
            dict.fromkeys([*interest_categories, *understanding.get("categoryHints", [])])
        )
        interest_labels = list(
            dict.fromkeys([*interest_labels, *understanding.get("attractions", [])])
        )
        if float(understanding.get("confidence", 0.0)) >= 0.55:
            understood_frictions = list(understanding.get("participationFrictions", []))
        if (
            understanding.get("doNotPush") is True
            and understanding.get("explicitness") == "explicit"
            and float(understanding.get("confidence", 0.0)) >= 0.8
        ):
            explicit_no_action = True
    deterministic_frictions = classify_participation_frictions(message)
    friction_origin = (
        "explicit"
        if deterministic_frictions
        or (understanding is not None and understanding.get("explicitness") == "explicit")
        else "inferred"
    )
    friction_confidence = (
        1.0
        if friction_origin == "explicit"
        else max(0.0, min(1.0, float(understanding.get("confidence", 0.55))))
        if understanding is not None
        else 0.55
    )

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
    if interest_labels:
        delta["interestLabels"] = interest_labels[:12]
        confidence = max(confidence, float(understanding.get("confidence", 0.0)) if understanding else 0.82)
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
            understood_frictions=understood_frictions,
            friction_origin=friction_origin,
            friction_confidence=friction_confidence,
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
            attraction_changed=bool(interest_categories or interest_labels),
            attraction_label=interest_labels[0] if interest_labels else None,
            understood_frictions=understood_frictions,
            friction_origin=friction_origin,
            friction_confidence=friction_confidence,
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

    plan = build_dialogue_plan(
        conversation,
        understanding=understanding,
        memories=relevant_memories,
    )
    rendered = render_conversation_reply(
        plan,
        user_message=message,
        memories=relevant_memories,
        recent_turns=recent_turns,
        idempotency_key=f"osekkai-render-{llm_id}",
    )
    conversation["reply"] = rendered.text

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
        memory_understanding = understanding
        deterministic_frictions = list(conversation.get("frictionDelta", []))
        if memory_understanding is None and (
            interest_labels
            or interest_categories
            or understood_frictions
            or deterministic_frictions
            or action == "check_in"
        ):
            memory_understanding = {
                "explicitness": "explicit",
                "confidence": confidence,
                "attractions": interest_labels,
                "categoryHints": interest_categories,
            }
        if memory_understanding is not None:
            try:
                notes = build_memory_notes(
                    user_id=user_id,
                    reference_id=conversation_id,
                    understanding=memory_understanding,
                    frictions=list(
                        dict.fromkeys([
                            *deterministic_frictions,
                            *understood_frictions,
                        ])
                    ),
                    now=now,
                    reference_type="feedback" if action == "check_in" else "conversation",
                    evidence_ids=_memory_evidence_ids(conversation.get("profile", profile), now),
                    feedback_summary=(
                        "イベント後に、また参加したい・よかったという感想を共有した"
                        if action == "check_in" and _contains(message, POSITIVE_CHECK_IN_MARKERS)
                        else "イベントに参加できなかったことを共有した"
                        if action == "check_in" and _contains(message, NOT_ATTENDED_MARKERS)
                        else "イベント後の感想を共有した"
                        if action == "check_in"
                        else None
                    ),
                )
                for note in notes:
                    vault.write_note(note)
                vault.write_profile_projection(conversation.get("profile", profile))
            except (ContractError, OSError):
                # JSON Profile remains the operational SSOT; Vault sync is best effort.
                pass

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
