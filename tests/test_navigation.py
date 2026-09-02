"""Tests for the navigation state machine.

Which screen the wearer is on, and what moves them between screens. This
is pure logic: no Qt, no framework, no network. The whole point of
keeping it here is that the rules can be checked exhaustively without a
display attached.

Two rules matter more than the rest:

* Selecting an action never sends it. It opens the confirmation screen.
* Nothing the gateway sends is allowed to yank the wearer somewhere they
  did not ask to go. A refresh may only pull them *out* of a screen that
  has stopped making sense.
"""

import pytest

from agent_hud.navigation import Event, Nav, Screen, advance, nav_for_tasks
from agent_hud.tasks import Action, Task

WAITING = Task(
    id="t1",
    revision=4,
    source="Claude",
    title="Deploy production",
    summary="Deployment needs approval",
    detail="Validation completed. " * 40,
    needs_you=True,
    primary=Action(id="approve", label="Approve"),
    secondary=Action(id="reject", label="Reject"),
)

ALSO_WAITING = Task(
    id="t2",
    revision=1,
    source="Codex",
    title="Integration tests",
    summary="2 integration tests failed",
    detail="Two tests failed on the parser branch.",
    needs_you=True,
    primary=Action(id="rerun", label="Rerun"),
)

BUSY = Task(
    id="t3",
    revision=2,
    source="Codex",
    title="Parser",
    summary="working on the parser",
    detail="",
    needs_you=False,
)

NO_ACTIONS = Task(
    id="t4",
    revision=1,
    source="Claude",
    title="Long build",
    summary="still building",
    detail="Nothing to decide yet.",
    needs_you=True,
)


@pytest.fixture
def tasks():
    return [WAITING, ALSO_WAITING, BUSY]


# --- walking deeper ---------------------------------------------------


def test_activate_opens_the_task_list_from_attention(tasks):
    nav = advance(Nav(screen=Screen.ATTENTION), Event.ACTIVATE, tasks)

    assert nav.screen is Screen.TASK_LIST


def test_selecting_a_task_opens_its_detail(tasks):
    nav = advance(
        Nav(screen=Screen.TASK_LIST), Event.ACTIVATE, tasks, task_id="t2"
    )

    assert nav.screen is Screen.TASK_DETAIL
    assert nav.task_id == "t2"
    assert nav.page == 0


def test_take_action_opens_the_action_menu(tasks):
    nav = Nav(screen=Screen.TASK_DETAIL, task_id="t1")

    nav = advance(nav, Event.TAKE_ACTION, tasks)

    assert nav.screen is Screen.ACTION_MENU
    assert nav.task_id == "t1"


def test_a_task_with_no_actions_cannot_open_the_action_menu():
    # The HUD never invents actions. With nothing to offer there is
    # nothing to open, and the button is not drawn in the first place.
    nav = Nav(screen=Screen.TASK_DETAIL, task_id="t4")

    nav = advance(nav, Event.TAKE_ACTION, [NO_ACTIONS])

    assert nav.screen is Screen.TASK_DETAIL


# --- selecting is not sending -----------------------------------------


def test_selecting_the_primary_action_only_opens_confirmation(tasks):
    nav = Nav(screen=Screen.ACTION_MENU, task_id="t1")

    nav = advance(nav, Event.SELECT_PRIMARY, tasks)

    assert nav.screen is Screen.CONFIRMATION
    assert nav.action_id == "approve"


def test_selecting_the_secondary_action_only_opens_confirmation(tasks):
    nav = Nav(screen=Screen.ACTION_MENU, task_id="t1")

    nav = advance(nav, Event.SELECT_SECONDARY, tasks)

    assert nav.screen is Screen.CONFIRMATION
    assert nav.action_id == "reject"


def test_selecting_an_action_that_does_not_exist_changes_nothing(tasks):
    # t2 has no secondary. Aiming at an empty slot must do nothing at all.
    nav = Nav(screen=Screen.ACTION_MENU, task_id="t2")

    assert advance(nav, Event.SELECT_SECONDARY, tasks) == nav


def test_confirming_records_the_intent_but_the_machine_does_not_send(tasks):
    # advance() is pure. Sending is the app's job, and only after CONFIRM.
    nav = Nav(screen=Screen.CONFIRMATION, task_id="t1", action_id="approve")

    nav = advance(nav, Event.CONFIRM, tasks)

    assert nav.screen is Screen.RESULT


# --- walking back -----------------------------------------------------


def test_back_from_detail_returns_to_the_list(tasks):
    nav = Nav(screen=Screen.TASK_DETAIL, task_id="t1")

    assert advance(nav, Event.BACK, tasks).screen is Screen.TASK_LIST


def test_cancel_from_the_action_menu_returns_to_detail(tasks):
    nav = Nav(screen=Screen.ACTION_MENU, task_id="t1")

    nav = advance(nav, Event.CANCEL, tasks)

    assert nav.screen is Screen.TASK_DETAIL
    assert nav.task_id == "t1"


