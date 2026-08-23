from __future__ import annotations

import json
import unittest
from unittest.mock import Mock

import requests

from helpers import USER_ID
from osekkai_dialogue_plan import build_dialogue_plan
from osekkai_llm import LLMClient, LLMConfig, LLMError
from osekkai_llm_renderer import render_conversation_reply
from osekkai_llm_understanding import understand_message


MEMORY_ID = "33333333-3333-4333-8333-333333333333"
OTHER_MEMORY_ID = "44444444-4444-4444-8444-444444444444"


def config() -> LLMConfig:
    return LLMConfig(
        enabled=True,
        provider="openai",
        model="test-model",
        api_key="test-only-key",
        base_url="https://api.openai.com/v1",
        timeout_seconds=1.0,
    )


class FakeResponse:
    def __init__(self, status_code: int, value):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._value = value

    def json(self):
        return self._value


class FakeClient:
    def __init__(self, value):
        self.value = value

    def generate_json(self, **_kwargs):
        return self.value


class LLMAdapterTests(unittest.TestCase):
    def test_responses_api_uses_store_false_and_parses_strict_json(self):
        output = {"schemaVersion": "1.0", "value": "ok"}
        session = Mock()
        session.post.return_value = FakeResponse(
            200,
            {
                "status": "completed",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": json.dumps(output)}]}
                ],
            },
        )
        client = LLMClient(config(), session)
        result = client.generate_json(
            instructions="test",
            input_text="input",
            schema_name="test_output",
            schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["schemaVersion", "value"],
                "properties": {
                    "schemaVersion": {"type": "string", "const": "1.0"},
                    "value": {"type": "string"},
                },
            },
        )
        self.assertEqual(result, output)
        request = session.post.call_args.kwargs
        self.assertFalse(request["json"]["store"])
        self.assertNotIn("test-only-key", json.dumps(request["json"]))

    def test_timeout_has_one_bounded_retry(self):
        session = Mock()
        session.post.side_effect = requests.Timeout()
        client = LLMClient(config(), session)
        with self.assertRaisesRegex(LLMError, "LLM provider unavailable") as raised:
            client.generate_json(
                instructions="test",
                input_text="input",
                schema_name="test_output",
                schema={"type": "object", "additionalProperties": False, "properties": {}, "required": []},
            )
        self.assertEqual(raised.exception.code, "LLM_TIMEOUT")
        self.assertEqual(session.post.call_count, 2)

    def test_malformed_json_fails_closed(self):
        session = Mock()
        session.post.return_value = FakeResponse(
            200,
            {"status": "completed", "output": [{"content": [{"type": "output_text", "text": "not-json"}]}]},
        )
        with self.assertRaises(LLMError) as raised:
            LLMClient(config(), session).generate_json(
                instructions="test",
                input_text="input",
                schema_name="test_output",
                schema={"type": "object", "additionalProperties": False, "properties": {}, "required": []},
            )
        self.assertEqual(raised.exception.code, "LLM_MALFORMED_JSON")


class LLMUnderstandingTests(unittest.TestCase):
    def test_free_expression_extracts_interest_and_multiple_frictions(self):
        value = {
            "schemaVersion": "1.0",
            "intent": "share_interest",
            "attractions": ["ボルダリング"],
            "categoryHints": ["趣味・実用"],
            "participationFrictions": ["first_time_anxiety", "group_size"],
            "explicitness": "explicit",
            "confidence": 0.96,
            "needsClarification": False,
            "suggestedMemoryReferences": [MEMORY_ID],
            "doNotRemember": False,
            "doNotPush": False,
        }
        result = understand_message(
            "登るのは好き。ただ常連ばかりの大人数へ最初から入るのは気が重い",
            memories=[{"id": MEMORY_ID, "kind": "preference", "summary": "前に登る話をした", "keywords": ["登る"], "origin": "explicit"}],
            recent_turns=[],
            episode_state="getting_to_know",
            client=FakeClient(value),
        )
        self.assertEqual(result["categoryHints"], ["趣味・実用"])
        self.assertEqual(set(result["participationFrictions"]), {"first_time_anxiety", "group_size"})

    def test_unknown_memory_reference_is_rejected(self):
        value = {
            "schemaVersion": "1.0",
            "intent": "general",
            "attractions": [],
            "categoryHints": [],
            "participationFrictions": [],
            "explicitness": "unknown",
            "confidence": 0.5,
            "needsClarification": True,
            "suggestedMemoryReferences": [OTHER_MEMORY_ID],
            "doNotRemember": False,
            "doNotPush": False,
        }
        with self.assertRaises(LLMError) as raised:
            understand_message(
                "前の話の続き",
                memories=[{"id": MEMORY_ID, "kind": "preference", "summary": "記憶", "keywords": [], "origin": "explicit"}],
                recent_turns=[],
                episode_state="getting_to_know",
                client=FakeClient(value),
            )
        self.assertEqual(raised.exception.code, "LLM_MEMORY_REFERENCE_INVALID")


class LLMRendererTests(unittest.TestCase):
    def plan(self):
        return build_dialogue_plan(
            {
                "reply": "やってみたいことを一つだけ教えて。",
                "context": {"state": "getting_to_know", "recommendations": [], "notice": None},
            },
            understanding={"needsClarification": False},
            memories=[],
        )

    def test_unsupported_event_claim_uses_fallback(self):
        generated = {
            "schemaVersion": "1.0",
            "text": "一人参加OKだから行けるよ。",
            "usedEventIds": [],
            "usedMemoryIds": [],
            "questionCount": 0,
        }
        result = render_conversation_reply(
            self.plan(),
            user_message="何かある？",
            memories=[],
            recent_turns=[],
            client=FakeClient(generated),
        )
        self.assertFalse(result.used_llm)
        self.assertEqual(result.fallback_code, "LLM_UNSUPPORTED_EVENT_CLAIM")

    def test_exact_repetition_uses_a_different_safe_fallback(self):
        plan = self.plan()
        repeated = {
            "schemaVersion": "1.0",
            "text": "やってみたいことを一つだけ教えて。",
            "usedEventIds": [],
            "usedMemoryIds": [],
            "questionCount": 1,
        }
        result = render_conversation_reply(
            plan,
            user_message="まだわからない",
            memories=[],
            recent_turns=[{"role": "assistant", "text": repeated["text"]}],
            client=FakeClient(repeated),
        )
        self.assertNotEqual(result.text, repeated["text"])
        self.assertEqual(result.fallback_code, "LLM_REPLY_REPEATED")


if __name__ == "__main__":
    unittest.main()
