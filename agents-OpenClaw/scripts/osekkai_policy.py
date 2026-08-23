"""Guardrail-first, deterministic P0 Distance Policy."""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from osekkai_contracts import POLICY_VERSION, REASON_CODES, SCHEMA_VERSION, ContractError, validate_reason_codes
from osekkai_profile import effective_participation_frictions


JST = ZoneInfo("Asia/Tokyo")


def _parse_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ContractError("datetime must include timezone")
    return parsed.astimezone(JST)


def load_policy_config() -> dict[str, Any]:
    configured = os.environ.get("OSEKKAI_POLICY_PATH")
    path = Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parent.parent / "config" / "osekkai_policy.json"
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError("policy configuration could not be loaded") from exc
    if value.get("schemaVersion") != SCHEMA_VERSION or value.get("policyVersion") != POLICY_VERSION:
        raise ContractError("policy configuration version mismatch")
    configured_codes = value.get("reasonCodes")
    if not isinstance(configured_codes, list) or set(configured_codes) != REASON_CODES:
        raise ContractError("policy reason codes differ from the contract")
    weights = value.get("weights", {})
    if set(weights) != {
        "opportunityFit",
        "currentReceptivity",
        "trust",
        "feasibility",
        "burden",
        "intrusionRisk",
    }:
        raise ContractError("policy weights are invalid")
    if not 0 <= value.get("pushThreshold", -1) <= 1:
        raise ContractError("policy threshold is invalid")
    if not 2 <= value.get("maxRankedOpportunities", 0) <= 8:
        raise ContractError("policy maxRankedOpportunities must be between 2 and 8")
    if not 2 <= value.get("minimumLiveConnectionLevel", 0) <= 3:
        raise ContractError("policy minimumLiveConnectionLevel is invalid")
    live_weights = value.get("liveRankingWeights")
    if not isinstance(live_weights, dict) or set(live_weights) != {"connection", "personalFit", "adjacentInterest", "continuity", "feasibility"}:
        raise ContractError("policy liveRankingWeights are invalid")
    if abs(sum(float(weight) for weight in live_weights.values()) - 1.0) > 0.0001:
        raise ContractError("policy liveRankingWeights must sum to 1")
    adjacent = value.get("adjacentCategories")
    if not isinstance(adjacent, dict) or not all(
        isinstance(key, str) and isinstance(items, list) and all(isinstance(item, str) for item in items)
        for key, items in adjacent.items()
    ):
        raise ContractError("policy adjacentCategories are invalid")
    trigger = value.get("conversationTrigger")
    expected_trigger_fields = {
        "horizonDays", "activityStart", "activityEnd", "longFreeWindowMinutes",
        "minimumLongFreeWindows", "maximumBusyOccupancyPercent", "minimumCandidates",
        "checkInDelayMinutes", "inferredFrictionHalfLifeDays", "adjustedTravelMinutes",
        "adjustedDurationMinutes", "adjustedGroupSize", "adjustedBudgetYen",
    }
    if not isinstance(trigger, dict) or set(trigger) != expected_trigger_fields:
        raise ContractError("policy conversationTrigger is invalid")
    if not 1 <= trigger["horizonDays"] <= 30:
        raise ContractError("conversation trigger horizon is invalid")
    for key in ("activityStart", "activityEnd"):
        try:
            time.fromisoformat(trigger[key])
        except (TypeError, ValueError) as exc:
            raise ContractError("conversation activity time is invalid") from exc
    for key in (
        "longFreeWindowMinutes", "minimumLongFreeWindows", "minimumCandidates",
        "checkInDelayMinutes", "inferredFrictionHalfLifeDays", "adjustedTravelMinutes",
        "adjustedDurationMinutes", "adjustedGroupSize", "adjustedBudgetYen",
    ):
        if isinstance(trigger[key], bool) or not isinstance(trigger[key], int) or trigger[key] < 0:
            raise ContractError(f"conversation trigger {key} is invalid")
    if not 0 <= trigger["maximumBusyOccupancyPercent"] <= 100:
        raise ContractError("conversation busy occupancy threshold is invalid")
    return value


def _is_quiet_hour(profile: dict[str, Any], now: datetime) -> bool:
    quiet = profile.get("quietHours", {})
    start = time.fromisoformat(quiet.get("start", "21:00"))
    end = time.fromisoformat(quiet.get("end", "08:00"))
    local_time = now.astimezone(JST).time().replace(tzinfo=None)
    if start == end:
        return True
    if start < end:
        return start <= local_time < end
    return local_time >= start or local_time < end


