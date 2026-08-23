from __future__ import annotations

import copy
import json
import unittest

from helpers import AGENT_ROOT  # Adds the canonical scripts directory to sys.path.
from osekkai_map_events import build_map_events_result


class MapEventsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads((AGENT_ROOT / "fixtures" / "osekkai" / "live-contracts.json").read_text(encoding="utf-8"))
        cls.base_event = fixture["events"][0]

    def event(self, index: int, *, ward: str = "千代田区", located: bool = True):
        event = copy.deepcopy(self.base_event)
        event["id"] = f"map-event-{index:04d}"
        event["sourceRecordId"] = f"map-record-{index:04d}"
        event["title"] = f"Map Event {index:04d}"
        event["address"] = f"東京都{ward}麹町{index % 6 + 1}-1"
        event["venueName"] = "麹町会場"
        event["latitude"] = 35.684 + (index % 20) * 0.0001 if located else None
        event["longitude"] = 139.7373 + (index % 20) * 0.0001 if located else None
        return event

    def test_two_thousand_events_are_filtered_and_paged_before_transport(self):
        events = [self.event(index, located=index % 20 != 0) for index in range(2000)]
        events.extend(self.event(3000 + index, ward="新宿区") for index in range(5))
        result = build_map_events_result(
            {
                "generatedAt": "2026-08-23T13:00:00+09:00",
                "events": events,
                "connectionEvidence": [],
            },
            {"scope": "chiyoda_kojimachi", "offset": 0, "limit": 250},
        )
        self.assertEqual(len(result["events"]), 250)
        self.assertEqual(result["nextOffset"], 250)
        self.assertEqual(result["counts"], {
            "totalInMesh": 2005,
            "inWard": 2000,
            "withCoordinates": 1900,
            "missingCoordinates": 100,
            "returned": 250,
        })
        self.assertLess(len(json.dumps(result, ensure_ascii=False).encode("utf-8")), 512 * 1024)

    def test_venue_name_never_overrides_an_address_outside_chiyoda(self):
        result = build_map_events_result(
            {
                "generatedAt": "2026-08-23T13:00:00+09:00",
                "events": [self.event(1, ward="新宿区")],
                "connectionEvidence": [],
            },
            {"scope": "chiyoda_kojimachi", "offset": 0, "limit": 250},
        )
        self.assertEqual(result["events"], [])
        self.assertEqual(result["counts"]["inWard"], 0)

    def test_next_page_is_contiguous_and_bounded(self):
        events = [self.event(index) for index in range(270)]
        page = build_map_events_result(
            {"generatedAt": "2026-08-23T13:00:00+09:00", "events": events, "connectionEvidence": []},
            {"scope": "chiyoda_kojimachi", "offset": 250, "limit": 250},
        )
        self.assertEqual(len(page["events"]), 20)
        self.assertIsNone(page["nextOffset"])


if __name__ == "__main__":
    unittest.main()
