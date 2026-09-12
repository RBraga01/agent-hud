"""Tests for the stub gateway.

It asks its provider for the current list on every request, so whatever the
feeders return is what the glasses see, with nothing cached in between.
"""

import importlib.util
import json
import threading

import pytest
import requests

from stub_server.server import TASKS_PATH, create_server

# The self-signed certificate needs cryptography, which is a gateway extra.
# Without it the off-loopback TLS tests skip rather than error.
requires_crypto = pytest.mark.skipif(
    importlib.util.find_spec("cryptography") is None,
    reason="cryptography is not installed (pip install -e '.[gateway]')",
)

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


def test_it_binds_loopback_by_default():
    import inspect

    from stub_server.net import LOOPBACK_HOST
    from stub_server.server import create_server

    host_param = inspect.signature(create_server).parameters["host"]
    assert host_param.default == LOOPBACK_HOST


def test_it_refuses_to_bind_off_loopback_without_the_lock():
    from stub_server.server import create_server

    with pytest.raises(ValueError, match="authentication"):
        create_server(list, port=0, host="0.0.0.0")


def test_it_refuses_to_bind_off_loopback_with_the_lock_but_no_tls(tmp_path):
    """Auth alone is not enough once it is a network surface: without a
    certificate the connection would be in the clear."""
    from stub_server.server import create_server

    with pytest.raises(ValueError, match="TLS"):
        create_server(list, port=0, host="0.0.0.0", require_auth=True)


@requires_crypto
def test_it_will_bind_off_loopback_with_the_lock_and_tls(tmp_path):
    from stub_server.server import create_server
    from stub_server.tls import ensure_cert, server_context

    info = ensure_cert(store_dir=tmp_path, hosts=["0.0.0.0"])
    server = create_server(
        list,
        port=0,
        host="0.0.0.0",
        require_auth=True,
        ssl_context=server_context(info),
    )
    try:
        assert server.server_address[0] == "0.0.0.0"
        assert server.scheme == "https"
    finally:
        server.server_close()


def test_a_lan_address_it_cannot_bind_still_gets_the_lock_check_first():
    """The auth check happens before the bind, so a bad host with the lock
    off is refused for the right reason, not a socket error."""
    from stub_server.server import create_server

    with pytest.raises(ValueError, match="authentication"):
        create_server(list, port=0, host="10.255.255.1")


# --- TLS, end to end -------------------------------------------------------


def _serve_tls(provider, *, ssl_context):
    """A locked, TLS-wrapped gateway on a free port. Bound to loopback so
    the test can reach it; the wrapping is what is under test."""
    from stub_server.server import create_server

    server = create_server(
        provider,
        port=0,
        host="127.0.0.1",
        require_auth=True,
        ssl_context=ssl_context,
    )
    # A client that rejects the pin aborts mid-handshake; that is the
    # test passing, not a server fault, so do not let it print a stack.
    server.handle_error = lambda request, client_address: None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    def stop():
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return f"https://127.0.0.1:{port}", stop


@requires_crypto
def test_a_client_pinned_to_the_fingerprint_reaches_the_gateway(tmp_path):
    from agent_hud.tls import session_for
    from stub_server.tls import ensure_cert, server_context

    info = ensure_cert(store_dir=tmp_path)
    base, stop = _serve_tls(lambda: list(SAMPLE), ssl_context=server_context(info))
    try:
        session = session_for(fingerprint=info.fingerprint)
        reply = session.get(f"{base}/auth/state", timeout=5)
        assert reply.status_code == 200
        assert reply.json()["required"] is True
    finally:
        stop()


@requires_crypto
def test_the_wrong_fingerprint_is_refused(tmp_path):
    from agent_hud.tls import session_for
    from stub_server.tls import ensure_cert, server_context

    info = ensure_cert(store_dir=tmp_path)
    base, stop = _serve_tls(lambda: list(SAMPLE), ssl_context=server_context(info))
    try:
        wrong = "AA:" * 31 + "AA"
        session = session_for(fingerprint=wrong)
        with pytest.raises(requests.exceptions.SSLError):
            session.get(f"{base}/auth/state", timeout=5)
    finally:
        stop()


