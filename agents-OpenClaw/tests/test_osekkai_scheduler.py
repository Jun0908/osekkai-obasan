from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from helpers import AGENT_ROOT
from osekkai_luma import LumaError
from osekkai_scheduler import load_event_mesh, load_source_status, run_sync, sync_before_push
from osekkai_store import JsonStore


NOW = datetime.fromisoformat("2026-08-23T09:00:00+09:00")


def source(source_id: str, *, credential_env=None):
    return {
        "id": source_id,
        "displayName": source_id,
        "enabled": True,
        "authorized": True,
        "requiredForDemo": True,
        "credentialEnv": credential_env or [],
        "refreshMinutes": 15,
        "staleAfterMinutes": 120,
    }


def provider_fixture(provider: str):
    value = json.loads((AGENT_ROOT / "fixtures" / "osekkai" / "live-contracts.json").read_text(encoding="utf-8"))
    events = [event for event in value["events"] if event["provider"] == provider]
    event_ids = {event["id"] for event in events}
    series = [item for item in value["series"] if item["provider"] == provider]
    communities = [item for item in value["communities"] if item["provider"] == provider]
    return {
        "schemaVersion": "1.0",
        "provider": provider,
        "fetchedAt": NOW.isoformat(),
        "events": events,
        "series": series,
        "communities": communities,
        "errors": [],
        "fixtureEventIds": list(event_ids),
    }


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = JsonStore(self.temporary.name)
        self.sources = [source("luma_tokyo"), source("doorkeeper")]
        self.env = {
            "OSEKKAI_LIVE_ORIGIN_LATITUDE": "35.6812",
            "OSEKKAI_LIVE_ORIGIN_LONGITUDE": "139.7671",
            "OSEKKAI_MAX_ROUTE_CANDIDATES": "10",
        }

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def route(_origin, event, now):
        return {
            "mode": "walk",
            "minutes": 8,
            "source": "maps_verified",
            "computedAt": now.isoformat(),
            "distanceMeters": 620,
            "confidence": 1,
            "resolvedAddress": event.get("address") or event.get("venueName"),
            "latitude": event.get("latitude") or 35.67,
            "longitude": event.get("longitude") or 139.82,
        }

    def test_one_provider_failure_does_not_stop_event_mesh(self):
        result = run_sync(
            store=self.store,
            now=NOW,
            force=True,
            adapters={
                "luma_tokyo": lambda _now: provider_fixture("luma_tokyo"),
                "doorkeeper": lambda _now: (_ for _ in ()).throw(LumaError("temporary failure")),
            },
            source_definitions=self.sources,
            environ=self.env,
            route_resolver=self.route,
            attempts=1,
            sleeper=lambda _seconds: None,
        )
        states = {item["id"]: item for item in result["sources"]}
        self.assertEqual(states["luma_tokyo"]["health"], "healthy")
        self.assertEqual(states["doorkeeper"]["health"], "error")
        self.assertGreater(result["counts"]["events"], 0)
        mesh = load_event_mesh(store=self.store)
        self.assertEqual(len(mesh["events"]), result["counts"]["events"])
        self.assertIn("connectionEvidence", mesh)

    def test_refresh_interval_skips_adapter_until_due(self):
        calls = []

        def adapter(_now):
            calls.append(1)
            return provider_fixture("luma_tokyo")

        kwargs = dict(
            store=self.store,
            adapters={"luma_tokyo": adapter},
            source_definitions=[source("luma_tokyo")],
            environ=self.env,
            route_resolver=self.route,
            sleeper=lambda _seconds: None,
        )
        run_sync(now=NOW, **kwargs)
        run_sync(now=NOW + timedelta(minutes=5), **kwargs)
        run_sync(now=NOW + timedelta(minutes=16), **kwargs)
        self.assertEqual(len(calls), 2)

    def test_status_reports_missing_credential_without_syncing(self):
        result = run_sync(
            store=self.store,
            now=NOW,
            source_definitions=[source("luma_tokyo", credential_env=["LUMA_ICAL_URL"])],
            environ=self.env,
            adapters={"luma_tokyo": lambda _now: self.fail("must not sync")},
            route_resolver=self.route,
        )
        self.assertEqual(result["sources"][0]["health"], "credential_missing")
        cached = load_source_status(store=self.store)
        self.assertEqual(cached["sources"][0]["readiness"], "credential_missing")

    def test_ckan_timeout_isolated_from_a_healthy_provider(self):
        result = run_sync(
            store=self.store,
            now=NOW,
            force=True,
            adapters={
                "tokyo_ckan": lambda _now: (_ for _ in ()).throw(TimeoutError("catalog timeout")),
                "luma_tokyo": lambda _now: provider_fixture("luma_tokyo"),
            },
            source_definitions=[source("tokyo_ckan"), source("luma_tokyo")],
            environ=self.env,
            route_resolver=self.route,
            attempts=1,
            sleeper=lambda _seconds: None,
        )
        states = {item["id"]: item for item in result["sources"]}
        self.assertEqual(states["tokyo_ckan"]["health"], "error")
        self.assertEqual(states["luma_tokyo"]["health"], "healthy")
        self.assertGreater(result["counts"]["events"], 0)

    def test_push_revalidation_rejects_an_event_canceled_after_ranking(self):
        run_sync(
            store=self.store,
            now=NOW,
            force=True,
            adapters={"luma_tokyo": lambda _now: provider_fixture("luma_tokyo")},
            source_definitions=[source("luma_tokyo")],
            environ=self.env,
            route_resolver=self.route,
        )
        mesh = load_event_mesh(store=self.store)
        event_id = next(event["id"] for event in mesh["events"] if event["provider"] == "luma_tokyo")

        def cancel_during_refresh(**_kwargs):
            updated = load_event_mesh(store=self.store)
            for event in updated["events"]:
                if event["id"] == event_id:
                    event["status"] = "canceled"
                    event["registrationStatus"] = "closed"
            self.store._atomic_write_json(
                self.store._safe_path("opportunities", "live-event-mesh.json"),
                updated,
            )
            return {
                "sources": [
                    {"id": "luma_tokyo", "health": "healthy", "lastSuccessAt": NOW.isoformat()}
                ]
            }

        with patch("osekkai_scheduler.run_sync", side_effect=cancel_during_refresh):
            result = sync_before_push([event_id], store=self.store, now=NOW, environ=self.env)
        self.assertFalse(result[event_id])


if __name__ == "__main__":
    unittest.main()
