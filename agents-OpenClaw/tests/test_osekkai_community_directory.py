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
    "area_name", "map_location_id", "latitude", "longitude", "geocoded_address",
    "location_precision", "location_source", "location_source_url",
    "supported_languages", "inbound_program", "notes", "source_updated_at", "fetched_at",
]

WARD_DIRECTORY_FIXTURE = {
    "schemaVersion": "1.0",
    "wards": {
        "千代田区": {
            "wardOffice": {
                "key": "chiyoda-office", "name": "千代田区役所", "address": "東京都千代田区九段南1-6-11",
                "latitude": 35.694138, "longitude": 139.752228, "sourceUrl": "https://www.city.chiyoda.lg.jp/",
            },
            "anchors": [
                {
                    "key": "kudan", "match": "九段", "name": "九段生涯学習館", "address": "東京都千代田区九段南1-5-10",
                    "latitude": 35.695339, "longitude": 139.751984,
                    "sourceUrl": "https://www.city.chiyoda.lg.jp/shisetsu/bunka/kudan-gakushu.html",
                },
                {
                    "key": "sports-center", "match": "スポーツセンター", "name": "千代田区立スポーツセンター",
                    "address": "東京都千代田区内神田2-1-8", "latitude": 35.689342, "longitude": 139.767685,
                    "sourceUrl": "https://www.city.chiyoda.lg.jp/shisetsu/bunka/sportscenter.html",
                },
            ],
        },
        "新宿区": {
            "wardOffice": {
                "key": "shinjuku-office", "name": "新宿区役所", "address": "東京都新宿区歌舞伎町1-4-1",
                "latitude": 35.693535, "longitude": 139.703476, "sourceUrl": "https://www.city.shinjuku.lg.jp/",
            },
            "anchors": [],
        },
    },
}


VENUE_ADDRESS_DIRECTORY_FIXTURE = {
    "schemaVersion": "1.0",
    "addresses": {
        "東京都渋谷区本町3-46-1": {"ward": "渋谷区", "latitude": 35.687641, "longitude": 139.682785},
    },
}


def row(**overrides: str) -> dict[str, str]:
    return {column: overrides.get(column, "") for column in HEADER}


