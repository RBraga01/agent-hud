"""Tests for the Claude Code hook feeder.

The hook writes one small JSON file per session into a state directory.
The feeder reads that directory. Neither touches a transcript, and the
tests never touch a real home directory — the state dir is a tmp_path.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agent_hud.items import parse_items
from feeders import claude_hook

NOW = 1_000_000.0

HOOK_DIR = Path(__file__).resolve().parents[1] / "integrations" / "claude_code"


def write_state(state_dir, session_id, project, state, age_seconds):
    state_dir.mkdir(parents=True, exist_ok=True)
    f = state_dir / f"{session_id}.json"
    f.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "project": project,
                "state": state,
                "at": NOW - age_seconds,
            }
        ),
        encoding="utf-8",
    )
    return f


# --- the feeder -----------------------------------------------------------


def test_a_waiting_session_needs_you(tmp_path):
    write_state(tmp_path, "abc12345", "Bookshop", "waiting", age_seconds=120)

    items = claude_hook.collect(tmp_path, now=NOW)

    assert len(items) == 1
    assert items[0]["needs_you"] is True
    assert items[0]["title"] == "Bookshop"
    assert items[0]["id"] == "claude-abc12345"


def test_a_working_session_does_not_need_you(tmp_path):
    write_state(tmp_path, "abc12345", "Bookshop", "working", age_seconds=120)

    assert claude_hook.collect(tmp_path, now=NOW)[0]["needs_you"] is False


def test_a_session_that_just_stopped_is_given_a_moment(tmp_path):
    write_state(tmp_path, "abc12345", "Bookshop", "waiting", age_seconds=5)

    assert claude_hook.collect(tmp_path, now=NOW)[0]["needs_you"] is False


def test_an_abandoned_session_drops_out(tmp_path):
    write_state(
        tmp_path, "old00000", "Old", "waiting",
        age_seconds=claude_hook.STALE_SECONDS + 60,
    )

    assert claude_hook.collect(tmp_path, now=NOW) == []


def test_things_waiting_on_you_come_first(tmp_path):
    write_state(tmp_path, "s1", "Busy", "working", age_seconds=300)
    write_state(tmp_path, "s2", "Waiting", "waiting", age_seconds=300)

    assert claude_hook.collect(tmp_path, now=NOW)[0]["title"] == "Waiting"


def test_a_missing_state_directory_is_not_fatal(tmp_path):
    assert claude_hook.collect(tmp_path / "nope", now=NOW) == []


def test_a_damaged_state_file_is_skipped_not_fatal(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "broken.json").write_text("{ half written", encoding="utf-8")

    assert claude_hook.collect(tmp_path, now=NOW) == []


def test_a_state_file_missing_fields_is_skipped(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "partial.json").write_text(
        json.dumps({"session_id": "x"}), encoding="utf-8"
    )

    assert claude_hook.collect(tmp_path, now=NOW) == []


def test_the_detail_never_carries_prompt_text(tmp_path):
    # The hook path deliberately records no prompt. The detail is state
    # plus age, nothing the wearer wrote.
    write_state(tmp_path, "abc12345", "Bookshop", "waiting", age_seconds=3600)

    detail = claude_hook.collect(tmp_path, now=NOW)[0]["detail"]

    assert "your turn" in detail
    assert "h" in detail  # an age like "1 h"


def test_items_match_the_contract(tmp_path):
    write_state(tmp_path, "abc12345", "Bookshop", "waiting", age_seconds=120)

    raw = claude_hook.collect(tmp_path, now=NOW)

    assert len(parse_items({"items": raw})) == len(raw)


def test_uses_the_real_clock_when_none_is_given(tmp_path):
    f = write_state(tmp_path, "s1", "Now", "waiting", age_seconds=0)
    recent = time.time() - 300
    import os

    os.utime(f, (recent, recent))
    # rewrite "at" to a real recent timestamp too
    f.write_text(
        json.dumps(
            {"session_id": "s1", "project": "Now", "state": "waiting", "at": recent}
        ),
        encoding="utf-8",
    )

    assert len(claude_hook.collect(tmp_path)) == 1


# --- the hook scripts ---------------------------------------------------


def run_hook(script, payload, env_extra=None):
    """Run a hook script the way Claude Code does: JSON on stdin, cwd set."""
    import os

    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        [sys.executable, str(HOOK_DIR / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.parametrize("script", ["agent_hud_stop.py", "agent_hud_prompt.py"])
def test_hook_scripts_exist(script):
    assert (HOOK_DIR / script).is_file()


def test_stop_hook_writes_a_waiting_record(tmp_path):
    proj = tmp_path / "workspace" / "my-app"
    proj.mkdir(parents=True)
    state = tmp_path / "state"

    r = run_hook(
        "agent_hud_stop.py",
        {"session_id": "sess-0001", "cwd": str(proj), "hook_event_name": "Stop"},
        {"AGENT_HUD_CLAUDE_STATE": str(state)},
    )

    assert r.returncode == 0, r.stderr
    rec = json.loads((state / "sess-0001.json").read_text(encoding="utf-8"))
    assert rec["state"] == "waiting"
    assert rec["project"] == "my app"
    assert isinstance(rec["at"], (int, float))


def test_prompt_hook_writes_a_working_record(tmp_path):
    proj = tmp_path / "workspace" / "my-app"
    proj.mkdir(parents=True)
    state = tmp_path / "state"

    run_hook(
        "agent_hud_stop.py",
        {"session_id": "sess-0002", "cwd": str(proj)},
        {"AGENT_HUD_CLAUDE_STATE": str(state)},
    )
    r = run_hook(
        "agent_hud_prompt.py",
        {"session_id": "sess-0002", "cwd": str(proj), "prompt": "do the thing"},
        {"AGENT_HUD_CLAUDE_STATE": str(state)},
    )

    assert r.returncode == 0, r.stderr
    rec = json.loads((state / "sess-0002.json").read_text(encoding="utf-8"))
    assert rec["state"] == "working"
    assert "do the thing" not in json.dumps(rec)  # prompt is never stored


def test_a_hook_with_no_stdin_exits_cleanly(tmp_path):
    r = subprocess.run(
        [sys.executable, str(HOOK_DIR / "agent_hud_stop.py")],
        input="",
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0


def test_a_hook_never_blocks_claude_even_on_a_bad_state_dir(tmp_path):
    # A path whose parent is a regular file cannot be turned into a
    # directory. The hook must still exit 0 — a non-zero exit would
    # interfere with Claude Code itself.
    blocker = tmp_path / "iamafile"
    blocker.write_text("x", encoding="utf-8")

    r = run_hook(
        "agent_hud_stop.py",
        {"session_id": "s", "cwd": "."},
        {"AGENT_HUD_CLAUDE_STATE": str(blocker / "under" / "here")},
    )
    assert r.returncode == 0


def test_stop_then_prompt_then_stop_round_trips(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    state = tmp_path / "state"
    env = {"AGENT_HUD_CLAUDE_STATE": str(state)}

    run_hook("agent_hud_stop.py", {"session_id": "s", "cwd": str(proj)}, env)
    assert json.loads((state / "s.json").read_text())["state"] == "waiting"

    run_hook("agent_hud_prompt.py", {"session_id": "s", "cwd": str(proj)}, env)
    assert json.loads((state / "s.json").read_text())["state"] == "working"

    run_hook("agent_hud_stop.py", {"session_id": "s", "cwd": str(proj)}, env)
    assert json.loads((state / "s.json").read_text())["state"] == "waiting"
