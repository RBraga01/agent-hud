"""Tests for the screen itself.

These need the Raven framework and are skipped without it, which is the
normal state in continuous integration. They check logic, not pixels:
whether the right number is shown, whether the right titles appear when
the panel opens. How it actually looks is checked by eye in the
simulator, because readability on an additive display cannot be asserted.
"""

import time

import pytest

from agent_hud.client import FetchResult
from agent_hud.config import Settings
from agent_hud.items import Item

pytest.importorskip(
    "raven_framework", reason="Raven framework not installed — screen tests skipped"
)

from PySide6.QtCore import QEvent

from agent_hud.app import AgentHud

# animations off: these tests check screen logic, not the Qt timeline.
SETTINGS = Settings(
    gateway_url="http://127.0.0.1:9/items", poll_seconds=3.0, animations=False
)

WAITING = Item(id="a", title="Claude Code", detail="approve deploy?", needs_you=True)
ALSO_WAITING = Item(id="b", title="PR 38", detail="review requested", needs_you=True)
BUSY = Item(id="c", title="Codex", detail="running", needs_you=False)


def pump(qapp):
    """Do what a real event loop does, including the deferred deletions.

    clear() disposes of children with deleteLater(), which posts a
    DeferredDelete event. processEvents() alone does NOT deliver those, so
    without this line a widget destroyed by Qt still looks alive to the
    tests and a dangling-pointer bug stays hidden until the app is run
    for real.
    """
    qapp.processEvents()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def make_hud(qapp, items=(), ok=True):
    """Build a HUD with the network and the clock replaced."""
    result = FetchResult(items=list(items), ok=ok, reason="" if ok else "test")
    hud = AgentHud(
        settings=SETTINGS,
        fetch=lambda url, timeout: result,
        gaze=lambda: None,
        clock=lambda: 0.0,
        auto_start=False,
    )
    hud.refresh_now()
    return hud


def test_shows_how_many_items_need_you(qapp):
    hud = make_hud(qapp, items=[WAITING, ALSO_WAITING, BUSY])

    assert hud.count_text == "2"


def test_shows_nothing_to_do_when_no_item_needs_you(qapp):
    hud = make_hud(qapp, items=[BUSY])

    assert hud.count_text == ""
    assert hud.is_idle is True


def test_is_idle_when_the_list_is_empty(qapp):
    hud = make_hud(qapp, items=[])

    assert hud.is_idle is True


def test_is_not_idle_when_something_is_waiting(qapp):
    hud = make_hud(qapp, items=[WAITING])

    assert hud.is_idle is False


def test_the_panel_starts_closed(qapp):
    hud = make_hud(qapp, items=[WAITING])

    assert hud.is_panel_open is False


def test_opening_the_panel_lists_what_is_waiting(qapp):
    hud = make_hud(qapp, items=[WAITING, ALSO_WAITING, BUSY])

    hud.open_panel()

    assert hud.is_panel_open is True
    assert hud.panel_lines == [
        ("Claude Code", "approve deploy?"),
        ("PR 38", "review requested"),
    ]


def test_the_panel_leaves_out_things_that_do_not_need_you(qapp):
    hud = make_hud(qapp, items=[WAITING, BUSY])

    hud.open_panel()

    assert [title for title, _ in hud.panel_lines] == ["Claude Code"]


def test_the_panel_does_not_open_when_nothing_is_waiting(qapp):
    hud = make_hud(qapp, items=[BUSY])

    hud.open_panel()

    assert hud.is_panel_open is False


def test_the_panel_closes_when_the_gaze_stays_away(qapp):
    hud = make_hud(qapp, items=[WAITING])
    hud.open_panel()

    # Gaze is nowhere near the panel, and enough time has passed.
    hud.tick_gaze(gaze_position=(0, 0), now=1000.0)

    assert hud.is_panel_open is False


