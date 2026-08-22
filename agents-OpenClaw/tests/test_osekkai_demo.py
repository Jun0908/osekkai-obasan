from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch

from helpers import AGENT_ROOT, NOW, USER_ID
from osekkai_cli import _demo_seed_unlocked, _is_untouched_default_profile
from osekkai_chat import process_chat_unlocked
from osekkai_metrics import calculate_metrics
from osekkai_profile import default_profile, seed_demo_profile
from osekkai_run import decide_unlocked, feedback_unlocked, record_outcome_unlocked
from osekkai_store import JsonStore


class DemoTests(unittest.TestCase):
    def test_atomic_demo_seed_initializes_only_a_fresh_user(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            result, replayed = store.execute_idempotent(
                USER_ID,
                "demo-seed",
                "demo-seed-fresh-0001",
                NOW,
                lambda: _demo_seed_unlocked(store, USER_ID, NOW),
            )

            self.assertFalse(replayed)
            self.assertTrue(result["seeded"])
            self.assertTrue(result["profile"]["memoryConsent"])
            self.assertTrue(result["profile"]["pushConsent"])
            self.assertEqual(store.list_conversations_unlocked(USER_ID), [])
            self.assertEqual(store.list_episodes_unlocked(USER_ID), [])

    def test_atomic_demo_seed_preserves_profile_conversation_and_episode_progress(self):
        cases = ("profile", "conversation", "episode")
        for progress_kind in cases:
            with self.subTest(progress_kind=progress_kind), tempfile.TemporaryDirectory() as directory:
                store = JsonStore(directory)
                with store.user_lock(USER_ID):
                    profile = default_profile(USER_ID, NOW)
                    if progress_kind == "profile":
                        profile["preferredTone"] = "direct"
                        profile["updatedAt"] = (NOW + timedelta(minutes=1)).isoformat()
                    store.save_profile_unlocked(USER_ID, profile)
                    if progress_kind == "conversation":
                        store.save_conversation_unlocked(
                            USER_ID,
                            {
                                "id": "33333333-3333-4333-8333-333333333333",
                                "userId": USER_ID,
                                "createdAt": NOW.isoformat(),
                            },
                        )
                    if progress_kind == "episode":
                        store.save_episode_unlocked(
                            USER_ID,
                            {
                                "id": "44444444-4444-4444-8444-444444444444",
                                "userId": USER_ID,
                                "createdAt": NOW.isoformat(),
                            },
                        )

                result, _ = store.execute_idempotent(
                    USER_ID,
                    "demo-seed",
                    f"demo-seed-{progress_kind}-0001",
                    NOW,
                    lambda: _demo_seed_unlocked(store, USER_ID, NOW),
                )

                self.assertFalse(result["seeded"])
                self.assertFalse(result["profile"]["memoryConsent"])
                self.assertFalse(result["profile"]["pushConsent"])

    def test_concurrent_user_update_after_seed_check_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            seed_store = JsonStore(directory, lock_timeout=5)
            writer_store = JsonStore(directory, lock_timeout=5)
            with seed_store.user_lock(USER_ID):
                seed_store.save_profile_unlocked(USER_ID, default_profile(USER_ID, NOW))

            checked = threading.Event()
            release_seed = threading.Event()
            writer_acquired = threading.Event()
            seed_result = {}
            original_check = _is_untouched_default_profile

            def pause_after_check(profile, user_id):
                untouched = original_check(profile, user_id)
                checked.set()
                self.assertTrue(release_seed.wait(5))
                return untouched

            def run_seed():
                result, _ = seed_store.execute_idempotent(
                    USER_ID,
                    "demo-seed",
                    "demo-seed-race-0001",
                    NOW,
                    lambda: _demo_seed_unlocked(seed_store, USER_ID, NOW),
                )
                seed_result.update(result)

            def apply_user_update():
                with writer_store.user_lock(USER_ID):
                    writer_acquired.set()
                    profile = writer_store.load_profile_unlocked(USER_ID)
                    profile["pushConsent"] = False
                    profile["preferredTone"] = "direct"
                    profile["updatedAt"] = (NOW + timedelta(minutes=1)).isoformat()
                    writer_store.save_profile_unlocked(USER_ID, profile)

            with patch("osekkai_cli._is_untouched_default_profile", side_effect=pause_after_check):
                seed_thread = threading.Thread(target=run_seed)
                seed_thread.start()
                self.assertTrue(checked.wait(5))
                writer_thread = threading.Thread(target=apply_user_update)
                writer_thread.start()
                self.assertFalse(writer_acquired.wait(0.2))
                release_seed.set()
                seed_thread.join(5)
                writer_thread.join(5)

            self.assertFalse(seed_thread.is_alive())
            self.assertFalse(writer_thread.is_alive())
            self.assertTrue(seed_result["seeded"])
            saved = seed_store.load_profile(USER_ID)
            self.assertEqual(saved["preferredTone"], "direct")
            self.assertFalse(saved["pushConsent"])

    def test_full_no_push_to_revisit_scenario(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            with store.user_lock(USER_ID):
                store.save_profile_unlocked(USER_ID, seed_demo_profile(USER_ID, NOW))
                first_chat = process_chat_unlocked(
                    store,
                    USER_ID,
                    {"message": "今週疲れた。何もしたくない", "remember": True},
                    NOW,
                )
            with store.user_lock(USER_ID):
                first_decide = decide_unlocked(store, USER_ID, NOW, "demo")
            with store.user_lock(USER_ID):
                second_chat = process_chat_unlocked(
                    store,
                    USER_ID,
                    {"message": "少し外に出たいが話したくない", "remember": True},
                    NOW,
                )
            with store.user_lock(USER_ID):
                second_decide = decide_unlocked(store, USER_ID, NOW, "demo")
                episode_id = second_decide["episode"]["id"]
                accepted = feedback_unlocked(
                    store, USER_ID, {"episodeId": episode_id, "actionResponse": "accepted"}, NOW
                )
                just_right = feedback_unlocked(
                    store,
                    USER_ID,
                    {"episodeId": episode_id, "distanceFeedback": "just_right"},
                    NOW,
                )
                attended = record_outcome_unlocked(
                    store,
                    USER_ID,
                    {"episodeId": episode_id, "eventType": "attendance", "status": "attended"},
                    NOW,
                )
                revisited = record_outcome_unlocked(
                    store,
                    USER_ID,
                    {"episodeId": episode_id, "eventType": "revisit", "status": "revisited"},
                    NOW,
                )
                episodes = store.list_episodes_unlocked(USER_ID)
            metrics = calculate_metrics(episodes, "demo", NOW)
            keyed = {item["key"]: item for item in metrics["metrics"]}
            self.assertEqual(first_chat["interventionHint"], "do_not_push")
            self.assertEqual(first_decide["decision"]["reasonCodes"], ["EXPLICIT_NO_ACTION"])
            self.assertEqual(second_chat["profile"]["socialBattery"], 20)
            self.assertEqual(second_chat["profile"]["maxSocialIntensity"], 1)
            self.assertTrue(second_decide["decision"]["shouldPush"])
            self.assertEqual(second_decide["decision"]["selectedOpportunity"]["id"], "koto-131083B00016")
            self.assertEqual(first_decide["episode"]["sequence"], 1)
            self.assertEqual(second_decide["episode"]["sequence"], 2)
            self.assertEqual(episodes[0]["id"], second_decide["episode"]["id"])
            self.assertEqual(accepted["episode"]["actionResponse"], "accepted")
            self.assertEqual(just_right["episode"]["distanceFeedback"], "just_right")
            self.assertIsNotNone(attended["episode"]["attendedAt"])
            self.assertIsNotNone(revisited["episode"]["revisitedAt"])
            self.assertEqual(keyed["just_right_push_rate"]["value"], 1.0)
            self.assertEqual(keyed["acceptance_rate"]["value"], 1.0)
            self.assertEqual(keyed["revisit_rate"]["value"], 1.0)

    def test_memory_consent_false_writes_minimal_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            profile = seed_demo_profile(USER_ID, NOW)
            profile["memoryConsent"] = False
            profile["pushConsent"] = False
            with store.user_lock(USER_ID):
                store.save_profile_unlocked(USER_ID, profile)
                result = decide_unlocked(store, USER_ID, NOW, "demo")
            episode = result["episode"]
            self.assertTrue(episode["minimalRecord"])
            self.assertIsNone(episode["profileSnapshot"])
            self.assertIsNone(episode["freeWindowSnapshot"])
            self.assertEqual(episode["candidateIdsBeforeFilter"], [])
            serialized = json.dumps(episode, ensure_ascii=False)
            self.assertNotIn("inferredPreferences", serialized)

    def test_distance_feedback_does_not_learn_cadence_without_memory_consent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            profile = seed_demo_profile(USER_ID, NOW)
            profile["memoryConsent"] = False
            profile["currentSignals"] = {
                "interventionHint": "consider_push",
                "currentReceptivity": 0.8,
                "safety": {"level": "normal", "requiresHumanSupport": False},
                "observedAt": NOW.isoformat(),
            }
            profile["socialBattery"] = 20
            profile["maxSocialIntensity"] = 1
            with store.user_lock(USER_ID):
                store.save_profile_unlocked(USER_ID, profile)
                episode_id = decide_unlocked(store, USER_ID, NOW, "demo")["episode"]["id"]
                result = feedback_unlocked(
                    store,
                    USER_ID,
                    {"episodeId": episode_id, "distanceFeedback": "too_much"},
                    NOW,
                )
                saved = store.load_profile_unlocked(USER_ID)

            self.assertEqual(result["episode"]["distanceFeedback"], "too_much")
            self.assertNotIn("pushCadenceDelta", result["profile"]["inferredPreferences"])
            self.assertNotIn("pushCadenceDelta", saved["inferredPreferences"])
            self.assertIsNotNone(saved["cooldownUntil"])

    def test_same_feedback_with_a_new_transport_key_is_a_domain_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            with store.user_lock(USER_ID):
                profile = seed_demo_profile(USER_ID, NOW)
                profile["currentSignals"] = {
                    "interventionHint": "consider_push",
                    "currentReceptivity": 0.8,
                    "safety": {"level": "normal", "requiresHumanSupport": False},
                    "observedAt": NOW.isoformat(),
                }
                profile["socialBattery"] = 20
                profile["maxSocialIntensity"] = 1
                store.save_profile_unlocked(USER_ID, profile)
                episode_id = decide_unlocked(store, USER_ID, NOW, "demo")["episode"]["id"]
                first_action = feedback_unlocked(
                    store,
                    USER_ID,
                    {"episodeId": episode_id, "actionResponse": "declined"},
                    NOW,
                )
                second_action = feedback_unlocked(
                    store,
                    USER_ID,
                    {"episodeId": episode_id, "actionResponse": "declined"},
                    NOW + timedelta(minutes=5),
                )
                first_distance = feedback_unlocked(
                    store,
                    USER_ID,
                    {"episodeId": episode_id, "distanceFeedback": "too_much"},
                    NOW,
                )
                cadence_id = first_distance["profile"]["inferredPreferences"]["pushCadenceDelta"]["evidence"][0]["id"]
                second_distance = feedback_unlocked(
                    store,
                    USER_ID,
                    {"episodeId": episode_id, "distanceFeedback": "too_much"},
                    NOW + timedelta(minutes=5),
                )
            self.assertEqual(first_action["profile"]["rejectionStreak"], 1)
            self.assertEqual(second_action["profile"]["rejectionStreak"], 1)
            self.assertEqual(
                first_action["episode"]["actionResponseAt"],
                second_action["episode"]["actionResponseAt"],
            )
            self.assertEqual(
                second_distance["profile"]["inferredPreferences"]["pushCadenceDelta"]["evidence"][0]["id"],
                cadence_id,
            )
            self.assertEqual(
                first_distance["episode"]["distanceFeedbackAt"],
                second_distance["episode"]["distanceFeedbackAt"],
            )

    def test_cli_stdout_is_one_json_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            env = os.environ.copy()
            env.update(
                {
                    "OSEKKAI_DATA_ROOT": directory,
                    "OSEKKAI_DEMO_MODE": "true",
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONUTF8": "1",
                }
            )
            cli = AGENT_ROOT / "scripts" / "osekkai_cli.py"

            def invoke(request):
                completed = subprocess.run(
                    [sys.executable, str(cli)],
                    input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    check=False,
                    timeout=15,
                )
                return completed, json.loads(completed.stdout.decode("utf-8"))

            reset_request = {
                "schemaVersion": "1.0",
                "requestId": "reset",
                "command": "demo-reset",
                "userId": USER_ID,
                "idempotencyKey": "demo-reset-0001",
                "payload": {},
            }
            reset, reset_json = invoke(reset_request)
            self.assertEqual(reset.returncode, 0)
            self.assertTrue(reset_json["ok"])
            decide_request = {
                "schemaVersion": "1.0",
                "requestId": "decide",
                "command": "decide",
                "userId": USER_ID,
                "idempotencyKey": "demo-decide-0001",
                "payload": {},
            }
            first, first_json = invoke(decide_request)
            second, second_json = invoke(decide_request)
            self.assertEqual(first.returncode, 0)
            self.assertEqual(first_json["data"], second_json["data"])
            self.assertTrue(second_json["idempotentReplay"])
            list_request = {
                "schemaVersion": "1.0",
                "requestId": "list",
                "command": "interventions",
                "userId": USER_ID,
                "idempotencyKey": None,
                "payload": {"action": "list"},
            }
            _, listed = invoke(list_request)
            self.assertEqual(len(listed["data"]["interventions"]), 1)

            private_message = "これは覚えないで。今週は放っておいて private-marker-9284"
            no_memory_request = {
                "schemaVersion": "1.0",
                "requestId": "no-memory",
                "command": "chat",
                "userId": USER_ID,
                "idempotencyKey": "no-memory-chat-0001",
                "payload": {"message": private_message, "remember": False},
            }
            no_memory_first, no_memory_first_json = invoke(no_memory_request)
            no_memory_second, no_memory_second_json = invoke(no_memory_request)
            self.assertEqual(no_memory_first.returncode, 0)
            self.assertEqual(no_memory_second.returncode, 0)
            self.assertTrue(no_memory_first_json["ok"])
            self.assertTrue(no_memory_second_json["idempotentReplay"])
            ledger = json.loads(
                (Path(directory) / "idempotency" / f"{USER_ID}.json").read_text(encoding="utf-8")
            )
            private_entry = ledger["entries"]["chat:no-memory-chat-0001"]
            self.assertEqual(private_entry["replay"], {"kind": "chat-no-memory"})
            self.assertNotIn(private_message, json.dumps(ledger, ensure_ascii=False))

            conflicting = copy.deepcopy(no_memory_request)
            conflicting["requestId"] = "no-memory-conflict"
            conflicting["payload"]["message"] = "違う内容"
            _, conflict_json = invoke(conflicting)
            self.assertFalse(conflict_json["ok"])
            self.assertEqual(conflict_json["error"]["code"], "IDEMPOTENCY_CONFLICT")

    def test_demo_reset_is_rejected_when_node_environment_is_production(self):
        with tempfile.TemporaryDirectory() as directory:
            env = os.environ.copy()
            env.update(
                {
                    "NODE_ENV": "production",
                    "OSEKKAI_DATA_ROOT": directory,
                    "OSEKKAI_DEMO_MODE": "true",
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONUTF8": "1",
                }
            )
            request = {
                "schemaVersion": "1.0",
                "requestId": "production-reset",
                "command": "demo-reset",
                "userId": USER_ID,
                "idempotencyKey": "production-reset-0001",
                "payload": {},
            }
            completed = subprocess.run(
                [sys.executable, str(AGENT_ROOT / "scripts" / "osekkai_cli.py")],
                input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=False,
                timeout=15,
            )
            response = json.loads(completed.stdout.decode("utf-8"))
            self.assertEqual(completed.returncode, 0)
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "DEMO_MODE_DISABLED")


if __name__ == "__main__":
    unittest.main()
