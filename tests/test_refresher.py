"""Tests for the background feeder sweep."""

import time

from stub_server.refresher import POLL_KEY, Refresher
from stub_server.store import TaskStore


def test_a_sweep_writes_the_poll_slice():
    store = TaskStore()
    r = Refresher(store, lambda: [{"id": "a"}], interval=0.05)

    assert r.sweep_once() is True
    assert [t["id"] for t in store.snapshot()] == ["a"]


def test_the_thread_sweeps_again_on_its_interval():
    store = TaskStore()
    counter = {"n": 0}

    def collect():
        counter["n"] += 1
        return [{"id": f"t{counter['n']}"}]

    r = Refresher(store, collect, interval=0.05)
    r.start()
    try:
        time.sleep(0.4)
    finally:
        r.stop()

    # one sweep on start, then at least one more on the interval -- the
    # exact count is at the mercy of a loaded CI box, so only "more than
    # once" is asserted.
    assert counter["n"] >= 2
    # the store holds the most recent sweep only
    assert len(store.snapshot()) == 1


def test_a_failing_sweep_keeps_the_previous_slice():
    store = TaskStore()
    state = {"ok": True}

    def collect():
        if state["ok"]:
            return [{"id": "good"}]
        raise RuntimeError("half-written file")

    seen = []
    r = Refresher(store, collect, interval=0.05, on_error=seen.append)

    assert r.sweep_once() is True
    state["ok"] = False
    assert r.sweep_once() is False

    assert [t["id"] for t in store.snapshot()] == ["good"]
    assert len(seen) == 1 and isinstance(seen[0], RuntimeError)


def test_stop_halts_the_loop():
    store = TaskStore()
    r = Refresher(store, list, interval=0.05)
    r.start()
    r.stop()

    assert not r.is_alive()


def test_a_zero_or_negative_interval_is_clamped():
    r = Refresher(TaskStore(), list, interval=0)
    assert r._interval >= 0.2


def test_the_slice_key_is_stable():
    store = TaskStore()
    Refresher(store, lambda: [{"id": "x"}], interval=1).sweep_once()
    assert POLL_KEY in store._slices


def test_sweep_health_distinguishes_never_checked_fresh_and_overdue():
    moment = {"wall": 1000.0, "mono": 10.0}
    r = Refresher(
        TaskStore(),
        list,
        interval=5,
        wall_clock=lambda: moment["wall"],
        monotonic_clock=lambda: moment["mono"],
    )

    assert r.health().state == "never_checked"
    assert r.sweep_once() is True
    fresh = r.health()
    assert fresh.state == "healthy"
    assert fresh.last_success_at == 1000.0
    assert fresh.fresh_until == 1010.0

    moment["mono"] = 21.0
    assert r.health().state == "overdue"


def test_malformed_sweep_preserves_last_good_data_but_marks_failure():
    store = TaskStore()
    results = [[{"id": "last-good"}], [{"id": "new"}, "broken"]]
    errors = []
    r = Refresher(store, lambda: results.pop(0), on_error=errors.append)

    assert r.sweep_once() is True
    assert r.sweep_once() is False
    assert store.snapshot() == [{"id": "last-good"}]
    assert r.health().state == "failed"
    assert len(errors) == 1


def test_non_list_sweep_is_failure_not_verified_empty():
    store = TaskStore()
    r = Refresher(store, lambda: None)

    assert r.sweep_once() is False
    assert r.health().state == "failed"
    assert store.snapshot() == []
