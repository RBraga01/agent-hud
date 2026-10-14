import json
import subprocess
from pathlib import Path

import agent_hud

ROOT = Path(__file__).resolve().parents[1]


def _tracked_platform_paths(platform: str) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", f"platforms/{platform}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [Path(raw) for raw in result.stdout.split("\0") if raw]


def test_raven_package_lives_behind_the_platform_boundary():
    package = Path(agent_hud.__file__).resolve()
    assert package.is_relative_to(ROOT / "platforms" / "raven" / "agent_hud")
    assert not (ROOT / "agent_hud").exists()


def test_platform_descriptors_separate_implementation_and_validation():
    raven = json.loads((ROOT / "platforms/raven/platform.json").read_text())
    halo = json.loads((ROOT / "platforms/halo/platform.json").read_text())
    memomind = json.loads(
        (ROOT / "platforms/memomind/platform.json").read_text()
    )
    assert raven == {
        "id": "raven-prism",
        "implementation": "implemented",
        "validation": "simulator-validated",
        "source": "platforms/raven/agent_hud",
    }
    assert halo == {
        "id": "brilliant-halo",
        "implementation": "in-repository",
        "validation": "emulator-validated",
        "source": "app/",
        "sdk_commit": "f582b88bee798121c51bc483c2b0b4a85dd5e411",
    }
    assert memomind == {
        "id": "memomind-one",
        "implementation": "in-repository",
        "validation": "simulator-validated",
        "source": ["glasses/", "phone/"],
        "sdk_commit": "f74ee53eb70b008e665adfd81ff8a78a344a4ecb",
    }


def test_halo_runtime_is_isolated_and_uses_the_shared_contract():
    halo = ROOT / "platforms" / "halo"
    assert (halo / "app" / "main.lua").is_file()
    assert (halo / "tests" / "test_m0_contract.py").is_file()
    assert not (halo / "core").exists()
    assert not [
        path
        for path in _tracked_platform_paths("halo")
        if path.is_relative_to(Path("platforms/halo/vendor/brilliant_sdk"))
    ]


def test_halo_import_contains_no_private_repository_or_sdk_metadata():
    forbidden_names = {".git", ".venv", "UPSTREAM_CONTRACT.json"}
    assert not [
        path
        for path in _tracked_platform_paths("halo")
        if set(path.parts) & forbidden_names or path.suffix in {".key", ".pem"}
    ]


def test_memomind_runtime_is_a_custom_pair_using_the_shared_contract():
    memomind = ROOT / "platforms" / "memomind"
    assert (memomind / "glasses" / "manifest.json").is_file()
    assert (memomind / "glasses" / "src" / "agent_hud.c").is_file()
    assert (memomind / "phone" / "manifest.json").is_file()
    assert (memomind / "phone" / "src" / "agent-hud.js").is_file()
    assert (memomind / "protocol" / "README.md").is_file()
    assert (memomind / "tests" / "test_m1_5_round_trip.py").is_file()
    assert not (memomind / "core").exists()
    assert not [
        path
        for path in _tracked_platform_paths("memomind")
        if path.is_relative_to(
            Path("platforms/memomind/vendor/plugin-open-platform")
        )
    ]
