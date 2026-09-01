# AGENTS.md — agent-hud

Notes for coding agents working on this project. Read this before changing anything.

## What this is

A display for Raven Prism smart glasses that shows whether anything needs the wearer's attention. Python, built on the Raven Framework, which wraps Qt.

## The rule that shapes every file

**Keep logic out of the screen.**

The Raven Framework is proprietary. Its licence grants no right to use it, so it is never installed in automated checks. Anything that needs it cannot be tested there.

So every decision worth testing lives in a module that does not import the framework:

| Module | Needs the framework | What it holds |
|---|---|---|
| `agent_hud/items.py` | no | the contract and its parser |
| `agent_hud/config.py` | no | settings from the environment |
| `agent_hud/client.py` | no | fetching from the gateway |
| `agent_hud/interaction.py` | no | when the detail panel is showing |
| `stub_server/server.py` | no | the development gateway |
| `agent_hud/app.py` | **yes** | placing widgets, and nothing else |

When you add behaviour, ask which side of that line it belongs on. Almost always it is the framework-free side.

## Things about this display that are not obvious

The glasses can only **add** light to the world. They can never darken it. Everything below follows from that one fact, and all of it was learned by rendering the screen and looking at it.

- **A dark fill is invisible.** Black adds nothing, so a black shape does not hide what is behind it. It is not a background.
- **A bright fill is the most visible thing available.** Large shapes therefore want outlines, so they do not glow as solid blocks. Small markers want solid fill, so their light stays concentrated — a thin ring on a small dot gets scattered by the optics until nothing is left.
- **Enclosure is how text stays readable.** A bright thin edge around text survives almost any background and gives the eye something to lock onto.
- **White is the ceiling.** Text is already `#FFFFFF`, so over a bright sky it will wash out and nothing can be done about it. Weight is the only lever left, which is why body text is medium rather than regular.

## Traps in the framework

All of these cost real time. None are in Raven's documentation.

| Trap | What happens |
|---|---|
| `disabled=True` on an `Icon` | Renders at reduced opacity. On this display, dimming is the same as deleting. |
| `Container` vs `VerticalContainer` | `Container` defaults `border_color` to transparent; `VerticalContainer` defaults it to the theme colour. A bare `Container` draws no visible edge at any border width. |
| `is_main_container=True` | Sets the background and border width but **not** the corner radius, despite the docstring. |
| `Button(content_widget=…)` | Stretches the content to fill the button. A `VerticalContainer` inside stacks from its own top edge, so without an inner margin the first line lands on the border. |
| `Container.clear()` | Calls `deleteLater()` on every child. A widget kept between redraws becomes a dangling pointer. Build fresh every time. |
| `AsyncRunner.run(fn, on_complete=…)` | The callback takes **no arguments** and `fn`'s return value is discarded. The documentation says otherwise and following it raises. Carry results on the instance. |
| A clickable `Icon` | Draws no outline until the dwell starts. It needs a bordered container behind it to have any visible shape at rest. |
| Sizing a `VerticalContainer` to exactly fit | The box layout compresses children to make room for text's real height. Leave slack or things get clipped. |

## Testing

```bash
pytest
ruff check .
```

Screen tests skip when the framework is absent. That is intended.

Two rules learned the hard way:

1. **`processEvents()` does not deliver `DeferredDelete` events.** Use the `pump()` helper in `tests/test_app.py`, which also calls `sendPostedEvents(None, QEvent.Type.DeferredDelete)`. Without it, widgets Qt has destroyed still look alive and a whole class of crash stays hidden until the app is run for real.
2. **A passing suite is not evidence the app runs.** Launch the simulator before claiming anything works.

## Design rules from Raven

Do not invent values. Take them from `raven_framework.helpers.themes.RAVEN_CORE`. Setting a flat `border_color` switches off the theme's white-to-silver gradient and makes the app look subtly foreign next to a real Raven screen.

- Text sizes: 38 title, 33 headline, 28 body, 18 small. Nothing smaller than body except sparingly.
- Interactive things go on the right. The display sits over the right eye, so assume asymmetry rather than centring for balance.
- At most six lines on screen.
- Cards are only as tall as their contents. A card sized to the full display leaves an empty box hanging in the wearer's vision.
- Colour never carries meaning on its own.

## What this project will not do

From the design spec, and not open for reinterpretation:

- No acting on items from the glasses. Reading only. Approving things from a display driven by eye tracking is a much bigger decision about safety.
- No tool-specific knowledge in the app. It draws a list of items; the gateway knows about GitHub and the rest.
- No third-party Python packages in the glasses app beyond what the framework already bundles. How extra packages get installed onto the device is undocumented.

## Repository rules

- **Never commit the Raven Framework.** It is proprietary and gitignored. Do not add any part of it.
- **Never commit credentials.** No API keys, no `app_id`, no `app_key`, no machine names or internal addresses.
- The framework, the virtual environment, the `logs/` directory it creates, and all local tooling are gitignored. Check `git status` before committing.
