"""Crash-safe JSON persistence with per-user, cross-process locking."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import secrets
import shutil
import tempfile
import time
from bisect import bisect_right
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator

from osekkai_contracts import ContractError, require_uuid


class StorageError(RuntimeError):
    """Storage, corruption, or lock failure safe to map at the CLI boundary."""


class LockTimeout(StorageError):
    pass


class IdempotencyConflict(StorageError):
    """The same command/key was reused for a different logical request."""


def _default_root() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "osekkai"


class JsonStore:
    IDEMPOTENCY_RETENTION_HOURS = 24
    MAX_JSON_BYTES = 2 * 1024 * 1024
    MAX_CONVERSATIONS_PER_USER = 2_000
    MAX_EPISODES_PER_USER = 2_000
    MAX_CONVERSATION_BYTES_PER_USER = 8 * 1024 * 1024
    MAX_EPISODE_BYTES_PER_USER = 16 * 1024 * 1024
    MAX_IDEMPOTENCY_ENTRIES_PER_USER = 2_000
    MAINTENANCE_INTERVAL_HOURS = 24
    MAINTENANCE_BATCH_SIZE = 10
    MAINTENANCE_USER_LOCK_TIMEOUT_SECONDS = 0.05
    SUBDIRECTORIES = (
        "profiles",
        "conversations",
        "conversation-episodes",
        "interventions",
        "opportunities",
        "credentials",
        "assessments",
        "outcomes",
        "third-places",
        "roles",
        "metrics",
        "idempotency",
        ".locks",
    )

    def __init__(self, root: Path | str | None = None, lock_timeout: float = 10.0):
        configured = root or os.environ.get("OSEKKAI_DATA_ROOT") or _default_root()
        self.root = Path(configured).expanduser().resolve()
        self.lock_timeout = lock_timeout
        self.root.mkdir(parents=True, exist_ok=True)
        for name in self.SUBDIRECTORIES:
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def _safe_path(self, *parts: str) -> Path:
        target = self.root.joinpath(*parts).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise StorageError("resolved storage path escapes OSEKKAI_DATA_ROOT") from exc
        return target

    @contextmanager
    def _file_lock(self, lock_name: str, timeout: float) -> Iterator[None]:
        lock_path = self._safe_path(".locks", f"{lock_name}.lock")
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
                        raise LockTimeout("timed out acquiring user data lock")
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

    @contextmanager
    def user_lock(self, user_id: str, timeout: float | None = None) -> Iterator[None]:
        require_uuid(user_id, "userId")
        lock_name = "user-" + hmac.new(
            self._idempotency_hmac_key(),
            user_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        with self._file_lock(lock_name, self.lock_timeout if timeout is None else timeout):
            # Releases upgraded stores from the pre-HMAC lock naming scheme.
            # A legacy lock is never the active lock in this process.  If an
            # older process still has it open, Windows refuses the unlink and
            # we leave it for a later request rather than failing user work.
            legacy_lock = self._safe_path(".locks", f"{user_id}.lock")
            try:
                legacy_lock.unlink(missing_ok=True)
            except OSError:
                pass
            yield

    @contextmanager
    def maintenance_lock(self) -> Iterator[None]:
        # Maintenance is opportunistic. A request must never queue behind a
        # sweep already being performed by another process.
        with self._file_lock("retention-maintenance", 0.0):
            yield

    @staticmethod
    def _read_json(path: Path, default: Any = None) -> Any:
        if not path.exists():
            return copy.deepcopy(default)
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError("stored JSON could not be read") from exc

    def _atomic_write_json(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if len(encoded) > self.MAX_JSON_BYTES:
            raise StorageError("stored JSON exceeds the per-file quota")
        fd = -1
        temp_name = ""
        try:
            fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
            with os.fdopen(fd, "wb") as handle:
                fd = -1
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
            temp_name = ""
        except OSError as exc:
            raise StorageError("stored JSON could not be written atomically") from exc
        finally:
            if fd >= 0:
                os.close(fd)
            if temp_name:
                try:
                    Path(temp_name).unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _json_size(value: Any) -> int:
        return len(
            (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        )

    def _enforce_directory_byte_quota(self, path: Path, value: Any, limit: int, label: str) -> None:
        directory = path.parent
        current_size = path.stat().st_size if path.exists() else 0
        existing_size = (
            sum(item.stat().st_size for item in directory.glob("*.json") if item.is_file())
            if directory.exists()
            else 0
        )
        if existing_size - current_size + self._json_size(value) > limit:
            raise StorageError(f"{label} byte quota exceeded")

    def profile_path(self, user_id: str) -> Path:
        require_uuid(user_id, "userId")
        return self._safe_path("profiles", f"{user_id}.json")

    def load_profile_unlocked(self, user_id: str) -> dict[str, Any] | None:
        return self._read_json(self.profile_path(user_id))

    def save_profile_unlocked(self, user_id: str, profile: dict[str, Any]) -> None:
        if profile.get("userId") != user_id:
            raise StorageError("profile ownership mismatch")
        self._atomic_write_json(self.profile_path(user_id), profile)

    def load_profile(self, user_id: str) -> dict[str, Any] | None:
        with self.user_lock(user_id):
            return self.load_profile_unlocked(user_id)

    def _idempotency_hmac_key(self) -> bytes:
        path = self._safe_path("credentials", "idempotency-hmac-key.bin")
        try:
            fd = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                0o600,
            )
        except FileExistsError:
            fd = -1
        except OSError as exc:
            raise StorageError("idempotency fingerprint key is unavailable") from exc
        if fd >= 0:
            key = secrets.token_bytes(32)
            try:
                os.write(fd, key)
                os.fsync(fd)
            except OSError as exc:
                raise StorageError("idempotency fingerprint key could not be created") from exc
            finally:
                os.close(fd)
            return key

        # A competing first request may still be finishing the exclusive
        # create. Brief bounded retries avoid ever accepting a partial key.
        for _ in range(20):
            try:
                key = path.read_bytes()
            except OSError as exc:
                raise StorageError("idempotency fingerprint key could not be read") from exc
            if len(key) == 32:
                return key
            time.sleep(0.005)
        raise StorageError("idempotency fingerprint key is invalid")

    def idempotency_fingerprint(
        self,
        user_id: str,
        command: str,
        payload: dict[str, Any],
    ) -> str:
        require_uuid(user_id, "userId")
        canonical = json.dumps(
            {
                "schemaVersion": "1.0",
                "userId": user_id,
                "command": command,
                "payload": payload,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hmac.new(self._idempotency_hmac_key(), canonical, hashlib.sha256).hexdigest()

    def save_conversation_unlocked(self, user_id: str, conversation: dict[str, Any]) -> None:
        conversation_id = require_uuid(conversation.get("id"), "conversation.id")
        if conversation.get("userId") != user_id:
            raise StorageError("conversation ownership mismatch")
        path = self._safe_path("conversations", user_id, f"{conversation_id}.json")
        if not path.exists():
            existing = self._safe_path("conversations", user_id)
            if existing.exists() and sum(1 for _ in existing.glob("*.json")) >= self.MAX_CONVERSATIONS_PER_USER:
                raise StorageError("conversation quota exceeded")
        self._enforce_directory_byte_quota(
            path,
            conversation,
            self.MAX_CONVERSATION_BYTES_PER_USER,
            "conversation",
        )
        self._atomic_write_json(path, conversation)

    def list_conversations_unlocked(self, user_id: str) -> list[dict[str, Any]]:
        require_uuid(user_id, "userId")
        directory = self._safe_path("conversations", user_id)
        if not directory.exists():
            return []
        values = [self._read_json(path) for path in directory.glob("*.json")]
        return sorted(values, key=lambda item: item.get("createdAt", ""))

    def save_conversation_episode_unlocked(self, user_id: str, episode: dict[str, Any]) -> None:
        episode_id = require_uuid(episode.get("id"), "conversationEpisode.id")
        if episode.get("userId") != user_id:
            raise StorageError("conversation episode ownership mismatch")
        path = self._safe_path("conversation-episodes", user_id, f"{episode_id}.json")
        if not path.exists():
            existing = self._safe_path("conversation-episodes", user_id)
            if existing.exists() and sum(1 for _ in existing.glob("*.json")) >= self.MAX_EPISODES_PER_USER:
                raise StorageError("conversation episode quota exceeded")
        self._enforce_directory_byte_quota(
            path,
            episode,
            self.MAX_EPISODE_BYTES_PER_USER,
            "conversation episode",
        )
        self._atomic_write_json(path, episode)

    def load_conversation_episode_unlocked(
        self, user_id: str, episode_id: str
    ) -> dict[str, Any] | None:
        require_uuid(user_id, "userId")
        require_uuid(episode_id, "conversationEpisodeId")
        return self._read_json(
            self._safe_path("conversation-episodes", user_id, f"{episode_id}.json")
        )

    def list_conversation_episodes_unlocked(self, user_id: str) -> list[dict[str, Any]]:
        require_uuid(user_id, "userId")
        directory = self._safe_path("conversation-episodes", user_id)
        if not directory.exists():
            return []
        values = [self._read_json(path) for path in directory.glob("*.json")]
        return sorted(
            values,
            key=lambda item: (str(item.get("updatedAt", "")), str(item.get("id", ""))),
            reverse=True,
        )

    def save_episode_unlocked(self, user_id: str, episode: dict[str, Any]) -> None:
        episode_id = require_uuid(episode.get("id"), "episode.id")
        if episode.get("userId") != user_id:
            raise StorageError("episode ownership mismatch")
        path = self._safe_path("interventions", user_id, f"{episode_id}.json")
        if not path.exists():
            existing = self._safe_path("interventions", user_id)
            if existing.exists() and sum(1 for _ in existing.glob("*.json")) >= self.MAX_EPISODES_PER_USER:
                raise StorageError("intervention quota exceeded")
        self._enforce_directory_byte_quota(
            path,
            episode,
            self.MAX_EPISODE_BYTES_PER_USER,
            "intervention",
        )
        self._atomic_write_json(path, episode)

    def load_episode_unlocked(self, user_id: str, episode_id: str) -> dict[str, Any] | None:
        require_uuid(user_id, "userId")
        require_uuid(episode_id, "episodeId")
        return self._read_json(self._safe_path("interventions", user_id, f"{episode_id}.json"))

    def list_episodes_unlocked(self, user_id: str) -> list[dict[str, Any]]:
        require_uuid(user_id, "userId")
        directory = self._safe_path("interventions", user_id)
        if not directory.exists():
            return []
        values = [self._read_json(path) for path in directory.glob("*.json")]

        def episode_order(item: dict[str, Any]) -> tuple[int, int, str, str]:
            sequence = item.get("sequence")
            if isinstance(sequence, int) and not isinstance(sequence, bool) and sequence >= 1:
                return (1, sequence, str(item.get("createdAt", "")), str(item.get("id", "")))
            # Records created before sequence was introduced remain readable and
            # deterministic. New sequenced records always sort ahead of them.
            created_at = item.get("createdAt") or item.get("decidedAt") or ""
            return (0, 0, str(created_at), str(item.get("id", "")))

        return sorted(values, key=episode_order, reverse=True)

    def list_episodes(self, user_id: str) -> list[dict[str, Any]]:
        with self.user_lock(user_id):
            return self.list_episodes_unlocked(user_id)

    def execute_idempotent(
        self,
        user_id: str,
        command: str,
        key: str,
        now: datetime,
        operation: Callable[[], Any],
        *,
        request_fingerprint: str | None = None,
        compact_result: Callable[[Any], Any] | None = None,
        replay_operation: Callable[[Any], Any] | None = None,
    ) -> tuple[Any, bool]:
        with self.user_lock(user_id):
            path = self._safe_path("idempotency", f"{user_id}.json")
            ledger = self._read_json(path, {"entries": {}})
            entries = ledger.get("entries")
            if not isinstance(entries, dict):
                entries = {}
                ledger = {"entries": entries}
            cutoff = now - timedelta(hours=self.IDEMPOTENCY_RETENTION_HOURS)
            pruned = False
            for entry_key, entry in list(entries.items()):
                created_at = entry.get("createdAt") if isinstance(entry, dict) else None
                try:
                    expired = not created_at or datetime.fromisoformat(created_at) < cutoff
                except (TypeError, ValueError):
                    expired = True
                if expired:
                    del entries[entry_key]
                    pruned = True
            if pruned:
                self._atomic_write_json(path, ledger)
            composite = f"{command}:{key}"
            existing = entries.get(composite)
            if existing is not None:
                if not isinstance(existing, dict):
                    raise StorageError("idempotency entry is invalid")
                if request_fingerprint is not None and existing.get("requestFingerprint") != request_fingerprint:
                    raise IdempotencyConflict("idempotency key was reused with a different payload")
                if "result" in existing:
                    return copy.deepcopy(existing["result"]), True
                if "replay" in existing and replay_operation is not None:
                    return replay_operation(copy.deepcopy(existing["replay"])), True
                raise StorageError("idempotency replay metadata is incomplete")
            if len(entries) >= self.MAX_IDEMPOTENCY_ENTRIES_PER_USER:
                raise StorageError("idempotency quota exceeded")
            result = operation()
            # The operation may delete or privacy-scrub the ledger. Reload it
            # so an in-memory pre-operation copy can never resurrect data.
            ledger = self._read_json(path, {"entries": {}})
            entries = ledger.get("entries")
            if not isinstance(entries, dict):
                ledger = {"entries": {}}
                entries = ledger["entries"]
            entry = {
                "createdAt": now.isoformat(),
            }
            if request_fingerprint is not None:
                entry["requestFingerprint"] = request_fingerprint
            if compact_result is None:
                entry["result"] = copy.deepcopy(result)
            else:
                entry["replay"] = copy.deepcopy(compact_result(result))
            entries[composite] = entry
            self._atomic_write_json(path, ledger)
            return result, False

    def delete_user_unlocked(self, user_id: str) -> dict[str, int]:
        require_uuid(user_id, "userId")
        deleted: dict[str, int] = {}
        file_areas = ("profiles", "idempotency", "credentials", "metrics")
        dir_areas = (
            "conversations",
            "conversation-episodes",
            "interventions",
            "opportunities",
            "assessments",
            "outcomes",
            "third-places",
            "roles",
        )
        for area in file_areas:
            path = self._safe_path(area, f"{user_id}.json")
            deleted[area] = int(path.exists())
            path.unlink(missing_ok=True)
        for area in dir_areas:
            path = self._safe_path(area, user_id)
            count = len(list(path.rglob("*"))) if path.exists() else 0
            if path.exists():
                shutil.rmtree(path)
            deleted[area] = count
        marker_path = self._safe_path("retention-maintenance.json")
        marker = self._read_json(marker_path, {})
        if isinstance(marker, dict) and marker.get("cursor") == user_id:
            marker["cursor"] = None
            marker["lastCompletedAt"] = None
            self._atomic_write_json(marker_path, marker)
        return deleted

    @staticmethod
    def _reconcile_scrubbed_inference_copy(value: dict[str, Any], changed_keys: set[str]) -> None:
        inferred = value.get("inferredPreferences")
        inferred = inferred if isinstance(inferred, dict) else {}
        if "socialBattery" in changed_keys and "socialBattery" in value:
            entry = inferred.get("socialBattery")
            candidate = entry.get("value") if isinstance(entry, dict) else None
            value["socialBattery"] = (
                candidate
                if isinstance(candidate, int)
                and not isinstance(candidate, bool)
                and 0 <= candidate <= 100
                else None
            )
        if "maxSocialIntensity" in changed_keys and "maxSocialIntensity" in value:
            explicit = value.get("explicitPreferences")
            stored = explicit.get("maxSocialIntensity") if isinstance(explicit, dict) else None
            baseline = stored.get("value") if isinstance(stored, dict) else stored
            if not isinstance(baseline, int) or isinstance(baseline, bool) or not 0 <= baseline <= 5:
                baseline = 2
            entry = inferred.get("maxSocialIntensity")
            candidate = entry.get("value") if isinstance(entry, dict) else None
            value["maxSocialIntensity"] = (
                min(baseline, candidate)
                if isinstance(candidate, int)
                and not isinstance(candidate, bool)
                and 0 <= candidate <= 5
                else baseline
            )

    @staticmethod
    def _scrub_expired_inferred_evidence(
        value: Any,
        cutoff: datetime,
    ) -> tuple[Any, int]:
        """Remove expired inferred evidence from any embedded profile copy."""

        removed = 0
        if isinstance(value, list):
            for item in value:
                _, child_removed = JsonStore._scrub_expired_inferred_evidence(item, cutoff)
                removed += child_removed
            return value, removed
        if not isinstance(value, dict):
            return value, removed

        inferred = value.get("inferredPreferences")
        if isinstance(inferred, dict):
            changed_keys: set[str] = set()
            for preference_key, preference in list(inferred.items()):
                if not isinstance(preference, dict):
                    del inferred[preference_key]
                    changed_keys.add(preference_key)
                    continue
                evidence = preference.get("evidence")
                if not isinstance(evidence, list):
                    del inferred[preference_key]
                    changed_keys.add(preference_key)
                    continue
                kept = []
                for item in evidence:
                    created_at = item.get("createdAt") if isinstance(item, dict) else None
                    try:
                        expired = not isinstance(created_at, str) or datetime.fromisoformat(created_at) < cutoff
                    except (TypeError, ValueError):
                        expired = True
                    if expired:
                        removed += 1
                        changed_keys.add(preference_key)
                    else:
                        kept.append(item)
                preference["evidence"] = kept
                if not kept:
                    del inferred[preference_key]
            JsonStore._reconcile_scrubbed_inference_copy(value, changed_keys)

        friction = value.get("participationFriction")
        if isinstance(friction, dict):
            for friction_key, item in list(friction.items()):
                if not isinstance(item, dict) or item.get("origin") != "inferred":
                    continue
                evidence = item.get("evidence")
                if not isinstance(evidence, list):
                    del friction[friction_key]
                    continue
                kept = []
                for evidence_item in evidence:
                    observed_at = (
                        evidence_item.get("lastConfirmedAt")
                        if isinstance(evidence_item, dict)
                        else None
                    )
                    try:
                        expired = (
                            not isinstance(observed_at, str)
                            or datetime.fromisoformat(observed_at) < cutoff
                        )
                    except (TypeError, ValueError):
                        expired = True
                    if expired:
                        removed += 1
                    else:
                        kept.append(evidence_item)
                item["evidence"] = kept
                if not kept:
                    del friction[friction_key]

        for child in value.values():
            _, child_removed = JsonStore._scrub_expired_inferred_evidence(child, cutoff)
            removed += child_removed
        return value, removed

    @staticmethod
    def _scrub_inferred_copy(
        value: Any,
        *,
        evidence_id: str | None = None,
        preference_key: str | None = None,
    ) -> int:
        removed = 0
        if isinstance(value, list):
            return sum(
                JsonStore._scrub_inferred_copy(
                    item,
                    evidence_id=evidence_id,
                    preference_key=preference_key,
                )
                for item in value
            )
        if not isinstance(value, dict):
            return 0
        inferred = value.get("inferredPreferences")
        if isinstance(inferred, dict):
            changed_keys: set[str] = set()
            if preference_key is not None and preference_key in inferred:
                del inferred[preference_key]
                removed += 1
                changed_keys.add(preference_key)
            if evidence_id is not None:
                for key, preference in list(inferred.items()):
                    if not isinstance(preference, dict) or not isinstance(preference.get("evidence"), list):
                        continue
                    evidence = preference["evidence"]
                    kept = [
                        item
                        for item in evidence
                        if not isinstance(item, dict) or item.get("id") != evidence_id
                    ]
                    removed += len(evidence) - len(kept)
                    if len(evidence) != len(kept):
                        changed_keys.add(key)
                    preference["evidence"] = kept
                    if not kept:
                        del inferred[key]
            JsonStore._reconcile_scrubbed_inference_copy(value, changed_keys)
        friction = value.get("participationFriction")
        if isinstance(friction, dict):
            friction_name = (
                preference_key.removeprefix("friction:")
                if isinstance(preference_key, str) and preference_key.startswith("friction:")
                else None
            )
            if friction_name is not None and friction_name in friction:
                del friction[friction_name]
                removed += 1
            if evidence_id is not None:
                for key, item in list(friction.items()):
                    if not isinstance(item, dict) or not isinstance(item.get("evidence"), list):
                        continue
                    evidence = item["evidence"]
                    kept = [
                        entry
                        for entry in evidence
                        if not isinstance(entry, dict) or entry.get("id") != evidence_id
                    ]
                    removed += len(evidence) - len(kept)
                    item["evidence"] = kept
                    if not kept:
                        del friction[key]
        for child in value.values():
            removed += JsonStore._scrub_inferred_copy(
                child,
                evidence_id=evidence_id,
                preference_key=preference_key,
            )
        return removed

    def scrub_inferred_copies_unlocked(
        self,
        user_id: str,
        *,
        evidence_id: str | None = None,
        preference_key: str | None = None,
    ) -> dict[str, int]:
        """Propagate an explicit deletion to Episode and replay copies."""

        require_uuid(user_id, "userId")
        if (evidence_id is None) == (preference_key is None):
            raise StorageError("provide exactly one inferred-data deletion selector")
        updated_episodes = 0
        removed = 0
        conversation_episode_directory = self._safe_path("conversation-episodes", user_id)
        if evidence_id is not None and conversation_episode_directory.exists():
            for path in conversation_episode_directory.glob("*.json"):
                episode = self._read_json(path)
                evidence_ids = episode.get("frictionEvidenceIds")
                if not isinstance(evidence_ids, list) or evidence_id not in evidence_ids:
                    continue
                episode["frictionEvidenceIds"] = [
                    item for item in evidence_ids if item != evidence_id
                ]
                self._atomic_write_json(path, episode)
                removed += 1
                updated_episodes += 1
        episode_directory = self._safe_path("interventions", user_id)
        if episode_directory.exists():
            for path in episode_directory.glob("*.json"):
                episode = self._read_json(path)
                item_removed = self._scrub_inferred_copy(
                    episode,
                    evidence_id=evidence_id,
                    preference_key=preference_key,
                )
                if item_removed:
                    removed += item_removed
                    updated_episodes += 1
                    self._atomic_write_json(path, episode)
        ledger_path = self._safe_path("idempotency", f"{user_id}.json")
        ledger = self._read_json(ledger_path)
        ledger_removed = 0
        if isinstance(ledger, dict):
            ledger_removed = self._scrub_inferred_copy(
                ledger,
                evidence_id=evidence_id,
                preference_key=preference_key,
            )
            if ledger_removed:
                self._atomic_write_json(ledger_path, ledger)
                removed += ledger_removed
        return {
            "removed": removed,
            "episodesUpdated": updated_episodes,
            "ledgerRemoved": ledger_removed,
        }

    def list_user_ids(self) -> list[str]:
        """Discover persisted user namespaces without trusting path names."""

        candidates: set[str] = set()
        for area in ("profiles", "idempotency"):
            directory = self._safe_path(area)
            candidates.update(path.stem for path in directory.glob("*.json"))
        for area in ("conversations", "conversation-episodes", "interventions"):
            directory = self._safe_path(area)
            candidates.update(path.name for path in directory.iterdir() if path.is_dir())

        valid: list[str] = []
        for candidate in candidates:
            try:
                require_uuid(candidate, "stored userId")
            except ContractError:
                # Unknown files are never opened or deleted by maintenance.
                continue
            valid.append(candidate)
        return sorted(valid)

    def cleanup_all_if_due(
        self,
        now: datetime,
        retention_days: int = 30,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """Periodically apply retention to inactive as well as current users.

        Per-user locks make concurrent maintenance safe. The cursor is written
        after each bounded batch, while ``lastCompletedAt`` is written only at
        the end of a cycle, so a crashed pass resumes on the next invocation.
        """

        marker_path = self._safe_path("retention-maintenance.json")
        try:
            lock = self.maintenance_lock()
            lock.__enter__()
        except LockTimeout:
            return {
                "ran": False,
                "busy": True,
                "cycleCompleted": False,
                "usersScanned": 0,
                "usersSkipped": 0,
                "skippedNamespaces": [],
                "removed": {},
            }

        try:
            try:
                marker = self._read_json(marker_path, {})
            except StorageError:
                # This marker contains no user data and is safe to rebuild.
                marker = {}
            if not isinstance(marker, dict) or marker.get("retentionDays") != retention_days:
                marker = {}
            last_completed_at = marker.get("lastCompletedAt")
            if isinstance(last_completed_at, str):
                try:
                    last_completed = datetime.fromisoformat(last_completed_at)
                except ValueError:
                    last_completed = None
                if not force and last_completed is not None and last_completed > now - timedelta(
                    hours=self.MAINTENANCE_INTERVAL_HOURS
                ):
                    return {
                        "ran": False,
                        "busy": False,
                        "cycleCompleted": True,
                        "usersScanned": 0,
                        "usersSkipped": 0,
                        "skippedNamespaces": [],
                        "removed": {},
                    }

            try:
                user_ids = self.list_user_ids()
            except OSError:
                user_ids = []
            cursor = marker.get("cursor") if isinstance(marker.get("cursor"), str) else None
            start = bisect_right(user_ids, cursor) if cursor else 0
            batch = user_ids[start : start + self.MAINTENANCE_BATCH_SIZE]
            cycle_completed = start + len(batch) >= len(user_ids)

            totals = {
                "conversations": 0,
                "evidence": 0,
                "episodesUpdated": 0,
                "idempotencyEntries": 0,
            }
            users_scanned = 0
            skipped_namespaces: list[dict[str, str]] = []
            for user_id in batch:
                try:
                    with self.user_lock(
                        user_id,
                        timeout=self.MAINTENANCE_USER_LOCK_TIMEOUT_SECONDS,
                    ):
                        removed = self.cleanup_unlocked(user_id, now, retention_days)
                except LockTimeout:
                    # One busy or corrupt namespace cannot make every API call
                    # fail. It is retried on the next daily cycle.
                    skipped_namespaces.append({"userId": user_id, "reason": "lock_busy"})
                    continue
                except StorageError:
                    skipped_namespaces.append({"userId": user_id, "reason": "corrupt_or_unreadable"})
                    continue
                except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
                    skipped_namespaces.append({"userId": user_id, "reason": "invalid_stored_data"})
                    continue
                except OSError:
                    skipped_namespaces.append({"userId": user_id, "reason": "invalid_or_unwritable"})
                    continue
                users_scanned += 1
                for key in totals:
                    totals[key] += removed[key]

            next_marker = {
                "retentionDays": retention_days,
                "lastBatchAt": now.isoformat(),
                "cursor": None if cycle_completed else batch[-1],
                "lastCompletedAt": now.isoformat() if cycle_completed else None,
            }
            self._atomic_write_json(marker_path, next_marker)
            return {
                "ran": True,
                "busy": False,
                "cycleCompleted": cycle_completed,
                "usersScanned": users_scanned,
                "usersSkipped": len(skipped_namespaces),
                "skippedNamespaces": skipped_namespaces,
                "removed": totals,
            }
        finally:
            lock.__exit__(None, None, None)

    def cleanup_unlocked(self, user_id: str, now: datetime, retention_days: int = 30) -> dict[str, int]:
        cutoff = now - timedelta(days=retention_days)
        removed_conversations = 0
        directory = self._safe_path("conversations", user_id)
        if directory.exists():
            for path in directory.glob("*.json"):
                value = self._read_json(path)
                timestamp = value.get("createdAt")
                try:
                    expired = not isinstance(timestamp, str) or datetime.fromisoformat(timestamp) < cutoff
                except (TypeError, ValueError):
                    expired = True
                if expired:
                    path.unlink(missing_ok=True)
                    removed_conversations += 1
        removed_evidence = 0
        profile = self.load_profile_unlocked(user_id)
        if profile:
            profile, profile_removed = self._scrub_expired_inferred_evidence(profile, cutoff)
            removed_evidence += profile_removed
            if profile_removed:
                profile["updatedAt"] = now.isoformat()
                self.save_profile_unlocked(user_id, profile)

        updated_episodes = 0
        episode_directory = self._safe_path("interventions", user_id)
        if episode_directory.exists():
            for path in episode_directory.glob("*.json"):
                episode = self._read_json(path)
                episode, episode_removed = self._scrub_expired_inferred_evidence(episode, cutoff)
                if episode_removed:
                    removed_evidence += episode_removed
                    updated_episodes += 1
                    self._atomic_write_json(path, episode)

        removed_idempotency = 0
        ledger_path = self._safe_path("idempotency", f"{user_id}.json")
        ledger = self._read_json(ledger_path)
        if isinstance(ledger, dict) and isinstance(ledger.get("entries"), dict):
            idempotency_cutoff = now - timedelta(hours=self.IDEMPOTENCY_RETENTION_HOURS)
            for entry_key, entry in list(ledger["entries"].items()):
                created_at = entry.get("createdAt") if isinstance(entry, dict) else None
                try:
                    expired = not created_at or datetime.fromisoformat(created_at) < idempotency_cutoff
                except (TypeError, ValueError):
                    expired = True
                if expired:
                    del ledger["entries"][entry_key]
                    removed_idempotency += 1
                    continue
                _, entry_removed = self._scrub_expired_inferred_evidence(entry, cutoff)
                removed_evidence += entry_removed
            if ledger["entries"]:
                self._atomic_write_json(ledger_path, ledger)
            else:
                ledger_path.unlink(missing_ok=True)

        return {
            "conversations": removed_conversations,
            "evidence": removed_evidence,
            "episodesUpdated": updated_episodes,
            "idempotencyEntries": removed_idempotency,
        }