def test_cancel_from_confirmation_returns_to_the_action_menu(tasks):
    nav = Nav(screen=Screen.CONFIRMATION, task_id="t1", action_id="approve")

    nav = advance(nav, Event.CANCEL, tasks)

    assert nav.screen is Screen.ACTION_MENU
    assert nav.action_id is None


def test_back_from_the_task_list_returns_to_attention(tasks):
    nav = Nav(screen=Screen.TASK_LIST)

    assert advance(nav, Event.BACK, tasks).screen is Screen.ATTENTION


def test_leaving_the_result_screen_returns_to_the_list(tasks):
    nav = Nav(screen=Screen.RESULT, task_id="t1", action_id="approve")

    nav = advance(nav, Event.BACK, tasks)

    assert nav.screen is Screen.TASK_LIST
    assert nav.action_id is None


# --- scrolling --------------------------------------------------------


def test_scrolling_down_moves_one_page(tasks):
    nav = Nav(screen=Screen.TASK_DETAIL, task_id="t1", page=0)

    assert advance(nav, Event.SCROLL_DOWN, tasks).page == 1


def test_scrolling_up_at_the_top_stays_at_the_top(tasks):
    nav = Nav(screen=Screen.TASK_DETAIL, task_id="t1", page=0)

    assert advance(nav, Event.SCROLL_UP, tasks).page == 0


def test_scrolling_down_stops_at_the_last_page(tasks):
    # t2's detail is one short line, so there is only ever one page.
    nav = Nav(screen=Screen.TASK_DETAIL, task_id="t2", page=0)

    assert advance(nav, Event.SCROLL_DOWN, tasks).page == 0


def test_opening_a_different_task_starts_at_the_first_page(tasks):
    nav = Nav(screen=Screen.TASK_DETAIL, task_id="t1", page=3)

    nav = advance(nav, Event.BACK, tasks)
    nav = advance(nav, Event.ACTIVATE, tasks, task_id="t2")

    assert nav.page == 0


# --- the gateway never steers the wearer ------------------------------


def test_the_viewed_task_disappearing_falls_back_to_the_list(tasks):
    nav = Nav(screen=Screen.TASK_DETAIL, task_id="gone")

    assert nav_for_tasks(nav, tasks).screen is Screen.TASK_LIST


def test_the_viewed_task_disappearing_from_confirmation_falls_all_the_way(tasks):
    nav = Nav(screen=Screen.CONFIRMATION, task_id="gone", action_id="approve")

    result = nav_for_tasks(nav, tasks)

    assert result.screen is Screen.TASK_LIST
    assert result.action_id is None


def test_everything_resolving_falls_back_to_idle():
    assert nav_for_tasks(Nav(screen=Screen.TASK_LIST), []).screen is Screen.IDLE


def test_work_arriving_while_idle_shows_attention(tasks):
    assert nav_for_tasks(Nav(screen=Screen.IDLE), tasks).screen is Screen.ATTENTION


def test_only_background_work_stays_idle():
    assert nav_for_tasks(Nav(screen=Screen.IDLE), [BUSY]).screen is Screen.IDLE


def test_a_refresh_does_not_move_someone_who_is_reading(tasks):
    # The list changing underneath must not pull the wearer out of the
    # task they are part way through reading.
    nav = Nav(screen=Screen.TASK_DETAIL, task_id="t1", page=2)

    assert nav_for_tasks(nav, tasks) == nav


def test_a_revision_change_while_confirming_drops_back_to_detail(tasks):
    # Never act on a stale representation. The wearer is sent back to read
    # the task again rather than confirming something that has moved on.
    nav = Nav(
        screen=Screen.CONFIRMATION, task_id="t1", action_id="approve", revision=4
    )
    moved = [Task(**{**WAITING.__dict__, "revision": 5}), ALSO_WAITING, BUSY]

    result = nav_for_tasks(nav, moved)

    assert result.screen is Screen.TASK_DETAIL
    assert result.action_id is None
    assert result.stale is True


def test_a_revision_change_while_only_reading_is_not_disruptive(tasks):
    # Reading is not acting. Refresh the text under them, do not move them.
    nav = Nav(screen=Screen.TASK_DETAIL, task_id="t1", revision=4)
    moved = [Task(**{**WAITING.__dict__, "revision": 5}), ALSO_WAITING, BUSY]

    assert nav_for_tasks(nav, moved).screen is Screen.TASK_DETAIL


def test_the_stale_flag_clears_once_the_wearer_moves(tasks):
    nav = Nav(screen=Screen.TASK_DETAIL, task_id="t1", stale=True)

    assert advance(nav, Event.BACK, tasks).stale is False


# --- shape ------------------------------------------------------------


def test_nav_is_immutable():
    from dataclasses import FrozenInstanceError

    nav = Nav(screen=Screen.IDLE)

    with pytest.raises(FrozenInstanceError):
        nav.screen = Screen.TASK_LIST


def test_an_unknown_event_for_the_screen_changes_nothing(tasks):
    nav = Nav(screen=Screen.IDLE)

    assert advance(nav, Event.SELECT_PRIMARY, tasks) == nav
    assert advance(nav, Event.SCROLL_DOWN, tasks) == nav
