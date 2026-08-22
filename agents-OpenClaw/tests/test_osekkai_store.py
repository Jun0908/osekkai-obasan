from __future__ import annotations

import tempfile
import unittest
import json
from datetime import timedelta
from pathlib import Path

from helpers import NOW, OTHER_USER_ID, USER_ID
from osekkai_profile import seed_demo_profile
from osekkai_store import IdempotencyConflict, JsonStore, StorageError


class StoreTests(unittest.TestCase):
    def test_profile_episode_crud_and_atomic_temp_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            profile = seed_demo_profile(USER_ID, NOW)
            with store.user_lock(USER_ID):
                store.save_profile_unlocked(USER_ID, profile)
                self.assertEqual(store.load_profile_unlocked(USER_ID), profile)
            self.assertEqual(list(Path(directory).rglob("*.tmp")), [])

    def test_idempotent_mutation_runs_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            calls = []
            first, replayed = store.execute_idempotent(
                USER_ID, "profile-update", "idem-key-0001", NOW, lambda: calls.append(1) or {"n": 1}
            )
            second, replayed_second = store.execute_idempotent(
                USER_ID, "profile-update", "idem-key-0001", NOW, lambda: calls.append(2) or {"n": 2}
            )
            self.assertEqual(first, second)
            self.assertFalse(replayed)
            self.assertTrue(replayed_second)
            self.assertEqual(calls, [1])

    def test_idempotency_key_reuse_with_a_different_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            first_fingerprint = store.idempotency_fingerprint(
                USER_ID,
                "profile-update",
                {"patch": {"pushConsent": True}},
            )
            second_fingerprint = store.idempotency_fingerprint(
                USER_ID,
                "profile-update",
                {"patch": {"pushConsent": False}},
            )
            store.execute_idempotent(
                USER_ID,
                "profile-update",
                "fingerprint-key-0001",
                NOW,
                lambda: {"saved": True},
                request_fingerprint=first_fingerprint,
            )
            with self.assertRaises(IdempotencyConflict):
                store.execute_idempotent(
                    USER_ID,
                    "profile-update",
                    "fingerprint-key-0001",
                    NOW,
                    lambda: {"saved": False},
                    request_fingerprint=second_fingerprint,
                )

    def test_storage_quotas_bound_files_and_idempotency_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            store.MAX_IDEMPOTENCY_ENTRIES_PER_USER = 1
            store.execute_idempotent(
                USER_ID,
                "profile-update",
                "quota-entry-0001",
                NOW,
                lambda: {"saved": True},
            )
            with self.assertRaises(StorageError):
                store.execute_idempotent(
                    USER_ID,
                    "profile-update",
                    "quota-entry-0002",
                    NOW,
                    lambda: {"saved": True},
                )

            store.MAX_CONVERSATIONS_PER_USER = 1
            with store.user_lock(USER_ID):
                store.save_conversation_unlocked(
                    USER_ID,
                    {"id": "33333333-3333-4333-8333-333333333331", "userId": USER_ID},
                )
                with self.assertRaises(StorageError):
                    store.save_conversation_unlocked(
                        USER_ID,
                        {"id": "33333333-3333-4333-8333-333333333332", "userId": USER_ID},
                    )

            store.MAX_JSON_BYTES = 32
            with store.user_lock(USER_ID):
                with self.assertRaises(StorageError):
                    store.save_profile_unlocked(USER_ID, seed_demo_profile(USER_ID, NOW))

    def test_storage_quotas_bound_total_conversation_and_episode_bytes_per_user(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            store.MAX_CONVERSATION_BYTES_PER_USER = 500
            store.MAX_EPISODE_BYTES_PER_USER = 500
            with store.user_lock(USER_ID):
                store.save_conversation_unlocked(
                    USER_ID,
                    {
                        "id": "33333333-3333-4333-8333-333333333331",
                        "userId": USER_ID,
                        "text": "x" * 180,
                    },
                )
                with self.assertRaises(StorageError):
                    store.save_conversation_unlocked(
                        USER_ID,
                        {
                            "id": "33333333-3333-4333-8333-333333333332",
                            "userId": USER_ID,
                            "text": "y" * 180,
                        },
                    )

                store.save_episode_unlocked(
                    USER_ID,
                    {
                        "id": "44444444-4444-4444-8444-444444444441",
                        "userId": USER_ID,
                        "profileSnapshot": {"padding": "x" * 180},
                    },
                )
                with self.assertRaises(StorageError):
                    store.save_episode_unlocked(
                        USER_ID,
                        {
                            "id": "44444444-4444-4444-8444-444444444442",
                            "userId": USER_ID,
                            "profileSnapshot": {"padding": "y" * 180},
                        },
                    )

    def test_idempotency_ledger_is_bounded_and_reset_does_not_restore_old_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            store.execute_idempotent(
                USER_ID,
                "profile-update",
                "old-entry-0001",
                NOW - timedelta(hours=25),
                lambda: {"old": True},
            )
            store.execute_idempotent(
                USER_ID,
                "profile-update",
                "fresh-entry-0001",
                NOW,
                lambda: {"fresh": True},
            )
            ledger_path = store.root / "idempotency" / f"{USER_ID}.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            self.assertNotIn("profile-update:old-entry-0001", ledger["entries"])
            self.assertIn("profile-update:fresh-entry-0001", ledger["entries"])

            store.execute_idempotent(
                USER_ID,
                "demo-reset",
                "reset-entry-0001",
                NOW,
                lambda: store.delete_user_unlocked(USER_ID) or {"reset": True},
            )
            reset_ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            self.assertEqual(list(reset_ledger["entries"]), ["demo-reset:reset-entry-0001"])

    def test_episode_order_uses_sequence_with_created_at_fallback_for_legacy_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            records = [
                {
                    "id": "33333333-3333-4333-8333-333333333331",
                    "userId": USER_ID,
                    "createdAt": "2019-02-22T10:00:00+09:00",
                },
                {
                    "id": "33333333-3333-4333-8333-333333333332",
                    "userId": USER_ID,
                    "createdAt": "2019-02-23T10:00:00+09:00",
                },
                {
                    "id": "33333333-3333-4333-8333-333333333333",
                    "userId": USER_ID,
                    "sequence": 1,
                    "createdAt": "2019-02-23T10:00:00+09:00",
                },
            ]
            with store.user_lock(USER_ID):
                for record in records:
                    store.save_episode_unlocked(USER_ID, record)
                ordered = store.list_episodes_unlocked(USER_ID)
            self.assertEqual(
                [item["id"] for item in ordered],
                [records[2]["id"], records[1]["id"], records[0]["id"]],
            )

    def test_delete_user_does_not_touch_another_user(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            with store.user_lock(USER_ID):
                store.save_profile_unlocked(USER_ID, seed_demo_profile(USER_ID, NOW))
            with store.user_lock(OTHER_USER_ID):
                store.save_profile_unlocked(OTHER_USER_ID, seed_demo_profile(OTHER_USER_ID, NOW))
            with store.user_lock(USER_ID):
                store.delete_user_unlocked(USER_ID)
            self.assertIsNone(store.load_profile(USER_ID))
            self.assertIsNotNone(store.load_profile(OTHER_USER_ID))

    def test_lock_names_and_deleted_retention_cursor_do_not_retain_user_id(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            legacy_lock = store.root / ".locks" / f"{USER_ID}.lock"
            legacy_lock.write_bytes(b"0")
            with store.user_lock(USER_ID):
                store.save_profile_unlocked(USER_ID, seed_demo_profile(USER_ID, NOW))
            self.assertFalse(legacy_lock.exists())
            lock_names = [path.name for path in (store.root / ".locks").glob("*.lock")]
            self.assertTrue(lock_names)
            self.assertTrue(all(USER_ID not in name for name in lock_names))

            marker_path = store.root / "retention-maintenance.json"
            store._atomic_write_json(marker_path, {"cursor": USER_ID, "lastCompletedAt": NOW.isoformat()})
            with store.user_lock(USER_ID):
                store.delete_user_unlocked(USER_ID)

            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            self.assertIsNone(marker["cursor"])
            self.assertIsNone(marker["lastCompletedAt"])


if __name__ == "__main__":
    unittest.main()
