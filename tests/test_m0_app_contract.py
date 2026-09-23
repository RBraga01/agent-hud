"""The same vectors against the actual Qt application and send boundary."""

import pytest
from test_app import make_hud, open_detail, pump
from test_decision_contract import VECTORS, as_task, assert_trace

from agent_hud.client import FetchResult
from agent_hud.decision_contract import canonical_decision, correlated_status
from agent_hud.feedback import SendOutcome, SendResult


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda case: case["name"])
def test_actual_app_vector(qapp, monkeypatch, case):
    task = as_task(case["initial"])
    hud = make_hud(qapp, tasks=[task])
    open_detail(qapp, hud, task.id)
    hud.take_action()
    transmissions, status = [], None
    ids = iter(f"{VECTORS['id_session']}:{n}" for n in range(1, 20))
    monkeypatch.setattr("agent_hud.app.new_request_id", lambda: next(ids))
    monkeypatch.setattr(
        hud,
        "_send_in_background",
        lambda: transmissions.append(canonical_decision(hud._outgoing)),
    )

    for event in case["events"]:
        kind = event["type"]
        if kind == "focus":
            hud.tick_gaze(gaze_position=(100, 100))
        elif kind == "select":
            if event["action_id"] == task.primary.id:
                hud.select_primary()
            elif task.secondary and event["action_id"] == task.secondary.id:
                hud.select_secondary()
        elif kind == "confirm":
            hud.confirm()
        elif kind == "cancel":
            hud.cancel()
        elif kind == "update":
            task = as_task(event["task"])
            hud.apply(FetchResult(tasks=[task], ok=True))
        elif kind == "result" and hud._outgoing:
            status = correlated_status(
                event["result"], canonical_decision(hud._outgoing)
            )
            if status:
                mapped = {
                    "ACCEPTED": SendOutcome.ACCEPTED,
                    "STALE": SendOutcome.STALE,
                    "INVALID_ACTION": SendOutcome.REJECTED,
                    "ERROR": SendOutcome.UNREACHABLE,
                }[status]
                hud._send_result = SendResult(outcome=mapped)
                hud._apply_send_result()
        elif kind == "retry":
            previous = len(transmissions)
            hud.retry_send()
            if len(transmissions) != previous:
                status = None
        pump(qapp)

    assert_trace(case, transmissions, status)
    if status:
        assert (
            hud.send_state.name
            == {
                "ACCEPTED": "SENT",
                "STALE": "STALE",
                "INVALID_ACTION": "REFUSED",
                "ERROR": "FAILED",
            }[status]
        )
    assert hud.current_task is None or hud.current_task.needs_you
    hud.close()
    hud.deleteLater()
    pump(qapp)