@requires_crypto
def test_an_unpinned_client_will_not_trust_the_self_signed_certificate(tmp_path):
    from stub_server.tls import ensure_cert, server_context

    info = ensure_cert(store_dir=tmp_path)
    base, stop = _serve_tls(lambda: list(SAMPLE), ssl_context=server_context(info))
    try:
        with pytest.raises(requests.exceptions.SSLError):
            requests.get(f"{base}/auth/state", timeout=5)
    finally:
        stop()


@requires_crypto
def test_bring_your_own_certificate_is_trusted_by_its_ca_file(tmp_path):
    """A certificate the test made itself, handed to the gateway as BYO
    and to the client as the CA to verify against."""
    from agent_hud.tls import session_for
    from stub_server.tls import ensure_cert, server_context

    made = ensure_cert(store_dir=tmp_path)  # self-signed: it is its own CA
    info = ensure_cert(
        cert_path=made.certfile, key_path=made.keyfile, store_dir=tmp_path
    )
    assert info.self_signed is False
    base, stop = _serve_tls(lambda: list(SAMPLE), ssl_context=server_context(info))
    try:
        session = session_for(ca=str(made.certfile))
        reply = session.get(f"{base}/auth/state", timeout=5)
        assert reply.status_code == 200
    finally:
        stop()


@requires_crypto
def test_a_stalled_handshake_does_not_freeze_the_gateway_for_everyone_else(
    tmp_path,
):
    """The handshake happens per connection, in its own worker thread --
    not in the single accept loop -- so a client that opens a connection
    and never sends a byte of TLS must not stop anyone else from
    connecting."""
    import socket

    from agent_hud.tls import session_for
    from stub_server.tls import ensure_cert, server_context

    info = ensure_cert(store_dir=tmp_path)
    base, stop = _serve_tls(lambda: list(SAMPLE), ssl_context=server_context(info))
    try:
        host, port = base.removeprefix("https://").split(":")
        stalled = socket.create_connection((host, int(port)), timeout=5)
        try:
            session = session_for(fingerprint=info.fingerprint)
            reply = session.get(f"{base}/auth/state", timeout=5)
            assert reply.status_code == 200
        finally:
            stalled.close()
    finally:
        stop()


# --- one noisy client cannot swamp it -----------------------------------


def _serve_limited(provider=None, **limits):
    """A gateway on a free port with limits a test can make tiny."""
    from stub_server.server import create_server

    server = create_server(provider or (lambda: list(SAMPLE)), port=0, **limits)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def stop():
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return f"http://127.0.0.1:{server.server_address[1]}", server, stop


def _pair_post(base, headers=None):
    return requests.post(
        f"{base}/auth/devices/pair", json={"name": "x"},
        headers=headers or {}, timeout=5,
    )


def test_writes_are_rate_limited_per_client():
    base, _, stop = _serve_limited(write_rate=1.0, write_burst=2)
    try:
        codes = [_pair_post(base).status_code for _ in range(4)]
        assert codes[:2] == [200, 200]
        assert codes[2] == 429
        # and it says how it is meant to be handled
        again = _pair_post(base)
        assert again.status_code == 429
        assert again.headers.get("Retry-After") == "1"
    finally:
        stop()


def test_reads_are_never_rate_limited():
    base, _, stop = _serve_limited(write_rate=1.0, write_burst=1)
    try:
        codes = [
            requests.get(f"{base}{TASKS_PATH}", timeout=5).status_code
            for _ in range(15)
        ]
        assert codes == [200] * 15
    finally:
        stop()


def test_each_paired_device_has_its_own_write_budget():
    """A recognized device's budget is its own -- keyed on a token the
    gateway actually issued, not merely one a caller presents."""
    base, server, stop = _serve_limited(write_rate=1.0, write_burst=2)
    try:
        _, token_a = server.auth.pair_device("device-a")
        _, token_b = server.auth.pair_device("device-b")
        a = {"X-Agent-Hud-Device": token_a}
        b = {"X-Agent-Hud-Device": token_b}

        assert [_pair_post(base, a).status_code for _ in range(3)] == [
            200, 200, 429,
        ]
        # b's bucket is untouched by a's spending
        assert _pair_post(base, b).status_code == 200
    finally:
        stop()


