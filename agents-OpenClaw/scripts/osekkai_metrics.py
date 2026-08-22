"""KPI recomputation from immutable Intervention Episodes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from osekkai_contracts import SCHEMA_VERSION


def _rate_metric(
    metric_key: str,
    label: str,
    numerator: int,
    denominator: int,
    classification: str,
) -> dict[str, Any]:
    return {
        "key": metric_key,
        "label": label,
        "value": round(numerator / denominator, 4) if denominator else None,
        "numerator": numerator,
        "denominator": denominator,
        "classification": classification,
        "note": "分母が0のため未計測です。" if not denominator else "Episodeから再計算しています。",
    }


def _unverified(metric_key: str, label: str) -> dict[str, Any]:
    return {
        "key": metric_key,
        "label": label,
        "value": None,
        "classification": "unverified",
        "note": "P0では収集・推計しません。",
    }


def calculate_metrics(
    episodes: list[dict[str, Any]],
    data_mode: str = "demo",
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    classification = "demo" if data_mode == "demo" else "measured"
    eligible_episodes = [
        episode
        for episode in episodes
        if episode.get("dataMode", data_mode) == data_mode
        and episode.get("metricClassification", classification) == classification
    ]
    pushed = [episode for episode in eligible_episodes if episode.get("shouldPush")]
    distance_answered = [
        episode
        for episode in pushed
        if episode.get("distanceFeedback") in {"too_much", "just_right", "push_more"}
    ]
    just_right = sum(episode.get("distanceFeedback") == "just_right" for episode in distance_answered)
    too_much_ids = {
        episode.get("id")
        for episode in pushed
        if episode.get("distanceFeedback") == "too_much"
        or episode.get("actionResponse") == "pause_one_week"
        or episode.get("explicitNotificationStopped") is True
    }
    under_support = sum(episode.get("distanceFeedback") == "push_more" for episode in distance_answered)
    action_answered = [
        episode
        for episode in pushed
        if episode.get("actionResponse") in {"accepted", "declined", "show_another", "pause_one_week"}
    ]
    accepted = sum(episode.get("actionResponse") == "accepted" for episode in action_answered)
    attended = sum(
        bool(episode.get("attendedAt"))
        for episode in action_answered
        if episode.get("actionResponse") == "accepted"
    )
    revisited = sum(bool(episode.get("revisitedAt")) for episode in pushed if episode.get("attendedAt"))
    attendance_denominator = accepted
    revisit_denominator = sum(bool(episode.get("attendedAt")) for episode in pushed)
    metrics = [
        _rate_metric(
            "just_right_push_rate",
            "Just-Right Push Rate",
            just_right,
            len(distance_answered),
            classification,
        ),
        _rate_metric(
            "overreach_rate",
            "Overreach Rate",
            len(too_much_ids),
            len(pushed),
            classification,
        ),
        _rate_metric(
            "under_support_rate",
            "Under-Support Rate",
            under_support,
            len(distance_answered),
            classification,
        ),
        _rate_metric(
            "acceptance_rate",
            "提案承諾率",
            accepted,
            len(action_answered),
            classification,
        ),
        _rate_metric(
            "attendance_rate",
            "参加率（デモ操作）" if data_mode == "demo" else "実参加率",
            attended,
            attendance_denominator,
            classification,
        ),
        _rate_metric(
            "revisit_rate",
            "再訪率（デモ操作）" if data_mode == "demo" else "再訪率",
            revisited,
            revisit_denominator,
            classification,
        ),
    ]
    unverified = [
        _unverified("third_place_acquisition_rate", "Third Place Acquisition Rate"),
        _unverified("role_acquisition_rate", "Role Acquisition Rate"),
        _unverified("graduation_rate", "OSEKKAI Graduation Rate"),
        _unverified("ucla3_baseline", "UCLA-3 baseline"),
        _unverified("ucla3_week_4", "UCLA-3 week 4"),
        _unverified("ucla3_week_8", "UCLA-3 week 8"),
        _unverified("loneliness_point_weeks_avoided", "Loneliness Point-Weeks Avoided"),
    ]
    timestamp = generated_at or datetime.now(timezone.utc)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": timestamp.isoformat(),
        "dataMode": data_mode,
        "metrics": metrics,
        "unverifiedMetrics": unverified,
    }
