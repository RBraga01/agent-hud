"""The gateway as a real network surface: bound off loopback, locked, and
wrapped in TLS, driven the way the glasses drive it.

The plain-http pairing tests in ``test_server.py`` prove the auth logic.
These prove it still holds once the request has crossed a pinned TLS
connection and gone through ``agent_hud.client`` -- header forwarding,
body streaming through the wrapped socket, the config-to-session wiring.
"""

from __future__ import annotations

import threading

import pytest

pytest.importorskip("cryptography")

from agent_hud.client import fetch_tasks
from agent_hud.feedback import Feedback, SendOutcome, send_feedback
from agent_hud.tls import session_for
from stub_server.server import create_server
from stub_server.tls import ensure_cert, server_context

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


class NetworkGateway:
    """A gateway started the way a network deployment would start it."""

    def __init__(self, base: str, fingerprint: str, server):
        self.base = base
        self.fingerprint = fingerprint
        self.server = server

    def pinned(self):
        return session_for(fingerprint=self.fingerprint)

    def pair(self, name: str = "Raven Prism", *, session=None):
        http = session or self.pinned()
        reply = http.post(
            f"{self.base}/auth/devices/pair", json={"name": name}, timeout=5
        )
        return reply

    def revoke(self, device_id: str, *, session=None):
        http = session or self.pinned()
        return http.post(
            f"{self.base}/auth/devices/revoke/{device_id}", timeout=5
        )


@pytest.fixture
def network_gateway(tmp_path):
    info = ensure_cert(store_dir=tmp_path, hosts=["0.0.0.0"])
    server = create_server(
        lambda: [dict(TASK)],
        port=0,
        host="0.0.0.0",
        require_auth=True,
        auth_path=tmp_path / "passkeys.json",
        ssl_context=server_context(info),
    )
    server.handle_error = lambda request, client_address: None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # Bound to every interface; the test reaches it on loopback.
    base = f"https://127.0.0.1:{server.server_address[1]}"
    yield NetworkGateway(base, info.fingerprint, server)

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


# --- the wire is what these exercise ---------------------------------------


def test_it_comes_up_on_https(network_gateway):
    assert network_gateway.base.startswith("https://")
    assert network_gateway.server.scheme == "https"


def test_pair_then_read_the_list_over_the_pinned_connection(network_gateway):
    token = network_gateway.pair().json()["token"]

    result = fetch_tasks(
        f"{network_gateway.base}/tasks",
        timeout=5,
        device_token=token,
        session=network_gateway.pinned(),
    )

    assert result.ok is True
    assert [t.id for t in result.tasks] == ["task-17"]


def test_a_paired_device_can_answer_over_tls(network_gateway):
    token = network_gateway.pair().json()["token"]

    result = send_feedback(
        network_gateway.base,
        Feedback(
            task_id="task-17", revision=4, action_id="approve",
            request_id="req-net",
        ),
        timeout=5,
        device_token=token,
        session=network_gateway.pinned(),
    )

    assert result.outcome is SendOutcome.ACCEPTED


def test_no_token_is_turned_away_over_tls(network_gateway):
    network_gateway.pair()  # a device exists; this request still has no token

    result = fetch_tasks(
        f"{network_gateway.base}/tasks",
        timeout=5,
        session=network_gateway.pinned(),
    )

    assert result.ok is False


def test_a_bad_token_is_turned_away_over_tls(network_gateway):
    network_gateway.pair()

    result = fetch_tasks(
        f"{network_gateway.base}/tasks",
        timeout=5,
        device_token="not-a-real-token",
        session=network_gateway.pinned(),
    )

    assert result.ok is False


def test_revoking_over_tls_stops_the_token_working(network_gateway):
    paired = network_gateway.pair().json()
    token = paired["token"]
    session = network_gateway.pinned()

    good = fetch_tasks(
        f"{network_gateway.base}/tasks",
        timeout=5, device_token=token, session=session,
    )
    assert good.ok is True

    revoked = network_gateway.revoke(paired["device_id"], session=session)
    assert revoked.json() == {"revoked": True}

    after = fetch_tasks(
        f"{network_gateway.base}/tasks",
        timeout=5, device_token=token, session=session,
    )
    assert after.ok is False


def test_revoking_a_device_that_is_not_there_is_not_found(network_gateway):
    reply = network_gateway.revoke("0000000000000000")
    assert reply.status_code == 404
    assert reply.json() == {"revoked": False}


def test_the_token_crosses_the_wire_once_and_is_never_stored_in_the_clear(
    network_gateway,
):
    token = network_gateway.pair().json()["token"]

    stored = next(iter(network_gateway.server.auth.devices.values()))
    assert stored.token_hash != token
    assert token not in stored.token_hash

    listed = network_gateway.pinned().get(
        f"{network_gateway.base}/auth/devices", timeout=5
    )
    assert token not in listed.text


# --- pinning is on the same door as auth ----------------------------------


def test_the_wrong_pin_cannot_even_begin_to_pair(network_gateway):
    import requests

    wrong = session_for(fingerprint="AA:" * 31 + "AA")

    with pytest.raises(requests.exceptions.SSLError):
        network_gateway.pair(session=wrong)


def test_an_unpinned_client_cannot_reach_the_locked_gateway(network_gateway):
    import requests

    with pytest.raises(requests.exceptions.SSLError):
        requests.get(f"{network_gateway.base}/tasks", timeout=5)


# --- the session the app would build from settings -----------------------


def test_the_session_built_from_settings_reaches_the_gateway(network_gateway):
    from agent_hud.config import load_settings

    token = network_gateway.pair().json()["token"]
    settings = load_settings(
        {
            "AGENT_HUD_GATEWAY_URL": f"{network_gateway.base}/tasks",
            "AGENT_HUD_GATEWAY_FINGERPRINT": network_gateway.fingerprint,
            "AGENT_HUD_DEVICE_TOKEN": token,
        }
    )

    session = session_for(
        fingerprint=settings.gateway_fingerprint, ca=settings.gateway_ca
    )
    result = fetch_tasks(
        settings.gateway_url,
        timeout=5,
        device_token=settings.device_token,
        session=session,
    )

    assert result.ok is True
