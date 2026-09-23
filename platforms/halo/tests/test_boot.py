from pathlib import Path

from halo_emulator import HaloEmulator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT = PROJECT_ROOT / "artifacts" / "screenshots" / "progress" / "h1-quiet.png"


def test_boot_is_quiet_and_sends_nothing(hud_emulator: HaloEmulator) -> None:
    framebuffer = hud_emulator.get_framebuffer()
    lit_pixels = sum(
        1
        for red, green, blue, _alpha in framebuffer.getdata()
        if red + green + blue > 30
    )
    assert framebuffer.size == (256, 256)
    assert lit_pixels == 0
    assert hud_emulator.get_bluetooth_sent() == []

    SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
    framebuffer.save(SCREENSHOT)
    assert SCREENSHOT.is_file()
