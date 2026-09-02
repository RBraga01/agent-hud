"""The six screens, one module each.

These build widgets and nothing else. Every decision about *which* screen
to show, and what a button leads to, lives in ``navigation.py``, which
needs no framework and is checked exhaustively in continuous integration.

Each builder takes the data it draws plus ``on_*`` callbacks, and returns
the widget to place. None of them touch the network, the clock, or the
app's state.
"""

from . import parts, style
from .action_menu import build_action_menu
from .attention import build_attention
from .confirmation import build_confirmation
from .task_detail import build_task_detail
from .task_list import build_task_list

__all__ = [
    "build_action_menu",
    "build_attention",
    "build_confirmation",
    "build_task_detail",
    "build_task_list",
    "parts",
    "style",
]
