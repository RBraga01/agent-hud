"""Repository guards for a project that is intended to stay public."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from stub_server.server import DEFAULT_DATA_PATH

ROOT = Path(__file__).resolve().parents[1]

LOCAL_ONLY_PATHS = (
    ".aider.chat.history.md",
    ".agent-hud/passkeys.json",
    ".claude/projects/example/session.jsonl",
    ".codex/session_index.jsonl",
    ".continue/sessions/example.json",
    ".cursor/session.json",
    ".opencode/opencode.db",
    ".windsurf/session.json",
    ".env.production",
    "gateway-cert.pem",
    "stub_server/agents.local.json",
)

FORBIDDEN_TRACKED_PARTS = {
    ".agent-hud",
    ".claude",
    ".codex",
    ".continue",
    ".cursor",
    ".opencode",
    ".windsurf",
    "sessions",
    "transcripts",
}

FORBIDDEN_TRACKED_SUFFIXES = {
    ".db",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
}

LOCAL_ABSOLUTE_PATH = re.compile(
    rb"(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|/(?:Users|home)/[^/\s]+/)"
)
PRIVATE_KEY_MARKER = re.compile(rb"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY")


def _git(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        input=input_text,
    )


def test_every_known_local_data_shape_is_ignored():
    not_ignored = [
        path
        for path in LOCAL_ONLY_PATHS
        if _git("check-ignore", "--no-index", "-q", path).returncode != 0
    ]

    assert not_ignored == []


def test_hand_edited_tasks_use_an_ignored_local_file():
    assert DEFAULT_DATA_PATH == ROOT / "stub_server" / "agents.local.json"
    assert (ROOT / "stub_server" / "agents.example.json").is_file()
    assert not (ROOT / "stub_server" / "agents.json").exists()


def test_no_local_state_or_credential_file_is_tracked():
    result = _git("ls-files", "-z")
    assert result.returncode == 0

    forbidden = []
    for raw in result.stdout.split("\0"):
        if not raw:
            continue
        path = Path(raw)
        if (
            set(path.parts) & FORBIDDEN_TRACKED_PARTS
            or any(part.startswith(".aider") for part in path.parts)
            or path.suffix.lower() in FORBIDDEN_TRACKED_SUFFIXES
            or path.name.lower()
            in {
                "agents.local.json",
                "credentials.json",
                "passkeys.json",
                "secrets.json",
                "tokens.json",
            }
        ):
            forbidden.append(raw)

    assert forbidden == []


def test_tracked_text_has_no_machine_local_path_or_private_key():
    result = _git("ls-files", "-z")
    assert result.returncode == 0

    findings = []
    for raw in result.stdout.split("\0"):
        if not raw:
            continue
        data = (ROOT / raw).read_bytes()
        if b"\0" in data:
            continue
        if LOCAL_ABSOLUTE_PATH.search(data) or PRIVATE_KEY_MARKER.search(data):
            findings.append(raw)

    assert findings == []
