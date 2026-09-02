"""Tests for the Claude Code hook feeder and its hook scripts.

The hooks write one small JSON file per session into a state directory.
The feeder reads it. Neither touches a transcript, and the tests never
touch a real home directory — the state dir is always a tmp_path.
"""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agent_hud.tasks import parse_tasks
from feeders import claude_hook

NOW = 1_000_000.0

HOOK_DIR = Path(__file__).resolve().parents[1] / "integrations" / "claude_code"


def _fname(session_id: str) -> str:
    return hashlib.sha256(session_id.encode()).hexdigest()[:16] + ".json"


def write_state(state_dir, session_id, project_raw, state, age_seconds):
    state_dir.mkdir(parents=True, exist_ok=True)
    f = state_dir / _fname(session_id)
    f.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "project_raw": project_raw,
                "state": state,
                "at": NOW - age_seconds,
            }
        ),
        encoding="utf-8",
    )
    return f


# --- the feeder: state -> needs_you ------------------------------------


def test_a_waiting_session_needs_you_immediately(tmp_path):
    # No settle delay: an official Stop means Claude has finished.
    write_state(tmp_path, "abc12345", "bookshop", "waiting", age_seconds=1)

    items = claude_hook.collect(tmp_path, now=NOW)

    assert len(items) == 1
    assert items[0]["needs_you"] is True
    assert items[0]["title"] == "bookshop"
    assert items[0]["id"] == "claude-abc12345"


def test_a_working_session_does_not_need_you(tmp_path):
    write_state(tmp_path, "abc12345", "bookshop", "working", age_seconds=1)

    assert claude_hook.collect(tmp_path, now=NOW)[0]["needs_you"] is False


def test_a_session_with_background_work_does_not_need_you(tmp_path):
    # Claude stopped but left autonomous work running. Not your turn yet.
    write_state(tmp_path, "abc12345", "bookshop", "background", age_seconds=120)

    item = claude_hook.collect(tmp_path, now=NOW)[0]

    assert item["needs_you"] is False
    assert "background" in item["summary"]


def test_a_failed_session_needs_you(tmp_path):
    write_state(tmp_path, "abc12345", "bookshop", "error", age_seconds=30)

    item = claude_hook.collect(tmp_path, now=NOW)[0]

    assert item["needs_you"] is True
    assert item["summary"] == "failed"


def test_the_waiting_detail_carries_an_age(tmp_path):
    write_state(tmp_path, "abc12345", "bookshop", "waiting", age_seconds=3600)

    assert "1 h" in claude_hook.collect(tmp_path, now=NOW)[0]["summary"]


def test_an_abandoned_session_drops_out(tmp_path):
    write_state(
        tmp_path, "old00000", "old", "waiting",
        age_seconds=claude_hook.STALE_SECONDS + 60,
    )

    assert claude_hook.collect(tmp_path, now=NOW) == []


def test_a_negative_age_is_treated_as_stale(tmp_path):
    write_state(tmp_path, "s", "p", "waiting", age_seconds=-100)

    assert claude_hook.collect(tmp_path, now=NOW) == []


def test_things_waiting_on_you_come_first(tmp_path):
    write_state(tmp_path, "s1", "busy", "working", age_seconds=300)
    write_state(tmp_path, "s2", "waiting-proj", "waiting", age_seconds=300)
    write_state(tmp_path, "s3", "failed-proj", "error", age_seconds=300)

    titles = [i["title"] for i in claude_hook.collect(tmp_path, now=NOW)]

    assert titles.index("busy") == len(titles) - 1  # working is last


# --- the feeder: titles and robustness -------------------------------


def test_the_feeder_prettifies_the_raw_project_name(tmp_path):
    write_state(tmp_path, "s", "c--Projects-my-api", "waiting", age_seconds=120)

    assert claude_hook.collect(tmp_path, now=NOW)[0]["title"] == "my api"


def test_skip_words_reach_the_feeder(tmp_path):
    write_state(tmp_path, "s", "acme-widgets", "waiting", age_seconds=120)

    title = claude_hook.collect(
        tmp_path, now=NOW, skip_words=(*claude_hook.DEFAULT_SKIP_WORDS, "acme")
    )[0]["title"]

    assert title == "widgets"


