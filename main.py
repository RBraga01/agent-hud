"""Agent HUD — entry point.

The Raven framework requires this exact shape: a file called main.py that
calls RunApp.run with a function returning the app.

Run it with no arguments to open the simulator.

Deploying to real glasses (`python main.py deploy`) needs Raven-issued
credentials. They come from the environment so this file never has to be
edited to hold a real key:

    export RAVEN_APP_ID=...
    export RAVEN_APP_KEY=...
    python main.py deploy
"""

import os
import sys
from pathlib import Path

# Raven deploys this repository as files rather than installing its Python
# package. Keep the public import name while the source lives behind its
# platform boundary.
RAVEN_PLATFORM_ROOT = Path(__file__).resolve().parent / "platforms" / "raven"
if str(RAVEN_PLATFORM_ROOT) not in sys.path:
    sys.path.insert(0, str(RAVEN_PLATFORM_ROOT))

from agent_hud.app import AgentHud  # noqa: E402
from raven_framework import RunApp  # noqa: E402

if __name__ == "__main__":
    RunApp.run(
        lambda: AgentHud(),
        app_id=os.environ.get("RAVEN_APP_ID", ""),
        app_key=os.environ.get("RAVEN_APP_KEY", ""),
    )
