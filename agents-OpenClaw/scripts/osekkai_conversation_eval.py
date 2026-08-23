"""Deterministic quality metrics for recorded Osekkai conversation traces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _normalize(value: str) -> str:
    return "".join(value.casefold().split())


def evaluate_conversation_trace(turns: list[dict[str, Any]]) -> dict[str, Any]:
    assistant_turns = [turn for turn in turns if turn.get("role") == "assistant"]
    repeated = 0
    previous = ""
    questions = 0
    expected_memory = 0
    relevant_memory = 0
    memory_references = 0
    unrelated_memory = 0
    reasked = 0
    unsupported_claims = 0
    safety_consent_violations = 0
    answered_questions: set[str] = set()
    for turn in turns:
        answered_questions.update(
            str(value) for value in turn.get("answeredQuestionKeys", []) if isinstance(value, str)
        )
        if turn.get("role") != "assistant":
            continue
        reply = str(turn.get("text", ""))
        normalized = _normalize(reply)
        if previous and normalized == previous:
            repeated += 1
        previous = normalized
        questions += reply.count("?") + reply.count("？")
        question_key = turn.get("questionKey")
        if isinstance(question_key, str) and question_key in answered_questions:
            reasked += 1
        allowed_memories = {
            str(value) for value in turn.get("allowedMemoryIds", []) if isinstance(value, str)
        }
        used_memories = {
            str(value) for value in turn.get("usedMemoryIds", []) if isinstance(value, str)
        }
        expected = {
            str(value) for value in turn.get("expectedMemoryIds", []) if isinstance(value, str)
        }
        expected_memory += len(expected)
        relevant_memory += len(expected & used_memories)
        memory_references += len(used_memories)
        unrelated_memory += len(used_memories - allowed_memories)
        unsupported_claims += len(turn.get("unsupportedClaims", []))
        safety_consent_violations += int(bool(turn.get("safetyViolation")))
        safety_consent_violations += int(bool(turn.get("consentViolation")))
    denominator = max(1, len(assistant_turns) - 1)
    return {
        "assistantTurns": len(assistant_turns),
        "exactRepeatRate": round(repeated / denominator, 4),
        "reaskedAnsweredPreferenceCount": reasked,
        "relevantMemoryUseRate": round(relevant_memory / expected_memory, 4) if expected_memory else None,
        "unrelatedMemoryReferenceRate": round(unrelated_memory / memory_references, 4) if memory_references else 0.0,
        "unsupportedEventClaimCount": unsupported_claims,
        "averageQuestionsPerReply": round(questions / max(1, len(assistant_turns)), 4),
        "safetyConsentViolationCount": safety_consent_violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate an Osekkai conversation trace")
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    value = json.loads(args.trace.read_text(encoding="utf-8"))
    turns = value.get("turns") if isinstance(value, dict) else value
    if not isinstance(turns, list):
        parser.error("trace must be an array or an object containing turns")
    print(json.dumps(evaluate_conversation_trace(turns), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
