from __future__ import annotations

import unittest
from datetime import datetime

import helpers  # noqa: F401
from osekkai_tokyo_ckan import discover_datasets, inspect_event_resource, latest_supported_resource


NOW = datetime.fromisoformat("2026-08-23T09:00:00+09:00")


class FakeClient:
    def __init__(self):
        self.shown = []

    def package_search(self, query, rows=10):
        return [
            {"id": "setagaya-events", "title": "世田谷イベント"},
            {"id": "tama-events", "title": "多摩イベント"},
        ]

    def package_show(self, dataset_id):
        self.shown.append(dataset_id)
        return {
            "id": dataset_id,
            "name": dataset_id,
            "title": dataset_id,
            "license_title": "CC BY 4.0",
            "organization": {"title": dataset_id.split("-")[0]},
            "resources": [
                {
                    "url": f"https://example.test/{dataset_id}-old.csv",
                    "format": "CSV",
                    "last_modified": "2025-01-01T00:00:00+09:00",
                },
                {
                    "url": f"https://example.test/{dataset_id}.csv",
                    "format": "CSV",
                    "last_modified": "2026-08-23T08:00:00+09:00",
                },
            ],
        }


def fixture_fetcher(url):
    if "setagaya" in url:
        return "名称,開催日,住所\n交流講座,2026-09-10,東京都世田谷区\n".encode("utf-8")
    return "名称,開催日,住所\n古い祭り,2024-02-01,東京都多摩市\n".encode("utf-8")


class TokyoCkanTests(unittest.TestCase):
    def test_latest_supported_resource_uses_resource_timestamp(self):
        dataset = FakeClient().package_show("setagaya-events")
        self.assertTrue(latest_supported_resource(dataset)["url"].endswith("setagaya-events.csv"))

    def test_future_content_not_catalog_timestamp_controls_activity(self):
        result = discover_datasets(
            client=FakeClient(),
            queries=("イベント", "講座"),
            now=NOW,
            fetcher=fixture_fetcher,
        )
        self.assertEqual({item["datasetId"] for item in result["datasets"]}, {"setagaya-events", "tama-events"})
        self.assertEqual([item["datasetId"] for item in result["activeDatasets"]], ["setagaya-events"])
        inactive = next(item for item in result["datasets"] if item["datasetId"] == "tama-events")
        self.assertEqual(inactive["inactiveReason"], "no_future_event")
        self.assertRegex(result["datasets"][0]["checksum"], r"^[0-9a-f]{64}$")

    def test_discovery_has_no_koto_or_ward_filter(self):
        result = discover_datasets(client=FakeClient(), queries=("イベント",), now=NOW, fetcher=fixture_fetcher)
        self.assertEqual(len(result["datasets"]), 2)
        self.assertIn("setagaya", {item["provider"] for item in result["datasets"]})
        self.assertIn("tama", {item["provider"] for item in result["datasets"]})

    def test_cp932_csv_and_japanese_date_field_are_supported(self):
        resource = {"url": "https://example.test/events.csv", "format": "CSV"}
        body = "名称,開催日時\n地域交流会,2026年9月12日\n".encode("cp932")
        result = inspect_event_resource(resource, now=NOW, fetcher=lambda _url: body)
        self.assertTrue(result["active"])
        self.assertEqual(result["futureEventCount"], 1)


if __name__ == "__main__":
    unittest.main()
