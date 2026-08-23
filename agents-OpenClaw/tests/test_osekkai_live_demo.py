from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timedelta

from helpers import AGENT_ROOT, USER_ID
from osekkai_connection import extract_connection_evidence
from osekkai_event_normalizer import normalize_event_mesh
from osekkai_policy import evaluate_policy, load_policy_config
from osekkai_profile import seed_demo_profile


NOW = datetime.fromisoformat("2026-08-23T09:00:00+09:00")


def fixture():
    return json.loads((AGENT_ROOT / "fixtures" / "osekkai" / "live-contracts.json").read_text(encoding="utf-8"))


def freebusy(start: str, end: str):
    start_at = datetime.fromisoformat(start)
    end_at = datetime.fromisoformat(end)
    return {
        "schemaVersion": "1.0",
        "dataMode": "live",
        "generatedAt": NOW.isoformat(),
        "source": {"type": "google_freebusy", "notice": "FreeBusy only"},
        "freeWindows": [{
            "id": "verified-window",
            "start": start,
            "end": end,
            "durationMinutes": int((end_at - start_at).total_seconds() // 60),
            "verificationStatus": "source_verified",
        }],
    }


class LiveDemoIntegrationTests(unittest.TestCase):
    def setUp(self):
        value = fixture()
        self.opportunities = copy.deepcopy(value["opportunities"])
        self.profile = seed_demo_profile(USER_ID, NOW)
        self.profile.update({
            "pushConsent": True,
            "memoryConsent": True,
            "socialBattery": 90,
            "maxSocialIntensity": 5,
            "maxTravelMinutes": 60,
            "maxBudgetYen": 5000,
            "preferredCategories": ["craft", "food", "community"],
            "currentSignals": {
                "interventionHint": "consider_push",
                "currentReceptivity": 0.9,
                "safety": {"level": "normal", "requiresHumanSupport": False},
                "observedAt": NOW.isoformat(),
            },
        })

    def test_calendar_and_routes_change_the_final_recommendation_set(self):
        both = evaluate_policy(
            self.profile,
            freebusy("2026-09-05T12:00:00+09:00", "2026-09-06T18:00:00+09:00"),
            {"schemaVersion": "1.0", "dataMode": "live", "notice": "fixture", "opportunities": self.opportunities},
            [], NOW, load_policy_config(),
        )
        self.assertGreaterEqual(len(both["rankedOpportunities"]), 2)

        second_only = evaluate_policy(
            self.profile,
            freebusy("2026-09-06T12:30:00+09:00", "2026-09-06T15:30:00+09:00"),
            {"schemaVersion": "1.0", "dataMode": "live", "notice": "fixture", "opportunities": self.opportunities},
            [], NOW, load_policy_config(),
        )
        self.assertEqual(len(second_only["rankedOpportunities"]), 1)
        self.assertEqual(second_only["rankedOpportunities"][0]["opportunityId"], self.opportunities[1]["id"])

        route_changed = copy.deepcopy(self.opportunities)
        route_changed[0]["travelEstimate"]["minutes"] = 180
        route_filtered = evaluate_policy(
            self.profile,
            freebusy("2026-09-05T12:00:00+09:00", "2026-09-06T18:00:00+09:00"),
            {"schemaVersion": "1.0", "dataMode": "live", "notice": "fixture", "opportunities": route_changed},
            [], NOW, load_policy_config(),
        )
        self.assertNotIn(route_changed[0]["id"], [item["opportunityId"] for item in route_filtered["rankedOpportunities"]])

    def test_map_keeps_mixed_quality_events_while_connection_gate_is_evidence_based(self):
        base = fixture()["events"][0]
        variants = []
        descriptions = {
            "exhibition": ("大型展示", "作品を自由に鑑賞する展示です。", "scheduled", "open"),
            "sales": ("営業Networking", "営業・勧誘と名刺交換を目的にした交流会です。", "scheduled", "open"),
            "meal": ("月例みんなでごはん", "一人参加歓迎。毎月みんなで食事し、テーブルで会話します。", "scheduled", "open"),
            "volunteer": ("継続ボランティア", "初心者歓迎。毎月グループで共同作業し、小さな役割があります。", "scheduled", "open"),
            "canceled": ("中止イベント", "交流会", "canceled", "closed"),
            "sold": ("満席イベント", "交流会", "sold_out", "sold_out"),
        }
        for index, (key, (title, description, status, registration)) in enumerate(descriptions.items()):
            event = copy.deepcopy(base)
            event.update({
                "id": f"event-{key}", "sourceRecordId": f"record-{key}", "sourceUrl": f"https://lu.ma/{key}",
                "title": title, "description": description, "status": status, "registrationStatus": registration,
                "startsAt": (datetime.fromisoformat(base["startsAt"]) + timedelta(days=index)).isoformat(),
                "endsAt": (datetime.fromisoformat(base["endsAt"]) + timedelta(days=index)).isoformat(),
            })
            variants.append(event)
        duplicate = copy.deepcopy(variants[2])
        duplicate.update({"id": "event-meal-copy", "provider": "doorkeeper", "sourceRecordId": "meal-copy"})
        mesh = normalize_event_mesh([
            {"provider": "luma_tokyo", "events": variants},
            {"provider": "doorkeeper", "events": [duplicate]},
        ], now=NOW)
        self.assertEqual(len(mesh["events"]), len(variants))
        self.assertEqual(len(next(event for event in mesh["events"] if event["id"] == "event-meal")["sourceLinks"]), 2)
        by_title = {
            event["title"]: extract_connection_evidence(event, evaluated_at=NOW)
            for event in mesh["events"]
        }
        self.assertEqual(by_title["大型展示"]["connectionLevel"], 0)
        self.assertEqual(by_title["営業Networking"]["connectionLevel"], 0)
        self.assertGreaterEqual(by_title["月例みんなでごはん"]["connectionLevel"], 2)
        self.assertGreaterEqual(by_title["継続ボランティア"]["connectionLevel"], 2)
        self.assertEqual({item["eventId"] for item in mesh["excludedEvents"]}, {"event-canceled", "event-sold"})

    def test_zero_candidates_never_creates_a_synthetic_event(self):
        result = evaluate_policy(
            self.profile,
            freebusy("2026-09-05T12:00:00+09:00", "2026-09-06T18:00:00+09:00"),
            {"schemaVersion": "1.0", "dataMode": "live", "notice": "none", "opportunities": []},
            [], NOW, load_policy_config(),
        )
        self.assertFalse(result["shouldPush"])
        self.assertEqual(result["rankedOpportunities"], [])
        self.assertIsNone(result["selectedOpportunity"])


if __name__ == "__main__":
    unittest.main()
