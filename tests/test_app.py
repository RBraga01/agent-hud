"""Tests for the screen itself.

These need the Raven framework and are skipped without it, which is the
normal state in continuous integration. They check logic, not pixels:
whether the right screen is showing, whether the right task is open,
whether a refresh moves the wearer when it should and leaves them alone
when it should not. How it actually *looks* is checked by eye in the
simulator, because readability on an additive display cannot be asserted.
"""

import time

import pytest

from agent_hud.client import FetchResult
from agent_hud.config import Settings
from agent_hud.navigation import Screen
from agent_hud.tasks import Action, Task

pytest.importorskip(
    "raven_framework", reason="Raven framework not installed — screen tests skipped"
)

from PySide6.QtCore import QEvent

from agent_hud.app import AgentHud

# animations off: these tests check screen logic, not the Qt timeline.
SETTINGS = Settings(
    gateway_url="http://127.0.0.1:9/tasks", poll_seconds=3.0, animations=False
)

WAITING = Task(
    id="a",
    revision=1,
    source="Claude",
    title="Deploy production",
    summary="Deployment needs approval",
    detail="Validation completed. 47 tests passed.",
    needs_you=True,
    primary=Action(id="approve", label="Approve"),
    secondary=Action(id="reject", label="Reject"),
)
ALSO_WAITING = Task(
    id="b",
    revision=1,
    source="Codex",
    title="Integration tests",
    summary="2 integration tests failed",
    detail="Two tests failed on the parser branch.",
    needs_you=True,
    primary=Action(id="rerun", label="Rerun"),
)
NO_ACTIONS = Task(
    id="d",
    revision=1,
    source="GitHub",
    title="PR 38",
    summary="Review requested",
    detail="A review was requested.",
    needs_you=True,
)
BUSY = Task(
    id="c",
    revision=1,
    source="Codex",
    title="Test run",
    summary="Running, 84 of 91",
    detail="Still going.",
    needs_you=False,
)


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


def make_hud(qapp, tasks=(), ok=True):
    """Build a HUD with the network and the clock replaced."""
    result = FetchResult(tasks=list(tasks), ok=ok, reason="" if ok else "test")
    hud = AgentHud(
        settings=SETTINGS,
        fetch=lambda url, timeout: result,
        gaze=lambda: None,
        clock=lambda: 0.0,
        auto_start=False,
    )
    hud.refresh_now()
    return hud


def open_detail(qapp, hud, task_id):
    """Walk from wherever we are down to one task's detail."""
    hud.open_list()
    hud.select_task(task_id)
    pump(qapp)
    return hud


# --- resting behaviour ------------------------------------------------


def test_shows_how_many_tasks_need_you(qapp):
    hud = make_hud(qapp, tasks=[WAITING, ALSO_WAITING, BUSY])

    assert hud.count_text == "2"
    assert hud.screen is Screen.ATTENTION


def test_nothing_waiting_rests_on_idle(qapp):
    hud = make_hud(qapp, tasks=[BUSY])

    assert hud.count_text == ""
    assert hud.is_idle is True
    assert hud.screen is Screen.IDLE


def test_an_empty_list_from_a_healthy_gateway_really_means_idle(qapp):
    hud = make_hud(qapp, tasks=[])

    assert hud.screen is Screen.IDLE
    assert hud.is_complete is True


# --- walking through the screens --------------------------------------


def test_opening_the_list_shows_what_is_waiting(qapp):
    hud = make_hud(qapp, tasks=[WAITING, ALSO_WAITING, BUSY])

    hud.open_list()

    assert hud.screen is Screen.TASK_LIST
    assert [t.id for t in hud.waiting] == ["a", "b"]


def test_the_list_leaves_out_things_that_do_not_need_you(qapp):
    hud = make_hud(qapp, tasks=[WAITING, BUSY])

    hud.open_list()

    assert [t.source for t in hud.waiting] == ["Claude"]


