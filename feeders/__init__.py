"""Feeders: the parts that know about particular tools.

The glasses app knows about none of them. It receives a list of items with
four fields and draws them, and every tool-specific detail lives here, on
the gateway side of the connection. That is not tidiness: changing the
glasses app will one day need Raven's approval to publish, and changing a
feeder never will.

Add a source by writing a module here and naming it in ``KNOWN_FEEDERS``.
Nothing in ``agent_hud`` should ever need to change.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_hud.config import Settings

from . import claude_hook, claude_sessions, codex, simulated

__all__ = [
    "FileFeederError",
    "claude_hook",
    "claude_sessions",
    "codex",
    "collect",
    "file_items",
    "simulated",
]


class FileFeederError(RuntimeError):
    """The hand-edited file exists but could not be read as JSON.

    Raised rather than swallowed: an unreadable file is a broken source,
    and a broken source must reach the screen as the incomplete marker,
    never as a calm empty display.
    """


def file_items(path: Path | str) -> list[dict]:
    """Read a hand-edited file. Useful for driving the display by hand.

    An absent file yields nothing: the feeder just has no data yet. A
    file that is present but not valid JSON raises ``FileFeederError``, so
    a typo mid-edit shows as incomplete instead of as nothing waiting.
    """
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise FileFeederError(f"could not read {p}: {exc}") from exc

    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise FileFeederError(f"{p} is not valid JSON: {exc}") from exc

    items = payload.get("tasks") if isinstance(payload, dict) else None
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def collect(settings: Settings, *, file_path: Path | str | None = None) -> list[dict]:
    """Run the configured feeders in order and join what they return.

    Items keep the order the feeders are listed in, so putting the source
    you care about first puts it on screen first.
    """
    items: list[dict] = []
    for name in settings.feeders:
        if name == "simulated":
            items.extend(simulated.collect())
        elif name == "claude":
            skip = claude_sessions.DEFAULT_SKIP_WORDS + settings.skip_path_words
            items.extend(
                claude_sessions.collect(
                    settings.claude_projects,
                    show_prompts=settings.show_prompts,
                    skip_words=skip,
                )
            )
        elif name == "claude_hook":
            items.extend(claude_hook.collect(settings.claude_state))
        elif name == "codex":
            items.extend(codex.collect(settings.codex_dir))
        elif name == "file" and file_path is not None:
            items.extend(file_items(file_path))
    return items
