import json
from pathlib import Path

import agent_hud

ROOT = Path(__file__).resolve().parents[1]


def test_raven_package_lives_behind_the_platform_boundary():
    package = Path(agent_hud.__file__).resolve()
    assert package.is_relative_to(ROOT / "platforms" / "raven" / "agent_hud")
    assert not (ROOT / "agent_hud").exists()


def test_platform_descriptors_separate_implementation_and_validation():
    raven = json.loads((ROOT / "platforms/raven/platform.json").read_text())
    halo = json.loads((ROOT / "platforms/halo/platform.json").read_text())
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


def test_halo_runtime_is_isolated_and_uses_the_shared_contract():
    halo = ROOT / "platforms" / "halo"
    assert (halo / "app" / "main.lua").is_file()
    assert (halo / "tests" / "test_m0_contract.py").is_file()
    assert not (halo / "core").exists()
    assert not (halo / "vendor" / "brilliant_sdk").exists()


def test_halo_import_contains_no_private_repository_or_sdk_metadata():
    halo = ROOT / "platforms" / "halo"
    forbidden_names = {".git", ".venv", "UPSTREAM_CONTRACT.json"}
    assert not [
        path
        for path in halo.rglob("*")
        if path.name in forbidden_names or path.suffix in {".key", ".pem"}
    ]
