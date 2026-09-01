"""Which animation plays when the screen changes, and its geometry.

Framework-free. `app.py` imports the layout constants and `transition_for`
from here, then drives the Qt timeline. Keeping the decision and the
numbers out of the screen means both can be tested without the framework.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- layout, shared with app.py ----------------------------------------

APP_SIZE = 640
EDGE_MARGIN = 24
FRAME_INSET = 6
FRAME_SIZE = APP_SIZE - FRAME_INSET * 2

COUNT_RING_SIZE = 132
COUNT_LABEL_HEIGHT = 42
COUNT_CARD_WIDTH = COUNT_RING_SIZE + 25 * 2 + 36

CARD_WIDTH = FRAME_SIZE
CARD_MARGIN_X = 25
CARD_MARGIN_TOP = 35
CARD_MARGIN_BOTTOM = 35
CARD_SPACING = 10
TITLE_HEIGHT = 46
OVERFLOW_LINE_HEIGHT = 34
ROW_HEIGHT = 96
MAX_PANEL_ITEMS = 2

IDLE_DOT_SIZE = 16

# Motion timings, in milliseconds.
GROW_MS = 260
EXPAND_MS = 300
COLLAPSE_MS = 240
SHRINK_MS = 220


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def interpolate(a: Rect, b: Rect, progress: float) -> Rect:
    """Linear blend between two rectangles. Progress is clamped to 0..1."""
    t = _clamp(progress, 0.0, 1.0)
    return Rect(
        x=round(a.x + (b.x - a.x) * t),
        y=round(a.y + (b.y - a.y) * t),
        width=round(a.width + (b.width - a.width) * t),
        height=round(a.height + (b.height - a.height) * t),
    )


def count_card_height() -> int:
    return (
        CARD_MARGIN_TOP
        + COUNT_RING_SIZE
        + CARD_SPACING
        + COUNT_LABEL_HEIGHT
        + CARD_MARGIN_BOTTOM
    )


def count_card_rect() -> Rect:
    h = count_card_height()
    return Rect(
        x=APP_SIZE - COUNT_CARD_WIDTH - EDGE_MARGIN,
        y=(APP_SIZE - h) // 2,
        width=COUNT_CARD_WIDTH,
        height=h,
    )


def ring_rect() -> Rect:
    """The count ring's bounding box, in app coordinates.

    The ring is the first stacked child inside the count card, so it sits
    one top-margin down from the card's own top-left.
    """
    card = count_card_rect()
    return Rect(
        x=card.x + CARD_MARGIN_X,
        y=card.y + CARD_MARGIN_TOP,
        width=COUNT_RING_SIZE,
        height=COUNT_RING_SIZE,
    )


def dot_rect() -> Rect:
    """The idle dot, centred where the ring's centre is."""
    ring = ring_rect()
    cx = ring.x + ring.width // 2
    cy = ring.y + ring.height // 2
    return Rect(
        x=cx - IDLE_DOT_SIZE // 2,
        y=cy - IDLE_DOT_SIZE // 2,
        width=IDLE_DOT_SIZE,
        height=IDLE_DOT_SIZE,
    )


def panel_height(rows: int, overflow: int) -> int:
    h = CARD_MARGIN_TOP + TITLE_HEIGHT + CARD_SPACING
    h += rows * (ROW_HEIGHT + CARD_SPACING)
    if overflow > 0:
        h += OVERFLOW_LINE_HEIGHT + CARD_SPACING
    return h + CARD_MARGIN_BOTTOM


def card_rect(rows: int, overflow: int) -> Rect:
    """Where the opened panel card sits."""
    h = panel_height(rows, overflow)
    return Rect(
        x=FRAME_INSET,
        y=(APP_SIZE - h) // 2,
        width=CARD_WIDTH,
        height=h,
    )


# --- the decision ----------------------------------------------------------

_KIND = {"idle": 0, "count": 1, "panel": 2}

_MOVES = {
    ("idle", "count"): "grow",
    ("count", "idle"): "shrink",
    ("count", "panel"): "expand",
    ("panel", "count"): "collapse",
    ("panel", "idle"): "collapse",
    ("idle", "panel"): "expand",
}


def transition_for(old_view, new_view, *, animate: bool = True) -> str:
    """The animation to play going from *old_view* to *new_view*.

    Both are the tuples ``AgentHud._view()`` returns; the first element is
    the kind (``idle`` / ``count`` / ``panel``). Returns one of ``grow``,
    ``shrink``, ``expand``, ``collapse`` or ``none``.
    """
    if not animate or old_view is None or new_view is None:
        return "none"
    old_kind = old_view[0]
    new_kind = new_view[0]
    if old_kind == new_kind:
        return "none"
    return _MOVES.get((old_kind, new_kind), "none")


def duration_ms(move: str) -> int:
    return {
        "grow": GROW_MS,
        "expand": EXPAND_MS,
        "collapse": COLLAPSE_MS,
        "shrink": SHRINK_MS,
    }.get(move, 0)
