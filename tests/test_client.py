"""Tests for fetching from the gateway.

The display must survive anything the network does. Every failure here
has to come back as an empty list with a reason attached, never as an
exception, because an exception on the glasses means a blank display.

These tests run real servers rather than mocking the network, so the
thing under test is actually exercised.
"""

import json
import threading
import time
from dataclasses import FrozenInstanceError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agent_hud.client import MAX_RESPONSE_BYTES, fetch_tasks
from agent_hud.tasks import MAX_TITLE
from stub_server.server import TASKS_PATH, create_server


def _task(**over):
    base = {
        "id": "a",
        "revision": 1,
        "source": "Claude",
        "title": "One",
        "summary": "first",
        "detail": "the first one",
        "needs_you": True,
    }
    base.update(over)
    return base


SAMPLE = {"tasks": [_task(id="a"), _task(id="b", needs_you=False)]}


def _serve(handler_class):
    """Run an arbitrary handler on a free loopback port. Returns the base URL."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    return f"http://127.0.0.1:{port}", server, thread


@pytest.fixture
def stub_url():
    """The real gateway, serving a list the test can change between calls."""
    state = {"tasks": list(SAMPLE["tasks"]), "fail": False}

    def provider():
        if state["fail"]:
            raise RuntimeError("feeder down")
        return state["tasks"]

    server = create_server(provider, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    yield f"http://127.0.0.1:{port}{TASKS_PATH}", state

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_fetches_and_parses_from_a_real_server(stub_url):
    url, _ = stub_url

    result = fetch_tasks(url)

    assert result.ok is True
    assert result.reason == ""
    assert [task.id for task in result.tasks] == ["a", "b"]


def test_reports_failure_when_nothing_is_listening():
    # Port 9 is the discard service and is virtually never bound locally.
    result = fetch_tasks("http://127.0.0.1:9/tasks", timeout=1)

    assert result.ok is False
    assert result.tasks == []
    assert result.reason != ""


def test_reports_failure_when_the_server_errors(stub_url):
    url, state = stub_url
    state["fail"] = True

    result = fetch_tasks(url)

    assert result.ok is False
    assert result.tasks == []
    assert "500" in result.reason


def test_reports_failure_when_the_body_is_not_json():
    class Garbage(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<html>not json at all</html>"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    base, server, thread = _serve(Garbage)
    try:
        result = fetch_tasks(f"{base}/tasks")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.ok is False
    assert result.tasks == []
    assert result.reason != ""


def test_reports_failure_when_the_server_is_too_slow():
    class Slow(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(3)

        def log_message(self, *args):
            pass

    base, server, thread = _serve(Slow)
    try:
        result = fetch_tasks(f"{base}/tasks", timeout=0.2)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.ok is False
    assert result.tasks == []
    assert result.reason != ""


def test_a_valid_response_with_malformed_entries_still_succeeds(stub_url):
    # A broken entry is the gateway's problem, not a network failure.
    # The good entries must still reach the display.
    url, state = stub_url
    state["tasks"] = [
        _task(id="a"),
        {"id": "broken", "title": "No revision", "needs_you": True},
    ]

    result = fetch_tasks(url)

    assert result.ok is True
    assert [task.id for task in result.tasks] == ["a"]


def test_an_empty_but_valid_response_succeeds(stub_url):
    url, state = stub_url
    state["tasks"] = []

    result = fetch_tasks(url)

    assert result.ok is True
    assert result.tasks == []


def test_the_result_is_immutable():
    result = fetch_tasks("http://127.0.0.1:9/tasks", timeout=1)

    with pytest.raises(FrozenInstanceError):
        result.ok = True


# --- telling "empty" apart from "broken" ------------------------------


def test_a_gateway_talking_nonsense_is_a_failure():
    # It answers, with valid JSON, something that is not a list of items.
    # Reporting that as "nothing needs you" is the worst thing this can do.
    class Nonsense(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"something_broke": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    base, server, thread = _serve(Nonsense)
    try:
        result = fetch_tasks(f"{base}/tasks")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.ok is False
    assert result.tasks == []
    assert result.reason != ""


def test_a_genuinely_empty_list_is_a_success(stub_url):
    url, state = stub_url
    state["tasks"] = []

    result = fetch_tasks(url)

    assert result.ok is True
    assert result.tasks == []
    assert result.dropped == 0


def test_reports_how_many_entries_had_to_be_discarded(stub_url):
    url, state = stub_url
    state["tasks"] = [_task(id="a"), {"broken": True}, {"also": "broken"}]

    result = fetch_tasks(url)

    assert result.ok is True
    assert len(result.tasks) == 1
    assert result.dropped == 2


def test_a_clean_response_discards_nothing(stub_url):
    url, _ = stub_url

    assert fetch_tasks(url).dropped == 0


# --- caps on the response -------------------------------------------


def _padded_body(pad_bytes: int) -> bytes:
    """A valid items payload inflated to a known size with an ignored key."""
    payload = dict(SAMPLE)
    payload["_pad"] = "x" * pad_bytes
    return json.dumps(payload).encode()


def _serve_body(body: bytes):
    class Fixed(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return _serve(Fixed)


def test_rejects_a_response_over_the_size_limit():
    body = _padded_body(MAX_RESPONSE_BYTES + 50_000)
    assert len(body) > MAX_RESPONSE_BYTES
    base, server, thread = _serve_body(body)
    try:
        result = fetch_tasks(f"{base}/tasks")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.ok is False
    assert result.tasks == []
    assert result.reason != ""


def test_accepts_a_response_just_under_the_size_limit():
    body = _padded_body(MAX_RESPONSE_BYTES - 20_000)
    assert len(body) < MAX_RESPONSE_BYTES
    base, server, thread = _serve_body(body)
    try:
        result = fetch_tasks(f"{base}/tasks")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.ok is True
    assert [task.id for task in result.tasks] == ["a", "b"]


def test_a_long_title_from_the_gateway_comes_back_truncated_and_incomplete(stub_url):
    url, state = stub_url
    state["tasks"] = [_task(title="T" * 120)]

    result = fetch_tasks(url)

    assert result.ok is True
    assert len(result.tasks[0].title) == MAX_TITLE
    assert result.truncated == 1
