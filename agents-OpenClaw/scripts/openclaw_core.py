"""
openclaw_core.py
OpenClaw の案件管理、公開情報連携、ブリーフ生成に使う共通ロジック。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency for local setup
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(os.environ.get("OPENCLAW_DATA_ROOT", PROJECT_ROOT))
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
CASES_DIR = DATA_DIR / "cases"
CASES_PUBLIC_DIR = DATA_DIR / "cases_public"
PUBLIC_DIR = DATA_DIR / "public" / "kesennuma"
BRIEFS_DIR = REPORTS_DIR / "briefs"
DAILY_BRIEF_DIR = REPORTS_DIR / "daily-briefing"
ACTIVITY_DRAFT_DIR = REPORTS_DIR / "activity-drafts"
RSS_DIR = DATA_DIR / "rss"
TELEGRAM_DIR = DATA_DIR / "telegram"
STAKEHOLDERS_DIR = DATA_DIR / "stakeholders"
STAKEHOLDER_PEOPLE_DIR = STAKEHOLDERS_DIR / "people"
STAKEHOLDER_GROUPS_DIR = STAKEHOLDERS_DIR / "groups"
STAKEHOLDER_REGIONS_DIR = STAKEHOLDERS_DIR / "regions"
FOLLOWUPS_DIR = DATA_DIR / "followups"
JUDGMENT_BOARD_DIR = REPORTS_DIR / "judgment-board"
CALENDAR_DIR = DATA_DIR / "calendar"

RISK_RULES_PATH = CONFIG_DIR / "risk_rules.json"

STOPWORDS = {
    "こと",
    "これ",
    "それ",
    "ため",
    "よう",
    "ところ",
    "さん",
    "です",
    "ます",
    "ある",
    "いる",
    "した",
    "して",
    "する",
    "いる",
    "なる",
    "また",
    "から",
    "まで",
    "について",
    "に関する",
    "おり",
    "より",
    "もの",
    "地域",
    "市民",
    "相談",
    "案件",
    "確認",
    "対応",
    "関連",
    "予定",
}

TAG_RULES = {
    "子育て": ["子育て", "保育", "保育園", "幼稚園", "こども", "子ども", "学童", "育児"],
    "教育": ["学校", "通学", "教育", "児童", "生徒", "部活", "再編"],
    "交通安全": ["横断歩道", "通学路", "信号", "交通", "安全", "道路", "歩道"],
    "防災": ["防災", "避難", "津波", "地震", "災害", "避難所"],
    "福祉": ["福祉", "介護", "高齢", "障がい", "障害", "福祉サービス"],
    "医療": ["病院", "医療", "診療", "健康", "検診"],
    "人口減少": ["人口減少", "移住", "定住", "少子化", "婚活"],
    "産業": ["雇用", "漁業", "観光", "商店", "事業者", "産業", "入札"],
    "議会": ["議会", "議案", "一般質問", "会議資料", "議会だより", "定例会", "委員会"],
}

ROUTE_LABELS = {
    "principal_decision": "本人判断",
    "secretary_action": "秘書対応",
    "admin_check": "行政確認",
    "watchlist": "経過観察",
}

RISK_LEVEL_ORDER = {"low": 1, "medium": 2, "high": 3}
ROUTE_ORDER = {"principal_decision": 3, "admin_check": 2, "secretary_action": 1, "watchlist": 0}
PRINCIPAL_TOPICS = {"交通安全", "教育", "防災", "福祉", "医療", "議会"}

DEFAULT_RISK_RULES = [
    {
        "flag": "約束リスク",
        "level": "medium",
        "keywords": ["必ず", "約束", "やります", "実施します", "対応します"],
    },
    {
        "flag": "公平性リスク",
        "level": "medium",
        "keywords": ["特別扱い", "優先して", "一部だけ", "うちだけ", "例外"],
    },
    {
        "flag": "事実未確認",
        "level": "medium",
        "keywords": ["未確認", "らしい", "かもしれない", "とのこと", "噂"],
    },
    {
        "flag": "選挙・党派リスク",
        "level": "high",
        "keywords": ["選挙", "票", "支持", "後援会", "党"],
    },
    {
        "flag": "行政権限リスク",
        "level": "medium",
        "keywords": ["決めます", "許可します", "補助金を出す", "行政でやる"],
    },
]

PUBLIC_STATUS_DEFAULTS = {
    "new": (
        "受付済み",
        "ご相談を受け付けました。内容の整理を始めています。",
    ),
    "open": (
        "受付済み",
        "ご相談を受け付けました。内容の整理を始めています。",
    ),
    "triage": (
        "確認中",
        "案件として整理し、公開情報や関連論点との照合を進めています。",
    ),
    "review": (
        "内部検討中",
        "内部で確認を進めています。公開できる範囲で進行状況を更新します。",
    ),
    "waiting_user": (
        "追加情報待ち",
        "案件化を進めています。場所や状況の補足があると、より具体的に確認できます。",
    ),
    "answered": (
        "回答・案内済み",
        "現時点で案内できる内容を整理しました。必要に応じて次の対応を検討します。",
    ),
    "closed": (
        "完了",
        "この案件の一次対応は完了しました。",
    ),
}


def ensure_directories():
    """OpenClaw が使う出力先ディレクトリを作成する。"""
    for path in [
        CASES_DIR,
        CASES_PUBLIC_DIR,
        PUBLIC_DIR,
        BRIEFS_DIR,
        DAILY_BRIEF_DIR,
        ACTIVITY_DRAFT_DIR,
        RSS_DIR,
        TELEGRAM_DIR,
        STAKEHOLDER_PEOPLE_DIR,
        STAKEHOLDER_GROUPS_DIR,
        STAKEHOLDER_REGIONS_DIR,
        FOLLOWUPS_DIR,
        JUDGMENT_BOARD_DIR,
        CALENDAR_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def now_jst() -> datetime:
    """JST の現在時刻を返す。"""
    return datetime.now(JST)


def parse_iso_datetime(value: str | None) -> datetime | None:
    """ISO 8601 文字列を JST datetime に変換する。"""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def read_text_if_exists(path: Path) -> str:
    """ファイルが存在すればテキストを返す。"""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def read_json_if_exists(path: Path, default=None):
    """ファイルが存在すれば JSON を返し、壊れていれば default を返す。"""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _strip_surrogates(text: str) -> str:
    """孤立サロゲート文字を除去して UTF-8 で安全な文字列にする。"""
    return text.encode("utf-8", errors="replace").decode("utf-8")


def write_json(path: Path, payload):
    """UTF-8 の整形済み JSON を書き込む。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _strip_surrogates(json.dumps(payload, ensure_ascii=False, indent=2)),
        encoding="utf-8",
    )


