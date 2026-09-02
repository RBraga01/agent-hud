"""Which animation plays when the screen changes.

Framework-free. ``app.py`` asks what to play and drives the Qt timeline;
the decision itself is plain data so it can be checked without a display.

The screens are a ladder, from the resting dot down into one task:

    idle -> attention -> task list -> task detail -> action menu
         -> confirmation -> result

Going down the ladder the new screen rises into place; coming back up it
settles from above. That is the whole idea: the wearer should feel they
are moving through one task rather than being shown a series of unrelated
cards. Motion is short and always secondary to being able to read the
thing that just arrived.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- layout, shared with app.py ----------------------------------------

APP_SIZE = 640
EDGE_MARGIN = 24
IDLE_DOT_SIZE = 16
INCOMPLETE_DOT_SIZE = 14

# Motion timings, in milliseconds.
GROW_MS = 260
DEEPER_MS = 300
SHALLOWER_MS = 240
SHRINK_MS = 220

# How far a screen travels as it arrives. Enough to read as movement,
# not far enough to be a journey.
DEEPER_RISE = 26
SHALLOWER_DROP = 20
GROW_RISE = 12
SHRINK_DROP = 8

# How deep each screen sits. Only the order matters.
_DEPTH = {
    "idle": 0,
    "attention": 1,
    "task_list": 2,
    "task_detail": 3,
    "action_menu": 4,
    "confirmation": 5,
    "result": 6,
    # Off to one side of the ladder rather than on it: arriving here is
    # not going deeper into anything.
    "unavailable": 1,
}


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


def centre_of(width: int, height: int) -> tuple[int, int]:
    """Where a screen of this size sits. Everything is centred."""
    return (APP_SIZE - width) // 2, (APP_SIZE - height) // 2


def idle_dot_position() -> tuple[int, int]:
    """The resting dot, out in the right periphery where it will not nag."""
    return APP_SIZE - IDLE_DOT_SIZE - EDGE_MARGIN, APP_SIZE // 2


def transition_for(old_screen, new_screen, *, animate: bool = True) -> str:
    """The animation to play moving from one screen to another.

    Both are ``Screen`` values, or the strings behind them, or None on the
    very first paint. Returns ``grow``, ``shrink``, ``deeper``,
    ``shallower`` or ``none``.
    """
    if not animate or old_screen is None or new_screen is None:
        return "none"

    old = _DEPTH.get(str(getattr(old_screen, "value", old_screen)))
    new = _DEPTH.get(str(getattr(new_screen, "value", new_screen)))
    if old is None or new is None or old == new:
        return "none"

    # The dot swelling into the count, and back, is its own small moment
    # rather than just another step down the ladder.
    if old == 0 and new == 1:
        return "grow"
    if old == 1 and new == 0:
        return "shrink"
    return "deeper" if new > old else "shallower"


def duration_ms(move: str) -> int:
    return {
        "grow": GROW_MS,
        "shrink": SHRINK_MS,
        "deeper": DEEPER_MS,
        "shallower": SHALLOWER_MS,
    }.get(move, 0)


def travel(move: str) -> int:
    """How far, and which way, the arriving screen moves.

    Positive means it starts below its resting place and rises.
    """
    return {
        "grow": GROW_RISE,
        "shrink": -SHRINK_DROP,
        "deeper": DEEPER_RISE,
        "shallower": -SHALLOWER_DROP,
    }.get(move, 0)


def is_springy(move: str) -> bool:
    """Whether the move overshoots slightly before settling.

    Only the two that open something. Coming back should feel like
    closing, which is calmer than arriving.
    """
    return move in ("grow", "deeper")
