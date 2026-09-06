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
    nav = advance(Nav(screen=Screen.TASK_LIST), Event.ACTIVATE, tasks, task_id="t2")

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
    nav = Nav(screen=Screen.CONFIRMATION, task_id="t1", action_id="approve", revision=4)
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


# --- paging a long detail ---------------------------------------------


def test_a_short_detail_is_one_page():
    from agent_hud.navigation import detail_page, page_count

    assert page_count(ALSO_WAITING) == 1
    assert detail_page(ALSO_WAITING, 0) == ALSO_WAITING.detail


def test_a_task_with_no_detail_is_still_one_page():
    from agent_hud.navigation import detail_page, page_count

    assert page_count(BUSY) == 1
    assert detail_page(BUSY, 0) == ""


def test_no_task_at_all_is_one_empty_page():
    from agent_hud.navigation import detail_page, page_count

    assert page_count(None) == 1
    assert detail_page(None, 0) == ""


def test_a_long_detail_splits_into_pages_that_join_back_up():
    from agent_hud.navigation import DETAIL_PAGE_CHARS, detail_page, page_count

    pages = page_count(WAITING)

    assert pages > 1
    joined = "".join(detail_page(WAITING, n) for n in range(pages))
    assert joined == WAITING.detail
    assert all(len(detail_page(WAITING, n)) <= DETAIL_PAGE_CHARS for n in range(pages))


def test_a_page_past_the_end_is_empty_rather_than_an_error():
    from agent_hud.navigation import detail_page

    assert detail_page(WAITING, 999) == ""


# --- the result screen is the wearer's, not the gateway's -------------


def test_a_refresh_never_moves_someone_off_the_result_screen(tasks):
    # Answering a task usually resolves it, so the very next refresh has
    # nothing waiting. Without this rule the wearer would be thrown to the
    # resting screen before they had read whether their answer worked.
    nav = Nav(screen=Screen.RESULT, task_id="t1", action_id="approve")

    assert nav_for_tasks(nav, []) == nav
    assert nav_for_tasks(nav, tasks) == nav


def test_the_result_screen_survives_its_own_task_disappearing(tasks):
    nav = Nav(screen=Screen.RESULT, task_id="gone", action_id="approve")

    assert nav_for_tasks(nav, tasks).screen is Screen.RESULT


def test_leaving_the_result_screen_is_the_wearers_choice(tasks):
    nav = Nav(screen=Screen.RESULT, task_id="t1", action_id="approve")

    assert advance(nav, Event.BACK, tasks).screen is Screen.TASK_LIST


# --- when nobody is answering -----------------------------------------


def test_a_couple_of_missed_polls_change_nothing(tasks):
    from agent_hud.navigation import nav_for_connection

    nav = Nav(screen=Screen.ATTENTION)

    assert nav_for_connection(nav, failures=2) == nav


def test_a_gateway_that_is_really_gone_takes_over_the_resting_screen(tasks):
    from agent_hud.navigation import OFFLINE_PATIENCE, nav_for_connection

    nav = Nav(screen=Screen.ATTENTION)

    result = nav_for_connection(nav, failures=OFFLINE_PATIENCE)

    assert result.screen is Screen.UNAVAILABLE


def test_someone_part_way_through_answering_is_left_alone(tasks):
    from agent_hud.navigation import OFFLINE_PATIENCE, nav_for_connection

    for screen in (Screen.TASK_DETAIL, Screen.ACTION_MENU, Screen.CONFIRMATION):
        nav = Nav(screen=screen, task_id="t1")
        assert nav_for_connection(nav, failures=OFFLINE_PATIENCE * 5) == nav


def test_the_result_screen_is_not_taken_over_either(tasks):
    from agent_hud.navigation import OFFLINE_PATIENCE, nav_for_connection

    nav = Nav(screen=Screen.RESULT, task_id="t1")

    assert nav_for_connection(nav, failures=OFFLINE_PATIENCE * 5) == nav


def test_the_gateway_answering_again_leaves_the_unavailable_screen(tasks):
    from agent_hud.navigation import nav_for_connection

    nav = Nav(screen=Screen.UNAVAILABLE)

    assert nav_for_connection(nav, failures=0).screen is Screen.IDLE


def test_pressing_retry_does_not_pretend_anything_happened(tasks):
    # The screen stays until an answer actually arrives.
    nav = Nav(screen=Screen.UNAVAILABLE)

    assert advance(nav, Event.ACTIVATE, tasks) == nav


# --- turning the page by looking at the bottom of it -------------------
#
# The one place the gaze drives anything, and only because scrolling
# executes nothing: nothing leaves the glasses and no agent is told
# anything. Off unless the wearer asks for it.


