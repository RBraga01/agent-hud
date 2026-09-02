"""The item contract between the gateway and the glasses.

The glasses know nothing about Codex, GitHub or any other tool. They
receive a list of items and draw them. An item is four fields and
nothing more.

Parsing is strict on purpose. An entry that does not match the contract
is dropped rather than guessed at, because guessing would either hide
work from you or invent work that is not there. Dropping surfaces a
broken gateway quickly; guessing hides it.

It is also bounded on purpose. The response is otherwise unlimited, and
on a wearable an oversized list or a single entry carrying a page of
text could make the display unusable. The list is capped at ``MAX_ITEMS``
and each drawn string at ``MAX_TITLE`` / ``MAX_DETAIL``. A capped list is
not a whole list, so it carries the same incomplete signal a discarded
entry does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Required text fields that must be present and non-empty.
_REQUIRED_TEXT = ("id", "title")

# Caps on what one response may contain. Excess items are dropped; text
# over length is truncated with a trailing "...". Both mark the payload
# incomplete.
MAX_ITEMS = 100
MAX_TITLE = 64
MAX_DETAIL = 256

_ELLIPSIS = "..."


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


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    """Hard-cap a drawn string. Returns the text and whether it was cut.

    A cut string is exactly ``limit`` characters, the last three a "...".
    """
    if len(text) <= limit:
        return text, False
    return text[: limit - len(_ELLIPSIS)] + _ELLIPSIS, True


def _parse_item(raw: Any) -> tuple[Item, bool] | None:
    """Return (Item, was_truncated), or None when it fails the contract."""
    if not isinstance(raw, dict):
        return None

    for name in _REQUIRED_TEXT:
        value = raw.get(name)
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

    title, title_cut = _truncate(raw["title"], MAX_TITLE)
    detail, detail_cut = _truncate(detail, MAX_DETAIL)
    return (
        Item(id=raw["id"], title=title, detail=detail, needs_you=needs_you),
        title_cut or detail_cut,
    )


@dataclass(frozen=True)
class ParsedPayload:
    """What a gateway response turned out to contain.

    Attributes:
        items: The entries that matched the contract.
        dropped: How many entries did not match, or were past the item
            cap, and were discarded.
        truncated: How many kept entries had a string cut to fit the
            length cap. Their content is on screen but not in full.
        valid: False when the payload was not a list of items at all.
            An invalid payload means the gateway cannot be trusted, which
            is a different thing from it having nothing to report.
    """

    items: list[Item] = field(default_factory=list)
    dropped: int = 0
    truncated: int = 0
    valid: bool = True


def parse_payload(payload: Any) -> ParsedPayload:
    """Read a gateway response, keeping empty and broken clearly apart.

    Never raises.
    """
    if not isinstance(payload, dict):
        return ParsedPayload(valid=False)

    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return ParsedPayload(valid=False)

    dropped = 0
    if len(raw_items) > MAX_ITEMS:
        dropped += len(raw_items) - MAX_ITEMS
        raw_items = raw_items[:MAX_ITEMS]

    items, truncated = [], 0
    for raw in raw_items:
        parsed = _parse_item(raw)
        if parsed is None:
            dropped += 1
            continue
        item, was_truncated = parsed
        items.append(item)
        if was_truncated:
            truncated += 1
    return ParsedPayload(
        items=items, dropped=dropped, truncated=truncated, valid=True
    )


def parse_items(payload: Any) -> list[Item]:
    """Just the items. For callers that only need to check their own shape."""
    return parse_payload(payload).items


def needs_you_count(items: list[Item]) -> int:
    """How many items are waiting on the wearer. This is the number shown."""
    return sum(1 for item in items if item.needs_you)
