from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime

from helpers import AGENT_ROOT
from osekkai_connection import extract_connection_evidence


NOW = datetime.fromisoformat("2026-08-23T09:00:00+09:00")


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        fixture = json.loads((AGENT_ROOT / "fixtures" / "osekkai" / "live-contracts.json").read_text(encoding="utf-8"))
        self.base = fixture["events"][0]

    def event(self, title, description):
        value = copy.deepcopy(self.base)
        value["id"] = f"event-{len(title)}-{abs(hash(title)) % 100000}"
        value["sourceRecordId"] = value["id"]
        value["title"] = title
        value["description"] = description
        value["sourceUrl"] = f"https://lu.ma/{value['id']}"
        return value

    def test_monthly_hobby_with_next_event_and_welcome_is_level_three(self):
        event = self.event("月例クラフト会", "初心者歓迎・ひとり参加歓迎。参加者同士で共同制作します。")
        series = {
            "futureOccurrenceIds": ["next-1", "next-2"],
            "sourceUrl": event["sourceUrl"],
            "evidence": [{"text": "翌月回が公開済み", "url": event["sourceUrl"], "classification": "live_provider", "capturedAt": event["fetchedAt"], "confidence": 1, "evidenceField": "calendar"}],
        }
        result = extract_connection_evidence(event, evaluated_at=NOW, series=series)
        self.assertEqual(result["connectionLevel"], 3)
        self.assertEqual(result["soloFriendly"], "yes")
        self.assertEqual(result["futureOccurrenceCount"], 2)

    def test_single_lecture_and_large_exhibition_are_not_connection_candidates(self):
        lecture = self.event("単発講演", "講師による90分の講演を聴講します。")
        expo = self.event("大型展示会", "会場内の展示を自由に観覧できます。")
        self.assertEqual(extract_connection_evidence(lecture, evaluated_at=NOW)["connectionLevel"], 0)
        self.assertEqual(extract_connection_evidence(expo, evaluated_at=NOW)["connectionLevel"], 0)

    def test_networking_word_alone_does_not_raise_score_and_sales_is_high_risk(self):
        plain = self.event("Tokyo Networking", "Networking eventです。")
        sales = self.event("名刺交換会", "営業目的の名刺交換会。不動産投資の商談があります。")
        self.assertEqual(extract_connection_evidence(plain, evaluated_at=NOW)["connectionLevel"], 0)
        sales_result = extract_connection_evidence(sales, evaluated_at=NOW)
        self.assertEqual(sales_result["connectionLevel"], 0)
        self.assertEqual(sales_result["solicitationRisk"], "high")

    def test_shared_meal_and_recurring_volunteer_have_grounded_evidence(self):
        meal = self.event("みんなで夕ごはん", "少人数で一緒に食事をし、初参加歓迎です。")
        volunteer = self.event("定期開催の地域ボランティア", "運営メンバーとして受付を担当。初心者歓迎です。")
        meal_result = extract_connection_evidence(meal, evaluated_at=NOW, community={"futureEventIds": ["meal-next"]})
        volunteer_result = extract_connection_evidence(volunteer, evaluated_at=NOW)
        self.assertEqual(meal_result["sharedMeal"], "yes")
        self.assertGreaterEqual(meal_result["connectionLevel"], 2)
        self.assertEqual(volunteer_result["roleAvailable"], "yes")
        self.assertGreaterEqual(volunteer_result["connectionLevel"], 2)

    def test_unsupported_claims_remain_unknown_and_short_evidence_has_url(self):
        event = self.event("静かな読書会", "本を持参して各自で読みます。")
        result = extract_connection_evidence(event, evaluated_at=NOW)
        self.assertEqual(result["soloFriendly"], "unknown")
        self.assertEqual(result["recurring"], "unknown")
        self.assertTrue(all(item["url"].startswith("https://") and len(item["text"]) <= 500 for item in result["evidence"]))


if __name__ == "__main__":
    unittest.main()
