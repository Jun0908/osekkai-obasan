from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import helpers  # noqa: F401  # Adds the canonical scripts directory to sys.path.
from osekkai_contracts import ContractError
from osekkai_source_registry import (
    CONFIG_PATH,
    is_stale,
    load_source_registry,
    source_by_id,
    sources_for_sync,
    stale_at,
)


class SourceRegistryTests(unittest.TestCase):
    def test_required_and_optional_sources_are_explicit(self):
        registry = load_source_registry(environ={})
        sources = {source["id"]: source for source in registry["sources"]}
        self.assertTrue({"tokyo_ckan", "luma_tokyo", "doorkeeper", "koto_culture"} <= set(sources))
        self.assertTrue({"connpass", "peatix_intake", "timeleft", "kitchhike"} <= set(sources))
        self.assertTrue(sources["tokyo_ckan"]["enabled"])
        self.assertFalse(sources["connpass"]["enabled"])

    def test_enabled_authorized_and_credential_ready_are_separate(self):
        empty = load_source_registry(environ={})
        states = {status["id"]: status for status in empty["statuses"]}
        self.assertEqual(states["tokyo_ckan"]["state"], "ready")
        self.assertEqual(states["koto_culture"]["state"], "ready")
        self.assertEqual(states["luma_tokyo"]["state"], "credential_missing")
        self.assertEqual(states["doorkeeper"]["state"], "credential_missing")
        self.assertEqual(states["connpass"]["state"], "disabled")
        ready = {source["id"] for source in sources_for_sync(environ={"LUMA_ICAL_URL": "https://example.test/tokyo.ics"})}
        self.assertIn("luma_tokyo", ready)
        self.assertNotIn("doorkeeper", ready)

    def test_registry_contains_env_names_but_no_secret_values(self):
        raw = CONFIG_PATH.read_text(encoding="utf-8")
        self.assertIn("DOORKEEPER_API_TOKEN", raw)
        self.assertNotIn("Bearer ", raw)
        self.assertNotIn("client_secret", raw.lower())
        for source in load_source_registry(environ={})["sources"]:
            self.assertTrue(source["termsUrl"])
            self.assertTrue(source["attribution"])

    def test_unknown_or_malformed_source_is_fail_closed(self):
        with self.assertRaises(ContractError):
            source_by_id("not-registered")
        registry = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        registry["sources"][0]["staleAfterMinutes"] = 5
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaises(ContractError):
                load_source_registry(path, environ={})

    def test_stale_threshold_is_owned_by_registry(self):
        source = source_by_id("luma_tokyo")
        fetched = "2026-08-23T08:00:00+09:00"
        self.assertEqual(stale_at(source, fetched), "2026-08-23T10:00:00+09:00")
        parsed = datetime.fromisoformat(fetched)
        self.assertFalse(is_stale(source, fetched, parsed + timedelta(minutes=119)))
        self.assertTrue(is_stale(source, fetched, parsed + timedelta(minutes=120)))


if __name__ == "__main__":
    unittest.main()
