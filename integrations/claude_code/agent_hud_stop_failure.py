#!/usr/bin/env python3
"""Claude Code `StopFailure` hook for Agent HUD.

Runs instead of `Stop` when a turn ends in an API error (rate limit, auth,
etc.). Records "error" so the HUD calls for your attention — a failed
agent is worth more of it than a normal finish. The error contents are
never stored.

Always exits 0.
"""

from __future__ import annotations

import contextlib
import sys

from _hook_common import read_payload, write_record


def main() -> None:
    payload = read_payload()
    if payload is not None:
        write_record("error", payload)


if __name__ == "__main__":
    with contextlib.suppress(Exception):
        main()
    sys.exit(0)