def test_auto_scroll_does_nothing_when_it_is_off():
    from agent_hud.navigation import AutoScroll

    scroll = AutoScroll(enabled=False)

    for step in range(100):
        assert scroll.should_advance(inside_zone=True, now=float(step)) is False


def test_looking_at_the_bottom_long_enough_turns_the_page():
    from agent_hud.navigation import AutoScroll

    scroll = AutoScroll(enabled=True, speed="normal")

    assert scroll.should_advance(inside_zone=True, now=0.0) is False
    assert scroll.should_advance(inside_zone=True, now=0.5) is False
    assert scroll.should_advance(inside_zone=True, now=5.0) is True


def test_a_glance_across_the_bottom_does_not_turn_it():
    # Passing your eyes over the foot of a card while reading must not
    # move it under you.
    from agent_hud.navigation import AutoScroll

    scroll = AutoScroll(enabled=True, speed="normal")
    scroll.should_advance(inside_zone=True, now=0.0)

    assert scroll.should_advance(inside_zone=True, now=0.3) is False


def test_looking_away_starts_the_wait_over():
    from agent_hud.navigation import AutoScroll

    scroll = AutoScroll(enabled=True, speed="fast")
    scroll.should_advance(inside_zone=True, now=0.0)
    scroll.should_advance(inside_zone=False, now=0.5)

    assert scroll.should_advance(inside_zone=True, now=1.4) is False


def test_it_turns_one_page_per_rest_not_one_per_tick():
    from agent_hud.navigation import AutoScroll

    scroll = AutoScroll(enabled=True, speed="fast")
    scroll.should_advance(inside_zone=True, now=0.0)
    assert scroll.should_advance(inside_zone=True, now=2.0) is True

    assert scroll.should_advance(inside_zone=True, now=2.1) is False


def test_a_slower_speed_asks_for_a_longer_look():
    from agent_hud.navigation import SCROLL_DELAYS

    assert SCROLL_DELAYS["slow"] > SCROLL_DELAYS["normal"] > SCROLL_DELAYS["fast"]


def test_resetting_forgets_where_the_gaze_was():
    from agent_hud.navigation import AutoScroll

    scroll = AutoScroll(enabled=True, speed="fast")
    scroll.should_advance(inside_zone=True, now=0.0)

    scroll.reset()

    assert scroll.should_advance(inside_zone=True, now=5.0) is False


# --- setting work aside -----------------------------------------------
#
# The wearer is not obliged to deal with things the moment they arrive.
# They can go back to rest, and it has to stay at rest -- otherwise the
# next poll drags them straight back to the attention screen and "later"
# means nothing.


def test_back_from_attention_returns_to_rest(tasks):
    nav = advance(Nav(screen=Screen.ATTENTION), Event.BACK, tasks)
    assert nav.screen is Screen.IDLE


def test_setting_aside_remembers_what_was_waiting(tasks):
    nav = advance(Nav(screen=Screen.ATTENTION), Event.BACK, tasks)
    # Only the tasks that actually wanted something, not the busy one.
    assert nav.set_aside == frozenset({"t1", "t2"})


def test_rest_stays_at_rest_while_the_same_work_waits(tasks):
    """The bug this fixes: 'later' that lasts until the next poll."""
    nav = advance(Nav(screen=Screen.ATTENTION), Event.BACK, tasks)
    for _ in range(5):
        nav = nav_for_tasks(nav, tasks)
        assert nav.screen is Screen.IDLE, "a poll dragged the wearer back"


def test_new_work_still_reaches_the_wearer(tasks):
    """Setting aside is not a mute switch."""
    nav = advance(Nav(screen=Screen.ATTENTION), Event.BACK, tasks)
    arrived = [*tasks, NO_ACTIONS]
    assert nav_for_tasks(nav, arrived).screen is Screen.ATTENTION


def test_answering_one_and_receiving_another_counts_as_new(tasks):
    """Ids, not a count. Both stay at two, but t4 is something unseen."""
    nav = advance(Nav(screen=Screen.ATTENTION), Event.BACK, tasks)
    swapped = [ALSO_WAITING, BUSY, NO_ACTIONS]
    assert nav_for_tasks(nav, swapped).screen is Screen.ATTENTION


def test_attention_returning_forgets_what_was_set_aside(tasks):
    nav = advance(Nav(screen=Screen.ATTENTION), Event.BACK, tasks)
    back = nav_for_tasks(nav, [*tasks, NO_ACTIONS])
    assert back.set_aside == frozenset()


def test_answered_work_stops_being_set_aside(tasks):
    """Otherwise the set only ever grows, and stale ids linger for ever."""
    nav = advance(Nav(screen=Screen.ATTENTION), Event.BACK, tasks)
    nav = nav_for_tasks(nav, [WAITING, BUSY])
    assert nav.set_aside == frozenset({"t1"})


