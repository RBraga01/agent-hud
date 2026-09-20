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
        "implementation": "private-prototype",
        "validation": "emulator-validated",
        "source": None,
    }


def test_public_halo_directory_contains_no_runtime_source():
    files = {
        path.relative_to(ROOT / "platforms/halo").as_posix()
        for path in (ROOT / "platforms/halo").rglob("*")
        if path.is_file()
    }
    assert files == {"README.md", "platform.json"}
