"""Agent HUD — entry point.

The Raven framework requires this exact shape: a file called main.py that
calls RunApp.run with a function returning the app.

Run it with no arguments to open the simulator. The app_id and app_key
stay empty until Raven issues them; they are only needed to deploy to
real glasses, which is not open yet.
"""

from raven_framework import RunApp

from agent_hud.app import AgentHud

if __name__ == "__main__":
    RunApp.run(lambda: AgentHud(), app_id="", app_key="")
