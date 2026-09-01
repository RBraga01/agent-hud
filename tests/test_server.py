"""Tests for the stub gateway.

It asks its provider for the current list on every request, so whatever the
feeders return is what the glasses see, with nothing cached in between.
"""

import json
import threading

import pytest
import requests

from stub_server.server import ITEMS_PATH, create_server

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
    response = requests.get(f"{fixed_server}{ITEMS_PATH}", timeout=5)

    assert response.status_code == 200
    assert response.json() == {"items": SAMPLE}


def test_says_it_is_json(fixed_server):
    response = requests.get(f"{fixed_server}{ITEMS_PATH}", timeout=5)

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
        first = requests.get(f"{base}{ITEMS_PATH}", timeout=5).json()
        second = requests.get(f"{base}{ITEMS_PATH}", timeout=5).json()
    finally:
        stop()

    assert first["items"][0]["detail"] == "1"
    assert second["items"][0]["detail"] == "2"


def test_a_broken_feeder_does_not_take_the_gateway_down():
    def provider():
        raise RuntimeError("the feeder fell over")

    base, stop = serve(provider)
    try:
        response = requests.get(f"{base}{ITEMS_PATH}", timeout=5)
        # And it is still answering afterwards.
        again = requests.get(f"{base}{ITEMS_PATH}", timeout=5)
    finally:
        stop()

    assert response.status_code == 500
    assert again.status_code == 500


def test_an_empty_list_is_a_normal_answer():
    base, stop = serve(list)
    try:
        response = requests.get(f"{base}{ITEMS_PATH}", timeout=5)
    finally:
        stop()

    assert response.status_code == 200
    assert response.json() == {"items": []}


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
    raw = requests.get(f"{fixed_server}{ITEMS_PATH}", timeout=5).text

    assert json.loads(raw)["items"][0]["title"] == "One"
