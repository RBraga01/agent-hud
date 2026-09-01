#!/usr/bin/env python3
"""Claude Code `SessionEnd` hook for Agent HUD.

Runs when a Claude Code session closes. Deletes that session's record so
a finished session does not linger as "your turn" until the staleness
cutoff.

Always exits 0.
"""

from __future__ import annotations

import contextlib
import sys

from _hook_common import read_payload, remove_record


def main() -> None:
    payload = read_payload()
    if payload is not None:
        remove_record(payload)


if __name__ == "__main__":
    with contextlib.suppress(Exception):
        main()
    sys.exit(0)
