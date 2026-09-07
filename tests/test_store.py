"""Tests for the gateway's task store."""

import threading

from stub_server.store import TaskStore


def task(tid, revision=1, needs_you=True):
    return {"id": tid, "revision": revision, "needs_you": needs_you, "title": tid}


def test_a_new_store_is_empty_at_version_zero():
    store = TaskStore()
    assert store.snapshot() == []
    assert store.version == 0


def test_replacing_a_slice_moves_the_version():
    store = TaskStore()
    assert store.replace("poll", [task("a")]) is True
    assert store.version == 1
    assert [t["id"] for t in store.snapshot()] == ["a"]


def test_an_identical_replace_does_not_move_the_version():
    store = TaskStore()
    store.replace("poll", [task("a", revision=2)])
    v = store.version

    assert store.replace("poll", [task("a", revision=2)]) is False
    assert store.version == v


def test_a_changed_revision_counts_as_a_change():
    store = TaskStore()
    store.replace("poll", [task("a", revision=1)])
    assert store.replace("poll", [task("a", revision=2)]) is True


def test_slices_are_flattened_in_first_written_order():
    store = TaskStore()
    store.replace("poll", [task("p1"), task("p2")])
    store.replace("push:codex", [task("c1")])

    assert [t["id"] for t in store.snapshot()] == ["p1", "p2", "c1"]


def test_a_later_slice_cannot_double_an_id_already_seen():
    store = TaskStore()
    store.replace("poll", [task("shared", revision=1)])
    store.replace("push:x", [task("shared", revision=9), task("only-here")])

    snap = store.snapshot()
    assert [t["id"] for t in snap] == ["shared", "only-here"]
    # the poll copy wins because it was written first
    assert snap[0]["revision"] == 1


def test_dropping_a_slice_removes_it_and_moves_the_version():
    store = TaskStore()
    store.replace("poll", [task("a")])
    store.replace("push:y", [task("b")])
    v = store.version

    assert store.drop("push:y") is True
    assert store.version == v + 1
    assert [t["id"] for t in store.snapshot()] == ["a"]
    assert store.drop("push:y") is False


def test_non_dict_entries_are_dropped_on_the_way_in():
    store = TaskStore()
    store.replace("poll", [task("a"), "not a task", None, {"id": "b"}])

    assert [t["id"] for t in store.snapshot()] == ["a", "b"]


def test_the_snapshot_is_a_copy_callers_cannot_mutate_the_store():
    store = TaskStore()
    store.replace("poll", [task("a")])

    store.snapshot()[0]["title"] = "changed"

    assert store.snapshot()[0]["title"] == "a"


def test_concurrent_replaces_do_not_corrupt_the_store():
    store = TaskStore()

    def worker(name):
        for i in range(200):
            store.replace(name, [task(f"{name}-{i}")])

    threads = [threading.Thread(target=worker, args=(n,)) for n in "abcd"]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ids = {t["id"].split("-")[0] for t in store.snapshot()}
    assert ids == set("abcd")
    assert store.version >= 4
