"""Tests for the V2 task contract.

The gateway sends a list of tasks. This module is what the glasses trust,
so it is deliberately strict: anything that does not match the contract
exactly is dropped rather than guessed at. A malformed entry must never
be able to crash the display or silently distort the count.

A task carries more than the V1 item did — where it came from, a one-line
summary for the list, the full text for the detail view, a revision so a
stale view cannot be acted on, and the actions the gateway is willing to
accept for it.
"""

from dataclasses import FrozenInstanceError

import pytest

from agent_hud.tasks import (
    MAX_DETAIL,
    MAX_LABEL,
    MAX_SUMMARY,
    MAX_TASKS,
    MAX_TITLE,
    Action,
    Task,
    needs_you_count,
    parse_tasks,
)

TASK = {
    "id": "task-17",
    "revision": 4,
    "source": "Claude",
    "title": "Deploy production",
    "summary": "Deployment needs approval",
    "detail": "Validation completed. 47 tests passed. Production deployment "
    "is waiting for your approval.",
    "needs_you": True,
    "actions": {
        "primary": {"id": "approve", "label": "Approve"},
        "secondary": {"id": "reject", "label": "Reject"},
    },
}

VALID = {"tasks": [TASK]}


def _task(**over):
    return {"tasks": [dict(TASK, **over)]}


# --- the happy path ---------------------------------------------------


def test_parses_a_v2_task():
    result = parse_tasks(VALID)

    assert result.valid is True
    task = result.tasks[0]
    assert task.id == "task-17"
    assert task.revision == 4
    assert task.source == "Claude"
    assert task.title == "Deploy production"
    assert task.summary == "Deployment needs approval"
    assert task.needs_you is True
    assert task.primary == Action(id="approve", label="Approve")
    assert task.secondary == Action(id="reject", label="Reject")


def test_preserves_the_order_the_gateway_sent():
    payload = {
        "tasks": [dict(TASK, id="a"), dict(TASK, id="b"), dict(TASK, id="c")]
    }

    assert [t.id for t in parse_tasks(payload).tasks] == ["a", "b", "c"]


def test_tasks_are_immutable_so_the_display_cannot_corrupt_them():
    task = parse_tasks(VALID).tasks[0]

    with pytest.raises(FrozenInstanceError):
        task.title = "changed"


def test_counts_only_the_tasks_that_need_you():
    payload = {
        "tasks": [
            dict(TASK, id="a", needs_you=True),
            dict(TASK, id="b", needs_you=False),
            dict(TASK, id="c", needs_you=True),
        ]
    }

    assert needs_you_count(parse_tasks(payload).tasks) == 2


# --- actions ----------------------------------------------------------


def test_a_task_may_have_no_actions():
    task = parse_tasks(_task(actions={})).tasks[0]

    assert task.primary is None
    assert task.secondary is None
    assert task.has_actions is False


def test_a_missing_actions_key_is_the_same_as_none():
    raw = {k: v for k, v in TASK.items() if k != "actions"}
    task = parse_tasks({"tasks": [raw]}).tasks[0]

    assert task.has_actions is False


def test_only_a_secondary_leaves_the_primary_slot_empty():
    # Spec: if only one dynamic action exists the unused slot stays empty.
    # The HUD never shuffles an action into a position the gateway did not
    # put it in, because the position is what the wearer aims at.
    task = parse_tasks(
        _task(actions={"secondary": {"id": "reject", "label": "Reject"}})
    ).tasks[0]

    assert task.primary is None
    assert task.secondary == Action(id="reject", label="Reject")
    assert task.has_actions is True


def test_a_malformed_action_is_dropped_but_the_task_survives():
    # The HUD never invents actions. A broken one simply is not offered.
    # Dropping the whole task instead would hide work from you.
    result = parse_tasks(_task(actions={"primary": {"id": "approve"}}))

    assert len(result.tasks) == 1
    assert result.tasks[0].primary is None
    assert result.dropped == 0
    assert result.truncated == 1


def test_an_action_that_is_not_a_dict_is_dropped():
    result = parse_tasks(_task(actions={"primary": "approve"}))

    assert result.tasks[0].primary is None
    assert result.truncated == 1


def test_an_actions_block_that_is_not_a_dict_leaves_both_slots_empty():
    result = parse_tasks(_task(actions=["approve", "reject"]))

    assert result.tasks[0].has_actions is False
    assert result.truncated == 1


# --- strictness -------------------------------------------------------


