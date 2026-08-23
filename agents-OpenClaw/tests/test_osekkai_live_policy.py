from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime

from helpers import AGENT_ROOT
from osekkai_policy import evaluate_policy, load_policy_config


NOW = datetime.fromisoformat("2026-08-23T09:00:00+09:00")


class LivePolicyTests(unittest.TestCase):
    def setUp(self):
        fixture = json.loads((AGENT_ROOT / "fixtures" / "osekkai" / "live-contracts.json").read_text(encoding="utf-8"))
        self.opportunities = {
            "schemaVersion": "1.0",
            "dataMode": "live",
            "notice": "Live fixture",
            "opportunities": fixture["opportunities"],
        }
        self.profile = json.loads((AGENT_ROOT / "fixtures" / "osekkai" / "profile.json").read_text(encoding="utf-8"))
        self.profile.update(
            {
                "preferredCategories": ["craft"],
                "maxSocialIntensity": 5,
                "socialBattery": 80,
                "maxTravelMinutes": 40,
                "maxBudgetYen": 3000,
            }
        )
        self.profile["currentSignals"] = {
            "interventionHint": "consider_push",
            "currentReceptivity": 0.8,
            "safety": {"level": "normal", "requiresHumanSupport": False},
            "observedAt": NOW.isoformat(),
        }
        self.freebusy = {
            "schemaVersion": "1.0",
            "dataMode": "live",
            "generatedAt": NOW.isoformat(),
            "source": {"type": "google_freebusy", "notice": "FreeBusyだけを使用"},
            "freeWindows": [
                {
                    "id": "window-craft",
                    "start": "2026-09-05T12:00:00+09:00",
                    "end": "2026-09-05T18:00:00+09:00",
                    "durationMinutes": 360,
                    "verificationStatus": "source_verified",
                },
                {
                    "id": "window-boardgame",
                    "start": "2026-09-06T10:00:00+09:00",
                    "end": "2026-09-06T18:00:00+09:00",
                    "durationMinutes": 480,
                    "verificationStatus": "source_verified",
                },
            ],
        }
        self.config = load_policy_config()

    def decide(self, opportunities=None, profile=None):
        return evaluate_policy(
            profile or self.profile,
            self.freebusy,
            opportunities or self.opportunities,
            [],
            NOW,
            self.config,
        )

    def test_returns_ranked_multiple_candidates_with_reproducible_reasons(self):
        first = self.decide()
        second = self.decide()
        self.assertTrue(first["shouldPush"])
        self.assertEqual(first, second)
        self.assertEqual([item["rank"] for item in first["rankedOpportunities"]], [1, 2])
        self.assertEqual(first["rankedOpportunities"][0]["opportunityId"], first["selectedOpportunityId"])
        second_reasons = first["rankedOpportunities"][1]["recommendationReasons"]
        self.assertIn("adjacent_interest", {item["code"] for item in second_reasons})
        self.assertTrue(all("classification" in item for ranked in first["rankedOpportunities"] for item in ranked["recommendationReasons"]))
        self.assertIn("あんた、この前craft好きって言うてたやろ", first["message"])

    def test_connection_level_zero_and_one_are_hard_rejected_in_live_mode(self):
        opportunities = copy.deepcopy(self.opportunities)
        passive = opportunities["opportunities"][0]
        passive["connectionEvidence"]["connectionLevel"] = 1
        result = self.decide(opportunities=opportunities)
        self.assertIn("CONNECTION_LEVEL", result["exclusions"][passive["id"]])
        self.assertEqual(len(result["rankedOpportunities"]), 1)

    def test_unknown_battery_uses_standard_intensity_without_a_fatigue_questionnaire(self):
        profile = copy.deepcopy(self.profile)
        profile["socialBattery"] = None
        profile["maxSocialIntensity"] = 2
        opportunities = copy.deepcopy(self.opportunities)
        for item in opportunities["opportunities"]:
            item["socialIntensity"] = 2
        result = self.decide(profile=profile, opportunities=opportunities)
        self.assertTrue(result["shouldPush"])
        self.assertGreaterEqual(len(result["rankedOpportunities"]), 2)

    def test_avoided_category_and_price_are_applied_before_ranking(self):
        profile = copy.deepcopy(self.profile)
        profile["avoidedCategories"] = ["craft"]
        result = self.decide(profile=profile)
        craft_id = self.opportunities["opportunities"][0]["id"]
        self.assertIn("SOCIAL_INTENSITY_LIMIT", result["exclusions"][craft_id])
        self.assertEqual(result["selectedOpportunityId"], self.opportunities["opportunities"][1]["id"])

    def test_unknown_price_is_visible_and_not_mislabeled_as_over_budget(self):
        opportunities = copy.deepcopy(self.opportunities)
        opportunities["opportunities"][0]["priceYen"] = None
        result = self.decide(opportunities=opportunities)
        candidate_id = opportunities["opportunities"][0]["id"]
        self.assertNotIn(candidate_id, result["exclusions"])
        ranked = {item["opportunityId"]: item for item in result["rankedOpportunities"]}
        self.assertIn(candidate_id, ranked)

    def test_shortlist_limit_is_policy_configuration_not_one(self):
        self.assertGreaterEqual(self.config["maxRankedOpportunities"], 2)
        self.assertLessEqual(self.config["maxRankedOpportunities"], 8)


if __name__ == "__main__":
    unittest.main()
