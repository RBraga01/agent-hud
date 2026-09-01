"""Tests for the transition decision logic.

Which animation plays when the screen changes state, and the start and
end rectangles it runs between. Framework-free: the Qt timeline is not
tested here, only the decision and the geometry it is handed.
"""

import pytest

from agent_hud.transitions import (
    Rect,
    card_rect,
    interpolate,
    ring_rect,
    transition_for,
)

# The four screen kinds, as _view() reports them.
IDLE = ("idle", True)
COUNT_2 = ("count", "2", True)
COUNT_3 = ("count", "3", True)
PANEL = ("panel", (("PR 38", "review requested"),), 1, True)


@pytest.mark.parametrize(
    "old, new, expected",
    [
        (None, IDLE, "none"),          # first paint never animates
        (None, COUNT_2, "none"),
        (IDLE, COUNT_2, "grow"),       # dot swells into the ring
        (COUNT_2, IDLE, "shrink"),     # ring collapses to the dot
        (COUNT_2, PANEL, "expand"),    # card unfolds from the ring
        (PANEL, COUNT_2, "collapse"),  # card folds back
        (PANEL, IDLE, "collapse"),     # items vanished while open
        (COUNT_2, COUNT_3, "none"),    # same kind, just redraw
        (IDLE, IDLE, "none"),
        (PANEL, PANEL, "none"),
    ],
)
def test_the_right_transition_is_chosen(old, new, expected):
    assert transition_for(old, new) == expected


def test_animations_off_is_always_none():
    assert transition_for(IDLE, COUNT_2, animate=False) == "none"
    assert transition_for(COUNT_2, PANEL, animate=False) == "none"


# --- geometry -------------------------------------------------------------


def test_the_ring_rect_sits_in_the_right_periphery():
    r = ring_rect()

    # Right of centre, vertically centred-ish, on-screen.
    assert r.x > 320
    assert r.width == r.height  # it is a circle's bounding box
    assert r.y >= 0 and r.y + r.height <= 640


def test_the_card_rect_is_large_and_offset_right():
    c = card_rect(rows=2, overflow=0)

    assert c.width > 400
    assert c.height > 150
    assert c.x + c.width <= 640


def test_the_card_grows_with_more_rows():
    one = card_rect(rows=1, overflow=0)
    two = card_rect(rows=2, overflow=0)
    two_plus = card_rect(rows=2, overflow=3)

    assert two.height > one.height
    assert two_plus.height > two.height


def test_interpolate_is_the_identity_at_the_ends():
    a = Rect(x=10, y=20, width=30, height=40)
    b = Rect(x=100, y=200, width=300, height=400)

    assert interpolate(a, b, 0.0) == a
    assert interpolate(a, b, 1.0) == b


def test_interpolate_is_linear_in_the_middle():
    a = Rect(x=0, y=0, width=0, height=0)
    b = Rect(x=100, y=200, width=300, height=400)

    mid = interpolate(a, b, 0.5)

    assert mid == Rect(x=50, y=100, width=150, height=200)


def test_interpolate_clamps_out_of_range_progress():
    a = Rect(x=0, y=0, width=10, height=10)
    b = Rect(x=100, y=100, width=100, height=100)

    assert interpolate(a, b, -1.0) == a
    assert interpolate(a, b, 2.0) == b
