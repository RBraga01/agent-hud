"""The deployment surface must stay exactly main.py + agent_hud/.

Raven's packager walks the whole directory and copies every `.py` unless
`.ravignore` excludes it. That file is a deny-list, so it breaks silently
every time a new top-level directory is added. This test replicates the
packager's decision from `.ravignore` and fails if anything else would
ship. It does not need the Raven Framework installed.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The only things that belong on the glasses.
ALLOWED = {"main.py"}
ALLOWED_DIRS = {"agent_hud"}


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


def test_only_main_and_agent_hud_would_be_deployed():
    files = deployable_files()

    unexpected = [
        f
        for f in files
        if f not in ALLOWED and f.split("/", 1)[0] not in ALLOWED_DIRS
    ]

    assert unexpected == [], (
        "These would be packaged into the .rav but should not be. "
        "Add the containing path to .ravignore:\n  " + "\n  ".join(unexpected)
    )


def test_main_and_the_package_are_actually_included():
    files = deployable_files()

    assert "main.py" in files
    assert any(f.startswith("agent_hud/") and f.endswith(".py") for f in files)


def test_the_framework_clone_is_excluded():
    assert is_ignored("raven-framework/core/deploy_app.py", load_ravignore())


def test_the_hook_scripts_are_excluded():
    patterns = load_ravignore()
    assert is_ignored("integrations/claude_code/agent_hud_stop.py", patterns)
