from __future__ import annotations

import unittest

from helpers import AGENT_ROOT  # noqa: F401  (adds the canonical scripts directory to sys.path)
from osekkai_dialogue_plan import build_dialogue_plan


def conversation(state: str = "getting_to_know", **context_overrides) -> dict:
    context = {"state": state, "recommendations": [], "notice": None, **context_overrides}
    return {"reply": "fallback reply", "context": context}


class DialoguePlanTests(unittest.TestCase):
    def test_without_community_facts_behaves_exactly_as_before(self):
        plan = build_dialogue_plan(conversation(), understanding=None, memories=[])
        self.assertEqual(plan["allowedEventFacts"], [])

    def test_community_facts_are_appended_to_allowed_event_facts(self):
        facts = [
            "地域コミュニティ(Open Data・活動有無/開催日時は未確認)=九段生涯学習館に3件登録、例: 読書会さくら、卓球クラブ",
        ]
        plan = build_dialogue_plan(
            conversation(), understanding=None, memories=[], community_facts=facts
        )
        self.assertEqual(plan["allowedEventFacts"], facts)
        # Community facts are informational only: never forced into mustMention.
        self.assertNotIn(facts[0], plan["mustMention"])

    def test_community_facts_are_deduplicated_and_capped_with_event_facts(self):
        opportunity = {
            "id": "opportunity-1",
            "title": "読書会",
            "startsAt": "2026-08-24T10:00:00+09:00",
            "endsAt": "2026-08-24T12:00:00+09:00",
            "address": "東京都千代田区麹町1-1",
            "provider": "koto_culture",
        }
        plan = build_dialogue_plan(
            conversation(recommendations=[{"opportunity": opportunity}]),
            understanding=None,
            memories=[],
            community_facts=["地域コミュニティ(Open Data・活動有無/開催日時は未確認)=九段生涯学習館に1件登録、例: 読書会さくら"] * 3,
        )
        self.assertEqual(len(plan["allowedEventFacts"]), len(set(plan["allowedEventFacts"])))
        self.assertLessEqual(len(plan["allowedEventFacts"]), 30)

    def test_blank_community_facts_are_dropped(self):
        plan = build_dialogue_plan(
            conversation(), understanding=None, memories=[], community_facts=["", "   "]
        )
        self.assertEqual(plan["allowedEventFacts"], [])


if __name__ == "__main__":
    unittest.main()
