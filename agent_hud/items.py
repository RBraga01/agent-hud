"""The item contract between the gateway and the glasses.

The glasses know nothing about Codex, GitHub or any other tool. They
receive a list of items and draw them. An item is four fields and
nothing more.

Parsing is strict on purpose. An entry that does not match the contract
is dropped rather than guessed at, because guessing would either hide
work from you or invent work that is not there. Dropping surfaces a
broken gateway quickly; guessing hides it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Required text fields that must be present and non-empty.
_REQUIRED_TEXT = ("id", "title")


@dataclass(frozen=True)
class Item:
    """One thing the gateway is reporting on.

    Attributes:
        id: Stable identifier, used to tell items apart between refreshes.
        title: Short name, drawn as-is. The glasses never build this text.
        detail: One line of context. May be empty.
        needs_you: True when this item is waiting on the wearer.
    """

    id: str
    title: str
    detail: str
    needs_you: bool


def _parse_item(raw: Any) -> Item | None:
    """Return an Item, or None when the entry does not match the contract."""
    if not isinstance(raw, dict):
        return None

    for field in _REQUIRED_TEXT:
        value = raw.get(field)
        if not isinstance(value, str) or not value:
            return None

    detail = raw.get("detail")
    if not isinstance(detail, str):
        return None

    needs_you = raw.get("needs_you")
    # Checked against bool specifically: in Python a plain 1 is an int, not
    # a bool, and the string "false" is truthy. Neither may slip through.
    if not isinstance(needs_you, bool):
        return None

    return Item(
        id=raw["id"], title=raw["title"], detail=detail, needs_you=needs_you
    )


def parse_items(payload: Any) -> list[Item]:
    """Turn a gateway response into items, dropping anything malformed.

    Never raises. A payload that makes no sense yields an empty list.
    """
    if not isinstance(payload, dict):
        return []

    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return []

    parsed = (_parse_item(raw) for raw in raw_items)
    return [item for item in parsed if item is not None]


def needs_you_count(items: list[Item]) -> int:
    """How many items are waiting on the wearer. This is the number shown."""
    return sum(1 for item in items if item.needs_you)
