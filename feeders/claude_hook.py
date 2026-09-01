"""Turn Claude Code hook state into items.

A Claude Code ``Stop`` hook writes one small JSON file per session into a
state directory when Claude finishes a turn; a ``UserPromptSubmit`` hook
flips it back when you reply. This feeder reads that directory.

This is the supported replacement for ``claude_sessions``, which infers
the same thing from undocumented transcript files. Install the hooks
(see ``integrations/claude_code/``) and set ``AGENT_HUD_FEEDERS=claude_hook``.

No prompt text passes through this path at all — the hook records only
the project, the state and a timestamp.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ._claude_shared import DEFAULT_SKIP_WORDS, ago, pretty_project

# Claude may still be settling after a turn; don't call for attention at once.
SETTLE_SECONDS = 45

# Older than this and a session is abandoned, not waiting on you.
STALE_SECONDS = 72 * 3600

_REQUIRED = ("session_id", "project", "state", "at")


def _read_record(path: Path, now: float) -> dict | None:
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(rec, dict) or any(k not in rec for k in _REQUIRED):
        return None

    try:
        age = now - float(rec["at"])
    except (TypeError, ValueError):
        return None
    if age > STALE_SECONDS or age < 0:
        return None

    waiting = rec["state"] == "waiting" and age > SETTLE_SECONDS
    detail = ("your turn" if waiting else "working") + (
        f" - {ago(age)}" if waiting else ""
    )
    return {
        "id": f"claude-{str(rec['session_id'])[:8]}",
        "title": str(rec["project"]) or "unnamed",
        "detail": detail,
        "needs_you": waiting,
    }


def collect(
    state_dir: Path | str,
    *,
    now: float | None = None,
    skip_words: tuple[str, ...] = DEFAULT_SKIP_WORDS,
) -> list[dict]:
    """Every recent session in *state_dir*, the ones waiting on you first.

    Args:
        state_dir: Directory the hooks write into. Passed in rather than
            found, so tests never touch a real home directory.
        now: Current time in seconds. Defaults to the real clock.
        skip_words: Unused here; accepted so the two Claude feeders share
            a signature. Titles are already prettified by the hook.
    """
    moment = time.time() if now is None else now
    folder = Path(state_dir)
    if not folder.is_dir():
        return []

    items = []
    for path in sorted(folder.glob("*.json")):
        item = _read_record(path, moment)
        if item is not None:
            items.append(item)

    items.sort(key=lambda i: not i["needs_you"])
    return items


# The hooks themselves want pretty_project; re-export so a single import
# from feeders.claude_hook covers writing and reading.
__all__ = ["SETTLE_SECONDS", "STALE_SECONDS", "collect", "pretty_project"]
