from __future__ import annotations

import json
import unittest
from datetime import datetime

from helpers import AGENT_ROOT
from osekkai_contracts import validate_schema
from osekkai_doorkeeper import DoorkeeperClient, DoorkeeperError, DoorkeeperRateLimitError, normalize_events, sync_doorkeeper


NOW = datetime.fromisoformat("2026-08-23T09:00:00+09:00")
FIXTURES = AGENT_ROOT / "fixtures" / "osekkai" / "doorkeeper"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class DoorkeeperTests(unittest.TestCase):
    def test_pagination_query_and_bearer_auth(self):
        calls = []

        def transport(url, headers, _timeout):
            calls.append((url, headers))
            from urllib.parse import parse_qs, urlparse

            if parse_qs(urlparse(url).query)["page"] == ["1"]:
                return 200, {"x-next-page": "2"}, json.dumps(fixture("page1.json"), ensure_ascii=False).encode()
            return 200, {}, json.dumps(fixture("page2.json"), ensure_ascii=False).encode()

        client = DoorkeeperClient("secret-token", transport=transport, sleeper=lambda _delay: None)
        result = client.events(since="2026-08-23", until="2026-12-21", per_page=100)
        self.assertEqual(len(result), 2)
        self.assertIn("prefecture=tokyo", calls[0][0])
        self.assertIn("sort=updated_at", calls[0][0])
        self.assertEqual(calls[0][1]["Authorization"], "Bearer secret-token")

    def test_429_uses_bounded_retry_and_then_recovers(self):
        statuses = [429, 200]
        delays = []

        def transport(_url, _headers, _timeout):
            status = statuses.pop(0)
            return (status, {"retry-after": "1"}, b"[]")

        client = DoorkeeperClient("token", transport=transport, sleeper=delays.append, max_attempts=2)
        self.assertEqual(client.events(since="2026-08-23", until="2026-12-21"), [])
        self.assertEqual(delays, [1.0])

    def test_429_retry_budget_is_fail_closed(self):
        client = DoorkeeperClient(
            "token",
            transport=lambda *_args: (429, {}, b"[]"),
            sleeper=lambda _delay: None,
            max_attempts=2,
        )
        with self.assertRaises(DoorkeeperRateLimitError):
            client.events(since="2026-08-23", until="2026-12-21")

    def test_events_groups_capacity_waitlist_and_continuity_normalize(self):
        result = normalize_events(fixture("page1.json") + fixture("page2.json"), fetched_at=NOW)
        self.assertEqual(len(result["events"]), 2)
        self.assertEqual(len(result["series"]), 1)
        self.assertEqual(result["events"][1]["status"], "sold_out")
        self.assertEqual(result["events"][1]["registrationStatus"], "waitlist")
        for event in result["events"]:
            validate_schema(event, "event.schema.json")
        validate_schema(result["series"][0], "event-series.schema.json")
        validate_schema(result["communities"][0], "community.schema.json")

    def test_missing_token_blocks_only_this_provider(self):
        with self.assertRaises(DoorkeeperError):
            sync_doorkeeper(environ={}, now=NOW)


if __name__ == "__main__":
    unittest.main()
