"""Turn Claude Code hook state into items.

Four small Claude Code hooks (in ``integrations/claude_code/``) write one
JSON record per session into a state directory:

    working     you are mid-conversation, or Claude is running
    background  Claude stopped but left tasks or scheduled work going
    waiting     Claude finished and it is your turn
    error       the turn ended in an API failure

This feeder reads that directory. It is the supported replacement for
``claude_sessions``, which infers the same thing from undocumented
transcript files. No prompt text passes through this path at all — the
record is project, state and a timestamp.

Install the hooks and set ``AGENT_HUD_FEEDERS=claude_hook``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ._claude_shared import DEFAULT_SKIP_WORDS, ago, pretty_project

# Older than this and a session is abandoned, not waiting on you. There is
# no settle delay: an official Stop event means Claude has finished.
STALE_SECONDS = 72 * 3600

_REQUIRED = ("session_id", "project_raw", "state", "at")

# state -> (needs_you, how to describe it)
_NEEDS_YOU = {"waiting": True, "error": True, "working": False, "background": False}


def _summary(state: str, age: float) -> str:
    """The one line the task list shows."""
    if state == "error":
        return "failed"
    if state == "background":
        return "working in background"
    if state == "waiting":
        return f"your turn - {ago(age)}"
    return "working"


def _detail(state: str, project: str, age: float) -> str:
    """The fuller text the detail screen shows.

    The hooks record when a session changed state and nothing about what
    it was doing, so this says only what is actually known. Claiming more
    would be inventing it.
    """
    when = ago(age)
    if state == "error":
        return f"The last run in {project} failed. Last change {when}."
    if state == "background":
        return f"{project} is still working in the background. Last change {when}."
    if state == "waiting":
        return f"{project} has finished and is waiting for you. Last change {when}."
    return f"{project} is working. Last change {when}."


def _read_record(
    path: Path, now: float, skip_words: tuple[str, ...]
) -> dict | None:
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(rec, dict) or any(k not in rec for k in _REQUIRED):
        return None

    state = rec["state"]
    if state not in _NEEDS_YOU:
        return None

    try:
        age = now - float(rec["at"])
    except (TypeError, ValueError):
        return None
    if age < 0 or age > STALE_SECONDS:
        return None

    project = pretty_project(str(rec["project_raw"]), skip_words) or "unnamed"
    return {
        "id": f"claude-{str(rec['session_id'])[:8]}",
        # When this version of the session was written. It moves whenever
        # the session changes state, which is exactly what a revision is
        # for: proof that what is on screen is still what the tool says.
        "revision": int(float(rec["at"])),
        "source": "Claude",
        "title": project,
        "summary": _summary(state, age),
        "detail": _detail(state, project, age),
        "needs_you": _NEEDS_YOU[state],
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
        skip_words: Generic folder names to drop when making a title.
    """
    moment = time.time() if now is None else now
    folder = Path(state_dir)
    if not folder.is_dir():
        return []

    items = []
    for path in sorted(folder.glob("*.json")):
        item = _read_record(path, moment, skip_words)
        if item is not None:
            items.append(item)

    items.sort(key=lambda i: not i["needs_you"])
    return items


__all__ = ["DEFAULT_SKIP_WORDS", "STALE_SECONDS", "collect"]
