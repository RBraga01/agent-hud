"""Bits shared by the two Claude feeders.

`claude_sessions` reads transcript files with no setup. `claude_hook`
reads a state directory written by a Claude Code hook — a supported
signal rather than an undocumented format. Both turn a project folder
into a readable title the same way, and age a timestamp the same way.
"""

from __future__ import annotations

import re

_DRIVE = re.compile(r"^([a-zA-Z])--")

# Folder names that describe where code is kept, not which project it is.
# Several languages, so none of this assumes one person's machine.
DEFAULT_SKIP_WORDS = (
    "projects", "projectos", "proyectos", "projekte", "projets",
    "code", "src", "repos", "repositories", "dev", "development",
    "workspace", "work", "documents", "users", "home",
)


def pretty_project(
    folder: str, skip_words: tuple[str, ...] = DEFAULT_SKIP_WORDS
) -> str:
    """Turn a folder name into something worth reading.

    ``c--Projects-api-core`` becomes ``api core``. A leading drive letter
    and any generic container folders are dropped; what is left is the
    project. Also accepts a plain path segment like ``my-app``.
    """
    drive = _DRIVE.match(folder)
    letter = drive.group(1).upper() if drive else ""
    rest = folder[drive.end():] if drive else folder

    lower = {w.lower() for w in skip_words}
    parts = [p for p in re.split(r"[-/\\]", rest) if p]
    while parts and parts[0].lower() in lower:
        parts.pop(0)

    name = " ".join(parts).strip()
    if name:
        return name
    return f"{letter} drive" if letter else "unnamed"


def ago(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{max(minutes, 1)} min"
    hours = minutes // 60
    return f"{hours} h" if hours < 24 else f"{hours // 24} d"
