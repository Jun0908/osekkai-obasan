from __future__ import annotations

import json
import unittest

from helpers import AGENT_ROOT
from osekkai_conversation_eval import evaluate_conversation_trace


class ConversationQualityEvaluationTests(unittest.TestCase):
    def test_fixture_covers_plan3_scenarios(self):
        fixture = json.loads(
            (AGENT_ROOT / "fixtures" / "osekkai" / "conversation-quality.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            set(fixture["scenarioCoverage"]),
            {
                "free_expression", "ambiguous_expression", "multiple_frictions",
                "rejection", "reopen_after_cooldown", "check_in",
            },
        )

    def test_candidate_reduces_repetition_and_has_no_grounding_violation(self):
        fixture = json.loads(
            (AGENT_ROOT / "fixtures" / "osekkai" / "conversation-quality.json").read_text(
                encoding="utf-8"
            )
        )
        baseline = evaluate_conversation_trace(fixture["baselineTurns"])
        candidate = evaluate_conversation_trace(fixture["candidateTurns"])
        self.assertLess(candidate["exactRepeatRate"], baseline["exactRepeatRate"])
        self.assertEqual(candidate["reaskedAnsweredPreferenceCount"], 0)
        self.assertEqual(candidate["relevantMemoryUseRate"], 1.0)
        self.assertEqual(candidate["unrelatedMemoryReferenceRate"], 0.0)
        self.assertEqual(candidate["unsupportedEventClaimCount"], 0)
        self.assertLessEqual(candidate["averageQuestionsPerReply"], 1.0)
        self.assertEqual(candidate["safetyConsentViolationCount"], 0)


if __name__ == "__main__":
    unittest.main()
