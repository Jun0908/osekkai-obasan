from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import AGENT_ROOT
from osekkai_freebusy import ProviderError
from osekkai_opportunity_sync import events_to_opportunities, load_opportunities


class OpportunitySyncTests(unittest.TestCase):
    def fixture(self):
        return json.loads((AGENT_ROOT / "fixtures" / "osekkai" / "live-contracts.json").read_text(encoding="utf-8"))

    def test_event_requires_connection_and_real_maps_before_opportunity(self):
        fixture = self.fixture()
        event = fixture["events"][0]
        opportunities, excluded = events_to_opportunities(
            [event], connection_by_event_id={}, route_by_event_id={}
        )
        self.assertEqual(opportunities, [])
        self.assertEqual(excluded[0]["reasons"], ["CONNECTION_EVIDENCE_MISSING", "MAPS_ROUTE_MISSING"])

    def test_verified_event_evidence_and_maps_make_live_opportunity(self):
        fixture = self.fixture()
        event = fixture["events"][0]
        connection = fixture["connectionEvidence"][0]
        route = {
            "mode": "walk",
            "minutes": 8,
            "source": "maps_verified",
            "computedAt": "2026-08-23T08:15:00+09:00",
            "distanceMeters": 620,
            "confidence": 1,
            "resolvedAddress": event["address"],
            "latitude": event["latitude"],
            "longitude": event["longitude"],
        }
        opportunities, excluded = events_to_opportunities(
            [event],
            connection_by_event_id={event["id"]: connection},
            route_by_event_id={event["id"]: route},
        )
        self.assertEqual(excluded, [])
        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0]["dataMode"], "live")
        self.assertEqual(opportunities[0]["travelEstimate"]["source"], "maps_verified")

    def test_unknown_price_is_preserved_instead_of_invented_or_hard_rejected(self):
        fixture = self.fixture()
        event = {**fixture["events"][0], "priceYen": None}
        connection = fixture["connectionEvidence"][0]
        route = {
            "mode": "walk",
            "minutes": 8,
            "source": "maps_verified",
            "computedAt": "2026-08-23T08:15:00+09:00",
            "distanceMeters": 620,
            "confidence": 1,
            "resolvedAddress": event["address"],
            "latitude": event["latitude"],
            "longitude": event["longitude"],
        }
        opportunities, excluded = events_to_opportunities(
            [event],
            connection_by_event_id={event["id"]: connection},
            route_by_event_id={event["id"]: route},
        )
        self.assertEqual(excluded, [])
        self.assertIsNone(opportunities[0]["priceYen"])

    def test_long_provider_description_is_bounded_without_stopping_materialization(self):
        fixture = self.fixture()
        event = {**fixture["events"][0], "description": "<p>交流イベントの説明</p>" * 1000}
        connection = fixture["connectionEvidence"][0]
        route = {
            "mode": "walk",
            "minutes": 8,
            "source": "maps_verified",
            "computedAt": "2026-08-23T08:15:00+09:00",
            "distanceMeters": 620,
            "confidence": 1,
            "resolvedAddress": event["address"],
            "latitude": event["latitude"],
            "longitude": event["longitude"],
        }
        opportunities, excluded = events_to_opportunities(
            [event],
            connection_by_event_id={event["id"]: connection},
            route_by_event_id={event["id"]: route},
        )
        self.assertEqual(excluded, [])
        self.assertEqual(len(opportunities), 1)
        self.assertLessEqual(len(opportunities[0]["description"]), 3000)
        self.assertTrue(opportunities[0]["description"].endswith("全文はSourceを確認］"))

    def test_invalid_provider_record_is_excluded_without_aborting_other_events(self):
        fixture = self.fixture()
        valid_event = fixture["events"][0]
        invalid_event = {**fixture["events"][1], "sourceRecordId": "x" * 161}
        connection_by_id = {
            valid_event["id"]: fixture["connectionEvidence"][0],
            invalid_event["id"]: fixture["connectionEvidence"][1],
        }

        def route(event):
            return {
                "mode": "walk",
                "minutes": 8,
                "source": "maps_verified",
                "computedAt": "2026-08-23T08:15:00+09:00",
                "distanceMeters": 620,
                "confidence": 1,
                "resolvedAddress": event["address"],
                "latitude": event["latitude"],
                "longitude": event["longitude"],
            }

        opportunities, excluded = events_to_opportunities(
            [valid_event, invalid_event],
            connection_by_event_id=connection_by_id,
            route_by_event_id={valid_event["id"]: route(valid_event), invalid_event["id"]: route(invalid_event)},
        )
        self.assertEqual([item["eventId"] for item in opportunities], [valid_event["id"]])
        self.assertEqual(
            excluded,
            [{"eventId": invalid_event["id"], "reasons": ["OPPORTUNITY_CONTRACT_INVALID"]}],
        )

    def test_route_longer_than_opportunity_contract_is_excluded_without_aborting_sync(self):
        fixture = self.fixture()
        event = fixture["events"][0]
        connection = fixture["connectionEvidence"][0]
        route = {
            "mode": "walk",
            "minutes": 754,
            "source": "maps_verified",
            "computedAt": "2026-08-23T08:15:00+09:00",
            "distanceMeters": 50000,
            "confidence": 1,
            "resolvedAddress": event["address"],
        }
        opportunities, excluded = events_to_opportunities(
            [event],
            connection_by_event_id={event["id"]: connection},
            route_by_event_id={event["id"]: route},
        )
        self.assertEqual(opportunities, [])
        self.assertEqual(excluded[0]["reasons"], ["MAPS_ROUTE_TOO_LONG"])

    def test_live_cache_rejects_historical_demo_fixture(self):
        demo = json.loads((AGENT_ROOT / "fixtures" / "osekkai" / "opportunities.normalized.json").read_text(encoding="utf-8"))
        demo["dataMode"] = "live"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "live.json"
            path.write_text(json.dumps(demo, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"OSEKKAI_LIVE_OPPORTUNITIES_PATH": str(path)}, clear=False):
                with self.assertRaises(ProviderError):
                    load_opportunities("live")


if __name__ == "__main__":
    unittest.main()
