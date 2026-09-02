"""Tests for what the gateway is willing to accept.

The glasses render actions; they do not authorise them. Everything here
is about the gateway refusing things it did not itself offer, refusing
answers to a version of a task that has moved on, and never carrying out
the same request twice.
"""

import pytest

from stub_server.policy import Policy


def task(**over):
    base = {
        "id": "task-17",
        "revision": 4,
        "source": "Claude",
        "title": "Deploy production",
        "summary": "Deployment needs approval",
        "detail": "Waiting for your approval.",
        "needs_you": True,
        "actions": {
            "primary": {"id": "approve", "label": "Approve"},
            "secondary": {"id": "reject", "label": "Reject"},
        },
    }
    base.update(over)
    return base


@pytest.fixture
def policy():
    state = {"tasks": [task()]}
    p = Policy(provider=lambda: list(state["tasks"]))
    p.state = state  # so a test can change what the feeder reports
    return p


def action(**over):
    body = {
        "revision": 4,
        "type": "action",
        "action_id": "approve",
        "request_id": "req-1",
    }
    body.update(over)
    return body


# --- accepting --------------------------------------------------------


def test_an_offered_action_on_the_current_revision_is_accepted(policy):
    status, payload = policy.receive("task-17", action())

    assert status == 200
    assert payload["status"] == "accepted"


def test_the_secondary_action_is_offered_too(policy):
    status, _ = policy.receive("task-17", action(action_id="reject"))

    assert status == 200


def test_a_message_is_accepted(policy):
    status, payload = policy.receive(
        "task-17",
        {
            "revision": 4,
            "type": "message",
            "text": "Rerun the tests first.",
            "request_id": "req-m",
        },
    )

    assert status == 200
    assert payload["status"] == "accepted"


# --- refusing ---------------------------------------------------------


def test_an_action_this_gateway_never_offered_is_refused(policy):
    # The whole point of the check. An agent cannot put an executable
    # button on someone's face by naming one in a payload.
    status, payload = policy.receive("task-17", action(action_id="rm-rf"))

    assert status == 422
    assert "rm-rf" in payload["error"]


def test_an_answer_to_an_older_revision_is_refused(policy):
    status, payload = policy.receive("task-17", action(revision=3))

    assert status == 409
    assert payload["status"] == "stale"
    assert payload["revision"] == 4


def test_an_answer_to_a_newer_revision_is_also_refused(policy):
    # Not a thing an honest client does, so it is not a thing to guess at.
    assert policy.receive("task-17", action(revision=99))[0] == 409


def test_an_unknown_task_is_not_found(policy):
    assert policy.receive("nope", action())[0] == 404


@pytest.mark.parametrize(
    "body, reason",
    [
        ("not a dict", "body is not an object"),
        ({}, "no request id"),
        ({"request_id": ""}, "empty request id"),
        ({"request_id": "r", "revision": "4"}, "revision is a string"),
        ({"request_id": "r", "revision": True}, "revision is a bool"),
        ({"request_id": "r", "revision": 4}, "no type"),
        ({"request_id": "r", "revision": 4, "type": "shout"}, "unknown type"),
        ({"request_id": "r", "revision": 4, "type": "action"}, "no action id"),
        (
            {"request_id": "r", "revision": 4, "type": "message", "text": "  "},
            "empty message",
        ),
    ],
)
def test_a_body_that_makes_no_sense_is_refused_not_guessed_at(policy, body, reason):
    status, payload = policy.receive("task-17", body)

    assert status == 400, reason
    assert "error" in payload


def test_a_task_offering_nothing_accepts_nothing(policy):
    policy.state["tasks"] = [task(actions={})]

    assert policy.receive("task-17", action())[0] == 422


# --- doing it once ----------------------------------------------------


def test_the_same_request_twice_is_only_carried_out_once(policy):
    first = policy.receive("task-17", action())
    second = policy.receive("task-17", action())

    assert first[0] == second[0] == 200
    assert second[1]["replayed"] is True


def test_a_replay_gets_the_original_answer_even_after_the_task_moves_on(policy):
    policy.receive("task-17", action())
    # The task is now answered, so a fresh request quoting revision 4
    # would be stale. The replay must still get the original acceptance.
    fresh = policy.receive("task-17", action(request_id="req-2"))
    replay = policy.receive("task-17", action())

    assert fresh[0] == 409
    assert replay[0] == 200
    assert replay[1]["replayed"] is True


def test_two_different_requests_are_two_different_decisions(policy):
    policy.receive("task-17", action(request_id="req-a"))
    status, _ = policy.receive("task-17", action(request_id="req-b"))

    # The second is judged fresh, and by then the task has been answered.
    assert status == 409


def test_a_refusal_is_remembered_so_a_retry_gets_the_same_refusal(policy):
    first = policy.receive("task-17", action(action_id="rm-rf"))
    second = policy.receive("task-17", action(action_id="rm-rf"))

    assert first[0] == second[0] == 422
    assert second[1]["replayed"] is True


def test_the_memory_does_not_grow_without_bound(policy):
    from stub_server.policy import MAX_REMEMBERED

    for n in range(MAX_REMEMBERED + 50):
        policy.receive("task-17", action(request_id=f"req-{n}"))

    assert len(policy._handled) <= MAX_REMEMBERED


# --- what the glasses see afterwards ----------------------------------


def test_an_answered_task_stops_needing_you(policy):
    policy.receive("task-17", action())

    shown = policy.tasks()[0]

    assert shown["needs_you"] is False
    assert shown["actions"] == {}


def test_an_answered_task_gets_a_new_revision(policy):
    before = policy.tasks()[0]["revision"]

    policy.receive("task-17", action())

    assert policy.tasks()[0]["revision"] > before


def test_an_unanswered_task_passes_through_untouched(policy):
    assert policy.tasks()[0] == task()


def test_the_feeder_reporting_a_newer_version_wins_again(policy):
    # The underlying tool moved on by itself. The gateway's memory of
    # having answered the old version must not keep hiding the new one.
    policy.receive("task-17", action())
    policy.state["tasks"] = [task(revision=9, summary="needs approval again")]

    shown = policy.tasks()[0]

    assert shown["needs_you"] is True
    assert shown["revision"] == 9
