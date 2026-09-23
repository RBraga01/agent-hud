"""Last-mile guards for the Raven package boundary."""

from fnmatch import fnmatchcase
from pathlib import Path

LOCAL_SECRET_PATTERNS = (
    "credentials*.json",
    "passkeys*.json",
    "secrets*.json",
    "tokens*.json",
)
RAVEN_RUNTIME = Path("platforms/raven/agent_hud")


def local_secret_files(repo_root: Path) -> list[Path]:
    """Return local-secret JSON files that Raven's packager could include."""
    roots = (repo_root, repo_root / RAVEN_RUNTIME)
    candidates = (
        path
        for root in roots
        if root.is_dir()
        for path in (root.glob("*.json") if root == repo_root else root.rglob("*.json"))
    )
    return sorted(
        path
        for path in candidates
        if any(
            fnmatchcase(path.name.lower(), pattern)
            for pattern in LOCAL_SECRET_PATTERNS
        )
    )


def assert_safe_deploy_tree(repo_root: Path) -> None:
    """Refuse deployment while a local-secret JSON file could be packaged."""
    secrets = local_secret_files(repo_root)
    if not secrets:
        return
    relative = ", ".join(path.relative_to(repo_root).as_posix() for path in secrets)
    raise RuntimeError(f"Refusing Raven deploy with local secret files: {relative}")
