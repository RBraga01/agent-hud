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


# --- audio, and the drafts it makes -----------------------------------


@pytest.fixture
def hearing_gateway():
    """A gateway with an engine that hears whatever the test says."""
    from stub_server.server import create_server
    from stub_server.transcription import Transcript

    state = {"tasks": [dict(TASK)], "heard": "rerun the tests"}

    class Fake:
        name = "fake"
        available = True

        def transcribe(self, audio, *, language="auto"):
            return Transcript(text=state["heard"], ok=True)

    server = create_server(lambda: list(state["tasks"]), port=0)
    server.transcriber = Fake()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    yield base, state, server

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _wav():
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 1600)
    return buffer.getvalue()


def _post_audio(base, task_id="task-17", audio=None):
    return requests.post(
        f"{base}/tasks/{task_id}/audio",
        data=_wav() if audio is None else audio,
        headers={"Content-Type": "audio/wav"},
        timeout=5,
    )


def test_with_no_engine_the_gateway_says_audio_is_off(gateway):
    base, _ = gateway
    settings = _get(base, "/settings").json()

    assert settings["audio_available"] is False
    assert settings["audio_engine"] == "none"


def test_with_no_engine_a_recording_is_refused_with_a_reason(gateway):
    base, _ = gateway

    response = _post_audio(base)

    assert response.status_code == 422
    assert "engine" in response.json()["error"].lower()


def test_a_recording_becomes_a_draft(hearing_gateway):
    base, _, _ = hearing_gateway

    body = _post_audio(base).json()

    assert body["text"] == "rerun the tests"
    assert body["task_id"] == "task-17"
    assert body["revision"] == 4
    assert body["draft_id"]


def test_the_draft_carries_the_revision_it_was_dictated_against(hearing_gateway):
    # So a task that moved on refuses it, exactly as an action would be.
    base, state, _ = hearing_gateway
    state["tasks"] = [dict(TASK, revision=9)]

    assert _post_audio(base).json()["revision"] == 9


def test_a_draft_shows_up_in_the_pending_list(hearing_gateway):
    base, _, _ = hearing_gateway
    _post_audio(base)

    drafts = _get(base, "/drafts").json()["drafts"]

    assert len(drafts) == 1
    assert drafts[0]["text"] == "rerun the tests"


def test_a_draft_can_be_edited_from_somewhere_more_comfortable(hearing_gateway):
    base, _, _ = hearing_gateway
    draft_id = _post_audio(base).json()["draft_id"]

    response = requests.post(
        f"{base}/drafts/{draft_id}/edit",
        json={"text": "rerun the tests and deploy only if they pass"},
        timeout=5,
    )

    assert response.status_code == 200
    assert "deploy only if they pass" in response.json()["text"]


def test_an_empty_edit_is_refused(hearing_gateway):
    base, _, _ = hearing_gateway
    draft_id = _post_audio(base).json()["draft_id"]

    response = requests.post(
        f"{base}/drafts/{draft_id}/edit", json={"text": "   "}, timeout=5
    )

    assert response.status_code == 400


def test_discarding_takes_the_words_with_it(hearing_gateway):
    base, _, _ = hearing_gateway
    draft_id = _post_audio(base).json()["draft_id"]

    requests.post(f"{base}/drafts/{draft_id}/discard", timeout=5)

    assert _get(base, "/drafts").json()["drafts"] == []