def test_an_unrecognized_device_header_does_not_grant_a_fresh_budget():
    """A caller cannot reset its rate limit by inventing a new device
    header on every request. Only a token the gateway issued gets its
    own bucket; anything else -- including a flood of distinct,
    never-paired values -- shares the peer address's budget."""
    base, _, stop = _serve_limited(write_rate=1.0, write_burst=2)
    try:
        # Spend the address bucket's burst with no header at all.
        assert [_pair_post(base).status_code for _ in range(2)] == [200, 200]

        # A flood of distinct, invented device headers from the same
        # address gets nothing extra: every one lands on that same,
        # already-spent bucket.
        codes = [
            _pair_post(base, {"X-Agent-Hud-Device": f"invented-{i}"}).status_code
            for i in range(10)
        ]
        assert codes == [429] * 10
    finally:
        stop()


def test_too_many_connections_at_once_are_refused():
    import threading as _t

    holding = _t.Event()
    release = _t.Event()

    def slow_provider():
        holding.set()
        release.wait(3)
        return list(SAMPLE)

    base, _, stop = _serve_limited(slow_provider, max_connections=1)
    try:
        first = _t.Thread(
            target=lambda: requests.get(f"{base}{TASKS_PATH}", timeout=5),
            daemon=True,
        )
        first.start()
        assert holding.wait(3)  # the one slot is now taken

        with pytest.raises(requests.exceptions.ConnectionError):
            requests.get(f"{base}{TASKS_PATH}", timeout=5)

        release.set()
        first.join(timeout=5)
    finally:
        release.set()
        stop()


def test_a_body_that_never_arrives_is_cut_off():
    import socket

    base, _, stop = _serve_limited(request_timeout=0.5)
    try:
        host, port = base.removeprefix("http://").split(":")
        conn = socket.create_connection((host, int(port)), timeout=3)
        conn.sendall(
            b"POST /auth/devices/pair HTTP/1.1\r\n"
            b"Host: x\r\nContent-Length: 400\r\n\r\n"
            b'{"name": "'  # ... and then nothing
        )
        conn.settimeout(3)
        # The server must not hang waiting for the rest: within its
        # timeout it either answers 400 or closes the connection.
        data = conn.recv(4096)
        conn.close()
        assert data == b"" or b" 400 " in data
    finally:
        stop()


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


def test_the_session_cookie_is_not_marked_secure_over_plain_http(locked_gateway):
    # Marking it Secure over http would be a lie the browser could not
    # act on usefully, and would suggest a guarantee that is not there.
    base, _ = locked_gateway

    response = requests.post(f"{base}/auth/logout", timeout=5)

    assert "Secure" not in response.headers.get("Set-Cookie", "")


@requires_crypto
def test_the_session_cookie_is_marked_secure_over_https(tmp_path):
    from agent_hud.tls import session_for
    from stub_server.tls import ensure_cert, server_context

    info = ensure_cert(store_dir=tmp_path)
    base, stop = _serve_tls(lambda: [], ssl_context=server_context(info))
    try:
        session = session_for(fingerprint=info.fingerprint)
        response = session.post(f"{base}/auth/logout", timeout=5)

        assert "Secure" in response.headers.get("Set-Cookie", "")
    finally:
        stop()


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


# --- pairing the glasses ----------------------------------------------
#
# The glasses cannot do a passkey ceremony: no browser, no sensor to
# prove anything with. Without a way to pair them, turning the lock on
# would lock them out of their own gateway -- which is exactly what it
# did before this existed.


def _pair(base, name="Raven Prism"):
    return requests.post(f"{base}/auth/devices/pair", json={"name": name}, timeout=5)


def test_locking_the_gateway_used_to_lock_the_glasses_out(locked_gateway):
    """The bug this closes, kept as a test so it cannot come back."""
    from agent_hud.client import fetch_tasks

    base, _ = locked_gateway

    assert fetch_tasks(f"{base}/tasks", timeout=3).ok is False


def test_a_paired_device_gets_in(locked_gateway):
    from agent_hud.client import fetch_tasks

    base, _ = locked_gateway
    token = _pair(base).json()["token"]

    result = fetch_tasks(f"{base}/tasks", timeout=3, device_token=token)

    assert result.ok is True


def test_a_paired_device_can_answer_too(locked_gateway):
    from agent_hud.feedback import Feedback, SendOutcome, send_feedback

    base, _ = locked_gateway
    token = _pair(base).json()["token"]

    result = send_feedback(
        base,
        Feedback(task_id="task-17", revision=4, action_id="approve",
                 request_id="req-paired"),
        timeout=3,
        device_token=token,
    )

    assert result.outcome is SendOutcome.ACCEPTED


