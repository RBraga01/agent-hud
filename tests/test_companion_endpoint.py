"""Live HTTP checks for the fail-closed companion snapshot boundary."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from stub_server.refresher import CollectionReport, Refresher
from stub_server.server import create_server
from stub_server.store import TaskStore
from tests.test_companion_contract import validator

PATH = "/v1/companion/snapshots/current"
TASK = {
    "id": "work-1", "revision": 2, "source": "Simulated", "title": "Review",
    "summary": "Needs review", "detail": "Review this change", "needs_you": True,
    "actions": {"primary": {"id": "approve", "label": "Approve"}},
}


def _serve(*, report, sources=("simulated",), auth=True):
    store = TaskStore()
    refresher = Refresher(store, report, sources=sources, interval=5)
    server = create_server(
        store.snapshot, port=0, store=store, refresher=refresher,
        sources=[{"name": name, "on": True} for name in sources],
        require_auth=auth,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    cookie = {"agent_hud_session": server.auth.open_session()}

    def stop():
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return base, cookie, refresher, server, stop


def test_authenticated_verified_snapshot_and_revision_change():
    base, cookie, refresher, _, stop = _serve(
        report=lambda: CollectionReport([TASK], ("simulated",))
    )
    try:
        before = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        assert before["complete"] is False
        assert before["source_health"][0]["state"] == "never_checked"
        assert refresher.sweep_once()
        response = requests.get(base + PATH, cookies=cookie, timeout=5)
        snapshot = response.json()
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        validator("Snapshot").validate(snapshot)
        assert snapshot["complete"] is True
        assert snapshot["tasks"][0]["task_id"] == "work-1"
        assert snapshot["tasks"][0]["actions"] == [
            {"action_id": "approve", "label": "Approve"}
        ]
        assert snapshot["selected_device"] is None
        assert snapshot["decision_submission_enabled"] is False
        assert snapshot["version"] > before["version"]
        assert requests.get(base + "/tasks", cookies=cookie, timeout=5).json()[
            "tasks"
        ] == [TASK]
    finally:
        stop()


def test_missing_source_evidence_never_makes_empty_authoritative():
    base, cookie, refresher, _, stop = _serve(
        report=lambda: CollectionReport([], ("simulated",)),
        sources=("simulated", "github"),
    )
    try:
        assert refresher.sweep_once()
        snapshot = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        validator("Snapshot").validate(snapshot)
        assert snapshot["complete"] is False
        assert {s["name"]: s["state"] for s in snapshot["source_health"]} == {
            "simulated": "healthy", "github": "failed"
        }
    finally:
        stop()


def test_auth_disabled_and_device_token_cannot_read_companion():
    base, cookie, _, _, stop = _serve(report=list, auth=False)
    try:
        response = requests.get(base + PATH, cookies=cookie, timeout=5)
        assert response.status_code == 403
        assert response.headers["Cache-Control"] == "no-store"
    finally:
        stop()

    base, cookie, _, server, stop = _serve(report=list)
    try:
        _, token = server.auth.pair_device("test glasses")
        response = requests.get(
            base + PATH, headers={"X-Agent-Hud-Device": token}, timeout=5
        )
        assert response.status_code == 401
        assert "tasks" not in response.json()
        owner = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        assert owner["selected_device"]["health"] == "unknown"
    finally:
        stop()


def test_restart_changes_identity_and_malformed_tasks_fail_closed():
    first, cookie, refresher, _, stop = _serve(
        report=lambda: CollectionReport([TASK], ("simulated",))
    )
    try:
        refresher.sweep_once()
        instance = requests.get(first + PATH, cookies=cookie, timeout=5).json()[
            "gateway_instance_id"
        ]
    finally:
        stop()
    second, cookie, refresher, _, stop = _serve(
        report=lambda: CollectionReport([dict(TASK, actions={"primary": {}})],
                                        ("simulated",))
    )
    try:
        refresher.sweep_once()
        snapshot = requests.get(second + PATH, cookies=cookie, timeout=5).json()
        validator("Snapshot").validate(snapshot)
        assert snapshot["gateway_instance_id"] != instance
        assert snapshot["complete"] is False
        assert snapshot["tasks"] == []
    finally:
        stop()


def test_policy_decision_moves_effective_version_without_store_change():
    base, cookie, refresher, _, stop = _serve(
        report=lambda: CollectionReport([TASK], ("simulated",))
    )
    try:
        assert refresher.sweep_once()
        before = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        accepted = requests.post(
            base + "/tasks/work-1/feedback", cookies=cookie, timeout=5,
            json={"request_id": "decision-1", "revision": 2,
                  "type": "action", "action_id": "approve"},
        )
        assert accepted.status_code == 200
        after = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        validator("Snapshot").validate(after)
        assert after["version"] > before["version"]
        assert after["tasks"][0]["needs_you"] is False
        assert after["tasks"][0]["revision"] == 3
    finally:
        stop()


def test_failed_sweep_preserves_tasks_but_never_claims_completeness():
    broken = {"value": False}

    def report():
        if broken["value"]:
            raise RuntimeError("source unavailable")
        return CollectionReport([TASK], ("simulated",))

    base, cookie, refresher, _, stop = _serve(report=report)
    try:
        assert refresher.sweep_once()
        before = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        broken["value"] = True
        assert not refresher.sweep_once()
        after = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        validator("Snapshot").validate(after)
        assert after["complete"] is False
        assert after["source_health"][0]["state"] == "failed"
        assert after["tasks"] == before["tasks"]
        assert after["version"] > before["version"]
    finally:
        stop()


def test_concurrent_sweeps_and_http_reads_always_validate():
    counter = {"n": 0}

    def report():
        counter["n"] += 1
        return CollectionReport(
            [dict(TASK, detail=f"revision {counter['n']}")], ("simulated",)
        )

    base, cookie, refresher, _, stop = _serve(report=report)
    try:
        assert refresher.sweep_once()
        with ThreadPoolExecutor(max_workers=4) as pool:
            writes = [pool.submit(refresher.sweep_once) for _ in range(20)]
            reads = [
                pool.submit(requests.get, base + PATH, cookies=cookie, timeout=5)
                for _ in range(20)
            ]
            assert all(job.result() for job in writes)
            for job in reads:
                response = job.result()
                assert response.status_code == 200
                snapshot = response.json()
                validator("Snapshot").validate(snapshot)
                assert snapshot["complete"] is True
    finally:
        stop()


def test_content_edit_and_unverified_push_both_move_version():
    base, cookie, refresher, server, stop = _serve(
        report=lambda: CollectionReport([TASK], ("simulated",))
    )
    try:
        assert refresher.sweep_once()
        before = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        server.store.replace("poll", [dict(TASK, detail="Edited without new revision")])
        edited = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        assert edited["version"] > before["version"]
        assert edited["tasks"][0]["detail"] == "Edited without new revision"
        server.store.replace("push:unknown", [dict(TASK, id="pushed")])
        pushed = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        validator("Snapshot").validate(pushed)
        assert pushed["version"] > edited["version"]
        assert pushed["complete"] is False
    finally:
        stop()


def test_http_push_cannot_inherit_poll_source_evidence():
    base, cookie, refresher, _, stop = _serve(
        report=lambda: CollectionReport([TASK], ("simulated",))
    )
    try:
        assert refresher.sweep_once()
        before = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        assert before["complete"] is True
        event = requests.post(
            base + "/events", cookies=cookie, timeout=5,
            json={"source": "other", "tasks": [dict(TASK, id="pushed")]},
        )
        assert event.status_code == 200
        after = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        validator("Snapshot").validate(after)
        assert after["version"] > before["version"]
        assert after["complete"] is False
        assert after["source_health"][0]["state"] == "failed"
    finally:
        stop()


def test_expired_source_evidence_revokes_complete_and_moves_version():
    base, cookie, refresher, _, stop = _serve(
        report=lambda: CollectionReport([], ("simulated",))
    )
    try:
        assert refresher.sweep_once()
        healthy = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        assert healthy["complete"] is True
        refresher._monotonic_clock = lambda: time.monotonic() + 60
        refresher._wall_clock = lambda: time.time() + 60
        expired = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        validator("Snapshot").validate(expired)
        assert expired["complete"] is False
        assert expired["source_health"][0]["state"] == "overdue"
        assert expired["version"] > healthy["version"]
    finally:
        stop()
