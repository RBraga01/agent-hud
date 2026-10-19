"""Selected-device snapshots never confuse token traffic with link evidence."""

import threading
import time

import requests

from stub_server.auth import Credential
from stub_server.companion_contract import validate_snapshot_semantics
from stub_server.presence import PresenceMonitor
from stub_server.refresher import CollectionReport, Refresher
from stub_server.server import create_server
from stub_server.store import TaskStore
from tests.test_companion_contract import validator

PATH = "/v1/companion/snapshots/current"


def test_two_failures_close_together_do_not_prove_a_minute_of_absence():
    monitor = PresenceMonitor()
    monitor.observe("paired-1", True, at=1000)
    monitor.observe("paired-1", False, at=1012)
    monitor.observe("paired-1", False, at=1013)

    assert monitor.state("paired-1", at=1072)["health"] == "unknown"
    monitor.observe("paired-1", False, at=1072)
    assert monitor.state("paired-1", at=1072)["health"] == "unavailable"


def test_negative_presence_evidence_expires_and_new_failure_starts_a_new_run():
    monitor = PresenceMonitor()
    monitor.observe("paired-1", True, at=1000)
    monitor.observe("paired-1", False, at=1012)
    monitor.observe("paired-1", False, at=1072)

    assert monitor.state("paired-1", at=1072)["health"] == "unavailable"
    assert monitor.state("paired-1", at=1192)["health"] == "unavailable"
    assert monitor.state("paired-1", at=1192.001)["health"] == "unknown"

    monitor.observe("paired-1", False, at=5000)
    restarted = monitor.state("paired-1", at=5000)
    assert restarted["health"] == "unknown"
    assert restarted["failed_observations"] == 1
    assert restarted["absence_started_at"] == 5000


def _gateway(clock, checker, auth_path=None):
    store = TaskStore()
    refresher = Refresher(
        store, lambda: CollectionReport([], ("simulated",)),
        sources=("simulated",), interval=5,
        wall_clock=clock, monotonic_clock=clock,
    )
    server = create_server(
        store.snapshot, port=0, store=store, refresher=refresher,
        sources=[{"name": "simulated", "on": True}],
        require_auth=True, auth_path=auth_path,
        link_checker=checker, presence_clock=clock,
    )
    server.auth.add(Credential("dummy-passkey", "public", 0, "owner", clock()))
    cookie = {"agent_hud_session": server.auth.open_session()}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def stop():
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return base, cookie, refresher, server, stop


def _snapshot(base, cookie):
    response = requests.get(base + PATH, cookies=cookie, timeout=5)
    assert response.status_code == 200
    payload = response.json()
    validator("Snapshot").validate(payload)
    validate_snapshot_semantics(payload)
    return payload


def test_authenticated_selection_and_link_state_transitions():
    moment = {"at": time.time()}
    link = {"up": True}
    checks = {"count": 0}

    def clock():
        return moment["at"]

    def checker(device):
        checks["count"] += 1
        return link["up"]

    base, cookie, refresher, server, stop = _gateway(
        clock, checker
    )
    try:
        assert refresher.sweep_once()
        refused = requests.post(
            base + "/auth/devices/pair", json={"name": "glasses"}, timeout=5
        )
        assert refused.status_code == 403
        paired = requests.post(
            base + "/auth/devices/pair", cookies=cookie,
            json={"name": "glasses", "device_id": "forged"}, timeout=5,
        )
        assert paired.status_code == 200
        device_id = paired.json()["device_id"]
        assert device_id != "forged"
        token = paired.json()["token"]
        unknown = _snapshot(base, cookie)
        assert unknown["selected_device"]["device_id"] == device_id
        assert unknown["selected_device"]["health"] == "unknown"
        assert unknown["selected_device"]["evidence"] == "none"
        assert _snapshot(base, cookie)["version"] == unknown["version"]

        # Valid token traffic is activity, never a physical-link proof.
        assert requests.get(
            base + "/tasks", headers={"X-Agent-Hud-Device": token}, timeout=5
        ).status_code == 200
        active = _snapshot(base, cookie)
        assert active["selected_device"]["last_authenticated_at"] is not None
        assert active["selected_device"]["health"] == "unknown"
        assert checks["count"] == 0

        assert server.poll_selected_link() is True
        assert checks["count"] == 1
        healthy = _snapshot(base, cookie)
        assert healthy["selected_device"]["health"] == "healthy"
        assert healthy["selected_device"]["evidence"] == "verified_link"
        assert healthy["version"] > active["version"]
        assert _snapshot(base, cookie)["version"] == healthy["version"]
        assert checks["count"] == 1

        link["up"] = False
        moment["at"] += 12
        assert server.poll_selected_link() is False
        uncertain = _snapshot(base, cookie)
        assert uncertain["selected_device"]["health"] == "unknown"
        assert uncertain["selected_device"]["failed_observations"] == 1
        assert server.poll_selected_link() is False
        assert _snapshot(base, cookie)["selected_device"]["failed_observations"] == 1

        moment["at"] += 60
        assert server.poll_selected_link() is False
        unavailable = _snapshot(base, cookie)
        assert unavailable["selected_device"]["health"] == "unavailable"
        assert unavailable["selected_device"]["failed_observations"] == 2

        moment["at"] += 121
        expired = _snapshot(base, cookie)
        assert expired["selected_device"]["health"] == "unknown"
        assert expired["version"] > unavailable["version"]
        assert server.poll_selected_link() is False
        assert _snapshot(base, cookie)["selected_device"]["failed_observations"] == 1

        link["up"] = True
        moment["at"] += 1
        assert server.poll_selected_link() is True
        recovered = _snapshot(base, cookie)
        assert recovered["selected_device"]["health"] == "healthy"
        assert recovered["selected_device"]["failed_observations"] == 0

        revoked = requests.post(
            base + f"/auth/devices/revoke/{device_id}", cookies=cookie, timeout=5
        )
        assert revoked.status_code == 200
        assert _snapshot(base, cookie)["selected_device"] is None
        assert requests.get(
            base + "/tasks", headers={"X-Agent-Hud-Device": token}, timeout=5
        ).status_code == 401
    finally:
        stop()


