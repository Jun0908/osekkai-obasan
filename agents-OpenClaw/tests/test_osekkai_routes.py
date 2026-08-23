from __future__ import annotations

import json
import unittest
from datetime import datetime

from helpers import AGENT_ROOT
from osekkai_routes import RoutesError, compute_event_route, feasible_free_windows


NOW = datetime.fromisoformat("2026-08-23T10:00:00+09:00")


def fixture(name: str):
    return json.loads((AGENT_ROOT / "fixtures" / "osekkai" / name).read_text(encoding="utf-8"))


class GoogleRoutesTests(unittest.TestCase):
    def setUp(self):
        self.origin = {"latitude": 35.6812, "longitude": 139.7671}
        self.event = {
            "startsAt": "2026-08-23T14:00:00+09:00",
            "endsAt": "2026-08-23T15:00:00+09:00",
            "address": "東京都江東区東陽4丁目11-3",
        }
        self.env = {"GOOGLE_ROUTES_API_KEY": "test-key", "OSEKKAI_ROUTES_TIMEOUT_SECONDS": "5"}

    def test_uses_verified_walk_route_and_geocoded_location(self):
        calls = []

        def route_transport(_key, payload):
            calls.append(payload)
            return fixture("google-routes-walk.json") if payload["travelMode"] == "WALK" else fixture("google-routes-transit.json")

        result = compute_event_route(
            self.origin,
            self.event,
            departure_time=NOW,
            environ=self.env,
            route_transport=route_transport,
            geocode_transport=lambda _key, _address: fixture("google-geocode.json"),
        )
        self.assertEqual(result["mode"], "walk")
        self.assertEqual(result["minutes"], 9)
        self.assertEqual(result["source"], "maps_verified")
        self.assertEqual(result["confidence"], 0.9)
        self.assertEqual({call["travelMode"] for call in calls}, {"WALK", "TRANSIT"})

    def test_coordinate_event_skips_geocoding(self):
        event = {**self.event, "latitude": 35.67, "longitude": 139.82}
        result = compute_event_route(
            self.origin,
            event,
            departure_time=NOW,
            modes=("walk",),
            environ=self.env,
            route_transport=lambda _key, _payload: fixture("google-routes-walk.json"),
            geocode_transport=lambda *_args: self.fail("geocoder should not be called"),
        )
        self.assertEqual(result["confidence"], 1.0)

    def test_zero_results_and_quota_are_classified(self):
        with self.assertRaisesRegex(RoutesError, "no walk route") as failure:
            compute_event_route(
                self.origin,
                {**self.event, "latitude": 35.67, "longitude": 139.82},
                departure_time=NOW,
                modes=("walk",),
                environ=self.env,
                route_transport=lambda *_args: {"routes": []},
            )
        self.assertEqual(failure.exception.code, "ROUTES_ZERO_RESULTS")

        def quota(*_args):
            raise RoutesError("ROUTES_QUOTA_EXCEEDED", "quota")

        with self.assertRaises(RoutesError) as quota_failure:
            compute_event_route(
                self.origin,
                {**self.event, "latitude": 35.67, "longitude": 139.82},
                departure_time=NOW,
                environ=self.env,
                route_transport=quota,
            )
        self.assertEqual(quota_failure.exception.code, "ROUTES_QUOTA_EXCEEDED")

    def test_free_window_requires_round_trip_visit_and_buffer(self):
        route = {"source": "maps_verified", "mode": "walk", "minutes": 9}
        windows = [
            {
                "id": "too-short",
                "start": "2026-08-23T13:45:00+09:00",
                "end": "2026-08-23T15:15:00+09:00",
                "durationMinutes": 90,
                "verificationStatus": "source_verified",
            },
            {
                "id": "fits",
                "start": "2026-08-23T13:30:00+09:00",
                "end": "2026-08-23T15:30:00+09:00",
                "durationMinutes": 120,
                "verificationStatus": "source_verified",
            },
        ]
        result = feasible_free_windows(self.event, route, windows, buffer_minutes=10)
        self.assertEqual([window["id"] for window in result], ["fits"])
        self.assertEqual(result[0]["roundTripMinutes"], 18)
        self.assertEqual(result[0]["requiredMinutes"], 88)


if __name__ == "__main__":
    unittest.main()
