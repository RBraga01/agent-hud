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
| `agent_hud/tasks.py` | no | the task contract and its parser |
| `agent_hud/config.py` | no | settings from the environment |
| `agent_hud/client.py` | no | fetching from the gateway |
| `agent_hud/navigation.py` | no | which of the six screens you are on, and what moves you |
| `agent_hud/transitions.py` | no | which motion plays on a screen change, and how far it travels |
| `feeders/simulated.py` | no | invented items, no accounts needed |
| `feeders/claude_hook.py` | no | reads state from the Claude Code hooks (supported) |
| `feeders/claude_sessions.py` | no | reads transcript files directly (no setup, undocumented format) |
| `feeders/codex.py` | no | reads Codex CLI sessions from `~/.codex` (undocumented format) |
| `feeders/__init__.py` | no | `collect()` runs the chosen feeders; `file_items()` reads a hand-edited file and raises `FileFeederError` when it exists but is not JSON |
| `integrations/claude_code/*.py` | no | four hook scripts + `_hook_common.py` — plain stdlib, always exit 0, never store prompt/error text |
| `stub_server/server.py` | no | the development gateway |
| `agent_hud/screens/*.py` | **yes** | building each screen's widgets, and nothing else |
| `agent_hud/app.py` | **yes** | placing screens, forwarding events, asking the gateway |

When you add behaviour, ask which side of that line it belongs on. Almost always it is the framework-free side.

## The rule that outranks everything else

**A calm display and a broken one must never look alike.**

The whole product is "you can trust that nothing on screen means nothing needs you". Every failure has to stay visible, so three outcomes are kept strictly apart:

| What came back | What happens |
|---|---|
| A list, with nothing in it | Idle. The world really is calm. |
| A list, with items | Show them. |
| Not a list at all, or unreachable | Keep the last known list, and mark it incomplete. |
| A list where some entries were malformed | Show the good ones, and mark it incomplete. |
| More than `MAX_TASKS`, or an entry's text over length | Keep the first `MAX_TASKS`, cut over-long `title`/`detail` to fit, and mark it incomplete. A response over `MAX_RESPONSE_BYTES` is refused unread and treated as unreachable. |
| A feeder threw while building the list | Let it propagate. `stub_server` returns 500, the client reads that as not-ok, and the screen keeps the last list and marks it incomplete. `file_items()` raises `FileFeederError` for a present-but-unparseable file for exactly this reason — it must not return `[]`. |

`parse_tasks` reports `valid`, `dropped` and `truncated` separately for this reason, and `AgentHud.is_complete` (online **and** `dropped == 0` **and** `truncated == 0`) is what drives the amber marker. The caps live at the contract boundary — `MAX_RESPONSE_BYTES` in `client.py`, `MAX_TASKS` / `MAX_SOURCE` / `MAX_TITLE` / `MAX_SUMMARY` / `MAX_DETAIL` / `MAX_LABEL` in `tasks.py` — so every feeder inherits them. If you ever find yourself returning an empty list for a failure, stop: that is the one bug this project cannot afford.

## Looking is not pressing

The second rule, and it is not negotiable or configurable.

**Gaze position is read for focus only.** `tick_gaze` records where the wearer is looking and does nothing else — no timer, no state to advance. If you ever find yourself writing "if the gaze has been here for N milliseconds, then…", stop: that is gaze-activation, and it is the thing this product must not do.

**Activation arrives as a framework `Button`'s `clicked` signal.** RavenOS emits it when the wearer double-blinks at the focused control or completes a dwell on it. Which of the two it was is the wearer's setting and the OS's business; the app is not told and does not need to be.

The consequence for the code: **anything pressable must be a real `Button`**. Building a "button" out of an outlined `Container` would mean re-implementing activation from gaze ourselves, which is exactly the forbidden thing wearing a different hat.

**Selecting is not sending.** Choosing an action opens the confirmation screen. `navigation.advance` is a pure function and could not send anything if it wanted to; only `app.py`, and only after `CONFIRM`, may talk to the gateway.

## What the framework actually gives you

Checked against the installed framework on 2026-09-02. Several of these contradict what you would assume.

| You want | What is really there |
|---|---|
| A double-blink event | **There is no API.** `peripherals/eye_control.py` exposes only `get_gaze_position()`. Blink and dwell both arrive as `Button.clicked`, and the app cannot tell them apart. |
| The dwell progress ring | Already built into `components/button.py`: `dwell_time`, `use_fill_dwell`, `enable_quad_dwell`. Configure it; do not draw your own. |
| Focus feedback on hover | `Button` already scales and lights on `enterEvent`. In the simulator the cursor *is* the gaze. |
| Scrolling | `components/scroll_view.py` has `ScrollView` and `PaginationContainer`. Raven's own guidance prefers pagination, and so do we: one glance per page beats holding your eyes on moving text. |
| `ClickButton` | The **physical** button on the glasses (Enter in the simulator). Not the eye. |

