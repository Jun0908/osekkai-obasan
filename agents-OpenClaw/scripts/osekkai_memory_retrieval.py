"""Bounded, user-isolated retrieval over Obsidian memory notes."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from osekkai_contracts import SCHEMA_VERSION, validate_schema
from osekkai_memory_vault import ObsidianMemoryVault


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\-]{2,}|[ぁ-んァ-ヶ一-龠々]{2,}")


def _tokens(value: str) -> set[str]:
    normalized = " ".join(value.casefold().split())
    return {match.group(0) for match in TOKEN_PATTERN.finditer(normalized)}


def _score(note: dict[str, Any], query: str, query_tokens: set[str], now: datetime) -> float:
    summary = str(note.get("summary", "")).casefold()
    keywords = [str(value).casefold() for value in note.get("keywords", [])]
    searchable = " ".join([summary, *keywords])
    score = 0.0
    for keyword in keywords:
        if keyword and keyword in query.casefold():
            score += 2.5
    note_tokens = _tokens(searchable)
    score += 0.6 * len(query_tokens & note_tokens)
    if note.get("origin") == "explicit":
        score += 0.6
    score += float(note.get("confidence", 0.0)) * 0.5
    try:
        age_days = max(
            0.0,
            (now - datetime.fromisoformat(str(note["lastConfirmedAt"]))).total_seconds() / 86400,
        )
        score += max(0.0, 0.5 - min(age_days, 90.0) / 180.0)
    except (KeyError, TypeError, ValueError):
        pass
    return score


def retrieve_relevant_memories(
    vault: ObsidianMemoryVault,
    user_id: str,
    query: str,
    now: datetime,
    *,
    limit: int = 5,
) -> dict[str, Any]:
    clean_query = " ".join(query.strip().split())[:1000]
    query_tokens = _tokens(clean_query)
    candidates = vault.list_notes(user_id, now=now)
    scored = [(_score(note, clean_query, query_tokens, now), note) for note in candidates]
    scored.sort(key=lambda item: (item[0], item[1]["lastConfirmedAt"], item[1]["id"]), reverse=True)
    minimum = 0.45 if clean_query else 0.0
    notes = [note for score, note in scored if score >= minimum][: max(1, min(5, limit))]
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "userId": user_id,
        "query": clean_query,
        "notes": notes,
        "generatedAt": now.isoformat(),
    }
    validate_schema(result, "memory-retrieval-result.schema.json")
    return result