def write_fixture(
    directory: Path,
    rows: list[dict[str, str]],
    address_fixture: dict | None = None,
) -> None:
    (directory / "ward-geocoding-directory.json").write_text(
        json.dumps(WARD_DIRECTORY_FIXTURE, ensure_ascii=False), encoding="utf-8"
    )
    (directory / "venue-address-directory.json").write_text(
        json.dumps(address_fixture if address_fixture is not None else VENUE_ADDRESS_DIRECTORY_FIXTURE, ensure_ascii=False),
        encoding="utf-8",
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
                    row(community_id="community_3", ward_name="千代田区", name="未知施設の会", description="謎", venue_name="未知の施設"),
                    row(community_id="community_4", ward_name="新宿区", name="よその区の会", description="その他", venue_name="九段"),
                ],
            )

            result = load_community_directory("千代田区", data_root=root)

            self.assertEqual(result["ward"], "千代田区")
            self.assertEqual(
                result["counts"],
                {"totalInWard": 3, "withVenueAddress": 0, "withKnownFacility": 2, "withAreaLocation": 0, "withWardOfficeFallback": 1},
            )
            self.assertEqual(len(result["facilities"]), 3)

            by_key = {facility["key"]: facility for facility in result["facilities"]}
            kudan = by_key["kudan"]
            self.assertEqual([item["name"] for item in kudan["communities"]], ["読書会さくら"])
            self.assertAlmostEqual(kudan["latitude"], 35.695339, places=5)
            self.assertAlmostEqual(kudan["longitude"], 139.751984, places=5)
            self.assertEqual(kudan["address"], "東京都千代田区九段南1-5-10")

            sports_center = by_key["sports-center"]
            self.assertEqual([item["name"] for item in sports_center["communities"]], ["卓球クラブ"])

            chiyoda_office = by_key["chiyoda-office"]
            self.assertEqual([item["name"] for item in chiyoda_office["communities"]], ["未知施設の会"])

    def test_falls_back_to_the_ward_office_for_a_ward_without_known_anchors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [row(community_id="community_5", ward_name="新宿区", name="新宿の会", description="謎", venue_name="公民館")],
            )

            result = load_community_directory("新宿区", data_root=root)

            self.assertEqual(
                result["counts"],
                {"totalInWard": 1, "withVenueAddress": 0, "withKnownFacility": 0, "withAreaLocation": 0, "withWardOfficeFallback": 1},
            )
            self.assertEqual(result["facilities"][0]["key"], "shinjuku-office")
            self.assertEqual(result["facilities"][0]["name"], "新宿区役所")

    def test_excludes_rows_outside_the_requested_ward(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [row(community_id="community_6", ward_name="新宿区", name="新宿の会", description="謎", venue_name="九段")],
            )

            result = load_community_directory("千代田区", data_root=root)

            self.assertEqual(
                result["counts"],
                {"totalInWard": 0, "withVenueAddress": 0, "withKnownFacility": 0, "withAreaLocation": 0, "withWardOfficeFallback": 0},
            )
            self.assertEqual(result["facilities"], [])

    def test_prefers_a_geocoded_venue_address_over_the_ward_office_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [
                    row(
                        community_id="community_1", ward_name="渋谷区", name="あみもの教室", description="手芸",
                        venue_name="本町区民会館", venue_address="東京都渋谷区本町3-46-1",
                    ),
                    row(community_id="community_2", ward_name="渋谷区", name="住所なしの会", description="その他", venue_name="未登録施設"),
                ],
            )

            result = load_community_directory("渋谷区", data_root=root)

            self.assertEqual(result["counts"]["withVenueAddress"], 1)
            by_key = {facility["key"]: facility for facility in result["facilities"]}
            address_facility = by_key["addr:東京都渋谷区本町3-46-1"]
            self.assertEqual(address_facility["communities"][0]["name"], "あみもの教室")
            self.assertAlmostEqual(address_facility["latitude"], 35.687641, places=5)
            # 渋谷区 has no ward-geocoding-directory entry in this fixture, so the second
            # (address-less) row cannot resolve anywhere and is simply excluded.
            self.assertEqual(len(result["facilities"]), 1)

    def test_ignores_a_venue_address_recorded_under_a_different_ward(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [
                    row(
                        community_id="community_1", ward_name="千代田区", name="間違った区の会", description="謎",
                        venue_name="未知の施設", venue_address="東京都渋谷区本町3-46-1",
                    ),
                ],
            )

            result = load_community_directory("千代田区", data_root=root)

            # The address is geocoded for 渋谷区, not 千代田区, so it must not be
            # trusted here — the row falls back to the Chiyoda ward office instead.
            self.assertEqual(
                result["counts"],
                {"totalInWard": 1, "withVenueAddress": 0, "withKnownFacility": 0, "withAreaLocation": 0, "withWardOfficeFallback": 1},
            )
            self.assertEqual(result["facilities"][0]["key"], "chiyoda-office")

    def test_prefers_a_csv_activity_area_before_the_ward_office(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [
                    row(
                        community_id="community_area", ward_name="新宿区", name="西新宿一丁目町会",
                        description="町会・自治会", area_name="西新宿一丁目", map_location_id="map_nishishinjuku",
                        latitude="35.6912", longitude="139.6996", geocoded_address="東京都新宿区西新宿一丁目",
                        location_precision="name_chome", location_source="community_name",
                        location_source_url="https://maps.gsi.go.jp/",
                    )
                ],
            )

            result = load_community_directory("新宿区", data_root=root)

            self.assertEqual(
                result["counts"],
                {"totalInWard": 1, "withVenueAddress": 0, "withKnownFacility": 0, "withAreaLocation": 1, "withWardOfficeFallback": 0},
            )
            self.assertEqual(result["facilities"][0]["key"], "map_nishishinjuku")
            self.assertEqual(result["facilities"][0]["locationKind"], "activity_area")

    def test_marks_first_multi_venue_address_as_representative(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(
                root,
                [
                    row(
                        community_id="community_multi", ward_name="千代田区", name="二会場の会",
                        description="文化", venue_address="東京都千代田区九段南1-5-10 | 東京都千代田区内神田2-1-8",
                        map_location_id="map_multi", latitude="35.6953", longitude="139.7520",
                        geocoded_address="東京都千代田区九段南一丁目5番10号",
                        location_precision="multiple_addresses_representative", location_source="venue_address",
                    )
                ],
            )

            result = load_community_directory("千代田区", data_root=root)

            self.assertEqual(result["counts"]["withVenueAddress"], 1)
            self.assertEqual(result["facilities"][0]["locationKind"], "multiple_addresses")
            self.assertIn("複数会場の代表", result["facilities"][0]["name"])

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

    def test_real_repository_csv_matches_the_shared_ward_directory(self):
        # Cross-check against the actual data the map reads, without asserting an exact
        # row count that would make this test brittle as the CSV is refreshed.
        repo_root = AGENT_ROOT.parent / "data" / "tokyo-community"
        result = load_community_directory("千代田区", data_root=repo_root)
        self.assertGreater(result["counts"]["totalInWard"], 0)
        self.assertGreater(len(result["facilities"]), 0)

        nerima = load_community_directory("練馬区", data_root=repo_root)
        self.assertGreater(nerima["counts"]["totalInWard"], 0)
        self.assertEqual(nerima["counts"]["withKnownFacility"], 0)
        self.assertEqual(nerima["facilities"][0]["name"], "練馬区役所")

        shibuya = load_community_directory("渋谷区", data_root=repo_root)
        self.assertGreater(shibuya["counts"]["withVenueAddress"], 0)
        address_facilities = [key for key in shibuya["facilities"] if key["key"].startswith("addr:")]
        self.assertTrue(address_facilities)


if __name__ == "__main__":
    unittest.main()
