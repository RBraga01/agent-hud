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


@pytest.fixture(scope="session")
def qapp():
    """One Qt application for the whole session. Qt allows only one."""
    pytest.importorskip(
        "PySide6", reason="Raven framework not installed — screen tests skipped"
    )
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
