"""Build a deterministic, grounded plan before any natural-language rendering."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from osekkai_contracts import SCHEMA_VERSION, validate_schema


STATE_TO_ACT = {
    "getting_to_know": "learn_preference",
    "calendar_sparse": "present_shortlist",
    "shortlist_shown": "present_shortlist",
    "friction_probe": "probe_friction",
    "adjusted_shortlist": "present_adjusted_shortlist",
    "accepted": "confirm_selection",
    "check_in_due": "check_in",
    "cooldown": "cooldown",
    "safety_handoff": "safety_handoff",
}

ACT_GOALS = {
    "learn_preference": "本人の興味か、参加するときのひっかかりを一つだけ自然に聞く",
    "clarify": "決めつけず、いま必要な確認を一つだけ聞く",
    "present_shortlist": "確認済みの複数候補があることと、本人に合う理由を短く伝える",
    "probe_friction": "候補を断った理由を責めず、一番大きいひっかかりを一つだけ聞く",
    "present_adjusted_shortlist": "聞いたひっかかりを反映して一度だけ並べ直したことを伝える",
    "confirm_selection": "選択を受け止め、イベント後に短く聞くことだけ伝える",
    "check_in": "参加できたかを決めつけず、感想か行けなかった理由を一つだけ聞く",
    "cooldown": "追いかけないことを短く伝え、罪悪感を与えない",
    "safety_handoff": "イベント推薦を止め、人の支えにつながる案内をそのまま伝える",
    "continue_conversation": "現在の会話状態に沿って次の一歩を一つだけ示す",
}

PROHIBITED_CLAIMS = [
    "絶対に楽しい",
    "孤独であるという診断",
    "一人参加OK（根拠なし）",
    "初心者歓迎（根拠なし）",
    "途中退出OK（根拠なし）",
    "次回あり（根拠なし）",
    "募集人数や残席（根拠なし）",
    "Calendar予定のタイトル・内容",
]


def _event_facts(opportunity: dict[str, Any]) -> list[str]:
    event_id = str(opportunity.get("id", ""))
    facts = [
        f"eventId={event_id}",
        f"名称={opportunity.get('title', '')}",
        f"開始={opportunity.get('startsAt', '')}",
        f"終了={opportunity.get('endsAt', '')}",
        f"場所={opportunity.get('address', '')}",
        f"Provider={opportunity.get('provider', '')}",
    ]
    price = opportunity.get("priceYen")
    if isinstance(price, int):
        facts.append(f"料金={price}円")
    travel = opportunity.get("travelEstimate")
    if isinstance(travel, dict) and isinstance(travel.get("minutes"), int):
        source = travel.get("source")
        mode = travel.get("mode")
        facts.append(f"移動={mode}で{travel['minutes']}分（{source}）")
    if opportunity.get("soloFriendly") is True:
        facts.append("一人参加しやすい根拠あり")
    if opportunity.get("recurring") is True:
        facts.append("継続開催の根拠あり")
    if isinstance(opportunity.get("capacity"), int):
        facts.append(f"定員={opportunity['capacity']}人")
    if isinstance(opportunity.get("participants"), int):
        facts.append(f"参加者数={opportunity['participants']}人")
    if isinstance(opportunity.get("registrationStatus"), str):
        facts.append(f"募集状態={opportunity['registrationStatus']}")
    return [fact[:300] for fact in facts if not fact.endswith("=")]


def build_dialogue_plan(
    conversation: dict[str, Any],
    *,
    understanding: dict[str, Any] | None,
    memories: list[dict[str, Any]],
    community_facts: list[str] | None = None,
) -> dict[str, Any]:
    fallback = str(conversation.get("reply", "")).strip()
    context = conversation.get("context") if isinstance(conversation.get("context"), dict) else {}
    state = str(context.get("state", "getting_to_know"))
    act = STATE_TO_ACT.get(state, "continue_conversation")
    if understanding and understanding.get("needsClarification") and state == "getting_to_know":
        act = "clarify"
    recommendations = [
        item for item in context.get("recommendations", []) if isinstance(item, dict)
    ][:3]
    opportunities = [
        item.get("opportunity") for item in recommendations if isinstance(item.get("opportunity"), dict)
    ]
    allowed_event_ids = [str(item["id"]) for item in opportunities if isinstance(item.get("id"), str)]
    allowed_facts = [fact for opportunity in opportunities for fact in _event_facts(opportunity)]
    # Community-directory facts are Raw Open Data (unverified activity/dates), not Live
    # Provider events, so they are appended as plain facts the renderer may mention, never
    # forced into mustMention and never given an eventId the renderer could treat as bookable.
    if community_facts:
        allowed_facts.extend(str(fact)[:300] for fact in community_facts if str(fact).strip())
    must_mention: list[str] = []
    notice = context.get("notice")
    if isinstance(notice, str) and notice.strip():
        must_mention.append(notice.strip()[:240])
    if recommendations:
        must_mention.append(f"募集状態と情報源を確認した候補が{len(recommendations)}件ある")
    if state == "cooldown":
        must_mention.append("今日はこれ以上候補を追加しない")
    if state == "safety_handoff":
        must_mention.append("イベント推薦より人の支えを優先する")
    question_budget = 1 if act in {
        "learn_preference", "clarify", "present_shortlist", "probe_friction",
        "present_adjusted_shortlist", "check_in", "continue_conversation",
    } else 0
    relevant_memory_ids = [
        str(note["id"])
        for note in memories[:5]
        if isinstance(note, dict) and isinstance(note.get("id"), str)
    ]
    plan = {
        "schemaVersion": SCHEMA_VERSION,
        "dialogueAct": act,
        "goal": ACT_GOALS[act],
        "mustMention": list(dict.fromkeys(must_mention))[:6],
        "allowedEventIds": list(dict.fromkeys(allowed_event_ids))[:3],
        "allowedEventFacts": list(dict.fromkeys(allowed_facts))[:30],
        "relevantMemoryIds": list(dict.fromkeys(relevant_memory_ids))[:5],
        "prohibitedClaims": PROHIBITED_CLAIMS,
        "questionBudget": question_budget,
        "tone": "casual_gentle",
        "fallbackReply": fallback,
    }
    validate_schema(plan, "dialogue-plan.schema.json")
    return plan
