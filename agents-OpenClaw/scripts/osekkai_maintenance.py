"""Run a complete, bounded retention-maintenance cycle.

This command is intended for an external daily scheduler.  It does not depend
on browser/API traffic, and it keeps invoking the store's bounded batch sweep
until the current cursor reaches the end of the discovered namespaces.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from typing import Any

from osekkai_profile import clock_now
from osekkai_store import JsonStore, StorageError


MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 365


def run_maintenance_cycle(
    store: JsonStore,
    now: datetime,
    retention_days: int = 30,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Advance every batch in one bounded worker invocation.

    ``cleanup_all_if_due`` deliberately processes only a small batch so normal
    API requests stay fast.  The dedicated worker may process all remaining
    batches, but still uses a hard upper bound derived from the namespace count
    observed at startup.  Namespaces created during a pass are picked up by the
    next scheduled cycle.
    """

    if (
        isinstance(retention_days, bool)
        or not MIN_RETENTION_DAYS <= retention_days <= MAX_RETENTION_DAYS
    ):
        raise ValueError(
            f"retention_days must be between {MIN_RETENTION_DAYS} and {MAX_RETENTION_DAYS}"
        )

    initial_user_count = len(store.list_user_ids())
    max_batches = max(1, math.ceil(initial_user_count / store.MAINTENANCE_BATCH_SIZE) + 1)
    totals = {
        "conversations": 0,
        "evidence": 0,
        "episodesUpdated": 0,
        "idempotencyEntries": 0,
    }
    summary: dict[str, Any] = {
        "ok": True,
        "status": "complete",
        "retentionDays": retention_days,
        "startedAt": now.isoformat(),
        "batchesRun": 0,
        "usersScanned": 0,
        "usersSkipped": 0,
        "skippedNamespaces": [],
        "removed": totals,
        "cycleCompleted": False,
    }

    for batch_index in range(max_batches):
        result = store.cleanup_all_if_due(
            now,
            retention_days,
            force=force and batch_index == 0,
        )
        if result.get("busy"):
            summary["status"] = "maintenance_lock_busy"
            summary["skippedNamespaces"].append(
                {"userId": None, "reason": "maintenance_lock_busy"}
            )
            return summary
        if not result.get("ran"):
            summary["status"] = "not_due"
            summary["cycleCompleted"] = bool(result.get("cycleCompleted"))
            return summary

        summary["batchesRun"] += 1
        summary["usersScanned"] += int(result.get("usersScanned", 0))
        summary["usersSkipped"] += int(result.get("usersSkipped", 0))
        skipped = result.get("skippedNamespaces", [])
        if isinstance(skipped, list):
            summary["skippedNamespaces"].extend(skipped)
        removed = result.get("removed", {})
        if isinstance(removed, dict):
            for key in totals:
                value = removed.get(key, 0)
                if isinstance(value, int) and not isinstance(value, bool):
                    totals[key] += value

        if result.get("cycleCompleted"):
            summary["cycleCompleted"] = True
            summary["status"] = "complete_with_skips" if summary["usersSkipped"] else "complete"
            return summary

    summary["ok"] = False
    summary["status"] = "batch_limit_reached"
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one complete おっせかいおばさん retention cycle.",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="Conversation and inferred-evidence retention period (1-365; default: 30).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Start/resume a cycle even when the previous cycle completed within 24 hours.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write one machine-readable JSON result to stdout.",
    )
    return parser


def _print_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return
    if not result.get("ok"):
        print(
            "retention maintenance: "
            f"status={result.get('status', 'maintenance_failed')} "
            f"message={result.get('message', 'maintenance did not complete')}"
        )
        return
    print(
        "retention maintenance: "
        f"status={result['status']} "
        f"batches={result['batchesRun']} "
        f"scanned={result['usersScanned']} "
        f"skipped={result['usersSkipped']}"
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        now = clock_now()
        result = run_maintenance_cycle(
            JsonStore(),
            now,
            args.retention_days,
            force=args.force,
        )
    except (OSError, StorageError, ValueError) as exc:
        result = {
            "ok": False,
            "status": "maintenance_failed",
            "message": str(exc),
        }
        _print_result(result, args.json)
        return 1

    _print_result(result, args.json)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
