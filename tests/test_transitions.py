"""Tests for the transition decision logic.

Which animation plays when the screen changes, how long it runs and how
far it travels. Framework-free: the Qt timeline is not tested here, only
the decision and the numbers it is handed.
"""

import pytest

from agent_hud.navigation import Screen
from agent_hud.transitions import (
    APP_SIZE,
    Rect,
    centre_of,
    duration_ms,
    idle_dot_position,
    interpolate,
    is_springy,
    transition_for,
    travel,
)


@pytest.mark.parametrize(
    "old, new, expected",
    [
        (None, Screen.IDLE, "none"),  # first paint never animates
        (None, Screen.ATTENTION, "none"),
        (Screen.IDLE, Screen.ATTENTION, "grow"),  # the dot swells
        (Screen.ATTENTION, Screen.IDLE, "shrink"),  # and collapses back
        (Screen.ATTENTION, Screen.TASK_LIST, "deeper"),
        (Screen.TASK_LIST, Screen.TASK_DETAIL, "deeper"),
        (Screen.TASK_DETAIL, Screen.ACTION_MENU, "deeper"),
        (Screen.ACTION_MENU, Screen.CONFIRMATION, "deeper"),
        (Screen.CONFIRMATION, Screen.RESULT, "deeper"),
        (Screen.TASK_DETAIL, Screen.TASK_LIST, "shallower"),
        (Screen.CONFIRMATION, Screen.ACTION_MENU, "shallower"),
        (Screen.RESULT, Screen.TASK_LIST, "shallower"),
        (Screen.TASK_LIST, Screen.TASK_LIST, "none"),  # same screen, redraw
        (Screen.IDLE, Screen.IDLE, "none"),
    ],
)
def test_the_right_transition_is_chosen(old, new, expected):
    assert transition_for(old, new) == expected


def test_skipping_rungs_still_reads_as_a_direction():
    # A refresh can drop someone from confirmation straight to the list.
    assert transition_for(Screen.CONFIRMATION, Screen.TASK_LIST) == "shallower"
    assert transition_for(Screen.IDLE, Screen.TASK_DETAIL) == "deeper"


def test_animations_off_is_always_none():
    assert transition_for(Screen.IDLE, Screen.ATTENTION, animate=False) == "none"
    assert (
        transition_for(Screen.TASK_LIST, Screen.TASK_DETAIL, animate=False) == "none"
    )


def test_an_unknown_screen_name_animates_nothing():
    # Never guess. A screen this module has not been told about is not a
    # reason to play the wrong motion.
    assert transition_for("somewhere_new", Screen.IDLE) == "none"


def test_plain_strings_work_as_well_as_the_enum():
    assert transition_for("idle", "attention") == "grow"


# --- the numbers ------------------------------------------------------


def test_going_deeper_rises_and_coming_back_settles_from_above():
    assert travel("deeper") > 0
    assert travel("grow") > 0
    assert travel("shallower") < 0
    assert travel("shrink") < 0
    assert travel("none") == 0


def test_only_the_moves_that_open_something_overshoot():
    assert is_springy("deeper") is True
    assert is_springy("grow") is True
    assert is_springy("shallower") is False
    assert is_springy("shrink") is False


def test_every_real_move_has_a_duration():
    for move in ("grow", "shrink", "deeper", "shallower"):
        assert duration_ms(move) > 0
    assert duration_ms("none") == 0


def test_coming_back_is_quicker_than_going_in():
    # Closing should not keep you waiting.
    assert duration_ms("shallower") < duration_ms("deeper")
    assert duration_ms("shrink") < duration_ms("grow")


# --- placement --------------------------------------------------------


def test_screens_are_centred():
    x, y = centre_of(400, 300)

    assert x == (APP_SIZE - 400) // 2
    assert y == (APP_SIZE - 300) // 2


def test_a_screen_as_large_as_the_display_sits_at_the_origin():
    assert centre_of(APP_SIZE, APP_SIZE) == (0, 0)


def test_the_idle_dot_sits_in_the_right_periphery():
    x, y = idle_dot_position()

    assert x > APP_SIZE // 2
    assert x < APP_SIZE
    assert 0 < y < APP_SIZE


# --- interpolate ------------------------------------------------------


def test_interpolate_is_the_identity_at_the_ends():
    a = Rect(x=10, y=20, width=30, height=40)
    b = Rect(x=100, y=200, width=300, height=400)

    assert interpolate(a, b, 0.0) == a
    assert interpolate(a, b, 1.0) == b


def test_interpolate_is_linear_in_the_middle():
    a = Rect(x=0, y=0, width=0, height=0)
    b = Rect(x=100, y=200, width=300, height=400)

    assert interpolate(a, b, 0.5) == Rect(x=50, y=100, width=150, height=200)


def test_interpolate_clamps_out_of_range_progress():
    a = Rect(x=0, y=0, width=10, height=10)
    b = Rect(x=100, y=100, width=100, height=100)

    assert interpolate(a, b, -1.0) == a
    assert interpolate(a, b, 2.0) == b
