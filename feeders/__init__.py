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

from . import claude_sessions, simulated

__all__ = ["claude_sessions", "collect", "file_items", "simulated"]


def file_items(path: Path | str) -> list[dict]:
    """Read a hand-edited file. Useful for driving the display by hand.

    A missing or damaged file yields nothing rather than raising, so a typo
    while editing cannot take the gateway down mid-demo.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = payload.get("items") if isinstance(payload, dict) else None
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
            items.extend(
                claude_sessions.collect(
                    settings.claude_projects, show_prompts=settings.show_prompts
                )
            )
        elif name == "file" and file_path is not None:
            items.extend(file_items(file_path))
    return items
