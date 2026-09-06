"""Turn Codex CLI sessions into items.

Codex writes append-only session logs as ``rollout-<timestamp>-<id>.jsonl``
under a date-nested tree, ``<codex_dir>/sessions/YYYY/MM/DD/``, and a
one-line-per-session index at ``<codex_dir>/session_index.jsonl``. This
feeder reads the index for a human title and last-activity time, then
tails the matching session log to work out whose turn it is:

    last terminal event is task_complete  -> your turn
    last terminal event is task_started   -> Codex is working
    an error event is last                -> failed

``<codex_dir>/archived_sessions/`` is a sibling of ``sessions/`` and is
left alone: an archived session is one the user has already put away.

Only sessions touched in the last three days are shown, matching the
Claude feeders. A slash command stored as the session name
(``<command-message>init</command-message>``) is treated as no title, and
the project folder is used instead.

Like the ``claude`` feeder this reads an undocumented on-disk format and
may need updating if Codex changes it. A Codex-native hook, if one lands,
would be the supported replacement — the same step ``claude_hook`` was
for ``claude``.

No message bodies are read — only event types.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from ._claude_shared import DEFAULT_SKIP_WORDS, ago, pretty_project

STALE_SECONDS = 72 * 3600

# How many trailing lines of a session log to inspect for the last event.
TAIL_LINES = 400

_TERMINAL = {"task_complete", "task_started"}
_ERROR = {"error", "stream_error", "turn_failed", "turn_aborted"}

# Codex stores a slash-command invocation as the session name, wrapped in
# a tag: "<command-message>init</command-message>",
# "<command-name>/clear</command-name>". That names a command, not a piece
# of work, so it is not a usable title.
_COMMAND_WRAPPER = re.compile(r"^<command-[a-z]+>.*</command-[a-z]+>$", re.DOTALL)


def _clean_title(raw: str) -> str:
    """A human title from the index's ``thread_name``, or ``""`` when there
    isn't one. ``collect`` falls back to the project folder on ``""``."""
    text = raw.strip()
    if not text or _COMMAND_WRAPPER.match(text):
        return ""
    return text


def _iso_to_epoch(value: str) -> float | None:
    """Parse Codex's ISO-8601 timestamps (``Z`` suffix, long fractions)."""
    import datetime

    text = value.strip().replace("Z", "+00:00")
    if "." in text:
        head, rest = text.split(".", 1)
        frac = "".join(c for c in rest if c.isdigit())[:6]
        tz = rest[len(frac):] if not rest[len(frac):].isdigit() else ""
        # keep whatever timezone marker trailed the fraction
        tz = rest.lstrip("0123456789")
        text = f"{head}.{frac or '0'}{tz}"
    try:
        return datetime.datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _read_index(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            entry = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(entry, dict) and entry.get("id"):
            out.append(entry)
    return out


def _find_rollout(sessions_dir: Path, session_id: str) -> Path | None:
    for path in sessions_dir.rglob(f"rollout-*-{session_id}.jsonl"):
        return path
    return None


def _tail(path: Path, lines: int) -> list[str]:
    try:
        all_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return all_lines[-lines:]


def _state_and_cwd(rollout: Path) -> tuple[str, str]:
    """Return (state, cwd). state is 'waiting', 'working' or 'error'.

    The last terminal or error event in the log wins: a `task_complete`
    followed by a fresh `task_started` means a new turn is running.
    """
    cwd = ""
    state = "working"
    for line in _tail(rollout, TAIL_LINES):
        try:
            entry = json.loads(line)
        except (ValueError, TypeError):
            continue
        payload = entry.get("payload") if isinstance(entry, dict) else None
        if not isinstance(payload, dict):
            continue
        if not cwd and payload.get("cwd"):
            cwd = str(payload["cwd"])
        if entry.get("type") == "event_msg":
            etype = payload.get("type")
            if etype in _ERROR:
                state = "error"
            elif etype == "task_complete":
                state = "waiting"
            elif etype == "task_started":
                state = "working"
    return state, cwd


def _summary(state: str, age: float) -> str:
    """The one line the task list shows."""
    if state == "error":
        return "failed"
    if state == "waiting":
        return f"your turn - {ago(age)}"
    return "working"


def _detail(state: str, title: str, age: float) -> str:
    """The fuller text the detail screen shows.

    The session log records that a turn ended, not what it was about, so
    this says only what is actually known.
    """
    when = ago(age)
    if state == "error":
        return f"The last turn in {title} failed. Last activity {when}."
    if state == "waiting":
        return (
            f"{title} has finished its turn and is waiting for you. "
            f"Last activity {when}."
        )
    return f"{title} is working. Last activity {when}."


def collect(
    codex_dir: Path | str,
    *,
    now: float | None = None,
    skip_words: tuple[str, ...] = DEFAULT_SKIP_WORDS,
) -> list[dict]:
    """Recent Codex sessions, the ones waiting on you first.

    Args:
        codex_dir: The ``.codex`` directory. Passed in rather than found,
            so tests never touch a real home directory.
        now: Current time in seconds. Defaults to the real clock.
        skip_words: Generic folder names to drop when making a title.
    """
    moment = time.time() if now is None else now
    root = Path(codex_dir)
    index = root / "session_index.jsonl"
    sessions_dir = root / "sessions"
    if not index.is_file() or not sessions_dir.is_dir():
        return []

    items = []
    for entry in _read_index(index):
        updated = _iso_to_epoch(str(entry.get("updated_at", "")))
        if updated is None:
            continue
        age = moment - updated
        if age < 0 or age > STALE_SECONDS:
            continue

        rollout = _find_rollout(sessions_dir, str(entry["id"]))
        if rollout is None:
            continue

        state, cwd = _state_and_cwd(rollout)
        title = _clean_title(str(entry.get("thread_name") or ""))
        if not title:
            title = pretty_project(Path(cwd).name, skip_words) if cwd else "unnamed"

        items.append(
            {
                "id": f"codex-{str(entry['id'])[:8]}",
                # When this version of the session was last updated. It
                # moves whenever the session does, which is what makes it
                # usable as a revision.
                "revision": int(updated),
                "source": "Codex",
                "title": title,
                "summary": _summary(state, age),
                "detail": _detail(state, title, age),
                "needs_you": state in ("waiting", "error"),
            }
        )

    items.sort(key=lambda i: not i["needs_you"])
    return items


__all__ = ["STALE_SECONDS", "collect"]
