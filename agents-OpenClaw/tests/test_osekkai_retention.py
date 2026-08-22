from __future__ import annotations

import copy
import json
import tempfile
import unittest
import uuid
from datetime import timedelta

from helpers import NOW, USER_ID
from osekkai_cli import _profile_update_unlocked
from osekkai_profile import seed_demo_profile
from osekkai_store import JsonStore


class RetentionTests(unittest.TestCase):
    def test_scheduled_cleanup_includes_an_inactive_user_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            inactive_user = "22222222-2222-4222-8222-222222222222"
            old = NOW - timedelta(days=31)
            profile = seed_demo_profile(inactive_user, NOW)
            profile["socialBattery"] = 20
            profile["inferredPreferences"] = {
                "socialBattery": {
                    "value": 20,
                    "confidence": 0.8,
                    "evidence": [
                        {"id": "inactive-old", "text": "old", "createdAt": old.isoformat()}
                    ],
                }
            }
            with store.user_lock(inactive_user):
                store.save_profile_unlocked(inactive_user, profile)
                store.save_conversation_unlocked(
                    inactive_user,
                    {
                        "id": str(uuid.uuid4()),
                        "userId": inactive_user,
                        "createdAt": old.isoformat(),
                    },
                )

            result = store.cleanup_all_if_due(NOW, 30)
            with store.user_lock(inactive_user):
                cleaned = store.load_profile_unlocked(inactive_user)
                conversations = store.list_conversations_unlocked(inactive_user)

            self.assertTrue(result["ran"])
            self.assertEqual(result["usersScanned"], 1)
            self.assertEqual(result["removed"]["conversations"], 1)
            self.assertEqual(result["removed"]["evidence"], 1)
            self.assertEqual(conversations, [])
            self.assertEqual(cleaned["inferredPreferences"], {})
            self.assertFalse(store.cleanup_all_if_due(NOW + timedelta(hours=1), 30)["ran"])

    def test_scheduled_cleanup_is_bounded_and_isolates_a_corrupt_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            corrupt_user = "00000000-0000-4000-8000-000000000001"
            (store.root / "profiles" / f"{corrupt_user}.json").write_text(
                "{not-json",
                encoding="utf-8",
            )
            valid_users = [
                f"00000000-0000-4000-8000-{index:012d}"
                for index in range(2, store.MAINTENANCE_BATCH_SIZE + 3)
            ]
            for user_id in valid_users:
                with store.user_lock(user_id):
                    store.save_profile_unlocked(user_id, seed_demo_profile(user_id, NOW))

            first = store.cleanup_all_if_due(NOW, 30)
            second = store.cleanup_all_if_due(NOW, 30)

            self.assertTrue(first["ran"])
            self.assertFalse(first["cycleCompleted"])
            self.assertEqual(first["usersSkipped"], 1)
            self.assertLessEqual(
                first["usersScanned"] + first["usersSkipped"],
                store.MAINTENANCE_BATCH_SIZE,
            )
            self.assertTrue(second["ran"])
            self.assertTrue(second["cycleCompleted"])
            self.assertEqual(second["usersScanned"], 2)

    def test_invalid_retention_timestamps_are_removed_without_aborting(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            profile = seed_demo_profile(USER_ID, NOW)
            profile["inferredPreferences"] = {
                "tone": {
                    "value": "quiet",
                    "confidence": 0.8,
                    "evidence": [{"id": "invalid-time", "text": "invalid", "createdAt": 123}],
                }
            }
            with store.user_lock(USER_ID):
                store.save_profile_unlocked(USER_ID, profile)
                store.save_conversation_unlocked(
                    USER_ID,
                    {
                        "id": str(uuid.uuid4()),
                        "userId": USER_ID,
                        "createdAt": {"invalid": True},
                    },
                )
                removed = store.cleanup_unlocked(USER_ID, NOW, 30)
            self.assertEqual(removed["conversations"], 1)
            self.assertEqual(removed["evidence"], 1)

    def test_cleanup_removes_only_expired_conversation_and_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            old = NOW - timedelta(days=31)
            fresh = NOW - timedelta(days=2)
            profile = seed_demo_profile(USER_ID, NOW)
            profile["inferredPreferences"] = {
                "tone": {
                    "value": "quiet",
                    "confidence": 0.8,
                    "evidence": [
                        {"id": "old", "text": "old", "createdAt": old.isoformat()},
                        {"id": "new", "text": "new", "createdAt": fresh.isoformat()},
                    ],
                }
            }
            with store.user_lock(USER_ID):
                store.save_profile_unlocked(USER_ID, profile)
                for timestamp in (old, fresh):
                    conversation = {
                        "id": str(uuid.uuid4()),
                        "userId": USER_ID,
                        "createdAt": timestamp.isoformat(),
                    }
                    store.save_conversation_unlocked(USER_ID, conversation)
                store.save_episode_unlocked(
                    USER_ID,
                    {
                        "id": str(uuid.uuid4()),
                        "userId": USER_ID,
                        "profileSnapshot": copy.deepcopy(profile),
                        "createdAt": fresh.isoformat(),
                    },
                )
            store.execute_idempotent(
                USER_ID,
                "profile-update",
                "retention-ledger-0001",
                NOW,
                lambda: {"profile": copy.deepcopy(profile)},
            )
            with store.user_lock(USER_ID):
                removed = store.cleanup_unlocked(USER_ID, NOW, 30)
                conversations = store.list_conversations_unlocked(USER_ID)
                episodes = store.list_episodes_unlocked(USER_ID)
                cleaned = store.load_profile_unlocked(USER_ID)
            ledger = json.loads(
                (store.root / "idempotency" / f"{USER_ID}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                removed,
                {
                    "conversations": 1,
                    "evidence": 3,
                    "episodesUpdated": 1,
                    "idempotencyEntries": 0,
                },
            )
            self.assertEqual(len(conversations), 1)
            self.assertEqual(cleaned["inferredPreferences"]["tone"]["evidence"][0]["id"], "new")
            episode_evidence = episodes[0]["profileSnapshot"]["inferredPreferences"]["tone"]["evidence"]
            ledger_result = next(iter(ledger["entries"].values()))["result"]
            ledger_evidence = ledger_result["profile"]["inferredPreferences"]["tone"]["evidence"]
            self.assertEqual([item["id"] for item in episode_evidence], ["new"])
            self.assertEqual([item["id"] for item in ledger_evidence], ["new"])

    def test_explicit_evidence_delete_propagates_to_episode_and_replay_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            evidence_id = "99999999-9999-4999-8999-999999999999"
            profile = seed_demo_profile(USER_ID, NOW)
            profile["socialBattery"] = 20
            profile["inferredPreferences"] = {
                "socialBattery": {
                    "value": 20,
                    "confidence": 1.0,
                    "evidence": [
                        {"id": evidence_id, "text": "delete me", "createdAt": NOW.isoformat()}
                    ],
                }
            }
            with store.user_lock(USER_ID):
                store.save_profile_unlocked(USER_ID, profile)
                store.save_episode_unlocked(
                    USER_ID,
                    {
                        "id": str(uuid.uuid4()),
                        "userId": USER_ID,
                        "profileSnapshot": copy.deepcopy(profile),
                        "createdAt": NOW.isoformat(),
                    },
                )
            store.execute_idempotent(
                USER_ID,
                "chat",
                "stored-copy-0001",
                NOW,
                lambda: {"profile": copy.deepcopy(profile)},
            )
            store.execute_idempotent(
                USER_ID,
                "profile-update",
                "remove-copy-0001",
                NOW,
                lambda: _profile_update_unlocked(
                    store,
                    USER_ID,
                    {"removeEvidenceId": evidence_id},
                    NOW,
                ),
            )
            serialized = "\n".join(
                path.read_text(encoding="utf-8")
                for path in store.root.rglob("*.json")
            )
            self.assertNotIn(evidence_id, serialized)
            with store.user_lock(USER_ID):
                cleaned_profile = store.load_profile_unlocked(USER_ID)
                cleaned_episode = store.list_episodes_unlocked(USER_ID)[0]
            ledger = json.loads(
                (store.root / "idempotency" / f"{USER_ID}.json").read_text(encoding="utf-8")
            )
            stored_copy = next(
                item["result"]["profile"]
                for item in ledger["entries"].values()
                if isinstance(item.get("result"), dict)
                and isinstance(item["result"].get("profile"), dict)
                and item["result"]["profile"].get("inferredPreferences") == {}
            )
            self.assertIsNone(cleaned_profile["socialBattery"])
            self.assertIsNone(cleaned_episode["profileSnapshot"]["socialBattery"])
            self.assertIsNone(stored_copy["socialBattery"])


if __name__ == "__main__":
    unittest.main()