def test_selecting_a_task_opens_its_detail(qapp):
    hud = make_hud(qapp, tasks=[WAITING, ALSO_WAITING])

    open_detail(qapp, hud, "b")

    assert hud.screen is Screen.TASK_DETAIL
    assert hud.current_task.id == "b"


def test_take_action_opens_the_menu(qapp):
    hud = make_hud(qapp, tasks=[WAITING])
    open_detail(qapp, hud, "a")

    hud.take_action()

    assert hud.screen is Screen.ACTION_MENU


def test_a_task_with_no_actions_has_no_way_into_the_menu(qapp):
    hud = make_hud(qapp, tasks=[NO_ACTIONS])
    open_detail(qapp, hud, "d")

    hud.take_action()

    assert hud.screen is Screen.TASK_DETAIL


def test_choosing_an_action_opens_confirmation_and_sends_nothing(qapp):
    calls = []
    hud = make_hud(qapp, tasks=[WAITING])
    hud._fetch = lambda url, timeout: (calls.append(1), FetchResult(ok=True))[1]
    open_detail(qapp, hud, "a")
    hud.take_action()

    hud.select_primary()

    assert hud.screen is Screen.CONFIRMATION
    assert hud.nav.action_id == "approve"
    assert calls == [], "choosing an action must not talk to the gateway"


def test_the_secondary_action_is_the_one_the_gateway_put_there(qapp):
    hud = make_hud(qapp, tasks=[WAITING])
    open_detail(qapp, hud, "a")
    hud.take_action()

    hud.select_secondary()

    assert hud.nav.action_id == "reject"


def test_an_action_the_gateway_did_not_offer_does_nothing(qapp):
    # ALSO_WAITING has no secondary. Aiming at the empty slot is a no-op.
    hud = make_hud(qapp, tasks=[ALSO_WAITING])
    open_detail(qapp, hud, "b")
    hud.take_action()

    hud.select_secondary()

    assert hud.screen is Screen.ACTION_MENU


def test_confirming_reaches_the_result_screen(qapp):
    hud = make_hud(qapp, tasks=[WAITING])
    open_detail(qapp, hud, "a")
    hud.take_action()
    hud.select_primary()

    hud.confirm()

    assert hud.screen is Screen.RESULT


# --- walking back -----------------------------------------------------


def test_cancel_steps_back_one_screen_at_a_time(qapp):
    hud = make_hud(qapp, tasks=[WAITING])
    open_detail(qapp, hud, "a")
    hud.take_action()
    hud.select_primary()

    hud.cancel()
    assert hud.screen is Screen.ACTION_MENU

    hud.cancel()
    assert hud.screen is Screen.TASK_DETAIL


def test_back_from_detail_returns_to_the_list(qapp):
    hud = make_hud(qapp, tasks=[WAITING, ALSO_WAITING])
    open_detail(qapp, hud, "a")

    hud.back()

    assert hud.screen is Screen.TASK_LIST


# --- gaze focuses, it never acts --------------------------------------


def test_gaze_alone_never_changes_the_screen(qapp):
    """The rule the whole input design exists to keep.

    Feeding gaze positions -- including straight at the middle of the
    display, repeatedly, for a long simulated time -- must never advance
    anything. Activation only ever arrives as a button's clicked signal,
    which RavenOS emits on a double blink or a completed dwell.
    """
    hud = make_hud(qapp, tasks=[WAITING, ALSO_WAITING])
    before = hud.screen

    for step in range(50):
        hud.tick_gaze(gaze_position=(320, 320), now=float(step) * 10)
        pump(qapp)

    assert hud.screen is before


def test_gaze_is_recorded_even_though_it_does_nothing(qapp):
    hud = make_hud(qapp, tasks=[WAITING])

    hud.tick_gaze(gaze_position=(100, 200))

    assert hud.gaze_position == (100, 200)


def test_an_unknown_gaze_position_is_not_an_error(qapp):
    hud = make_hud(qapp, tasks=[WAITING])
    open_detail(qapp, hud, "a")

    hud.tick_gaze(gaze_position=None)

    assert hud.screen is Screen.TASK_DETAIL


