"""The visual language, in one place.

Every screen takes its colours, sizes and spacing from here, so the six
screens stay a family rather than six separate designs. The values come
from the approved reference images.

Two facts about the display drive all of it:

* The waveguide only *adds* light. Black is transparent and white is the
  brightest thing available, so nothing here relies on a dark fill to
  create contrast. Outlines and text carry the design.
* Gaze lands within about two to three degrees of where the wearer means
  it, so touch targets are large and well separated.

Colour is never the only signal for anything. The accent marks structure;
what a thing *means* is always also said in words or position.
"""

from __future__ import annotations

from raven_framework.helpers.themes import RAVEN_CORE as theme

# --- colour ------------------------------------------------------------

# The accent. Outlines, small caps labels, and the fill on a primary
# button. Raven's own blue, so the app looks native rather than pasted on.
ACCENT = theme.basic_palette.blue

# The theme's own border is a white-to-grey gradient, and it *overrides*
# any flat border colour you pass. So every outline in this app sets the
# gradient explicitly: a light cyan falling to the accent blue, which is
# what gives an edge its lit look on the waveguide rather than a flat line.
GLOW_START = "#5AC8FA"
GLOW_END = ACCENT

# Text. White is the most visible thing an additive display can draw, so
# it carries anything that has to be read rather than merely noticed.
TEXT = theme.basic_palette.white
TEXT_DIM = theme.basic_palette.light_gray

# The amber "you are not seeing everything" marker. Fully saturated on
# purpose: a dulled colour is one with less light in it.
INCOMPLETE = theme.basic_palette.yellow

TRANSPARENT = theme.basic_palette.transparent

# --- shape -------------------------------------------------------------

CARD_RADIUS = 18
ROW_RADIUS = 12
BUTTON_RADIUS = 10
BORDER = 2

# --- type --------------------------------------------------------------

# Checked against the simulator's waveguide blend in all three lighting
# presets. In daylight the display cannot darken what is behind it, so
# regular-weight body text washes out against a bright wall or window.
# Anything that must be read is at least medium.
LABEL_SIZE = 15  # "CLAUDE", "STATUS" — uppercase, tracked, accent colour
TITLE_SIZE = 30  # "Deploy production"
ROW_TITLE_SIZE = 22  # "Claude" on a list row
BODY_SIZE = 19
SMALL_SIZE = 15  # "+1 more"

HEAVY = "bold"
MEDIUM = "medium"

# --- layout ------------------------------------------------------------

APP_SIZE = 640
EDGE_MARGIN = 24

CARD_MARGIN = 26
CARD_SPACING = 12

ROW_HEIGHT = 76
ROW_ICON_SIZE = 34
ROW_SPACING = 10

BUTTON_HEIGHT = 56
BUTTON_MIN_WIDTH = 150

# How many list rows fit on one page before the overflow line appears.
ROWS_PER_PAGE = 3

# Longest word that still gets letter-spacing in a small caps label.
MAX_TRACKED_LABEL = 6


def outline(color_start: str = GLOW_START, color_end: str = GLOW_END) -> dict:
    """Border settings for anything outlined.

    Always spread into a component's constructor. Passing ``border_color``
    alone does nothing: the theme's gradient is on by default and wins.
    """
    return {
        "use_gradient_border": True,
        "border_gradient_start_color": color_start,
        "border_gradient_end_color": color_end,
        "border_gradient_direction": "diagonal",
    }


def label_text(text: str) -> str:
    """Small caps labels are written upper case, with a little air.

    Letter-spacing is not exposed by the framework's text widget, so the
    spacing is put into the string itself. It is only ever used on short
    single words like a source name.
    """
    if len(text) > MAX_TRACKED_LABEL:
        # Tracking a long word makes it far wider than its box. Past this
        # length the extra air costs more than it buys.
        return text.upper()
    return " ".join(text.upper())
