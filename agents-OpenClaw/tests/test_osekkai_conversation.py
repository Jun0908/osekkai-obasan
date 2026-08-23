from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch

from helpers import AGENT_ROOT, NOW, USER_ID
from osekkai_chat import process_chat_unlocked
from osekkai_context_trigger import analyze_calendar_sparsity, proactive_trigger_allowed
from osekkai_contracts import ContractError, validate_schema
from osekkai_conversation import (
    _new_episode,
    classify_participation_frictions,
    start_calendar_sparse_episode_unlocked,
    transition_episode,
)
from osekkai_freebusy import ProviderError
from osekkai_policy import rank_conversation_candidates
from osekkai_profile import (
    apply_participation_frictions,
    default_profile,
    effective_participation_frictions,
    parse_datetime,
)
from osekkai_store import JsonStore


def live_fixture():
    value = json.loads(
        (AGENT_ROOT / "fixtures" / "osekkai" / "live-contracts.json").read_text(
            encoding="utf-8"
        )
    )
    opportunities = copy.deepcopy(value["opportunities"][:2])
    ranked = [
        {
            "rank": rank,
            "opportunity": opportunity,
            "recommendationReasons": [
                {
                    "code": "personal_fit",
                    "text": "本人の好みと確認済み条件に合う候補です。",
                    "evidenceUrl": opportunity["sourceUrl"],
                    "classification": "private_user_data",
                }
            ],
        }
        for rank, opportunity in enumerate(opportunities, start=1)
    ]
    return opportunities, ranked


def freebusy(now=NOW):
    return {
        "schemaVersion": "1.0",
        "dataMode": "live",
        "generatedAt": now.isoformat(),
        "source": {"type": "google_freebusy", "notice": "FreeBusyだけを使用"},
        "freeWindows": [
            {
                "id": "free-1",
                "start": (now + timedelta(days=1)).replace(hour=10).isoformat(),
                "end": (now + timedelta(days=1)).replace(hour=13).isoformat(),
                "durationMinutes": 180,
                "verificationStatus": "source_verified",
            },
            {
                "id": "free-2",
                "start": (now + timedelta(days=2)).replace(hour=14).isoformat(),
                "end": (now + timedelta(days=2)).replace(hour=17).isoformat(),
                "durationMinutes": 180,
                "verificationStatus": "source_verified",
            },
        ],
    }


