"""Calendar-sparse trigger and privacy-minimal Chat recommendation context."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from osekkai_contracts import ContractError
from osekkai_opportunity_sync import load_opportunities
from osekkai_policy import load_policy_config, rank_conversation_candidates
from osekkai_profile import parse_datetime
from osekkai_scheduler import sync_before_push
from osekkai_store import JsonStore


JST = ZoneInfo("Asia/Tokyo")


def _activity_segments(
    start: datetime,
    end: datetime,
    *,
    activity_start: time,
    activity_end: time,
) -> list[tuple[datetime, datetime]]:
    if end <= start:
        return []
    segments: list[tuple[datetime, datetime]] = []
    day = start.astimezone(JST).date()
    final_day = end.astimezone(JST).date()
    while day <= final_day:
        segment_start = datetime.combine(day, activity_start, JST)
        segment_end = datetime.combine(day, activity_end, JST)
        clipped_start = max(segment_start, start.astimezone(JST))
        clipped_end = min(segment_end, end.astimezone(JST))
        if clipped_end > clipped_start:
            segments.append((clipped_start, clipped_end))
        day += timedelta(days=1)
    return segments


def analyze_calendar_sparsity(
    freebusy: dict[str, Any],
    now: datetime,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize only aggregate availability; never retain Busy details."""

    config = config or load_policy_config()
    trigger = config["conversationTrigger"]
    activity_start = time.fromisoformat(trigger["activityStart"])
    activity_end = time.fromisoformat(trigger["activityEnd"])
    local_now = now.astimezone(JST)
    horizon_end = local_now + timedelta(days=trigger["horizonDays"])
    total_segments = _activity_segments(
        local_now,
        horizon_end,
        activity_start=activity_start,
        activity_end=activity_end,
    )
    total_minutes = sum(int((end - start).total_seconds() // 60) for start, end in total_segments)
    if total_minutes <= 0:
        raise ContractError("conversation activity window is empty")

    clipped: list[tuple[datetime, datetime]] = []
    for window in freebusy.get("freeWindows", []):
        if not isinstance(window, dict):
            raise ContractError("FreeBusy window is malformed")
        try:
            start = max(local_now, parse_datetime(window["start"]))
            end = min(horizon_end, parse_datetime(window["end"]))
        except (KeyError, TypeError, ValueError, ContractError) as exc:
            raise ContractError("FreeBusy window is malformed") from exc
        clipped.extend(
            _activity_segments(
                start,
                end,
                activity_start=activity_start,
                activity_end=activity_end,
            )
        )

    clipped.sort(key=lambda value: value[0])
    merged: list[tuple[datetime, datetime]] = []
    for start, end in clipped:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    durations = [int((end - start).total_seconds() // 60) for start, end in merged]
    free_minutes = min(total_minutes, sum(durations))
    long_count = sum(1 for duration in durations if duration >= trigger["longFreeWindowMinutes"])
    busy_percent = round(max(0.0, min(100.0, 100 * (1 - free_minutes / total_minutes))), 1)
    sparse = (
        long_count >= trigger["minimumLongFreeWindows"]
        or busy_percent < trigger["maximumBusyOccupancyPercent"]
    )
    source = freebusy.get("source", {})
    source_type = source.get("type") if isinstance(source, dict) else None
    if source_type not in {"google_freebusy", "synthetic_demo"}:
        raise ContractError("FreeBusy source is invalid")
    return {
        "isSparse": sparse,
        "summary": {
            "source": source_type,
            "generatedAt": freebusy["generatedAt"],
            "longFreeWindowCount": long_count,
            "busyOccupancyPercent": busy_percent,
        },
    }


def _quiet_hour(profile: dict[str, Any], now: datetime) -> bool:
    quiet = profile.get("quietHours", {})
    start = time.fromisoformat(str(quiet.get("start", "21:00")))
    end = time.fromisoformat(str(quiet.get("end", "08:00")))
    current = now.astimezone(JST).time().replace(tzinfo=None)
    if start == end:
        return True
    return start <= current < end if start < end else current >= start or current < end


def _pushed_this_week(episodes: list[dict[str, Any]], now: datetime) -> int:
    local_now = now.astimezone(JST)
    week_start = (local_now - timedelta(days=local_now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    count = 0
    for episode in episodes:
        is_calendar_trigger = episode.get("trigger") == "calendar_sparse"
        pushed = episode.get("createdAt") if is_calendar_trigger else episode.get("pushedAt")
        if not (episode.get("shouldPush") or is_calendar_trigger) or not isinstance(pushed, str):
            continue
        try:
            if week_start <= parse_datetime(pushed) <= local_now:
                count += 1
        except (ContractError, ValueError):
            continue
    return count


def proactive_trigger_allowed(
    profile: dict[str, Any],
    intervention_episodes: list[dict[str, Any]],
    now: datetime,
) -> bool:
    if not profile.get("pushConsent") or _quiet_hour(profile, now):
        return False
    for field in ("cooldownUntil", "pauseUntil"):
        value = profile.get(field)
        if isinstance(value, str):
            try:
                if parse_datetime(value) > now:
                    return False
            except (ContractError, ValueError):
                return False
    signals = profile.get("currentSignals", {})
    if isinstance(signals, dict) and (
        signals.get("interventionHint") == "do_not_push"
        or signals.get("safety", {}).get("requiresHumanSupport") is True
    ):
        return False
    return _pushed_this_week(intervention_episodes, now) < int(profile.get("maxPushesPerWeek", 0))


def build_recommendation_context(
    store: JsonStore,
    user_id: str,
    profile: dict[str, Any],
    freebusy: dict[str, Any],
    now: datetime,
    *,
    data_mode: str,
    friction_types: set[str] | None = None,
    revalidate: bool = False,
) -> list[dict[str, Any]]:
    opportunities = load_opportunities(data_mode)
    recommendations = rank_conversation_candidates(
        profile,
        freebusy,
        opportunities,
        now,
        friction_types=friction_types,
    )
    if data_mode != "live" or not revalidate or not recommendations:
        return recommendations
    event_ids = [
        item["opportunity"].get("eventId")
        for item in recommendations
        if isinstance(item.get("opportunity"), dict)
        and isinstance(item["opportunity"].get("eventId"), str)
    ]
    if not event_ids:
        return []
    try:
        current = sync_before_push(event_ids, store=store, now=now)
        refreshed = load_opportunities("live")
        refreshed["opportunities"] = [
            item
            for item in refreshed.get("opportunities", [])
            if current.get(str(item.get("eventId")), False)
        ]
        return rank_conversation_candidates(
            profile,
            freebusy,
            refreshed,
            now,
            friction_types=friction_types,
        )
    except Exception:
        # A proactive nudge is fail-closed when live status cannot be confirmed.
        return []
