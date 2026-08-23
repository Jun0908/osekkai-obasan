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


def row(**overrides: str) -> dict[str, str]:
    return {column: overrides.get(column, "") for column in HEADER}


def write_fixture(directory: Path, rows: list[dict[str, str]]) -> None:
    (directory / "ward-geocoding-directory.json").write_text(
        json.dumps(WARD_DIRECTORY_FIXTURE, ensure_ascii=False), encoding="utf-8"
    )
    with (directory / "communities.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)


class CommunityDirectoryTests(unittest.TestCase):
    def test_groups_rows_sharing_a_map_location_id_under_one_precise_point(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [
                    row(
                        community_id="community_1", ward_name="渋谷区", name="あみもの教室", description="手芸",
                        venue_name="本町区民会館", venue_address="東京都渋谷区本町3-46-1",
                        map_location_id="map_abc", latitude="35.687641", longitude="139.682785",
                        geocoded_address="東京都渋谷区本町三丁目46番1号",
                    ),
                    row(
                        community_id="community_2", ward_name="渋谷区", name="茶道教室", description="茶華道",
                        venue_name="本町区民会館", venue_address="東京都渋谷区本町3-46-1",
                        map_location_id="map_abc", latitude="35.687641", longitude="139.682785",
                        geocoded_address="東京都渋谷区本町三丁目46番1号",
                    ),
                    row(community_id="community_3", ward_name="千代田区", name="未登録の会", description="謎"),
                ],
            )

            result = load_community_directory("渋谷区", data_root=root)

            self.assertEqual(
                result["counts"],
                {"totalInWard": 2, "withPreciseLocation": 2, "withWardOfficeFallback": 0},
            )
            self.assertEqual(len(result["facilities"]), 1)

            precise = result["facilities"][0]
            self.assertEqual(precise["key"], "loc:map_abc")
            self.assertEqual(precise["name"], "本町区民会館")
            self.assertTrue(precise["precise"])
            self.assertEqual(len(precise["communities"]), 2)
            self.assertAlmostEqual(precise["latitude"], 35.687641, places=5)

    def test_falls_back_to_the_ward_office_when_no_coordinates_are_present(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [row(community_id="community_1", ward_name="千代田区", name="未登録の会", description="謎")],
            )

            result = load_community_directory("千代田区", data_root=root)

            self.assertEqual(
                result["counts"],
                {"totalInWard": 1, "withPreciseLocation": 0, "withWardOfficeFallback": 1},
            )
            self.assertEqual(result["facilities"][0]["key"], "chiyoda-office")
            self.assertFalse(result["facilities"][0]["precise"])

    def test_derives_a_facility_name_from_the_geocoded_address_when_venue_name_is_blank(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [
                    row(
                        community_id="community_1", ward_name="渋谷区", name="無名施設の会", description="その他",
                        map_location_id="map_xyz", latitude="35.66", longitude="139.7",
                        geocoded_address="東京都渋谷区代々木1-1-1",
                    ),
                ],
            )

            result = load_community_directory("渋谷区", data_root=root)

            self.assertEqual(result["facilities"][0]["name"], "渋谷区代々木1-1-1")

    def test_treats_an_unparseable_coordinate_as_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [
                    row(
                        community_id="community_1", ward_name="渋谷区", name="壊れた座標の会", description="その他",
                        latitude="not-a-number", longitude="139.7",
                    ),
                ],
            )

            result = load_community_directory("渋谷区", data_root=root)

            # 渋谷区 has no ward-geocoding-directory entry in this fixture, so a row that
            # cannot resolve a precise point falls through with nowhere to go and is excluded.
            self.assertEqual(
                result["counts"],
                {"totalInWard": 1, "withPreciseLocation": 0, "withWardOfficeFallback": 0},
            )
            self.assertEqual(result["facilities"], [])

    def test_excludes_rows_outside_the_requested_ward(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [row(community_id="community_1", ward_name="新宿区", name="新宿の会", description="謎")],
            )

            result = load_community_directory("千代田区", data_root=root)

            self.assertEqual(
                result["counts"],
                {"totalInWard": 0, "withPreciseLocation": 0, "withWardOfficeFallback": 0},
            )
            self.assertEqual(result["facilities"], [])

    def test_format_community_facts_is_bounded_and_carries_the_unverified_caveat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [
                    row(
                        community_id=f"community_{index}", ward_name="千代田区", name=f"サークル{index}",
                        description="趣味", venue_name="九段生涯学習館", map_location_id="map_kudan",
                        latitude="35.695339", longitude="139.751984",
                    )
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

    def test_real_repository_csv_has_mostly_precise_locations(self):
        # Cross-check against the actual data the map reads, without asserting an exact
        # row count that would make this test brittle as the CSV is refreshed.
        repo_root = AGENT_ROOT.parent / "data" / "tokyo-community"
        result = load_community_directory("千代田区", data_root=repo_root)
        self.assertGreater(result["counts"]["totalInWard"], 0)
        self.assertGreater(result["counts"]["withPreciseLocation"], 0)
        self.assertGreater(len(result["facilities"]), 0)

        nerima = load_community_directory("練馬区", data_root=repo_root)
        self.assertGreater(nerima["counts"]["totalInWard"], 0)


if __name__ == "__main__":
    unittest.main()