class ConversationContractTests(unittest.TestCase):
    def test_valid_state_path_and_invalid_transition(self):
        episode = _new_episode(
            USER_ID,
            NOW,
            trigger="user_initiated",
            state="getting_to_know",
            reason="test",
        )
        episode = transition_episode(
            episode,
            "shortlist_shown",
            NOW,
            shownOpportunityIds=["event-a", "event-b"],
            presentationCount=1,
        )
        episode = transition_episode(episode, "friction_probe", NOW)
        episode = transition_episode(
            episode,
            "adjusted_shortlist",
            NOW,
            adjustedOpportunityIds=["event-b", "event-a"],
            presentationCount=2,
            adjustmentCount=1,
        )
        episode = transition_episode(
            episode,
            "accepted",
            NOW,
            selectedOpportunityId="event-b",
            selectedEventId="event-b",
            selectedEventEndsAt=(NOW + timedelta(hours=2)).isoformat(),
            checkInDueAt=(NOW + timedelta(hours=4)).isoformat(),
        )
        episode = transition_episode(episode, "check_in_due", NOW + timedelta(hours=4))
        validate_schema(episode, "conversation-episode.schema.json")

        start = _new_episode(
            USER_ID,
            NOW,
            trigger="user_initiated",
            state="getting_to_know",
            reason="test",
        )
        with self.assertRaises(ContractError):
            transition_episode(start, "accepted", NOW)
        with self.assertRaises(ContractError):
            transition_episode(
                episode,
                "check_in_due",
                NOW,
                adjustmentCount=2,
            )

    def test_every_participation_friction_is_classified_from_free_text(self):
        message = (
            "探すのが面倒。初参加で知らない人ばかり、大人数で会話が多そう。"
            "遠いし時間が長く料金も高い。今日は疲れたし、強く誘わないで。今回は無理。"
        )
        self.assertEqual(
            set(classify_participation_frictions(message)),
            {
                "search_fatigue",
                "first_time_anxiety",
                "stranger_anxiety",
                "group_size",
                "conversation_load",
                "travel_effort",
                "time_commitment",
                "cost",
                "low_social_energy",
                "push_aversion",
                "not_today",
            },
        )

    def test_explicit_friction_wins_and_only_inferred_evidence_decays(self):
        profile = default_profile(USER_ID, NOW)
        inferred, _ = apply_participation_frictions(
            profile,
            ["travel_effort"],
            origin="inferred",
            reference_type="message",
            reference_id="turn-1",
            evidence_text="移動負担の推定",
            confidence=0.8,
            now=NOW,
        )
        explicit, _ = apply_participation_frictions(
            inferred,
            ["travel_effort"],
            origin="explicit",
            reference_type="feedback",
            reference_id="feedback-1",
            evidence_text="本人が遠いと回答",
            confidence=1,
            now=NOW + timedelta(days=1),
        )
        overwritten, _ = apply_participation_frictions(
            explicit,
            ["travel_effort"],
            origin="inferred",
            reference_type="message",
            reference_id="turn-2",
            evidence_text="近そうという推定",
            confidence=0.2,
            now=NOW + timedelta(days=2),
        )
        self.assertEqual(overwritten["participationFriction"]["travel_effort"]["origin"], "explicit")
        self.assertEqual(
            effective_participation_frictions(overwritten, NOW + timedelta(days=365))["travel_effort"],
            1.0,
        )
        self.assertNotIn(
            "travel_effort",
            effective_participation_frictions(inferred, NOW + timedelta(days=365)),
        )


class CalendarConversationTriggerTests(unittest.TestCase):
    def test_sparse_dense_and_malformed_freebusy(self):
        sparse = analyze_calendar_sparsity(freebusy(), NOW)
        self.assertTrue(sparse["isSparse"])
        self.assertGreaterEqual(sparse["summary"]["longFreeWindowCount"], 2)

        dense_value = freebusy()
        dense_value["freeWindows"] = [
            {
                "id": "tiny",
                "start": (NOW + timedelta(days=1)).replace(hour=10).isoformat(),
                "end": (NOW + timedelta(days=1)).replace(hour=10, minute=30).isoformat(),
                "durationMinutes": 30,
                "verificationStatus": "source_verified",
            }
        ]
        self.assertFalse(analyze_calendar_sparsity(dense_value, NOW)["isSparse"])

        malformed = freebusy()
        malformed["freeWindows"] = [{"start": "not-a-date", "end": "also-bad"}]
        with self.assertRaises(ContractError):
            analyze_calendar_sparsity(malformed, NOW)

    def test_consent_quiet_cooldown_and_safety_block_trigger(self):
        profile = default_profile(USER_ID, NOW)
        profile["pushConsent"] = True
        self.assertTrue(proactive_trigger_allowed(profile, [], NOW))
        for mutation in (
            {"pushConsent": False},
            {"cooldownUntil": (NOW + timedelta(days=1)).isoformat()},
            {"pauseUntil": (NOW + timedelta(days=1)).isoformat()},
        ):
            blocked = copy.deepcopy(profile)
            blocked.update(mutation)
            self.assertFalse(proactive_trigger_allowed(blocked, [], NOW))
        unsafe = copy.deepcopy(profile)
        unsafe["currentSignals"]["safety"] = {
            "level": "urgent",
            "requiresHumanSupport": True,
        }
        self.assertFalse(proactive_trigger_allowed(unsafe, [], NOW))

    def test_sparse_trigger_needs_multiple_real_candidates_and_fails_closed_on_timeout(self):
        opportunities, ranked = live_fixture()
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            profile = default_profile(USER_ID, NOW)
            profile.update({"pushConsent": True, "memoryConsent": True})
            with store.user_lock(USER_ID):
                store.save_profile_unlocked(USER_ID, profile)
                with (
                    patch("osekkai_conversation.load_freebusy", return_value=freebusy()),
                    patch("osekkai_conversation.build_recommendation_context", return_value=ranked),
                ):
                    result = start_calendar_sparse_episode_unlocked(store, USER_ID, NOW, "live")
                self.assertIsNotNone(result)
                self.assertEqual(result["episode"]["state"], "shortlist_shown")
                self.assertEqual(len(result["context"]["recommendations"]), 2)

            other = "22222222-2222-4222-8222-222222222222"
            other_profile = default_profile(other, NOW)
            other_profile["pushConsent"] = True
            with store.user_lock(other):
                store.save_profile_unlocked(other, other_profile)
                with (
                    patch("osekkai_conversation.load_freebusy", return_value=freebusy()),
                    patch("osekkai_conversation.build_recommendation_context", return_value=ranked[:1]),
                ):
                    self.assertIsNone(start_calendar_sparse_episode_unlocked(store, other, NOW, "live"))
                with patch(
                    "osekkai_conversation.load_freebusy",
                    side_effect=ProviderError("timeout"),
                ):
                    self.assertIsNone(start_calendar_sparse_episode_unlocked(store, other, NOW, "live"))


