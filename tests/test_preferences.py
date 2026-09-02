"""Tests for the preferences the gateway owns and the glasses cache.

Two things are being protected here. The obvious one is that a malformed
settings response must never turn into a surprising setting — every field
that cannot be read falls back to what is already in force, so a gateway
talking nonsense changes nothing rather than changing something at
random.

The one that matters more: there is no setting, and no payload, that can
make looking at something enough to activate it.
"""

import pytest

from agent_hud.preferences import (
    ACTIVATION_MODES,
    DEFAULTS,
    MAX_DWELL_MS,
    MIN_DWELL_MS,
    Preferences,
    parse_preferences,
    to_payload,
)

FULL = {
    "revision": 12,
    "interaction": {"mode": "dwell", "dwell_ms": 1200},
    "scroll": {"auto": True, "speed": "fast"},
    "display": {"animations": False},
    "audio": {"language": "pt-PT", "silence_ms": 900},
}


# --- reading a good response ------------------------------------------


def test_reads_every_field():
    prefs, accepted = parse_preferences(FULL)

    assert accepted is True
    assert prefs.revision == 12
    assert prefs.activation == "dwell"
    assert prefs.dwell_ms == 1200
    assert prefs.auto_scroll is True
    assert prefs.scroll_speed == "fast"
    assert prefs.animations is False
    assert prefs.audio_language == "pt-PT"
    assert prefs.silence_ms == 900


def test_an_empty_but_valid_response_gives_the_defaults():
    prefs, accepted = parse_preferences({"revision": 1})

    assert accepted is True
    assert prefs.activation == DEFAULTS.activation
    assert prefs.animations == DEFAULTS.animations


def test_preferences_are_immutable():
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        DEFAULTS.activation = "dwell"


def test_the_payload_round_trips():
    prefs, _ = parse_preferences(FULL)

    again, accepted = parse_preferences(to_payload(prefs))

    assert accepted is True
    assert again == prefs


# --- looking is never enough ------------------------------------------


def test_gaze_is_not_an_activation_mode():
    # Not a setting. Not a payload. Not anything.
    assert "gaze" not in ACTIVATION_MODES
    assert set(ACTIVATION_MODES) == {"double_blink", "dwell"}


@pytest.mark.parametrize(
    "mode", ["gaze", "look", "instant", "hover", "", None, 1, True]
)
def test_a_gateway_asking_for_gaze_activation_is_ignored(mode):
    payload = dict(FULL, interaction={"mode": mode})

    prefs, accepted = parse_preferences(payload)

    assert accepted is True  # the rest of the response is still usable
    assert prefs.activation in ACTIVATION_MODES


def test_a_dwell_short_enough_to_be_a_glance_is_raised_to_the_floor():
    prefs, _ = parse_preferences(
        dict(FULL, interaction={"mode": "dwell", "dwell_ms": 5})
    )

    assert prefs.dwell_ms == MIN_DWELL_MS


def test_an_absurd_dwell_is_brought_back_to_the_ceiling():
    prefs, _ = parse_preferences(
        dict(FULL, interaction={"mode": "dwell", "dwell_ms": 10_000_000})
    )

    assert prefs.dwell_ms == MAX_DWELL_MS


# --- nonsense changes nothing -----------------------------------------


@pytest.mark.parametrize(
    "payload", ["garbage", None, [], 42, {"no_revision": True}]
)
def test_an_unusable_response_leaves_everything_as_it_was(payload):
    current = Preferences(revision=5, activation="dwell", animations=False)

    prefs, accepted = parse_preferences(payload, current=current)

    assert accepted is False
    assert prefs == current


@pytest.mark.parametrize("revision", ["12", True, -1, 1.5])
def test_a_revision_that_is_not_a_whole_number_is_refused(revision):
    prefs, accepted = parse_preferences(dict(FULL, revision=revision))

    assert accepted is False
    assert prefs == DEFAULTS


def test_an_older_answer_arriving_late_does_not_undo_a_newer_choice():
    # Two requests in flight; the slow one answers second. Applying it
    # would silently revert whatever the wearer just changed.
    current = Preferences(revision=20, animations=False)

    prefs, accepted = parse_preferences(dict(FULL, revision=12), current=current)

    assert accepted is False
    assert prefs == current


def test_the_same_revision_is_applied_again_harmlessly():
    current = Preferences(revision=12)

    _, accepted = parse_preferences(FULL, current=current)

    assert accepted is True


@pytest.mark.parametrize(
    "section", ["interaction", "scroll", "display", "audio"]
)
def test_a_section_that_is_not_a_section_keeps_the_current_values(section):
    current = Preferences(
        revision=1, activation="dwell", auto_scroll=True, animations=False,
        scroll_speed="fast", audio_language="pt-PT",
    )
    payload = dict(FULL, revision=99)
    payload[section] = "not a section"

    prefs, accepted = parse_preferences(payload, current=current)

    assert accepted is True
    if section == "interaction":
        assert prefs.activation == "dwell"
    if section == "scroll":
        assert prefs.auto_scroll is True
        assert prefs.scroll_speed == "fast"
    if section == "display":
        assert prefs.animations is False
    if section == "audio":
        assert prefs.audio_language == "pt-PT"


@pytest.mark.parametrize("value", ["yes", 1, 0, None, "true"])
def test_a_flag_that_is_not_a_flag_keeps_the_current_one(value):
    # In Python 1 is truthy and the string "false" is too. Neither may
    # slip through and quietly turn something on.
    current = Preferences(revision=1, animations=False)

    prefs, _ = parse_preferences(
        dict(FULL, revision=2, display={"animations": value}), current=current
    )

    assert prefs.animations is False


def test_an_unknown_scroll_speed_keeps_the_current_one():
    current = Preferences(revision=1, scroll_speed="slow")

    prefs, _ = parse_preferences(
        dict(FULL, revision=2, scroll={"speed": "ludicrous"}), current=current
    )

    assert prefs.scroll_speed == "slow"


def test_an_empty_language_keeps_the_current_one():
    current = Preferences(revision=1, audio_language="pt-PT")

    prefs, _ = parse_preferences(
        dict(FULL, revision=2, audio={"language": "   "}), current=current
    )

    assert prefs.audio_language == "pt-PT"


def test_extra_fields_a_future_gateway_might_add_are_ignored():
    prefs, accepted = parse_preferences(dict(FULL, something_new={"a": 1}))

    assert accepted is True
    assert prefs.revision == 12
