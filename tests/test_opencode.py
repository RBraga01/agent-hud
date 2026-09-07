"""Tests for the OpenCode feeder.

OpenCode keeps its sessions in a SQLite database, ``opencode.db``. This
feeder opens it read-only and decides whose turn it is from the newest
row in ``message``. The tests build a small database in tmp_path with the
columns the feeder reads and never touch a real one.
"""

import json
import sqlite3

from agent_hud.tasks import parse_tasks
from feeders import opencode

NOW = 1_000_000.0
MS = 1000  # the database stores milliseconds


def build_db(tmp_path, sessions):
    """sessions: list of dicts with
    id, title, directory, age_seconds, and a `last` message dict
    (or None for a session with no messages / archived=<epoch>).
    """
    path = tmp_path / "opencode.db"
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE session ("
        "id TEXT PRIMARY KEY, title TEXT NOT NULL, directory TEXT NOT NULL, "
        "time_updated INTEGER NOT NULL, time_archived INTEGER)"
    )
    db.execute(
        "CREATE TABLE message ("
        "id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
        "time_created INTEGER NOT NULL, data TEXT NOT NULL)"
    )
    for i, s in enumerate(sessions):
        updated = int((NOW - s["age"]) * MS)
        db.execute(
            "INSERT INTO session VALUES (?,?,?,?,?)",
            (
                s["id"],
                s.get("title", ""),
                s.get("directory", "e:/Projectos/thing"),
                updated,
                s.get("archived"),
            ),
        )
        last = s.get("last", _sentinel)
        if last is not _sentinel and last is not None:
            db.execute(
                "INSERT INTO message VALUES (?,?,?,?)",
                (f"msg{i}", s["id"], updated, json.dumps(last)),
            )
    db.commit()
    db.close()
    return path


_sentinel = object()


def assistant(*, completed=True, finish="stop"):
    msg = {"role": "assistant", "time": {"created": 1}}
    if completed:
        msg["time"]["completed"] = 2
    if finish is not None:
        msg["finish"] = finish
    return msg


def user():
    return {"role": "user", "time": {"created": 1}}


def test_a_finished_turn_needs_you(tmp_path):
    db = build_db(
        tmp_path,
        [{"id": "ses_aaaa1111bbbb", "title": "Refactor the loader", "age": 300,
          "last": assistant()}],
    )

    items = opencode.collect(db, now=NOW)

    assert len(items) == 1
    it = items[0]
    assert it["source"] == "OpenCode"
    assert it["title"] == "Refactor the loader"
    assert it["needs_you"] is True
    assert "your turn" in it["summary"]
    assert it["id"] == "opencode-aaaa1111bbbb"


def test_a_still_generating_turn_does_not_need_you(tmp_path):
    db = build_db(
        tmp_path,
        [{"id": "ses_x", "title": "Long job", "age": 60,
          "last": assistant(completed=False, finish=None)}],
    )

    assert opencode.collect(db, now=NOW)[0]["needs_you"] is False
    assert opencode.collect(db, now=NOW)[0]["summary"] == "working"


def test_your_line_is_newest_means_working(tmp_path):
    db = build_db(
        tmp_path,
        [{"id": "ses_y", "title": "Just asked", "age": 30, "last": user()}],
    )

    assert opencode.collect(db, now=NOW)[0]["summary"] == "working"


def test_an_errored_turn_needs_you_and_says_failed(tmp_path):
    db = build_db(
        tmp_path,
        [{"id": "ses_z", "title": "Broke", "age": 120,
          "last": assistant(finish="error")}],
    )

    it = opencode.collect(db, now=NOW)[0]
    assert it["needs_you"] is True
    assert it["summary"] == "failed"


def test_an_aborted_turn_also_says_failed(tmp_path):
    db = build_db(
        tmp_path,
        [{"id": "ses_ab", "title": "Killed", "age": 120,
          "last": assistant(finish="aborted")}],
    )

    assert opencode.collect(db, now=NOW)[0]["summary"] == "failed"


