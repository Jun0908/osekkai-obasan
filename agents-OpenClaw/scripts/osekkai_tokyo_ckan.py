"""Tokyo CKAN discovery with resource-level freshness checks.

The catalogue is discovery metadata, not proof that an event is current.  A
dataset becomes an active event source only after its latest resource contains
at least one future date.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

from osekkai_contracts import ContractError
from osekkai_source_registry import source_by_id


DEFAULT_QUERIES = ("イベント", "講座", "交流会", "公民館")
DATE_FIELD_HINTS = ("date", "start", "end", "開催日", "開始", "終了", "日時", "期間")
MAX_RESOURCE_BYTES = 8 * 1024 * 1024
USER_AGENT = "osekkai-obasan-live-discovery/1.0"


class CkanError(RuntimeError):
    pass


def _http_bytes(url: str, *, timeout: float = 15.0, max_bytes: int = MAX_RESOURCE_BYTES) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/csv,*/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise CkanError("resource exceeds the configured byte limit")
            body = response.read(max_bytes + 1)
    except (OSError, ValueError) as exc:
        raise CkanError(f"request failed for {url}") from exc
    if len(body) > max_bytes:
        raise CkanError("resource exceeds the configured byte limit")
    return body


class TokyoCkanClient:
    def __init__(self, base_url: str | None = None, *, timeout: float = 15.0):
        source = source_by_id("tokyo_ckan")
        self.base_url = (base_url or source["baseUrl"]).rstrip("/") + "/"
        self.timeout = timeout

    def action(self, name: str, **params: Any) -> dict[str, Any]:
        if name not in {"package_search", "package_show"}:
            raise CkanError("CKAN action is not allowed")
        query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
        payload = json.loads(_http_bytes(f"{self.base_url}{name}?{query}", timeout=self.timeout).decode("utf-8"))
        if payload.get("success") is not True or not isinstance(payload.get("result"), (dict, list)):
            raise CkanError(f"CKAN {name} returned an unsuccessful response")
        return payload["result"]

    def package_search(self, query: str, *, rows: int = 20, start: int = 0) -> list[dict[str, Any]]:
        result = self.action("package_search", q=query, rows=max(1, min(rows, 100)), start=max(0, start))
        if not isinstance(result, dict) or not isinstance(result.get("results"), list):
            raise CkanError("CKAN package_search result is malformed")
        return [item for item in result["results"] if isinstance(item, dict)]

    def package_show(self, dataset_id: str) -> dict[str, Any]:
        result = self.action("package_show", id=dataset_id)
        if not isinstance(result, dict):
            raise CkanError("CKAN package_show result is malformed")
        return result


def _resource_timestamp(resource: Mapping[str, Any]) -> str:
    return str(resource.get("last_modified") or resource.get("created") or "")


def latest_supported_resource(dataset: Mapping[str, Any]) -> dict[str, Any] | None:
    resources = dataset.get("resources")
    if not isinstance(resources, list):
        return None
    supported: list[dict[str, Any]] = []
    for value in resources:
        if not isinstance(value, dict) or not str(value.get("url", "")).startswith(("https://", "http://")):
            continue
        format_name = str(value.get("format") or "").strip().lower()
        path = urllib.parse.urlparse(str(value["url"])).path.lower()
        if format_name in {"csv", "json"} or path.endswith((".csv", ".json")):
            supported.append(value)
    if not supported:
        return None
    return dict(max(supported, key=_resource_timestamp))


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    normalized = text.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")
    normalized = re.sub(r"\s+", " ", normalized)
    candidates = [normalized, normalized.replace(" ", "T", 1)]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        except ValueError:
            pass
    match = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", normalized)
    if not match:
        return None
    try:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc)
    except ValueError:
        return None


def _decode_text(body: bytes) -> str:
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CkanError("resource encoding is not supported")


def _records(body: bytes, resource: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    format_name = str(resource.get("format") or "").lower()
    path = urllib.parse.urlparse(str(resource.get("url") or "")).path.lower()
    text = _decode_text(body)
    if format_name == "json" or path.endswith(".json"):
        payload = json.loads(text)
        if isinstance(payload, dict):
            payload = payload.get("results") or payload.get("records") or payload.get("data") or []
        if not isinstance(payload, list):
            raise CkanError("JSON resource is not a record array")
        return (item for item in payload if isinstance(item, dict))
    return csv.DictReader(io.StringIO(text))


def inspect_event_resource(
    resource: Mapping[str, Any],
    *,
    now: datetime,
    fetcher: Callable[[str], bytes] = _http_bytes,
) -> dict[str, Any]:
    if now.tzinfo is None:
        raise ContractError("now must be timezone-aware")
    body = fetcher(str(resource["url"]))
    future_count = 0
    row_count = 0
    for row in _records(body, resource):
        row_count += 1
        dates = [
            parsed
            for key, value in row.items()
            if any(hint in str(key).lower() for hint in DATE_FIELD_HINTS)
            for parsed in [_parse_datetime(value)]
            if parsed is not None
        ]
        if dates and max(dates).astimezone(now.tzinfo) >= now:
            future_count += 1
    return {
        "resourceUrl": resource["url"],
        "resourceFormat": str(resource.get("format") or "").upper() or None,
        "resourceUpdatedAt": resource.get("last_modified") or resource.get("created"),
        "fetchedAt": now.isoformat(),
        "checksum": hashlib.sha256(body).hexdigest(),
        "rowCount": row_count,
        "futureEventCount": future_count,
        "active": future_count > 0,
    }


def discover_datasets(
    *,
    client: TokyoCkanClient | Any | None = None,
    queries: Iterable[str] = DEFAULT_QUERIES,
    now: datetime,
    rows_per_query: int = 10,
    inspect_resources: bool = True,
    fetcher: Callable[[str], bytes] = _http_bytes,
) -> dict[str, Any]:
    api = client or TokyoCkanClient()
    packages: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    for query in queries:
        try:
            for item in api.package_search(query, rows=rows_per_query):
                dataset_id = str(item.get("id") or item.get("name") or "")
                if dataset_id:
                    packages.setdefault(dataset_id, item)
        except CkanError as exc:
            errors.append({"query": query, "message": str(exc)})

    datasets: list[dict[str, Any]] = []
    for dataset_id in packages:
        try:
            dataset = api.package_show(dataset_id)
            resource = latest_supported_resource(dataset)
            if resource is None:
                datasets.append({
                    "datasetId": dataset_id,
                    "title": dataset.get("title") or dataset_id,
                    "provider": (dataset.get("organization") or {}).get("title"),
                    "datasetUrl": f"https://catalog.data.metro.tokyo.lg.jp/dataset/{dataset.get('name') or dataset_id}",
                    "license": dataset.get("license_title") or "unknown",
                    "active": False,
                    "inactiveReason": "no_supported_resource",
                })
                continue
            inspection = inspect_event_resource(resource, now=now, fetcher=fetcher) if inspect_resources else {
                "resourceUrl": resource["url"],
                "resourceFormat": str(resource.get("format") or "").upper() or None,
                "resourceUpdatedAt": resource.get("last_modified") or resource.get("created"),
                "fetchedAt": now.isoformat(),
                "checksum": None,
                "rowCount": None,
                "futureEventCount": None,
                "active": None,
            }
            datasets.append({
                "datasetId": dataset_id,
                "title": dataset.get("title") or dataset_id,
                "provider": (dataset.get("organization") or {}).get("title"),
                "datasetUrl": f"https://catalog.data.metro.tokyo.lg.jp/dataset/{dataset.get('name') or dataset_id}",
                "license": dataset.get("license_title") or "unknown",
                **inspection,
                "inactiveReason": "no_future_event" if inspection["active"] is False else None,
            })
        except (CkanError, json.JSONDecodeError) as exc:
            errors.append({"query": dataset_id, "message": str(exc)})
    return {
        "schemaVersion": "1.0",
        "provider": "tokyo_ckan",
        "fetchedAt": now.isoformat(),
        "datasets": datasets,
        "activeDatasets": [item for item in datasets if item.get("active") is True],
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover current Tokyo event datasets")
    parser.add_argument("--smoke", action="store_true", help="query the official catalogue")
    parser.add_argument("--inspect-resources", action="store_true", help="download bounded CSV/JSON resources and inspect future dates")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.smoke:
        parser.error("--smoke is required when invoking this module directly")
    result = discover_datasets(
        now=datetime.now().astimezone(),
        queries=("イベント",),
        rows_per_query=3,
        inspect_resources=args.inspect_resources,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"Tokyo CKAN: {len(result['datasets'])} datasets, {len(result['errors'])} errors")
    return 0 if result["datasets"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
