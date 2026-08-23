from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from helpers import NOW, OTHER_USER_ID, USER_ID
from osekkai_chat import process_chat_unlocked
from osekkai_contracts import ContractError
from osekkai_llm_renderer import RenderOutcome
from osekkai_memory_retrieval import retrieve_relevant_memories
from osekkai_memory_vault import ObsidianMemoryVault, build_memory_notes
from osekkai_profile import default_profile
from osekkai_store import JsonStore


UNDERSTANDING = {
    "schemaVersion": "1.0",
    "intent": "share_interest",
    "attractions": ["ボルダリング"],
    "categoryHints": ["趣味・実用"],
    "participationFrictions": ["first_time_anxiety"],
    "explicitness": "explicit",
    "confidence": 0.95,
    "needsClarification": False,
    "suggestedMemoryReferences": [],
    "doNotRemember": False,
    "doNotPush": False,
}


class ObsidianMemoryVaultTests(unittest.TestCase):
    def test_write_retrieve_and_user_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = ObsidianMemoryVault(Path(directory) / "vault")
            notes = build_memory_notes(
                user_id=USER_ID,
                reference_id="turn-1",
                understanding=UNDERSTANDING,
                frictions=["first_time_anxiety"],
                now=NOW,
            )
            for note in notes:
                vault.write_note(note)
            result = retrieve_relevant_memories(vault, USER_ID, "ボルダリング 初参加", NOW)
            self.assertEqual({note["kind"] for note in result["notes"]}, {"preference", "friction"})
            self.assertEqual(vault.list_notes(OTHER_USER_ID), [])
            self.assertTrue((Path(directory) / "vault" / ".obsidian" / "app.json").exists())

    def test_secret_coordinate_and_path_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = ObsidianMemoryVault(Path(directory) / "vault")
            note = build_memory_notes(
                user_id=USER_ID,
                reference_id="turn-1",
                understanding=UNDERSTANDING,
                frictions=[],
                now=NOW,
            )[0]
            note["summary"] = "token sk-proj-123456789012345678901234"
            with self.assertRaises(ContractError):
                vault.write_note(note)
            note["summary"] = "現在地 35.68123, 139.76712"
            with self.assertRaises(ContractError):
                vault.write_note(note)
            with self.assertRaises(ContractError):
                vault.list_notes("../../another-user")

    def test_retention_and_delete_remove_only_the_target_user(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = ObsidianMemoryVault(Path(directory) / "vault")
            note = build_memory_notes(
                user_id=USER_ID,
                reference_id="turn-1",
                understanding=UNDERSTANDING,
                frictions=[],
                now=NOW,
                retention_days=1,
            )[0]
            vault.write_note(note)
            other = dict(note, id="55555555-5555-4555-8555-555555555555", userId=OTHER_USER_ID)
            vault.write_note(other)
            self.assertEqual(vault.cleanup_expired(USER_ID, NOW + timedelta(days=2)), 1)
            self.assertEqual(len(vault.list_notes(OTHER_USER_ID)), 1)
            self.assertTrue(vault.delete_user(OTHER_USER_ID))

    def test_chat_writes_notes_only_with_memory_consent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            profile = default_profile(USER_ID, NOW)
            profile["memoryConsent"] = True
            store.save_profile_unlocked(USER_ID, profile)
            with (
                patch("osekkai_chat.understand_message", return_value=UNDERSTANDING),
                patch(
                    "osekkai_chat.render_conversation_reply",
                    return_value=RenderOutcome("ボルダリングね。候補を見てみよか。", True, None),
                ),
            ):
                process_chat_unlocked(
                    store,
                    USER_ID,
                    {"message": "ボルダリングが好き。初参加は少し不安", "remember": True},
                    NOW,
                    "demo",
                )
            vault = ObsidianMemoryVault(data_root=directory)
            self.assertEqual({note["kind"] for note in vault.list_notes(USER_ID)}, {"preference", "friction"})

            other_profile = default_profile(OTHER_USER_ID, NOW)
            other_profile["memoryConsent"] = False
            store.save_profile_unlocked(OTHER_USER_ID, other_profile)
            with (
                patch("osekkai_chat.understand_message", return_value=UNDERSTANDING),
                patch(
                    "osekkai_chat.render_conversation_reply",
                    return_value=RenderOutcome("いまの話だけで考えるね。", True, None),
                ),
            ):
                process_chat_unlocked(
                    store,
                    OTHER_USER_ID,
                    {"message": "料理が好き", "remember": True},
                    NOW,
                    "demo",
                )
            self.assertEqual(vault.list_notes(OTHER_USER_ID), [])


if __name__ == "__main__":
    unittest.main()
