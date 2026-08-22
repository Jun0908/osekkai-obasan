from __future__ import annotations

import copy
import unittest
from datetime import timedelta

from helpers import NOW, demo_inputs, ready_profile
from osekkai_policy import evaluate_policy, filter_candidates, load_policy_config


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.profile = ready_profile()
        self.freebusy, self.opportunities = demo_inputs()
        self.config = load_policy_config()

    def decision(self, profile=None, freebusy=None, opportunities=None, episodes=None, now=NOW):
        return evaluate_policy(
            profile or self.profile,
            freebusy or self.freebusy,
            opportunities or self.opportunities,
            episodes or [],
            now,
            self.config,
        )

    def test_push_consent_guardrail_is_first(self):
        profile = copy.deepcopy(self.profile)
        profile["pushConsent"] = False
        profile["currentSignals"]["interventionHint"] = "do_not_push"
        self.assertEqual(self.decision(profile=profile)["reasonCodes"], ["NO_PUSH_CONSENT"])

    def test_quiet_hours_guardrail(self):
        now = NOW.replace(hour=22)
        self.assertEqual(self.decision(now=now)["reasonCodes"], ["QUIET_HOURS"])

    def test_cooldown_guardrail(self):
        profile = copy.deepcopy(self.profile)
        profile["cooldownUntil"] = (NOW + timedelta(hours=1)).isoformat()
        self.assertEqual(self.decision(profile=profile)["reasonCodes"], ["COOLDOWN_ACTIVE"])

    def test_weekly_limit_guardrail(self):
        episodes = [
            {"shouldPush": True, "pushedAt": NOW.isoformat()},
            {"shouldPush": True, "pushedAt": NOW.isoformat()},
        ]
        self.assertEqual(self.decision(episodes=episodes)["reasonCodes"], ["WEEKLY_LIMIT_REACHED"])

    def test_explicit_pause_and_no_action_guardrails(self):
        paused = copy.deepcopy(self.profile)
        paused["pauseUntil"] = (NOW + timedelta(days=1)).isoformat()
        self.assertEqual(self.decision(profile=paused)["reasonCodes"], ["EXPLICIT_PAUSE"])
        no_action = copy.deepcopy(self.profile)
        no_action["currentSignals"]["interventionHint"] = "do_not_push"
        self.assertEqual(self.decision(profile=no_action)["reasonCodes"], ["EXPLICIT_NO_ACTION"])

    def test_human_support_guardrail(self):
        profile = copy.deepcopy(self.profile)
        profile["currentSignals"] = {
            "interventionHint": "do_not_push",
            "currentReceptivity": 0,
            "safety": {"level": "urgent", "requiresHumanSupport": True},
            "observedAt": NOW.isoformat(),
        }
        self.assertEqual(self.decision(profile=profile)["reasonCodes"], ["HUMAN_SUPPORT_REQUIRED"])

    def test_no_free_window_and_no_source_do_not_invent_candidate(self):
        freebusy = copy.deepcopy(self.freebusy)
        freebusy["freeWindows"] = []
        no_window = self.decision(freebusy=freebusy)
        self.assertFalse(no_window["shouldPush"])
        self.assertIsNone(no_window["selectedOpportunity"])
        self.assertEqual(no_window["reasonCodes"], ["NO_FREE_WINDOW"])
        opportunities = copy.deepcopy(self.opportunities)
        opportunities["opportunities"][0]["verificationStatus"] = "unverified"
        no_source = self.decision(opportunities=opportunities)
        self.assertEqual(no_source["reasonCodes"], ["NO_VERIFIED_OPPORTUNITY"])

    def test_low_battery_filters_high_intensity(self):
        opportunities = copy.deepcopy(self.opportunities)
        opportunities["opportunities"][0]["socialIntensity"] = 4
        eligible, exclusions, _ = filter_candidates(
            self.profile,
            self.freebusy["freeWindows"],
            opportunities["opportunities"],
            self.config,
            NOW,
            "demo",
        )
        self.assertEqual(eligible, [])
        self.assertIn("SOCIAL_INTENSITY_LIMIT", exclusions["koto-131083B00016"])

    def test_demo_acceptance_selects_exactly_one_and_is_deterministic(self):
        first = self.decision()
        second = self.decision()
        self.assertTrue(first["shouldPush"])
        self.assertEqual(first["decision"], "suggest_solo_place")
        self.assertEqual(first["selectedOpportunityId"], "koto-131083B00016")
        self.assertEqual(first, second)
        self.assertGreaterEqual(first["score"], self.config["pushThreshold"])

    def test_live_policy_rejects_demo_snapshot(self):
        opportunities = copy.deepcopy(self.opportunities)
        opportunities["dataMode"] = "live"
        for item in opportunities["opportunities"]:
            item["dataMode"] = "live"
        result = self.decision(opportunities=opportunities)
        self.assertEqual(result["reasonCodes"], ["NO_VERIFIED_OPPORTUNITY"])


if __name__ == "__main__":
    unittest.main()