# --- when things go wrong ---------------------------------------------


def test_a_failed_fetch_keeps_the_last_known_list(qapp):
    hud = make_hud(qapp, tasks=[WAITING, ALSO_WAITING])

    hud.apply(FetchResult(tasks=[], ok=False, reason="gateway unreachable"))

    assert hud.count_text == "2"
    assert hud.is_online is False


def test_a_failed_fetch_does_not_blank_the_display(qapp):
    # A blank screen and a broken one must never look the same.
    hud = make_hud(qapp, tasks=[WAITING])

    hud.apply(FetchResult(tasks=[], ok=False, reason="down"))

    assert hud.is_idle is False
    assert hud.is_complete is False


def test_a_gateway_talking_nonsense_keeps_the_last_list(qapp):
    hud = make_hud(qapp, tasks=[WAITING, ALSO_WAITING])

    hud.apply(FetchResult(ok=False, reason="gateway did not send a list of tasks"))

    assert hud.count_text == "2"
    assert hud.is_complete is False


def test_a_clean_response_is_complete(qapp):
    hud = make_hud(qapp, tasks=[WAITING])

    assert hud.is_complete is True


def test_a_response_with_discarded_entries_is_not_complete(qapp):
    # The connection is fine, but the picture has holes in it. Saying
    # nothing about that would let a real alert vanish silently.
    hud = make_hud(qapp, tasks=[WAITING])

    hud.apply(FetchResult(tasks=[WAITING], ok=True, dropped=2))

    assert hud.is_online is True
    assert hud.is_complete is False


def test_a_response_with_truncated_text_is_not_complete(qapp):
    hud = make_hud(qapp, tasks=[WAITING])

    hud.apply(FetchResult(tasks=[WAITING], ok=True, truncated=1))

    assert hud.is_complete is False


def test_recovering_clears_the_warning(qapp):
    hud = make_hud(qapp, tasks=[WAITING])
    hud.apply(FetchResult(tasks=[WAITING], ok=True, dropped=1))

    hud.apply(FetchResult(tasks=[WAITING, ALSO_WAITING], ok=True))

    assert hud.is_complete is True


# --- a refresh may pull you out, never push you in --------------------


def test_a_refresh_leaves_someone_reading_where_they_are(qapp):
    hud = make_hud(qapp, tasks=[WAITING, ALSO_WAITING])
    open_detail(qapp, hud, "a")

    hud.apply(FetchResult(tasks=[WAITING, ALSO_WAITING], ok=True))

    assert hud.screen is Screen.TASK_DETAIL
    assert hud.current_task.id == "a"


def test_the_open_task_disappearing_falls_back_to_the_list(qapp):
    hud = make_hud(qapp, tasks=[WAITING, ALSO_WAITING])
    open_detail(qapp, hud, "a")

    hud.apply(FetchResult(tasks=[ALSO_WAITING], ok=True))

    assert hud.screen is Screen.TASK_LIST


def test_everything_resolving_returns_to_rest(qapp):
    hud = make_hud(qapp, tasks=[WAITING])
    open_detail(qapp, hud, "a")

    hud.apply(FetchResult(tasks=[BUSY], ok=True))

    assert hud.screen is Screen.IDLE


def test_a_task_changing_under_a_confirmation_sends_you_back_to_read_it(qapp):
    hud = make_hud(qapp, tasks=[WAITING])
    open_detail(qapp, hud, "a")
    hud.take_action()
    hud.select_primary()
    assert hud.screen is Screen.CONFIRMATION

    moved = Task(**{**WAITING.__dict__, "revision": 2})
    hud.apply(FetchResult(tasks=[moved], ok=True))

    assert hud.screen is Screen.TASK_DETAIL
    assert hud.nav.stale is True
    assert hud.nav.action_id is None


def test_work_arriving_while_at_rest_raises_the_count(qapp):
    hud = make_hud(qapp, tasks=[BUSY])
    assert hud.screen is Screen.IDLE

    hud.apply(FetchResult(tasks=[BUSY, WAITING], ok=True))

    assert hud.screen is Screen.ATTENTION
    assert hud.count_text == "1"


