"""Tests for the screen itself.

These need the Raven framework and are skipped without it, which is the
normal state in continuous integration. They check logic, not pixels:
whether the right number is shown, whether the right titles appear when
the panel opens. How it actually looks is checked by eye in the
simulator, because readability on an additive display cannot be asserted.
"""

import pytest

from agent_hud.client import FetchResult
from agent_hud.config import Settings
from agent_hud.items import Item

pytest.importorskip(
    "raven_framework", reason="Raven framework not installed — screen tests skipped"
)

from agent_hud.app import AgentHud

SETTINGS = Settings(gateway_url="http://127.0.0.1:9/items", poll_seconds=3.0)

WAITING = Item(id="a", title="Claude Code", detail="approve deploy?", needs_you=True)
ALSO_WAITING = Item(id="b", title="PR 38", detail="review requested", needs_you=True)
BUSY = Item(id="c", title="Codex", detail="running", needs_you=False)


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
