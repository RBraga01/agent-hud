"""Shared by the four Agent HUD hook scripts.

The hooks are dumb on purpose: they read the Claude Code payload from
stdin, write one small JSON record per session, and always exit 0. All
presentation — turning a folder name into a readable title — is the
feeder's job, not theirs.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path


def state_dir() -> Path:
    override = os.environ.get("AGENT_HUD_CLAUDE_STATE")
    if override:
        return Path(override)
    return Path.home() / ".agent-hud" / "claude"


def _record_path(directory: Path, session_id: str) -> Path:
    """A hashed filename, so an arbitrary session id can never be a path."""
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
    return directory / f"{digest}.json"


def read_payload() -> dict | None:
    """The Claude Code hook input. None if there is nothing usable."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def session_id(payload: dict) -> str:
    return str(payload.get("session_id") or "").strip()


def project_raw(payload: dict) -> str:
    """The last path segment of the session's directory, unprettified."""
    cwd = payload.get("cwd") or os.getcwd()
    return Path(str(cwd)).name


def write_record(state: str, payload: dict) -> None:
    """Write this session's record atomically. Never raises."""
    sid = session_id(payload)
    if not sid:
        return
    record = {
        "session_id": sid,
        "project_raw": project_raw(payload),
        "state": state,
        "at": time.time(),
    }
    try:
        directory = state_dir()
        directory.mkdir(parents=True, exist_ok=True)
        target = _record_path(directory, sid)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh)
        os.replace(tmp, target)
    except OSError:
        return


def remove_record(payload: dict) -> None:
    """Delete this session's record. Fine if it is already gone."""
    sid = session_id(payload)
    if not sid:
        return
    try:
        _record_path(state_dir(), sid).unlink(missing_ok=True)
    except OSError:
        return


def has_background_work(payload: dict) -> bool:
    """True when Claude stopped but left autonomous work running.

    `Stop` carries `background_tasks` and `session_crons` so an integration
    can tell "session done" from "session paused, work still pending".
    Absent fields (older Claude Code) read as no background work.
    """
    for key in ("background_tasks", "session_crons"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return True
    return False
