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
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_GATEWAY_URL = "http://127.0.0.1:8765/items"
DEFAULT_POLL_SECONDS = 3.0

_GATEWAY_URL_VAR = "AGENT_HUD_GATEWAY_URL"
_POLL_SECONDS_VAR = "AGENT_HUD_POLL_SECONDS"
_FEEDERS_VAR = "AGENT_HUD_FEEDERS"
_SHOW_PROMPTS_VAR = "AGENT_HUD_SHOW_PROMPTS"
_CLAUDE_PROJECTS_VAR = "AGENT_HUD_CLAUDE_PROJECTS"

# Invented data only. The safe default: no accounts, no personal data, and
# it works for anyone who clones this.
DEFAULT_FEEDERS = ("simulated",)
KNOWN_FEEDERS = ("simulated", "claude", "file")

_TRUE_WORDS = frozenset({"1", "true", "yes", "on"})

_ALLOWED_SCHEMES = ("http://", "https://")

_MILLISECONDS_PER_SECOND = 1000


@dataclass(frozen=True)
class Settings:
    """Everything the app needs to know before it starts."""

    gateway_url: str
    poll_seconds: float
    feeders: tuple[str, ...] = DEFAULT_FEEDERS
    show_prompts: bool = False
    claude_projects: Path = field(
        default_factory=lambda: Path.home() / ".claude" / "projects"
    )

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


def _read_feeders(env: Mapping[str, str]) -> tuple[str, ...]:
    raw = env.get(_FEEDERS_VAR)
    if raw is None:
        return DEFAULT_FEEDERS

    names = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not names:
        raise ValueError(f"{_FEEDERS_VAR} lists no feeders, got {raw!r}")

    unknown = [n for n in names if n not in KNOWN_FEEDERS]
    if unknown:
        raise ValueError(
            f"{_FEEDERS_VAR} does not know {unknown!r}. "
            f"Choose from {list(KNOWN_FEEDERS)}"
        )
    return names


def _read_show_prompts(env: Mapping[str, str]) -> bool:
    """Off unless clearly switched on. It is the wearer's own writing."""
    return env.get(_SHOW_PROMPTS_VAR, "").strip().lower() in _TRUE_WORDS


def _read_claude_projects(env: Mapping[str, str]) -> Path:
    raw = env.get(_CLAUDE_PROJECTS_VAR)
    if raw is None or not raw.strip():
        return Path.home() / ".claude" / "projects"
    return Path(raw.strip())


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build settings from the given environment, or the real one.

    Raises:
        ValueError: when a value is present but unusable.
    """
    source = os.environ if env is None else env
    return Settings(
        gateway_url=_read_gateway_url(source),
        poll_seconds=_read_poll_seconds(source),
        feeders=_read_feeders(source),
        show_prompts=_read_show_prompts(source),
        claude_projects=_read_claude_projects(source),
    )