def test_a_missing_state_directory_is_not_fatal(tmp_path):
    assert claude_hook.collect(tmp_path / "nope", now=NOW) == []


def test_a_damaged_state_file_is_skipped(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "broken.json").write_text("{ half written", encoding="utf-8")

    assert claude_hook.collect(tmp_path, now=NOW) == []


def test_a_state_file_missing_fields_is_skipped(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "partial.json").write_text(
        json.dumps({"session_id": "x"}), encoding="utf-8"
    )

    assert claude_hook.collect(tmp_path, now=NOW) == []


def test_an_unknown_state_string_is_skipped(tmp_path):
    write_state(tmp_path, "s", "p", "confused", age_seconds=120)

    assert claude_hook.collect(tmp_path, now=NOW) == []


def test_no_prompt_text_anywhere_in_the_output(tmp_path):
    write_state(tmp_path, "abc12345", "bookshop", "waiting", age_seconds=3600)

    assert "prompt" not in json.dumps(claude_hook.collect(tmp_path, now=NOW)).lower()


def test_items_match_the_contract(tmp_path):
    write_state(tmp_path, "abc12345", "bookshop", "waiting", age_seconds=120)

    raw = claude_hook.collect(tmp_path, now=NOW)

    assert len(parse_tasks({"tasks": raw}).tasks) == len(raw)


def test_uses_the_real_clock_when_none_is_given(tmp_path):
    write_state(tmp_path, "s1", "now", "waiting", age_seconds=0)
    f = tmp_path / _fname("s1")
    rec = json.loads(f.read_text())
    rec["at"] = time.time() - 300
    f.write_text(json.dumps(rec), encoding="utf-8")

    assert len(claude_hook.collect(tmp_path)) == 1


# --- the hook scripts ------------------------------------------------