## Only one request at a time

The poll interval is shorter than the request timeout. Without a guard, a slow gateway leaves several requests in flight and an older answer can land after a newer one, walking the display backwards. `_refresh_in_background` refuses to start a second fetch while one is running, and clears the guard in a `finally` so a failure cannot latch it shut. Skipping a tick is harmless; the next is seconds away.

The **first** fetch at startup goes through this same background path, not a blocking call. `__init__` renders the resting frame and returns; the count fills in when the answer arrives. Against a remote gateway a blocking first fetch would otherwise hold the glasses on the resting frame for the whole request timeout. `refresh_now()` is the synchronous form, kept for tests only.

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
| `python main.py deploy` | Raven's packager walks the whole directory and copies every `.py` plus `.json`/`.md`/`.gif`/... It ignores `.gitignore`. Its own guard only skips a folder literally named `raven_framework` (underscore), not the `raven-framework` clone. `.ravignore` is what keeps the framework, tests and docs out of the upload — keep it current. |
| `app_id` / `app_key` at runtime | `RunApp.run` passes them into `bind_sleep_wake` and on into peripheral authentication, not only into `deploy`. For current internal testing Raven checks out the app and adds internal credentials locally; the public developer token / runtime mechanism has not been released yet. Agent HUD therefore keeps credentials out of source control and reads them from `RAVEN_APP_ID` / `RAVEN_APP_KEY`. Our `EyeControl()` call does not thread credentials through — revisit once the public mechanism exists. |
| `border_color=` on any container or button | Silently ignored. The theme sets `use_gradient_border=True` with a **white-to-grey** gradient, which overrides it — which is why every outline came out white the first time. Spread `style.outline()` into the constructor to set the gradient explicitly. |
| `background_color=` on a `Button` | Silently discarded when `use_fill_dwell` is on, which it is by default: the framework paints its own dwell fill instead, so a button you meant to be filled comes out hollow. Pass `use_fill_dwell=False` when the fill is the point. |
| Centring a child inside a container | `VerticalContainer`/`HorizontalContainer` only stack; they centre nothing. Nudging `inner_margin` to fake it breaks the moment a label changes length. Use a `Container` and `add(widget, x, y)`. |
| A container with no `height` in a card | Reserves no space, so the card closes early and the contents spill through its bottom border. State the height (see `parts.button_row`). |
| `AsyncRunner.run(fn, on_complete=…)` | The callback takes **no arguments** and `fn`'s return value is discarded. The documentation says otherwise and following it raises. Carry results on the instance. |
| A clickable `Icon` | Draws no outline until the dwell starts. It needs a bordered container behind it to have any visible shape at rest. |
| Sizing a `VerticalContainer` to exactly fit | The box layout compresses children to make room for text's real height. Leave slack or things get clipped. |
| Animating `b"geometry"` on a framework widget | It has a fixed size (`setFixedSize`), which `QPropertyAnimation` on geometry fights. `_animate_in` animates `b"pos"` plus a `QGraphicsOpacityEffect` instead — a slide-and-fade, not a scale. |

## Testing

```bash
pytest
ruff check .
```

Screen tests skip when the framework is absent. That is intended.

Two rules learned the hard way:

0. **Transitions must settle to a clean rebuild.** `_animate_in` builds the new tree, animates it in, then `_settle` forces a plain `_render()`. A test that changes state under `animations=True` must pump the loop until `hud._transitioning` is `False` (`drain()` in `test_app.py`), or set `animations=False`.
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
- No tool-specific knowledge in the app. It draws a list of items; feeders know about the tools. Adding a source means adding a module to `feeders/` and naming it in `KNOWN_FEEDERS`, and changing nothing in `agent_hud/`.
- No reading of anyone's personal data by default. `simulated` is the default feeder for that reason, and the Claude reader keeps prompt text off unless it is asked for.
- No third-party Python packages in the glasses app beyond what the framework already bundles. How extra packages get installed onto the device is undocumented.

## Repository rules

- **Never commit the Raven Framework.** It is proprietary and gitignored. Do not add any part of it.
- **Never commit credentials.** No API keys, no `app_id`, no `app_key`, no machine names or internal addresses.
- **Test data is invented, never observed.** Fixtures must not contain anything seen on a real machine: no real project names, folder layouts, prompts or session identifiers. This has already gone wrong once. Reading real data while developing a feeder is exactly how it happens — you see plausible values on screen and reach for them when writing the test an hour later. Make names up, and make them obviously made up.
- The framework, the virtual environment, the `logs/` directory it creates, and all local tooling are gitignored. Check `git status` before committing.
