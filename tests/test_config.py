"""Tests for settings loading.

Settings come from the environment so that no address or tuning value is
written into source. Bad settings fail loudly at startup rather than
producing a display that quietly does nothing.
"""

from dataclasses import FrozenInstanceError

import pytest

from agent_hud.config import DEFAULT_GATEWAY_URL, DEFAULT_POLL_SECONDS, load_settings


def test_uses_defaults_when_nothing_is_set():
    settings = load_settings(env={})

    assert settings.gateway_url == DEFAULT_GATEWAY_URL
    assert settings.poll_seconds == DEFAULT_POLL_SECONDS


def test_reads_the_gateway_address_from_the_environment():
    settings = load_settings(env={"AGENT_HUD_GATEWAY_URL": "https://gw.example/items"})

    assert settings.gateway_url == "https://gw.example/items"


def test_reads_the_poll_interval_from_the_environment():
    settings = load_settings(env={"AGENT_HUD_POLL_SECONDS": "10"})

    assert settings.poll_seconds == 10.0


def test_accepts_a_fractional_poll_interval():
    settings = load_settings(env={"AGENT_HUD_POLL_SECONDS": "1.5"})

    assert settings.poll_seconds == 1.5


def test_surrounding_whitespace_is_ignored():
    settings = load_settings(
        env={
            "AGENT_HUD_GATEWAY_URL": "  https://gw.example/items  ",
            "AGENT_HUD_POLL_SECONDS": " 5 ",
        }
    )

    assert settings.gateway_url == "https://gw.example/items"
    assert settings.poll_seconds == 5.0


@pytest.mark.parametrize("value", ["0", "-1", "not a number", "", "   "])
def test_rejects_a_poll_interval_that_is_not_a_positive_number(value):
    with pytest.raises(ValueError, match="AGENT_HUD_POLL_SECONDS"):
        load_settings(env={"AGENT_HUD_POLL_SECONDS": value})


@pytest.mark.parametrize(
    "value", ["", "   ", "gw.example/items", "ftp://gw.example", "file:///etc/passwd"]
)
def test_rejects_a_gateway_address_that_is_not_http(value):
    with pytest.raises(ValueError, match="AGENT_HUD_GATEWAY_URL"):
        load_settings(env={"AGENT_HUD_GATEWAY_URL": value})


def test_converts_the_interval_to_milliseconds_for_the_display_timer():
    # The glasses framework schedules work in milliseconds. Doing the
    # conversion here keeps arithmetic out of the screen code.
    settings = load_settings(env={"AGENT_HUD_POLL_SECONDS": "2.5"})

    assert settings.poll_interval_ms == 2500


def test_settings_are_immutable():
    settings = load_settings(env={})

    with pytest.raises(FrozenInstanceError):
        settings.gateway_url = "https://somewhere.else/items"


def test_reads_the_real_environment_when_none_is_given(monkeypatch):
    monkeypatch.setenv("AGENT_HUD_GATEWAY_URL", "https://from-real-env/items")

    settings = load_settings()

    assert settings.gateway_url == "https://from-real-env/items"


# --- feeder settings --------------------------------------------------


def test_defaults_to_invented_data_only():
    # The safe default: no personal data, no accounts, works for anyone.
    settings = load_settings(env={})

    assert settings.feeders == ("simulated",)
    assert settings.show_prompts is False


def test_feeders_can_be_chosen_and_ordered():
    settings = load_settings(env={"AGENT_HUD_FEEDERS": "claude, simulated"})

    assert settings.feeders == ("claude", "simulated")


def test_rejects_a_feeder_it_does_not_know():
    with pytest.raises(ValueError, match="AGENT_HUD_FEEDERS"):
        load_settings(env={"AGENT_HUD_FEEDERS": "claude,telepathy"})


def test_rejects_an_empty_feeder_list():
    with pytest.raises(ValueError, match="AGENT_HUD_FEEDERS"):
        load_settings(env={"AGENT_HUD_FEEDERS": "  "})


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_prompt_text_can_be_switched_on(value):
    assert load_settings(env={"AGENT_HUD_SHOW_PROMPTS": value}).show_prompts is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", ""])
def test_prompt_text_stays_off_for_anything_else(value):
    assert load_settings(env={"AGENT_HUD_SHOW_PROMPTS": value}).show_prompts is False


def test_the_claude_folder_can_be_pointed_somewhere_else():
    settings = load_settings(env={"AGENT_HUD_CLAUDE_PROJECTS": "/tmp/sessions"})

    assert str(settings.claude_projects).replace("\\", "/").endswith("/tmp/sessions")


def test_the_claude_folder_defaults_into_the_home_directory():
    settings = load_settings(env={})

    parts = settings.claude_projects.parts
    assert parts[-2:] == (".claude", "projects")


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "infinity", "1e400"])
def test_rejects_a_poll_interval_that_is_not_a_finite_number(value):
    # float("nan") and float("inf") both slip past a plain "> 0" check, and
    # then break when converted to integer milliseconds for the timer.
    with pytest.raises(ValueError, match="AGENT_HUD_POLL_SECONDS"):
        load_settings(env={"AGENT_HUD_POLL_SECONDS": value})
