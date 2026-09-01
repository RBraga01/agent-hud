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

from agent_hud.client import fetch_items
from stub_server.server import ITEMS_PATH, create_server

SAMPLE = {
    "items": [
        {"id": "a", "title": "One", "detail": "first", "needs_you": True},
        {"id": "b", "title": "Two", "detail": "second", "needs_you": False},
    ]
}


def _serve(handler_class):
    """Run an arbitrary handler on a free loopback port. Returns the base URL."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    return f"http://127.0.0.1:{port}", server, thread


@pytest.fixture
def stub_url(tmp_path):
    data_file = tmp_path / "agents.json"
    data_file.write_text(json.dumps(SAMPLE), encoding="utf-8")

    server = create_server(data_path=data_file, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    yield f"http://127.0.0.1:{port}{ITEMS_PATH}", data_file

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_fetches_and_parses_from_a_real_server(stub_url):
    url, _ = stub_url

    result = fetch_items(url)

    assert result.ok is True
    assert result.reason == ""
    assert [item.id for item in result.items] == ["a", "b"]


def test_reports_failure_when_nothing_is_listening():
    # Port 9 is the discard service and is virtually never bound locally.
    result = fetch_items("http://127.0.0.1:9/items", timeout=1)

    assert result.ok is False
    assert result.items == []
    assert result.reason != ""


def test_reports_failure_when_the_server_errors(stub_url):
    url, data_file = stub_url
    data_file.unlink()

    result = fetch_items(url)

    assert result.ok is False
    assert result.items == []
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
        result = fetch_items(f"{base}/items")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.ok is False
    assert result.items == []
    assert result.reason != ""


def test_reports_failure_when_the_server_is_too_slow():
    class Slow(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(3)

        def log_message(self, *args):
            pass

    base, server, thread = _serve(Slow)
    try:
        result = fetch_items(f"{base}/items", timeout=0.2)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.ok is False
    assert result.items == []
    assert result.reason != ""


def test_a_valid_response_with_malformed_entries_still_succeeds(stub_url):
    # A broken entry is the gateway's problem, not a network failure.
    # The good entries must still reach the display.
    url, data_file = stub_url
    data_file.write_text(
        json.dumps(
            {
                "items": [
                    SAMPLE["items"][0],
                    {"id": "broken", "title": "No detail", "needs_you": True},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = fetch_items(url)

    assert result.ok is True
    assert [item.id for item in result.items] == ["a"]


def test_an_empty_but_valid_response_succeeds(stub_url):
    url, data_file = stub_url
    data_file.write_text(json.dumps({"items": []}), encoding="utf-8")

    result = fetch_items(url)

    assert result.ok is True
    assert result.items == []


def test_the_result_is_immutable():
    result = fetch_items("http://127.0.0.1:9/items", timeout=1)

    with pytest.raises(FrozenInstanceError):
        result.ok = True
