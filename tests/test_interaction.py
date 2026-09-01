"""Tests for when the detail panel is showing.

Opening is triggered by staring at the count. Closing happens when you
look away and stay away. This is kept out of the screen code so it can
be tested properly: on the glasses the gaze is your eye, in the
simulator it is the mouse, and this logic does not care which.

The grace period matters. Closing the instant the gaze leaves would make
the panel flicker every time your eye drifts while reading it.
"""

import pytest

from agent_hud.interaction import DetailPanel, Rect

GRACE = 2.0


@pytest.fixture
def panel():
    return DetailPanel(grace_seconds=GRACE)


# --- Rect -------------------------------------------------------------


def test_rect_contains_a_point_inside_it():
    assert Rect(x=10, y=10, width=100, height=50).contains(50, 30) is True


def test_rect_contains_its_top_left_corner():
    assert Rect(x=10, y=10, width=100, height=50).contains(10, 10) is True


@pytest.mark.parametrize(
    "point", [(5, 30), (200, 30), (50, 5), (50, 200), (110, 60)]
)
def test_rect_excludes_points_outside_it(point):
    assert Rect(x=10, y=10, width=100, height=50).contains(*point) is False


def test_rect_with_no_area_contains_nothing():
    assert Rect(x=0, y=0, width=0, height=0).contains(0, 0) is False


# --- Opening and closing ----------------------------------------------


def test_starts_closed(panel):
    assert panel.is_open is False


def test_opens_when_asked(panel):
    panel.open(now=100.0)

    assert panel.is_open is True


def test_stays_open_while_you_are_looking_at_it(panel):
    panel.open(now=100.0)

    assert panel.update(gaze_inside=True, now=200.0) is True
    assert panel.is_open is True


def test_stays_open_during_the_grace_period_after_you_look_away(panel):
    panel.open(now=100.0)
    panel.update(gaze_inside=True, now=101.0)

    assert panel.update(gaze_inside=False, now=101.0 + GRACE - 0.1) is True


def test_closes_once_you_have_looked_away_for_the_whole_grace_period(panel):
    panel.open(now=100.0)
    panel.update(gaze_inside=True, now=101.0)

    assert panel.update(gaze_inside=False, now=101.0 + GRACE) is False
    assert panel.is_open is False


def test_looking_back_cancels_the_pending_close(panel):
    panel.open(now=100.0)
    panel.update(gaze_inside=True, now=101.0)
    panel.update(gaze_inside=False, now=102.0)

    # Eye drifts back before the grace runs out.
    panel.update(gaze_inside=True, now=102.5)

    # The clock restarts from 102.5, so the old deadline no longer applies.
    assert panel.update(gaze_inside=False, now=102.5 + GRACE - 0.1) is True


def test_closes_on_its_own_if_you_never_look_at_it(panel):
    # Opened by a stare at the count, then ignored. It should not linger.
    panel.open(now=100.0)

    assert panel.update(gaze_inside=False, now=100.0 + GRACE) is False


def test_stays_closed_no_matter_what_once_it_has_closed(panel):
    panel.open(now=100.0)
    panel.update(gaze_inside=False, now=100.0 + GRACE)

    assert panel.update(gaze_inside=True, now=200.0) is False
    assert panel.is_open is False


def test_can_be_reopened_after_closing(panel):
    panel.open(now=100.0)
    panel.update(gaze_inside=False, now=100.0 + GRACE)

    panel.open(now=300.0)

    assert panel.is_open is True


def test_closes_immediately_when_told_to(panel):
    panel.open(now=100.0)

    panel.close()

    assert panel.is_open is False


def test_updates_do_nothing_while_closed(panel):
    assert panel.update(gaze_inside=True, now=100.0) is False


def test_rejects_a_grace_period_that_is_not_positive():
    with pytest.raises(ValueError):
        DetailPanel(grace_seconds=0)