def test_restart_keeps_pairing_but_forgets_physical_presence(tmp_path):
    moment = {"at": time.time()}

    def clock():
        return moment["at"]

    path = tmp_path / "gateway-auth.json"
    base, cookie, refresher, server, stop = _gateway(
        clock, lambda device: True, auth_path=path
    )
    try:
        refresher.sweep_once()
        paired = requests.post(
            base + "/auth/devices/pair", cookies=cookie,
            json={"name": "test glasses"}, timeout=5,
        ).json()
        assert server.poll_selected_link() is True
        before = _snapshot(base, cookie)
        assert before["selected_device"]["health"] == "healthy"
    finally:
        stop()

    base, cookie, refresher, _, stop = _gateway(
        clock, lambda device: None, auth_path=path
    )
    try:
        refresher.sweep_once()
        after = _snapshot(base, cookie)
        assert after["gateway_instance_id"] != before["gateway_instance_id"]
        assert after["selected_device"]["device_id"] == paired["device_id"]
        assert after["selected_device"]["health"] == "unknown"
        assert after["selected_device"]["last_verified_link_at"] is None
    finally:
        stop()


def test_revocation_during_link_probe_discards_late_result():
    entered = threading.Event()
    release = threading.Event()

    def checker(device):
        entered.set()
        assert release.wait(timeout=5)
        return True

    base, cookie, refresher, server, stop = _gateway(time.time, checker)
    try:
        refresher.sweep_once()
        paired = requests.post(
            base + "/auth/devices/pair", cookies=cookie,
            json={"name": "test glasses"}, timeout=5,
        ).json()
        observed = {}
        worker = threading.Thread(
            target=lambda: observed.setdefault("result", server.poll_selected_link())
        )
        worker.start()
        assert entered.wait(timeout=5)
        revoked = requests.post(
            base + f"/auth/devices/revoke/{paired['device_id']}",
            cookies=cookie, timeout=5,
        )
        assert revoked.status_code == 200
        release.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert observed["result"] is None
        assert _snapshot(base, cookie)["selected_device"] is None
    finally:
        release.set()
        stop()


def test_newer_negative_probe_cannot_be_overwritten_by_late_positive():
    old_entered = threading.Event()
    release_old = threading.Event()
    calls = {"count": 0}

    def checker(device):
        calls["count"] += 1
        if calls["count"] == 1:
            return True
        if calls["count"] == 2:
            old_entered.set()
            assert release_old.wait(timeout=5)
            return True
        return False

    base, cookie, refresher, server, stop = _gateway(time.time, checker)
    try:
        refresher.sweep_once()
        paired = requests.post(
            base + "/auth/devices/pair", cookies=cookie,
            json={"name": "test glasses"}, timeout=5,
        )
        assert paired.status_code == 200
        assert server.poll_selected_link() is True

        observed = {}
        worker = threading.Thread(
            target=lambda: observed.setdefault("old", server.poll_selected_link())
        )
        worker.start()
        assert old_entered.wait(timeout=5)
        assert server.poll_selected_link() is False
        release_old.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert observed["old"] is None

        presence = _snapshot(base, cookie)["selected_device"]
        assert presence["health"] == "unknown"
        assert presence["failed_observations"] == 1
    finally:
        release_old.set()
        stop()


def test_malformed_pairing_request_cannot_select_a_device():
    base, cookie, refresher, _, stop = _gateway(time.time, None)
    try:
        refresher.sweep_once()
        response = requests.post(
            base + "/auth/devices/pair", cookies=cookie,
            data="{", headers={"Content-Type": "application/json"}, timeout=5,
        )
        assert response.status_code == 400
        assert _snapshot(base, cookie)["selected_device"] is None
    finally:
        stop()