# --- surviving a real event loop --------------------------------------


def test_survives_many_refreshes_with_the_event_loop_running(qapp):
    """Redrawing repeatedly must not touch a widget Qt has destroyed.

    The container's clear() calls deleteLater() on every child, so a
    widget kept between redraws is a dangling pointer. Without pumping
    the event loop those deletions never happen and the bug hides: this
    test only fails if processEvents is called, which is exactly the
    difference between the test suite and the running simulator.
    """
    hud = make_hud(qapp, tasks=[WAITING])

    for step in range(6):
        shown = [WAITING, ALSO_WAITING] if step % 2 else [WAITING]
        hud.apply(FetchResult(tasks=shown, ok=True))
        pump(qapp)

    assert hud.count_text in {"1", "2"}


def test_walking_all_the_way_down_and_back_repeatedly(qapp):
    hud = make_hud(qapp, tasks=[WAITING, ALSO_WAITING])

    for _ in range(3):
        hud.open_list()
        pump(qapp)
        hud.select_task("a")
        pump(qapp)
        hud.take_action()
        pump(qapp)
        hud.select_primary()
        pump(qapp)
        hud.cancel()
        pump(qapp)
        hud.cancel()
        pump(qapp)
        hud.back()
        pump(qapp)
        hud.back()
        pump(qapp)

    assert hud.screen is Screen.ATTENTION


def test_switching_between_waiting_and_idle_repeatedly(qapp):
    hud = make_hud(qapp, tasks=[WAITING])

    for step in range(6):
        hud.apply(FetchResult(tasks=[] if step % 2 else [WAITING], ok=True))
        pump(qapp)

    assert hud.is_idle is True


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
        return FetchResult(tasks=[WAITING], ok=True)

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
        return FetchResult(tasks=[WAITING], ok=True)

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


# --- the first fetch is asynchronous ----------------------------------


def test_construction_does_not_block_on_a_slow_first_fetch(qapp):
    """Once the gateway is remote, a slow or unreachable one must not hold
    the glasses blank for the whole request timeout. The resting state
    shows at once and the first result lands when it lands."""
    import threading

    release = threading.Event()
    started = []

    def slow_fetch(url, timeout):
        started.append(1)
        release.wait(2)
        return FetchResult(tasks=[WAITING, ALSO_WAITING], ok=True)

    try:
        start = time.monotonic()
        hud = AgentHud(
            settings=SETTINGS, fetch=slow_fetch, gaze=lambda: None,
            clock=lambda: 0.0, auto_start=True,
        )
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, "__init__ blocked on the first fetch"
        assert hud.screen is Screen.IDLE  # resting state, no data yet
        assert hud.count_text == ""

        release.set()
        deadline = time.monotonic() + 5
        while hud.count_text == "" and time.monotonic() < deadline:
            pump(qapp)
            time.sleep(0.02)

        assert hud.count_text == "2"  # the real result still arrives
    finally:
        release.set()
        hud.deleteLater()
        pump(qapp)


# --- animated transitions ---------------------------------------------

ANIM = Settings(
    gateway_url="http://127.0.0.1:9/tasks", poll_seconds=3.0, animations=True
)


def make_animated_hud(qapp, tasks=()):
    result = FetchResult(tasks=list(tasks), ok=True)
    hud = AgentHud(
        settings=ANIM,
        fetch=lambda url, timeout: result,
        gaze=lambda: None,
        clock=lambda: 0.0,
        auto_start=False,
    )
    hud.refresh_now()  # first data render: instant, by design
    return hud


def drain(qapp, hud, deadline_s=3.0):
    """Pump until any running transition has settled."""
    end = time.monotonic() + deadline_s
    while hud._transitioning and time.monotonic() < end:
        pump(qapp)
        time.sleep(0.01)
    for _ in range(4):
        pump(qapp)
        time.sleep(0.01)


