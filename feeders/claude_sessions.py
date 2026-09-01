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
import time
from pathlib import Path

# Claude may still be mid-reply; do not call for attention immediately.
SETTLE_SECONDS = 45

# Older than this and a session is abandoned, not waiting on you.
STALE_SECONDS = 72 * 3600

# A row is about 530px wide at body size, which is roughly this many
# characters. Longer than this and the text runs past its own outline.
MAX_DETAIL = 30

_PROJECT_PREFIX = "Projects"


def pretty_project(folder: str) -> str:
    """Turn an encoded folder name into something worth reading.

    ``e--Projects-api-core`` becomes ``api core``.
    """
    name = folder.lstrip("eE").lstrip("-")
    if name.startswith(_PROJECT_PREFIX):
        name = name[len(_PROJECT_PREFIX):]
    name = name.strip("-").replace("-", " ").strip()
    return name or "E drive"


def _ago(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{max(minutes, 1)} min"
    hours = minutes // 60
    return f"{hours} h" if hours < 24 else f"{hours // 24} d"


def _last_role_and_prompt(path: Path) -> tuple[str | None, str | None]:
    """Read backwards for whose turn it is, and the last thing you asked."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
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


def _read_session(path: Path, now: float, show_prompts: bool) -> dict | None:
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
        "title": pretty_project(path.parent.name),
        "detail": detail,
        "needs_you": waiting,
    }


def collect(
    root: Path | str, *, now: float | None = None, show_prompts: bool = False
) -> list[dict]:
    """Every live session under *root*, the ones waiting on you first.

    Args:
        root: The ``projects`` directory to read. Passed in rather than
            found, so tests never touch a real home directory.
        now: Current time in seconds. Defaults to the real clock.
        show_prompts: Include the last thing you asked in the detail line.
            Off by default; it is your own writing.
    """
    moment = time.time() if now is None else now
    folder = Path(root)
    if not folder.is_dir():
        return []

    items = []
    for path in sorted(folder.glob("*/*.jsonl")):
        item = _read_session(path, moment, show_prompts)
        if item is not None:
            items.append(item)

    items.sort(key=lambda i: not i["needs_you"])
    return items