def _weekly_push_count(episodes: list[dict[str, Any]], now: datetime) -> int:
    local_now = now.astimezone(JST)
    week_start = (local_now - timedelta(days=local_now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    count = 0
    for episode in episodes:
        if not episode.get("shouldPush"):
            continue
        pushed_at = episode.get("pushedAt")
        if not pushed_at:
            continue
        try:
            parsed = _parse_datetime(pushed_at)
        except (ValueError, ContractError):
            continue
        if week_start <= parsed <= local_now:
            count += 1
    return count


def _source_is_eligible(opportunity: dict[str, Any], data_mode: str) -> bool:
    if opportunity.get("dataMode") != data_mode:
        return False
    status = opportunity.get("verificationStatus")
    if data_mode == "demo":
        return status == "source_snapshot" and bool(opportunity.get("checksum")) and bool(opportunity.get("sourceUrl"))
    return status in {"source_verified", "organizer_verified"}


def _eligible_windows(freebusy: dict[str, Any], config: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    minimum = config["minimumFreeWindowMinutes"]
    windows = []
    for window in freebusy.get("freeWindows", []):
        try:
            start = _parse_datetime(window["start"])
            end = _parse_datetime(window["end"])
        except (KeyError, ValueError, ContractError):
            continue
        if end <= now or end <= start or int(window.get("durationMinutes", 0)) < minimum:
            continue
        windows.append(window)
    return windows


def _battery_band(profile: dict[str, Any], config: dict[str, Any]) -> str:
    battery = profile.get("socialBattery")
    if battery is None:
        return "unknown"
    if battery <= config["batteryBands"]["lowMax"]:
        return "low"
    if battery <= config["batteryBands"]["mediumMax"]:
        return "medium"
    return "high"


def _fits_window(opportunity: dict[str, Any], windows: list[dict[str, Any]]) -> tuple[bool, dict[str, Any] | None]:
    try:
        event_start = _parse_datetime(opportunity["startsAt"])
        event_end = _parse_datetime(opportunity["endsAt"])
        travel = int(opportunity["travelEstimate"]["minutes"])
    except (KeyError, TypeError, ValueError, ContractError):
        return False, None
    for window in windows:
        start = _parse_datetime(window["start"])
        end = _parse_datetime(window["end"])
        if opportunity.get("flexibleVisit"):
            visit = int(opportunity.get("visitDurationMinutes", 0))
            if visit <= 0:
                continue
            proposed_start = max(start + timedelta(minutes=travel), event_start)
            proposed_end = proposed_start + timedelta(minutes=visit)
            if proposed_end + timedelta(minutes=travel) <= min(end, event_end):
                selected = copy.deepcopy(window)
                selected["suggestedVisitStart"] = proposed_start.isoformat()
                selected["suggestedVisitEnd"] = proposed_end.isoformat()
                return True, selected
        elif event_start - timedelta(minutes=travel) >= start and event_end + timedelta(minutes=travel) <= end:
            return True, copy.deepcopy(window)
    return False, None


def filter_candidates(
    profile: dict[str, Any],
    windows: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    config: dict[str, Any],
    now: datetime,
    data_mode: str,
) -> tuple[list[dict[str, Any]], dict[str, list[str]], dict[str, dict[str, Any]]]:
    band = _battery_band(profile, config)
    effective_intensity = min(
        int(profile.get("maxSocialIntensity", 0)),
        int(config["effectiveIntensityCaps"][band]),
    )
    eligible: list[dict[str, Any]] = []
    exclusions: dict[str, list[str]] = {}
    matched_windows: dict[str, dict[str, Any]] = {}
    avoided = set(profile.get("avoidedCategories", []))
    for candidate in opportunities:
        candidate_id = str(candidate.get("id", "invalid"))
        reasons: list[str] = []
        required = ("id", "title", "startsAt", "endsAt", "address", "provider", "sourceUrl", "fieldProvenance")
        if any(not candidate.get(field) for field in required) or not _source_is_eligible(candidate, data_mode):
            reasons.append("INVALID_SOURCE")
        try:
            if _parse_datetime(candidate.get("endsAt", "")) < now:
                reasons.append("INVALID_SOURCE")
        except (ValueError, ContractError):
            if "INVALID_SOURCE" not in reasons:
                reasons.append("INVALID_SOURCE")
        fits, matched = _fits_window(candidate, windows)
        if not fits:
            reasons.append("OUTSIDE_FREE_WINDOW")
        travel = candidate.get("travelEstimate", {}).get("minutes")
        if isinstance(travel, bool) or not isinstance(travel, int) or travel > profile.get("maxTravelMinutes", 0):
            reasons.append("TRAVEL_LIMIT")
        price = candidate.get("priceYen")
        if isinstance(price, bool) or (price is not None and not isinstance(price, int)):
            reasons.append("INVALID_SOURCE")
        elif isinstance(price, int) and price > profile.get("maxBudgetYen", 0):
            reasons.append("OVER_BUDGET")
        intensity = candidate.get("socialIntensity")
        if isinstance(intensity, bool) or not isinstance(intensity, int) or intensity > effective_intensity:
            reasons.append("SOCIAL_INTENSITY_LIMIT")
        categories = set(candidate.get("categories", []))
        if avoided & categories:
            reasons.append("SOCIAL_INTENSITY_LIMIT")
        if data_mode == "live":
            connection = candidate.get("connectionEvidence", {})
            level = connection.get("connectionLevel") if isinstance(connection, dict) else None
            if not isinstance(level, int) or level < int(config["minimumLiveConnectionLevel"]):
                reasons.append("CONNECTION_LEVEL")
            if candidate.get("status") != "scheduled" or candidate.get("registrationStatus") not in {"open", "not_required"}:
                reasons.append("REGISTRATION_UNAVAILABLE")
        reasons = list(dict.fromkeys(reasons))
        if reasons:
            exclusions[candidate_id] = reasons
        else:
            eligible.append(copy.deepcopy(candidate))
            if matched:
                matched_windows[candidate_id] = matched
    return eligible, exclusions, matched_windows


def _score_candidate(
    profile: dict[str, Any], opportunity: dict[str, Any], config: dict[str, Any]
) -> tuple[float, dict[str, float]]:
    preferred = set(profile.get("preferredCategories", []))
    categories = set(opportunity.get("categories", []))
    fit = 0.65
    if opportunity.get("soloFriendly"):
        fit += 0.1
    if opportunity.get("conversationRequired") in {"none", "low"}:
        fit += 0.1
    if preferred and preferred & categories:
        fit += 0.1
    fit = min(fit, 1.0)
    signals = profile.get("currentSignals", {})
    receptivity = signals.get("currentReceptivity")
    if not isinstance(receptivity, (int, float)):
        receptivity = 0.5
    cadence = profile.get("inferredPreferences", {}).get("pushCadenceDelta", {}).get("value", 0)
    if isinstance(cadence, (int, float)) and cadence > 0:
        receptivity = min(1.0, receptivity + 0.1)
    trust = float(opportunity.get("sourceTrust", 0.0))
    max_travel = max(int(profile.get("maxTravelMinutes", 0)), 1)
    travel = int(opportunity.get("travelEstimate", {}).get("minutes", max_travel))
    max_budget = max(int(profile.get("maxBudgetYen", 0)), 1)
    raw_price = opportunity.get("priceYen")
    price = raw_price if isinstance(raw_price, int) and not isinstance(raw_price, bool) else max_budget
    feasibility = max(0.0, 1.0 - 0.35 * (travel / max_travel) - 0.25 * (price / max_budget))
    intensity = int(opportunity.get("socialIntensity", 5))
    burden = min(1.0, 0.5 * (intensity / 5.0) + 0.5 * (travel / max_travel))
    battery = profile.get("socialBattery")
    intrusion = 0.35 if isinstance(battery, int) and battery <= 30 else 0.15
    intrusion = min(1.0, intrusion + min(int(profile.get("rejectionStreak", 0)), 3) * 0.1)
    components = {
        "opportunityFit": round(fit, 4),
        "currentReceptivity": round(float(receptivity), 4),
        "trust": round(trust, 4),
        "feasibility": round(feasibility, 4),
        "burden": round(burden, 4),
        "intrusionRisk": round(intrusion, 4),
    }
    score = sum(config["weights"][key] * value for key, value in components.items())
    return round(score, 4), components


def _live_score_candidate(
    profile: dict[str, Any], opportunity: dict[str, Any], config: dict[str, Any]
) -> tuple[float, dict[str, float], dict[str, bool]]:
    preferred = {str(value).lower() for value in profile.get("preferredCategories", [])}
    categories = {str(value).lower() for value in opportunity.get("categories", [])}
    exact = bool(preferred & categories)
    adjacent_values = {
        adjacent.lower()
        for preference in preferred
        for adjacent in config["adjacentCategories"].get(preference, [])
    }
    adjacent = bool(categories & adjacent_values) and not exact
    connection_value = opportunity.get("connectionEvidence", {})
    level = int(connection_value.get("connectionLevel", 0))
    connection = level / 3.0
    future_count = int(connection_value.get("futureOccurrenceCount", 0))
    continuity = 1.0 if future_count > 0 else (0.65 if opportunity.get("recurring") else 0.2)
    personal_fit = 1.0 if exact else (0.7 if adjacent else (0.45 if not preferred else 0.25))
    adjacent_fit = 1.0 if adjacent else (0.45 if exact else 0.2)
    max_travel = max(int(profile.get("maxTravelMinutes", 0)), 1)
    travel = int(opportunity.get("travelEstimate", {}).get("minutes", max_travel))
    max_budget = max(int(profile.get("maxBudgetYen", 0)), 1)
    raw_price = opportunity.get("priceYen")
    price = raw_price if isinstance(raw_price, int) and not isinstance(raw_price, bool) else max_budget
    intensity = int(opportunity.get("socialIntensity", 5))
    feasibility = max(0.0, 1.0 - 0.35 * (travel / max_travel) - 0.25 * (price / max_budget) - 0.15 * (intensity / 5))
    rejection_penalty = min(0.2, int(profile.get("rejectionStreak", 0)) * 0.05)
    components = {
        "connection": round(connection, 4),
        "personalFit": round(personal_fit, 4),
        "adjacentInterest": round(adjacent_fit, 4),
        "continuity": round(continuity, 4),
        "feasibility": round(feasibility, 4),
    }
    score = sum(float(config["liveRankingWeights"][key]) * value for key, value in components.items()) - rejection_penalty
    return round(max(-1.0, min(1.0, score)), 4), components, {"exact": exact, "adjacent": adjacent}


def _recommendation_reasons(
    profile: dict[str, Any], opportunity: dict[str, Any], fit_flags: dict[str, bool]
) -> list[dict[str, Any]]:
    connection = opportunity["connectionEvidence"]
    evidence = connection.get("evidence", [])
    first_evidence = evidence[0] if evidence else None
    reasons: list[dict[str, Any]] = []
    if first_evidence:
        reasons.append(
            {
                "code": "connection",
                "text": first_evidence["text"],
                "evidenceUrl": first_evidence["url"],
                "classification": first_evidence["classification"],
            }
        )
    continuity_evidence = next((item for item in evidence if item.get("kind") in {"future_occurrence", "recurrence", "community_path"}), None)
    if continuity_evidence:
        reasons.append(
            {
                "code": "continuity",
                "text": continuity_evidence["text"],
                "evidenceUrl": continuity_evidence["url"],
                "classification": continuity_evidence["classification"],
            }
        )
    preferred = ", ".join(str(value) for value in profile.get("preferredCategories", [])[:3]) or "これまでの会話"
    if fit_flags["adjacent"]:
        reasons.append(
            {
                "code": "adjacent_interest",
                "text": f"{preferred}から少しずらした、会話の入口が作りやすい隣接ジャンルです。",
                "evidenceUrl": None,
                "classification": "ai_derived",
            }
        )
    elif fit_flags["exact"]:
        reasons.append(
            {
                "code": "personal_fit",
                "text": f"本人が話した好み（{preferred}）と一致します。",
                "evidenceUrl": None,
                "classification": "private_user_data",
            }
        )
    reasons.extend(
        [
            {
                "code": "calendar_fit",
                "text": "Google Calendarの空き時間に往復を含めて収まります。",
                "evidenceUrl": None,
                "classification": "private_user_data",
            },
            {
                "code": "travel_fit",
                "text": f"Google Routes実測で片道{opportunity['travelEstimate']['minutes']}分です。",
                "evidenceUrl": None,
                "classification": "private_user_data",
            },
        ]
    )
    return reasons


def _has_connection_fact(opportunity: dict[str, Any], *facts: str) -> bool:
    connection = opportunity.get("connectionEvidence")
    if not isinstance(connection, dict):
        return False
    if any(connection.get(name) == "yes" for name in facts):
        return True
    evidence = connection.get("evidence", [])
    return any(
        isinstance(item, dict) and item.get("kind") in set(facts)
        for item in evidence
    )


def _conversation_reason(
    opportunity: dict[str, Any], friction_types: set[str]
) -> dict[str, Any] | None:
    text: str | None = None
    if "first_time_anxiety" in friction_types and _has_connection_fact(
        opportunity, "beginnerFriendly", "soloFriendly", "beginner_friendly", "solo_friendly"
    ):
        text = "初参加・ひとり参加への案内がSourceで確認できる候補を優先しました。"
    elif friction_types & {"stranger_anxiety", "conversation_load"} and _has_connection_fact(
        opportunity, "groupWork", "sharedMeal", "structuredConversation", "group_work", "shared_meal", "structured_conversation"
    ):
        text = "知らない人との雑談だけに頼らず、共同活動や進行の根拠がある候補です。"
    elif "group_size" in friction_types and isinstance(opportunity.get("capacity"), int):
        text = f"Sourceで確認できた定員は{opportunity['capacity']}人です。"
    elif "travel_effort" in friction_types:
        text = f"移動負担を優先し、Google Routes実測{opportunity['travelEstimate']['minutes']}分で並べ直しました。"
    elif "time_commitment" in friction_types:
        text = "拘束時間を抑え、Calendarの空きへ往復込みで収まる候補を優先しました。"
    elif "cost" in friction_types and isinstance(opportunity.get("priceYen"), int):
        text = f"料金確認済みで、参加費は{opportunity['priceYen']:,}円です。"
    if text is None:
        return None
    return {
        "code": "personal_fit",
        "text": text,
        "evidenceUrl": opportunity.get("sourceUrl"),
        "classification": "private_user_data",
    }


def rank_conversation_candidates(
    profile: dict[str, Any],
    freebusy: dict[str, Any],
    opportunity_result: dict[str, Any],
    now: datetime,
    *,
    friction_types: set[str] | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rank full, source-backed cards for Chat without creating an intervention."""

    config = copy.deepcopy(config or load_policy_config())
    trigger = config["conversationTrigger"]
    config["minimumFreeWindowMinutes"] = trigger["longFreeWindowMinutes"]
    active = friction_types
    if active is None:
        active = set(
            effective_participation_frictions(
                profile,
                now,
                half_life_days=trigger["inferredFrictionHalfLifeDays"],
            )
        )
    adjusted_profile = copy.deepcopy(profile)
    if "travel_effort" in active:
        adjusted_profile["maxTravelMinutes"] = min(
            int(adjusted_profile.get("maxTravelMinutes", 240)),
            trigger["adjustedTravelMinutes"],
        )
    if "cost" in active:
        adjusted_profile["maxBudgetYen"] = min(
            int(adjusted_profile.get("maxBudgetYen", 1_000_000)),
            trigger["adjustedBudgetYen"],
        )

    data_mode = opportunity_result.get("dataMode", "demo")
    windows = _eligible_windows(freebusy, config, now)
    source_items = opportunity_result.get("opportunities", [])
    eligible, _exclusions, _matched = filter_candidates(
        adjusted_profile, windows, source_items, config, now, data_mode
    )
    narrowed: list[dict[str, Any]] = []
    for opportunity in eligible:
        if "group_size" in active:
            capacity = opportunity.get("capacity")
            if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity > trigger["adjustedGroupSize"]:
                continue
        if "time_commitment" in active:
            try:
                duration = int((_parse_datetime(opportunity["endsAt"]) - _parse_datetime(opportunity["startsAt"])).total_seconds() // 60)
            except (KeyError, TypeError, ValueError, ContractError):
                continue
            if duration > trigger["adjustedDurationMinutes"]:
                continue
        if "cost" in active and not isinstance(opportunity.get("priceYen"), int):
            continue
        narrowed.append(opportunity)

    scored: list[tuple[dict[str, Any], float, dict[str, bool]]] = []
    for opportunity in narrowed:
        if data_mode == "live":
            score, _components, fit_flags = _live_score_candidate(adjusted_profile, opportunity, config)
        else:
            score, _components = _score_candidate(adjusted_profile, opportunity, config)
            fit_flags = {"exact": False, "adjacent": False}
        adjustment = 0.0
        if "first_time_anxiety" in active:
            adjustment += 0.15 if _has_connection_fact(
                opportunity, "beginnerFriendly", "soloFriendly", "beginner_friendly", "solo_friendly"
            ) else -0.08
        if active & {"stranger_anxiety", "conversation_load"}:
            adjustment += 0.14 if _has_connection_fact(
                opportunity, "groupWork", "sharedMeal", "structuredConversation", "group_work", "shared_meal", "structured_conversation"
            ) else -0.08
            if opportunity.get("conversationRequired") == "low":
                adjustment += 0.05
        scored.append((opportunity, round(max(-1.0, min(1.0, score + adjustment)), 4), fit_flags))
    scored.sort(
        key=lambda entry: (
            -entry[1],
            -float(entry[0].get("sourceTrust", 0)),
            entry[0].get("startsAt", ""),
            int(entry[0].get("travelEstimate", {}).get("minutes", 10**9)),
            entry[0].get("id", ""),
        )
    )

    recommendations: list[dict[str, Any]] = []
    for rank, (opportunity, _score, fit_flags) in enumerate(
        scored[: int(config["maxRankedOpportunities"])], start=1
    ):
        if data_mode == "live" and isinstance(opportunity.get("connectionEvidence"), dict):
            reasons = _recommendation_reasons(adjusted_profile, opportunity, fit_flags)
        else:
            reasons = [
                {
                    "code": "personal_fit",
                    "text": "話した好みと、確認できた参加条件に合う候補です。",
                    "evidenceUrl": opportunity.get("sourceUrl"),
                    "classification": "private_user_data",
                }
            ]
        friction_reason = _conversation_reason(opportunity, active)
        if friction_reason is not None:
            reasons = [friction_reason, *reasons]
        recommendations.append(
            {
                "rank": rank,
                "opportunity": copy.deepcopy(opportunity),
                "recommendationReasons": reasons[:6],
            }
        )
    return recommendations


def _guardrail_reason(
    profile: dict[str, Any],
    windows: list[dict[str, Any]],
    source_candidates: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
    now: datetime,
) -> str | None:
    if not profile.get("pushConsent"):
        return "NO_PUSH_CONSENT"
    if _is_quiet_hour(profile, now):
        return "QUIET_HOURS"
    cooldown = profile.get("cooldownUntil")
    if cooldown and _parse_datetime(cooldown) > now:
        return "COOLDOWN_ACTIVE"
    if _weekly_push_count(episodes, now) >= int(profile.get("maxPushesPerWeek", 0)):
        return "WEEKLY_LIMIT_REACHED"
    pause_until = profile.get("pauseUntil")
    if pause_until and _parse_datetime(pause_until) > now:
        return "EXPLICIT_PAUSE"
    signals = profile.get("currentSignals", {})
    if signals.get("interventionHint") == "do_not_push":
        if signals.get("safety", {}).get("requiresHumanSupport"):
            return "HUMAN_SUPPORT_REQUIRED"
        return "EXPLICIT_NO_ACTION"
    if signals.get("safety", {}).get("requiresHumanSupport"):
        return "HUMAN_SUPPORT_REQUIRED"
    if not windows:
        return "NO_FREE_WINDOW"
    if not source_candidates:
        return "NO_VERIFIED_OPPORTUNITY"
    return None


def evaluate_policy(
    profile: dict[str, Any],
    freebusy: dict[str, Any],
    opportunity_result: dict[str, Any],
    episodes: list[dict[str, Any]],
    now: datetime,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or load_policy_config()
    data_mode = opportunity_result.get("dataMode", "demo")
    opportunities = opportunity_result.get("opportunities", [])
    windows = _eligible_windows(freebusy, config, now)
    source_candidates = [item for item in opportunities if _source_is_eligible(item, data_mode)]
    guardrail = _guardrail_reason(profile, windows, source_candidates, episodes, now)
    base = {
        "schemaVersion": SCHEMA_VERSION,
        "policyVersion": config["policyVersion"],
        "decidedAt": now.isoformat(),
        "dataMode": data_mode,
        "tone": profile.get("preferredTone", "gentle"),
        "candidateIdsBeforeFilter": [str(item.get("id")) for item in opportunities],
        "candidateIdsAfterFilter": [],
        "exclusions": {},
        "selectedOpportunity": None,
        "selectedOpportunityId": None,
        "selectedFreeWindow": None,
        "score": None,
        "scoreComponents": None,
    }
    if data_mode == "live":
        base["rankedOpportunities"] = []
    if guardrail:
        base.update(
            {
                "decision": "do_not_push",
                "shouldPush": False,
                "reasonCodes": [guardrail],
                "message": None,
            }
        )
        return base

    eligible, exclusions, matched_windows = filter_candidates(
        profile, windows, opportunities, config, now, data_mode
    )
    base["candidateIdsAfterFilter"] = [item["id"] for item in eligible]
    base["exclusions"] = exclusions
    if not eligible:
        base.update(
            {
                "decision": "do_not_push",
                "shouldPush": False,
                "reasonCodes": ["NO_VERIFIED_OPPORTUNITY"],
                "message": None,
            }
        )
        return base

    scored = []
    for item in eligible:
        if data_mode == "live":
            score, components, fit_flags = _live_score_candidate(profile, item, config)
        else:
            score, components = _score_candidate(profile, item, config)
            fit_flags = {"exact": False, "adjacent": False}
        scored.append((item, score, components, fit_flags))
    scored.sort(
        key=lambda entry: (
            -entry[1],
            -float(entry[0].get("sourceTrust", 0)),
            entry[0].get("startsAt", ""),
            int(entry[0].get("travelEstimate", {}).get("minutes", 10**9)),
            entry[0].get("id", ""),
        )
    )
    if data_mode == "live":
        shortlist = scored[: int(config["maxRankedOpportunities"])]
        base["rankedOpportunities"] = [
            {
                "rank": index,
                "score": item_score,
                "opportunityId": item["id"],
                "recommendationReasons": _recommendation_reasons(profile, item, fit_flags),
                "exclusionReasons": [],
            }
            for index, (item, item_score, _components, fit_flags) in enumerate(shortlist, start=1)
        ]
    selected, score, components, _fit_flags = scored[0]
    base["score"] = score
    base["scoreComponents"] = components
    if score < float(config["pushThreshold"]):
        base.update(
            {
                "decision": "do_not_push",
                "shouldPush": False,
                "reasonCodes": ["SCORE_BELOW_THRESHOLD"],
                "message": None,
            }
        )
        return base

    reasons = ["FREE_WINDOW_AVAILABLE"]
    if profile.get("socialBattery") is not None and profile["socialBattery"] <= config["batteryBands"]["lowMax"]:
        reasons.append("LOW_SOCIAL_BATTERY")
    if selected.get("conversationRequired") in {"none", "low"}:
        reasons.append("LOW_CONVERSATION_REQUIREMENT")
    reasons.append("WITHIN_TRAVEL_LIMIT")
    selected_price = selected.get("priceYen")
    if isinstance(selected_price, int) and not isinstance(selected_price, bool):
        reasons.append("UNDER_BUDGET")
    validate_reason_codes(reasons)
    travel = selected["travelEstimate"]["minutes"]
    if data_mode == "live":
        preference = str(profile.get("preferredCategories", ["それ"])[0]) if profile.get("preferredCategories") else "それ"
        continuity = "次もある" if selected.get("connectionEvidence", {}).get("futureOccurrenceCount", 0) else "少人数の"
        solo = "ひとり参加OKで、" if selected.get("connectionEvidence", {}).get("soloFriendly") == "yes" else ""
        message = (
            f"あんた、この前{preference}好きって言うてたやろ。片道{travel}分のとこで{continuity}「{selected['title']}」あるで。"
            f"{solo}合わんかったら次は別のにしたらええ。"
        )
        decision = "suggest_small_role" if selected.get("connectionEvidence", {}).get("roleAvailable") == "yes" else "suggest_light_social"
    else:
        message = (
            f"会話をほとんどしなくても見られる「{selected['title']}」があるわよ。"
            f"移動はデモ上で徒歩{travel}分。短く見るだけでもどう？"
        )
        decision = "suggest_solo_place" if selected.get("conversationRequired") == "none" else "suggest_light_social"
    base.update(
        {
            "decision": decision,
            "shouldPush": True,
            "reasonCodes": reasons,
            "message": message,
            "selectedOpportunity": copy.deepcopy(selected),
            "selectedOpportunityId": selected["id"],
            "selectedFreeWindow": matched_windows.get(selected["id"]),
        }
    )
    return base