def test_the_panel_stays_open_while_the_gaze_is_on_it(qapp):
    hud = make_hud(qapp, items=[WAITING])
    hud.open_panel()
    centre = hud.panel_region()

    hud.tick_gaze(
        gaze_position=(centre.x + centre.width // 2, centre.y + centre.height // 2),
        now=1000.0,
    )

    assert hud.is_panel_open is True


def test_an_unknown_gaze_position_does_not_close_the_panel(qapp):
    # Losing tracking for a moment must not dismiss what you were reading.
    hud = make_hud(qapp, items=[WAITING])
    hud.open_panel()

    hud.tick_gaze(gaze_position=None, now=1000.0)

    assert hud.is_panel_open is True


def test_the_count_updates_when_new_data_arrives(qapp):
    hud = make_hud(qapp, items=[WAITING])
    assert hud.count_text == "1"

    hud.apply(FetchResult(items=[WAITING, ALSO_WAITING], ok=True))

    assert hud.count_text == "2"


def test_the_panel_closes_if_its_items_disappear(qapp):
    hud = make_hud(qapp, items=[WAITING])
    hud.open_panel()

    hud.apply(FetchResult(items=[BUSY], ok=True))

    assert hud.is_panel_open is False


def test_survives_many_refreshes_with_the_event_loop_running(qapp):
    """Redrawing repeatedly must not touch a widget Qt has destroyed.

    The container's clear() calls deleteLater() on every child, so a
    widget kept between redraws is a dangling pointer. Without pumping
    the event loop those deletions never happen and the bug hides: this
    test only fails if processEvents is called, which is exactly the
    difference between the test suite and the running simulator.
    """
    hud = make_hud(qapp, items=[WAITING])

    for step in range(6):
        shown = [WAITING, ALSO_WAITING] if step % 2 else [WAITING]
        hud.apply(FetchResult(items=shown, ok=True))
        pump(qapp)

    assert hud.count_text in {"1", "2"}


def test_survives_opening_and_closing_repeatedly(qapp):
    hud = make_hud(qapp, items=[WAITING, ALSO_WAITING])

    for _ in range(4):
        hud.open_panel()
        pump(qapp)
        hud.tick_gaze(gaze_position=(0, 0), now=10_000.0)
        pump(qapp)

    assert hud.is_panel_open is False


def test_switching_between_waiting_and_idle_repeatedly(qapp):
    hud = make_hud(qapp, items=[WAITING])

    for step in range(6):
        hud.apply(FetchResult(items=[] if step % 2 else [WAITING], ok=True))
        pump(qapp)

    assert hud.is_idle is True


# --- Phase 3: when things go wrong -----------------------------------


def test_a_failed_fetch_keeps_the_last_known_list(qapp):
    hud = make_hud(qapp, items=[WAITING, ALSO_WAITING])

    hud.apply(FetchResult(items=[], ok=False, reason="gateway unreachable"))

    assert hud.count_text == "2"
    assert hud.is_online is False


def test_a_failed_fetch_does_not_blank_the_display(qapp):
    # A blank screen and a broken one must never look the same.
    hud = make_hud(qapp, items=[WAITING])

    hud.apply(FetchResult(items=[], ok=False, reason="down"))

    assert hud.is_idle is False


def test_coming_back_online_clears_the_marker(qapp):
    hud = make_hud(qapp, items=[WAITING])
    hud.apply(FetchResult(items=[], ok=False, reason="down"))

    hud.apply(FetchResult(items=[WAITING, ALSO_WAITING], ok=True))

    assert hud.is_online is True
    assert hud.count_text == "2"


def test_reports_nothing_left_over_when_everything_fits(qapp):
    hud = make_hud(qapp, items=[WAITING, ALSO_WAITING])

    assert hud.overflow_count == 0


def test_counts_what_did_not_fit_in_the_panel(qapp):
    extra = Item(id="d", title="Build", detail="failed on main", needs_you=True)
    hud = make_hud(qapp, items=[WAITING, ALSO_WAITING, extra])

    hud.open_panel()

    assert len(hud.panel_lines) == 2
    assert hud.overflow_count == 1


def test_the_count_still_reports_everything_even_when_the_panel_cannot(qapp):
    extra = Item(id="d", title="Build", detail="failed on main", needs_you=True)
    hud = make_hud(qapp, items=[WAITING, ALSO_WAITING, extra])

    assert hud.count_text == "3"


def test_status_markers_are_never_dimmed(qapp):
    """A disabled Icon is drawn at reduced opacity by the framework.

    On a display that can only add light, dimming a marker makes it fade
    into whatever is behind it. Both markers were invisible outdoors at
    every size and colour until this flag was removed, so it is worth
    holding in place.
    """
    from agent_hud.app import IDLE_COLOR, IDLE_DOT_SIZE, _dot

    marker = _dot(IDLE_DOT_SIZE, IDLE_COLOR)

    assert marker.disabled is False
    assert marker.enable_click is False


# --- "empty" must never be confused with "broken" ---------------------


def test_a_gateway_talking_nonsense_keeps_the_last_list(qapp):
    hud = make_hud(qapp, items=[WAITING, ALSO_WAITING])

    hud.apply(FetchResult(ok=False, reason="gateway did not send a list of items"))

    assert hud.count_text == "2"
    assert hud.is_online is False
    assert hud.is_complete is False


def test_a_clean_response_is_complete(qapp):
    hud = make_hud(qapp, items=[WAITING])

    assert hud.is_complete is True


def test_a_response_with_discarded_entries_is_not_complete(qapp):
    # The connection is fine, but the picture has holes in it. Saying
    # nothing about that would let a real alert vanish silently.
    hud = make_hud(qapp, items=[WAITING])

    hud.apply(FetchResult(items=[WAITING], ok=True, dropped=2))

    assert hud.is_online is True
    assert hud.is_complete is False
    assert hud.count_text == "1"


def test_recovering_from_discarded_entries_clears_the_warning(qapp):
    hud = make_hud(qapp, items=[WAITING])
    hud.apply(FetchResult(items=[WAITING], ok=True, dropped=1))

    hud.apply(FetchResult(items=[WAITING, ALSO_WAITING], ok=True))

    assert hud.is_complete is True


def test_a_response_with_truncated_text_is_not_complete(qapp):
    # The entry is shown, but part of its text was cut to fit the cap.
    # That is still a picture with a hole in it.
    hud = make_hud(qapp, items=[WAITING])

    hud.apply(FetchResult(items=[WAITING], ok=True, truncated=1))

    assert hud.is_online is True
    assert hud.is_complete is False


def test_an_empty_list_from_a_healthy_gateway_really_means_idle(qapp):
    hud = make_hud(qapp, items=[WAITING])

    hud.apply(FetchResult(items=[], ok=True))

    assert hud.is_idle is True
    assert hud.is_complete is True


# --- one request at a time --------------------------------------------


def test_a_slow_fetch_does_not_pile_up(qapp):
    """The poll interval is shorter than the request timeout by default.

    Without a guard, a slow gateway means several requests in flight at
    once and an older answer can land after a newer one, walking the
    display backwards. Over 5G that stops being theoretical.
    """
    import threading

    started = []
    release = threading.Event()

    def slow_fetch(url, timeout):
        started.append(1)
        release.wait(3)
        return FetchResult(items=[WAITING], ok=True)

    hud = AgentHud(
        settings=SETTINGS, fetch=slow_fetch, gaze=lambda: None,
        clock=lambda: 0.0, auto_start=False,
    )

    hud._refresh_in_background()

    # Wait until the worker is genuinely running before testing the guard;
    # the thread pool has not necessarily picked it up when run() returns.
    deadline = time.monotonic() + 5
    while not started and time.monotonic() < deadline:
        pump(qapp)
        time.sleep(0.01)
    assert started, "the first fetch never started"

    hud._refresh_in_background()
    hud._refresh_in_background()
    assert len(started) == 1, "a second request was started while one was running"

    release.set()
    deadline = time.monotonic() + 5
    while hud.is_fetching and time.monotonic() < deadline:
        pump(qapp)
        time.sleep(0.02)

    assert hud.is_fetching is False
    assert hud.count_text == "1"


def test_the_guard_clears_so_later_polls_still_happen(qapp):
    calls = []

    def fetch(url, timeout):
        calls.append(1)
        return FetchResult(items=[WAITING], ok=True)

    hud = AgentHud(
        settings=SETTINGS, fetch=fetch, gaze=lambda: None,
        clock=lambda: 0.0, auto_start=False,
    )

    for _ in range(3):
        hud._refresh_in_background()
        deadline = time.monotonic() + 5
        while hud.is_fetching and time.monotonic() < deadline:
            pump(qapp)
            time.sleep(0.01)

    assert len(calls) == 3


# --- animated transitions -------------------------------------------------

ANIM = Settings(
    gateway_url="http://127.0.0.1:9/items", poll_seconds=3.0, animations=True
)


def make_animated_hud(qapp, items=()):
    result = FetchResult(items=list(items), ok=True)
    hud = AgentHud(
        settings=ANIM,
        fetch=lambda url, timeout: result,
        gaze=lambda: None,
        clock=lambda: 0.0,
        auto_start=False,
    )
    return hud


def drain(qapp, hud, deadline_s=3.0):
    """Pump the loop until any running transition has settled."""
    end = time.monotonic() + deadline_s
    while hud._transitioning and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)
    pump(qapp)


