"""Tests for the Codex feeder.

Codex writes append-only session logs under ``~/.codex/sessions/`` and an
index at ``~/.codex/session_index.jsonl``. This feeder reads both: the
index for a human title and last-activity time, the session log's tail
for whose turn it is. The tests build a fake ``.codex`` tree in tmp_path
and never touch a real home directory.
"""

import json
import time

from agent_hud.tasks import parse_tasks
from feeders import codex

NOW = 1_000_000.0


def iso(epoch: float) -> str:
    import datetime

    return (
        datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_codex(tmp_path, sessions):
    """sessions: list of (id, thread_name, age_seconds, [event_types], cwd)."""
    root = tmp_path / ".codex"
    (root / "sessions" / "2026" / "09" / "01").mkdir(parents=True, exist_ok=True)
    index_lines = []
    for sid, name, age, events, cwd in sessions:
        updated = NOW - age
        index_lines.append(
            json.dumps(
                {"id": sid, "thread_name": name, "updated_at": iso(updated)}
            )
        )
        rollout = (
            root / "sessions" / "2026" / "09" / "01"
            / f"rollout-2026-09-01T09-00-00-{sid}.jsonl"
        )
        lines = [
            json.dumps(
                {
                    "timestamp": iso(updated - 100),
                    "type": "session_meta",
                    "payload": {"id": sid, "cwd": cwd},
                }
            )
        ]
        for et in events:
            lines.append(
                json.dumps(
                    {
                        "timestamp": iso(updated),
                        "type": "event_msg",
                        "payload": {"type": et},
                    }
                )
            )
        rollout.write_text("\n".join(lines), encoding="utf-8")
    (root / "session_index.jsonl").write_text(
        "\n".join(index_lines), encoding="utf-8"
    )
    return root


def test_a_finished_turn_needs_you(tmp_path):
    root = build_codex(
        tmp_path,
        [(
            "aaa11111", "Refactor parser", 300,
            ["task_started", "task_complete"], "e:/p",
        )],
    )

    items = codex.collect(root, now=NOW)

    assert len(items) == 1
    assert items[0]["needs_you"] is True
    assert items[0]["title"] == "Refactor parser"
    assert items[0]["id"] == "codex-aaa11111"
    assert "your turn" in items[0]["summary"]


def test_a_running_turn_does_not_need_you(tmp_path):
    root = build_codex(
        tmp_path,
        [("bbb22222", "Long job", 60, ["task_started", "token_count"], "e:/p")],
    )

    assert codex.collect(root, now=NOW)[0]["needs_you"] is False


def test_a_failed_turn_needs_you_and_says_failed(tmp_path):
    root = build_codex(
        tmp_path,
        [("ccc33333", "Broken", 120, ["task_started", "stream_error"], "e:/p")],
    )

    item = codex.collect(root, now=NOW)[0]

    assert item["needs_you"] is True
    assert item["summary"] == "failed"


def test_the_last_terminal_event_wins(tmp_path):
    # task_complete then a new task_started = a new turn is running.
    root = build_codex(
        tmp_path,
        [("ddd44444", "Two turns", 120,
          ["task_started", "task_complete", "task_started"], "e:/p")],
    )

    assert codex.collect(root, now=NOW)[0]["needs_you"] is False


def test_an_abandoned_session_drops_out(tmp_path):
    root = build_codex(
        tmp_path,
        [("eee55555", "Old", codex.STALE_SECONDS + 60, ["task_complete"], "e:/p")],
    )

    assert codex.collect(root, now=NOW) == []


def test_the_title_falls_back_to_the_project_when_the_thread_is_unnamed(tmp_path):
    root = build_codex(
        tmp_path,
        [("fff66666", "", 120, ["task_complete"], "e:/Projectos/my-api")],
    )

    assert codex.collect(root, now=NOW)[0]["title"] == "my api"


def test_things_waiting_on_you_come_first(tmp_path):
    root = build_codex(
        tmp_path,
        [
            ("s1111111", "Working one", 100, ["task_started"], "e:/a"),
            ("s2222222", "Waiting one", 100, ["task_complete"], "e:/b"),
        ],
    )

    assert codex.collect(root, now=NOW)[0]["title"] == "Waiting one"


def test_a_missing_codex_directory_is_not_fatal(tmp_path):
    assert codex.collect(tmp_path / "nope", now=NOW) == []


def test_a_missing_index_is_not_fatal(tmp_path):
    (tmp_path / ".codex").mkdir()
    assert codex.collect(tmp_path / ".codex", now=NOW) == []


def test_a_damaged_index_line_is_skipped(tmp_path):
    root = build_codex(
        tmp_path, [("ggg77777", "Good", 120, ["task_complete"], "e:/p")]
    )
    with (root / "session_index.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("\n{ not json\n")

    assert len(codex.collect(root, now=NOW)) == 1


def test_an_index_entry_with_no_rollout_file_is_skipped(tmp_path):
    root = build_codex(tmp_path, [])
    (root / "session_index.jsonl").write_text(
        json.dumps({"id": "hhh88888", "thread_name": "Ghost", "updated_at": iso(NOW)}),
        encoding="utf-8",
    )

    assert codex.collect(root, now=NOW) == []


def test_no_message_content_reaches_the_output(tmp_path):
    # The feeder reads event types, never message bodies.
    root = tmp_path / ".codex"
    (root / "sessions" / "2026" / "09" / "01").mkdir(parents=True)
    (root / "session_index.jsonl").write_text(
        json.dumps(
            {"id": "iii99999", "thread_name": "T", "updated_at": iso(NOW - 200)}
        ),
        encoding="utf-8",
    )
    (root / "sessions" / "2026" / "09" / "01"
     / "rollout-2026-09-01T09-00-00-iii99999.jsonl").write_text(
        "\n".join([
            json.dumps({"type": "response_item", "payload": {
                "type": "message", "role": "user",
                "content": [{"type": "input_text", "text": "my secret prompt"}]}}),
            json.dumps({"type": "event_msg", "payload": {"type": "task_complete"},
                        "timestamp": iso(NOW - 200)}),
        ]),
        encoding="utf-8",
    )

    assert "secret prompt" not in json.dumps(codex.collect(root, now=NOW))


def test_items_match_the_contract(tmp_path):
    root = build_codex(
        tmp_path, [("jjj00000", "T", 120, ["task_complete"], "e:/p")]
    )

    raw = codex.collect(root, now=NOW)

    assert len(parse_tasks({"tasks": raw}).tasks) == len(raw)


def test_uses_the_real_clock_when_none_is_given(tmp_path):
    root = build_codex(
        tmp_path, [("kkk11111", "T", 0, ["task_complete"], "e:/p")]
    )
    # Rewrite the index timestamp to genuinely recent.
    (root / "session_index.jsonl").write_text(
        json.dumps(
            {"id": "kkk11111", "thread_name": "T",
             "updated_at": iso(time.time() - 200)}
        ),
        encoding="utf-8",
    )

    assert len(codex.collect(root)) == 1
