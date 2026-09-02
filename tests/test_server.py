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


# --- the Control it serves --------------------------------------------


def _get(base, path):
    return requests.get(f"{base}{path}", timeout=3)


def test_the_control_page_is_served(gateway):
    base, _ = gateway

    response = _get(base, "/control/")

    assert response.status_code == 200
    assert "Agent HUD Control" in response.text
    assert response.headers["Content-Type"].startswith("text/html")


def test_the_root_leads_to_the_control(gateway):
    base, _ = gateway

    assert _get(base, "/").status_code == 200


def test_the_control_script_and_manifest_are_served(gateway):
    base, _ = gateway

    assert _get(base, "/control/control.js").status_code == 200
    assert _get(base, "/control/manifest.webmanifest").status_code == 200


def test_the_control_is_told_to_talk_to_nothing_else(gateway):
    # Said out loud so a browser enforces it even if the page is ever
    # changed by mistake.
    base, _ = gateway

    policy = _get(base, "/control/").headers["Content-Security-Policy"]

    assert "default-src 'self'" in policy
    assert "connect-src 'self'" in policy


@pytest.mark.parametrize(
    "path",
    [
        "/control/../pyproject.toml",
        "/control/..%2fpyproject.toml",
        "/control/../../etc/passwd",
        "/control/agents.json",
        "/control/server.py",
        "/control/nope.html",
    ],
)
def test_nothing_outside_the_control_folder_can_be_reached(gateway, path):
    base, _ = gateway

    assert _get(base, path).status_code == 404


def test_the_settings_response_tells_the_control_what_it_shows(gateway):
    base, _ = gateway
    body = _get(base, "/settings").json()

    assert "gateway_name" in body
    assert "sources" in body
    assert "device_last_seen" in body


def test_asking_for_the_task_list_counts_as_the_device_being_around(gateway):
    from agent_hud.client import fetch_tasks

    base, _ = gateway
    assert _get(base, "/settings").json()["device_last_seen"] is None

    fetch_tasks(f"{base}/tasks")

    assert _get(base, "/settings").json()["device_last_seen"] is not None


# --- it cannot be exposed by accident ---------------------------------


def test_it_binds_only_to_loopback():
    """The gateway has no authentication at all.

    That is defensible while it is only reachable from the machine it
    runs on, and indefensible the moment it is not. The address is not a
    parameter, so there is no way to get this wrong by passing the wrong
    argument.
    """
    from stub_server.server import LOOPBACK_HOST, create_server

    server = create_server(lambda: [], port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert LOOPBACK_HOST == "127.0.0.1"
    finally:
        server.server_close()


def test_there_is_no_way_to_ask_it_to_listen_elsewhere():
    import inspect

    from stub_server.server import create_server

    parameters = set(inspect.signature(create_server).parameters)

    assert "host" not in parameters
    assert "address" not in parameters
    assert "bind" not in parameters
