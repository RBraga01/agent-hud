"""Turn OpenCode sessions into items.

Unlike the Claude and Codex feeders, there is no per-session log file to
tail: OpenCode keeps everything in one SQLite database,
``opencode.db``, under its data directory (``~/.local/share/opencode`` on
this setup). This feeder opens that database **read-only** and never
writes to it.

Whose turn it is comes from the newest row in ``message`` for a session:

    role == "assistant", time.completed set, finish is a clean stop
        -> your turn
    role == "assistant", time.completed set, finish is an error/abort
        -> failed
    role == "assistant", no time.completed  (still generating, or the run
        was interrupted)                     -> working
    role == "user"  (you sent something, no reply row yet)
        -> working

Only sessions touched in the last three days are shown, matching the
Claude and Codex feeders. Archived sessions (``time_archived`` set) are
left alone. OpenCode's auto-generated title (``New session - <ISO>``) is
treated as no title, and the project folder is used instead.

Timestamps in the database are milliseconds.

Undocumented format, like ``claude`` and ``codex``. If OpenCode changes
its schema this feeder may need updating; a bad read returns nothing
rather than raising.

No message text is read -- only role, timing and the finish reason.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

from ._claude_shared import DEFAULT_SKIP_WORDS, ago, pretty_project

STALE_SECONDS = 72 * 3600

DEFAULT_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"

# OpenCode names a fresh session "New session - 2026-09-07T11:44:02.472Z"
# until something better is generated. That is not a human title.
_AUTO_TITLE = re.compile(r"^New session - \d{4}-\d{2}-\d{2}T[\d:.]+Z?$")

# finish reasons that mean the turn ended badly rather than normally.
_BAD_FINISH = {"error", "aborted", "cancelled", "canceled"}


def _connect_readonly(db_path: Path) -> sqlite3.Connection | None:
    """A read-only connection, or None if the file is not there / not a db."""
    if not db_path.is_file():
        return None
    try:
        conn = sqlite3.connect(
            f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=2.0
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        return conn
    except sqlite3.Error:
        return None


def _state(last_message: dict) -> str:
    """'waiting', 'working' or 'error' from a session's newest message."""
    if last_message.get("role") != "assistant":
        # the user's line is the newest -> OpenCode has not answered yet
        return "working"
    completed = (last_message.get("time") or {}).get("completed")
    if not completed:
        return "working"
    if str(last_message.get("finish") or "").lower() in _BAD_FINISH:
        return "error"
    return "waiting"


def _summary(state: str, age: float) -> str:
    if state == "error":
        return "failed"
    if state == "waiting":
        return f"your turn - {ago(age)}"
    return "working"


def _detail(state: str, title: str, age: float) -> str:
    when = ago(age)
    if state == "error":
        return f"The last turn in {title} failed. Last activity {when}."
    if state == "waiting":
        return (
            f"{title} has finished its turn and is waiting for you. "
            f"Last activity {when}."
        )
    return f"{title} is working. Last activity {when}."


def _title(raw: str, directory: str, skip_words: tuple[str, ...]) -> str:
    text = raw.strip()
    if text and not _AUTO_TITLE.match(text):
        return text
    if directory:
        return pretty_project(Path(directory).name, skip_words)
    return "unnamed"


def collect(
    db_path: Path | str | None = None,
    *,
    now: float | None = None,
    skip_words: tuple[str, ...] = DEFAULT_SKIP_WORDS,
) -> list[dict]:
    """Recent OpenCode sessions, the ones waiting on you first.

    Args:
        db_path: The ``opencode.db`` file. Defaults to the standard
            location; passed in by tests so they never touch a real one.
        now: Current time in seconds. Defaults to the real clock.
        skip_words: Generic folder names to drop when making a title.
    """
    moment = time.time() if now is None else now
    conn = _connect_readonly(Path(db_path) if db_path else DEFAULT_DB)
    if conn is None:
        return []

    items = []
    try:
        sessions = conn.execute(
            "SELECT id, title, directory, time_updated "
            "FROM session WHERE time_archived IS NULL"
        ).fetchall()
        for s in sessions:
            updated = int(s["time_updated"]) / 1000.0
            age = moment - updated
            if age < 0 or age > STALE_SECONDS:
                continue

            row = conn.execute(
                "SELECT data FROM message WHERE session_id = ? "
                "ORDER BY time_created DESC LIMIT 1",
                (s["id"],),
            ).fetchone()
            if row is None:
                continue
            try:
                last = json.loads(row["data"])
            except (ValueError, TypeError):
                continue
            if not isinstance(last, dict):
                continue

            state = _state(last)
            title = _title(s["title"] or "", s["directory"] or "", skip_words)

            items.append(
                {
                    "id": f"opencode-{str(s['id']).removeprefix('ses_')[:12]}",
                    "revision": int(updated),
                    "source": "OpenCode",
                    "title": title,
                    "summary": _summary(state, age),
                    "detail": _detail(state, title, age),
                    "needs_you": state in ("waiting", "error"),
                }
            )
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    items.sort(key=lambda i: not i["needs_you"])
    return items


__all__ = ["DEFAULT_DB", "STALE_SECONDS", "collect"]