class FullConversationLoopTests(unittest.TestCase):
    def test_chat_completes_shortlist_adjustment_selection_and_check_in(self):
        opportunities, ranked = live_fixture()
        source = {
            "schemaVersion": "1.0",
            "dataMode": "live",
            "notice": "fixture",
            "opportunities": opportunities,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            profile = default_profile(USER_ID, NOW)
            profile["memoryConsent"] = True
            with store.user_lock(USER_ID):
                store.save_profile_unlocked(USER_ID, profile)
                with (
                    patch("osekkai_conversation.load_freebusy", return_value=freebusy()),
                    patch("osekkai_conversation.build_recommendation_context", return_value=ranked),
                    patch("osekkai_conversation.load_opportunities", return_value=source),
                ):
                    first = process_chat_unlocked(
                        store,
                        USER_ID,
                        {"message": "ボルダリングが好き", "remember": True},
                        NOW,
                        "live",
                    )
                    self.assertEqual(first["context"]["state"], "shortlist_shown")
                    self.assertEqual(len(first["context"]["recommendations"]), 2)

                    rejected = process_chat_unlocked(
                        store,
                        USER_ID,
                        {"message": "これは違う", "remember": True},
                        NOW + timedelta(minutes=1),
                        "live",
                    )
                    self.assertEqual(rejected["context"]["state"], "friction_probe")

                    adjusted = process_chat_unlocked(
                        store,
                        USER_ID,
                        {"message": "ちょっと遠い", "remember": True},
                        NOW + timedelta(minutes=2),
                        "live",
                    )
                    self.assertEqual(adjusted["context"]["state"], "adjusted_shortlist")
                    selected_id = adjusted["context"]["recommendations"][0]["opportunity"]["id"]
                    accepted = process_chat_unlocked(
                        store,
                        USER_ID,
                        {"action": "select", "opportunityId": selected_id, "remember": True},
                        NOW + timedelta(minutes=3),
                        "live",
                    )
                    self.assertEqual(accepted["context"]["state"], "accepted")

                    with self.assertRaisesRegex(ContractError, "check-in is not due"):
                        process_chat_unlocked(
                            store,
                            USER_ID,
                            {
                                "action": "check_in",
                                "message": "どうだった？",
                                "remember": True,
                            },
                            NOW + timedelta(minutes=4),
                            "live",
                        )

                    due = parse_datetime(accepted["context"]["checkInDueAt"]) + timedelta(minutes=1)
                    resumed = process_chat_unlocked(
                        store,
                        USER_ID,
                        {"action": "start", "remember": True},
                        due,
                        "live",
                    )
                    self.assertEqual(resumed["context"]["state"], "check_in_due")
                    checked = process_chat_unlocked(
                        store,
                        USER_ID,
                        {"action": "check_in", "message": "会話が多すぎた", "remember": True},
                        due + timedelta(minutes=1),
                        "live",
                    )
                    self.assertEqual(checked["context"]["state"], "getting_to_know")
                    self.assertIn("conversation_load", checked["profile"]["participationFriction"])

                    with self.assertRaises(ContractError):
                        process_chat_unlocked(
                            store,
                            USER_ID,
                            {"action": "check_in", "message": "楽しかった", "remember": True},
                            due + timedelta(minutes=2),
                            "live",
                        )

    def test_memory_off_keeps_raw_text_and_inference_out_of_storage(self):
        _opportunities, ranked = live_fixture()
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            profile = default_profile(USER_ID, NOW)
            profile["memoryConsent"] = True
            with store.user_lock(USER_ID):
                store.save_profile_unlocked(USER_ID, profile)
                with (
                    patch("osekkai_conversation.load_freebusy", return_value=freebusy()),
                    patch("osekkai_conversation.build_recommendation_context", return_value=ranked),
                ):
                    result = process_chat_unlocked(
                        store,
                        USER_ID,
                        {"message": "ボルダリングが好き", "remember": False},
                        NOW,
                        "live",
                    )
                saved = store.load_profile_unlocked(USER_ID)
                episodes = store.list_conversation_episodes_unlocked(USER_ID)
            self.assertFalse(result["persisted"])
            self.assertEqual(store.list_conversations_unlocked(USER_ID), [])
            self.assertEqual(saved["preferredCategories"], [])
            self.assertEqual(saved["participationFriction"], {})
            self.assertEqual(episodes[0]["turnIds"], [])

    def test_same_attraction_different_friction_changes_explanation(self):
        opportunities, _ranked = live_fixture()
        live_now = parse_datetime("2026-08-23T09:00:00+09:00")
        live_freebusy = {
            **freebusy(live_now),
            "freeWindows": [
                {
                    "id": "window-craft",
                    "start": "2026-09-05T12:00:00+09:00",
                    "end": "2026-09-05T18:00:00+09:00",
                    "durationMinutes": 360,
                    "verificationStatus": "source_verified",
                },
                {
                    "id": "window-boardgame",
                    "start": "2026-09-06T10:00:00+09:00",
                    "end": "2026-09-06T18:00:00+09:00",
                    "durationMinutes": 480,
                    "verificationStatus": "source_verified",
                },
            ],
        }
        profile = json.loads(
            (AGENT_ROOT / "fixtures" / "osekkai" / "profile.json").read_text(encoding="utf-8")
        )
        profile.update(
            {
                "preferredCategories": ["craft"],
                "maxSocialIntensity": 5,
                "socialBattery": 80,
                "maxTravelMinutes": 40,
                "maxBudgetYen": 3000,
            }
        )
        source = {"dataMode": "live", "opportunities": opportunities}
        plain = rank_conversation_candidates(
            profile, live_freebusy, source, live_now, friction_types=set()
        )
        travel = rank_conversation_candidates(
            profile,
            live_freebusy,
            source,
            live_now,
            friction_types={"travel_effort"},
        )
        self.assertEqual(
            [item["opportunity"]["id"] for item in plain],
            [item["opportunity"]["id"] for item in travel],
        )
        self.assertNotEqual(
            plain[0]["recommendationReasons"][0]["text"],
            travel[0]["recommendationReasons"][0]["text"],
        )


if __name__ == "__main__":
    unittest.main()
