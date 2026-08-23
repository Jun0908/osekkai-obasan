from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import NOW, USER_ID
from osekkai_chat import process_chat_unlocked
from osekkai_llm_renderer import RenderOutcome
from osekkai_store import JsonStore


HEADER = [
    "community_id", "ward_code", "ward_name", "name", "name_kana", "category", "activity_status",
    "description", "source_comment", "target_audience", "target_audience_notes", "venue_name",
    "venue_notes", "venue_address", "venue_address_source_url", "venue_address_match_status",
    "area_name", "map_query", "map_location_id", "latitude", "longitude", "geocoded_address",
    "location_precision", "location_source", "location_source_url", "official_url",
    "online_participation", "foreign_language_support", "supported_languages", "inbound_program",
    "notes", "source_updated_at", "fetched_at",
]

WARD_DIRECTORY_FIXTURE = {
    "schemaVersion": "1.0",
    "wards": {
        "千代田区": {
            "wardOffice": {
                "key": "chiyoda-office", "name": "千代田区役所", "address": "東京都千代田区九段南1-6-11",
                "latitude": 35.694138, "longitude": 139.752228, "sourceUrl": "https://www.city.chiyoda.lg.jp/",
            },
        },
    },
}


def _write_directory_fixture(directory: Path) -> None:
    (directory / "ward-geocoding-directory.json").write_text(
        json.dumps(WARD_DIRECTORY_FIXTURE, ensure_ascii=False), encoding="utf-8"
    )
    row = {column: "" for column in HEADER}
    row.update(
        community_id="community_1",
        ward_name="千代田区",
        name="読書会さくら",
        description="読書",
        venue_name="九段生涯学習館",
        map_location_id="map_kudan",
        latitude="35.695339",
        longitude="139.751984",
        geocoded_address="東京都千代田区九段南一丁目5番10号",
    )
    with (directory / "communities.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerow(row)


def _fake_understanding(**_kwargs):
    return {
        "schemaVersion": "1.0",
        "intent": "general",
        "attractions": [],
        "categoryHints": [],
        "participationFrictions": [],
        "explicitness": "explicit",
        "confidence": 0.9,
        "needsClarification": False,
        "suggestedMemoryReferences": [],
        "doNotRemember": False,
        "doNotPush": False,
    }


class ChatCommunityDirectoryWiringTests(unittest.TestCase):
    def _send(self, message: str) -> list[str]:
        """Send one message and return the allowedEventFacts the renderer received."""

        captured: dict[str, list[str]] = {}

        def fake_renderer(plan, **_kwargs):
            captured["facts"] = plan["allowedEventFacts"]
            return RenderOutcome(plan["fallbackReply"], True, None)

        with tempfile.TemporaryDirectory() as store_dir, tempfile.TemporaryDirectory() as data_dir:
            _write_directory_fixture(Path(data_dir))
            store = JsonStore(store_dir)
            with (
                patch("osekkai_chat.understand_message", side_effect=lambda *a, **k: _fake_understanding()),
                patch("osekkai_chat.render_conversation_reply", side_effect=fake_renderer),
                patch.dict("os.environ", {"OSEKKAI_COMMUNITY_DATA_ROOT": data_dir}),
            ):
                process_chat_unlocked(
                    store, USER_ID, {"message": message, "remember": False}, NOW, "demo"
                )
        return captured.get("facts", [])

    def test_a_community_related_message_surfaces_open_data_facts(self):
        facts = self._send("九段について教えて")
        self.assertEqual(len(facts), 1)
        self.assertIn("九段生涯学習館", facts[0])
        self.assertIn("Open Data", facts[0])
        self.assertIn("未確認", facts[0])

    def test_an_unrelated_message_never_fetches_community_facts(self):
        self.assertEqual(self._send("こんにちは"), [])


if __name__ == "__main__":
    unittest.main()
