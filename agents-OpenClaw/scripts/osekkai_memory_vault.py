"""Consent-gated Obsidian-compatible episodic memory storage."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from osekkai_contracts import ContractError, SCHEMA_VERSION, require_uuid, validate_schema


KIND_DIRECTORIES = {
    "preference": "Preferences",
    "friction": "Frictions",
    "episode": "Episodes",
    "feedback": "Episodes",
    "community": "Communities",
}
SECRET_MARKER = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._-]{12,})",
    re.IGNORECASE,
)
COORDINATE_MARKER = re.compile(r"(?<!\d)(?:3[0-9]|4[0-6])\.\d{4,}\s*[,/]\s*(?:1[34][0-9])\.\d{4,}(?!\d)")


def _default_data_root() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "osekkai"


def _clean_text(value: str, maximum: int) -> str:
    clean = " ".join(value.strip().split())[:maximum]
    if SECRET_MARKER.search(clean) or COORDINATE_MARKER.search(clean):
        raise ContractError("memory text contains prohibited secret or exact coordinate data")
    return clean


class ObsidianMemoryVault:
    """Writes only schema-valid summaries under an opaque per-user folder."""

    def __init__(self, root: str | Path | None = None, *, data_root: str | Path | None = None):
        configured = root or os.environ.get("OSEKKAI_VAULT_ROOT", "").strip()
        base = Path(data_root or os.environ.get("OSEKKAI_DATA_ROOT", "").strip() or _default_data_root())
        self.root = Path(configured).expanduser().resolve() if configured else (base / "obsidian-vault").resolve()

    def _safe_path(self, *parts: str) -> Path:
        target = self.root.joinpath(*parts).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise ContractError("memory vault path escapes OSEKKAI_VAULT_ROOT") from exc
        return target

    def _user_root(self, user_id: str) -> Path:
        return self._safe_path("users", require_uuid(user_id, "memory.userId"))

    def _ensure_vault(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        obsidian = self._safe_path(".obsidian")
        obsidian.mkdir(parents=True, exist_ok=True)
        app_config = obsidian / "app.json"
        if not app_config.exists():
            self._atomic_write(app_config, "{}\n")

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = text.encode("utf-8")
        if len(encoded) > 32 * 1024:
            raise ContractError("memory note exceeds size limit")
        fd = -1
        temporary = ""
        try:
            fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
            with os.fdopen(fd, "wb") as handle:
                fd = -1
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = ""
        finally:
            if fd >= 0:
                os.close(fd)
            if temporary:
                Path(temporary).unlink(missing_ok=True)

    @contextmanager
    def _user_lock(self, user_id: str, timeout: float = 2.0) -> Iterator[None]:
        lock_path = self._safe_path(".locks", f"{require_uuid(user_id, 'memory.userId')}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
        if lock_path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout
        acquired = False
        try:
            while not acquired:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except (BlockingIOError, OSError):
                    if time.monotonic() >= deadline:
                        raise ContractError("memory vault lock timed out")
                    time.sleep(0.025)
            yield
        finally:
            if acquired:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
            handle.close()

    @staticmethod
    def _serialize_note(note: dict[str, Any]) -> str:
        ordered = (
            "schemaVersion", "id", "kind", "userId", "origin", "referenceType",
            "referenceId", "evidenceIds", "keywords", "confidence", "observedAt", "lastConfirmedAt",
            "retentionUntil",
        )
        frontmatter = ["---"]
        for key in ordered:
            frontmatter.append(f"{key}: {json.dumps(note[key], ensure_ascii=False)}")
        frontmatter.extend(["---", "", f"# {note['kind']}", "", note["summary"], ""])
        return "\n".join(frontmatter)

    @staticmethod
    def _parse_note(path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if len(lines) < 5 or lines[0] != "---":
            raise ContractError("memory note frontmatter is invalid")
        try:
            end = lines.index("---", 1)
        except ValueError as exc:
            raise ContractError("memory note frontmatter is invalid") from exc
        metadata: dict[str, Any] = {}
        for line in lines[1:end]:
            key, separator, raw = line.partition(":")
            if not separator or not key:
                raise ContractError("memory note metadata is invalid")
            try:
                metadata[key] = json.loads(raw.strip())
            except json.JSONDecodeError as exc:
                raise ContractError("memory note metadata is invalid") from exc
        body = "\n".join(lines[end + 1 :]).strip().splitlines()
        summary_lines = [line.strip() for line in body if line.strip() and not line.startswith("#")]
        metadata["summary"] = " ".join(summary_lines)
        validate_schema(metadata, "memory-note.schema.json")
        return metadata

    def write_note(self, note: dict[str, Any]) -> Path:
        clean = dict(note)
        clean["summary"] = _clean_text(str(clean.get("summary", "")), 280)
        clean["keywords"] = list(
            dict.fromkeys(_clean_text(str(value), 80) for value in clean.get("keywords", []) if str(value).strip())
        )[:16]
        validate_schema(clean, "memory-note.schema.json")
        user_id = clean["userId"]
        kind_directory = KIND_DIRECTORIES[clean["kind"]]
        note_id = require_uuid(clean["id"], "memory.id")
        with self._user_lock(user_id):
            self._ensure_vault()
            path = self._safe_path("users", user_id, kind_directory, f"{note_id}.md")
            self._atomic_write(path, self._serialize_note(clean))
        return path

    def write_profile_projection(self, profile: dict[str, Any]) -> Path:
        user_id = require_uuid(profile.get("userId"), "profile.userId")
        categories = [
            _clean_text(str(value), 80)
            for value in profile.get("preferredCategories", [])
            if isinstance(value, str) and value.strip()
        ][:20]
        frictions = sorted(
            key for key, value in profile.get("participationFriction", {}).items()
            if isinstance(value, dict) and value.get("value") is True
        )[:20]
        updated_at = str(profile.get("updatedAt", ""))
        text = "\n".join(
            [
                "---",
                f"schemaVersion: {json.dumps(SCHEMA_VERSION)}",
                f"userId: {json.dumps(user_id)}",
                f"updatedAt: {json.dumps(updated_at)}",
                "projection: true",
                "---",
                "",
                "# Profile projection",
                "",
                "このファイルはJSON Profileから生成される閲覧用Projectionです。",
                "",
                "## 好みのカテゴリ",
                *(f"- {value}" for value in categories),
                "",
                "## 参加のひっかかり",
                *(f"- {value}" for value in frictions),
                "",
            ]
        )
        with self._user_lock(user_id):
            self._ensure_vault()
            path = self._safe_path("users", user_id, "Profile.md")
            self._atomic_write(path, text)
        return path

    def list_notes(self, user_id: str, *, now: datetime | None = None) -> list[dict[str, Any]]:
        user_root = self._user_root(user_id)
        if not user_root.exists():
            return []
        values: list[dict[str, Any]] = []
        for directory in sorted(set(KIND_DIRECTORIES.values())):
            for path in self._safe_path("users", user_id, directory).glob("*.md"):
                try:
                    note = self._parse_note(path)
                except (ContractError, OSError):
                    continue
                if note.get("userId") != user_id:
                    continue
                if now is not None:
                    try:
                        if datetime.fromisoformat(note["retentionUntil"]) <= now:
                            continue
                    except (TypeError, ValueError):
                        continue
                values.append(note)
        return sorted(values, key=lambda item: (item["lastConfirmedAt"], item["id"]), reverse=True)

    def delete_note(self, user_id: str, note_id: str) -> bool:
        require_uuid(user_id, "memory.userId")
        require_uuid(note_id, "memory.id")
        with self._user_lock(user_id):
            for directory in sorted(set(KIND_DIRECTORIES.values())):
                path = self._safe_path("users", user_id, directory, f"{note_id}.md")
                if path.exists():
                    path.unlink()
                    return True
        return False

    def delete_profile_projection(self, user_id: str) -> bool:
        path = self._safe_path("users", require_uuid(user_id, "memory.userId"), "Profile.md")
        if not path.exists():
            return False
        with self._user_lock(user_id):
            path.unlink(missing_ok=True)
        return True

    def delete_reference(self, user_id: str, reference_id: str) -> int:
        removed = 0
        for note in self.list_notes(user_id):
            if (
                note.get("referenceId") == reference_id
                or reference_id in note.get("evidenceIds", [])
            ) and self.delete_note(user_id, note["id"]):
                removed += 1
        return removed

    def cleanup_expired(self, user_id: str, now: datetime) -> int:
        removed = 0
        for note in self.list_notes(user_id):
            try:
                expired = datetime.fromisoformat(note["retentionUntil"]) <= now
            except (TypeError, ValueError):
                expired = True
            if expired and self.delete_note(user_id, note["id"]):
                removed += 1
        return removed

    def delete_user(self, user_id: str) -> bool:
        target = self._user_root(user_id)
        if not target.exists():
            return False
        resolved = target.resolve()
        users_root = self._safe_path("users")
        try:
            resolved.relative_to(users_root)
        except ValueError as exc:
            raise ContractError("memory user path is outside the vault") from exc
        if resolved == users_root:
            raise ContractError("refusing to delete the memory users root")
        with self._user_lock(user_id):
            shutil.rmtree(resolved)
        return True


def build_memory_notes(
    *,
    user_id: str,
    reference_id: str,
    understanding: dict[str, Any] | None,
    frictions: list[str],
    now: datetime,
    reference_type: str = "conversation",
    retention_days: int = 90,
    evidence_ids: list[str] | None = None,
    feedback_summary: str | None = None,
) -> list[dict[str, Any]]:
    """Convert structured understanding into short, non-transcript notes."""

    if understanding is None:
        return []
    origin = "explicit" if understanding.get("explicitness") == "explicit" else "inferred"
    confidence = float(understanding.get("confidence", 0.5))
    retention_until = (now + timedelta(days=max(1, min(365, retention_days)))).isoformat()
    common = {
        "schemaVersion": SCHEMA_VERSION,
        "userId": require_uuid(user_id, "memory.userId"),
        "origin": origin,
        "referenceType": reference_type,
        "referenceId": reference_id[:200],
        "evidenceIds": list(dict.fromkeys(evidence_ids or []))[:20],
        "confidence": confidence,
        "observedAt": now.isoformat(),
        "lastConfirmedAt": now.isoformat(),
        "retentionUntil": retention_until,
    }
    notes: list[dict[str, Any]] = []
    attractions = [str(value) for value in understanding.get("attractions", []) if str(value).strip()]
    categories = [str(value) for value in understanding.get("categoryHints", []) if str(value).strip()]
    if attractions or categories:
        labels = list(dict.fromkeys([*attractions, *categories]))[:12]
        notes.append(
            {
                **common,
                "id": str(uuid.uuid4()),
                "kind": "preference",
                "summary": f"関心として話したこと: {'、'.join(labels)}",
                "keywords": labels,
            }
        )
    clean_frictions = list(dict.fromkeys(frictions))[:12]
    if clean_frictions:
        notes.append(
            {
                **common,
                "id": str(uuid.uuid4()),
                "kind": "friction" if reference_type == "conversation" else "feedback",
                "summary": f"参加するときにひっかかる点: {'、'.join(clean_frictions)}",
                "keywords": clean_frictions,
            }
        )
    if reference_type == "feedback" and feedback_summary:
        clean_feedback = _clean_text(feedback_summary, 280)
        notes.append(
            {
                **common,
                "id": str(uuid.uuid4()),
                "kind": "feedback",
                "summary": clean_feedback,
                "keywords": ["check_in"],
            }
        )
    for note in notes:
        validate_schema(note, "memory-note.schema.json")
    return notes


def build_episode_memory_note(
    *,
    user_id: str,
    reference_id: str,
    opportunity_id: str,
    now: datetime,
    retention_days: int = 90,
) -> dict[str, Any]:
    note = {
        "schemaVersion": SCHEMA_VERSION,
        "id": str(uuid.uuid4()),
        "kind": "episode",
        "userId": require_uuid(user_id, "memory.userId"),
        "origin": "explicit",
        "referenceType": "conversation",
        "referenceId": reference_id[:200],
        "evidenceIds": [],
        "summary": "提示されたイベント候補を『行ってみる』と選んだ",
        "keywords": [opportunity_id[:80]],
        "confidence": 1.0,
        "observedAt": now.isoformat(),
        "lastConfirmedAt": now.isoformat(),
        "retentionUntil": (
            now + timedelta(days=max(1, min(365, retention_days)))
        ).isoformat(),
    }
    validate_schema(note, "memory-note.schema.json")
    return note