def test_sending_a_draft_goes_through_the_same_door_an_action_does(
    hearing_gateway,
):
    base, _, _ = hearing_gateway
    draft_id = _post_audio(base).json()["draft_id"]

    response = requests.post(
        f"{base}/drafts/{draft_id}/send",
        json={"request_id": "req-draft-1"},
        timeout=5,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert _get(base, "/drafts").json()["drafts"] == []


def test_a_draft_written_against_a_task_that_moved_on_is_refused(
    hearing_gateway,
):
    base, state, _ = hearing_gateway
    draft_id = _post_audio(base).json()["draft_id"]
    state["tasks"] = [dict(TASK, revision=99)]

    response = requests.post(
        f"{base}/drafts/{draft_id}/send",
        json={"request_id": "req-draft-2"},
        timeout=5,
    )

    assert response.status_code == 409


def test_sending_the_same_draft_twice_only_acts_once(hearing_gateway):
    base, _, _ = hearing_gateway
    draft_id = _post_audio(base).json()["draft_id"]
    body = {"request_id": "req-draft-3"}

    first = requests.post(f"{base}/drafts/{draft_id}/send", json=body, timeout=5)
    # The draft is gone now, so a repeat cannot even find it -- which is
    # the same protection arriving one step earlier.
    second = requests.post(f"{base}/drafts/{draft_id}/send", json=body, timeout=5)

    assert first.status_code == 200
    assert second.status_code == 404


def test_a_recording_for_a_task_that_does_not_exist_is_refused(hearing_gateway):
    base, _, _ = hearing_gateway

    assert _post_audio(base, task_id="nope").status_code == 404


def test_something_that_is_not_a_recording_is_refused(hearing_gateway):
    base, _, _ = hearing_gateway

    response = _post_audio(base, audio=b'{"not": "audio"}')

    assert response.status_code == 422


def test_an_oversized_recording_is_refused(hearing_gateway):
    """It is turned away, whether by an answer or by the door shutting.

    The gateway refuses on the declared length before reading the body,
    which is the right way round: it should not pull megabytes into
    memory to decide it does not want them. A client mid-upload sees the
    connection close rather than a status line, and either way the
    recording was not accepted.
    """
    from stub_server.transcription import MAX_AUDIO_BYTES

    base, _, _ = hearing_gateway
    oversized = b"RIFF" + b"\x00" * (MAX_AUDIO_BYTES + 2048)

    try:
        status = _post_audio(base, audio=oversized).status_code
    except requests.RequestException:
        status = 413  # refused before it would finish listening

    assert status in (413, 422)
    # And the gateway is still there, serving.
    assert _get(base, "/tasks").status_code == 200


def test_acting_on_a_draft_that_is_gone_is_not_found(hearing_gateway):
    base, _, _ = hearing_gateway

    assert requests.post(f"{base}/drafts/nope/discard", timeout=5).status_code == 404


# --- the lock, when it is on ------------------------------------------


@pytest.fixture
def locked_gateway(tmp_path):
    """A gateway that asks for a passkey before it says anything."""
    from stub_server.server import create_server

    server = create_server(
        lambda: [dict(TASK)],
        port=0,
        require_auth=True,
        auth_path=tmp_path / "passkeys.json",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    yield base, server

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_the_lock_is_off_by_default(gateway):
    base, _ = gateway

    assert _get(base, "/auth/state").json()["required"] is False
    assert _get(base, "/tasks").status_code == 200


@pytest.mark.parametrize(
    "path", ["/tasks", "/settings", "/drafts"]
)
def test_with_the_lock_on_nothing_of_yours_is_readable(locked_gateway, path):
    base, _ = locked_gateway

    response = _get(base, path)

    assert response.status_code == 401


def test_with_the_lock_on_nothing_can_be_answered(locked_gateway):
    base, _ = locked_gateway

    response = requests.post(
        f"{base}/tasks/task-17/feedback",
        json={"revision": 4, "type": "action", "action_id": "approve",
              "request_id": "r"},
        timeout=5,
    )

    assert response.status_code == 401


def test_the_sign_in_page_itself_stays_reachable(locked_gateway):
    # Otherwise there would be no way in.
    base, _ = locked_gateway

    assert _get(base, "/control/").status_code == 200
    assert _get(base, "/control/control.js").status_code == 200
    assert _get(base, "/auth/state").status_code == 200


def test_the_state_endpoint_says_what_is_needed(locked_gateway):
    """Including whether this gateway can check a passkey at all.

    A gateway that demands one it cannot verify has to say so, or the
    Control would show a sign-in button that could never work.
    """
    from stub_server.auth import library_available

    base, _ = locked_gateway

    state = _get(base, "/auth/state").json()

    assert state["required"] is True
    assert state["signed_in"] is False
    assert state["registered"] is False
    assert state["available"] is library_available()


def test_an_invented_session_cookie_does_not_get_in(locked_gateway):
    base, _ = locked_gateway

    response = requests.get(
        f"{base}/tasks",
        headers={"Cookie": "agent_hud_session=invented"},
        timeout=5,
    )

    assert response.status_code == 401


def test_a_real_session_gets_in(locked_gateway):
    # The ceremony itself is the library's; this checks that a session it
    # produced is what the gate actually honours.
    base, server = locked_gateway
    token = server.auth.open_session()

    response = requests.get(
        f"{base}/tasks",
        headers={"Cookie": f"agent_hud_session={token}"},
        timeout=5,
    )

    assert response.status_code == 200


def test_signing_out_stops_it_getting_in_again(locked_gateway):
    base, server = locked_gateway
    token = server.auth.open_session()
    cookie = {"Cookie": f"agent_hud_session={token}"}

    requests.post(f"{base}/auth/logout", headers=cookie, timeout=5)

    assert requests.get(f"{base}/tasks", headers=cookie, timeout=5).status_code == 401


def test_the_session_cookie_cannot_be_read_by_a_script(locked_gateway):
    base, _ = locked_gateway

    response = requests.post(f"{base}/auth/logout", timeout=5)
    cookie = response.headers.get("Set-Cookie", "")

    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie


def test_adding_a_second_passkey_needs_a_recent_sign_in(locked_gateway):
    """Somebody who picks up an unlocked phone must not be able to quietly
    add their own key."""
    base, server = locked_gateway
    from stub_server.auth import Credential

    server.auth.add(
        Credential(
            credential_id="existing", public_key="k", sign_count=0,
            name="phone", created_at=0.0,
        )
    )

    # No session at all.
    assert _get(base, "/auth/register/options").status_code == 403

    # A session that signed in long ago.
    token = server.auth.open_session(now=0.0)
    stale = requests.get(
        f"{base}/auth/register/options",
        headers={"Cookie": f"agent_hud_session={token}"},
        timeout=5,
    )
    assert stale.status_code in (401, 403)


def test_the_first_passkey_can_be_registered_without_one(locked_gateway):
    # There has to be a way to set the first device up.
    from stub_server.auth import library_available

    base, _ = locked_gateway

    response = _get(base, "/auth/register/options")

    if library_available():
        assert response.status_code == 200
        assert response.json()["challenge"]
    else:
        assert response.status_code == 501


def test_a_ceremony_that_does_not_check_out_says_only_no(locked_gateway):
    """It refuses, and says nothing about why.

    With the library absent it answers 501 and names the package to
    install, which is a different thing from refusing a bad passkey and is
    the honest answer to "I was asked to check something I cannot check".
    """
    from stub_server.auth import library_available

    base, _ = locked_gateway

    response = requests.post(
        f"{base}/auth/login",
        json={"credential": {"id": "made-up"}},
        timeout=5,
    )

    expected = (400, 401) if library_available() else (501,)
    assert response.status_code in expected
    # Nothing about why, beyond that it did not.
    assert "traceback" not in response.text.lower()
