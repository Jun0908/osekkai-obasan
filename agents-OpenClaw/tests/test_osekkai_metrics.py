from __future__ import annotations

import unittest

from helpers import NOW
from osekkai_metrics import calculate_metrics


class MetricsTests(unittest.TestCase):
    def metric(self, result, key):
        return next(item for item in result["metrics"] if item["key"] == key)

    def test_zero_denominators_are_null_not_zero(self):
        result = calculate_metrics([], "demo", NOW)
        for item in result["metrics"]:
            self.assertIsNone(item["value"])
            self.assertEqual(item["denominator"], 0)
            self.assertEqual(item["classification"], "demo")
        self.assertTrue(result["unverifiedMetrics"])
        self.assertTrue(all(item["classification"] == "unverified" for item in result["unverifiedMetrics"]))

    def test_unique_episode_feedback_is_counted_once(self):
        episodes = [
            {
                "id": "one",
                "shouldPush": True,
                "distanceFeedback": "just_right",
                "actionResponse": "accepted",
                "attendedAt": NOW.isoformat(),
                "revisitedAt": NOW.isoformat(),
            },
            {
                "id": "two",
                "shouldPush": True,
                "distanceFeedback": "too_much",
                "actionResponse": "declined",
            },
            {"id": "three", "shouldPush": False},
        ]
        result = calculate_metrics(episodes, "demo", NOW)
        self.assertEqual(self.metric(result, "just_right_push_rate")["value"], 0.5)
        self.assertEqual(self.metric(result, "overreach_rate")["value"], 0.5)
        self.assertEqual(self.metric(result, "under_support_rate")["value"], 0.0)
        self.assertEqual(self.metric(result, "acceptance_rate")["value"], 0.5)
        self.assertEqual(self.metric(result, "attendance_rate")["value"], 1.0)
        self.assertEqual(self.metric(result, "revisit_rate")["value"], 1.0)

    def test_decline_alone_is_not_overreach(self):
        result = calculate_metrics(
            [{"id": "one", "shouldPush": True, "actionResponse": "declined"}], "demo", NOW
        )
        self.assertEqual(self.metric(result, "overreach_rate")["value"], 0.0)

    def test_demo_episodes_are_never_reclassified_as_live_measurements(self):
        demo_episode = {
            "id": "demo-one",
            "dataMode": "demo",
            "metricClassification": "demo",
            "shouldPush": True,
            "actionResponse": "accepted",
        }
        live = calculate_metrics([demo_episode], "live", NOW)
        self.assertIsNone(self.metric(live, "acceptance_rate")["value"])
        self.assertEqual(self.metric(live, "acceptance_rate")["denominator"], 0)
        self.assertEqual(self.metric(live, "acceptance_rate")["classification"], "measured")


if __name__ == "__main__":
    unittest.main()