def test_the_auto_generated_title_falls_back_to_the_project(tmp_path):
    db = build_db(
        tmp_path,
        [{"id": "ses_p", "title": "New session - 2026-09-07T11:44:02.472Z",
          "directory": "e:/Projectos/my-api", "age": 120, "last": assistant()}],
    )

    assert opencode.collect(db, now=NOW)[0]["title"] == "my api"


def test_an_abandoned_session_drops_out(tmp_path):
    db = build_db(
        tmp_path,
        [{"id": "ses_old", "title": "Old", "age": opencode.STALE_SECONDS + 60,
          "last": assistant()}],
    )

    assert opencode.collect(db, now=NOW) == []


def test_an_archived_session_is_left_alone(tmp_path):
    db = build_db(
        tmp_path,
        [{"id": "ses_arch", "title": "Done and filed", "age": 120,
          "archived": int((NOW - 100) * MS), "last": assistant()}],
    )

    assert opencode.collect(db, now=NOW) == []


def test_a_session_with_no_messages_is_skipped(tmp_path):
    db = build_db(
        tmp_path,
        [{"id": "ses_empty", "title": "Nothing said", "age": 60, "last": None}],
    )

    assert opencode.collect(db, now=NOW) == []


def test_things_waiting_on_you_come_first(tmp_path):
    db = build_db(
        tmp_path,
        [
            {"id": "ses_w", "title": "Working one", "age": 100,
             "last": assistant(completed=False, finish=None)},
            {"id": "ses_r", "title": "Ready one", "age": 100, "last": assistant()},
        ],
    )

    assert opencode.collect(db, now=NOW)[0]["title"] == "Ready one"


def test_a_missing_database_is_not_fatal(tmp_path):
    assert opencode.collect(tmp_path / "nope.db", now=NOW) == []


def test_a_file_that_is_not_a_database_is_not_fatal(tmp_path):
    junk = tmp_path / "opencode.db"
    junk.write_text("this is not sqlite", encoding="utf-8")

    assert opencode.collect(junk, now=NOW) == []


def test_a_damaged_message_row_is_skipped_not_fatal(tmp_path):
    db = build_db(
        tmp_path,
        [{"id": "ses_ok", "title": "Fine", "age": 60, "last": assistant()}],
    )
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO session VALUES ('ses_bad','Bad','e:/p',?,NULL)",
        (int((NOW - 60) * MS),),
    )
    con.execute(
        "INSERT INTO message VALUES ('mb','ses_bad',?,'{ not json')",
        (int((NOW - 60) * MS),),
    )
    con.commit()
    con.close()

    assert [i["title"] for i in opencode.collect(db, now=NOW)] == ["Fine"]


def test_the_feeder_never_writes_to_the_database(tmp_path):
    db = build_db(
        tmp_path,
        [{"id": "ses_ro", "title": "x", "age": 60, "last": assistant()}],
    )
    before = db.stat().st_mtime_ns

    opencode.collect(db, now=NOW)

    assert db.stat().st_mtime_ns == before


def test_the_items_parse_as_tasks(tmp_path):
    db = build_db(
        tmp_path,
        [
            {"id": "ses_1", "title": "One", "age": 100, "last": assistant()},
            {"id": "ses_2", "title": "Two", "age": 200,
             "last": assistant(finish="error")},
        ],
    )

    tasks = parse_tasks({"tasks": opencode.collect(db, now=NOW)}).tasks
    assert len(tasks) == 2
    assert all(t.needs_you for t in tasks)


def test_no_message_text_reaches_the_output(tmp_path):
    leaky = assistant()
    leaky["content"] = "a private prompt the wearer typed"
    db = build_db(
        tmp_path,
        [{"id": "ses_leak", "title": "T", "age": 60, "last": leaky}],
    )

    blob = json.dumps(opencode.collect(db, now=NOW))
    assert "private prompt" not in blob


def test_it_is_a_known_feeder(tmp_path):
    from agent_hud.config import KNOWN_FEEDERS

    assert "opencode" in KNOWN_FEEDERS
