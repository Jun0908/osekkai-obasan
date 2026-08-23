from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timedelta

from helpers import AGENT_ROOT
from osekkai_event_normalizer import canonical_url, normalize_event_mesh


NOW = datetime.fromisoformat("2026-08-23T09:00:00+09:00")


class EventNormalizerTests(unittest.TestCase):
    def setUp(self):
        fixture = json.loads((AGENT_ROOT / "fixtures" / "osekkai" / "live-contracts.json").read_text(encoding="utf-8"))
        self.event = fixture["events"][0]

    def test_canonical_url_removes_only_tracking_and_fragment(self):
        self.assertEqual(
            canonical_url("https://Example.com/event/?utm_source=x&b=2&a=1#top"),
            "https://example.com/event?a=1&b=2",
        )

    def test_duplicate_external_event_from_luma_and_origin_merges_sources(self):
        duplicate = copy.deepcopy(self.event)
        duplicate.update(
            {
                "id": "event-origin-copy",
                "provider": "koto_culture",
                "sourceRecordId": "course-44",
                "sourceUrl": f"{self.event['sourceUrl']}?utm_source=luma",
                "fetchedAt": (NOW - timedelta(minutes=10)).isoformat(),
                "revalidatedAt": (NOW - timedelta(minutes=10)).isoformat(),
            }
        )
        result = normalize_event_mesh(
            [{"provider": "luma_tokyo", "events": [self.event]}, {"provider": "koto_culture", "events": [duplicate]}],
            now=NOW,
        )
        self.assertEqual(result["counts"]["received"], 2)
        self.assertEqual(result["counts"]["merged"], 1)
        self.assertEqual(len(result["events"][0]["sourceLinks"]), 2)

    def test_map_keeps_statuses_but_push_gate_excludes_them(self):
        variants = []
        for index, status in enumerate(("canceled", "sold_out", "registration_closed", "unknown"), start=1):
            item = copy.deepcopy(self.event)
            item["id"] = f"event-{status}"
            item["sourceRecordId"] = f"record-{status}"
            item["sourceUrl"] = f"https://lu.ma/status-{index}"
            item["title"] = f"状態確認 {status}"
            item["status"] = status
            item["registrationStatus"] = "closed" if status != "sold_out" else "sold_out"
            variants.append(item)
        result = normalize_event_mesh([{"provider": "luma_tokyo", "events": variants}], now=NOW)
        self.assertEqual(len(result["events"]), 4)
        self.assertEqual(len(result["eligibleEvents"]), 0)
        self.assertEqual(len(result["excludedEvents"]), 4)

    def test_public_title_and_description_add_transparent_derived_categories(self):
        event = copy.deepcopy(self.event)
        event["title"] = "Pilates & Chat"
        event["description"] = "初心者向けピラティスのあとに会話します。"
        event["categories"] = []
        result = normalize_event_mesh([{"provider": "luma_tokyo", "events": [event]}], now=NOW)
        enriched = result["events"][0]
        self.assertEqual(enriched["categories"], ["ダンス・健康"])
        self.assertEqual(enriched["fieldProvenance"]["categories"]["classification"], "ai_derived")
        self.assertEqual(enriched["fieldProvenance"]["categories"]["evidenceField"], "title,description")

    def test_series_occurrences_with_same_record_and_url_stay_separate(self):
        next_occurrence = copy.deepcopy(self.event)
        next_occurrence["id"] = "event-next-occurrence"
        next_occurrence["startsAt"] = "2026-10-03T14:00:00+09:00"
        next_occurrence["endsAt"] = "2026-10-03T16:00:00+09:00"
        result = normalize_event_mesh(
            [{"provider": "luma_tokyo", "events": [self.event, next_occurrence]}],
            now=NOW,
        )
        self.assertEqual(result["counts"]["merged"], 2)
        self.assertEqual({event["id"] for event in result["events"]}, {self.event["id"], "event-next-occurrence"})

    def test_stale_deadline_and_2019_event_never_enter_live_candidates(self):
        stale = copy.deepcopy(self.event)
        stale["fetchedAt"] = (NOW - timedelta(hours=3)).isoformat()
        stale["revalidatedAt"] = stale["fetchedAt"]
        deadline = copy.deepcopy(self.event)
        deadline["id"] = "event-deadline"
        deadline["sourceRecordId"] = "deadline"
        deadline["sourceUrl"] = "https://lu.ma/deadline"
        deadline["title"] = "締切済みイベント"
        deadline["registrationDeadline"] = (NOW - timedelta(minutes=1)).isoformat()
        historical = copy.deepcopy(self.event)
        historical["id"] = "event-2019"
        historical["sourceRecordId"] = "2019"
        historical["sourceUrl"] = "https://lu.ma/2019"
        historical["title"] = "2019年イベント"
        historical["startsAt"] = "2019-02-10T10:00:00+09:00"
        historical["endsAt"] = "2019-02-10T12:00:00+09:00"
        result = normalize_event_mesh([{"provider": "luma_tokyo", "events": [stale, deadline, historical]}], now=NOW)
        self.assertEqual(result["eligibleEvents"], [])
        reasons = {item["eventId"]: item["reasons"] for item in result["excludedEvents"]}
        self.assertIn("STALE", reasons[self.event["id"]])
        self.assertIn("DEADLINE_PASSED", reasons["event-deadline"])
        self.assertIn("ENDED_OR_STARTED", reasons["event-2019"])


if __name__ == "__main__":
    unittest.main()