def run_hook(script, payload, env_extra=None):
    """Run a hook the way Claude Code does: JSON on stdin, environment set."""
    import os

    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        [sys.executable, str(HOOK_DIR / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


HOOK_SCRIPTS = [
    "agent_hud_stop.py",
    "agent_hud_prompt.py",
    "agent_hud_stop_failure.py",
    "agent_hud_session_end.py",
]


@pytest.mark.parametrize("script", HOOK_SCRIPTS)
def test_hook_scripts_exist(script):
    assert (HOOK_DIR / script).is_file()


@pytest.mark.parametrize("script", HOOK_SCRIPTS)
def test_a_hook_with_no_stdin_exits_cleanly(script):
    r = subprocess.run(
        [sys.executable, str(HOOK_DIR / script)],
        input="",
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0


@pytest.mark.parametrize("script", HOOK_SCRIPTS)
def test_a_hook_never_blocks_claude_even_on_a_bad_state_dir(script, tmp_path):
    blocker = tmp_path / "iamafile"
    blocker.write_text("x", encoding="utf-8")

    r = run_hook(
        script,
        {"session_id": "s", "cwd": "."},
        {"AGENT_HUD_CLAUDE_STATE": str(blocker / "under" / "here")},
    )
    assert r.returncode == 0


def test_stop_with_no_background_work_writes_waiting(tmp_path):
    state = tmp_path / "state"

    r = run_hook(
        "agent_hud_stop.py",
        {"session_id": "s1", "cwd": "/home/me/workspace/my-app"},
        {"AGENT_HUD_CLAUDE_STATE": str(state)},
    )

    assert r.returncode == 0, r.stderr
    rec = json.loads((state / _fname("s1")).read_text(encoding="utf-8"))
    assert rec["state"] == "waiting"
    assert rec["project_raw"] == "my-app"
    assert "prompt" not in json.dumps(rec).lower()


@pytest.mark.parametrize(
    "payload_extra",
    [
        {"background_tasks": [{"id": "t1"}]},
        {"session_crons": [{"id": "c1"}]},
        {"background_tasks": [], "session_crons": [{"id": "c1"}]},
    ],
)
def test_stop_with_background_work_writes_background(tmp_path, payload_extra):
    state = tmp_path / "state"

    run_hook(
        "agent_hud_stop.py",
        {"session_id": "s2", "cwd": "/p", **payload_extra},
        {"AGENT_HUD_CLAUDE_STATE": str(state)},
    )

    rec = json.loads((state / _fname("s2")).read_text(encoding="utf-8"))
    assert rec["state"] == "background"


def test_prompt_hook_writes_working(tmp_path):
    state = tmp_path / "state"

    run_hook(
        "agent_hud_stop.py",
        {"session_id": "s3", "cwd": "/p"},
        {"AGENT_HUD_CLAUDE_STATE": str(state)},
    )
    r = run_hook(
        "agent_hud_prompt.py",
        {"session_id": "s3", "cwd": "/p", "prompt": "do not store me"},
        {"AGENT_HUD_CLAUDE_STATE": str(state)},
    )

    assert r.returncode == 0, r.stderr
    rec = json.loads((state / _fname("s3")).read_text(encoding="utf-8"))
    assert rec["state"] == "working"
    assert "do not store me" not in json.dumps(rec)


def test_stop_failure_hook_writes_error(tmp_path):
    state = tmp_path / "state"

    r = run_hook(
        "agent_hud_stop_failure.py",
        {"session_id": "s4", "cwd": "/p", "error": "rate limited"},
        {"AGENT_HUD_CLAUDE_STATE": str(state)},
    )

    assert r.returncode == 0, r.stderr
    rec = json.loads((state / _fname("s4")).read_text(encoding="utf-8"))
    assert rec["state"] == "error"
    assert "rate limited" not in json.dumps(rec)  # error contents not stored


def test_session_end_hook_removes_the_record(tmp_path):
    state = tmp_path / "state"

    run_hook(
        "agent_hud_stop.py",
        {"session_id": "s5", "cwd": "/p"},
        {"AGENT_HUD_CLAUDE_STATE": str(state)},
    )
    assert (state / _fname("s5")).exists()

    r = run_hook(
        "agent_hud_session_end.py",
        {"session_id": "s5", "cwd": "/p"},
        {"AGENT_HUD_CLAUDE_STATE": str(state)},
    )

    assert r.returncode == 0, r.stderr
    assert not (state / _fname("s5")).exists()


def test_session_end_on_an_already_gone_record_is_fine(tmp_path):
    r = run_hook(
        "agent_hud_session_end.py",
        {"session_id": "never-existed", "cwd": "/p"},
        {"AGENT_HUD_CLAUDE_STATE": str(tmp_path / "state")},
    )
    assert r.returncode == 0


def test_the_filename_is_a_hash_not_the_raw_session_id(tmp_path):
    state = tmp_path / "state"
    weird = "../../etc/passwd"

    run_hook(
        "agent_hud_stop.py",
        {"session_id": weird, "cwd": "/p"},
        {"AGENT_HUD_CLAUDE_STATE": str(state)},
    )

    written = list(state.glob("*.json"))
    assert len(written) == 1
    assert written[0].name == _fname(weird)
    assert ".." not in written[0].name


def test_the_full_lifecycle_round_trips(tmp_path):
    state = tmp_path / "state"
    env = {"AGENT_HUD_CLAUDE_STATE": str(state)}
    sid = {"session_id": "s", "cwd": "/home/me/my-project"}

    run_hook("agent_hud_prompt.py", sid, env)
    assert claude_hook.collect(state)[0]["needs_you"] is False  # working

    run_hook("agent_hud_stop.py", sid, env)
    assert claude_hook.collect(state)[0]["needs_you"] is True  # waiting

    run_hook("agent_hud_prompt.py", sid, env)
    run_hook("agent_hud_stop_failure.py", {**sid, "error": "boom"}, env)
    item = claude_hook.collect(state)[0]
    assert item["needs_you"] is True and item["summary"] == "failed"

    run_hook("agent_hud_session_end.py", sid, env)
    assert claude_hook.collect(state) == []
