"""Official public-cultural-facility adapters.

The first domain adapter targets Koto Culture and Community Foundation.  The
domain parser is separate from geographic filtering so additional official
facility sites can be added without turning Koto into the product boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, time
from typing import Any, Callable
from zoneinfo import ZoneInfo


BASE_URL = "https://www.kcf.or.jp/koza/"
MAX_HTML_BYTES = 5 * 1024 * 1024
TOKYO = ZoneInfo("Asia/Tokyo")
USER_AGENT = "osekkai-obasan-public-events/1.0"


class PublicEventError(RuntimeError):
    pass


def _safe_kcf_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"www.kcf.or.jp", "kcf.or.jp"}:
        raise PublicEventError("public event adapter refused a non-KCF URL")
    return parsed.geturl()


def fetch_html(url: str, *, timeout: float = 15.0) -> bytes:
    safe_url = _safe_kcf_url(url)
    request = urllib.request.Request(safe_url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_HTML_BYTES:
                raise PublicEventError("public page exceeds the byte limit")
            body = response.read(MAX_HTML_BYTES + 1)
    except OSError as exc:
        raise PublicEventError(f"official page request failed: {safe_url}") from exc
    if len(body) > MAX_HTML_BYTES:
        raise PublicEventError("public page exceeds the byte limit")
    return body


def _decode(body: bytes | str) -> str:
    if isinstance(body, str):
        return body
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise PublicEventError("official page encoding is not supported")


def _text(markup: str) -> str:
    without_scripts = re.sub(r"<(script|style)\b.*?</\1>", " ", markup, flags=re.IGNORECASE | re.DOTALL)
    with_breaks = re.sub(r"<(?:br|/p|/div|/tr|/dd|/li)\b[^>]*>", "\n", without_scripts, flags=re.IGNORECASE)
    plain = re.sub(r"<[^>]+>", "", with_breaks)
    plain = html.unescape(plain).replace("\u3000", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", plain).strip()


def parse_course_list(body: bytes | str, *, page_url: str = BASE_URL) -> list[dict[str, str]]:
    source = _decode(body)
    event_list = re.search(r"<ul[^>]+class=['\"][^'\"]*event_list[^'\"]*['\"][^>]*>(.*?)</ul>", source, re.I | re.S)
    if not event_list:
        return []
    courses: list[dict[str, str]] = []
    for item in re.findall(r"<li\b[^>]*>(.*?)</li>", event_list.group(1), re.I | re.S):
        href_match = re.search(r"<a[^>]+href=['\"]([^'\"]*?/koza/detail/\?id=\d+[^'\"]*)['\"]", item, re.I)
        title_match = re.search(r"class=['\"][^'\"]*ev_title[^'\"]*['\"][^>]*>(.*?)</div>", item, re.I | re.S)
        if not href_match or not title_match:
            continue
        status_match = re.search(r"class=['\"][^'\"]*info_type[^'\"]*['\"][^>]*>(.*?)</span>", item, re.I | re.S)
        genre_match = re.search(r"class=['\"][^'\"]*genre[^'\"]*['\"][^>]*>(.*?)</span>", item, re.I | re.S)
        courses.append(
            {
                "url": urllib.parse.urljoin(page_url, html.unescape(href_match.group(1))),
                "title": _text(title_match.group(1)),
                "statusText": _text(status_match.group(1)) if status_match else "不明",
                "genre": _text(genre_match.group(1)) if genre_match else "",
            }
        )
    return courses


def _details(source: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for key_markup, value_markup in re.findall(r"<dt\b[^>]*>(.*?)</dt>\s*<dd\b[^>]*>(.*?)</dd>", source, re.I | re.S):
        key = _text(key_markup)
        if key:
            values[key] = _text(value_markup)
    return values


def _date_values(value: str) -> list[datetime]:
    dates: list[datetime] = []
    for year, month, day in re.findall(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日", value):
        try:
            candidate = datetime(int(year), int(month), int(day), tzinfo=TOKYO)
        except ValueError:
            continue
        if not dates or candidate.date() != dates[-1].date():
            dates.append(candidate)
    return dates


def _time_range(value: str) -> tuple[time, time]:
    found = re.findall(r"(\d{1,2})時\s*(\d{1,2})分", value)
    if len(found) >= 2:
        return time(int(found[0][0]), int(found[0][1])), time(int(found[1][0]), int(found[1][1]))
    colon = re.findall(r"(\d{1,2}):(\d{2})", value)
    if len(colon) >= 2:
        return time(int(colon[0][0]), int(colon[0][1])), time(int(colon[1][0]), int(colon[1][1]))
    return time(10, 0), time(12, 0)


def _integer(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d[\d,]*", value)
    return int(match.group().replace(",", "")) if match else None


def _registration_status(status_text: str) -> tuple[str, str]:
    if any(label in status_text for label in ("完売", "満席")):
        return "sold_out", "sold_out"
    if any(label in status_text for label in ("募集終了", "受付終了")):
        return "registration_closed", "closed"
    if "募集前" in status_text:
        return "scheduled", "closed"
    if any(label in status_text for label in ("募集中", "先着受付中", "受付中")):
        return "scheduled", "open"
    return "unknown", "unknown"


def parse_course_detail(
    body: bytes | str,
    *,
    url: str,
    status_text: str,
    genre: str,
    fetched_at: datetime,
    now: datetime | None = None,
) -> dict[str, Any]:
    source = _decode(body)
    details = _details(source)
    title_match = re.search(r"class=['\"][^'\"]*detail_title[^'\"]*['\"][^>]*>(.*?)</h2>", source, re.I | re.S)
    if not title_match:
        raise PublicEventError("course detail has no title")
    title = _text(title_match.group(1))[:240]
    course_id_match = re.search(r"[?&]id=(\d+)", url)
    course_id = course_id_match.group(1) if course_id_match else hashlib.sha256(url.encode()).hexdigest()[:12]
    occurrence_dates = _date_values(details.get("開催日") or details.get("開催期間") or "")
    if not occurrence_dates:
        raise PublicEventError("course detail has no occurrence dates")
    start_time, end_time = _time_range(details.get("時間", ""))
    event_status, registration_status = _registration_status(status_text)
    current_time = now or fetched_at
    capacity = _integer(details.get("定員"))
    price = (_integer(details.get("受講料")) or 0) + (_integer(details.get("教材費")) or 0)
    if not details.get("受講料") and not details.get("教材費"):
        price = None
    venue = details.get("会場") or None
    audience = details.get("対象") or None
    description_match = re.search(r"class=['\"][^'\"]*kikaku_explanation[^'\"]*['\"][^>]*>(.*?)</div>", source, re.I | re.S)
    description = _text(description_match.group(1))[:10000] if description_match else ""
    facility_match = re.search(r"class=['\"][^'\"]*fcl_title_logo[^'\"]*['\"][^>]*>.*?<img[^>]+alt=['\"]([^'\"]+)['\"]", source, re.I | re.S)
    facility = html.unescape(facility_match.group(1)).strip() if facility_match else (venue or "江東区文化コミュニティ財団")
    facility_slug = urllib.parse.urlparse(url).path.strip("/").split("/")[0] or "kcf"
    community_id = f"community-kcf-{facility_slug}"
    series_id = f"series-kcf-{course_id}" if len(occurrence_dates) > 1 else None
    deadline_dates = _date_values(details.get("申込期間", ""))
    registration_deadline = datetime.combine(deadline_dates[-1].date(), time(23, 59), TOKYO).isoformat() if deadline_dates else None
    events: list[dict[str, Any]] = []
    for index, occurrence in enumerate(occurrence_dates, start=1):
        starts_at = datetime.combine(occurrence.date(), start_time, TOKYO)
        ends_at = datetime.combine(occurrence.date(), end_time, TOKYO)
        occurrence_status = "ended" if ends_at < current_time and event_status == "scheduled" else event_status
        occurrence_registration = "closed" if occurrence_status == "ended" else registration_status
        record_id = f"{course_id}:{occurrence.date().isoformat()}"
        canonical = f"{record_id}|{title}|{starts_at.isoformat()}|{ends_at.isoformat()}|{status_text}|{capacity}|{price}"
        events.append(
            {
                "schemaVersion": "1.0",
                "id": f"event-kcf-{course_id}-{occurrence.date().isoformat()}",
                "provider": "koto_culture",
                "sourceRecordId": record_id,
                "title": title if len(occurrence_dates) == 1 else f"{title}（第{index}回）",
                "description": description,
                "startsAt": starts_at.isoformat(),
                "endsAt": ends_at.isoformat(),
                "timezone": "Asia/Tokyo",
                "venueName": venue[:240] if venue else None,
                "address": None,
                "latitude": None,
                "longitude": None,
                "communityId": community_id,
                "seriesId": series_id,
                "status": occurrence_status,
                "registrationStatus": occurrence_registration,
                "registrationDeadline": registration_deadline,
                "capacity": capacity,
                "participants": None,
                "audience": audience[:500] if audience else None,
                "priceYen": price,
                "categories": [genre[:80]] if genre else [],
                "sourceUrl": url,
                "sourceDataset": "江東区文化コミュニティ財団 公式講座ページ",
                "license": "Official-site terms; event facts only",
                "sourceClassification": "live_provider",
                "sourceUpdatedAt": fetched_at.isoformat(),
                "fetchedAt": fetched_at.isoformat(),
                "revalidatedAt": fetched_at.isoformat(),
                "checksum": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                "fieldProvenance": {
                    "title": {"classification": "source_verified", "sourceUrl": url, "capturedAt": fetched_at.isoformat()},
                    "startsAt": {"classification": "source_verified", "sourceUrl": url, "capturedAt": fetched_at.isoformat()},
                    "capacity": {"classification": "source_verified", "sourceUrl": url, "capturedAt": fetched_at.isoformat()},
                    "audience": {"classification": "source_verified", "sourceUrl": url, "capturedAt": fetched_at.isoformat()},
                    "registrationStatus": {"classification": "source_verified", "sourceUrl": url, "capturedAt": fetched_at.isoformat()},
                },
            }
        )
    evidence_url = url
    series = []
    if series_id:
        series.append(
            {
                "schemaVersion": "1.0",
                "id": series_id,
                "provider": "koto_culture",
                "communityId": community_id,
                "title": title,
                "recurrenceText": f"公式講座ページに全{len(events)}回の日程が掲載されています。",
                "futureOccurrenceIds": [event["id"] for event in events if event["status"] != "ended"],
                "sourceUrl": url,
                "sourceClassification": "live_provider",
                "sourceUpdatedAt": fetched_at.isoformat(),
                "fetchedAt": fetched_at.isoformat(),
                "revalidatedAt": fetched_at.isoformat(),
                "evidence": [
                    {
                        "kind": "future_occurrence",
                        "text": f"開催日欄に全{len(events)}回の日程があります。",
                        "url": evidence_url,
                        "classification": "live_provider",
                        "capturedAt": fetched_at.isoformat(),
                        "confidence": 1,
                        "evidenceField": "開催日",
                    }
                ],
            }
        )
    community = {
        "schemaVersion": "1.0",
        "id": community_id,
        "provider": "koto_culture",
        "name": facility[:240],
        "description": "公共文化施設が公式に掲載する講座・継続活動。",
        "organizerName": "公益財団法人江東区文化コミュニティ財団",
        "eventSeriesIds": [series_id] if series_id else [],
        "futureEventIds": [event["id"] for event in events if event["status"] != "ended"],
        "communityUrl": urllib.parse.urljoin(url, f"/{facility_slug}/"),
        "sourceClassification": "live_provider",
        "sourceUpdatedAt": fetched_at.isoformat(),
        "fetchedAt": fetched_at.isoformat(),
        "revalidatedAt": fetched_at.isoformat(),
        "evidence": [
            {
                "kind": "community_path",
                "text": f"{facility}の公式講座です。",
                "url": url,
                "classification": "live_provider",
                "capturedAt": fetched_at.isoformat(),
                "confidence": 1,
                "evidenceField": "facility",
            }
        ],
    }
    return {"events": events, "series": series, "communities": [community]}


def sync_kcf_courses(
    *,
    fetched_at: datetime | None = None,
    max_pages: int = 3,
    max_details: int = 30,
    fetcher: Callable[[str], bytes] = fetch_html,
) -> dict[str, Any]:
    captured = fetched_at or datetime.now().astimezone()
    if captured.tzinfo is None:
        raise PublicEventError("fetched_at must be timezone-aware")
    courses: dict[str, dict[str, str]] = {}
    errors: list[dict[str, str]] = []
    for page in range(1, max(1, min(max_pages, 20)) + 1):
        page_url = BASE_URL if page == 1 else f"{BASE_URL}?page={page}"
        try:
            items = parse_course_list(fetcher(page_url), page_url=page_url)
        except PublicEventError as exc:
            errors.append({"url": page_url, "message": str(exc)})
            continue
        for item in items:
            courses.setdefault(item["url"], item)
        if not items:
            break
    events: list[dict[str, Any]] = []
    series_by_id: dict[str, dict[str, Any]] = {}
    communities_by_id: dict[str, dict[str, Any]] = {}
    for course in list(courses.values())[: max(1, min(max_details, 100))]:
        try:
            normalized = parse_course_detail(
                fetcher(course["url"]),
                url=course["url"],
                status_text=course["statusText"],
                genre=course["genre"],
                fetched_at=captured,
            )
        except PublicEventError as exc:
            errors.append({"url": course["url"], "message": str(exc)})
            continue
        events.extend(normalized["events"])
        for value in normalized["series"]:
            series_by_id[value["id"]] = value
        for value in normalized["communities"]:
            existing = communities_by_id.get(value["id"])
            if existing:
                existing["eventSeriesIds"] = list(dict.fromkeys(existing["eventSeriesIds"] + value["eventSeriesIds"]))
                existing["futureEventIds"] = list(dict.fromkeys(existing["futureEventIds"] + value["futureEventIds"]))
            else:
                communities_by_id[value["id"]] = value
    return {
        "schemaVersion": "1.0",
        "provider": "koto_culture",
        "scope": "official_domain_adapter",
        "fetchedAt": captured.isoformat(),
        "events": sorted(events, key=lambda item: (item["startsAt"], item["id"])),
        "series": list(series_by_id.values()),
        "communities": list(communities_by_id.values()),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync public cultural-facility courses")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--max-details", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.smoke:
        parser.error("--smoke is required")
    result = sync_kcf_courses(max_pages=1, max_details=args.max_details)
    summary = {
        "ok": bool(result["events"]),
        "provider": result["provider"],
        "fetchedAt": result["fetchedAt"],
        "eventCount": len(result["events"]),
        "seriesCount": len(result["series"]),
        "communityCount": len(result["communities"]),
        "errors": result["errors"],
    }
    print(json.dumps(summary, ensure_ascii=False) if args.json else summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