def test_an_invented_token_does_not_get_in(locked_gateway):
    from agent_hud.client import fetch_tasks

    base, _ = locked_gateway
    _pair(base)

    assert fetch_tasks(f"{base}/tasks", timeout=3, device_token="made-up").ok is False


def test_the_token_is_shown_once_and_never_stored(locked_gateway):
    """Only its hash is kept, so a copy of the credential file is not a
    way in."""
    base, server = locked_gateway

    token = _pair(base).json()["token"]

    assert token
    stored = next(iter(server.auth.devices.values()))
    assert token not in stored.token_hash
    assert stored.token_hash != token
    # And nothing anywhere else hands it back.
    listed = _get(base, "/auth/devices").json()["devices"]
    assert "token" not in listed[0]
    assert token not in _get(base, "/auth/devices").text


def test_a_revoked_device_stops_getting_in(locked_gateway):
    from agent_hud.client import fetch_tasks

    base, _ = locked_gateway
    paired = _pair(base).json()
    token = paired["token"]
    assert fetch_tasks(f"{base}/tasks", timeout=3, device_token=token).ok is True

    requests.post(
        f"{base}/auth/devices/revoke/{paired['device_id']}", timeout=5
    )

    assert fetch_tasks(f"{base}/tasks", timeout=3, device_token=token).ok is False


def test_a_paired_device_is_listed_without_its_token(locked_gateway):
    base, _ = locked_gateway
    _pair(base, name="My glasses")

    devices = _get(base, "/auth/devices").json()["devices"]

    assert devices[0]["name"] == "My glasses"
    assert set(devices[0]) == {"device_id", "name", "created_at", "last_seen"}


def test_using_a_device_records_that_it_was_around(locked_gateway):
    from agent_hud.client import fetch_tasks

    base, _ = locked_gateway
    token = _pair(base).json()["token"]
    assert _get(base, "/auth/devices").json()["devices"][0]["last_seen"] is None

    fetch_tasks(f"{base}/tasks", timeout=3, device_token=token)

    assert _get(base, "/auth/devices").json()["devices"][0]["last_seen"] is not None


def test_pairing_needs_a_recent_sign_in_once_a_passkey_exists(locked_gateway):
    """Somebody who picks up an unlocked phone must not be able to pair
    their own glasses to your gateway."""
    from stub_server.auth import Credential

    base, server = locked_gateway
    server.auth.add(
        Credential(credential_id="existing", public_key="k", sign_count=0,
                   name="phone", created_at=0.0)
    )

    assert _pair(base).status_code == 403

    stale = server.auth.open_session(now=0.0)
    response = requests.post(
        f"{base}/auth/devices/pair",
        json={"name": "theirs"},
        headers={"Cookie": f"agent_hud_session={stale}"},
        timeout=5,
    )
    assert response.status_code == 403


def test_revoking_needs_a_recent_sign_in_too(locked_gateway):
    from stub_server.auth import Credential

    base, server = locked_gateway
    paired = _pair(base).json()
    server.auth.add(
        Credential(credential_id="existing", public_key="k", sign_count=0,
                   name="phone", created_at=0.0)
    )

    response = requests.post(
        f"{base}/auth/devices/revoke/{paired['device_id']}", timeout=5
    )

    assert response.status_code == 403


def test_an_unlocked_gateway_does_not_ask_for_any_of_this(gateway):
    # Pairing is what makes locking usable; it is not a thing to make
    # somebody do before they have locked anything.
    from agent_hud.client import fetch_tasks

    base, _ = gateway

    assert fetch_tasks(f"{base}/tasks", timeout=3).ok is True
    assert _pair(base).status_code == 200


# --- changing settings from the Control --------------------------------
#
# The glasses read their settings from the gateway and never write them,
# so until now nothing could change them at all: the Control could show
# the wearer's choices but not alter one. Per-control activation is the
# first setting anybody actually needs to change from a phone.


SETTINGS_PATH = "/settings"


def _put_settings(base, payload):
    return requests.post(f"{base}{SETTINGS_PATH}", json=payload, timeout=3)


def test_settings_can_be_changed(gateway):
    base, _ = gateway

    response = _put_settings(base, {"interaction": {"mode": "dwell"}})

    assert response.status_code == 200
    assert _get(base, SETTINGS_PATH).json()["interaction"]["mode"] == "dwell"


