"""Turn live Claude Code sessions into items.

Claude Code writes a transcript per session under ``~/.claude/projects``.
The last entry in one says whose turn it is: an assistant entry means
Claude has stopped and is waiting on you.

Two warnings about this module.

**The format is undocumented.** Nothing promises these files keep their
shape, so this can stop working without notice. It earns its place by
needing no setup at all. When you want this running for real, a Claude
Code ``Stop`` hook is the supported mechanism and should replace it.

**Your prompt text stays off by default.** It is your own writing, and
switching it on puts it on a display and into a file on disk. See
``show_prompts``.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

# Claude may still be mid-reply; do not call for attention immediately.
SETTLE_SECONDS = 45

# Older than this and a session is abandoned, not waiting on you.
STALE_SECONDS = 72 * 3600

# A row is about 530px wide at body size, which is roughly this many
# characters. Longer than this and the text runs past its own outline.
MAX_DETAIL = 30

# Transcripts grow without limit and are re-read on every poll. Only the
# end matters — whose turn it is, and the last prompt — so reading the
# whole file would be megabytes of pointless work every few seconds.
TAIL_BYTES = 64 * 1024

# Folder names that describe where code is kept rather than which project
# it is. Dropped from the front of a name so the project itself is what
# shows. Several languages, because none of this should assume one
# person's machine. Add your own with AGENT_HUD_SKIP_PATH_WORDS.
DEFAULT_SKIP_WORDS = (
    "projects", "projectos", "proyectos", "projekte", "projets",
    "code", "src", "repos", "repositories", "dev", "development",
    "workspace", "work", "documents", "users", "home",
)

_DRIVE = re.compile(r"^([a-zA-Z])--")


def pretty_project(
    folder: str, skip_words: tuple[str, ...] = DEFAULT_SKIP_WORDS
) -> str:
    """Turn an encoded folder name into something worth reading.

    ``e--Projects-api-core`` becomes ``api core``. The leading drive and
    any generic container folders are dropped; what is left is the project.
    """
    drive = _DRIVE.match(folder)
    letter = drive.group(1).upper() if drive else ""
    rest = folder[drive.end():] if drive else folder

    lower = {w.lower() for w in skip_words}
    parts = [p for p in rest.split("-") if p]
    while parts and parts[0].lower() in lower:
        parts.pop(0)

    name = " ".join(parts).strip()
    if name:
        return name
    return f"{letter} drive" if letter else "unnamed"


def _ago(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{max(minutes, 1)} min"
    hours = minutes // 60
    return f"{hours} h" if hours < 24 else f"{hours // 24} d"


def _tail_lines(path: Path) -> list[str]:
    """The last stretch of a transcript, as lines.

    The first line of the chunk is usually cut in half, which is harmless:
    unparseable lines are skipped anyway.
    """
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - TAIL_BYTES))
            chunk = handle.read()
    except OSError:
        return []
    return chunk.decode("utf-8", errors="replace").splitlines()


def _last_role_and_prompt(path: Path) -> tuple[str | None, str | None]:
    """Read backwards for whose turn it is, and the last thing you asked."""
    lines = _tail_lines(path)
    if not lines:
        return None, None

    role: str | None = None
    prompt: str | None = None
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(entry, dict):
            continue
        kind = entry.get("type")
        if role is None and kind in ("assistant", "user"):
            role = kind
        if prompt is None and kind == "last-prompt":
            prompt = (entry.get("lastPrompt") or "").strip() or None
        if role and prompt:
            break
    return role, prompt


def _read_session(
    path: Path, now: float, show_prompts: bool, skip_words: tuple[str, ...]
) -> dict | None:
    try:
        age = now - path.stat().st_mtime
    except OSError:
        return None
    if age > STALE_SECONDS:
        return None

    role, prompt = _last_role_and_prompt(path)
    if role is None:
        return None

    waiting = role == "assistant" and age > SETTLE_SECONDS

    if show_prompts and prompt:
        detail = (
            prompt
            if len(prompt) <= MAX_DETAIL
            else prompt[: MAX_DETAIL - 1] + "..."
        )
    else:
        detail = "your turn" if waiting else "working"
    if waiting:
        detail = f"{detail} - {_ago(age)}"

    return {
        "id": f"claude-{path.stem[:8]}",
        "title": pretty_project(path.parent.name, skip_words),
        "detail": detail,
        "needs_you": waiting,
    }


def collect(
    root: Path | str,
    *,
    now: float | None = None,
    show_prompts: bool = False,
    skip_words: tuple[str, ...] = DEFAULT_SKIP_WORDS,
) -> list[dict]:
    """Every live session under *root*, the ones waiting on you first.

    Args:
        root: The ``projects`` directory to read. Passed in rather than
            found, so tests never touch a real home directory.
        now: Current time in seconds. Defaults to the real clock.
        show_prompts: Include the last thing you asked in the detail line.
            Off by default; it is your own writing.
        skip_words: Generic folder names to drop when making a title.
    """
    moment = time.time() if now is None else now
    folder = Path(root)
    if not folder.is_dir():
        return []

    items = []
    for path in sorted(folder.glob("*/*.jsonl")):
        item = _read_session(path, moment, show_prompts, skip_words)
        if item is not None:
            items.append(item)

    items.sort(key=lambda i: not i["needs_you"])
    return items