def test_the_launch_and_first_data_render_are_instant(qapp):
    hud = make_animated_hud(qapp, tasks=[WAITING])

    assert hud._transitioning is False


def test_going_deeper_runs_a_transition_and_settles(qapp):
    hud = make_animated_hud(qapp, tasks=[WAITING, ALSO_WAITING])

    hud.open_list()

    assert hud._transitioning is True
    drain(qapp, hud)
    assert hud._transitioning is False
    assert hud.screen is Screen.TASK_LIST


def test_a_full_walk_with_animation_never_crashes(qapp):
    hud = make_animated_hud(qapp, tasks=[WAITING, ALSO_WAITING])

    for _ in range(3):
        hud.open_list()
        drain(qapp, hud)
        hud.select_task("a")
        drain(qapp, hud)
        hud.take_action()
        drain(qapp, hud)
        hud.select_primary()
        drain(qapp, hud)
        hud.cancel()
        drain(qapp, hud)
        hud.cancel()
        drain(qapp, hud)
        hud.back()
        drain(qapp, hud)
        hud.back()
        drain(qapp, hud)

    assert hud.screen is Screen.ATTENTION


def test_a_data_change_on_the_same_screen_does_not_animate(qapp):
    hud = make_animated_hud(qapp, tasks=[WAITING])

    hud.apply(FetchResult(tasks=[WAITING, ALSO_WAITING], ok=True))

    assert hud._transitioning is False
    assert hud.count_text == "2"


# --- sending, and saying only what is known ---------------------------

from agent_hud.feedback import SendOutcome, SendResult  # noqa: E402
from agent_hud.screens import SendState  # noqa: E402


def make_sending_hud(qapp, outcome=SendOutcome.ACCEPTED, reason="", record=None):
    """A HUD whose gateway answers a send in a known way."""

    def send(base, feedback, timeout=None):
        if record is not None:
            record.append(feedback)
        return SendResult(
            outcome=outcome, reason=reason, request_id=feedback.request_id
        )

    result = FetchResult(tasks=[WAITING], ok=True)
    hud = AgentHud(
        settings=SETTINGS,
        fetch=lambda url, timeout: result,
        send=send,
        gaze=lambda: None,
        clock=lambda: 0.0,
        auto_start=False,
    )
    hud.refresh_now()
    return hud


def walk_to_confirm(qapp, hud, task_id="a"):
    hud.open_list()
    hud.select_task(task_id)
    hud.take_action()
    hud.select_primary()
    pump(qapp)
    return hud


def settle_send(qapp, hud, deadline_s=5.0):
    end = time.monotonic() + deadline_s
    while hud._sending and time.monotonic() < end:
        pump(qapp)
        time.sleep(0.01)
    for _ in range(4):
        pump(qapp)
        time.sleep(0.01)


def test_nothing_is_sent_until_the_final_confirmation(qapp):
    sent = []
    hud = make_sending_hud(qapp, record=sent)

    hud.open_list()
    hud.select_task("a")
    hud.take_action()
    hud.select_primary()
    pump(qapp)

    assert sent == [], "walking to the confirmation screen must send nothing"


def test_confirming_sends_the_task_the_revision_and_the_action(qapp):
    sent = []
    hud = make_sending_hud(qapp, record=sent)
    walk_to_confirm(qapp, hud)

    hud.confirm()
    settle_send(qapp, hud)

    assert len(sent) == 1
    assert sent[0].task_id == "a"
    assert sent[0].revision == WAITING.revision
    assert sent[0].action_id == "approve"
    assert sent[0].request_id


def test_an_accepted_answer_says_sent_and_nothing_stronger(qapp):
    hud = make_sending_hud(qapp, outcome=SendOutcome.ACCEPTED)
    walk_to_confirm(qapp, hud)

    hud.confirm()
    settle_send(qapp, hud)

    assert hud.screen is Screen.RESULT
    assert hud.send_state is SendState.SENT


