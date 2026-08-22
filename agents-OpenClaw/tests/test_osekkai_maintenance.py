from __future__ import annotations

import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from helpers import NOW
from osekkai_maintenance import main, run_maintenance_cycle
from osekkai_profile import seed_demo_profile
from osekkai_store import JsonStore, LockTimeout


def _user_id(index: int) -> str:
    return f"30000000-0000-4000-8000-{index:012d}"


class MaintenanceWorkerTests(unittest.TestCase):
    def test_cli_uses_the_same_fail_closed_clock_as_demo_data(self):
        result = {"ok": True, "status": "complete"}
        with (
            patch("osekkai_maintenance.clock_now", return_value=NOW),
            patch("osekkai_maintenance.JsonStore", return_value=object()),
            patch("osekkai_maintenance.run_maintenance_cycle", return_value=result) as run,
            patch("builtins.print"),
        ):
            exit_code = main(["--json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(run.call_args.args[1], NOW)

    def test_one_worker_invocation_completes_multiple_batches(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            store.MAINTENANCE_BATCH_SIZE = 2
            for index in range(1, 6):
                user_id = _user_id(index)
                with store.user_lock(user_id):
                    store.save_profile_unlocked(user_id, seed_demo_profile(user_id, NOW))

            result = run_maintenance_cycle(store, NOW, 30)

            self.assertTrue(result["ok"])
            self.assertTrue(result["cycleCompleted"])
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["batchesRun"], 3)
            self.assertEqual(result["usersScanned"], 5)
            self.assertEqual(result["usersSkipped"], 0)

    def test_corrupt_namespace_is_reported_and_does_not_abort_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            corrupt_user = _user_id(1)
            valid_user = _user_id(2)
            (store.root / "profiles" / f"{corrupt_user}.json").write_text(
                "{not-json",
                encoding="utf-8",
            )
            with store.user_lock(valid_user):
                store.save_profile_unlocked(valid_user, seed_demo_profile(valid_user, NOW))

            result = run_maintenance_cycle(store, NOW, 30)

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "complete_with_skips")
            self.assertTrue(result["cycleCompleted"])
            self.assertEqual(result["usersScanned"], 1)
            self.assertEqual(result["usersSkipped"], 1)
            self.assertEqual(
                result["skippedNamespaces"],
                [{"userId": corrupt_user, "reason": "corrupt_or_unreadable"}],
            )

    def test_busy_user_lock_is_reported_while_other_namespaces_continue(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            busy_user = _user_id(1)
            valid_user = _user_id(2)
            for user_id in (busy_user, valid_user):
                with store.user_lock(user_id):
                    store.save_profile_unlocked(user_id, seed_demo_profile(user_id, NOW))

            original_user_lock = store.user_lock

            @contextmanager
            def selective_user_lock(user_id: str, timeout: float | None = None):
                if user_id == busy_user:
                    raise LockTimeout("simulated concurrent writer")
                with original_user_lock(user_id, timeout=timeout):
                    yield

            store.user_lock = selective_user_lock  # type: ignore[method-assign]
            result = run_maintenance_cycle(store, NOW, 30)

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "complete_with_skips")
            self.assertEqual(result["usersScanned"], 1)
            self.assertEqual(result["usersSkipped"], 1)
            self.assertEqual(
                result["skippedNamespaces"],
                [{"userId": busy_user, "reason": "lock_busy"}],
            )

    def test_force_starts_a_new_finite_cycle_inside_the_daily_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(directory)
            user_id = _user_id(1)
            with store.user_lock(user_id):
                store.save_profile_unlocked(user_id, seed_demo_profile(user_id, NOW))

            first = run_maintenance_cycle(store, NOW, 30)
            not_due = run_maintenance_cycle(store, NOW, 30)
            forced = run_maintenance_cycle(store, NOW, 30, force=True)

            self.assertEqual(first["status"], "complete")
            self.assertEqual(not_due["status"], "not_due")
            self.assertEqual(not_due["batchesRun"], 0)
            self.assertEqual(forced["status"], "complete")
            self.assertEqual(forced["batchesRun"], 1)

    def test_worker_has_a_hard_batch_limit_if_cursor_cannot_advance(self):
        class StalledStore:
            MAINTENANCE_BATCH_SIZE = 10

            def __init__(self):
                self.calls = 0

            @staticmethod
            def list_user_ids():
                return [_user_id(1)]

            def cleanup_all_if_due(self, now, retention_days, *, force=False):
                self.calls += 1
                return {
                    "ran": True,
                    "busy": False,
                    "cycleCompleted": False,
                    "usersScanned": 0,
                    "usersSkipped": 0,
                    "skippedNamespaces": [],
                    "removed": {},
                }

        store = StalledStore()
        result = run_maintenance_cycle(store, NOW, 30)  # type: ignore[arg-type]

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "batch_limit_reached")
        self.assertEqual(store.calls, 2)


if __name__ == "__main__":
    unittest.main()
