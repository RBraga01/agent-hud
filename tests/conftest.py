"""Shared test setup.

Screen tests need Qt but not a monitor, so Qt is told to render offscreen.
This must happen before PySide6 is imported anywhere, which is why it sits
in conftest.py rather than in a test module.

Screen tests are skipped when the Raven framework is not installed. That
is the normal state in continuous integration: the framework is
proprietary and its licence grants no right to use it, so it is never
installed there.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def no_settings_over_the_network(monkeypatch):
    """Unit tests never call out to a gateway for settings.

    The display fetches the wearer's settings on every poll. In a test
    that address is nobody, so each fetch sat waiting for a connection
    timeout -- it turned a 79 second suite into a 263 second one without
    testing anything.

    Anything that wants the settings path exercised passes its own
    ``fetch_settings_fn``, which this does not touch. The wiring itself is
    covered by ``test_the_display_asks_the_gateway_for_settings``.
    """
    try:
        import agent_hud.app as app_module
    except Exception:
        return  # framework missing; screen tests are skipped anyway
    monkeypatch.setattr(app_module, "fetch_settings", lambda *a, **k: None)


@pytest.fixture(scope="session")
def qapp():
    """One Qt application for the whole session. Qt allows only one."""
    pytest.importorskip(
        "PySide6", reason="Raven framework not installed — screen tests skipped"
    )
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
