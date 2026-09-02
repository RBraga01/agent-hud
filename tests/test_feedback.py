"""Tests for sending an answer back to the gateway.

This is the only part of the app that transmits anything, so it is the
part with the most ways to be wrong. Two failures matter more than the
rest, and most of these tests exist to rule them out:

* Saying something was sent when it was not. A wearer who trusts "Sent"
  and walks away, while nothing happened, is worse off than one who was
  told plainly that it failed.
* Doing something twice. A retry after an uncertain network must not
  approve a deployment a second time.

Like the fetch tests, these run real servers rather than mocking the
network, so the thing under test is actually exercised.
"""

import json
import threading
from dataclasses import FrozenInstanceError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agent_hud.feedback import (
    Feedback,
    SendOutcome,
    new_request_id,
    send_feedback,
)


def _serve(handler_class):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_address[1]}", server, thread


def _answering(status: int, body: dict | None = None, capture: list | None = None):
    """A server that answers every POST the same way."""

    class Fixed(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            if capture is not None:
                capture.append((self.path, json.loads(raw.decode())))
            payload = json.dumps(body or {}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    return Fixed


def _send(handler, feedback=None, **kw):
    base, server, thread = _serve(handler)
    try:
        return send_feedback(
            base, feedback or FEEDBACK, timeout=kw.pop("timeout", 2), **kw
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


FEEDBACK = Feedback(
    task_id="task-17",
    revision=4,
    action_id="approve",
    request_id="req-abc",
)


# --- the request itself -----------------------------------------------


def test_a_request_id_is_unique_every_time():
    ids = {new_request_id() for _ in range(200)}

    assert len(ids) == 200


def test_a_request_id_gives_nothing_away():
    # It travels to the gateway, so it must say nothing about the wearer,
    # the machine, or what they are doing.
    import getpass
    import socket

    blob = " ".join(new_request_id() for _ in range(20)).lower()

    for personal in (getpass.getuser().lower(), socket.gethostname().lower()):
        if personal:
            assert personal not in blob


def test_the_feedback_is_immutable():
    with pytest.raises(FrozenInstanceError):
        FEEDBACK.action_id = "reject"


def test_the_body_carries_exactly_what_the_gateway_needs():
    seen = []

    _send(_answering(200, {"status": "accepted"}, capture=seen))

    path, body = seen[0]
    assert path == "/tasks/task-17/feedback"
    assert body == {
        "revision": 4,
        "type": "action",
        "action_id": "approve",
        "request_id": "req-abc",
    }


def test_nothing_about_the_machine_is_sent():
    # The gateway maps the task id to whatever session it belongs to. The
    # glasses never learn or send a path, a session id or a credential.
    seen = []

    _send(_answering(200, {"status": "accepted"}, capture=seen))

    blob = json.dumps(seen[0][1]).lower()
    for leak in ("/", "\\", "token", "key", "secret", "session"):
        assert leak not in blob


def test_a_message_is_sent_as_a_message_not_an_action():
    seen = []
    note = Feedback(
        task_id="task-17",
        revision=4,
        text="Rerun the tests and deploy only if they pass.",
        request_id="req-xyz",
    )

    _send(_answering(200, {"status": "accepted"}, capture=seen), feedback=note)

    _, body = seen[0]
    assert body["type"] == "message"
    assert body["text"] == "Rerun the tests and deploy only if they pass."
    assert "action_id" not in body


# --- the three outcomes -----------------------------------------------


def test_a_gateway_that_accepts_reports_accepted():
    result = _send(_answering(200, {"status": "accepted"}))

    assert result.outcome is SendOutcome.ACCEPTED
    assert result.request_id == "req-abc"


def test_a_stale_revision_is_its_own_outcome():
    # Not a failure to send. The gateway heard it and refused, because the
    # task moved on. The wearer has to read it again, not retry blindly.
    result = _send(_answering(409, {"status": "stale"}))

    assert result.outcome is SendOutcome.STALE
    assert result.reason != ""


def test_an_action_the_gateway_will_not_accept_is_rejected():
    result = _send(_answering(422, {"error": "unknown action"}))

    assert result.outcome is SendOutcome.REJECTED


def test_a_malformed_request_is_rejected_not_retried():
    result = _send(_answering(400, {"error": "bad body"}))

    assert result.outcome is SendOutcome.REJECTED


@pytest.mark.parametrize("status", [500, 502, 503])
def test_a_broken_gateway_is_unreachable_so_it_can_be_retried(status):
    result = _send(_answering(status, {"error": "boom"}))

    assert result.outcome is SendOutcome.UNREACHABLE


def test_nothing_listening_is_unreachable():
    result = send_feedback("http://127.0.0.1:9", FEEDBACK, timeout=1)

    assert result.outcome is SendOutcome.UNREACHABLE
    assert result.reason != ""


def test_an_unreadable_answer_is_still_a_clear_outcome():
    class Garbage(BaseHTTPRequestHandler):
        def do_POST(self):
            body = b"<html>not json</html>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    result = _send(Garbage)

    # It answered 200, so it took the request. Anything else would be
    # claiming a failure that may not have happened.
    assert result.outcome is SendOutcome.ACCEPTED


def test_a_server_that_hangs_up_mid_answer_never_raises():
    class Rude(BaseHTTPRequestHandler):
        def do_POST(self):
            self.wfile.close()

        def log_message(self, *args):
            pass

    result = _send(Rude)

    assert result.outcome is SendOutcome.UNREACHABLE


def test_the_result_is_immutable():
    result = send_feedback("http://127.0.0.1:9", FEEDBACK, timeout=1)

    with pytest.raises(FrozenInstanceError):
        result.outcome = SendOutcome.ACCEPTED


# --- retries -----------------------------------------------------------


def test_a_retry_reuses_the_same_request_id():
    # The whole point. If the first attempt did reach the gateway and only
    # the answer was lost, the second must be recognised as the same
    # request rather than approving anything twice.
    seen = []
    handler = _answering(200, {"status": "accepted"}, capture=seen)

    _send(handler)
    _send(handler)

    assert [body["request_id"] for _, body in seen] == ["req-abc", "req-abc"]


def test_the_outcome_carries_the_id_back_so_a_retry_can_use_it():
    result = _send(_answering(500, {"error": "boom"}))

    assert result.request_id == "req-abc"


# --- bounds ------------------------------------------------------------


def test_an_oversized_answer_is_refused_rather_than_read():
    from agent_hud.feedback import MAX_RESPONSE_BYTES

    big = json.dumps({"pad": "x" * (MAX_RESPONSE_BYTES + 1000)}).encode()

    class Huge(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(big)))
            self.end_headers()
            self.wfile.write(big)

        def log_message(self, *args):
            pass

    result = _send(Huge)

    assert result.outcome is SendOutcome.UNREACHABLE


def test_message_text_is_capped_before_it_leaves():
    from agent_hud.feedback import MAX_TEXT

    seen = []
    note = Feedback(
        task_id="t", revision=1, text="x" * 5000, request_id="r"
    )

    _send(_answering(200, {}, capture=seen), feedback=note)

    assert len(seen[0][1]["text"]) == MAX_TEXT


def test_a_feedback_with_neither_an_action_nor_text_is_refused_locally():
    # Never bother the gateway with something that cannot mean anything.
    empty = Feedback(task_id="t", revision=1, request_id="r")

    result = send_feedback("http://127.0.0.1:9", empty, timeout=1)

    assert result.outcome is SendOutcome.REJECTED
    assert "nothing to send" in result.reason.lower()
