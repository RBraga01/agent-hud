"""The deployment surface must stay exactly main.py + the Raven runtime.

Raven's packager walks the whole directory and copies every `.py` unless
`.ravignore` excludes it. That file is a deny-list, so it breaks silently
every time a new top-level directory is added. This test replicates the
packager's decision from `.ravignore` and fails if anything else would
ship. It does not need the Raven Framework installed.
"""

from pathlib import Path

import pytest

from agent_hud.deployment import assert_safe_deploy_tree

REPO = Path(__file__).resolve().parents[1]

# The only things that belong on the glasses.
ALLOWED = {"main.py"}
ALLOWED_DIRS = {"platforms/raven/agent_hud"}


def load_ravignore():
    """Same parse Raven's deploy tool uses: comments and blanks dropped."""
    lines = (REPO / ".ravignore").read_text(encoding="utf-8").splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def is_ignored(rel_path: str, patterns) -> bool:
    """Raven matches plain path prefixes, not globs (deploy_app._should_ignore_path)."""
    rel = rel_path.replace("\\", "/").lstrip("./")
    for pattern in patterns:
        pat = pattern.replace("\\", "/").lstrip("./").rstrip("/")
        if rel == pat or rel.startswith(pat + "/"):
            return True
    return False


def deployable_files():
    """Every tracked-style file the packager would copy, per .ravignore."""
    patterns = load_ravignore()
    out = []
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(REPO).as_posix()
        if rel.startswith(".git/"):
            continue
        # The packager copies .py plus a fixed set of asset extensions.
        if path.suffix not in (
            ".py", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".wav",
            ".mp3", ".mp4", ".json", ".txt", ".md", ".sh",
        ):
            continue
        if not is_ignored(rel, patterns):
            out.append(rel)
    return sorted(out)


def test_only_main_and_raven_runtime_would_be_deployed():
    files = deployable_files()

    unexpected = [
        f
        for f in files
        if f not in ALLOWED
        and not any(f.startswith(directory + "/") for directory in ALLOWED_DIRS)
    ]

    assert unexpected == [], (
        "These would be packaged into the .rav but should not be. "
        "Add the containing path to .ravignore:\n  " + "\n  ".join(unexpected)
    )


def test_main_and_the_raven_package_are_actually_included():
    files = deployable_files()

    assert "main.py" in files
    assert any(
        f.startswith("platforms/raven/agent_hud/") and f.endswith(".py")
        for f in files
    )


def test_the_framework_clone_is_excluded():
    assert is_ignored("raven-framework/core/deploy_app.py", load_ravignore())


def test_the_hook_scripts_are_excluded():
    patterns = load_ravignore()
    assert is_ignored("integrations/claude_code/agent_hud_stop.py", patterns)


def test_local_secret_json_files_are_excluded_from_raven_deploys():
    patterns = load_ravignore()
    exact_names = (
        "credentials.json",
        "passkeys.json",
        "secrets.json",
        "tokens.json",
    )

    assert all(is_ignored(path, patterns) for path in exact_names)


def test_suffixed_local_secret_json_files_block_raven_deploys(tmp_path):
    runtime = tmp_path / "platforms/raven/agent_hud"
    runtime.mkdir(parents=True)
    local_secrets = (
        tmp_path / "credentials-production.json",
        tmp_path / "passkeys.local.json",
        tmp_path / "secrets-backup.json",
        tmp_path / "tokens.dev.json",
        runtime / "tokens-runtime.json",
    )
    for path in local_secrets:
        path.write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Refusing Raven deploy"):
        assert_safe_deploy_tree(tmp_path)


def test_raven_deploy_entrypoint_runs_the_local_secret_guard_first():
    source = (REPO / "main.py").read_text(encoding="utf-8")

    guard_call = "assert_safe_deploy_tree(Path(__file__).resolve().parent)"
    deploy_call = "RunApp.run("
    assert guard_call in source
    assert source.index(guard_call) < source.index(deploy_call)
