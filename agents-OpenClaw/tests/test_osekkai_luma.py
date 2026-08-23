from __future__ import annotations

import unittest
from datetime import datetime

from helpers import AGENT_ROOT
from osekkai_contracts import validate_schema
from osekkai_luma import LumaError, normalize_ical, sync_configured_calendar


NOW = datetime.fromisoformat("2026-08-23T09:00:00+09:00")
LUMA_FIXTURES = AGENT_ROOT / "fixtures" / "osekkai" / "luma"


def fixture(name):
    return (LUMA_FIXTURES / name).read_bytes()


class LumaTests(unittest.TestCase):
    def normalize(self, name):
        return normalize_ical(
            fixture(name),
            calendar_url="https://lu.ma/test-calendar.ics",
            fetched_at=NOW,
        )

    def test_ical_normalizes_current_events_series_and_community(self):
        result = self.normalize("initial.ics")
        self.assertEqual(result["scope"], "configured_calendar_only")
        self.assertEqual(len(result["events"]), 2)
        self.assertEqual(len(result["series"]), 1)
        self.assertEqual(len(result["communities"]), 1)
        for event in result["events"]:
            validate_schema(event, "event.schema.json")
        validate_schema(result["series"][0], "event-series.schema.json")
        validate_schema(result["communities"][0], "community.schema.json")

    def test_same_uid_updates_time_and_cancellation_in_place(self):
        initial = {event["sourceRecordId"]: event for event in self.normalize("initial.ics")["events"]}
        updated = {event["sourceRecordId"]: event for event in self.normalize("updated-and-canceled.ics")["events"]}
        self.assertEqual(initial["craft-monthly@example.test"]["id"], updated["craft-monthly@example.test"]["id"])
        self.assertNotEqual(initial["craft-monthly@example.test"]["startsAt"], updated["craft-monthly@example.test"]["startsAt"])
        self.assertEqual(updated["meal@example.test"]["status"], "canceled")
        self.assertEqual(updated["meal@example.test"]["registrationStatus"], "closed")

    def test_no_api_key_is_needed_when_authorized_ical_url_exists(self):
        result = sync_configured_calendar(
            environ={"LUMA_ICAL_URL": "https://lu.ma/test-calendar.ics"},
            fetched_at=NOW,
            fetcher=lambda _url: fixture("initial.ics"),
        )
        self.assertEqual(len(result["events"]), 2)

    def test_missing_or_unsafe_calendar_url_is_blocked(self):
        with self.assertRaises(LumaError):
            sync_configured_calendar(environ={}, fetched_at=NOW)
        with self.assertRaises(LumaError):
            sync_configured_calendar(
                environ={"LUMA_ICAL_URL": "http://localhost/calendar.ics"},
                fetched_at=NOW,
                fetcher=lambda _url: fixture("initial.ics"),
            )


if __name__ == "__main__":
    unittest.main()
