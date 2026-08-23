from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from helpers import AGENT_ROOT, USER_ID
from osekkai_freebusy import ProviderError, free_windows_from_response, query_google_freebusy
from osekkai_google_credentials import CALENDAR_FREEBUSY_SCOPE, GoogleCredentialStore, GoogleOAuthConfig


NOW = datetime.fromisoformat("2026-09-05T09:00:00+09:00")
END = datetime.fromisoformat("2026-09-05T20:00:00+09:00")
ENV = {"OSEKKAI_CREDENTIAL_ENCRYPTION_KEY": "test-key-that-is-longer-than-thirty-two-bytes"}
CONFIG = GoogleOAuthConfig("client", "secret", "http://localhost:3000/api/osekkai/calendar/callback")


class GoogleFreeBusyTests(unittest.TestCase):
    def fixture(self):
        return json.loads((AGENT_ROOT / "fixtures" / "osekkai" / "google-freebusy-response.json").read_text(encoding="utf-8"))

    def test_freebusy_fixture_becomes_privacy_minimal_windows(self):
        result = free_windows_from_response(self.fixture(), time_min=NOW, time_max=END, generated_at=NOW)
        self.assertEqual(result["dataMode"], "live")
        self.assertEqual([window["durationMinutes"] for window in result["freeWindows"]], [120, 300, 90])
        serialized = json.dumps(result).lower()
        for forbidden in ("title", "summary", "description", "attendees", "location"):
            self.assertNotIn(f'"{forbidden}"', serialized)

    def test_query_sends_only_primary_and_freebusy_time_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            store = GoogleCredentialStore(Path(directory), environ=ENV)
            store.save_token(
                USER_ID,
                {
                    "type": "google_calendar_freebusy_token",
                    "accessToken": "access-token",
                    "refreshToken": "refresh-token",
                    "expiresAt": (NOW + timedelta(hours=1)).isoformat(),
                    "scope": CALENDAR_FREEBUSY_SCOPE,
                    "tokenType": "Bearer",
                    "updatedAt": NOW.isoformat(),
                },
            )
            captured = {}

            def api_transport(token, payload):
                captured.update({"token": token, "payload": payload})
                return self.fixture()

            result = query_google_freebusy(
                USER_ID,
                time_min=NOW,
                time_max=END,
                generated_at=NOW,
                config=CONFIG,
                credential_store=store,
                api_transport=api_transport,
            )
            self.assertEqual(captured["token"], "access-token")
            self.assertEqual(captured["payload"]["items"], [{"id": "primary"}])
            self.assertEqual(set(captured["payload"]), {"timeMin", "timeMax", "timeZone", "items"})
            self.assertEqual(len(result["freeWindows"]), 3)

    def test_empty_calendar_accepts_the_full_live_horizon(self):
        end = NOW + timedelta(days=30)
        result = free_windows_from_response(
            {"calendars": {"primary": {"busy": []}}},
            time_min=NOW,
            time_max=end,
            generated_at=NOW,
        )
        self.assertEqual(len(result["freeWindows"]), 1)
        self.assertEqual(result["freeWindows"][0]["durationMinutes"], 30 * 24 * 60)

    def test_event_detail_fields_and_calendar_errors_fail_closed(self):
        detailed = self.fixture()
        detailed["calendars"]["primary"]["busy"][0]["summary"] = "private"
        with self.assertRaises(ProviderError):
            free_windows_from_response(detailed, time_min=NOW, time_max=END, generated_at=NOW)
        errored = self.fixture()
        errored["calendars"]["primary"]["errors"] = [{"reason": "notFound"}]
        with self.assertRaises(ProviderError):
            free_windows_from_response(errored, time_min=NOW, time_max=END, generated_at=NOW)


if __name__ == "__main__":
    unittest.main()