def test_everything_resolving_clears_it_completely(tasks):
    nav = advance(Nav(screen=Screen.ATTENTION), Event.BACK, tasks)
    nav = nav_for_tasks(nav, [BUSY])
    assert nav.screen is Screen.IDLE
    assert nav.set_aside == frozenset()


def test_opening_the_list_clears_what_was_set_aside(tasks):
    """Having looked, there is nothing left to be reminded of."""
    nav = advance(Nav(screen=Screen.ATTENTION), Event.BACK, tasks)
    nav = replace_screen(nav, Screen.ATTENTION)
    assert advance(nav, Event.ACTIVATE, tasks).set_aside == frozenset()


def test_work_set_aside_is_still_reported_as_waiting(tasks):
    """The resting dot has to know there is something behind it."""
    nav = advance(Nav(screen=Screen.ATTENTION), Event.BACK, tasks)
    nav = nav_for_tasks(nav, tasks)
    assert nav.screen is Screen.IDLE
    assert nav.set_aside, "nothing left to tell the wearer about"


def test_the_gateway_cannot_set_work_aside_by_itself(tasks):
    """Only the wearer decides to defer something."""
    nav = nav_for_tasks(Nav(screen=Screen.IDLE), tasks)
    assert nav.screen is Screen.ATTENTION
    assert nav.set_aside == frozenset()


def test_unavailable_does_not_inherit_a_stale_set_aside(tasks):
    from agent_hud.navigation import nav_for_connection

    nav = advance(Nav(screen=Screen.ATTENTION), Event.BACK, tasks)
    gone = nav_for_connection(nav, failures=99)
    assert gone.screen is Screen.UNAVAILABLE


def replace_screen(nav, screen):
    from dataclasses import replace

    return replace(nav, screen=screen)


def test_the_resting_screen_can_be_opened_again(tasks):
    """Otherwise setting work aside is a one-way door: nothing brings the
    wearer back until something new happens to arrive."""
    nav = advance(Nav(screen=Screen.ATTENTION), Event.BACK, tasks)
    reopened = advance(nav, Event.ACTIVATE, tasks)
    assert reopened.screen is Screen.ATTENTION
    assert reopened.set_aside == frozenset()


def test_resting_with_nothing_waiting_stays_put(tasks):
    """No work, no screen to open. A dot that leads nowhere must not
    pretend to lead somewhere."""
    assert (
        advance(Nav(screen=Screen.IDLE), Event.ACTIVATE, [BUSY]).screen is Screen.IDLE
    )


# --- the list needs a way out too -------------------------------------
#
# The count card was not the screen people get stuck on. The list is: it
# is titled "Needs you", it is where the wearer actually spends time, and
# until now the only exit was to open one of the things on it.


def test_the_list_can_be_set_aside_directly(tasks):
    nav = advance(Nav(screen=Screen.TASK_LIST), Event.SET_ASIDE, tasks)
    assert nav.screen is Screen.IDLE
    assert nav.set_aside == frozenset({"t1", "t2"})


def test_setting_the_list_aside_also_holds_against_polls(tasks):
    nav = advance(Nav(screen=Screen.TASK_LIST), Event.SET_ASIDE, tasks)
    for _ in range(5):
        nav = nav_for_tasks(nav, tasks)
    assert nav.screen is Screen.IDLE


def test_the_count_card_can_still_be_set_aside(tasks):
    """Both screens offer it, and they must agree on what it does."""
    from_card = advance(Nav(screen=Screen.ATTENTION), Event.SET_ASIDE, tasks)
    from_list = advance(Nav(screen=Screen.TASK_LIST), Event.SET_ASIDE, tasks)
    assert from_card.screen is from_list.screen is Screen.IDLE
    assert from_card.set_aside == from_list.set_aside


def test_back_from_the_list_still_goes_up_one_screen(tasks):
    """Setting aside is not the same as stepping back, and adding one
    must not quietly replace the other."""
    nav = advance(Nav(screen=Screen.TASK_LIST), Event.BACK, tasks)
    assert nav.screen is Screen.ATTENTION


def test_setting_aside_deeper_in_does_nothing(tasks):
    """It belongs to the screens that survey work, not to the ones in the
    middle of answering a particular thing."""
    for screen in (
        Screen.TASK_DETAIL,
        Screen.ACTION_MENU,
        Screen.CONFIRMATION,
        Screen.LISTENING,
        Screen.REVIEW,
    ):
        nav = Nav(screen=screen, task_id="t1")
        assert advance(nav, Event.SET_ASIDE, tasks).screen is screen
