"""Settings, read from the environment.

Nothing here is hardcoded into the app: no addresses, no machine names,
no tuning values. That is a deliberate rule for this repository, since
it is intended to be published.

Bad settings raise at startup. On the glasses that surfaces in the
console immediately, which is far easier to diagnose than a display
that silently shows nothing.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .gateways import Gateway, GatewayBook, parse_gateways

DEFAULT_GATEWAY_URL = "http://127.0.0.1:8765/tasks"
DEFAULT_POLL_SECONDS = 3.0

_GATEWAY_URL_VAR = "AGENT_HUD_GATEWAY_URL"
_POLL_SECONDS_VAR = "AGENT_HUD_POLL_SECONDS"
_FEEDERS_VAR = "AGENT_HUD_FEEDERS"
_SHOW_PROMPTS_VAR = "AGENT_HUD_SHOW_PROMPTS"
_ANIMATIONS_VAR = "AGENT_HUD_ANIMATIONS"
_CLAUDE_PROJECTS_VAR = "AGENT_HUD_CLAUDE_PROJECTS"
_CLAUDE_STATE_VAR = "AGENT_HUD_CLAUDE_STATE"
_CODEX_DIR_VAR = "AGENT_HUD_CODEX_DIR"
_SKIP_PATH_WORDS_VAR = "AGENT_HUD_SKIP_PATH_WORDS"
_GATEWAYS_VAR = "AGENT_HUD_GATEWAYS"
_ACTIVE_GATEWAY_VAR = "AGENT_HUD_ACTIVE_GATEWAY"
_TRANSCRIBER_VAR = "AGENT_HUD_TRANSCRIBER"

# Invented data only. The safe default: no accounts, no personal data, and
# it works for anyone who clones this.
DEFAULT_FEEDERS = ("simulated",)
KNOWN_FEEDERS = ("simulated", "claude", "claude_hook", "codex", "file")

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
    # Slide-and-fade transitions between screen states. On by default;
    # turn off for a lower-motion display or to save simulator frames.
    animations: bool = True
    claude_projects: Path = field(
        default_factory=lambda: Path.home() / ".claude" / "projects"
    )
    # Where the Claude Code hooks write session state, for the claude_hook
    # feeder. The hooks default to the same path.
    claude_state: Path = field(
        default_factory=lambda: Path.home() / ".agent-hud" / "claude"
    )
    # The Codex CLI directory, for the codex feeder.
    codex_dir: Path = field(default_factory=lambda: Path.home() / ".codex")
    # Extra generic folder names to drop when naming a project. Empty means
    # use the feeder's own list, which already covers the common ones.
    skip_path_words: tuple[str, ...] = ()
    # Every paired gateway, and which one is in use. Empty means the
    # single one named by gateway_url, which is the ordinary case.
    gateways: GatewayBook = field(default_factory=GatewayBook)
    # Which speech engine the development gateway should use. Empty means
    # none, and Audio then reports itself unavailable.
    transcriber: str = ""

    @property
    def active_gateway(self) -> Gateway:
        """The gateway in use.

        With nothing paired explicitly this is the single one named by
        ``gateway_url``, which is what most people will ever have.
        """
        active = self.gateways.active
        if active is not None:
            return active
        return Gateway(name="Gateway", url=self.gateway_url)

    @property
    def gateway_base(self) -> str:
        """The gateway's root, without the path that fetches the list.

        Reading and answering are two different paths on the same server,
        so the address is configured once, as the read URL, and the root
        is taken from it rather than asking for the same host twice.
        """
        marker = "://"
        start = self.gateway_url.find(marker)
        if start == -1:
            return self.gateway_url.rstrip("/")
        slash = self.gateway_url.find("/", start + len(marker))
        base = self.gateway_url if slash == -1 else self.gateway_url[:slash]
        return base.rstrip("/")

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

    # isfinite rejects nan and inf, which both pass a plain "> 0" check and
    # then fail when turned into an integer millisecond count for the timer.
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError(
            f"{_POLL_SECONDS_VAR} must be a finite number greater than zero, "
            f"got {raw!r}"
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


def _read_animations(env: Mapping[str, str]) -> bool:
    """On unless clearly switched off."""
    raw = env.get(_ANIMATIONS_VAR)
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "off", "false", "no"}


def _read_claude_projects(env: Mapping[str, str]) -> Path:
    raw = env.get(_CLAUDE_PROJECTS_VAR)
    if raw is None or not raw.strip():
        return Path.home() / ".claude" / "projects"
    return Path(raw.strip())


def _read_claude_state(env: Mapping[str, str]) -> Path:
    raw = env.get(_CLAUDE_STATE_VAR)
    if raw is None or not raw.strip():
        return Path.home() / ".agent-hud" / "claude"
    return Path(raw.strip())


def _read_codex_dir(env: Mapping[str, str]) -> Path:
    raw = env.get(_CODEX_DIR_VAR)
    if raw is None or not raw.strip():
        return Path.home() / ".codex"
    return Path(raw.strip())


def _read_skip_path_words(env: Mapping[str, str]) -> tuple[str, ...]:
    raw = env.get(_SKIP_PATH_WORDS_VAR, "")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _read_gateways(env: Mapping[str, str]) -> GatewayBook:
    raw = env.get(_GATEWAYS_VAR, "")
    return parse_gateways(raw, env.get(_ACTIVE_GATEWAY_VAR))


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
        animations=_read_animations(source),
        claude_projects=_read_claude_projects(source),
        claude_state=_read_claude_state(source),
        codex_dir=_read_codex_dir(source),
        skip_path_words=_read_skip_path_words(source),
        gateways=_read_gateways(source),
        transcriber=source.get(_TRANSCRIBER_VAR, "").strip(),
    )
