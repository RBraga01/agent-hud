"""Normative vectors exercised by production Raven navigation and feedback."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from agent_hud.decision_contract import (
    canonical_decision,
    correlated_status,
    current_observations,
    prepare_feedback,
)
from agent_hud.navigation import Event, Nav, Screen, advance, nav_for_tasks
from agent_hud.tasks import Action, Task

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads(
    (ROOT / "core/conformance/vectors/decision-lifecycle.json").read_text()
)


def as_task(raw):
    actions = [Action(a["action_id"], a["label"]) for a in raw["actions"]]
    return Task(
        id=raw["task_id"],
        revision=raw["revision"],
        source="Example",
        title="Example decision",
        summary="Example decision",
        detail="Example only",
        needs_you=True,
        primary=actions[0],
        secondary=actions[1] if len(actions) > 1 else None,
    )


def assert_trace(case, transmissions, status):
    assert transmissions == case["expected_transmissions"]
    unique = {d["decision_id"]: d for d in transmissions}
    assert list(unique.values()) == case["expected_decisions"]
    assert status == case["expected_result"]


def run_vector(case):
    tasks = [as_task(case["initial"])]
    nav = Nav(
        screen=Screen.ACTION_MENU, task_id=tasks[0].id, revision=tasks[0].revision
    )
    transmissions, outgoing, status = [], None, None
    allocated = 0

    def allocate():
        nonlocal allocated
        allocated += 1
        return f"{VECTORS['id_session']}:{allocated}"

    for event in case["events"]:
        kind = event["type"]
        if kind == "select":
            for action, selection in (
                (tasks[0].primary, Event.SELECT_PRIMARY),
                (tasks[0].secondary, Event.SELECT_SECONDARY),
            ):
                if action and action.id == event["action_id"]:
                    nav = advance(nav, selection, tasks)
        elif kind == "cancel":
            nav = advance(nav, Event.CANCEL, tasks)
        elif kind == "confirm":
            feedback = prepare_feedback(nav, tasks, allocate)
            if feedback:
                outgoing = feedback
                nav = advance(nav, Event.CONFIRM, tasks)
                transmissions.append(canonical_decision(feedback))
                status = None
        elif kind == "update":
            updated = as_task(event["task"])
            tasks = current_observations(tasks, [updated])
            nav = nav_for_tasks(nav, tasks)
        elif kind == "result" and outgoing:
            if status is None:
                status = correlated_status(
                    event["result"], canonical_decision(outgoing)
                )
        elif kind == "retry" and status == "ERROR":
            transmissions.append(canonical_decision(outgoing))
            status = None
    assert_trace(case, transmissions, status)
    return {"name": case["name"], "transmissions": transmissions, "result": status}


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda case: case["name"])
def test_normative_vector(case):
    run_vector(case)


def test_confirmation_rechecks_current_action_and_observed_revision():
    task = as_task(VECTORS["cases"][0]["initial"])
    nav = Nav(
        screen=Screen.CONFIRMATION,
        task_id=task.id,
        revision=task.revision,
        action_id="approve",
    )
    assert prepare_feedback(nav, [replace(task, revision=4)]) is None
    assert prepare_feedback(nav, [replace(task, primary=None)]) is None
    assert prepare_feedback(nav, []) is None


def test_write_conformance_report():
    source = ROOT / "core/conformance/vectors/decision-lifecycle.json"
    output = ROOT / "docs/m0-conformance-raven.json"
    report = {
        "contract_version": VECTORS["contract_version"],
        "vector_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "runtime": "Raven Python production navigation/confirmation",
        "cases": [run_vector(case) for case in VECTORS["cases"]],
    }
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