def test_going_from_idle_to_count_runs_a_transition(qapp):
    hud = make_animated_hud(qapp, items=[BUSY])   # idle
    hud.refresh_now()                             # first data render: instant
    pump(qapp)
    assert hud.is_idle
    assert hud._transitioning is False

    hud.apply(FetchResult(items=[WAITING], ok=True))  # -> count, animates
    assert hud._transitioning is True

    drain(qapp, hud)
    assert hud._transitioning is False
    assert hud.count_text == "1"


def test_opening_the_panel_runs_a_transition_and_settles(qapp):
    hud = make_animated_hud(qapp, items=[WAITING, ALSO_WAITING])
    hud.refresh_now()
    pump(qapp)
    # A second data render, so the "first render instant" rule is spent.
    hud.apply(FetchResult(items=[WAITING, ALSO_WAITING], ok=True))
    pump(qapp)

    hud.open_panel()
    assert hud._transitioning is True

    drain(qapp, hud)
    assert hud.is_panel_open is True
    assert hud.panel_lines == [
        ("Claude Code", "approve deploy?"),
        ("PR 38", "review requested"),
    ]


def test_a_data_change_of_the_same_kind_does_not_animate(qapp):
    hud = make_animated_hud(qapp, items=[WAITING])
    hud.refresh_now()
    pump(qapp)
    hud.apply(FetchResult(items=[WAITING], ok=True))  # spend the first-render rule
    pump(qapp)

    hud.apply(FetchResult(items=[WAITING, ALSO_WAITING], ok=True))  # still count

    assert hud._transitioning is False
    assert hud.count_text == "2"


def test_the_launch_and_first_data_render_are_instant(qapp):
    hud = make_animated_hud(qapp, items=[WAITING])  # would be idle->count
    hud.refresh_now()

    assert hud._transitioning is False
    assert hud.count_text == "1"


def test_repeated_open_and_close_with_animation_never_crashes(qapp):
    hud = make_animated_hud(qapp, items=[WAITING, ALSO_WAITING])
    hud.refresh_now()
    pump(qapp)

    for _ in range(3):
        hud.open_panel()
        drain(qapp, hud)
        hud.tick_gaze(gaze_position=(0, 0), now=10_000.0)
        drain(qapp, hud)

    assert hud.is_panel_open is False
