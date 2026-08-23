from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch

from helpers import AGENT_ROOT, NOW, USER_ID
from osekkai_chat import process_chat_unlocked
from osekkai_llm_renderer import RenderOutcome
from osekkai_memory_vault import ObsidianMemoryVault
from osekkai_profile import default_profile, parse_datetime
from osekkai_store import JsonStore


def understanding(
    *,
    intent="general",
    attractions=None,
    categories=None,
    frictions=None,
    explicitness="explicit",
):
    return {
        "schemaVersion": "1.0",
        "intent": intent,
        "attractions": attractions or [],
        "categoryHints": categories or [],
        "participationFrictions": frictions or [],
        "explicitness": explicitness,
        "confidence": 0.96,
        "needsClarification": False,
        "suggestedMemoryReferences": [],
        "doNotRemember": False,
        "doNotPush": False,
    }


class Plan3JudgeDemoTests(unittest.TestCase):
    def test_interest_friction_selection_checkin_and_learned_memory_complete(self):
        fixture = json.loads(
            (AGENT_ROOT / "fixtures" / "osekkai" / "live-contracts.json").read_text(
                encoding="utf-8"
            )
        )
        opportunities = copy.deepcopy(fixture["opportunities"][:2])
        ranked = [
            {
                "rank": rank,
                "opportunity": value,
                "recommendationReasons": [
                    {
                        "code": "personal_fit",
                        "text": "本人の好みと確認済み条件に合う候補です。",
                        "evidenceUrl": value["sourceUrl"],
                        "classification": "private_user_data",
                    }
                ],
            }
            for rank, value in enumerate(opportunities, start=1)
        ]
        source = {
            "schemaVersion": "1.0",
            "dataMode": "live",
            "notice": "fixture",
            "opportunities": opportunities,
        }
        freebusy = {
            "schemaVersion": "1.0",
            "dataMode": "live",
            "generatedAt": NOW.isoformat(),
            "source": {"type": "google_freebusy", "notice": "FreeBusyだけを使用"},
            "freeWindows": [
                {
                    "id": "free-1",
                    "start": (NOW + timedelta(days=1)).replace(hour=9).isoformat(),
                    "end": (NOW + timedelta(days=1)).replace(hour=20).isoformat(),
                    "durationMinutes": 660,
                    "verificationStatus": "source_verified",
                }
            ],
        }
        messages = {
            "ボルダリングが好き": understanding(
                intent="share_interest",
                attractions=["ボルダリング"],
                categories=["趣味・実用"],
            ),
            "これは違う": understanding(intent="reject"),
            "常連ばかりの大人数だと入りにくい": understanding(
                intent="share_friction", frictions=["group_size"]
            ),
            "また行きたい。人の感じもよかった": understanding(intent="check_in"),
        }

        def fake_understanding(message, **_kwargs):
            return messages.get(message, understanding())

        def fake_renderer(plan, **_kwargs):
            prefix = {
                "present_shortlist": "好みを踏まえて見つけたよ。",
                "probe_friction": "違うのはわかった。",
                "present_adjusted_shortlist": "大人数を避けて見直したよ。",
                "check_in": "この前のこと、さりげなく聞かせて。",
            }.get(plan["dialogueAct"], "")
            return RenderOutcome((prefix + plan["fallbackReply"])[:300], True, None)

        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            profile = default_profile(USER_ID, NOW)
            profile["memoryConsent"] = True
            store.save_profile_unlocked(USER_ID, profile)
            with (
                patch("osekkai_chat.understand_message", side_effect=fake_understanding),
                patch("osekkai_chat.render_conversation_reply", side_effect=fake_renderer),
                patch("osekkai_conversation.load_freebusy", return_value=freebusy),
                patch("osekkai_conversation.build_recommendation_context", return_value=ranked),
                patch("osekkai_conversation.load_opportunities", return_value=source),
            ):
                first = process_chat_unlocked(
                    store, USER_ID, {"message": "ボルダリングが好き", "remember": True}, NOW, "live"
                )
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
                    {"message": "常連ばかりの大人数だと入りにくい", "remember": True},
                    NOW + timedelta(minutes=2),
                    "live",
                )
                self.assertEqual(len(adjusted["context"]["recommendations"]), 2)
                selected_id = adjusted["context"]["recommendations"][0]["opportunity"]["id"]
                selected = process_chat_unlocked(
                    store,
                    USER_ID,
                    {"action": "select", "opportunityId": selected_id, "remember": True},
                    NOW + timedelta(minutes=3),
                    "live",
                )
                due = parse_datetime(selected["context"]["checkInDueAt"]) + timedelta(minutes=1)
                process_chat_unlocked(
                    store, USER_ID, {"action": "start", "remember": True}, due, "live"
                )
                checked = process_chat_unlocked(
                    store,
                    USER_ID,
                    {"action": "check_in", "message": "また行きたい。人の感じもよかった", "remember": True},
                    due + timedelta(minutes=1),
                    "live",
                )

            self.assertEqual(checked["context"]["state"], "getting_to_know")
            self.assertEqual(checked["profile"]["inferredPreferences"]["revisitPreference"]["value"], "interested")
            kinds = {note["kind"] for note in ObsidianMemoryVault(data_root=directory).list_notes(USER_ID)}
            self.assertTrue({"preference", "friction", "episode", "feedback"}.issubset(kinds))
            assistant_replies = [
                value["text"]
                for value in store.list_conversations_unlocked(USER_ID)
                if value["role"] == "assistant"
            ]
            self.assertEqual(len(assistant_replies), len(set(assistant_replies)))


if __name__ == "__main__":
    unittest.main()
