"""Conservative deterministic safety routing; no diagnosis and no reporting."""

from __future__ import annotations

from typing import Any


URGENT_MARKERS = (
    "死にたい",
    "消えたい",
    "自殺",
    "自分を傷つけ",
    "命を絶",
    "suicide",
    "kill myself",
    "harm myself",
)


def assess_safety(message: str) -> dict[str, Any]:
    normalized = message.casefold()
    urgent = any(marker in normalized for marker in URGENT_MARKERS)
    if urgent:
        return {
            "level": "urgent",
            "requiresHumanSupport": True,
            "message": (
                "今はイベントを提案しません。差し迫った危険がある場合は、"
                "地域の緊急窓口や信頼できる人へ直接連絡してください。"
                "このデモは診断や自動通報を行いません。"
            ),
            "supportResourcesVerified": False,
        }
    return {
        "level": "normal",
        "requiresHumanSupport": False,
        "message": None,
        "supportResourcesVerified": False,
    }

