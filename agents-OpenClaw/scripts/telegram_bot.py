"""
telegram_bot.py
ともさん向けの Telegram コマンドを受ける秘書 bot。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time

import requests

from activity_draft import activity_draft_to_telegram_text, build_activity_draft_payload
from case_update import update_case_status
from morning_brief import build_brief_payload, payload_to_telegram_text
from openclaw_core import (
    TELEGRAM_DIR,
    build_followup_queue,
    build_judgment_board,
    build_query_record,
    find_related_cases,
    find_related_public_info,
    load_calendar_events,
    load_case_records,
    load_public_records,
    search_stakeholders,
)
from tomo_profile import add_preference, learn_from_feedback, load_profile, profile_to_text


OFFSET_PATH = TELEGRAM_DIR / "telegram_offset.json"
TUTORIAL_STATE_PATH = TELEGRAM_DIR / "tutorial_state.json"
CASE_ID_PATTERN = re.compile(r"(case_[a-zA-Z0-9]+)")
TODAY_HINTS = ("今日", "要点", "予定", "ブリーフ", "朝")
BOARD_HINTS = ("判断", "決める", "判断ボード", "本人判断")
FOLLOWUP_HINTS = ("フォローアップ", "残タスク", "残件", "未処理", "追う")
PUBLIC_HINTS = ("公開情報", "議会", "資料", "お知らせ")
RSS_HINTS = ("rss", "RSS", "新着")
SEARCH_HINTS = ("似た", "過去", "相談", "案件", "探", "検索")
HELP_HINTS = ("help", "ヘルプ", "使い方", "どう使", "何ができる")
SKIP_HINTS = ("skip", "スキップ", "あとで", "今はいい", "また今度")
PREFERENCE_HINTS = ("優先", "重視", "上に", "短く", "詳しく", "見やすく", "読みやすく")
THANKS_HINTS = ("ありがとう", "助かった", "了解", "わかった", "OK", "ok")
ARTICLE_HINTS = ("記事", "投稿", "note", "Note", "インスタ", "Instagram", "instagram", "下書き", "キャプション")
PERSON_HINTS = ("人物", "支援者", "関係者", "人名")
GROUP_HINTS = ("団体", "自治会", "後援会", "グループ")
REGION_HINTS = ("地域", "地区", "エリア")


def parse_args():
    parser = argparse.ArgumentParser(description="Telegram command bot")
    parser.add_argument("--loop", action="store_true", help="ロングポーリングを継続する")
    parser.add_argument("--poll-seconds", type=int, default=20, help="getUpdates の timeout 秒")
    return parser.parse_args()


def get_bot_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN が未設定です。")
    return token


def get_authorized_chat_id() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def telegram_api(method: str, payload: dict):
    token = get_bot_token()
    response = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=35)
    response.raise_for_status()
    return response.json()


def load_offset() -> int:
    payload = read_json_file(OFFSET_PATH)
    return int(payload.get("offset", 0))


def save_offset(offset: int):
    write_json_file(OFFSET_PATH, {"offset": offset})


def read_json_file(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def write_json_file(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_tutorial_states() -> dict:
    payload = read_json_file(TUTORIAL_STATE_PATH)
    return payload if isinstance(payload, dict) else {}


def save_tutorial_states(states: dict):
    write_json_file(TUTORIAL_STATE_PATH, states)


def get_tutorial_state(chat_id: str) -> dict:
    states = load_tutorial_states()
    state = states.get(chat_id)
    if isinstance(state, dict):
        return state
    return {"step": "none", "completed": False}


def set_tutorial_state(chat_id: str, *, step: str, completed: bool | None = None):
    states = load_tutorial_states()
    state = states.get(chat_id, {"step": "none", "completed": False})
    state["step"] = step
    if completed is not None:
        state["completed"] = completed
    states[chat_id] = state
    save_tutorial_states(states)


def compact_query(text: str) -> str:
    cleaned = text
    for token in [
        "公開情報",
        "公開",
        "RSS",
        "rss",
        "新着",
        "議会",
        "資料",
        "お知らせ",
        "案件",
        "相談",
        "似た",
        "過去",
        "探して",
        "検索",
        "見たい",
        "教えて",
        "記事",
        "投稿",
        "下書き",
        "note",
        "Note",
        "インスタ",
        "Instagram",
        "instagram",
        "キャプション",
        "ありますか",
        "ある",
        "ですか",
        "について",
        "を",
        "？",
        "?",
    ]:
        cleaned = cleaned.replace(token, " ")
    cleaned = " ".join(cleaned.split())
    return cleaned or text.strip()


def extract_case_id(text: str) -> str:
    match = CASE_ID_PATTERN.search(text or "")
    return match.group(1) if match else ""


def get_updates(offset: int, timeout_seconds: int) -> list[dict]:
    payload = {"timeout": timeout_seconds}
    if offset > 0:
        payload["offset"] = offset
    result = telegram_api("getUpdates", payload)
    return result.get("result", [])


def send_reply(chat_id: str, text: str):
    telegram_api("sendMessage", {"chat_id": chat_id, "text": text[:4000]})


def format_case_results(query: str) -> str:
    results = find_related_cases(build_query_record(query), load_case_records(), limit=5)
    if not results:
        return f"類似案件は見つかりませんでした: {query}"

    lines = [f"類似案件: {query}"]
    for item in results:
        lines.append(f"- {item['title']} | score={item['score']} | {item.get('route') or '未分類'}")
        if item.get("location"):
            lines.append(f"  場所: {item['location']}")
    return "\n".join(lines)


def format_case_detail(case_id: str) -> str:
    cases = load_case_records()
    case = next((item for item in cases if item.get("id") == case_id or item.get("id", "").startswith(case_id)), None)
    if case is None:
        return f"案件が見つかりませんでした: {case_id}"

    lines = [
        f"案件: {case['title']}",
        f"ID: {case['id']}",
        f"場所: {case.get('location') or '未設定'}",
        f"緊急度: {case.get('urgency', 'medium')}",
        f"ルート: {case.get('route') or '未設定'}",
        f"リスク: {case.get('risk_level', 'low')} / {' / '.join(case.get('risk_flags', [])[:3]) or 'なし'}",
        f"公開ステータス: {case.get('status_public') or '未設定'}",
        f"要約: {case.get('summary') or 'なし'}",
    ]
    if case.get("decision_options"):
        lines.append("判断候補:")
        lines.extend([f"- {item}" for item in case["decision_options"][:4]])
    if case.get("open_questions"):
        lines.append("確認したいこと:")
        lines.extend([f"- {item}" for item in case["open_questions"][:3]])
    return "\n".join(lines)


def format_public_results(query: str, *, title: str) -> str:
    results = find_related_public_info(build_query_record(query), load_public_records(), limit=5)
    if not results:
        return f"{title}は見つかりませんでした: {query}"

    lines = [f"{title}: {query}"]
    for item in results:
        lines.append(f"- {item['title']} ({item['published_at']})")
    return "\n".join(lines)


def format_board_text() -> str:
    board = build_judgment_board(load_case_records(), events=load_calendar_events())
    lines = [
        "本人判断ボード",
        f"- 本人判断待ち: {board['summary']['principal_decision_count']}件",
        f"- 今日中に見たい案件: {board['summary']['due_today_count']}件",
        f"- リスク確認: {board['summary']['risk_count']}件",
    ]
    if board["must_decide_today"]:
        lines.append("")
        lines.append("今日まず決めること")
        for item in board["must_decide_today"][:5]:
            options = " / ".join(item["decision_options"][:2])
            lines.append(f"- {item['title']} | {options}")
    return "\n".join(lines)


def format_followup_text() -> str:
    queue = build_followup_queue(load_case_records())
    lines = [
        "フォローアップ",
        f"- 稼働中: {queue['summary']['active_count']}件",
        f"- 緊急: {queue['summary']['urgent_count']}件",
        f"- 超過: {queue['summary']['overdue_count']}件",
    ]
    if queue["urgent"]:
        lines.append("")
        lines.append("急ぎ")
        for item in queue["urgent"][:5]:
            lines.append(f"- {item['case_title']} ({item['status']})")
    if queue["overdue"]:
        lines.append("")
        lines.append("超過")
        for item in queue["overdue"][:5]:
            lines.append(f"- {item['case_title']} ({item['due_at'][:10] if item.get('due_at') else '期限未設定'})")
    return "\n".join(lines)


def format_stakeholder_results(kind: str, query: str) -> str:
    if not query.strip():
        return f"使い方: /{kind} キーワード"
    results = search_stakeholders(kind, query, limit=5)
    if not results:
        return f"{kind} メモリは見つかりませんでした: {query}"

    title_map = {"person": "人物メモリ", "group": "団体メモリ", "region": "地域メモリ"}
    lines = [f"{title_map.get(kind, kind)}: {query}"]
    for item in results:
        lines.append(f"- {item['name']}")
        regions = ", ".join(item.get("regions", [])[:3]) or "未設定"
        topics = ", ".join(item.get("recent_topics", [])[:3]) or "未設定"
        lines.append(f"  地域: {regions}")
        lines.append(f"  話題: {topics}")
        if item.get("open_loops"):
            lines.append(f"  未解決: {item['open_loops'][0]}")
    return "\n".join(lines)


def format_decision_text(remainder: str) -> str:
    if not remainder.strip():
        return "使い方: /decide case_xxx 判断内容"

    parts = remainder.split(" ", 1)
    case_id = parts[0]
    decision_text = parts[1].strip() if len(parts) == 2 else ""
    if not decision_text:
        return format_case_detail(case_id)

    payload = update_case_status(
        case_id,
        "",
        follow_up_status="pending",
        decision_result=decision_text,
        owner="secretary",
        public_message="内部で判断結果を整理し、次の対応へ進めています。",
    )
    return "\n".join(
        [
            f"判断結果を保存しました: {payload['case']['title']}",
            f"- 決定: {decision_text}",
            f"- 次の状態: {payload['case']['follow_up_status']}",
        ]
    )


def start_tutorial(chat_id: str) -> str:
    set_tutorial_state(chat_id, step="choose_first_action", completed=False)
    return "\n".join(
        [
            "はじめまして。政治家秘書の使い方を1分で案内します。",
            "",
            "まず覚えることは4つです。",
            "1. /today で朝ブリーフ",
            "2. /board で本人判断ボード",
            "3. /followup で残タスク確認",
            "4. /person /group /region で関係者メモリ検索",
            "",
            "今すぐ試すなら、次のどれかを返してください。",
            "- 今日を見たい",
            "- 判断ボードを見たい",
            "- スキップ",
        ]
    )


def complete_tutorial(chat_id: str) -> str:
    set_tutorial_state(chat_id, step="done", completed=True)
    return "\n".join(
        [
            "チュートリアルはここまでです。",
            "これからは自然な言い方でも大丈夫です。",
            "",
            "例:",
            "- 今日は何を決める？",
            "- フォローアップは残ってる？",
            "- 鹿折地区の地域メモを見たい",
            "- 子育て案件を上に出して",
            "",
            "困ったら /help で一覧を出せます。",
        ]
    )


def handle_tutorial_message(chat_id: str, text: str) -> str:
    state = get_tutorial_state(chat_id)
    step = state.get("step", "none")
    lowered = text.lower()

    if any(hint in lowered or hint in text for hint in SKIP_HINTS):
        return complete_tutorial(chat_id)

    if step == "choose_first_action":
        if any(hint in text for hint in BOARD_HINTS):
            set_tutorial_state(chat_id, step="awaiting_preference")
            return format_board_text() + "\n\n最後に、重視したいテーマや地域があれば自然に送ってください。"
        if any(hint in text for hint in TODAY_HINTS):
            set_tutorial_state(chat_id, step="awaiting_preference")
            return payload_to_telegram_text(build_brief_payload()) + "\n\n最後に、重視したいテーマや地域があれば自然に送ってください。"
        return "「今日を見たい」「判断ボードを見たい」「スキップ」のどれかを返してください。"

    if step == "awaiting_preference":
        profile, changes = learn_from_feedback(text)
        response = render_learning_reply(profile, changes)
        return response + "\n\n" + complete_tutorial(chat_id)

    return start_tutorial(chat_id)


def render_learning_reply(profile: dict, changes: list[str]) -> str:
    if changes:
        return "\n".join(["好みとして保存しました。", *[f"- {change}" for change in changes[:5]], "", profile_to_text(profile)])
    return "フィードバックを保存しました。次の最適化材料として残します。"


def format_learning_reply(text: str) -> str:
    profile, changes = learn_from_feedback(text)
    return render_learning_reply(profile, changes)


def interpret_natural_language(text: str, *, chat_id: str) -> str:
    if any(hint in text for hint in HELP_HINTS):
        return start_tutorial(chat_id)

    if any(hint in text for hint in THANKS_HINTS):
        return "了解しました。必要なときは自然な言い方のままで大丈夫です。困ったら /tutorial で案内できます。"

    case_id = extract_case_id(text)
    if case_id and ("完了" in text or "閉じ" in text or "done" in text.lower()):
        payload = update_case_status(case_id, "closed", public_message="この案件の一次対応を完了として整理しました。")
        return f"案件を完了にしました: {payload['case']['title']}"

    if case_id and ("保留" in text or "hold" in text.lower() or "継続確認" in text):
        payload = update_case_status(case_id, "review", public_message="内部で継続確認する案件として保留・整理しました。")
        return f"案件を保留にしました: {payload['case']['title']}"

    if any(hint in text for hint in BOARD_HINTS):
        return format_board_text()

    if any(hint in text for hint in FOLLOWUP_HINTS):
        return format_followup_text()

    if any(hint in text for hint in TODAY_HINTS):
        return payload_to_telegram_text(build_brief_payload())

    if any(hint in text for hint in ARTICLE_HINTS):
        return activity_draft_to_telegram_text(build_activity_draft_payload(query=compact_query(text)))

    if any(hint in text for hint in RSS_HINTS):
        return format_public_results(compact_query(text), title="関連RSS情報")

    if any(hint in text for hint in PUBLIC_HINTS):
        return format_public_results(compact_query(text), title="関連公開情報")

    if any(hint in text for hint in PREFERENCE_HINTS):
        return format_learning_reply(text)

    if "地区" in text or any(hint in text for hint in REGION_HINTS):
        return format_stakeholder_results("region", compact_query(text))

    if any(hint in text for hint in GROUP_HINTS):
        return format_stakeholder_results("group", compact_query(text))

    if any(hint in text for hint in PERSON_HINTS):
        return format_stakeholder_results("person", compact_query(text))

    if any(hint in text for hint in SEARCH_HINTS) or len(text.strip()) >= 8:
        return format_case_results(compact_query(text))

    return ""


def handle_command(text: str) -> str:
    command, _, remainder = text.partition(" ")
    remainder = remainder.strip()

    if command in {"/start", "/tutorial"}:
        return start_tutorial(get_authorized_chat_id() or "default")
    if command == "/help":
        return "\n".join(
            [
                "使えるコマンド",
                "/tutorial",
                "/today",
                "/board",
                "/followup",
                "/search 通学路",
                "/case case_xxx",
                "/public 子育て",
                "/rss 福祉",
                "/person 佐藤",
                "/group 自治会",
                "/region 鹿折",
                "/decide case_xxx 担当課へ確認する",
                "/done case_xxx",
                "/hold case_xxx",
                "/draft 子育て",
                "/feedback 子育て案件を上に出してほしい",
                "/prefer topic 子育て",
                "/prefer region 鹿折地区",
                "/profile",
            ]
        )
    if command == "/today":
        return payload_to_telegram_text(build_brief_payload())
    if command == "/board":
        return format_board_text()
    if command == "/followup":
        return format_followup_text()
    if command == "/search":
        return format_case_results(remainder) if remainder else "使い方: /search 通学路"
    if command == "/case":
        return format_case_detail(remainder) if remainder else "使い方: /case case_xxx"
    if command == "/public":
        return format_public_results(remainder, title="関連公開情報") if remainder else "使い方: /public 通学路"
    if command == "/rss":
        return format_public_results(remainder, title="関連RSS情報") if remainder else "使い方: /rss 子育て"
    if command == "/person":
        return format_stakeholder_results("person", remainder)
    if command == "/group":
        return format_stakeholder_results("group", remainder)
    if command == "/region":
        return format_stakeholder_results("region", remainder)
    if command == "/decide":
        return format_decision_text(remainder)
    if command == "/draft":
        if not remainder:
            return "使い方: /draft 子育て"
        return activity_draft_to_telegram_text(build_activity_draft_payload(query=remainder))
    if command == "/done":
        if not remainder:
            return "使い方: /done case_xxx"
        payload = update_case_status(
            remainder,
            "closed",
            follow_up_status="completed",
            public_message="この案件の一次対応を完了として整理しました。",
        )
        return f"案件を完了にしました: {payload['case']['title']}"
    if command == "/hold":
        if not remainder:
            return "使い方: /hold case_xxx"
        payload = update_case_status(
            remainder,
            "review",
            follow_up_status="watching",
            public_message="内部で継続確認する案件として保留・整理しました。",
        )
        return f"案件を保留にしました: {payload['case']['title']}"
    if command == "/feedback":
        if not remainder:
            return "使い方: /feedback 子育て案件を上に出してほしい"
        return format_learning_reply(remainder)
    if command == "/prefer":
        parts = remainder.split(" ", 1)
        if len(parts) != 2:
            return "使い方: /prefer topic 子育て"
        kind, value = parts
        add_preference(kind, value)
        return f"設定しました: {kind} = {value}"
    if command == "/profile":
        return profile_to_text(load_profile())
    return "コマンドが分かりません。/help を送ると一覧を返します。"


def handle_message(message: dict):
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        return

    authorized_chat_id = get_authorized_chat_id()
    if authorized_chat_id and chat_id != authorized_chat_id:
        return

    if text.startswith("/"):
        try:
            if text.split(" ", 1)[0] in {"/start", "/tutorial"}:
                reply = start_tutorial(chat_id)
            else:
                reply = handle_command(text)
        except SystemExit as exc:
            reply = str(exc)
        if reply:
            send_reply(chat_id, reply)
        return

    state = get_tutorial_state(chat_id)
    if state.get("step") not in {"none", "done"}:
        reply = handle_tutorial_message(chat_id, text)
        send_reply(chat_id, reply)
        return

    reply = interpret_natural_language(text, chat_id=chat_id)
    if reply:
        send_reply(chat_id, reply)
        return

    if not state.get("completed", False):
        send_reply(chat_id, start_tutorial(chat_id))
        return

    profile, changes = learn_from_feedback(text, source="telegram_freeform")
    if changes:
        send_reply(chat_id, render_learning_reply(profile, changes))
        return
    send_reply(chat_id, "メッセージを秘書フィードバックとして保存しました。必要なら /tutorial で使い方を案内します。")


def process_updates(timeout_seconds: int) -> int:
    offset = load_offset()
    updates = get_updates(offset=offset, timeout_seconds=timeout_seconds)
    new_offset = offset
    for update in updates:
        new_offset = max(new_offset, int(update["update_id"]) + 1)
        message = update.get("message") or update.get("edited_message")
        if message:
            handle_message(message)
    if new_offset != offset:
        save_offset(new_offset)
    return len(updates)


def main():
    args = parse_args()
    while True:
        process_updates(args.poll_seconds)
        if not args.loop:
            break
        time.sleep(1)


if __name__ == "__main__":
    main()
