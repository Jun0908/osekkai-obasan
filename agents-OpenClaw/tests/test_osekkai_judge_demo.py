from __future__ import annotations

import json
import unittest

import helpers  # noqa: F401  # Adds the canonical scripts directory to sys.path.
from osekkai_judge_demo import (
    DEFAULT_OUTPUT,
    DEFAULT_SOURCE,
    load_judge_demo_scenario,
    render_judge_demo_scenario,
    validate_scenario_semantics,
)


class JudgeDemoTests(unittest.TestCase):
    def test_scenario_is_contract_valid_and_covers_three_osekkai_distances(self):
        scenario = load_judge_demo_scenario()
        validate_scenario_semantics(scenario)
        self.assertEqual(len(scenario["stories"]), 3)
        self.assertEqual(
            {story["kind"] for story in scenario["stories"]},
            {"preference_discovery", "respectful_hold", "continuity_followup"},
        )

        hold = next(story for story in scenario["stories"] if story["kind"] == "respectful_hold")
        hold_choices = [choice for step in hold["steps"] for choice in step["choices"]]
        self.assertTrue(all(not choice["eventOrder"] for choice in hold_choices))
        self.assertTrue(all(not choice["selectFirstEvent"] for choice in hold_choices))
        self.assertIn("今日は疲れた", json.dumps(hold, ensure_ascii=False))

        continuity = next(story for story in scenario["stories"] if story["kind"] == "continuity_followup")
        orders = [
            choice["eventOrder"]
            for step in continuity["steps"]
            for choice in step["choices"]
            if choice["eventOrder"]
        ]
        self.assertGreaterEqual(len(orders), 2)
        self.assertNotEqual(orders[0], orders[1])

    def test_data_classifications_and_claim_boundaries_are_explicit(self):
        scenario = load_judge_demo_scenario()
        classifications = {note["classification"] for note in scenario["dataNotes"]}
        self.assertEqual(
            classifications,
            {"recorded_source_snapshot", "recorded_live", "synthetic_demo", "deterministic_replay"},
        )
        self.assertTrue(
            all(
                window["classification"] == "synthetic_demo"
                for story in scenario["stories"]
                for window in story["freeWindows"]
            )
        )
        self.assertTrue(
            all(
                event["route"] is None or event["route"]["classification"] == "recorded_live"
                for event in scenario["events"]
            )
        )
        serialized = json.dumps(scenario, ensure_ascii=False)
        self.assertIn("Googleログイン不要", serialized)
        self.assertNotIn("一人参加OK", serialized)
        self.assertNotIn("無料です", serialized)

    def test_generated_frontend_artifact_is_current(self):
        self.assertTrue(DEFAULT_SOURCE.exists())
        self.assertTrue(DEFAULT_OUTPUT.exists())
        self.assertEqual(DEFAULT_OUTPUT.read_text(encoding="utf-8"), render_judge_demo_scenario())


if __name__ == "__main__":
    unittest.main()