def test_an_unreachable_gateway_never_reads_as_sent(qapp):
    # The failure this whole design exists to prevent.
    hud = make_sending_hud(qapp, outcome=SendOutcome.UNREACHABLE)
    walk_to_confirm(qapp, hud)

    hud.confirm()
    settle_send(qapp, hud)

    assert hud.send_state is SendState.FAILED


def test_a_stale_task_says_so_rather_than_failing(qapp):
    hud = make_sending_hud(qapp, outcome=SendOutcome.STALE, reason="it changed")
    walk_to_confirm(qapp, hud)

    hud.confirm()
    settle_send(qapp, hud)

    assert hud.send_state is SendState.STALE


def test_a_refused_action_says_refused(qapp):
    hud = make_sending_hud(qapp, outcome=SendOutcome.REJECTED, reason="no such action")
    walk_to_confirm(qapp, hud)

    hud.confirm()
    settle_send(qapp, hud)

    assert hud.send_state is SendState.REFUSED


def test_a_retry_reuses_the_same_request_id(qapp):
    # If the first attempt did arrive and only the answer was lost, the
    # gateway must recognise the second rather than acting twice.
    sent = []
    hud = make_sending_hud(qapp, outcome=SendOutcome.UNREACHABLE, record=sent)
    walk_to_confirm(qapp, hud)
    hud.confirm()
    settle_send(qapp, hud)

    hud.retry_send()
    settle_send(qapp, hud)

    assert len(sent) == 2
    assert sent[0].request_id == sent[1].request_id


def test_a_retry_is_only_offered_when_we_do_not_know(qapp):
    sent = []
    hud = make_sending_hud(qapp, outcome=SendOutcome.REJECTED, record=sent)
    walk_to_confirm(qapp, hud)
    hud.confirm()
    settle_send(qapp, hud)

    hud.retry_send()
    settle_send(qapp, hud)

    assert len(sent) == 1, "a refusal must not be asked again unchanged"


def test_confirming_with_nothing_chosen_sends_nothing(qapp):
    sent = []
    hud = make_sending_hud(qapp, record=sent)
    hud.open_list()
    hud.select_task("a")
    pump(qapp)

    hud.confirm()
    settle_send(qapp, hud)

    assert sent == []
    assert hud.screen is Screen.TASK_DETAIL


def test_answering_does_not_throw_you_off_the_result_screen(qapp):
    # Answering usually resolves the task, so the very next poll has
    # nothing waiting. The acknowledgement must survive that.
    hud = make_sending_hud(qapp)
    walk_to_confirm(qapp, hud)
    hud.confirm()
    settle_send(qapp, hud)

    hud.apply(FetchResult(tasks=[], ok=True))
    pump(qapp)

    assert hud.screen is Screen.RESULT
    assert hud.send_state is SendState.SENT


def test_leaving_the_result_screen_is_the_wearers_own_move(qapp):
    hud = make_sending_hud(qapp)
    walk_to_confirm(qapp, hud)
    hud.confirm()
    settle_send(qapp, hud)

    hud.back()

    assert hud.screen is Screen.TASK_LIST


def test_the_display_does_not_freeze_while_an_answer_is_in_flight(qapp):
    import threading

    release = threading.Event()

    def slow_send(base, feedback, timeout=None):
        release.wait(2)
        return SendResult(outcome=SendOutcome.ACCEPTED, request_id=feedback.request_id)

    result = FetchResult(tasks=[WAITING], ok=True)
    hud = AgentHud(
        settings=SETTINGS, fetch=lambda u, t: result, send=slow_send,
        gaze=lambda: None, clock=lambda: 0.0, auto_start=False,
    )
    hud.refresh_now()
    walk_to_confirm(qapp, hud)

    try:
        start = time.monotonic()
        hud.confirm()
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, "confirm() blocked the display on the network"
        assert hud.screen is Screen.RESULT
        assert hud.send_state is SendState.SENDING

        release.set()
        settle_send(qapp, hud)
        assert hud.send_state is SendState.SENT
    finally:
        release.set()
        settle_send(qapp, hud)