def test_changing_settings_moves_the_revision_on(gateway):
    """The glasses ignore a payload quoting a revision they have already
    passed, so a change nobody numbered is a change nobody applies."""
    base, _ = gateway
    before = _get(base, SETTINGS_PATH).json()["revision"]

    _put_settings(base, {"interaction": {"mode": "dwell"}})

    assert _get(base, SETTINGS_PATH).json()["revision"] > before


def test_one_control_can_be_set_apart(gateway):
    base, _ = gateway

    _put_settings(
        base,
        {"interaction": {"mode": "dwell", "controls": {"confirm": "double_blink"}}},
    )

    served = _get(base, SETTINGS_PATH).json()
    assert served["interaction"]["controls"] == {"confirm": "double_blink"}


def test_settings_not_mentioned_are_left_alone(gateway):
    """A Control that only knows about some settings must not wipe the
    rest by omitting them."""
    base, _ = gateway
    _put_settings(base, {"audio": {"language": "pt-PT"}})

    _put_settings(base, {"interaction": {"mode": "dwell"}})

    served = _get(base, SETTINGS_PATH).json()
    assert served["audio"]["language"] == "pt-PT"
    assert served["interaction"]["mode"] == "dwell"


def test_gaze_cannot_be_set_as_an_activation(gateway):
    """Not a validation nicety: it is the rule the whole design rests on."""
    base, _ = gateway

    _put_settings(
        base,
        {"interaction": {"mode": "gaze", "controls": {"confirm": "gaze"}}},
    )

    served = _get(base, SETTINGS_PATH).json()
    assert served["interaction"]["mode"] != "gaze"
    assert "confirm" not in served["interaction"]["controls"]


def test_an_invented_control_is_refused(gateway):
    base, _ = gateway

    _put_settings(base, {"interaction": {"controls": {"open_the_pod_bay": "dwell"}}})

    served = _get(base, SETTINGS_PATH).json()
    assert "open_the_pod_bay" not in served["interaction"]["controls"]


def test_rubbish_does_not_take_the_gateway_down(gateway):
    base, _ = gateway

    for junk in ("not json", "[]", '{"interaction": 7}', "null"):
        response = requests.post(
            f"{base}{SETTINGS_PATH}",
            data=junk,
            headers={"Content-Type": "application/json"},
            timeout=3,
        )
        assert response.status_code in (200, 400), junk

    assert _get(base, SETTINGS_PATH).status_code == 200


def test_the_control_page_offers_every_control(gateway):
    """The page and the glasses must agree on the list of controls. If
    they drift, the Control offers settings the glasses ignore."""
    from agent_hud.preferences import CONTROL_ROLES

    base, _ = gateway
    page = _get(base, "/control/control.js").text

    for role in CONTROL_ROLES:
        assert f'"{role}"' in page, f"the Control never offers {role!r}"


def test_the_control_page_does_not_offer_gaze(gateway):
    base, _ = gateway
    page = _get(base, "/control/control.js").text
    assert '"gaze"' not in page


def test_setting_one_control_from_the_control_page(gateway):
    """The round trip the page actually performs: send only the controls
    map, and expect everything else to survive."""
    base, _ = gateway
    _put_settings(base, {"audio": {"language": "pt-PT"}})

    response = _put_settings(
        base, {"interaction": {"controls": {"confirm": "double_blink"}}}
    )

    assert response.status_code == 200
    served = response.json()
    assert served["interaction"]["controls"] == {"confirm": "double_blink"}
    assert served["audio"]["language"] == "pt-PT"


def test_a_control_can_be_put_back_under_the_main_setting(gateway):
    base, _ = gateway
    _put_settings(base, {"interaction": {"controls": {"confirm": "dwell"}}})

    _put_settings(base, {"interaction": {"controls": {}}})

    assert _get(base, SETTINGS_PATH).json()["interaction"]["controls"] == {}


def test_control_files_are_served_without_being_cached(gateway):
    """A browser that cached an old build must not be stranded on it after
    the gateway is restarted with new files. It is a localhost dev
    gateway; revalidating every load costs nothing."""
    base, _ = gateway

    for name in ("", "control.js", "index.html"):
        response = _get(base, f"/control/{name}")
        assert response.status_code == 200
        cache = response.headers.get("Cache-Control", "")
        assert "no-cache" in cache or "no-store" in cache, (
            f"/control/{name} was served as cacheable: {cache!r}"
        )