def write_markdown(path: Path, text: str):
    """UTF-8 の Markdown を書き込む。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_strip_surrogates(text), encoding="utf-8")


def send_telegram_message(message: str, *, parse_mode: str | None = None) -> bool:
    """Telegram にメッセージを送る。未設定時は False を返す。"""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        return False

    payload = {"chat_id": chat_id, "text": message}
    if parse_mode:
        payload["parse_mode"] = parse_mode

    response = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json=payload,
        timeout=10,
    )
    return response.ok


def slugify(text: str, fallback: str = "item", max_length: int = 32) -> str:
    """ファイル名向けの簡易 slug を返す。"""
    normalized = unicodedata.normalize("NFKC", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    if not slug:
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
        return f"{fallback}-{digest}"
    return slug[:max_length].strip("-") or fallback


def stable_id(prefix: str, *parts: str) -> str:
    """文字列群から安定した短い ID を作る。"""
    joined = "||".join(part for part in parts if part)
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def normalize_text(text: str) -> str:
    """比較用にテキストを正規化する。"""
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def clean_text_block(text: str) -> str:
    """表示用にテキストを整える。"""
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_csv_field(value: str | None) -> list[str]:
    """カンマ区切りや改行区切りの文字列を配列に変換する。"""
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,\n]", value) if item.strip()]


def coerce_string_list(value) -> list[str]:
    """str / list / tuple 混在入力を文字列配列へ変換する。"""
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if "," in stripped or "\n" in stripped:
            return split_csv_field(stripped)
        return [stripped]

    if isinstance(value, Iterable) and not isinstance(value, (dict, bytes, bytearray)):
        result: list[str] = []
        for item in value:
            result.extend(coerce_string_list(item))
        return result
    return [clean_text_block(str(value))]


def dedupe_keep_order(values: Iterable[str]) -> list[str]:
    """順序を保ったまま重複を除く。"""
    seen = set()
    result = []
    for value in values:
        cleaned = clean_text_block(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def extract_keywords(text: str, limit: int = 12) -> list[str]:
    """案件や公開情報の簡易検索に使うキーワードを抽出する。"""
    text = normalize_text(text)
    tokens = re.findall(r"[一-龥ぁ-んァ-ヶーa-z0-9]{2,}", text)
    filtered = [token for token in tokens if token not in STOPWORDS and not token.isdigit()]
    counts = Counter(filtered)
    return [token for token, _ in counts.most_common(limit)]


def derive_tags(*texts: str) -> list[str]:
    """定義済みキーワードからタグを推定する。"""
    joined = normalize_text(" ".join(texts))
    tags = []
    for tag, keywords in TAG_RULES.items():
        if any(keyword.lower() in joined for keyword in keywords):
            tags.append(tag)
    return tags


def summarize_text(text: str, limit: int = 140) -> str:
    """長文から短い要約用テキストを作る。"""
    cleaned = re.sub(r"\s+", " ", clean_text_block(text))
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def extract_people(text: str) -> list[str]:
    """簡易的に人名らしき表現を拾う。"""
    matches = re.findall(r"([一-龥ぁ-んァ-ヶA-Za-z0-9]+(?:さん|氏|様))", text or "")
    return dedupe_keep_order(matches)


def urgency_rank(value: str) -> int:
    """緊急度の比較用数値を返す。"""
    return {"high": 3, "medium": 2, "low": 1}.get((value or "").lower(), 0)


def max_risk_level(*levels: str) -> str:
    """複数のリスクレベルから最大のものを返す。"""
    best = "low"
    for level in levels:
        cleaned = (level or "").lower()
        if RISK_LEVEL_ORDER.get(cleaned, 0) > RISK_LEVEL_ORDER.get(best, 0):
            best = cleaned
    return best


def load_risk_rules() -> list[dict]:
    """設定ファイルまたはデフォルトからリスクルールを読む。"""
    payload = read_json_if_exists(RISK_RULES_PATH, default=DEFAULT_RISK_RULES)
    if isinstance(payload, list):
        return payload
    return DEFAULT_RISK_RULES


def infer_policy_signal(tags: list[str], urgency: str, related_case_count: int, related_public_count: int) -> str:
    """案件が政策テーマ化しそうかをざっくり判定する。"""
    principal_hits = len(PRINCIPAL_TOPICS & set(tags))
    if principal_hits >= 2 or related_case_count >= 3:
        return "strong"
    if principal_hits >= 1 or related_public_count >= 2 or urgency == "high":
        return "possible"
    return "none"


def detect_risk_flags(case: dict, issue: dict) -> tuple[list[str], str, list[str]]:
    """案件内容から簡易的にリスクを推定する。"""
    transcript = case.get("source_transcript", "")
    summary = case.get("summary", "")
    open_questions = " ".join(case.get("open_questions", []))
    next_actions = " ".join(case.get("next_actions", []))
    full_text = normalize_text(" ".join([case.get("title", ""), summary, transcript, open_questions, next_actions]))

    flags: list[str] = []
    levels: list[str] = []
    notes: list[str] = []
    for rule in load_risk_rules():
        keywords = [normalize_text(item) for item in coerce_string_list(rule.get("keywords"))]
        if any(keyword and keyword in full_text for keyword in keywords):
            flags.append(rule.get("flag", "要確認"))
            levels.append(rule.get("level", "medium"))

    if case.get("open_questions") or not case.get("location"):
        flags.append("事実未確認")
        levels.append("medium")
        if case.get("open_questions"):
            notes.append("未確認事項が残っているため、対外発信は慎重に扱う。")
        if not case.get("location"):
            notes.append("場所が未設定のため、担当課確認の前に追加ヒアリングが必要。")

    if "議会" in issue.get("tags", []):
        flags.append("対外発言リスク")
        levels.append("medium")
        notes.append("議会論点に接続するため、発言の整合性確認が必要。")

    if case.get("groups") and ("要望" in full_text or "陳情" in full_text):
        flags.append("公平性リスク")
        levels.append("medium")

    if case.get("urgency") == "high" and "事実未確認" in flags:
        levels.append("high")

    level = max_risk_level(*levels, case.get("risk_level", "low"))
    return dedupe_keep_order(flags), level, dedupe_keep_order(notes)


def infer_route_reason(case: dict, issue: dict, risk: dict) -> tuple[str, str]:
    """案件の処理ルートと理由を返す。"""
    explicit = clean_text_block(case.get("route") or case.get("route_hint") or case.get("triage", {}).get("route", ""))
    if explicit in ROUTE_LABELS:
        reason = clean_text_block(case.get("triage", {}).get("reason", "")) or "入力時に処理ルートが指定されたため"
        return explicit, reason

    tags = set(issue.get("tags", []))
    policy_signal = issue.get("policy_signal", "none")

    if risk.get("level") == "high":
        return "principal_decision", "高リスク案件のため、本人判断を優先する"

    if {"約束リスク", "選挙・党派リスク"} & set(risk.get("flags", [])):
        return "principal_decision", "対外的な判断リスクがあるため、本人判断が必要"

    if "議会" in tags or policy_signal == "strong":
        return "principal_decision", "議会論点や政策テーマにつながる可能性が高い"

    full_text = normalize_text(" ".join([case.get("title", ""), case.get("summary", ""), " ".join(case.get("next_actions", []))]))
    if any(token in full_text for token in ["担当課", "行政", "照会", "確認"]):
        return "admin_check", "行政確認が先行する案件"

    if case.get("urgency") == "low" and not case.get("open_questions") and not risk.get("flags"):
        return "watchlist", "緊急性が低く、継続監視でよい案件"

    return "secretary_action", "秘書側で一次整理と段取りを進められる案件"


def infer_decision_options(route: str, case: dict, issue: dict, risk: dict) -> list[str]:
    """本人や秘書が選びやすい選択肢を返す。"""
    options: list[str] = []
    flags = set(risk.get("flags", []))

    if route == "principal_decision":
        if "約束リスク" in flags or "対外発言リスク" in flags:
            options.append("本人から返答する")
        options.append("秘書から一次返信する")
        options.append("担当課へ確認する")
        if issue.get("policy_signal") in {"possible", "strong"}:
            options.append("議会質問候補にする")
        if case.get("location"):
            options.append("現地確認を先に入れる")
    elif route == "admin_check":
        options.extend(
            [
                "担当課へ確認する",
                "事実確認後に返信する",
                "現地確認を先に入れる" if case.get("location") else "追加ヒアリングする",
            ]
        )
    elif route == "watchlist":
        options.extend(
            [
                "経過観察する",
                "次回会合まで保留する",
                "類似案件が増えたら再判定する",
            ]
        )
    else:
        options.extend(
            [
                "秘書から一次返信する",
                "追加ヒアリングする",
                "関連資料を集める",
            ]
        )

    return dedupe_keep_order(options)[:4]


def infer_deadline(case: dict, route: str, risk: dict, created_at: str) -> str:
    """案件の初期期限をざっくり決める。"""
    explicit = clean_text_block(
        case.get("deadline")
        or case.get("due")
        or case.get("triage", {}).get("deadline", "")
        or case.get("follow_up", {}).get("due_at", "")
    )
    if explicit:
        return explicit

    base = parse_iso_datetime(created_at) or now_jst()
    if risk.get("level") == "high" or case.get("urgency") == "high":
        due = base + timedelta(days=1)
    elif route == "principal_decision":
        due = base + timedelta(days=2)
    elif case.get("urgency") == "low":
        due = base + timedelta(days=7)
    else:
        due = base + timedelta(days=3)
    due = due.replace(hour=18, minute=0, second=0, microsecond=0)
    return due.isoformat()


def infer_follow_up_actions(route: str, case: dict, risk: dict) -> list[str]:
    """案件の次アクション候補を作る。"""
    explicit = dedupe_keep_order(case.get("next_actions", []))
    if explicit:
        return explicit

    if route == "principal_decision":
        actions = ["本人判断を待つ", "関連案件を確認する"]
        if case.get("location"):
            actions.append("現地確認の要否を整理する")
        if "事実未確認" in risk.get("flags", []):
            actions.append("事実確認前の発信を止める")
        return dedupe_keep_order(actions)

    if route == "admin_check":
        actions = ["担当課へ確認する", "確認結果を踏まえて返信案を作る"]
        if case.get("location"):
            actions.append("現地写真や地図を集める")
        return dedupe_keep_order(actions)

    if route == "watchlist":
        return ["関連公開情報を監視する", "類似案件が増えたら再判定する"]

    actions = ["秘書から一次返信の下書きを作る", "必要なら追加ヒアリングする"]
    if case.get("location"):
        actions.append("関連する地域課題を確認する")
    return dedupe_keep_order(actions)


def normalize_case_record(case: dict) -> dict:
    """旧フィールドと Plan2 の構造化フィールドを共存させて正規化する。"""
    normalized = dict(case or {})
    source_payload = normalized.get("source") if isinstance(normalized.get("source"), dict) else {}
    entities_payload = normalized.get("entities") if isinstance(normalized.get("entities"), dict) else {}
    issue_payload = normalized.get("issue") if isinstance(normalized.get("issue"), dict) else {}
    triage_payload = normalized.get("triage") if isinstance(normalized.get("triage"), dict) else {}
    risk_payload = normalized.get("risk") if isinstance(normalized.get("risk"), dict) else {}
    follow_up_payload = normalized.get("follow_up") if isinstance(normalized.get("follow_up"), dict) else {}
    links_payload = normalized.get("links") if isinstance(normalized.get("links"), dict) else {}

    created_at = clean_text_block(normalized.get("created_at") or source_payload.get("received_at") or "") or now_jst().isoformat()
    updated_at = clean_text_block(normalized.get("updated_at") or "") or created_at
    transcript = clean_text_block(normalized.get("source_transcript") or normalized.get("transcript") or source_payload.get("transcript", ""))
    title = clean_text_block(normalized.get("title") or "") or summarize_text(normalized.get("summary") or transcript, limit=36) or "無題の案件"
    summary = clean_text_block(normalized.get("summary") or "") or summarize_text(transcript or title, limit=180)
    location = clean_text_block(normalized.get("location") or normalized.get("region") or entities_payload.get("region", ""))

    people = dedupe_keep_order(
        coerce_string_list(entities_payload.get("people"))
        + coerce_string_list(normalized.get("people"))
        + extract_people(transcript)
    )
    groups = dedupe_keep_order(coerce_string_list(entities_payload.get("groups")) + coerce_string_list(normalized.get("groups")))
    region = clean_text_block(entities_payload.get("region") or normalized.get("region") or location)
    tags = dedupe_keep_order(
        coerce_string_list(issue_payload.get("tags"))
        + coerce_string_list(normalized.get("tags"))
        + derive_tags(title, summary, transcript, location, region, " ".join(groups))
    )
    keywords = dedupe_keep_order(
        coerce_string_list(issue_payload.get("keywords"))
        + coerce_string_list(normalized.get("keywords"))
        + extract_keywords(" ".join([title, summary, transcript, location, region, " ".join(people), " ".join(groups)]))
    )
    open_questions = dedupe_keep_order(
        coerce_string_list(issue_payload.get("facts_unconfirmed"))
        + coerce_string_list(normalized.get("open_questions"))
    )
    urgency = (clean_text_block(normalized.get("urgency") or "") or "medium").lower()
    if urgency not in {"low", "medium", "high"}:
        urgency = "medium"

    source = {
        "type": clean_text_block(source_payload.get("type") or normalized.get("source_type") or "citizen_consultation") or "citizen_consultation",
        "channel": clean_text_block(source_payload.get("channel") or normalized.get("channel") or "unknown") or "unknown",
        "received_at": clean_text_block(source_payload.get("received_at") or normalized.get("received_at") or created_at) or created_at,
    }

    related_case_ids = dedupe_keep_order(
        coerce_string_list(normalized.get("related_case_ids"))
        + coerce_string_list(links_payload.get("related_case_ids"))
    )
    related_public_info_ids = dedupe_keep_order(
        coerce_string_list(normalized.get("related_public_info_ids"))
        + coerce_string_list(links_payload.get("related_public_info_ids"))
    )
    policy_signal = clean_text_block(issue_payload.get("policy_signal") or normalized.get("policy_signal") or "")
    if not policy_signal:
        policy_signal = infer_policy_signal(tags, urgency, len(related_case_ids), len(related_public_info_ids))

    issue = {
        "tags": tags,
        "keywords": keywords,
        "policy_signal": policy_signal,
        "facts_confirmed": dedupe_keep_order(coerce_string_list(issue_payload.get("facts_confirmed"))),
        "facts_unconfirmed": open_questions,
        "topic_cluster": tags[:2],
    }

    base_case = {
        "title": title,
        "summary": summary,
        "location": location,
        "people": people,
        "groups": groups,
        "region": region or location,
        "tags": tags,
        "keywords": keywords,
        "urgency": urgency,
        "open_questions": open_questions,
        "next_actions": dedupe_keep_order(
            coerce_string_list(follow_up_payload.get("next_actions")) + coerce_string_list(normalized.get("next_actions"))
        ),
        "source_transcript": transcript,
    }

    risk_flags, inferred_risk_level, risk_notes = detect_risk_flags({**normalized, **base_case}, issue)
    risk = {
        "level": max_risk_level(risk_payload.get("level", ""), normalized.get("risk_level", ""), inferred_risk_level),
        "flags": dedupe_keep_order(coerce_string_list(risk_payload.get("flags")) + coerce_string_list(normalized.get("risk_flags")) + risk_flags),
        "notes": dedupe_keep_order(coerce_string_list(risk_payload.get("notes")) + risk_notes),
    }

    route, route_reason = infer_route_reason({**normalized, **base_case}, issue, risk)
    route = clean_text_block(triage_payload.get("route") or normalized.get("route") or route) or route
    if route not in ROUTE_LABELS:
        route = "secretary_action"
    triage_reason = clean_text_block(triage_payload.get("reason") or route_reason) or route_reason
    decision_options = dedupe_keep_order(
        coerce_string_list(triage_payload.get("decision_options"))
        + coerce_string_list(normalized.get("decision_options"))
        + infer_decision_options(route, {**normalized, **base_case}, issue, risk)
    )
    deadline = infer_deadline({**normalized, **base_case, "triage": triage_payload, "follow_up": follow_up_payload}, route, risk, created_at)
    triage = {
        "route": route,
        "requires_principal_decision": bool(
            triage_payload.get("requires_principal_decision")
            if "requires_principal_decision" in triage_payload
            else route == "principal_decision"
        ),
        "reason": triage_reason,
        "decision_options": decision_options,
        "deadline": deadline,
    }

    status_internal = clean_text_block(normalized.get("status_internal") or normalized.get("status") or "open") or "open"
    decision_result = clean_text_block(
        follow_up_payload.get("decision_result") or normalized.get("decision_result") or triage_payload.get("decision_result", "")
    )
    follow_up_status = clean_text_block(
        follow_up_payload.get("status") or normalized.get("follow_up_status") or ""
    )
    if not follow_up_status:
        if status_internal in {"answered", "closed"}:
            follow_up_status = "completed"
        elif triage["requires_principal_decision"] and not decision_result:
            follow_up_status = "needs_decision"
        elif route == "watchlist":
            follow_up_status = "watching"
        else:
            follow_up_status = "pending"
    owner = clean_text_block(follow_up_payload.get("owner") or normalized.get("owner") or "")
    if not owner:
        owner = "principal" if follow_up_status == "needs_decision" else "secretary"
    due_at = clean_text_block(follow_up_payload.get("due_at") or normalized.get("due") or triage["deadline"]) or triage["deadline"]
    follow_up = {
        "owner": owner,
        "status": follow_up_status,
        "due_at": due_at,
        "decision_result": decision_result,
        "next_actions": infer_follow_up_actions(
            route,
            {**normalized, **base_case, "next_actions": base_case["next_actions"]},
            risk,
        ),
    }

    person_ids = [stable_id("person", item) for item in people]
    group_ids = [stable_id("group", item) for item in groups]
    region_ids = [stable_id("region", region)] if region else []
    links = {
        "related_case_ids": related_case_ids,
        "related_public_info_ids": related_public_info_ids,
        "person_ids": dedupe_keep_order(coerce_string_list(links_payload.get("person_ids")) + person_ids),
        "group_ids": dedupe_keep_order(coerce_string_list(links_payload.get("group_ids")) + group_ids),
        "region_ids": dedupe_keep_order(coerce_string_list(links_payload.get("region_ids")) + region_ids),
    }

    case_id = clean_text_block(normalized.get("id") or "") or stable_id("case", created_at, title, summary)
    normalized.update(
        {
            "id": case_id,
            "title": title,
            "summary": summary,
            "location": location,
            "people": people,
            "groups": groups,
            "region": region or location,
            "tags": tags,
            "keywords": keywords,
            "urgency": urgency,
            "status": status_internal,
            "status_internal": status_internal,
            "created_at": created_at,
            "updated_at": updated_at,
            "open_questions": open_questions,
            "next_actions": follow_up["next_actions"],
            "related_case_ids": related_case_ids,
            "related_public_info_ids": related_public_info_ids,
            "source_transcript": transcript,
            "source": source,
            "entities": {
                "people": people,
                "groups": groups,
                "region": region or location,
            },
            "issue": issue,
            "triage": triage,
            "risk": risk,
            "follow_up": follow_up,
            "links": links,
            "route": triage["route"],
            "requires_principal_decision": triage["requires_principal_decision"],
            "decision_options": triage["decision_options"],
            "deadline": triage["deadline"],
            "risk_level": risk["level"],
            "risk_flags": risk["flags"],
            "owner": follow_up["owner"],
            "follow_up_status": follow_up["status"],
            "decision_result": follow_up["decision_result"],
            "due": follow_up["due_at"],
            "policy_signal": issue["policy_signal"],
        }
    )
    return normalized


def build_public_timeline_entry(status: str, message: str, created_at: str | None = None) -> dict:
    """公開向けの進行状況 1 件分を作る。"""
    return {
        "status": clean_text_block(status) or "受付済み",
        "message": clean_text_block(message) or "ご相談を受け付けました。",
        "created_at": created_at or now_jst().isoformat(),
    }


def needs_more_user_input(case: dict) -> bool:
    """公開向けに追加確認が必要かをざっくり判定する。"""
    transcript = clean_text_block(case.get("source_transcript", ""))
    summary = clean_text_block(case.get("summary", ""))
    location = clean_text_block(case.get("location", ""))
    open_questions = case.get("open_questions", [])
    return (not location) or len(transcript or summary) < 80 or len(open_questions) > 0


def derive_public_status(case: dict) -> tuple[str, str]:
    """内部ステータスや案件内容から公開向けステータスを決める。"""
    internal_status = clean_text_block(case.get("status_internal") or case.get("status") or "open").lower()
    if internal_status in PUBLIC_STATUS_DEFAULTS:
        return PUBLIC_STATUS_DEFAULTS[internal_status]
    if case.get("risk_level") == "high":
        return PUBLIC_STATUS_DEFAULTS["review"]
    if needs_more_user_input(case):
        return PUBLIC_STATUS_DEFAULTS["waiting_user"]
    return PUBLIC_STATUS_DEFAULTS["triage"]


def normalize_public_fields(case: dict) -> dict:
    """案件レコードへ公開向けフィールドを補完する。"""
    normalized = normalize_case_record(case)
    status_public, latest_public_message = derive_public_status(normalized)
    normalized["status_public"] = clean_text_block(normalized.get("status_public") or status_public) or status_public
    normalized["latest_public_message"] = clean_text_block(
        normalized.get("latest_public_message") or latest_public_message
    ) or latest_public_message
    normalized["requires_user_input"] = bool(
        normalized.get("requires_user_input")
        if "requires_user_input" in normalized
        else needs_more_user_input(normalized)
    )

    timeline = normalized.get("public_timeline") or []
    if timeline:
        normalized["public_timeline"] = [
            build_public_timeline_entry(
                item.get("status", normalized["status_public"]),
                item.get("message", normalized["latest_public_message"]),
                item.get("created_at"),
            )
            for item in timeline
        ]
    else:
        created_at = normalized.get("created_at") or now_jst().isoformat()
        normalized["public_timeline"] = [
            build_public_timeline_entry("受付済み", "ご相談を受け付けました。内容の整理を始めています。", created_at),
        ]
        if normalized["status_public"] != "受付済み":
            normalized["public_timeline"].append(
                build_public_timeline_entry(
                    normalized["status_public"],
                    normalized["latest_public_message"],
                    normalized.get("updated_at") or created_at,
                )
            )

    normalized["updated_at"] = clean_text_block(normalized.get("updated_at") or "") or (
        normalized["public_timeline"][-1]["created_at"] if normalized["public_timeline"] else normalized.get("created_at")
    )
    return normalized


def append_public_timeline(
    case: dict,
    status: str,
    message: str,
    *,
    created_at: str | None = None,
    update_latest: bool = True,
) -> dict:
    """案件に公開向けタイムラインを 1 件追加する。"""
    normalized = normalize_public_fields(case)
    entry = build_public_timeline_entry(status, message, created_at)
    normalized["public_timeline"] = [*normalized.get("public_timeline", []), entry]
    if update_latest:
        normalized["status_public"] = entry["status"]
        normalized["latest_public_message"] = entry["message"]
        normalized["updated_at"] = entry["created_at"]
    return normalized


def to_public_case_record(case: dict) -> dict:
    """フロントなどに渡せる公開向け案件 JSON を作る。"""
    normalized = normalize_public_fields(case)
    return {
        "id": normalized["id"],
        "title": normalized["title"],
        "summary": normalized["summary"],
        "location": normalized.get("location", ""),
        "tags": normalized.get("tags", []),
        "created_at": normalized["created_at"],
        "updated_at": normalized.get("updated_at", normalized["created_at"]),
        "status_public": normalized["status_public"],
        "latest_public_message": normalized["latest_public_message"],
        "requires_user_input": normalized["requires_user_input"],
        "public_timeline": normalized.get("public_timeline", []),
    }


def build_case_record(
    *,
    title: str = "",
    summary: str = "",
    transcript: str = "",
    location: str = "",
    people: list[str] | None = None,
    groups: list[str] | None = None,
    tags: list[str] | None = None,
    urgency: str = "medium",
    status: str = "open",
    source_type: str = "citizen_consultation",
    channel: str = "frontend",
    received_at: str | None = None,
    deadline: str = "",
    route_hint: str = "",
    open_questions: list[str] | None = None,
    next_actions: list[str] | None = None,
    facts_confirmed: list[str] | None = None,
    facts_unconfirmed: list[str] | None = None,
    related_case_ids: list[str] | None = None,
    related_public_info_ids: list[str] | None = None,
    created_at: str | None = None,
) -> dict:
    """相談内容から案件レコードを作る。"""
    created_at = created_at or received_at or now_jst().isoformat()
    transcript = clean_text_block(transcript)
    people = dedupe_keep_order((people or []) + extract_people(transcript))
    groups = dedupe_keep_order(groups or [])
    summary = clean_text_block(summary) or summarize_text(transcript or title, limit=180)
    title = clean_text_block(title) or summarize_text(summary or transcript, limit=36) or "無題の案件"
    location = clean_text_block(location)
    tags = dedupe_keep_order((tags or []) + derive_tags(title, summary, transcript, location, " ".join(groups)))

    case_record = {
        "id": stable_id("case", created_at, title, summary),
        "title": title,
        "summary": summary,
        "location": location,
        "people": people,
        "groups": groups,
        "tags": tags,
        "urgency": urgency,
        "status": status,
        "status_internal": status,
        "created_at": created_at,
        "updated_at": created_at,
        "open_questions": dedupe_keep_order((open_questions or []) + (facts_unconfirmed or [])),
        "next_actions": dedupe_keep_order(next_actions or []),
        "related_case_ids": dedupe_keep_order(related_case_ids or []),
        "related_public_info_ids": dedupe_keep_order(related_public_info_ids or []),
        "source_transcript": transcript,
        "source": {
            "type": source_type,
            "channel": channel,
            "received_at": created_at,
        },
        "issue": {
            "facts_confirmed": dedupe_keep_order(facts_confirmed or []),
            "facts_unconfirmed": dedupe_keep_order((facts_unconfirmed or []) + (open_questions or [])),
        },
        "triage": {
            "route": route_hint,
            "deadline": deadline,
        },
    }
    return normalize_public_fields(case_record)


def case_to_markdown(case: dict) -> str:
    """案件レコードを Markdown にする。"""
    lines = [
        f"# {case['title']}",
        "",
        f"- ID: {case['id']}",
        f"- 作成日時: {case['created_at']}",
        f"- 更新日時: {case['updated_at']}",
        f"- 内部ステータス: {case['status_internal']}",
        f"- 公開ステータス: {case.get('status_public') or '未設定'}",
        f"- 緊急度: {case['urgency']}",
        f"- ルート: {ROUTE_LABELS.get(case.get('route', ''), case.get('route', '未設定'))}",
        f"- 本人判断: {'要' if case.get('requires_principal_decision') else '不要'}",
        f"- 期限: {case.get('deadline') or '未設定'}",
        f"- フォローアップ: {case.get('follow_up_status') or '未設定'}",
        f"- 担当: {case.get('owner') or '未設定'}",
        f"- リスク: {case.get('risk_level', 'low')}",
        f"- 場所: {case['location'] or '未設定'}",
        f"- 地域: {case.get('region') or '未設定'}",
        f"- 関係者: {', '.join(case['people']) if case['people'] else '未設定'}",
        f"- 団体: {', '.join(case.get('groups', [])) if case.get('groups') else '未設定'}",
        f"- タグ: {', '.join(case['tags']) if case['tags'] else '未設定'}",
        f"- 入力元: {case.get('source', {}).get('type', '未設定')} / {case.get('source', {}).get('channel', '未設定')}",
        "",
        "## 要約",
        case["summary"] or "なし",
        "",
        "## トリアージ理由",
        case.get("triage", {}).get("reason") or "未設定",
        "",
        "## 判断候補",
    ]

    lines.extend([f"- {item}" for item in case.get("decision_options", [])] or ["- なし"])
    lines.extend(["", "## リスクフラグ"])
    lines.extend([f"- {item}" for item in case.get("risk_flags", [])] or ["- なし"])
    if case.get("risk", {}).get("notes"):
        lines.extend(["", "## リスクメモ"])
        lines.extend([f"- {item}" for item in case["risk"]["notes"]])

    lines.extend(["", "## 未確認事項"])
    lines.extend([f"- {item}" for item in case["open_questions"]] or ["- なし"])
    lines.extend(["", "## 次のアクション"])
    lines.extend([f"- {item}" for item in case["next_actions"]] or ["- なし"])
    lines.extend(["", "## 関連案件"])
    lines.extend([f"- {item}" for item in case["related_case_ids"]] or ["- なし"])
    lines.extend(["", "## 関連公開情報"])
    lines.extend([f"- {item}" for item in case["related_public_info_ids"]] or ["- なし"])
    lines.extend(["", "## 元の会話"])
    lines.append(case["source_transcript"] or "記録なし")
    return "\n".join(lines).strip() + "\n"


def stakeholder_directory(kind: str) -> Path:
    """種別に応じた関係者メモリの保存先を返す。"""
    mapping = {
        "person": STAKEHOLDER_PEOPLE_DIR,
        "group": STAKEHOLDER_GROUPS_DIR,
        "region": STAKEHOLDER_REGIONS_DIR,
    }
    return mapping.get(kind, STAKEHOLDER_PEOPLE_DIR)


def build_stakeholder_record(name: str, kind: str) -> dict:
    """空の関係者メモリを作る。"""
    cleaned_name = clean_text_block(name)
    return {
        "id": stable_id(kind, cleaned_name),
        "name": cleaned_name,
        "type": kind,
        "regions": [],
        "case_ids": [],
        "open_loops": [],
        "recent_topics": [],
        "notes": [],
        "last_contact_at": "",
        "updated_at": now_jst().isoformat(),
    }


def write_stakeholder_memories_for_case(case: dict):
    """案件から人・団体・地域メモリを更新する。"""
    ensure_directories()
    normalized = normalize_public_fields(case)
    entities = [
        ("person", item) for item in normalized.get("people", [])
    ] + [
        ("group", item) for item in normalized.get("groups", [])
    ]
    if normalized.get("region"):
        entities.append(("region", normalized["region"]))

    for kind, name in entities:
        record = build_stakeholder_record(name, kind)
        path = stakeholder_directory(kind) / f"{record['id']}.json"
        existing = read_json_if_exists(path, default={}) or {}
        if isinstance(existing, dict):
            record.update(existing)

        record["name"] = clean_text_block(record.get("name") or name)
        record["type"] = kind
        record["regions"] = dedupe_keep_order(
            coerce_string_list(record.get("regions"))
            + ([normalized.get("region", "")] if normalized.get("region") else [])
        )
        record["case_ids"] = dedupe_keep_order(coerce_string_list(record.get("case_ids")) + [normalized["id"]])
        record["open_loops"] = dedupe_keep_order(
            coerce_string_list(record.get("open_loops"))
            + normalized.get("open_questions", [])
            + ([normalized["title"]] if normalized.get("follow_up_status") not in {"completed", "closed"} else [])
        )[:12]
        record["recent_topics"] = dedupe_keep_order(
            coerce_string_list(record.get("recent_topics")) + normalized.get("tags", [])
        )[:10]
        summary_note = summarize_text(normalized.get("summary", "") or normalized.get("title", ""), limit=100)
        notes = record.get("notes", [])
        if not isinstance(notes, list):
            notes = []
        notes = [item for item in notes if isinstance(item, dict)]
        existing_cases = {item.get("case_id") for item in notes}
        if normalized["id"] not in existing_cases:
            notes.append(
                {
                    "case_id": normalized["id"],
                    "created_at": normalized.get("updated_at") or normalized.get("created_at"),
                    "text": summary_note,
                }
            )
        record["notes"] = notes[-8:]
        last_contact = parse_iso_datetime(record.get("last_contact_at")) or parse_iso_datetime(normalized.get("updated_at"))
        candidate_contact = parse_iso_datetime(normalized.get("updated_at")) or parse_iso_datetime(normalized.get("created_at"))
        if candidate_contact and (last_contact is None or candidate_contact >= last_contact):
            record["last_contact_at"] = candidate_contact.isoformat()
        record["updated_at"] = now_jst().isoformat()
        write_json(path, record)


def load_stakeholder_records(kind: str) -> list[dict]:
    """関係者メモリを一覧で返す。"""
    ensure_directories()
    records = []
    for path in sorted(stakeholder_directory(kind).glob("*.json")):
        payload = read_json_if_exists(path, default=None)
        if isinstance(payload, dict):
            records.append(payload)
    return sorted(records, key=lambda item: item.get("updated_at", ""), reverse=True)


def search_stakeholders(kind: str, query: str = "", *, limit: int = 5) -> list[dict]:
    """名前・地域・話題で関係者メモリを検索する。"""
    query_text = normalize_text(query)
    results = []
    for record in load_stakeholder_records(kind):
        haystack = normalize_text(
            " ".join(
                [
                    record.get("name", ""),
                    " ".join(coerce_string_list(record.get("regions"))),
                    " ".join(coerce_string_list(record.get("recent_topics"))),
                    " ".join(item.get("text", "") for item in record.get("notes", []) if isinstance(item, dict)),
                ]
            )
        )
        score = 1
        if query_text:
            if query_text in haystack:
                score += 5
            if query_text in normalize_text(record.get("name", "")):
                score += 3
        results.append({**record, "score": score})
    results.sort(key=lambda item: (-item.get("score", 0), item.get("updated_at", "")))
    return results[:limit]


def stakeholder_summary_from_case(case: dict) -> list[dict]:
    """案件に関係する関係者メモリの要約を返す。"""
    summaries: list[dict] = []
    seen_ids = set()
    for kind, names in [
        ("person", case.get("people", [])),
        ("group", case.get("groups", [])),
        ("region", [case.get("region", "")] if case.get("region") else []),
    ]:
        for record in search_stakeholders(kind, "", limit=50):
            if record.get("name") not in names or record.get("id") in seen_ids:
                continue
            seen_ids.add(record["id"])
            summaries.append(
                {
                    "id": record["id"],
                    "name": record.get("name", ""),
                    "type": record.get("type", kind),
                    "last_contact_at": record.get("last_contact_at", ""),
                    "open_loops": coerce_string_list(record.get("open_loops"))[:3],
                    "recent_topics": coerce_string_list(record.get("recent_topics"))[:3],
                }
            )
    return summaries[:6]


def build_followup_record(case: dict) -> dict:
    """案件 1 件分のフォローアップ記録を返す。"""
    normalized = normalize_public_fields(case)
    return {
        "id": stable_id("followup", normalized["id"]),
        "case_id": normalized["id"],
        "case_title": normalized["title"],
        "route": normalized.get("route", ""),
        "route_label": ROUTE_LABELS.get(normalized.get("route", ""), normalized.get("route", "")),
        "owner": normalized.get("owner", "secretary"),
        "status": normalized.get("follow_up_status", "pending"),
        "due_at": normalized.get("due", normalized.get("deadline", "")),
        "risk_level": normalized.get("risk_level", "low"),
        "requires_principal_decision": bool(normalized.get("requires_principal_decision")),
        "decision_options": normalized.get("decision_options", []),
        "decision_result": normalized.get("decision_result", ""),
        "next_actions": normalized.get("next_actions", []),
        "updated_at": normalized.get("updated_at", normalized.get("created_at")),
    }


def sync_followup_queue_for_case(case: dict) -> Path:
    """案件からフォローアップ記録を保存する。"""
    ensure_directories()
    followup = build_followup_record(case)
    path = FOLLOWUPS_DIR / f"{followup['case_id']}.json"
    write_json(path, followup)
    return path


def load_followup_records() -> list[dict]:
    """保存済みフォローアップ記録を一覧で返す。"""
    ensure_directories()
    records = []
    for path in sorted(FOLLOWUPS_DIR.glob("*.json")):
        payload = read_json_if_exists(path, default=None)
        if isinstance(payload, dict):
            records.append(payload)
    return sorted(records, key=lambda item: item.get("due_at", ""))


def build_followup_queue(cases: list[dict] | None = None, *, now: datetime | None = None) -> dict:
    """案件一覧からフォローアップキューを組み立てる。"""
    now = now or now_jst()
    if cases is None:
        cases = load_case_records()
    items = [build_followup_record(case) for case in cases]
    active = [item for item in items if item.get("status") not in {"completed", "closed"}]

    urgent = []
    overdue = []
    for item in active:
        due_at = parse_iso_datetime(item.get("due_at"))
        if due_at is not None and due_at < now:
            overdue.append(item)
        elif item.get("risk_level") == "high" or item.get("status") == "needs_decision":
            urgent.append(item)

    active.sort(
        key=lambda item: (
            item.get("status") != "needs_decision",
            RISK_LEVEL_ORDER.get(item.get("risk_level", "low"), 0) * -1,
            item.get("due_at", ""),
        )
    )
    return {
        "generated_at": now.isoformat(),
        "summary": {
            "active_count": len(active),
            "urgent_count": len(urgent),
            "overdue_count": len(overdue),
        },
        "active": active[:20],
        "urgent": urgent[:10],
        "overdue": overdue[:10],
    }


def load_calendar_events() -> list[dict]:
    """保存済みのカレンダーイベントを返す。"""
    payload = read_json_if_exists(CALENDAR_DIR / "today.json", default={}) or {}
    if isinstance(payload, dict):
        events = payload.get("events", [])
        if isinstance(events, list):
            return events
    return []


def case_to_board_entry(case: dict, *, reason: str = "") -> dict:
    """本人判断ボード向けの案件要約を返す。"""
    normalized = normalize_public_fields(case)
    return {
        "id": normalized["id"],
        "title": normalized["title"],
        "summary": summarize_text(normalized.get("summary", ""), limit=80),
        "route": normalized.get("route", ""),
        "route_label": ROUTE_LABELS.get(normalized.get("route", ""), normalized.get("route", "")),
        "reason": reason or normalized.get("triage", {}).get("reason", ""),
        "deadline": normalized.get("deadline", ""),
        "risk_level": normalized.get("risk_level", "low"),
        "risk_flags": normalized.get("risk_flags", []),
        "decision_options": normalized.get("decision_options", []),
        "location": normalized.get("location", ""),
        "follow_up_status": normalized.get("follow_up_status", ""),
    }


def build_judgment_board(
    cases: list[dict] | None = None,
    *,
    events: list[dict] | None = None,
    now: datetime | None = None,
) -> dict:
    """本人判断が必要な案件だけを抽出したボードを返す。"""
    now = now or now_jst()
    if cases is None:
        cases = load_case_records()
    if events is None:
        events = load_calendar_events()

    unresolved = [
        normalize_public_fields(case)
        for case in cases
        if (case.get("status_internal") or case.get("status") or "open").lower() not in {"answered", "closed"}
    ]
    due_today: list[dict] = []
    risk_alerts: list[dict] = []
    meeting_related: list[dict] = []
    overdue_followups: list[dict] = []
    must_decide: list[dict] = []

    meeting_case_ids = {
        item.get("id", "")
        for event in events
        for item in event.get("related_cases", [])
        if item.get("id")
    }

    for case in unresolved:
        deadline_dt = parse_iso_datetime(case.get("deadline"))
        due_passed = deadline_dt is not None and deadline_dt <= now
        if case.get("requires_principal_decision"):
            must_decide.append(case_to_board_entry(case))
            if due_passed or case.get("risk_level") == "high":
                due_today.append(case_to_board_entry(case, reason="今日中に判断したい案件"))

        if case.get("risk_level") == "high" or case.get("risk_flags"):
            risk_alerts.append(case_to_board_entry(case, reason="リスク確認が必要"))

        if case.get("id") in meeting_case_ids:
            meeting_related.append(case_to_board_entry(case, reason="予定に関係する案件"))

        follow_due = parse_iso_datetime(case.get("due"))
        if case.get("follow_up_status") not in {"completed", "closed"} and follow_due is not None and follow_due < now:
            overdue_followups.append(case_to_board_entry(case, reason="フォローアップ期限を超過"))

    must_decide.sort(key=lambda item: (-RISK_LEVEL_ORDER.get(item["risk_level"], 0), item.get("deadline", "")))
    due_today.sort(key=lambda item: (-RISK_LEVEL_ORDER.get(item["risk_level"], 0), item.get("deadline", "")))
    risk_alerts.sort(key=lambda item: (-RISK_LEVEL_ORDER.get(item["risk_level"], 0), item["title"]))
    meeting_related.sort(key=lambda item: (-RISK_LEVEL_ORDER.get(item["risk_level"], 0), item["title"]))
    overdue_followups.sort(key=lambda item: (-RISK_LEVEL_ORDER.get(item["risk_level"], 0), item.get("deadline", "")))

    return {
        "generated_at": now.isoformat(),
        "must_decide_today": due_today[:10],
        "risk_alerts": risk_alerts[:10],
        "meeting_related": meeting_related[:10],
        "overdue_followups": overdue_followups[:10],
        "principal_queue": must_decide[:20],
        "summary": {
            "principal_decision_count": len(must_decide),
            "due_today_count": len(due_today),
            "risk_count": len(risk_alerts),
            "meeting_related_count": len(meeting_related),
            "overdue_followups_count": len(overdue_followups),
        },
    }


def judgment_board_to_markdown(board: dict) -> str:
    """本人判断ボードを Markdown 化する。"""
    lines = [
        "# 本人判断ボード",
        "",
        f"- 生成日時: {board['generated_at']}",
        f"- 本人判断待ち: {board['summary']['principal_decision_count']}件",
        f"- 今日中に見たい案件: {board['summary']['due_today_count']}件",
        f"- リスク確認: {board['summary']['risk_count']}件",
        f"- 面会関連: {board['summary']['meeting_related_count']}件",
        f"- フォローアップ超過: {board['summary']['overdue_followups_count']}件",
        "",
        "## 今日中に見たい案件",
    ]
    lines.extend(
        [f"- {item['title']} | {item['reason']} | 選択肢: {' / '.join(item['decision_options'][:3])}" for item in board["must_decide_today"]]
        or ["- なし"]
    )
    lines.extend(["", "## リスク確認"])
    lines.extend(
        [f"- {item['title']} | {' / '.join(item['risk_flags'][:3]) or item['risk_level']}" for item in board["risk_alerts"]]
        or ["- なし"]
    )
    lines.extend(["", "## 面会関連"])
    lines.extend([f"- {item['title']}" for item in board["meeting_related"]] or ["- なし"])
    lines.extend(["", "## フォローアップ超過"])
    lines.extend([f"- {item['title']}" for item in board["overdue_followups"]] or ["- なし"])
    return "\n".join(lines).strip() + "\n"


def write_judgment_board_files(board: dict) -> dict[str, str]:
    """本人判断ボードを latest / dated で保存する。"""
    ensure_directories()
    date_prefix = board["generated_at"][:10]
    latest_md = JUDGMENT_BOARD_DIR / "judgment-board-latest.md"
    latest_json = JUDGMENT_BOARD_DIR / "judgment-board-latest.json"
    dated_md = JUDGMENT_BOARD_DIR / f"judgment-board-{date_prefix}.md"
    dated_json = JUDGMENT_BOARD_DIR / f"judgment-board-{date_prefix}.json"
    markdown = judgment_board_to_markdown(board)
    write_markdown(latest_md, markdown)
    write_markdown(dated_md, markdown)
    write_json(latest_json, board)
    write_json(dated_json, board)
    return {
        "latest_markdown": str(latest_md),
        "latest_json": str(latest_json),
        "dated_markdown": str(dated_md),
        "dated_json": str(dated_json),
    }


def write_case_files(case: dict):
    """案件の Markdown と JSON を保存する。"""
    ensure_directories()
    normalized = normalize_public_fields(case)
    date_prefix = normalized["created_at"][:10]
    filename = f"{date_prefix}-{slugify(normalized['title'], fallback='case')}"
    md_path = CASES_DIR / f"{filename}.md"
    json_path = CASES_DIR / f"{filename}.json"
    public_json_path = CASES_PUBLIC_DIR / f"{filename}.json"
    write_markdown(md_path, case_to_markdown(normalized))
    write_json(json_path, normalized)
    write_json(public_json_path, to_public_case_record(normalized))
    write_stakeholder_memories_for_case(normalized)
    sync_followup_queue_for_case(normalized)
    return md_path, json_path, public_json_path


def load_case_records() -> list[dict]:
    """保存済み案件を JSON から読み込む。"""
    ensure_directories()
    records = []
    for path in sorted(CASES_DIR.glob("*.json")):
        payload = read_json_if_exists(path, default=None)
        if isinstance(payload, dict):
            records.append(normalize_public_fields(payload))
    return sorted(records, key=lambda item: item.get("created_at", ""), reverse=True)


def load_public_case_records() -> list[dict]:
    """公開向け案件 JSON をまとめて返す。"""
    return [to_public_case_record(case) for case in load_case_records()]


def write_public_case_latest_snapshot() -> tuple[Path, list[dict]]:
    """公開向け案件一覧 latest.json を再生成する。"""
    ensure_directories()
    records = load_public_case_records()
    latest_path = CASES_PUBLIC_DIR / "latest.json"
    write_json(latest_path, records)
    return latest_path, records


def build_query_record(text: str = "", location: str = "", tags: list[str] | None = None) -> dict:
    """検索用の擬似レコードを作る。"""
    query_tags = dedupe_keep_order((tags or []) + derive_tags(text, location))
    region = clean_text_block(location)
    return {
        "id": "query",
        "title": summarize_text(text, limit=36) or "query",
        "summary": text,
        "location": location,
        "people": [],
        "groups": [],
        "region": region,
        "tags": query_tags,
        "keywords": extract_keywords(" ".join([text, location])),
        "open_questions": [],
        "next_actions": [],
        "route": "secretary_action",
    }


def score_case_similarity(query: dict, candidate: dict) -> int:
    """案件同士の関連度をざっくり数値化する。"""
    score = 0
    query_tags = set(query.get("tags", []))
    candidate_tags = set(candidate.get("tags", []))
    shared_tags = query_tags & candidate_tags
    score += len(shared_tags) * 6

    query_keywords = set(query.get("keywords", []))
    candidate_keywords = set(candidate.get("keywords", []))
    shared_keywords = query_keywords & candidate_keywords
    score += min(len(shared_keywords), 6) * 2

    query_location = normalize_text(query.get("location", "") or query.get("region", ""))
    candidate_location = normalize_text(candidate.get("location", "") or candidate.get("region", ""))
    if query_location and candidate_location and query_location in candidate_location:
        score += 5

    shared_people = set(query.get("people", [])) & set(candidate.get("people", []))
    score += len(shared_people) * 3

    shared_groups = set(query.get("groups", [])) & set(candidate.get("groups", []))
    score += len(shared_groups) * 3

    query_text = normalize_text(" ".join([query.get("title", ""), query.get("summary", "")]))
    candidate_text = normalize_text(" ".join([candidate.get("title", ""), candidate.get("summary", "")]))
    if query_text and candidate_text and (query_text in candidate_text or candidate_text in query_text):
        score += 4

    score += ROUTE_ORDER.get(candidate.get("route", ""), 0)
    return score


def find_related_cases(
    query: dict | str,
    cases: list[dict] | None = None,
    *,
    limit: int = 5,
    exclude_ids: Iterable[str] | None = None,
) -> list[dict]:
    """案件またはクエリ文字列に関連する案件候補を返す。"""
    query_record = query if isinstance(query, dict) else build_query_record(query)
    cases = cases if cases is not None else load_case_records()
    exclude_ids = set(exclude_ids or [])
    results = []

    for candidate in cases:
        if candidate.get("id") in exclude_ids:
            continue
        score = score_case_similarity(query_record, candidate)
        if score <= 0:
            continue
        results.append(
            {
                "id": candidate["id"],
                "title": candidate["title"],
                "score": score,
                "summary": candidate.get("summary", ""),
                "location": candidate.get("location", ""),
                "tags": candidate.get("tags", []),
                "status_public": candidate.get("status_public", ""),
                "route": candidate.get("route", ""),
                "risk_level": candidate.get("risk_level", "low"),
                "groups": candidate.get("groups", []),
            }
        )

    results.sort(key=lambda item: (-item["score"], item["title"]))
    return results[:limit]


def build_public_record(
    *,
    source: str,
    title: str,
    url: str,
    published_at: str,
    summary: str = "",
) -> dict:
    """公開情報レコードを作る。"""
    tags = derive_tags(title, summary, source)
    keywords = extract_keywords(" ".join([title, summary, source]))
    item_id = stable_id("public", source, url, title)
    return {
        "id": item_id,
        "source": source,
        "title": clean_text_block(title),
        "url": url,
        "published_at": published_at,
        "summary": clean_text_block(summary),
        "tags": tags,
        "keywords": keywords,
    }


def load_public_records() -> list[dict]:
    """最新の公開情報スナップショットを読む。"""
    ensure_directories()
    latest_path = PUBLIC_DIR / "latest.json"
    payload = read_json_if_exists(latest_path, default=[])
    return payload if isinstance(payload, list) else []


def public_records_to_markdown(records: list[dict], title: str) -> str:
    """公開情報一覧を Markdown 化する。"""
    lines = [f"# {title}", ""]
    if not records:
        lines.append("公開情報はありません。")
        return "\n".join(lines) + "\n"

    for item in records:
        lines.append(f"## {item['title']}")
        lines.append(f"- ID: {item['id']}")
        lines.append(f"- ソース: {item['source']}")
        lines.append(f"- 公開日: {item['published_at']}")
        lines.append(f"- URL: {item['url']}")
        lines.append(f"- タグ: {', '.join(item['tags']) if item['tags'] else '未設定'}")
        if item.get("summary"):
            lines.append("")
            lines.append(item["summary"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def write_public_snapshot(records: list[dict]):
    """公開情報の latest / 日付スナップショットを保存する。"""
    ensure_directories()
    date_prefix = now_jst().strftime("%Y-%m-%d")
    write_json(PUBLIC_DIR / "latest.json", records)
    write_json(PUBLIC_DIR / f"{date_prefix}.json", records)
    write_markdown(PUBLIC_DIR / "latest.md", public_records_to_markdown(records, "気仙沼市 公開情報 latest"))
    write_markdown(PUBLIC_DIR / f"{date_prefix}.md", public_records_to_markdown(records, f"気仙沼市 公開情報 {date_prefix}"))


def score_public_relevance(query: dict, item: dict) -> int:
    """案件や予定に対する公開情報の関連度を返す。"""
    score = 0
    shared_tags = set(query.get("tags", [])) & set(item.get("tags", []))
    score += len(shared_tags) * 6

    shared_keywords = set(query.get("keywords", [])) & set(item.get("keywords", []))
    score += min(len(shared_keywords), 6) * 2

    query_text = normalize_text(" ".join([query.get("title", ""), query.get("summary", "")]))
    item_text = normalize_text(" ".join([item.get("title", ""), item.get("summary", "")]))
    if query_text and item_text and (query_text in item_text or item_text in query_text):
        score += 4
    return score


def find_related_public_info(query: dict | str, public_records: list[dict] | None = None, *, limit: int = 5) -> list[dict]:
    """案件やテキストに関連する公開情報候補を返す。"""
    query_record = query if isinstance(query, dict) else build_query_record(query)
    public_records = public_records if public_records is not None else load_public_records()

    results = []
    for item in public_records:
        score = score_public_relevance(query_record, item)
        if score <= 0:
            continue
        results.append(
            {
                "id": item["id"],
                "title": item["title"],
                "url": item["url"],
                "published_at": item["published_at"],
                "tags": item.get("tags", []),
                "score": score,
            }
        )
    results.sort(key=lambda entry: (-entry["score"], entry["published_at"]), reverse=False)
    return results[:limit]


def build_event_query_record(event: dict) -> dict:
    """予定から案件・公開情報検索用の擬似レコードを作る。"""
    title = event.get("title", "")
    location = event.get("location", "")
    attendees = " ".join(event.get("attendees", []))
    description = event.get("description", "")
    tags = derive_tags(title, location, description)
    keywords = extract_keywords(" ".join([title, location, attendees, description]))
    return {
        "id": event.get("id", "event"),
        "title": title,
        "summary": description or title,
        "location": location,
        "people": event.get("attendees", []),
        "groups": [],
        "region": location,
        "tags": tags,
        "keywords": keywords,
        "open_questions": [],
        "next_actions": [],
    }


def build_brief_record(event: dict, related_cases: list[dict], related_public_info: list[dict]) -> dict:
    """予定向けのブリーフレコードを作る。"""
    tag_counter = Counter()
    open_questions = []
    next_actions = []
    risk_flags = []
    decision_focus = []
    stakeholder_items = []
    recent_contacts = []

    for case in related_cases:
        normalized = normalize_public_fields(case)
        for tag in normalized.get("tags", []):
            tag_counter[tag] += 1
        open_questions.extend(normalized.get("open_questions", []))
        next_actions.extend(normalized.get("next_actions", []))
        risk_flags.extend(normalized.get("risk_flags", []))
        decision_focus.extend(normalized.get("decision_options", []))
        stakeholder_items.extend(stakeholder_summary_from_case(normalized))
        recent_contacts.append(
            {
                "case_id": normalized["id"],
                "title": normalized["title"],
                "summary": summarize_text(normalized.get("summary", ""), limit=70),
                "updated_at": normalized.get("updated_at", normalized.get("created_at")),
            }
        )

    caution_points = []
    if "事実未確認" in risk_flags:
        caution_points.append("事実確認が済むまでは断定表現を避ける")
    if "約束リスク" in risk_flags:
        caution_points.append("その場で確約せず、確認後に返答する")
    if "公平性リスク" in risk_flags:
        caution_points.append("個別案件として扱いつつ、公平性の説明を意識する")
    if "対外発言リスク" in risk_flags:
        caution_points.append("過去発言や議会論点との整合性を確認する")

    return {
        "event_id": event["id"],
        "event_title": event["title"],
        "event_time": event["start_at"],
        "event_location": event.get("location", ""),
        "related_cases": related_cases,
        "related_public_info": related_public_info,
        "stakeholders": dedupe_keep_order([]) or stakeholder_items[:6],
        "recent_contacts": recent_contacts[:5],
        "recent_patterns": [{"tag": tag, "count": count} for tag, count in tag_counter.most_common(5)],
        "questions_to_ask": dedupe_keep_order(open_questions)[:5],
        "next_actions": dedupe_keep_order(next_actions)[:5],
        "decision_focus": dedupe_keep_order(decision_focus)[:4],
        "risk_flags": dedupe_keep_order(risk_flags),
        "caution_points": dedupe_keep_order(caution_points),
        "reference_docs": [{"title": item["title"], "url": item.get("url", "")} for item in related_public_info[:5]],
        "generated_at": now_jst().isoformat(),
    }


def brief_to_markdown(brief: dict) -> str:
    """ブリーフレコードを Markdown にする。"""
    lines = [
        f"# 準備ブリーフ: {brief['event_title']}",
        "",
        f"- 予定ID: {brief['event_id']}",
        f"- 開始: {brief['event_time']}",
        f"- 場所: {brief['event_location'] or '未設定'}",
        f"- 作成: {brief['generated_at']}",
        "",
        "## 関連案件",
    ]

    if brief["related_cases"]:
        for case in brief["related_cases"]:
            normalized = normalize_public_fields(case)
            lines.append(f"- {normalized['title']} ({normalized['id']})")
            if normalized.get("summary"):
                lines.append(f"  - 要約: {summarize_text(normalized['summary'], limit=100)}")
            if normalized.get("location"):
                lines.append(f"  - 場所: {normalized['location']}")
            if normalized.get("decision_options"):
                lines.append(f"  - 判断候補: {' / '.join(normalized['decision_options'][:3])}")
    else:
        lines.append("- 該当なし")

    lines.extend(["", "## 過去接点メモ"])
    if brief["recent_contacts"]:
        for item in brief["recent_contacts"]:
            lines.append(f"- {item['title']} ({item['updated_at'][:10]})")
            lines.append(f"  - {item['summary']}")
    else:
        lines.append("- 該当なし")

    lines.extend(["", "## 最近の論点"])
    if brief["recent_patterns"]:
        for pattern in brief["recent_patterns"]:
            lines.append(f"- {pattern['tag']} ({pattern['count']}件)")
    else:
        lines.append("- 該当なし")

    lines.extend(["", "## 今回確認したいこと"])
    lines.extend([f"- {item}" for item in brief["questions_to_ask"]] or ["- 特になし"])

    lines.extend(["", "## この場で決めたいこと"])
    lines.extend([f"- {item}" for item in brief["decision_focus"]] or ["- 特になし"])

    lines.extend(["", "## 慎重にしたいこと"])
    lines.extend([f"- {item}" for item in brief["caution_points"]] or ["- 特になし"])

    lines.extend(["", "## 次のアクション候補"])
    lines.extend([f"- {item}" for item in brief["next_actions"]] or ["- 特になし"])

    lines.extend(["", "## 関連する公開情報"])
    if brief["related_public_info"]:
        for item in brief["related_public_info"]:
            lines.append(f"- {item['title']} ({item['published_at']})")
            if item.get("url"):
                lines.append(f"  - URL: {item['url']}")
    else:
        lines.append("- 該当なし")

    return "\n".join(lines).strip() + "\n"


def write_brief_files(brief: dict):
    """ブリーフの Markdown と JSON を保存する。"""
    ensure_directories()
    date_prefix = brief["event_time"][:10]
    filename = f"{date_prefix}-{slugify(brief['event_title'], fallback='brief')}"
    md_path = BRIEFS_DIR / f"{filename}.md"
    json_path = BRIEFS_DIR / f"{filename}.json"
    write_markdown(md_path, brief_to_markdown(brief))
    write_json(json_path, brief)
    return md_path, json_path
