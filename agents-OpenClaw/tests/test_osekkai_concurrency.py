from __future__ import annotations

import multiprocessing
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import NOW, SCRIPTS, USER_ID
from osekkai_profile import seed_demo_profile
from osekkai_store import JsonStore


def _increment_worker(root: str, index: int) -> None:
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    store = JsonStore(root, lock_timeout=20)

    def operation():
        profile = store.load_profile_unlocked(USER_ID)
        profile["rejectionStreak"] += 1
        store.save_profile_unlocked(USER_ID, profile)
        return profile["rejectionStreak"]

    store.execute_idempotent(USER_ID, "test-increment", f"increment-{index:08d}", NOW, operation)


class ConcurrencyTests(unittest.TestCase):
    def test_cross_process_updates_have_no_lost_update(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            with store.user_lock(USER_ID):
                store.save_profile_unlocked(USER_ID, seed_demo_profile(USER_ID, NOW))
            context = multiprocessing.get_context("spawn")
            processes = [context.Process(target=_increment_worker, args=(directory, index)) for index in range(6)]
            for process in processes:
                process.start()
            for process in processes:
                process.join(30)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(store.load_profile(USER_ID)["rejectionStreak"], 6)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    unittest.main()
