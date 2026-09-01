"""Tests for settings loading.

Settings come from the environment so that no address or tuning value is
written into source. Bad settings fail loudly at startup rather than
producing a display that quietly does nothing.
"""

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

    with pytest.raises(Exception):
        settings.gateway_url = "https://somewhere.else/items"


def test_reads_the_real_environment_when_none_is_given(monkeypatch):
    monkeypatch.setenv("AGENT_HUD_GATEWAY_URL", "https://from-real-env/items")

    settings = load_settings()

    assert settings.gateway_url == "https://from-real-env/items"
