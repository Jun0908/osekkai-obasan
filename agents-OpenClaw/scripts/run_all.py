"""
run_all.py
OpenClaw の定期実行系スクリプトをまとめて順番に実行する。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

JOBS = [
    ("public-info-sync", ["scripts/public_info_sync.py"]),
    ("public-info-linker", ["scripts/public_info_linker.py"]),
    ("public-case-export", ["scripts/public_case_export.py"]),
    ("calendar-sync", ["scripts/calendar_sync.py"]),
    ("gmail-sync", ["scripts/email_manager.py"]),
    ("expense-append", ["scripts/expense_append.py"]),
    ("task-reminder", ["scripts/task_reminder.py"]),
    ("citizen-digest", ["scripts/citizen_digest.py"]),
    ("judgment-board", ["scripts/judgment_board.py"]),
    ("morning-brief", ["scripts/morning_brief.py"]),
]


def parse_args():
    parser = argparse.ArgumentParser(description="OpenClaw の定期実行系スクリプトをまとめて動かす")
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="どれか1つ失敗した時点で終了する",
    )
    return parser.parse_args()


def run_job(name: str, command: list[str]) -> int:
    print(f"[run_all] start: {name}")
    completed = subprocess.run(
        [PYTHON, *command],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if completed.returncode == 0:
        print(f"[run_all] ok: {name}")
    else:
        print(f"[run_all] failed: {name} (exit={completed.returncode})")
    return completed.returncode


def main():
    args = parse_args()
    failures: list[tuple[str, int]] = []

    for name, command in JOBS:
        returncode = run_job(name, command)
        if returncode == 0:
            continue

        failures.append((name, returncode))
        if args.fail_fast:
            break

    if failures:
        print("[run_all] summary: failed jobs detected")
        for name, returncode in failures:
            print(f"- {name}: exit={returncode}")
        raise SystemExit(1)

    print("[run_all] summary: all jobs completed")


if __name__ == "__main__":
    main()
