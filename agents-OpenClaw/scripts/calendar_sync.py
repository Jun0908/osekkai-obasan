"""
calendar_sync.py
Google Calendar の予定を取得し、OpenClaw 用の予定一覧と準備ブリーフを生成する。

保存先:
  data/calendar/today.md
  data/calendar/today.json
  reports/briefs/
  reports/meeting-prep/
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from dateutil import parser as dateparser

from openclaw_core import (
    BASE_DIR,
    BRIEFS_DIR,
    JST,
    build_brief_record,
    build_event_query_record,
    ensure_directories,
    find_related_cases,
    find_related_public_info,
    load_case_records,
    load_public_records,
    now_jst,
    slugify,
    write_brief_files,
    write_json,
)


NOW = now_jst()
TODAY_STR = NOW.strftime("%Y-%m-%d")
CALENDAR_DIR = BASE_DIR / "data" / "calendar"
MEETING_PREP_DIR = BASE_DIR / "reports" / "meeting-prep"
BRIEF_WINDOW_HOURS = int(os.environ.get("BRIEF_WINDOW_HOURS", "24"))


def parse_args():
    parser = argparse.ArgumentParser(description="Google Calendar を OpenClaw 用に同期する")
    parser.add_argument("--events-file", default="", help="Google API の代わりに読む JSON ファイル")
    return parser.parse_args()


def get_credentials():
    """環境変数から Google OAuth2 認証情報を作成する。"""
    from google.oauth2.credentials import Credentials

    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    )
    return creds


def fetch_events(service):
    """今日0時〜明日23:59 の予定を取得する。"""
    today_start = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = today_start + timedelta(days=2)

    result = service.events().list(
        calendarId="primary",
        timeMin=today_start.isoformat(),
        timeMax=tomorrow_end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=50,
    ).execute()

    return result.get("items", [])


def load_events_from_file(path: Path):
    """ローカル JSON から予定一覧を読む。"""
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            return payload.get("items", [])
        if payload.get("start") and payload.get("end"):
            return [payload]
        return []
    return payload


def parse_event_time(event):
    """イベントの開始・終了時刻をパースして返す。"""
    start_raw = event["start"].get("dateTime") or event["start"].get("date")
    end_raw = event["end"].get("dateTime") or event["end"].get("date")

    start = dateparser.parse(start_raw)
    end = dateparser.parse(end_raw)

    if start.tzinfo is None:
        start = start.replace(tzinfo=JST)
    if end.tzinfo is None:
        end = end.replace(tzinfo=JST)

    return start.astimezone(JST), end.astimezone(JST)


def enrich_event(event, cases, public_records):
    """予定に関連案件と公開情報を付与する。"""
    start, end = parse_event_time(event)
    attendees = [item.get("email", "") for item in event.get("attendees", []) if item.get("email")]
    event_record = {
        "id": event.get("id") or f"event-{slugify(event.get('summary', 'event'))}",
        "title": event.get("summary", "(タイトルなし)"),
        "description": event.get("description", ""),
        "location": event.get("location", ""),
        "attendees": attendees,
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
        "start_date": start.date().isoformat(),
    }

    query_record = build_event_query_record(event_record)
    related_cases = find_related_cases(query_record, cases, limit=5)
    related_public = find_related_public_info(query_record, public_records, limit=5)

    event_record["related_cases"] = related_cases
    event_record["related_public_info"] = related_public
    return event_record


def save_today_calendar(enriched_events):
    """今日・明日の予定を Markdown / JSON で保存する。"""
    ensure_directories()
    CALENDAR_DIR.mkdir(parents=True, exist_ok=True)
    now_str = NOW.strftime("%Y-%m-%d %H:%M")
    today_events = [event for event in enriched_events if event["start_date"] == TODAY_STR]
    tomorrow_str = (NOW + timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_events = [event for event in enriched_events if event["start_date"] == tomorrow_str]

    lines = [
        f"# 📅 カレンダー: {TODAY_STR}",
        f"最終更新: {now_str}",
        "",
        f"## 今日の予定 ({len(today_events)}件)",
        "",
    ]

    def append_event_block(event):
        start = dateparser.parse(event["start_at"]).astimezone(JST)
        end = dateparser.parse(event["end_at"]).astimezone(JST)
        lines.append(f"- **{event['title']}** ({start.strftime('%H:%M')} - {end.strftime('%H:%M')})")
        if event.get("location"):
            lines.append(f"  - 場所: {event['location']}")
        if event.get("attendees"):
            lines.append(f"  - 参加者: {', '.join(event['attendees'])}")
        if event["related_cases"]:
            lines.append(
                "  - 関連案件: " +
                ", ".join(item["title"] for item in event["related_cases"][:3])
            )
        if event["related_public_info"]:
            lines.append(
                "  - 関連公開情報: " +
                ", ".join(item["title"] for item in event["related_public_info"][:2])
            )
        lines.append("")

    if today_events:
        for event in today_events:
            append_event_block(event)
    else:
        lines.append("予定なし\n")

    lines.extend([f"## 明日の予定 ({len(tomorrow_events)}件)", ""])
    if tomorrow_events:
        for event in tomorrow_events:
            append_event_block(event)
    else:
        lines.append("予定なし\n")

    markdown_path = CALENDAR_DIR / "today.md"
    json_path = CALENDAR_DIR / "today.json"
    markdown_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    write_json(json_path, {"generated_at": NOW.isoformat(), "events": enriched_events})
    print(f"[ok] カレンダー保存完了: {markdown_path}")


def write_legacy_meeting_prep(brief: dict):
    """既存の meeting-prep 互換 Markdown も保存する。"""
    MEETING_PREP_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{brief['event_time'][:10]}-{slugify(brief['event_title'], fallback='meeting')}.md"
    output_path = MEETING_PREP_DIR / filename
    lines = [
        f"# 🔔 MTG準備レポート: {brief['event_title']}",
        f"開始: {brief['event_time']}",
        f"作成: {brief['generated_at']}",
        "",
        "## 関連案件",
    ]
    lines.extend([f"- {item['title']}" for item in brief["related_cases"]] or ["- 該当なし"])
    lines.extend(["", "## 今回確認したいこと"])
    lines.extend([f"- {item}" for item in brief["questions_to_ask"]] or ["- 特になし"])
    lines.extend(["", "## この場で決めたいこと"])
    lines.extend([f"- {item}" for item in brief.get("decision_focus", [])] or ["- 特になし"])
    lines.extend(["", "## 慎重にしたいこと"])
    lines.extend([f"- {item}" for item in brief.get("caution_points", [])] or ["- 特になし"])
    lines.extend(["", "## 関連する公開情報"])
    lines.extend([f"- {item['title']}" for item in brief["related_public_info"]] or ["- 該当なし"])
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(f"[info] MTG準備レポート生成: {output_path}")


def check_upcoming_meetings(enriched_events, cases, public_records):
    """一定時間以内の予定に対して準備ブリーフを生成する。"""
    briefs = []
    window_end = NOW + timedelta(hours=BRIEF_WINDOW_HOURS)

    for event in enriched_events:
        start = dateparser.parse(event["start_at"]).astimezone(JST)
        if not (NOW <= start <= window_end):
            continue

        related_case_ids = [item["id"] for item in event["related_cases"]]
        full_cases = [case for case in cases if case.get("id") in related_case_ids]
        public_by_id = {item["id"]: item for item in public_records}
        full_public = [public_by_id[item["id"]] for item in event["related_public_info"] if item["id"] in public_by_id]

        brief = build_brief_record(event, full_cases, full_public)
        write_brief_files(brief)
        write_legacy_meeting_prep(brief)
        briefs.append(brief)

    if not briefs:
        print(f"[info] {BRIEF_WINDOW_HOURS}時間以内の予定はありません。")


def main():
    args = parse_args()
    print(f"[info] カレンダー同期開始: {NOW}")

    cases = load_case_records()
    public_records = load_public_records()

    if args.events_file:
        raw_events = load_events_from_file(Path(args.events_file))
    else:
        from googleapiclient.discovery import build

        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)
        raw_events = fetch_events(service)

    enriched_events = [enrich_event(event, cases, public_records) for event in raw_events]
    enriched_events.sort(key=lambda item: item["start_at"])
    save_today_calendar(enriched_events)
    check_upcoming_meetings(enriched_events, cases, public_records)


if __name__ == "__main__":
    main()
