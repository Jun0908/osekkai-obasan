from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from helpers import AGENT_ROOT, USER_ID
from osekkai_google_credentials import (
    CALENDAR_FREEBUSY_SCOPE,
    GoogleCredentialError,
    GoogleCredentialStore,
    GoogleOAuthConfig,
    access_token,
    complete_authorization,
    create_authorization_request,
    disconnect_google,
)


NOW = datetime.fromisoformat("2026-08-23T09:00:00+09:00")
ENV = {"OSEKKAI_CREDENTIAL_ENCRYPTION_KEY": "test-key-that-is-longer-than-thirty-two-bytes"}
CONFIG = GoogleOAuthConfig("client.apps.googleusercontent.com", "client-secret", "http://localhost:3000/api/osekkai/calendar/callback")


class GoogleCredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = GoogleCredentialStore(Path(self.temp.name), environ=ENV)

    def tearDown(self):
        self.temp.cleanup()

    def test_authorization_uses_state_pkce_and_only_freebusy_scope(self):
        result = create_authorization_request(USER_ID, now=NOW, config=CONFIG, store=self.store)
        query = parse_qs(urlparse(result["authorizationUrl"]).query)
        self.assertEqual(query["scope"], [CALENDAR_FREEBUSY_SCOPE])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertNotIn("code_verifier", query)
        self.assertEqual(query["state"], [result["state"]])

    def test_callback_is_session_bound_one_time_and_encrypted_at_rest(self):
        request = create_authorization_request(USER_ID, now=NOW, config=CONFIG, store=self.store)
        seen = {}

        def exchange(_url, form):
            seen.update(form)
            return {
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
                "expires_in": 3600,
                "scope": CALENDAR_FREEBUSY_SCOPE,
                "token_type": "Bearer",
            }

        result = complete_authorization(
            USER_ID,
            state=request["state"],
            code="authorization-code",
            now=NOW,
            config=CONFIG,
            store=self.store,
            token_transport=exchange,
        )
        self.assertTrue(result["connected"])
        self.assertIn("code_verifier", seen)
        encrypted = b"".join(path.read_bytes() for path in (Path(self.temp.name) / "credentials").glob("*.enc"))
        self.assertNotIn(b"access-secret", encrypted)
        self.assertNotIn(USER_ID.encode(), encrypted)
        with self.assertRaises(GoogleCredentialError):
            complete_authorization(
                USER_ID,
                state=request["state"],
                code="authorization-code",
                now=NOW,
                config=CONFIG,
                store=self.store,
                token_transport=exchange,
            )

    def test_state_rejects_another_session_and_expiration(self):
        request = create_authorization_request(USER_ID, now=NOW, config=CONFIG, store=self.store)
        with self.assertRaises(GoogleCredentialError):
            complete_authorization(
                "22222222-2222-4222-8222-222222222222",
                state=request["state"],
                code="code",
                now=NOW,
                config=CONFIG,
                store=self.store,
                token_transport=lambda *_args: {},
            )
        expired = create_authorization_request(USER_ID, now=NOW, config=CONFIG, store=self.store)
        with self.assertRaises(GoogleCredentialError):
            complete_authorization(
                USER_ID,
                state=expired["state"],
                code="code",
                now=NOW + timedelta(minutes=11),
                config=CONFIG,
                store=self.store,
                token_transport=lambda *_args: {},
            )

    def test_expired_access_token_refreshes_and_disconnect_deletes(self):
        self.store.save_token(
            USER_ID,
            {
                "type": "google_calendar_freebusy_token",
                "accessToken": "old",
                "refreshToken": "refresh",
                "expiresAt": (NOW - timedelta(minutes=1)).isoformat(),
                "scope": CALENDAR_FREEBUSY_SCOPE,
                "tokenType": "Bearer",
                "updatedAt": NOW.isoformat(),
            },
        )
        token = access_token(
            USER_ID,
            now=NOW,
            config=CONFIG,
            store=self.store,
            token_transport=lambda _url, _form: {
                "access_token": "new-access",
                "expires_in": 3600,
                "scope": CALENDAR_FREEBUSY_SCOPE,
                "token_type": "Bearer",
            },
        )
        self.assertEqual(token, "new-access")
        self.assertTrue(disconnect_google(USER_ID, self.store)["disconnected"])
        self.assertIsNone(self.store.load_token(USER_ID))

    def test_profile_delete_also_deletes_encrypted_calendar_credential(self):
        self.store.save_token(
            USER_ID,
            {
                "type": "google_calendar_freebusy_token",
                "accessToken": "access-secret",
                "refreshToken": "refresh-secret",
                "expiresAt": (NOW + timedelta(hours=1)).isoformat(),
                "scope": CALENDAR_FREEBUSY_SCOPE,
                "tokenType": "Bearer",
                "updatedAt": NOW.isoformat(),
            },
        )
        env = os.environ.copy()
        env.update(
            {
                "OSEKKAI_DATA_ROOT": self.temp.name,
                "OSEKKAI_CREDENTIAL_ENCRYPTION_KEY": ENV["OSEKKAI_CREDENTIAL_ENCRYPTION_KEY"],
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            }
        )
        request = {
            "schemaVersion": "1.0",
            "requestId": "profile-delete-calendar-credential",
            "command": "profile-delete",
            "userId": USER_ID,
            "idempotencyKey": "profile-delete-calendar-credential-0001",
            "payload": {"confirm": True},
        }
        completed = subprocess.run(
            [sys.executable, str(AGENT_ROOT / "scripts" / "osekkai_cli.py")],
            input=json.dumps(request).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
            timeout=15,
        )
        response = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        self.assertTrue(response["ok"])
        self.assertTrue(response["data"]["deleted"])
        self.assertIsNone(self.store.load_token(USER_ID))


if __name__ == "__main__":
    unittest.main()