# --- the event-shaped gateway ---------------------------------------------
#
# Instead of running every feeder inside every GET, the gateway keeps its
# own view: a background sweep for the polled sources, and POST /events for
# a source that knows the moment something changed.


@pytest.fixture
def event_gateway():
    """A gateway backed by a TaskStore, with no background sweep running
    (the tests drive the store directly)."""
    from stub_server.server import create_server
    from stub_server.store import TaskStore

    store = TaskStore()
    store.replace("poll", [dict(TASK)])
    server = create_server(store.snapshot, port=0, store=store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    yield base, store

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_get_tasks_is_served_from_the_store(event_gateway):
    base, store = event_gateway

    got = requests.get(f"{base}{TASKS_PATH}", timeout=5).json()["tasks"]
    assert [t["id"] for t in got] == [TASK["id"]]

    store.replace("poll", [{"id": "fresh", "revision": 1, "needs_you": True}])
    got = requests.get(f"{base}{TASKS_PATH}", timeout=5).json()["tasks"]
    assert [t["id"] for t in got] == ["fresh"]


def test_get_tasks_carries_the_store_version_as_a_header(event_gateway):
    base, store = event_gateway

    r = requests.get(f"{base}{TASKS_PATH}", timeout=5)
    assert r.headers["X-Tasks-Version"] == str(store.version)

    store.replace("push:x", [{"id": "e1", "revision": 1}])
    r = requests.get(f"{base}{TASKS_PATH}", timeout=5)
    assert r.headers["X-Tasks-Version"] == str(store.version)


def test_a_pushed_slice_shows_up_immediately(event_gateway):
    base, store = event_gateway

    r = requests.post(
        f"{base}/events",
        json={
            "source": "claude_hook",
            "tasks": [{"id": "ch-1", "revision": 2, "needs_you": True,
                       "source": "Claude", "title": "iPS"}],
        },
        timeout=5,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 1 and body["changed"] is True
    assert body["version"] == store.version

    got = requests.get(f"{base}{TASKS_PATH}", timeout=5).json()["tasks"]
    assert "ch-1" in {t["id"] for t in got}


def test_pushing_the_same_slice_again_reports_no_change(event_gateway):
    base, _ = event_gateway
    payload = {"source": "codex", "tasks": [{"id": "cx-1", "revision": 1}]}

    requests.post(f"{base}/events", json=payload, timeout=5)
    again = requests.post(f"{base}/events", json=payload, timeout=5).json()

    assert again["changed"] is False


def test_a_push_replaces_only_its_own_source(event_gateway):
    base, store = event_gateway
    store.replace("poll", [{"id": "p", "revision": 1}])

    requests.post(
        f"{base}/events",
        json={"source": "github", "tasks": [{"id": "g", "revision": 1}]},
        timeout=5,
    )

    got = requests.get(f"{base}{TASKS_PATH}", timeout=5).json()["tasks"]
    assert {t["id"] for t in got} == {"p", "g"}


def test_events_needs_a_source(event_gateway):
    base, _ = event_gateway
    r = requests.post(f"{base}/events", json={"tasks": []}, timeout=5)
    assert r.status_code == 400


def test_events_rejects_tasks_that_are_not_a_list_of_objects(event_gateway):
    base, _ = event_gateway
    for bad in ({"source": "x", "tasks": "nope"},
                {"source": "x", "tasks": [1, 2]},
                {"source": "x", "tasks": [{"id": "ok"}, "bad"]}):
        r = requests.post(f"{base}/events", json=bad, timeout=5)
        assert r.status_code == 400, bad


def test_events_rejects_a_non_json_body(event_gateway):
    base, _ = event_gateway
    r = requests.post(
        f"{base}/events", data="not json",
        headers={"Content-Type": "application/json"}, timeout=5,
    )
    assert r.status_code == 400


def test_a_provider_only_gateway_refuses_events(gateway):
    base, _ = gateway
    r = requests.post(
        f"{base}/events", json={"source": "x", "tasks": []}, timeout=5
    )
    assert r.status_code == 404


def test_a_provider_only_gateway_sends_no_version_header(gateway):
    base, _ = gateway
    r = requests.get(f"{base}{TASKS_PATH}", timeout=5)
    assert "X-Tasks-Version" not in r.headers
