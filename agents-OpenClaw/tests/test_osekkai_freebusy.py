from __future__ import annotations

import copy
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import demo_inputs
from osekkai_freebusy import _walk_keys
from osekkai_opportunity_sync import _read_json, _source_record, load_opportunities


class ProviderFixtureTests(unittest.TestCase):
    def test_freebusy_has_four_hours_and_no_private_event_fields(self):
        freebusy, _ = demo_inputs()
        self.assertEqual(freebusy["freeWindows"][0]["durationMinutes"], 240)
        self.assertTrue(
            {"title", "summary", "description", "attendees", "location"}.isdisjoint(_walk_keys(freebusy))
        )

    def test_raw_snapshot_checksum_matches_immutable_csv_row(self):
        raw = _read_json("opportunities.raw.json")
        digest = hashlib.sha256(raw["rawCsvRow"].encode("utf-8")).hexdigest()
        self.assertEqual(digest, raw["checksum"])
        self.assertEqual(_source_record(raw)[2], "131083B00016")

    def test_normalized_snapshot_keeps_source_facts_and_marks_derivations(self):
        opportunity = load_opportunities("demo")["opportunities"][0]
        self.assertEqual(opportunity["title"], "亀戸天神梅まつり")
        self.assertEqual(opportunity["startsAt"], "2019-02-10T00:00:00+09:00")
        self.assertEqual(opportunity["roleAvailable"], None)
        self.assertEqual(opportunity["fieldProvenance"]["socialIntensity"]["classification"], "ai_derived")
        self.assertEqual(opportunity["travelEstimate"]["source"], "synthetic_demo")

    def test_live_mode_never_reuses_snapshot(self):
        # A developer may have a real live cache in the default store. Point this
        # test at a deliberately absent cache so it verifies the demo/live
        # boundary without depending on or deleting that local provider data.
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"OSEKKAI_LIVE_OPPORTUNITIES_PATH": str(Path(directory) / "absent-live.json")},
            clear=False,
        ):
            result = load_opportunities("live")
        self.assertEqual(result["dataMode"], "live")
        self.assertEqual(result["opportunities"], [])


if __name__ == "__main__":
    unittest.main()
