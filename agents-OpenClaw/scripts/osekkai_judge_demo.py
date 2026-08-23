"""Build the backend-independent Judge Demo artifact from a validated fixture."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from osekkai_contracts import validate_schema


AGENT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = AGENT_ROOT.parent
DEFAULT_SOURCE = AGENT_ROOT / "fixtures" / "osekkai" / "judge-demo-scenario.json"
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT
    / "frontend"
    / "lib"
    / "osekkai"
    / "judge-demo-scenario.generated.json"
)


def load_judge_demo_scenario(path: Path = DEFAULT_SOURCE) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_schema(value, "judge-demo-scenario.schema.json")
    return value


def validate_scenario_semantics(value: dict[str, Any]) -> None:
    events = value["events"]
    event_ids = {event["id"] for event in events}
    if len(event_ids) != len(events):
        raise ValueError("Judge Demo Event IDs must be unique")

    stories = value["stories"]
    if [story["storyNumber"] for story in stories] != [1, 2, 3]:
        raise ValueError("Judge Demo Story numbers must be ordered 1, 2, 3")
    kinds = {story["kind"] for story in stories}
    expected_kinds = {"preference_discovery", "respectful_hold", "continuity_followup"}
    if kinds != expected_kinds:
        raise ValueError("Judge Demo must cover discovery, respectful hold, and continuity")
    story_ids = {story["id"] for story in stories}
    if len(story_ids) != len(stories):
        raise ValueError("Judge Demo Story IDs must be unique")

    has_ranking_change = False
    for story in stories:
        step_ids: set[str] = set()
        prior_orders: list[list[str]] = []
        for step in story["steps"]:
            if step["id"] in step_ids:
                raise ValueError(f"Duplicate Step ID in Story {story['id']}")
            step_ids.add(step["id"])
            choice_ids: set[str] = set()
            for choice in step["choices"]:
                if choice["id"] in choice_ids:
                    raise ValueError(f"Duplicate Choice ID in Step {step['id']}")
                choice_ids.add(choice["id"])
                order = choice["eventOrder"]
                if any(event_id not in event_ids for event_id in order):
                    raise ValueError("Judge Demo eventOrder must reference known Events")
                if order and len(order) != 3:
                    raise ValueError("A visible Judge Demo shortlist must contain exactly 3 Events")
                if choice["selectFirstEvent"] and not prior_orders and not order:
                    raise ValueError("Selection requires an earlier or current Event shortlist")
                if order:
                    if any(previous != order for previous in prior_orders):
                        has_ranking_change = True
                    prior_orders.append(order)

        if story["kind"] == "respectful_hold":
            if any(
                choice["eventOrder"] or choice["selectFirstEvent"]
                for step in story["steps"]
                for choice in step["choices"]
            ):
                raise ValueError("Respectful-hold Story must not recommend or select an Event")

    if not has_ranking_change:
        raise ValueError("Judge Demo must demonstrate at least one ranking change")

    for event in events:
        route = event["route"]
        if route is not None and route["classification"] != "recorded_live":
            raise ValueError("Recorded routes must be classified as recorded_live")


def render_judge_demo_scenario(path: Path = DEFAULT_SOURCE) -> str:
    value = load_judge_demo_scenario(path)
    validate_scenario_semantics(value)
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def write_atomic(output: Path, content: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the static Osekkai Judge Demo artifact")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    content = render_judge_demo_scenario(args.source.resolve())
    output = args.output.resolve()
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != content:
            parser.error("generated Judge Demo artifact is stale")
        return 0
    write_atomic(output, content)
    print(f"Generated {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
