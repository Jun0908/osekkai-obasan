from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from helpers import NOW, USER_ID
from osekkai_chat import process_chat_unlocked
from osekkai_contracts import ContractError
from osekkai_profile import (
    apply_explicit_patch,
    apply_inferred_delta,
    clock_now,
    default_profile,
    get_or_create_profile_unlocked,
    remove_evidence,
    remove_inferred_preference,
)
from osekkai_store import JsonStore


class ProfileTests(unittest.TestCase):
    def test_production_clock_ignores_demo_and_fixed_time_flags(self):
        with patch.dict(
            "os.environ",
            {
                "NODE_ENV": "production",
                "OSEKKAI_DEMO_MODE": "true",
                "OSEKKAI_FIXED_NOW": "2019-02-23T10:00:00+09:00",
            },
            clear=False,
        ):
            observed = clock_now()
        self.assertNotEqual(observed.year, 2019)
        self.assertLess(abs(datetime.now(observed.tzinfo) - observed), timedelta(seconds=5))

    def test_safe_defaults_keep_both_consents_off(self):
        profile = default_profile(USER_ID, NOW)
        self.assertFalse(profile["memoryConsent"])
        self.assertFalse(profile["pushConsent"])
        self.assertIsNone(profile["socialBattery"])
        self.assertEqual(profile["maxTravelMinutes"], 40)

    def test_old_untouched_travel_default_migrates_but_explicit_value_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            old = default_profile(USER_ID, NOW - timedelta(days=1))
            old["maxTravelMinutes"] = 30
            with store.user_lock(USER_ID):
                store.save_profile_unlocked(USER_ID, old)
                migrated = get_or_create_profile_unlocked(store, USER_ID, NOW)
                explicit = apply_explicit_patch(migrated, {"maxTravelMinutes": 30}, NOW)
                store.save_profile_unlocked(USER_ID, explicit)
                preserved = get_or_create_profile_unlocked(store, USER_ID, NOW + timedelta(minutes=1))
        self.assertEqual(migrated["maxTravelMinutes"], 40)
        self.assertEqual(preserved["maxTravelMinutes"], 30)

    def test_explicit_patch_is_whitelisted_and_separate(self):
        profile = default_profile(USER_ID, NOW)
        updated = apply_explicit_patch(profile, {"pushConsent": True, "maxBudgetYen": 500}, NOW)
        self.assertTrue(updated["pushConsent"])
        self.assertEqual(updated["maxBudgetYen"], 500)
        self.assertEqual(updated["inferredPreferences"], {})
        with self.assertRaises(ContractError):
            apply_explicit_patch(profile, {"rejectionStreak": 99}, NOW)

    def test_inference_has_confidence_and_individually_removable_evidence(self):
        profile = default_profile(USER_ID, NOW)
        inferred = apply_inferred_delta(profile, {"socialBattery": 20}, 0.82, "今週疲れた", NOW)
        item = inferred["inferredPreferences"]["socialBattery"]
        self.assertEqual(item["confidence"], 0.82)
        evidence_id = item["evidence"][0]["id"]
        cleaned, removed = remove_evidence(inferred, evidence_id, NOW)
        self.assertTrue(removed)
        self.assertNotIn("socialBattery", cleaned["inferredPreferences"])
        self.assertIsNone(cleaned["socialBattery"])

    def test_inferred_preference_key_can_be_removed(self):
        profile = apply_inferred_delta(default_profile(USER_ID, NOW), {"socialBattery": 20}, 0.8, "疲れた", NOW)
        cleaned, removed = remove_inferred_preference(profile, "socialBattery", NOW)
        self.assertTrue(removed)
        self.assertEqual(cleaned["inferredPreferences"], {})
        self.assertIsNone(cleaned["socialBattery"])

    def test_hobby_conversation_accumulates_categories_used_by_ranking(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            with store.user_lock(USER_ID):
                profile = default_profile(USER_ID, NOW)
                profile["memoryConsent"] = True
                store.save_profile_unlocked(USER_ID, profile)
                yoga = process_chat_unlocked(
                    store,
                    USER_ID,
                    {"message": "ヨガをやってみたい", "remember": True},
                    NOW,
                )
                climbing = process_chat_unlocked(
                    store,
                    USER_ID,
                    {"message": "ボルダリングが好き", "remember": True},
                    NOW + timedelta(minutes=1),
                )
            self.assertEqual(yoga["profileDelta"]["preferredCategories"], ["ダンス・健康"])
            self.assertIn("ヨガ", yoga["reply"])
            self.assertEqual(
                climbing["profile"]["preferredCategories"],
                ["ダンス・健康", "趣味・実用"],
            )
            self.assertEqual(climbing["interventionHint"], "consider_push")

    def test_removing_hobby_evidence_restores_explicit_categories_only(self):
        profile = default_profile(USER_ID, NOW)
        profile = apply_explicit_patch(profile, {"preferredCategories": ["音楽・演劇"]}, NOW)
        inferred = apply_inferred_delta(
            profile,
            {"preferredCategories": ["ダンス・健康"]},
            0.86,
            "ヨガをやってみたい",
            NOW,
        )
        evidence_id = inferred["inferredPreferences"]["preferredCategories"]["evidence"][0]["id"]
        cleaned, removed = remove_evidence(inferred, evidence_id, NOW)
        self.assertTrue(removed)
        self.assertEqual(cleaned["preferredCategories"], ["音楽・演劇"])

    def test_deleting_inference_restores_pre_inference_social_intensity(self):
        profile = default_profile(USER_ID, NOW)
        profile = apply_explicit_patch(profile, {"maxSocialIntensity": 4}, NOW)
        inferred = apply_inferred_delta(
            profile,
            {"maxSocialIntensity": 1},
            0.9,
            "話したくない",
            NOW,
        )
        self.assertEqual(inferred["maxSocialIntensity"], 1)

        evidence_id = inferred["inferredPreferences"]["maxSocialIntensity"]["evidence"][0]["id"]
        cleaned, removed = remove_evidence(inferred, evidence_id, NOW)

        self.assertTrue(removed)
        self.assertNotIn("maxSocialIntensity", cleaned["inferredPreferences"])
        self.assertEqual(cleaned["maxSocialIntensity"], 4)

    def test_remember_false_does_not_store_conversation_or_inference_but_keeps_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            with store.user_lock(USER_ID):
                profile = default_profile(USER_ID, NOW)
                profile["memoryConsent"] = True
                store.save_profile_unlocked(USER_ID, profile)
                result = process_chat_unlocked(
                    store,
                    USER_ID,
                    {"message": "これは覚えないで。今週は放っておいて", "remember": False},
                    NOW,
                )
                saved = store.load_profile_unlocked(USER_ID)
                conversations = store.list_conversations_unlocked(USER_ID)
            self.assertFalse(result["persisted"])
            self.assertEqual(result["profileDelta"], {})
            self.assertEqual(conversations, [])
            self.assertIsNotNone(saved["pauseUntil"])
            self.assertEqual(saved["inferredPreferences"], {})

    def test_do_not_remember_still_honors_explicit_no_push(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            with store.user_lock(USER_ID):
                profile = default_profile(USER_ID, NOW)
                profile["memoryConsent"] = True
                store.save_profile_unlocked(USER_ID, profile)
                result = process_chat_unlocked(
                    store,
                    USER_ID,
                    {"message": "今日はそっとしておいて", "remember": False},
                    NOW,
                )
                conversations = store.list_conversations_unlocked(USER_ID)
            self.assertFalse(result["persisted"])
            self.assertEqual(result["profileDelta"], {})
            self.assertEqual(result["interventionHint"], "do_not_push")
            self.assertEqual(result["profile"]["currentSignals"]["interventionHint"], "do_not_push")
            self.assertEqual(conversations, [])


if __name__ == "__main__":
    unittest.main()
