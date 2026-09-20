"""Real Qt rendering for the unchanged Raven action flow, using invented data."""

import os
from pathlib import Path

from test_app import WAITING, make_hud, open_detail, pump


def test_m0_visual_flow(qapp, monkeypatch):
    # Match the clock visible in the pre-M0 capture; time is not a UI change.
    monkeypatch.setattr("agent_hud.app._now_hhmm", lambda: "10:28")
    monkeypatch.setattr(
        "agent_hud.screens.parts._activation",
        {
            "mode": "double_blink",
            "dwell_ms": 1500,
            "controls": {},
        },
    )
    output = Path(os.environ.get("M0_CAPTURE_DIR", "docs/m0-screenshots/current"))
    output.mkdir(parents=True, exist_ok=True)
    hud = make_hud(qapp, tasks=[WAITING])
    monkeypatch.setattr(hud, "_send_in_background", lambda: None)
    hud.show()

    def capture(name):
        pump(qapp)
        assert hud.grab().save(str(output / f"{name}.png"))

    capture("attention")
    open_detail(qapp, hud, WAITING.id)
    hud.take_action()
    capture("action-menu")
    hud.select_primary()
    capture("confirmation")
    hud.confirm()
    capture("sending")
    hud.close()
    hud.deleteLater()
    pump(qapp)
