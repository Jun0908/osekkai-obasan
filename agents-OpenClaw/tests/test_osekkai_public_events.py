from __future__ import annotations

import unittest
from datetime import datetime

from helpers import AGENT_ROOT
from osekkai_contracts import validate_schema
from osekkai_public_events import PublicEventError, parse_course_detail, parse_course_list, sync_kcf_courses


NOW = datetime.fromisoformat("2026-08-23T09:00:00+09:00")
FIXTURES = AGENT_ROOT / "fixtures" / "osekkai" / "public_events"


def fixture(name):
    return (FIXTURES / name).read_bytes()


class PublicEventTests(unittest.TestCase):
    def test_list_parser_keeps_official_status_genre_and_detail_url(self):
        courses = parse_course_list(fixture("kcf-list.html"), page_url="https://www.kcf.or.jp/koza/")
        self.assertEqual(len(courses), 2)
        self.assertEqual(courses[0]["statusText"], "募集中")
        self.assertEqual(courses[0]["genre"], "趣味・実用")
        self.assertEqual(courses[0]["url"], "https://www.kcf.or.jp/higashiojima/koza/detail/?id=3349")

    def test_detail_expands_every_occurrence_and_keeps_capacity_target_price(self):
        result = parse_course_detail(
            fixture("kcf-detail.html"),
            url="https://www.kcf.or.jp/higashiojima/koza/detail/?id=3349",
            status_text="募集中",
            genre="趣味・実用",
            fetched_at=NOW,
        )
        self.assertEqual(len(result["events"]), 3)
        self.assertEqual(result["events"][0]["capacity"], 20)
        self.assertEqual(result["events"][0]["priceYen"], 12000)
        self.assertIn("成人", result["events"][0]["audience"])
        self.assertEqual(len(result["series"][0]["futureOccurrenceIds"]), 3)
        for event in result["events"]:
            validate_schema(event, "event.schema.json")
        validate_schema(result["series"][0], "event-series.schema.json")
        validate_schema(result["communities"][0], "community.schema.json")

    def test_sync_isolates_broken_detail_and_is_not_a_region_filter(self):
        listing = fixture("kcf-list.html")
        detail = fixture("kcf-detail.html")

        def fetcher(url):
            if "/koza/?" in url or url.endswith("/koza/"):
                return listing
            if "id=3349" in url:
                return detail
            raise PublicEventError("fixture failure")

        result = sync_kcf_courses(fetched_at=NOW, max_pages=1, max_details=10, fetcher=fetcher)
        self.assertEqual(len(result["events"]), 3)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["scope"], "official_domain_adapter")

    def test_non_official_domain_is_rejected(self):
        from osekkai_public_events import _safe_kcf_url

        with self.assertRaises(PublicEventError):
            _safe_kcf_url("https://example.com/koza/")


if __name__ == "__main__":
    unittest.main()
