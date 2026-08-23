from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from helpers import AGENT_ROOT  # Adds the canonical scripts directory to sys.path.
from osekkai_community_directory import format_community_facts, load_community_directory


HEADER = [
    "community_id", "ward_code", "ward_name", "name", "name_kana", "category", "activity_status",
    "description", "source_comment", "target_audience", "target_audience_notes", "venue_name",
    "venue_notes", "venue_address", "official_url", "online_participation", "foreign_language_support",
    "supported_languages", "inbound_program", "notes", "source_updated_at", "fetched_at",
]

FACILITY_DIRECTORY_FIXTURE = {
    "schemaVersion": "1.0",
    "ward": "千代田区",
    "facilities": [
        {
            "key": "kudan",
            "match": "九段",
            "name": "九段生涯学習館",
            "address": "東京都千代田区九段南1-5-10",
            "latitude": 35.695339,
            "longitude": 139.751984,
            "sourceUrl": "https://www.city.chiyoda.lg.jp/shisetsu/bunka/kudan-gakushu.html",
        },
        {
            "key": "sports-center",
            "match": "スポーツセンター",
            "name": "千代田区立スポーツセンター",
            "address": "東京都千代田区内神田2-1-8",
            "latitude": 35.689342,
            "longitude": 139.767685,
            "sourceUrl": "https://www.city.chiyoda.lg.jp/shisetsu/bunka/sportscenter.html",
        },
    ],
}


def row(**overrides: str) -> dict[str, str]:
    return {column: overrides.get(column, "") for column in HEADER}


def write_fixture(directory: Path, rows: list[dict[str, str]]) -> None:
    (directory / "chiyoda-facility-directory.json").write_text(
        json.dumps(FACILITY_DIRECTORY_FIXTURE, ensure_ascii=False), encoding="utf-8"
    )
    with (directory / "communities.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)


class CommunityDirectoryTests(unittest.TestCase):
    def test_groups_chiyoda_communities_by_known_facility_and_geocodes_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [
                    row(community_id="community_1", ward_name="千代田区", name="読書会さくら", description="読書", venue_name="九段;スポーツセンター"),
                    row(community_id="community_2", ward_name="千代田区", name="卓球クラブ", description="スポーツ", venue_name="スポーツセンター"),
                    row(community_id="community_3", ward_name="千代田区", name="行き先不明の会", description="謎", venue_name="未知の施設"),
                    row(community_id="community_4", ward_name="新宿区", name="よその区の会", description="その他", venue_name="九段"),
                ],
            )

            result = load_community_directory("千代田区", data_root=root)

            self.assertEqual(result["ward"], "千代田区")
            self.assertEqual(
                result["counts"],
                {"totalInWard": 3, "withKnownVenue": 2, "withoutKnownVenue": 1},
            )
            self.assertEqual(len(result["facilities"]), 2)

            by_key = {facility["key"]: facility for facility in result["facilities"]}
            kudan = by_key["kudan"]
            self.assertEqual([item["name"] for item in kudan["communities"]], ["読書会さくら"])
            self.assertAlmostEqual(kudan["latitude"], 35.695339, places=5)
            self.assertAlmostEqual(kudan["longitude"], 139.751984, places=5)
            self.assertEqual(kudan["address"], "東京都千代田区九段南1-5-10")

            sports_center = by_key["sports-center"]
            self.assertEqual([item["name"] for item in sports_center["communities"]], ["卓球クラブ"])

    def test_excludes_rows_outside_the_requested_ward(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [row(community_id="community_5", ward_name="新宿区", name="新宿の会", description="謎", venue_name="九段")],
            )

            result = load_community_directory("千代田区", data_root=root)

            self.assertEqual(
                result["counts"],
                {"totalInWard": 0, "withKnownVenue": 0, "withoutKnownVenue": 0},
            )
            self.assertEqual(result["facilities"], [])

    def test_format_community_facts_is_bounded_and_carries_the_unverified_caveat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [
                    row(community_id=f"community_{index}", ward_name="千代田区", name=f"サークル{index}", description="趣味", venue_name="九段")
                    for index in range(5)
                ],
            )

            result = load_community_directory("千代田区", data_root=root)
            facts = format_community_facts(result)

            self.assertEqual(len(facts), 1)
            self.assertIn("九段生涯学習館", facts[0])
            self.assertIn("Open Data", facts[0])
            self.assertIn("未確認", facts[0])
            self.assertLessEqual(len(facts[0]), 300)

    def test_format_community_facts_returns_nothing_for_an_empty_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(root, [])

            result = load_community_directory("千代田区", data_root=root)

            self.assertEqual(format_community_facts(result), [])

    def test_real_repository_csv_matches_the_shared_facility_directory(self):
        # Cross-check against the actual data the map reads, without asserting an exact
        # row count that would make this test brittle as the CSV is refreshed.
        repo_root = AGENT_ROOT.parent / "data" / "tokyo-community"
        result = load_community_directory("千代田区", data_root=repo_root)
        self.assertGreater(result["counts"]["totalInWard"], 0)
        self.assertEqual(result["counts"]["withoutKnownVenue"], 0)
        self.assertGreater(len(result["facilities"]), 0)


if __name__ == "__main__":
    unittest.main()