@pytest.mark.parametrize(
    "over, reason",
    [
        ({"id": ""}, "empty id"),
        ({"id": 17}, "id is not text"),
        ({"source": ""}, "empty source"),
        ({"title": ""}, "empty title"),
        ({"summary": ""}, "empty summary"),
        ({"detail": None}, "detail is not text"),
        ({"needs_you": "true"}, "needs_you is a string"),
        ({"needs_you": 1}, "needs_you is an int, not a bool"),
        ({"revision": "4"}, "revision is a string"),
        ({"revision": True}, "revision is a bool, not a number"),
        ({"revision": -1}, "revision is negative"),
    ],
)
def test_drops_tasks_that_do_not_match_the_contract(over, reason):
    result = parse_tasks(_task(**over))

    assert result.tasks == [], reason
    assert result.dropped == 1
    assert result.valid is True


def test_a_task_without_a_revision_is_dropped():
    # Revision protection is not optional. Without it there is no way to
    # tell that the thing on screen still matches the thing on the gateway.
    raw = {k: v for k, v in TASK.items() if k != "revision"}
    result = parse_tasks({"tasks": [raw]})

    assert result.tasks == []
    assert result.dropped == 1


def test_keeps_good_tasks_when_a_bad_one_sits_between_them():
    payload = {
        "tasks": [dict(TASK, id="a"), {"nonsense": True}, dict(TASK, id="c")]
    }

    result = parse_tasks(payload)

    assert [t.id for t in result.tasks] == ["a", "c"]
    assert result.dropped == 1


def test_allows_an_empty_detail_because_some_tasks_have_nothing_to_add():
    task = parse_tasks(_task(detail="")).tasks[0]

    assert task.detail == ""


def test_ignores_extra_fields_the_gateway_might_add_later():
    task = parse_tasks(_task(future_field="ignored")).tasks[0]

    assert task.id == "task-17"


# --- telling "empty" apart from "broken" ------------------------------
#
# The single most important distinction in this project. A display showing
# nothing must mean nothing needs you, never that the gateway is talking
# nonsense.


def test_a_valid_payload_with_no_tasks_is_valid():
    result = parse_tasks({"tasks": []})

    assert result.valid is True
    assert result.tasks == []
    assert result.dropped == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"something_broke": True},
        {"tasks": "not a list"},
        {"tasks": 42},
        "garbage",
        None,
        [],
        123,
    ],
)
def test_a_payload_that_is_not_a_task_list_is_invalid(payload):
    result = parse_tasks(payload)

    assert result.valid is False
    assert result.tasks == []


def test_a_payload_of_entirely_bad_tasks_is_still_a_valid_payload():
    # The gateway spoke the right language; its contents were wrong. That
    # is a different failure from an unreachable or nonsensical gateway.
    result = parse_tasks({"tasks": [{"nope": 1}, {"nope": 2}]})

    assert result.valid is True
    assert result.tasks == []
    assert result.dropped == 2


# --- caps -------------------------------------------------------------


def test_keeps_at_most_the_task_limit_and_counts_the_rest_as_dropped():
    payload = {"tasks": [dict(TASK, id=f"t{n}") for n in range(MAX_TASKS + 15)]}

    result = parse_tasks(payload)

    assert len(result.tasks) == MAX_TASKS
    assert result.dropped == 15
    assert result.tasks[0].id == "t0"


def test_long_detail_is_cut_and_marks_the_payload_incomplete():
    result = parse_tasks(_task(detail="d" * 5000))

    assert len(result.tasks[0].detail) == MAX_DETAIL
    assert result.tasks[0].detail.endswith("...")
    assert result.truncated == 1


def test_a_long_title_and_summary_are_cut():
    result = parse_tasks(_task(title="T" * 300, summary="S" * 300))

    assert len(result.tasks[0].title) == MAX_TITLE
    assert len(result.tasks[0].summary) == MAX_SUMMARY
    assert result.truncated == 1


def test_a_long_action_label_is_cut():
    result = parse_tasks(
        _task(actions={"primary": {"id": "approve", "label": "A" * 50}})
    )

    assert len(result.tasks[0].primary.label) == MAX_LABEL
    assert result.tasks[0].primary.id == "approve"
    assert result.truncated == 1


def test_text_within_the_limits_is_left_alone():
    result = parse_tasks(VALID)

    assert result.truncated == 0
    assert result.tasks[0].detail == TASK["detail"]


def test_one_truncated_task_among_several_is_counted_once():
    payload = {
        "tasks": [
            dict(TASK, id="a"),
            dict(TASK, id="b", detail="d" * 5000, title="T" * 300),
            dict(TASK, id="c"),
        ]
    }

    result = parse_tasks(payload)

    assert len(result.tasks) == 3
    assert result.truncated == 1


def test_a_task_is_a_plain_frozen_dataclass():
    # Nothing here should need the framework or a network to build.
    task = Task(
        id="t",
        revision=1,
        source="Codex",
        title="Title",
        summary="Summary",
        detail="",
        needs_you=False,
    )

    assert task.has_actions is False
    assert task.needs_you is False
