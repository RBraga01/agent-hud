"""Tests for the stub gateway.

It asks its provider for the current list on every request, so whatever the
feeders return is what the glasses see, with nothing cached in between.
"""

import json
import threading

import pytest
import requests

from stub_server.server import TASKS_PATH, create_server

SAMPLE = [
    {"id": "a", "title": "One", "detail": "first", "needs_you": True},
    {"id": "b", "title": "Two", "detail": "second", "needs_you": False},
]


def serve(provider):
    """Start the gateway on a free port. Returns the base URL and a stopper."""
    server = create_server(provider, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    def stop():
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return f"http://127.0.0.1:{port}", stop


@pytest.fixture
def fixed_server():
    base, stop = serve(lambda: list(SAMPLE))
    yield base
    stop()


def test_serves_what_the_provider_returns(fixed_server):
    response = requests.get(f"{fixed_server}{TASKS_PATH}", timeout=5)

    assert response.status_code == 200
    assert response.json() == {"tasks": SAMPLE}


def test_says_it_is_json(fixed_server):
    response = requests.get(f"{fixed_server}{TASKS_PATH}", timeout=5)

    assert response.headers["Content-Type"].startswith("application/json")


def test_asks_again_on_every_request(fixed_server=None):
    # Nothing is cached: a second request must see a changed list.
    state = {"n": 0}

    def provider():
        state["n"] += 1
        return [
            {
                "id": "x",
                "title": "Counter",
                "detail": str(state["n"]),
                "needs_you": True,
            }
        ]

    base, stop = serve(provider)
    try:
        first = requests.get(f"{base}{TASKS_PATH}", timeout=5).json()
        second = requests.get(f"{base}{TASKS_PATH}", timeout=5).json()
    finally:
        stop()

    assert first["tasks"][0]["detail"] == "1"
    assert second["tasks"][0]["detail"] == "2"


def test_a_broken_feeder_does_not_take_the_gateway_down():
    def provider():
        raise RuntimeError("the feeder fell over")

    base, stop = serve(provider)
    try:
        response = requests.get(f"{base}{TASKS_PATH}", timeout=5)
        # And it is still answering afterwards.
        again = requests.get(f"{base}{TASKS_PATH}", timeout=5)
    finally:
        stop()

    assert response.status_code == 500
    assert again.status_code == 500


def test_an_empty_list_is_a_normal_answer():
    base, stop = serve(list)
    try:
        response = requests.get(f"{base}{TASKS_PATH}", timeout=5)
    finally:
        stop()

    assert response.status_code == 200
    assert response.json() == {"tasks": []}


def test_unknown_paths_are_not_found(fixed_server):
    response = requests.get(f"{fixed_server}/something-else", timeout=5)

    assert response.status_code == 404


def test_binds_only_to_the_loopback_address():
    # It serves whatever the feeders return with no authentication at all,
    # so it must never be reachable from a network.
    server = create_server(list, port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_the_response_is_valid_json_the_client_can_parse(fixed_server):
    raw = requests.get(f"{fixed_server}{TASKS_PATH}", timeout=5).text

    assert json.loads(raw)["tasks"][0]["title"] == "One"


# --- taking answers back ----------------------------------------------
#
# End to end: the real client talking to the real gateway. These are the
# tests that would catch the two failures that matter -- claiming
# something was sent when it was not, and doing it twice.


TASK = {
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


@pytest.fixture
def gateway():
    """A real gateway whose task list a test can change between calls."""
    from stub_server.server import create_server

    state = {"tasks": [dict(TASK)]}
    server = create_server(lambda: list(state["tasks"]), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    yield base, state

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _answer(base, **over):
    from agent_hud.feedback import Feedback, send_feedback

    fields = {
        "task_id": "task-17",
        "revision": 4,
        "action_id": "approve",
        "request_id": "req-1",
    }
    fields.update(over)
    return send_feedback(base, Feedback(**fields), timeout=3)


def test_an_offered_action_is_accepted_end_to_end(gateway):
    from agent_hud.feedback import SendOutcome

    base, _ = gateway

    assert _answer(base).outcome is SendOutcome.ACCEPTED


def test_an_action_the_gateway_never_offered_is_refused_end_to_end(gateway):
    from agent_hud.feedback import SendOutcome

    base, _ = gateway

    result = _answer(base, action_id="rm-rf")

    assert result.outcome is SendOutcome.REJECTED
    assert result.reason != ""


def test_answering_a_version_that_moved_on_reads_as_stale(gateway):
    from agent_hud.feedback import SendOutcome

    base, state = gateway
    state["tasks"] = [dict(TASK, revision=9)]

    assert _answer(base, revision=4).outcome is SendOutcome.STALE


def test_a_retry_with_the_same_id_does_not_answer_twice(gateway):
    from agent_hud.feedback import SendOutcome

    base, _ = gateway

    first = _answer(base)
    retry = _answer(base)

    assert first.outcome is SendOutcome.ACCEPTED
    assert retry.outcome is SendOutcome.ACCEPTED
    assert retry.fields.get("replayed") is True


def test_a_fresh_id_after_answering_is_refused_as_stale(gateway):
    from agent_hud.feedback import SendOutcome

    base, _ = gateway
    _answer(base)

    assert _answer(base, request_id="req-2").outcome is SendOutcome.STALE


def test_an_answered_task_comes_back_no_longer_needing_you(gateway):
    from agent_hud.client import fetch_tasks

    base, _ = gateway
    _answer(base)

    tasks = fetch_tasks(f"{base}/tasks").tasks

    assert tasks[0].needs_you is False
    assert tasks[0].has_actions is False
    assert tasks[0].revision == 5


def test_feedback_for_a_task_that_does_not_exist_is_refused(gateway):
    from agent_hud.feedback import SendOutcome

    base, _ = gateway

    assert _answer(base, task_id="nope").outcome is SendOutcome.REJECTED


def test_a_body_that_is_not_json_never_takes_the_gateway_down(gateway):
    import urllib.error
    import urllib.request

    base, _ = gateway
    req = urllib.request.Request(
        f"{base}/tasks/task-17/feedback",
        data=b"{ half written",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=3)
        status = 200
    except urllib.error.HTTPError as exc:
        status = exc.code

    assert status == 400
    # And it is still serving.
    from agent_hud.client import fetch_tasks

    assert fetch_tasks(f"{base}/tasks").ok is True


def test_posting_somewhere_else_is_not_found(gateway):
    import urllib.error
    import urllib.request

    base, _ = gateway
    req = urllib.request.Request(f"{base}/tasks", data=b"{}", method="POST")
    try:
        urllib.request.urlopen(req, timeout=3)
        status = 200
    except urllib.error.HTTPError as exc:
        status = exc.code

    assert status == 404


# --- the preferences it serves ----------------------------------------


def test_it_serves_the_wearers_preferences(gateway):
    from agent_hud.preferences import parse_preferences

    base, _ = gateway
    body = requests.get(f"{base}/settings", timeout=3).json()

    prefs, accepted = parse_preferences(body)

    assert accepted is True
    assert prefs.revision >= 1


def test_the_preferences_it_serves_never_ask_for_gaze_activation(gateway):
    from agent_hud.preferences import ACTIVATION_MODES

    base, _ = gateway
    body = requests.get(f"{base}/settings", timeout=3).json()

    assert body["interaction"]["mode"] in ACTIVATION_MODES
