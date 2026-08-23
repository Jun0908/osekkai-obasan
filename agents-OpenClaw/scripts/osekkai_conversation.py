"""Deterministic conversation episode state machine for Osekkai Chat."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, time, timedelta
from typing import Any, Iterable

from osekkai_context_trigger import (
    analyze_calendar_sparsity,
    build_recommendation_context,
    proactive_trigger_allowed,
)
from osekkai_contracts import ContractError, SCHEMA_VERSION, validate_schema
from osekkai_freebusy import ProviderError, load_freebusy
from osekkai_opportunity_sync import load_opportunities
from osekkai_policy import load_policy_config
from osekkai_profile import (
    apply_inferred_delta,
    apply_participation_frictions,
    get_or_create_profile_unlocked,
    parse_datetime,
)
from osekkai_store import JsonStore


STATES = {
    "getting_to_know",
    "calendar_sparse",
    "shortlist_shown",
    "friction_probe",
    "adjusted_shortlist",
    "accepted",
    "check_in_due",
    "cooldown",
    "safety_handoff",
}

ALLOWED_TRANSITIONS = {
    "getting_to_know": {"shortlist_shown", "cooldown", "safety_handoff"},
    "calendar_sparse": {"shortlist_shown", "cooldown", "safety_handoff"},
    "shortlist_shown": {"friction_probe", "accepted", "cooldown", "safety_handoff"},
    "friction_probe": {"adjusted_shortlist", "cooldown", "safety_handoff"},
    "adjusted_shortlist": {"accepted", "cooldown", "safety_handoff"},
    "accepted": {"check_in_due", "cooldown", "safety_handoff"},
    "check_in_due": {"getting_to_know", "cooldown", "safety_handoff"},
    "cooldown": {"getting_to_know", "safety_handoff"},
    "safety_handoff": {"cooldown"},
}

FRICTION_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("search_fatigue", ("探すのが面倒", "検索が面倒", "探し疲れ", "選ぶのが面倒", "探したくない")),
    ("first_time_anxiety", ("初参加", "初めて", "初心者", "入り方がわからない", "勝手がわからない")),
    ("stranger_anxiety", ("知らない人", "人見知り", "よそ者", "知り合いがいない", "一人で行くのが不安")),
    ("group_size", ("人が多い", "大人数", "混んで", "少人数がいい", "人数が多")),
    ("conversation_load", ("会話が多", "雑談", "話し続け", "話すのが苦手", "喋るのが", "会話したくない")),
    ("travel_effort", ("遠い", "移動が", "乗り換え", "歩くのが", "近い方が", "行くのが大変")),
    ("time_commitment", ("時間が長", "長すぎ", "拘束", "短時間", "時間がない", "予定に収ま")),
    ("cost", ("高い", "お金", "料金", "参加費", "予算", "無料がいい")),
    ("low_social_energy", ("疲れた", "しんどい", "気力が", "元気が", "今日は疲", "人に会う元気")),
    ("push_aversion", ("押さないで", "しつこい", "圧が", "強く誘", "放っておいて", "急かさないで")),
    ("not_today", ("今日は無理", "今回は無理", "今日はいい", "今じゃない", "また今度", "今日はやめ")),
)

REJECTION_MARKERS = (
    "これは違う",
    "行きたくない",
    "微妙",
    "ちょっと違う",
    "ほかがいい",
    "別のがいい",
    "無理",
    "嫌",
    "やめとく",
    "もういい",
)

POSITIVE_CHECK_IN_MARKERS = (
    "また行きたい",
    "楽しかった",
    "よかった",
    "良かった",
    "入りやすかった",
    "人の感じはよかった",
)

NOT_ATTENDED_MARKERS = ("行けなかった", "参加できなかった", "行かなかった")
ATTENDANCE_REASON_MARKERS = ("予定", "用事", "仕事", "体調", "気分", "その他")

FRICTION_QUICK_REPLIES = [
    {"id": "first-time", "label": "初参加が不安", "message": "初参加で入り方がわからない"},
    {"id": "people", "label": "人・会話が不安", "message": "知らない人との雑談が多そう"},
    {"id": "effort", "label": "時間・距離・料金", "message": "時間か距離か料金がひっかかる"},
]

CHECK_IN_QUICK_REPLIES = [
    {"id": "again", "label": "また行きたい", "message": "また行きたい"},
    {"id": "too-much-talk", "label": "会話が多かった", "message": "会話が多すぎた"},
    {"id": "not-attended", "label": "行けなかった", "message": "行けなかった"},
]

NOT_ATTENDED_QUICK_REPLIES = [
    {"id": "schedule", "label": "予定", "message": "予定が変わって行けなかった"},
    {"id": "distance", "label": "距離", "message": "ちょっと遠くて行けなかった"},
    {"id": "anxiety", "label": "気分・不安", "message": "初参加が不安で行けなかった"},
]


def classify_participation_frictions(message: str) -> list[str]:
    normalized = " ".join(message.casefold().split())
    return [
        friction
        for friction, markers in FRICTION_MARKERS
        if any(marker.casefold() in normalized for marker in markers)
    ]


def _contains(message: str, markers: Iterable[str]) -> bool:
    normalized = message.casefold()
    return any(marker.casefold() in normalized for marker in markers)


def transition_episode(
    episode: dict[str, Any],
    next_state: str,
    now: datetime,
    **changes: Any,
) -> dict[str, Any]:
    current = episode.get("state")
    if current not in STATES or next_state not in STATES:
        raise ContractError("conversation state is invalid")
    if next_state != current and next_state not in ALLOWED_TRANSITIONS[current]:
        raise ContractError(f"invalid conversation transition: {current} -> {next_state}")
    updated = copy.deepcopy(episode)
    updated.update(changes)
    updated["state"] = next_state
    updated["updatedAt"] = now.isoformat()
    if int(updated.get("adjustmentCount", 0)) > 1:
        raise ContractError("conversation shortlist can be adjusted only once")
    if int(updated.get("presentationCount", 0)) > 2:
        raise ContractError("conversation shortlist can be presented only twice")
    validate_schema(updated, "conversation-episode.schema.json")
    return updated


def _new_episode(
    user_id: str,
    now: datetime,
    *,
    trigger: str,
    state: str,
    reason: str,
) -> dict[str, Any]:
    timestamp = now.isoformat()
    episode = {
        "schemaVersion": SCHEMA_VERSION,
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "state": state,
        "trigger": trigger,
        "startedReason": reason,
        "shownOpportunityIds": [],
        "adjustedOpportunityIds": [],
        "presentationCount": 0,
        "adjustmentCount": 0,
        "selectedOpportunityId": None,
        "selectedEventId": None,
        "selectedEventEndsAt": None,
        "checkInDueAt": None,
        "checkInCompletedAt": None,
        "cooldownUntil": None,
        "frictionEvidenceIds": [],
        "turnIds": [],
        "closedAt": None,
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }
    validate_schema(episode, "conversation-episode.schema.json")
    return episode


def _save_episode(store: JsonStore, user_id: str, episode: dict[str, Any]) -> dict[str, Any]:
    validate_schema(episode, "conversation-episode.schema.json")
    store.save_conversation_episode_unlocked(user_id, episode)
    return episode


def _latest_open_episode(store: JsonStore, user_id: str, now: datetime) -> dict[str, Any] | None:
    for episode in store.list_conversation_episodes_unlocked(user_id):
        if episode.get("closedAt") is not None:
            continue
        if episode.get("state") == "accepted" and isinstance(episode.get("checkInDueAt"), str):
            if parse_datetime(episode["checkInDueAt"]) <= now:
                episode = transition_episode(episode, "check_in_due", now)
                _save_episode(store, user_id, episode)
        if episode.get("state") == "cooldown" and isinstance(episode.get("cooldownUntil"), str):
            if parse_datetime(episode["cooldownUntil"]) <= now:
                episode = transition_episode(episode, "getting_to_know", now, cooldownUntil=None)
                _save_episode(store, user_id, episode)
        return episode
    return None


def _basic_context(
    episode: dict[str, Any] | None,
    *,
    recommendations: list[dict[str, Any]] | None = None,
    quick_replies: list[dict[str, str]] | None = None,
    calendar_summary: dict[str, Any] | None = None,
    notice: str | None = None,
) -> dict[str, Any]:
    context = {
        "schemaVersion": SCHEMA_VERSION,
        "episodeId": episode.get("id") if episode else None,
        "state": episode.get("state", "getting_to_know") if episode else "getting_to_know",
        "trigger": episode.get("trigger", "user_initiated") if episode else "user_initiated",
        "quickReplies": copy.deepcopy(quick_replies or []),
        "recommendations": copy.deepcopy(recommendations or []),
        "calendarSummary": copy.deepcopy(calendar_summary),
        "selectedOpportunityId": episode.get("selectedOpportunityId") if episode else None,
        "checkInDueAt": episode.get("checkInDueAt") if episode else None,
        "canSendMessage": episode is None or episode.get("state") != "safety_handoff",
        "notice": notice,
    }
    validate_schema(context, "conversation-context.schema.json")
    return context


def _stored_recommendations(episode: dict[str, Any], data_mode: str) -> list[dict[str, Any]]:
    ids = (
        episode.get("adjustedOpportunityIds", [])
        if episode.get("state") == "adjusted_shortlist"
        else episode.get("shownOpportunityIds", [])
    )
    try:
        source = load_opportunities(data_mode)
    except Exception:
        return []
    by_id = {
        item.get("id"): item
        for item in source.get("opportunities", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    values: list[dict[str, Any]] = []
    for rank, opportunity_id in enumerate(ids, start=1):
        opportunity = by_id.get(opportunity_id)
        if opportunity is None:
            continue
        values.append(
            {
                "rank": rank,
                "opportunity": copy.deepcopy(opportunity),
                "recommendationReasons": [
                    {
                        "code": "personal_fit",
                        "text": "話した好みと参加条件から残った、Source確認済みの候補です。",
                        "evidenceUrl": opportunity.get("sourceUrl"),
                        "classification": "private_user_data",
                    }
                ],
            }
        )
    return values


def _calendar_and_recommendations(
    store: JsonStore,
    user_id: str,
    profile: dict[str, Any],
    now: datetime,
    data_mode: str,
    *,
    friction_types: set[str] | None = None,
    revalidate: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, str | None]:
    try:
        freebusy = load_freebusy(data_mode, user_id=user_id, now=now)
        sparsity = analyze_calendar_sparsity(freebusy, now)
        recommendations = build_recommendation_context(
            store,
            user_id,
            profile,
            freebusy,
            now,
            data_mode=data_mode,
            friction_types=friction_types,
            revalidate=revalidate,
        )
        minimum = int(load_policy_config()["conversationTrigger"]["minimumCandidates"])
        if data_mode == "live" and len(recommendations) < minimum:
            return (
                [],
                sparsity["summary"],
                "条件を満たす実Eventが複数そろわなかったため、無理に一件だけを押していません。",
            )
        return recommendations, sparsity["summary"], None
    except ProviderError as exc:
        if exc.code == "CALENDAR_NOT_CONNECTED":
            return [], None, "候補を空き時間に合わせるには、設定からGoogle Calendarを接続してください。"
        return [], None, "Calendarの空き時間を確認できませんでした。少し後でもう一度試してください。"
    except (ContractError, OSError, TimeoutError):
        return [], None, "確認済みの空き時間を読み取れなかったため、いまは候補を作っていません。"


def _present_recommendations(
    store: JsonStore,
    user_id: str,
    episode: dict[str, Any],
    recommendations: list[dict[str, Any]],
    now: datetime,
    *,
    adjusted: bool,
) -> dict[str, Any]:
    if not recommendations:
        raise ContractError("recommendations require source-backed opportunities")
    ids = [item["opportunity"]["id"] for item in recommendations[:3]]
    changes: dict[str, Any] = {
        "presentationCount": int(episode.get("presentationCount", 0)) + 1,
    }
    next_state = "adjusted_shortlist" if adjusted else "shortlist_shown"
    if adjusted:
        changes.update({"adjustmentCount": 1, "adjustedOpportunityIds": ids})
    else:
        changes["shownOpportunityIds"] = ids
    return _save_episode(
        store,
        user_id,
        transition_episode(episode, next_state, now, **changes),
    )


def start_user_episode_unlocked(
    store: JsonStore,
    user_id: str,
    profile: dict[str, Any],
    now: datetime,
    data_mode: str,
) -> dict[str, Any]:
    episode = _latest_open_episode(store, user_id, now)
    if episode is None:
        episode = _save_episode(
            store,
            user_id,
            _new_episode(
                user_id,
                now,
                trigger="user_initiated",
                state="getting_to_know",
                reason="本人が「話す」を開いた",
            ),
        )
    state = episode["state"]
    if state == "check_in_due":
        reply = "この前のイベント、どうだった？ また行ってもよさそうだった？"
        return {
            "episode": episode,
            "reply": reply,
            "context": _basic_context(episode, quick_replies=CHECK_IN_QUICK_REPLIES),
        }
    if state in {"shortlist_shown", "adjusted_shortlist"}:
        recommendations = _stored_recommendations(episode, data_mode)
        return {
            "episode": episode,
            "reply": "さっきの候補は覚えてるよ。どれなら行けそう？",
            "context": _basic_context(
                episode,
                recommendations=recommendations,
                notice=None if recommendations else "候補の募集状態が変わったため、もう一度探し直してください。",
            ),
        }
    if state == "friction_probe":
        return {
            "episode": episode,
            "reply": "何がひっかかった？ 一番近いものを一つだけ教えて。",
            "context": _basic_context(episode, quick_replies=FRICTION_QUICK_REPLIES),
        }
    if state == "accepted":
        return {
            "episode": episode,
            "reply": "よし。行ってみて、終わった頃に一言だけ聞くね。",
            "context": _basic_context(episode),
        }
    if state == "cooldown":
        return {
            "episode": episode,
            "reply": "今日はここまでで大丈夫。次に話したくなった時に呼んで。",
            "context": _basic_context(episode, quick_replies=[]),
        }
    if state == "safety_handoff":
        return {
            "episode": episode,
            "reply": "いまはイベント探しより、人の支えにつながることを優先します。",
            "context": _basic_context(episode),
        }
    known = profile.get("preferredCategories", [])
    if known:
        reply = "前に話してた好み、覚えてるよ。今日はどんな集まりなら行けそう？"
    else:
        reply = "まず、最近ちょっと気になってることを一つ聞かせて。"
    return {"episode": episode, "reply": reply, "context": _basic_context(episode)}


def start_calendar_sparse_episode_unlocked(
    store: JsonStore,
    user_id: str,
    now: datetime,
    data_mode: str,
) -> dict[str, Any] | None:
    """Create a proactive episode only after every Calendar/PUSH/live gate passes."""

    profile = get_or_create_profile_unlocked(store, user_id, now)
    conversation_episodes = store.list_conversation_episodes_unlocked(user_id)
    if any(item.get("closedAt") is None for item in conversation_episodes):
        return None
    push_history = [*store.list_episodes_unlocked(user_id), *conversation_episodes]
    if not proactive_trigger_allowed(profile, push_history, now):
        return None
    try:
        freebusy = load_freebusy(data_mode, user_id=user_id, now=now)
        sparsity = analyze_calendar_sparsity(freebusy, now)
    except (ProviderError, ContractError, OSError, TimeoutError):
        return None
    if not sparsity["isSparse"]:
        return None
    horizon_days = int(load_policy_config()["conversationTrigger"]["horizonDays"])
    horizon_end = now + timedelta(days=horizon_days)
    trigger_freebusy = copy.deepcopy(freebusy)
    trigger_freebusy["freeWindows"] = [
        item
        for item in trigger_freebusy.get("freeWindows", [])
        if isinstance(item, dict)
        and isinstance(item.get("start"), str)
        and isinstance(item.get("end"), str)
        and parse_datetime(item["start"]) < horizon_end
        and parse_datetime(item["end"]) > now
    ]
    recommendations = build_recommendation_context(
        store,
        user_id,
        profile,
        trigger_freebusy,
        now,
        data_mode=data_mode,
        revalidate=True,
    )
    minimum = int(load_policy_config()["conversationTrigger"]["minimumCandidates"])
    if len(recommendations) < minimum:
        return None
    episode = _save_episode(
        store,
        user_id,
        _new_episode(
            user_id,
            now,
            trigger="calendar_sparse",
            state="calendar_sparse",
            reason="次の7日間に確認済みの長い空き時間が複数ある",
        ),
    )
    episode = _present_recommendations(
        store, user_id, episode, recommendations, now, adjusted=False
    )
    return {
        "episode": episode,
        "reply": "来週、長めの空きがいくつかあるね。予定の中身は見てないよ。その時間に収まる集まりを、情報源まで確認して持ってきたよ。",
        "context": _basic_context(
            episode,
            recommendations=recommendations,
            calendar_summary=sparsity["summary"],
        ),
    }


def move_to_safety_handoff_unlocked(
    store: JsonStore, user_id: str, now: datetime
) -> dict[str, Any]:
    episode = _latest_open_episode(store, user_id, now)
    if episode is None:
        episode = _new_episode(
            user_id,
            now,
            trigger="user_initiated",
            state="safety_handoff",
            reason="Safety GuardrailがEvent推薦より先に作動",
        )
    elif episode["state"] != "safety_handoff":
        episode = transition_episode(episode, "safety_handoff", now)
    return _save_episode(store, user_id, episode)


def _cooldown(
    store: JsonStore,
    user_id: str,
    episode: dict[str, Any],
    profile: dict[str, Any],
    now: datetime,
    *,
    days: int = 1,
) -> tuple[dict[str, Any], dict[str, Any]]:
    until = now + timedelta(days=days)
    episode = transition_episode(
        episode,
        "cooldown",
        now,
        cooldownUntil=until.isoformat(),
    )
    profile["cooldownUntil"] = until.isoformat()
    profile["currentSignals"] = {
        "interventionHint": "do_not_push",
        "currentReceptivity": 0.0,
        "safety": {"level": "normal", "requiresHumanSupport": False},
        "observedAt": now.isoformat(),
    }
    profile["updatedAt"] = now.isoformat()
    store.save_profile_unlocked(user_id, profile)
    return _save_episode(store, user_id, episode), profile


def handle_conversation_message_unlocked(
    store: JsonStore,
    user_id: str,
    profile: dict[str, Any],
    message: str,
    now: datetime,
    data_mode: str,
    *,
    remember: bool,
    attraction_changed: bool,
    attraction_label: str | None = None,
    understood_frictions: list[str] | None = None,
    friction_origin: str = "explicit",
    friction_confidence: float = 1.0,
) -> dict[str, Any]:
    episode = _latest_open_episode(store, user_id, now)
    if episode is None:
        episode = _save_episode(
            store,
            user_id,
            _new_episode(
                user_id,
                now,
                trigger="preference_intake" if attraction_changed else "user_initiated",
                state="getting_to_know",
                reason="本人が会話を始めた",
            ),
        )
    if episode["state"] == "check_in_due":
        return handle_check_in_unlocked(
            store,
            user_id,
            profile,
            message,
            now,
            data_mode,
            remember=remember,
            understood_frictions=understood_frictions,
            friction_origin=friction_origin,
            friction_confidence=friction_confidence,
        )

    frictions = list(
        dict.fromkeys([*classify_participation_frictions(message), *(understood_frictions or [])])
    )
    rejected = _contains(message, REJECTION_MARKERS) or bool(frictions)
    if episode["state"] == "cooldown":
        return {
            "episode": episode,
            "profile": profile,
            "frictionDelta": [],
            "reply": "今日はここまで。しつこく追いかけないから、また話したくなったら呼んで。",
            "context": _basic_context(episode),
        }
    if episode["state"] == "accepted":
        return {
            "episode": episode,
            "profile": profile,
            "frictionDelta": [],
            "reply": "選んだイベントは覚えてるよ。終わった頃に一言だけ聞くね。",
            "context": _basic_context(episode),
        }
    if episode["state"] in {"shortlist_shown", "adjusted_shortlist"} and rejected:
        if episode["state"] == "adjusted_shortlist" or "もういい" in message:
            episode, profile = _cooldown(store, user_id, episode, profile, now)
            return {
                "episode": episode,
                "profile": profile,
                "frictionDelta": [],
                "reply": "わかった。今日はもう出さないね。断ったことを責めたりしないよ。",
                "context": _basic_context(episode),
            }
        episode = _save_episode(
            store,
            user_id,
            transition_episode(episode, "friction_probe", now),
        )
        if not frictions:
            return {
                "episode": episode,
                "profile": profile,
                "frictionDelta": [],
                "reply": "何がひっかかった？ 初参加、人や会話、時間・距離・料金のどれに近い？ 一つだけでいいよ。",
                "context": _basic_context(episode, quick_replies=FRICTION_QUICK_REPLIES),
            }

    if episode["state"] == "friction_probe" or (
        episode["state"] == "shortlist_shown" and frictions
    ):
        if not frictions:
            return {
                "episode": episode,
                "profile": profile,
                "frictionDelta": [],
                "reply": "うまく言えなくても大丈夫。一番近いものを一つだけ選んで。",
                "context": _basic_context(episode, quick_replies=FRICTION_QUICK_REPLIES),
            }
        if set(frictions) & {"low_social_energy", "not_today", "push_aversion"}:
            days = 7 if "push_aversion" in frictions else 1
            episode, profile = _cooldown(store, user_id, episode, profile, now, days=days)
            if remember:
                profile, evidence_ids = apply_participation_frictions(
                    profile,
                    frictions,
                    origin=friction_origin,
                    reference_type="message",
                    reference_id=str(uuid.uuid4()),
                    evidence_text="本人が参加をためらう理由を明示",
                    confidence=friction_confidence,
                    now=now,
                )
                episode["frictionEvidenceIds"] = sorted(
                    set([*episode["frictionEvidenceIds"], *evidence_ids])
                )
                store.save_profile_unlocked(user_id, profile)
                _save_episode(store, user_id, episode)
            return {
                "episode": episode,
                "profile": profile,
                "frictionDelta": frictions if remember else [],
                "reply": "そっか。今日は候補を足さないね。次に自分から話したくなった時で大丈夫。",
                "context": _basic_context(episode),
            }

        evidence_ids: list[str] = []
        if remember:
            profile, evidence_ids = apply_participation_frictions(
                profile,
                frictions,
                origin=friction_origin,
                reference_type="message",
                reference_id=str(uuid.uuid4()),
                evidence_text="本人が参加をためらう理由を明示",
                confidence=friction_confidence,
                now=now,
            )
            store.save_profile_unlocked(user_id, profile)
        recommendations, calendar_summary, notice = _calendar_and_recommendations(
            store,
            user_id,
            profile,
            now,
            data_mode,
            friction_types=set(frictions),
        )
        if not recommendations:
            episode, profile = _cooldown(store, user_id, episode, profile, now)
            return {
                "episode": episode,
                "profile": profile,
                "frictionDelta": frictions if remember else [],
                "reply": "その条件で確認できる候補は今はなかったよ。無理に別の候補は作らないね。",
                "context": _basic_context(episode, calendar_summary=calendar_summary, notice=notice),
            }
        episode["frictionEvidenceIds"] = sorted(
            set([*episode["frictionEvidenceIds"], *evidence_ids])
        )
        episode = _present_recommendations(
            store, user_id, episode, recommendations, now, adjusted=True
        )
        return {
            "episode": episode,
            "profile": profile,
            "frictionDelta": frictions if remember else [],
            "reply": "なるほど、そこがひっかかってたんだね。条件を変えて、一度だけ並べ直したよ。どれなら行けそう？",
            "context": _basic_context(
                episode,
                recommendations=recommendations,
                calendar_summary=calendar_summary,
                notice=notice,
            ),
        }

    if episode["state"] == "getting_to_know":
        if not attraction_changed and not profile.get("preferredCategories"):
            return {
                "episode": episode,
                "profile": profile,
                "frictionDelta": [],
                "reply": "もう少し具体的に聞かせて。ヨガ、料理、音楽みたいに、やってみたいことを一つだけ。",
                "context": _basic_context(episode),
            }
        evidence_ids: list[str] = []
        if remember and frictions:
            profile, evidence_ids = apply_participation_frictions(
                profile,
                frictions,
                origin=friction_origin,
                reference_type="message",
                reference_id=str(uuid.uuid4()),
                evidence_text="本人が参加をためらう理由を明示",
                confidence=friction_confidence,
                now=now,
            )
            store.save_profile_unlocked(user_id, profile)
            episode["frictionEvidenceIds"] = sorted(
                set([*episode["frictionEvidenceIds"], *evidence_ids])
            )
            _save_episode(store, user_id, episode)
        recommendations, calendar_summary, notice = _calendar_and_recommendations(
            store,
            user_id,
            profile,
            now,
            data_mode,
            friction_types=set(frictions),
        )
        if not recommendations:
            return {
                "episode": episode,
                "profile": profile,
                "frictionDelta": frictions if remember else [],
                "reply": "好みはわかったよ。でも空き時間と募集状態まで確認できる候補は今はない。架空のイベントは出さないね。",
                "context": _basic_context(episode, calendar_summary=calendar_summary, notice=notice),
            }
        episode = _present_recommendations(
            store, user_id, episode, recommendations, now, adjusted=False
        )
        label = (attraction_label or message.strip())[:40]
        return {
            "episode": episode,
            "profile": profile,
            "frictionDelta": frictions if remember else [],
            "reply": f"{label}ね、いいじゃない。空き時間と実際の移動まで見て、行った先で人と関われる候補を持ってきたよ。",
            "context": _basic_context(
                episode,
                recommendations=recommendations,
                calendar_summary=calendar_summary,
                notice=notice,
            ),
        }

    return {
        "episode": episode,
        "profile": profile,
        "frictionDelta": [],
        "reply": "候補の「行ってみる」を押すか、ひっかかるところを一つ教えて。",
        "context": _basic_context(
            episode, recommendations=_stored_recommendations(episode, data_mode)
        ),
    }


def select_opportunity_unlocked(
    store: JsonStore,
    user_id: str,
    profile: dict[str, Any],
    opportunity_id: str,
    now: datetime,
    data_mode: str,
) -> dict[str, Any]:
    episode = _latest_open_episode(store, user_id, now)
    if episode is None or episode.get("state") not in {"shortlist_shown", "adjusted_shortlist"}:
        raise ContractError("an opportunity can be selected only from an active shortlist")
    allowed = set(episode.get("adjustedOpportunityIds") or episode.get("shownOpportunityIds", []))
    if opportunity_id not in allowed:
        raise ContractError("selected opportunity was not shown in this conversation")
    source = load_opportunities(data_mode)
    opportunity = next(
        (item for item in source.get("opportunities", []) if item.get("id") == opportunity_id),
        None,
    )
    if not isinstance(opportunity, dict):
        raise ContractError("selected opportunity is no longer available")
    if data_mode == "live" and (
        opportunity.get("status") != "scheduled"
        or opportunity.get("registrationStatus") not in {"open", "not_required"}
    ):
        raise ContractError("selected opportunity is no longer open")
    ends_at = parse_datetime(opportunity["endsAt"])
    trigger_config = load_policy_config()["conversationTrigger"]
    delay = int(trigger_config["checkInDelayMinutes"])
    due_at = ends_at + timedelta(minutes=delay)
    activity_start = time.fromisoformat(trigger_config["activityStart"])
    activity_end = time.fromisoformat(trigger_config["activityEnd"])
    if due_at.timetz().replace(tzinfo=None) < activity_start:
        due_at = due_at.replace(
            hour=activity_start.hour,
            minute=activity_start.minute,
            second=0,
            microsecond=0,
        )
    elif due_at.timetz().replace(tzinfo=None) >= activity_end:
        due_at = (due_at + timedelta(days=1)).replace(
            hour=activity_start.hour,
            minute=activity_start.minute,
            second=0,
            microsecond=0,
        )
    episode = transition_episode(
        episode,
        "accepted",
        now,
        selectedOpportunityId=opportunity_id,
        selectedEventId=str(opportunity.get("eventId") or opportunity_id),
        selectedEventEndsAt=ends_at.isoformat(),
        checkInDueAt=due_at.isoformat(),
    )
    _save_episode(store, user_id, episode)
    return {
        "episode": episode,
        "profile": profile,
        "frictionDelta": [],
        "reply": f"{opportunity['title']}ね。よし、決まり。終わったあとに一言だけ聞くね。",
        "context": _basic_context(episode),
    }


def _selected_opportunity(
    episode: dict[str, Any], data_mode: str, store: JsonStore
) -> dict[str, Any] | None:
    selected = episode.get("selectedOpportunityId")
    try:
        source = load_opportunities(data_mode)
    except Exception:
        source = {"opportunities": []}
    opportunity = next(
        (item for item in source.get("opportunities", []) if item.get("id") == selected),
        None,
    )
    if opportunity is not None or data_mode != "live":
        return opportunity
    try:
        from osekkai_scheduler import load_event_mesh

        selected_event_id = episode.get("selectedEventId")
        event = next(
            (
                item
                for item in load_event_mesh(store=store)["events"]
                if item.get("id") == selected_event_id
            ),
            None,
        )
        return event if isinstance(event, dict) else None
    except Exception:
        return None


def handle_check_in_unlocked(
    store: JsonStore,
    user_id: str,
    profile: dict[str, Any],
    message: str,
    now: datetime,
    data_mode: str,
    *,
    remember: bool,
    understood_frictions: list[str] | None = None,
    friction_origin: str = "explicit",
    friction_confidence: float = 1.0,
) -> dict[str, Any]:
    episode = _latest_open_episode(store, user_id, now)
    if episode is None or episode.get("state") != "check_in_due":
        raise ContractError("check-in is not due")
    if parse_datetime(episode["checkInDueAt"]) > now:
        raise ContractError("check-in cannot be recorded before the event ends")
    opportunity = _selected_opportunity(episode, data_mode, store)
    if isinstance(opportunity, dict) and opportunity.get("status") in {"canceled", "postponed"}:
        episode = transition_episode(
            episode,
            "getting_to_know",
            now,
            checkInCompletedAt=now.isoformat(),
            closedAt=now.isoformat(),
        )
        _save_episode(store, user_id, episode)
        return {
            "episode": episode,
            "profile": profile,
            "frictionDelta": [],
            "reply": "中止・延期になってたんだね。参加できたことには数えないよ。",
            "context": _basic_context(episode),
        }

    frictions = list(
        dict.fromkeys([*classify_participation_frictions(message), *(understood_frictions or [])])
    )
    not_attended = _contains(message, NOT_ATTENDED_MARKERS)
    if (
        not_attended
        and not frictions
        and not _contains(message, ATTENDANCE_REASON_MARKERS)
    ):
        return {
            "episode": episode,
            "profile": profile,
            "frictionDelta": [],
            "reply": "そっか、行けなかったんだね。理由は決めつけないよ。予定、距離、気分や不安のどれか、一つだけ近いものはある？",
            "context": _basic_context(episode, quick_replies=NOT_ATTENDED_QUICK_REPLIES),
        }

    evidence_ids: list[str] = []
    if remember and frictions:
        profile, evidence_ids = apply_participation_frictions(
            profile,
            frictions,
            origin=friction_origin,
            reference_type="feedback",
            reference_id=str(uuid.uuid4()),
            evidence_text="Event後の本人Feedback",
            confidence=friction_confidence,
            now=now,
        )
    if remember and _contains(message, POSITIVE_CHECK_IN_MARKERS):
        categories = opportunity.get("categories", []) if isinstance(opportunity, dict) else []
        delta = {"revisitPreference": "interested"}
        if isinstance(categories, list) and categories:
            delta["preferredCategories"] = categories[:10]
        profile = apply_inferred_delta(
            profile,
            delta,
            0.9,
            "Event後にまた参加したいと回答",
            now,
        )
    if remember and (frictions or _contains(message, POSITIVE_CHECK_IN_MARKERS)):
        store.save_profile_unlocked(user_id, profile)
    episode["frictionEvidenceIds"] = sorted(
        set([*episode["frictionEvidenceIds"], *evidence_ids])
    )
    episode = transition_episode(
        episode,
        "getting_to_know",
        now,
        checkInCompletedAt=now.isoformat(),
        closedAt=now.isoformat(),
    )
    _save_episode(store, user_id, episode)
    if not_attended:
        reply = "教えてくれてありがとう。行けなかったことは失敗にしないよ。次はその負担を外して探すね。"
    elif frictions:
        reply = "そこがしんどかったんだね。次は同じ負担が少ない候補を先にするよ。"
    else:
        reply = "まあ、悪くなかったんだね。次に探す時、その感じをちゃんと使うよ。"
    return {
        "episode": episode,
        "profile": profile,
        "frictionDelta": frictions if remember else [],
        "reply": reply,
        "context": _basic_context(episode),
    }


def promote_due_check_ins_unlocked(
    store: JsonStore, user_id: str, now: datetime
) -> int:
    changed = 0
    for episode in store.list_conversation_episodes_unlocked(user_id):
        if episode.get("closedAt") is not None or episode.get("state") != "accepted":
            continue
        due_at = episode.get("checkInDueAt")
        if isinstance(due_at, str) and parse_datetime(due_at) <= now:
            _save_episode(
                store,
                user_id,
                transition_episode(episode, "check_in_due", now),
            )
            changed += 1
    return changed
