from __future__ import annotations

import tempfile
import unittest

from helpers import USER_ID
from osekkai_contracts import ContractError
from osekkai_store import JsonStore


class SecurityTests(unittest.TestCase):
    def test_store_rejects_path_traversal_user_id(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            with self.assertRaises(ContractError):
                store.profile_path("../../victim")

    def test_profile_ownership_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            with store.user_lock(USER_ID):
                with self.assertRaises(Exception):
                    store.save_profile_unlocked(USER_ID, {"userId": "22222222-2222-4222-8222-222222222222"})


if __name__ == "__main__":
    unittest.main()
