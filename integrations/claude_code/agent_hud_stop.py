#!/usr/bin/env python3
"""Claude Code `Stop` hook for Agent HUD.

Runs when Claude finishes a turn. Records that the session is waiting on
you — unless Claude left background tasks or scheduled work running, in
which case it records "background" instead and the HUD stays quiet.

Never reads or stores prompt text. Always exits 0.

Install: see README, "Installing the Claude Code hooks".
"""

from __future__ import annotations

import contextlib
import sys

from _hook_common import has_background_work, read_payload, write_record


def main() -> None:
    payload = read_payload()
    if payload is None:
        return
    write_record("background" if has_background_work(payload) else "waiting", payload)


if __name__ == "__main__":
    with contextlib.suppress(Exception):
        main()
    sys.exit(0)
