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
        if isinstance(price, bool) or not isinstance(price, int) or price > profile.get("maxBudgetYen", 0):
            reasons.append("OVER_BUDGET")
        intensity = candidate.get("socialIntensity")
        if isinstance(intensity, bool) or not isinstance(intensity, int) or intensity > effective_intensity:
            reasons.append("SOCIAL_INTENSITY_LIMIT")
        categories = set(candidate.get("categories", []))
        if avoided & categories:
            reasons.append("SOCIAL_INTENSITY_LIMIT")
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
    price = int(opportunity.get("priceYen", max_budget))
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
        score, components = _score_candidate(profile, item, config)
        scored.append((item, score, components))
    scored.sort(
        key=lambda entry: (
            -entry[1],
            -float(entry[0].get("sourceTrust", 0)),
            entry[0].get("startsAt", ""),
            int(entry[0].get("travelEstimate", {}).get("minutes", 10**9)),
            entry[0].get("id", ""),
        )
    )
    selected, score, components = scored[0]
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
    reasons.extend(["WITHIN_TRAVEL_LIMIT", "UNDER_BUDGET"])
    validate_reason_codes(reasons)
    travel = selected["travelEstimate"]["minutes"]
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

