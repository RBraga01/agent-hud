"""Preferences, which belong to the gateway and are cached on the glasses.

Almost everything the wearer can change lives on their gateway rather
than on the glasses. There are two reasons for that, and they are both
practical: a headset is a miserable place to change a setting, and
somebody with a Home gateway and a Work gateway wants them to behave
differently without carrying one set of choices between the two.

The glasses read these, cache the last good copy, and apply them. They
never write them; that is the Control app's job.

Two things here are deliberately **not** preferences, and this module
will refuse to make them so:

* Two-step confirmation is always required.
* Gaze alone never activates anything.

A wearer may choose *how* they activate a control — a double blink, or a
dwell they hold — but not whether looking at something is enough. A
display you can trigger by glancing at the wrong thing is not one anybody
should be asked to wear, so it is not offered as an option.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

# How a wearer activates the control they are looking at.
ACTIVATION_MODES = ("double_blink", "dwell")

# Bounds on the dwell. Too short and a glance becomes a press, which is
# the thing we are avoiding; too long and it is unusable.
MIN_DWELL_MS = 600
MAX_DWELL_MS = 5000
DEFAULT_DWELL_MS = 1500

SCROLL_SPEEDS = ("slow", "normal", "fast")

MIN_SILENCE_MS = 500
MAX_SILENCE_MS = 10_000
DEFAULT_SILENCE_MS = 1500


@dataclass(frozen=True)
class Preferences:
    """What the wearer has chosen, as the glasses will apply it.

    Attributes:
        revision: Which version of the settings this is. A response
            quoting an older one is ignored, so a slow answer cannot
            overwrite a newer choice.
        activation: ``double_blink`` or ``dwell``. Never "gaze".
        dwell_ms: How long a dwell must be held, when dwell is chosen.
        auto_scroll: Whether looking at the lower zone scrolls on its own.
            Only ever affects scrolling, which executes nothing.
        scroll_speed: How fast, when auto-scroll is on.
        animations: Whether screens slide, or simply change.
        audio_language: A language tag, or ``auto``.
        silence_ms: How much quiet ends a recording.
    """

    revision: int = 0
    activation: str = "double_blink"
    dwell_ms: int = DEFAULT_DWELL_MS
    auto_scroll: bool = False
    scroll_speed: str = "normal"
    animations: bool = True
    audio_language: str = "auto"
    silence_ms: int = DEFAULT_SILENCE_MS

    @property
    def uses_dwell(self) -> bool:
        return self.activation == "dwell"


DEFAULTS = Preferences()


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _whole(raw: Any) -> int | None:
    """A real integer. ``True`` is an int in Python and is not one here."""
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    return raw


def _choice(raw: Any, allowed: tuple[str, ...], fallback: str) -> str:
    return raw if isinstance(raw, str) and raw in allowed else fallback


def _flag(raw: Any, fallback: bool) -> bool:
    return raw if isinstance(raw, bool) else fallback


def parse_preferences(payload: Any, *, current: Preferences | None = None):
    """Read a settings response, keeping the last good copy on anything odd.

    Never raises, and never lets a malformed field become a surprising
    setting. Every value that cannot be read falls back to what is already
    in force, so a gateway that starts talking nonsense changes nothing
    rather than changing something at random.

    Args:
        payload: Whatever the gateway sent.
        current: What is in force now. Defaults are used when there is
            nothing yet.

    Returns:
        ``(preferences, accepted)``. ``accepted`` is False when the payload
        was unusable or older than what is already held, in which case the
        preferences come back unchanged.
    """
    base = current or DEFAULTS

    if not isinstance(payload, dict):
        return base, False

    revision = _whole(payload.get("revision"))
    if revision is None or revision < 0:
        return base, False
    if current is not None and revision < current.revision:
        # An older answer arriving late. Applying it would undo a choice
        # the wearer has already made.
        return base, False

    interaction = payload.get("interaction")
    interaction = interaction if isinstance(interaction, dict) else {}
    scroll = payload.get("scroll")
    scroll = scroll if isinstance(scroll, dict) else {}
    display = payload.get("display")
    display = display if isinstance(display, dict) else {}
    audio = payload.get("audio")
    audio = audio if isinstance(audio, dict) else {}

    dwell = _whole(interaction.get("dwell_ms"))
    language = audio.get("language")
    silence = _whole(audio.get("silence_ms"))

    return (
        replace(
            base,
            revision=revision,
            activation=_choice(
                interaction.get("mode"), ACTIVATION_MODES, base.activation
            ),
            dwell_ms=(
                _clamp(dwell, MIN_DWELL_MS, MAX_DWELL_MS)
                if dwell is not None
                else base.dwell_ms
            ),
            auto_scroll=_flag(scroll.get("auto"), base.auto_scroll),
            scroll_speed=_choice(
                scroll.get("speed"), SCROLL_SPEEDS, base.scroll_speed
            ),
            animations=_flag(display.get("animations"), base.animations),
            audio_language=(
                language.strip()
                if isinstance(language, str) and language.strip()
                else base.audio_language
            ),
            silence_ms=(
                _clamp(silence, MIN_SILENCE_MS, MAX_SILENCE_MS)
                if silence is not None
                else base.silence_ms
            ),
        ),
        True,
    )


def to_payload(preferences: Preferences) -> dict:
    """The shape the gateway serves. Used by the development gateway."""
    return {
        "revision": preferences.revision,
        "interaction": {
            "mode": preferences.activation,
            "dwell_ms": preferences.dwell_ms,
        },
        "scroll": {
            "auto": preferences.auto_scroll,
            "speed": preferences.scroll_speed,
        },
        "display": {"animations": preferences.animations},
        "audio": {
            "language": preferences.audio_language,
            "silence_ms": preferences.silence_ms,
        },
    }
