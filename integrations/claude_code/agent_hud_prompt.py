#!/usr/bin/env python3
"""Claude Code `UserPromptSubmit` hook for Agent HUD.

Runs when you send Claude a prompt. Flips the session's record back to
"working" so it stops calling for your attention once you have replied.

The prompt text itself is never read or stored — only the state changes.

Always exits 0. See agent_hud_stop.py for install instructions.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

STATE = "working"


def _pretty(folder: str) -> str:
    import re

    parts = [p for p in re.split(r"[-/\\]", folder) if p]
    skip = {
        "projects", "projectos", "proyectos", "projekte", "projets",
        "code", "src", "repos", "repositories", "dev", "development",
        "workspace", "work", "documents", "users", "home",
    }
    while parts and parts[0].lower() in skip:
        parts.pop(0)
    return " ".join(parts).strip() or "unnamed"


def _state_dir() -> Path:
    override = os.environ.get("AGENT_HUD_CLAUDE_STATE")
    if override:
        return Path(override)
    return Path.home() / ".agent-hud" / "claude"


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    if not isinstance(data, dict):
        return

    session_id = str(data.get("session_id") or "").strip()
    if not session_id:
        return

    cwd = data.get("cwd") or os.getcwd()
    record = {
        "session_id": session_id,
        "project": _pretty(Path(cwd).name),
        "state": STATE,
        "at": time.time(),
    }

    try:
        state_dir = _state_dir()
        state_dir.mkdir(parents=True, exist_ok=True)
        target = state_dir / f"{session_id}.json"
        fd, tmp = tempfile.mkstemp(dir=state_dir, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh)
        os.replace(tmp, target)
    except OSError:
        return


if __name__ == "__main__":
    with contextlib.suppress(Exception):
        main()
    sys.exit(0)
