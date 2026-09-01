"""Settings, read from the environment.

Nothing here is hardcoded into the app: no addresses, no machine names,
no tuning values. That is a deliberate rule for this repository, since
it is intended to be published.

Bad settings raise at startup. On the glasses that surfaces in the
console immediately, which is far easier to diagnose than a display
that silently shows nothing.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_GATEWAY_URL = "http://127.0.0.1:8765/items"
DEFAULT_POLL_SECONDS = 3.0

_GATEWAY_URL_VAR = "AGENT_HUD_GATEWAY_URL"
_POLL_SECONDS_VAR = "AGENT_HUD_POLL_SECONDS"

_ALLOWED_SCHEMES = ("http://", "https://")

_MILLISECONDS_PER_SECOND = 1000


@dataclass(frozen=True)
class Settings:
    """Everything the app needs to know before it starts."""

    gateway_url: str
    poll_seconds: float

    @property
    def poll_interval_ms(self) -> int:
        """The interval as milliseconds, which is what the display timer wants."""
        return int(self.poll_seconds * _MILLISECONDS_PER_SECOND)


def _read_gateway_url(env: Mapping[str, str]) -> str:
    raw = env.get(_GATEWAY_URL_VAR)
    if raw is None:
        return DEFAULT_GATEWAY_URL

    url = raw.strip()
    if not url.startswith(_ALLOWED_SCHEMES):
        raise ValueError(
            f"{_GATEWAY_URL_VAR} must be an http:// or https:// address, got {raw!r}"
        )
    return url


def _read_poll_seconds(env: Mapping[str, str]) -> float:
    raw = env.get(_POLL_SECONDS_VAR)
    if raw is None:
        return DEFAULT_POLL_SECONDS

    try:
        seconds = float(raw.strip())
    except ValueError as exc:
        raise ValueError(
            f"{_POLL_SECONDS_VAR} must be a number, got {raw!r}"
        ) from exc

    if seconds <= 0:
        raise ValueError(
            f"{_POLL_SECONDS_VAR} must be greater than zero, got {raw!r}"
        )
    return seconds


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build settings from the given environment, or the real one.

    Raises:
        ValueError: when a value is present but unusable.
    """
    source = os.environ if env is None else env
    return Settings(
        gateway_url=_read_gateway_url(source),
        poll_seconds=_read_poll_seconds(source),
    )
