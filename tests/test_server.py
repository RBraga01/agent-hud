"""Tests for the stub server.

The stub stands in for the real gateway. It reads a file you hand-edit
and serves it, so editing the file is how we drive the display during
development. It must re-read on every request, or edits would not show
up without a restart.
"""

import json
import threading

import pytest
import requests

from stub_server.server import ITEMS_PATH, create_server

SAMPLE = {
    "items": [
        {"id": "a", "title": "One", "detail": "first", "needs_you": True},
        {"id": "b", "title": "Two", "detail": "second", "needs_you": False},
    ]
}


@pytest.fixture
def running_server(tmp_path):
    """Start the stub on a free port, serving a file the test controls."""
    data_file = tmp_path / "agents.json"
    data_file.write_text(json.dumps(SAMPLE), encoding="utf-8")

    server = create_server(data_path=data_file, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    host, port = server.server_address[:2]
    yield f"http://127.0.0.1:{port}", data_file

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_serves_the_file_contents_as_json(running_server):
    base_url, _ = running_server

    response = requests.get(f"{base_url}{ITEMS_PATH}", timeout=5)

    assert response.status_code == 200
    assert response.json() == SAMPLE


def test_says_it_is_json(running_server):
    base_url, _ = running_server

    response = requests.get(f"{base_url}{ITEMS_PATH}", timeout=5)

    assert response.headers["Content-Type"].startswith("application/json")


def test_picks_up_edits_without_a_restart(running_server):
    base_url, data_file = running_server
    edited = {"items": [{"id": "c", "title": "Three", "detail": "", "needs_you": True}]}

    data_file.write_text(json.dumps(edited), encoding="utf-8")
    response = requests.get(f"{base_url}{ITEMS_PATH}", timeout=5)

    assert response.json() == edited


def test_returns_an_error_when_the_file_is_missing(running_server):
    base_url, data_file = running_server

    data_file.unlink()
    response = requests.get(f"{base_url}{ITEMS_PATH}", timeout=5)

    assert response.status_code == 500


def test_returns_an_error_when_the_file_is_not_valid_json(running_server):
    base_url, data_file = running_server

    data_file.write_text("{ this is not json", encoding="utf-8")
    response = requests.get(f"{base_url}{ITEMS_PATH}", timeout=5)

    assert response.status_code == 500


def test_unknown_paths_are_not_found(running_server):
    base_url, _ = running_server

    response = requests.get(f"{base_url}/something-else", timeout=5)

    assert response.status_code == 404


def test_binds_only_to_the_loopback_address(tmp_path):
    # The stub must never be reachable from the network. It serves whatever
    # is in a local file with no authentication of any kind.
    data_file = tmp_path / "agents.json"
    data_file.write_text(json.dumps(SAMPLE), encoding="utf-8")

    server = create_server(data_path=data_file, port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()
