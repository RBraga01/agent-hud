#!/usr/bin/env python3
"""Claude Code `Stop` hook for Agent HUD.

Claude Code runs this when it finishes a turn. It records that the session
is now waiting on you, in a small per-session file the `claude_hook` feeder
reads.

Install by adding to `~/.claude/settings.json`:

    {
      "hooks": {
        "Stop": [
          {"hooks": [{"type": "command",
            "command": "python /abs/path/to/agent_hud_stop.py"}]}
        ],
        "UserPromptSubmit": [
          {"hooks": [{"type": "command",
            "command": "python /abs/path/to/agent_hud_prompt.py"}]}
        ]
      }
    }

Always exits 0. It must never interfere with Claude Code itself.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

STATE = "waiting"


def _pretty(folder: str) -> str:
    """A readable project name from a path segment. Mirrors the feeder."""
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
        # Write-then-rename, so a reader never sees a half-written file.
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
