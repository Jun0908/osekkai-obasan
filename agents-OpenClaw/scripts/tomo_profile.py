"""
tomo_profile.py
Telegram 上のフィードバックから、ともさん向けの秘書 profile を保存する。
"""

from __future__ import annotations

import re

from openclaw_core import TAG_RULES, TELEGRAM_DIR, derive_tags, now_jst, read_json_if_exists, write_json


PROFILE_PATH = TELEGRAM_DIR / "tomo_profile.json"
PREFERENCE_HINTS = ("優先", "重視", "上に", "先に", "大事", "重要", "注目", "よく見る", "増やして")
SHORT_STYLE_HINTS = ("短く", "短め", "一言", "要点だけ", "端的")
DETAILED_STYLE_HINTS = ("詳しく", "詳細", "長め", "丁寧", "くわしく")
REGION_PATTERN = re.compile(r"([一-龥ぁ-んァ-ヶA-Za-z0-9]+(?:地区|地域|エリア))")


def default_profile() -> dict:
    return {
        "preferred_topics": [],
        "preferred_regions": [],
        "brief_style": "short",
        "priority_bias": {},
        "feedback_history": [],
        "updated_at": now_jst().isoformat(),
    }


def load_profile() -> dict:
    profile = read_json_if_exists(PROFILE_PATH, default=None)
    if isinstance(profile, dict):
        merged = default_profile()
        merged.update(profile)
        return merged
    return default_profile()


def save_profile(profile: dict):
    profile["updated_at"] = now_jst().isoformat()
    write_json(PROFILE_PATH, profile)


def _append_unique(values: list[str], value: str):
    if value and value not in values:
        values.append(value)


def detect_regions(text: str) -> list[str]:
    return list(dict.fromkeys(match.strip() for match in REGION_PATTERN.findall(text or "") if match.strip()))


def auto_learn_preferences(profile: dict, text: str) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    changes: list[str] = []
    lowered = cleaned.lower()
    preferred_topics = profile.setdefault("preferred_topics", [])
    preferred_regions = profile.setdefault("preferred_regions", [])
    priority_bias = profile.setdefault("priority_bias", {})

    if any(hint in cleaned for hint in SHORT_STYLE_HINTS):
        if profile.get("brief_style") != "short":
            profile["brief_style"] = "short"
            changes.append("ブリーフ形式を short に設定")
    elif any(hint in cleaned for hint in DETAILED_STYLE_HINTS):
        if profile.get("brief_style") != "detailed":
            profile["brief_style"] = "detailed"
            changes.append("ブリーフ形式を detailed に設定")

    preference_requested = any(hint in cleaned for hint in PREFERENCE_HINTS)
    detected_topics = list(dict.fromkeys(derive_tags(cleaned) + [tag for tag in TAG_RULES if tag in cleaned]))
    detected_regions = detect_regions(cleaned)

    if preference_requested:
        for topic in detected_topics:
            if topic not in preferred_topics:
                _append_unique(preferred_topics, topic)
                changes.append(f"優先テーマに {topic} を追加")
            priority_bias[topic] = int(priority_bias.get(topic, 0)) + 1

        for region in detected_regions:
            if region not in preferred_regions:
                _append_unique(preferred_regions, region)
                changes.append(f"重点地域に {region} を追加")

    # 明示コマンドがなくても、表現の好みや地域の強調は拾う
    if ("見やすい" in cleaned or "読みやすい" in cleaned) and "短" in cleaned:
        if profile.get("brief_style") != "short":
            profile["brief_style"] = "short"
            changes.append("読みやすさの好みとして short を採用")

    if ("見やすい" in cleaned or "必要" in cleaned) and ("詳" in cleaned or "詳細" in cleaned):
        if profile.get("brief_style") != "detailed":
            profile["brief_style"] = "detailed"
            changes.append("読みやすさの好みとして detailed を採用")

    return list(dict.fromkeys(changes))


def learn_from_feedback(text: str, *, source: str = "telegram") -> tuple[dict, list[str]]:
    profile = load_profile()
    profile.setdefault("feedback_history", []).append(
        {
            "text": text.strip(),
            "source": source,
            "created_at": now_jst().isoformat(),
        }
    )
    profile["feedback_history"] = profile["feedback_history"][-50:]
    changes = auto_learn_preferences(profile, text)
    save_profile(profile)
    return profile, changes


def add_feedback(text: str, *, source: str = "telegram") -> dict:
    profile, _changes = learn_from_feedback(text, source=source)
    return profile


def add_preference(kind: str, value: str) -> dict:
    profile = load_profile()
    cleaned = value.strip()
    if not cleaned:
        return profile

    if kind == "topic":
        values = profile.setdefault("preferred_topics", [])
    elif kind == "region":
        values = profile.setdefault("preferred_regions", [])
    elif kind == "style":
        profile["brief_style"] = cleaned
        save_profile(profile)
        return profile
    else:
        values = profile.setdefault("preferred_topics", [])

    if cleaned not in values:
        values.append(cleaned)
    save_profile(profile)
    return profile


def profile_to_text(profile: dict) -> str:
    topics = ", ".join(profile.get("preferred_topics", [])) or "未設定"
    regions = ", ".join(profile.get("preferred_regions", [])) or "未設定"
    style = profile.get("brief_style", "short")
    feedback_count = len(profile.get("feedback_history", []))
    return "\n".join(
        [
            "ともさん profile",
            f"- 優先テーマ: {topics}",
            f"- 重点地域: {regions}",
            f"- ブリーフ形式: {style}",
            f"- 保存済みフィードバック: {feedback_count}件",
        ]
    )
