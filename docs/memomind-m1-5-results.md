# MemoMind M1.5 integration results

**Date:** 2026-10-13
**SDK:** `memomind-open/plugin-open-platform` at
`f74ee53eb70b008e665adfd81ff8a78a344a4ecb`
**Platform status:** first-class experimental integration
**Validation:** `simulator-validated` for the M1.5 gate

MemoMind One now has an in-repository paired implementation under
`platforms/memomind/`: a C glasses GMP, a JavaScript phone MMPKG, shared wire
vectors and exactly-once/stale-decision guards.

| Check | Result |
|---|---|
| JavaScript protocol/controller tests | 6 passed |
| Native C protocol/round-trip test | 1 passed |
| Official GlassSDK build | PASS |
| Official GlassSDK inspect | PASS |
| GMP footprint in this run | 1,828 B flash; 88 B static RAM |
| Official PhoneSDK packager | PASS; 6 files; 15,595 B |
| Official paired metadata checker | PASS |
| Desktop Studio round-trip | PASS; three consecutive clean runs; `42 / 3 / test` received exactly once per run |
| Single tap safety property | PASS; focus changed and no decision was emitted |
| Duplicate replay guard | PASS; repeated `m1-5:1` was rejected |
| Installable app bundle | PASS; Studio produced `Scan to install` QR |
| Physical hardware | NOT RUN |

Local build SHA-256 evidence:

- GMP: `029e54c7f95e99a98a72238d1ef2e275916d5f1a3d0b28c29b8ccccb4ad8d142`
- MMPKG: `66d10e7f83ce79c57249dfcdb08eb664fa63a1bd10df5491927bcf56b3f616b6`

The current code proves that the proposed adapter compiles against the public
SDK, that both sides agree on the M1.5 bytes, and that the paired artifacts run
end to end in MemoMind Desktop Studio. The simulator observed request delivery,
single-tap focus without transmission, double-tap confirmation, one response on
channel `16713`, and exactly-once acceptance by the phone plugin.

The repeatability gate was then run three consecutive times. Each run delivered
the probe, kept the decision count at zero after single tap, emitted once after
double tap and reached the phone-side `PASS` state. No permission denial appeared
in any run.

This does not prove real-hardware input timing, physical readability, complete
lifecycle recovery, or background behavior. Those claims remain gated by a
MemoMind One device and the remaining M1 lifecycle tests.

## Desktop Studio evidence

The final run used Desktop Studio `0.1.0` and the pinned SDK commit above.

```text
16:04:27.953 phone -> glasses  channel=16712 payloadBytes=14
16:04:28.831 primary button   single
                     phone decision count remains 0
16:04:29.265 primary button   double
16:04:29.274 glasses -> phone channel=16713 payloadBytes=25
                     phone result: PASS — decision received exactly once
```

Accepted decision:

```json
{
  "decision_id": "m1-5:1",
  "task_id": "42",
  "revision": 3,
  "action_id": "test"
}
```

Observed simulator surface: logical framebuffer `600 × 350`, `GRAY_4`, about
`30 FPS`; compiled plugin image `1,828 B` and runtime static RAM `88 B`. These
are simulator observations, not physical-display or hardware measurements.

No permission denial occurred in the final trace. The phone package explicitly
declares the `device.info` permission used by `device.getInfo()`.

## M2B simulator evidence

The later M2B build compiles the shared state machine into the GMP, renders all
states through a bounded view adapter, normalizes both candidate input mappings
and requires a correlated phone result before showing `Sent`.

| Artifact | Size | SHA-256 |
|---|---:|---|
| `glasses.gmp` | 5,912 B package; 5,720 B flash; 2,032 B static RAM | `d7152b73a5deeddcff89af3f5057658fe36160671c7b3f23f4b3ce755d26c081` |
| `agent-hud.mmpkg` | 16,262 B | `33bf3df6ebb907a56a9053992c142bd9dbb24a4a04d1f3831dd837f506c58d43` |

The official RV32 build reports a maximum function frame of 768 B against the
1,024 B limit. Native tests, phone tests, packaging and paired metadata checks
pass. The exact M2B artifacts above were loaded into Desktop Studio and produced
this trace:

```text
19:23:36.415 glasses plugin loaded  image=5720 runtime=2032
19:23:50.398 phone -> glasses        channel=16712 payloadBytes=14
19:23:53.920 primary button         single
19:23:59.786 primary button         double
19:24:08.397 primary button         double
19:24:14.143 primary button         double
19:24:14.178 glasses -> phone       channel=16713 payloadBytes=30
19:24:14.181 Studio routes decision to phone
19:24:14.187 phone -> glasses       channel=16712 payloadBytes=28
                     HUD observed in Sent state after the ACK
```

The resulting state sequence was request open, action menu, confirmation,
`SEND`, correlated phone acceptance, then `ACK`/`Sent`. No decision was emitted
by navigation or either of the first two double taps. This establishes
`CONFIRMED_BY_SIMULATOR` for the M2B Mapping B path and ACK gate only. The phone
acceptance remains synthetic and is not evidence of live gateway integration.

## Canonical-v2 simulator rerun — 2026-10-14

The instrumented candidate (`agent-hud.mmpkg` SHA-256
`79d3fb8c5b0eb95d880ffee6ab8626f15da6b64e8305bc22995af0ddc71dd72c`)
was paired with the canonical Mapping-B GMP in Desktop Studio `0.1.0`. The
matching log set uses suffix `20261014-083721-23036`.
The three logs were copied without modification to
`platforms/memomind/artifacts/memomind/event-traces/20261014-083721-23036/`.

```text
08:38:59 phone -> glasses        channel=16712 payloadBytes=171
08:39:14 primary button         single
08:39:19 primary button         double
08:39:21 primary button         double
08:39:22 primary button         double
08:39:22 glasses -> phone       channel=16713 payloadBytes=75
08:39:22 Studio routes decision to phone
08:39:22 phone -> glasses        channel=16712 payloadBytes=71 handled=true
         HUD observed in Sent state after the correlated result
```

The complete log set contains exactly one 171-byte request, one 75-byte
decision and one 71-byte result, with one single click, three double clicks and
zero `[ERROR]` entries. Studio redacts application payload contents, so the
`ACCEPTED` classification is jointly evidenced by the deterministic phone
scenario, protocol tests and the single correlated result delivery; it is not
inferred from the byte length alone.

The same candidate then completed all three safety scenarios in the same
process:

```text
08:41:36 cancel request       channel=16712 payloadBytes=174
         1 single, 2 doubles, 3 back triggers
         0 decisions, 0 errors

08:43:54 stale revision 3    channel=16712 payloadBytes=171
08:44:10 stale revision 4    channel=16712 payloadBytes=171
         1 single, 2 doubles
         0 decisions, 0 errors

08:44:58 duplicate request   channel=16712 payloadBytes=183
08:45:05 first decision      channel=16713 payloadBytes=79
08:45:05 ambiguous result    channel=16712 payloadBytes=106
08:45:32 retry decision      channel=16713 payloadBytes=79
08:45:32 duplicate result    channel=16712 payloadBytes=75
         1 single, 5 doubles, 0 errors
```

Studio exposes message sizes but redacts the binary bodies. Reuse of the same
`decision_id` is therefore established by the phone scenario's structured
classification plus the native/protocol tests, while the Studio trace proves
that exactly two separately confirmed transmissions and two correlated results
crossed the paired bridge.

## M2 safety-scenario trace — 2026-10-14

Desktop Studio stores local runtime logs in
`platforms/memomind/vendor/plugin-open-platform/Studio/logs/`. The relevant
files for this run share suffix `20261014-070939-12964`:

- `studio-20261014-070939-12964.log`;
- `phonesdk-20261014-070939-12964.log`;
- `glasssdk-20261014-070939-12964.log`.

The two supplied `glasssdk-20261013-*` files are valid earlier-run evidence,
but they predate the dedicated cancel, stale and duplicate controls. The
2026-10-14 matching log set records the current safety run:

```text
07:16:11 phone -> glasses   channel=16712 bytes=174  cancel task
07:16:13 primary single
07:16:21 primary double
07:16:23 primary double
07:16:45 back trigger
         no channel=16713 decision before the next scenario

07:17:15 phone -> glasses   channel=16712 bytes=171  stale revision 3
07:17:19 primary single
07:17:36 primary double
07:17:37 primary double
07:17:49 phone -> glasses   channel=16712 bytes=171  replacement revision 4
         no channel=16713 decision before the next scenario

07:18:08 phone -> glasses   channel=16712 bytes=183  duplicate-safe task
07:18:12 primary single
07:18:18 primary double
07:18:20 primary double
07:18:24 primary double
07:18:24 glasses -> phone   channel=16713 bytes=79   first decision
07:18:24 phone -> glasses   channel=16712 bytes=106  ambiguous result fixture
07:18:32 primary double                                  retry review
07:18:36 primary double
07:18:36 glasses -> phone   channel=16713 bytes=79   replayed decision
07:18:36 phone -> glasses   channel=16712 bytes=75   duplicate result fixture
```

This directly confirms, in Desktop Studio, that cancel and a superseding stale
revision emitted no decision, while the duplicate-safe flow emitted twice only
after two separate confirmations and received a correlated result each time.
Studio deliberately redacts `dataBase64`, so the log alone does not expose the
two `decision_id` values or decoded result statuses. Reuse of the same ID and
`DUPLICATE` with original status `ACCEPTED` remain established by the 12-phone-
test suite plus the phone UI observation, not by raw-byte inspection of this
log.

Five `CAPABILITY_UNAVAILABLE` errors occurred between `07:16:32` and
`07:16:34`: one unhandled simulated event and four unhandled direction inputs.
They did not emit a decision, and the later Back event was handled, but they are
retained as an explicit simulator-input limitation rather than discarded as
noise.

## Phone lifecycle evidence — 2026-10-14

The current phone workspace was loaded in the official PhoneSDK Browser Studio.
Browser Studio injects phone lifecycle and connection events but does not run
the glasses GMP, so this evidence is deliberately limited to phone behavior.

With a request armed, each injected `suspended`, `stopped` and `failed` state
produced `Phone lifecycle <state> — pending test discarded`, disabled the
scenario-specific continuation and rejected a late decision as unrelated.
Returning to `running` required a fresh scenario. Disconnecting the simulated
device similarly showed `Glasses disconnected — pending test discarded`;
reconnecting restored the start controls without restoring the request.

Reloading the plugin while the duplicate-safe scenario was armed reopened the
permission launch. After launch, the UI showed `Ready for canonical Agent HUD
test` and `No run yet`. The next request used session
`mm:1698dac6-d279-4f0e-9aae-f4aec55ab371`, replacing the pre-reload session
`mm:90bbb8d2-86b9-4747-bca8-8a1ef68ead8e`. This confirms runtime-generation
isolation in the simulator and prevents an old phone request from returning
armed after reconstruction.

The instrumented rerun used session
`mm:3d8b38b8-b7ce-4617-ad28-236f3baac7a0` and retained structured entries in
the plugin's Event log. Each armed interruption recorded
`pendingDiscarded: true`, followed by `scenario.reset`; returning to `running`
or reconnecting recorded `pendingDiscarded: false` without restoring the
scenario. Visual evidence is saved under
`platforms/memomind/artifacts/memomind/screenshots/browser-event-log-2026-10-14.png`.
Browser Studio does not write these phone events to `Studio/logs/`; those files
belong to the separate Desktop Studio process.

The only browser-console error was the Studio host's missing `/favicon.ico`
resource (`404`); no plugin runtime error was observed. This does not establish
OS background/lock behavior, companion-app process-kill persistence, Bluetooth
delivery guarantees, or glass-side reconnect behavior.

## Milestone state

| Gate | State | Evidence boundary |
|---|---|---|
| M0 — pre-beta readiness | PASS | Platform-neutral contract and fixtures exist |
| M1 — SDK/Studio assessment | PASS | Official SDK pinned; both packages build, pair, load and produce an installable bundle |
| M1.5 — minimal round trip | PASS | Three clean paired Studio runs plus approved execution-placement ADR |
| M2A — SDK-independent core | PASS | Native C runs all 22 shared lifecycle vectors plus no-confirm and restart safety tests |
| M2B — MemoMind adapters | PASS | Mapping B completed in Desktop Studio with single-tap open, three-stage double-tap progression, one decision and a correlated phone ACK before `Sent` |
| M2C — canonical paired transport | PASS (code/build) | Full session/task/presentation/action envelope and 53-bit revisions match byte-for-byte in C and JavaScript |
| M2D — result and retry parity | PASS (native + simulator transport) | Native tests prove decoded statuses and decision-ID reuse; the 2026-10-14 Studio trace confirms two separately confirmed transmissions and two correlated result deliveries, with payload contents redacted by Studio |
| M2E — input/lifecycle safety | PASS (native + phone simulator) | Both mappings preserve navigation/action separation; head motion cannot confirm; native restart returns to quiet; Browser Studio suspension, stop, failure, disconnect and runtime reconstruction discard phone pending state |
| M2F — state-specific LVGL renderer | PASS (Desktop Studio visual review) | The provisional single-label renderer was rejected. The replacement multi-object 600 × 350 renderer runs in Desktop Studio; real framebuffer captures cover attention, request, actions, confirmation, stale, delivery uncertainty and Sent. The user approved the corrected renderer on 2026-10-14. |
| M2 — full simulator parity | IN PROGRESS | Canonical-v2 behavior and the approved renderer run in Desktop Studio; paired glass-side reconnect evidence remains open |
| Physical hardware | NOT RUN | No MemoMind One claim is made |

## Current canonical-v2 candidate

The 2026-10-14 replacement-renderer candidate passes 15 JavaScript tests and 8
native Python/C tests. The official RV32 build reports 11,180 B flash, 1,952 B
static RAM and a maximum function frame of 832/1,024 B. The paired metadata
checker passes. Visual approval is recorded separately below; build results alone do not establish it.

| Artifact | Size | SHA-256 |
|---|---:|---|
| Mapping-B `glasses.gmp` | 11,372 B package | `e23a60be72b96f9c0a0d25eed41c72ef0fafc710ba720beaef6e3bea4ba655a1` |
| `agent-hud.mmpkg` | 20,862 B | `79d3fb8c5b0eb95d880ffee6ab8626f15da6b64e8305bc22995af0ddc71dd72c` |

The replacement renderer was exercised in the official Desktop Studio on
2026-10-14. The Studio loaded the 11,180-byte image and displayed the real
600 × 350 glass framebuffer. The phone-side cancel test returned
`decisionsReceived: 0` after Back; a revision-4 update replaced revision 3 at
confirmation and displayed `REQUEST CHANGED`; the duplicate-safe path returned
`DUPLICATE` with `originalStatus: ACCEPTED`, followed by `SENT` on glasses.
These are simulator observations, not physical-glasses validation.

The first capture exposed a clipped `REQUEST` indicator. Its frame was widened
and the final `1 REQUEST` indicator was recaptured. A temporary Desktop Studio
`Review manifest or SHA-256 mismatch` error was caused by staging a new GMP
alongside stale review metadata. The matching encrypted review-source bundle
and hashes were staged together; Desktop Studio then showed `Scan to install`
for the paired app. The local screenshots are under
`platforms/memomind/artifacts/memomind/screenshots/`, including
`glasses-01-attention-final.png`, `glasses-02-request-final.png`,
`glasses-03-actions-final.png`, `glasses-04-confirmation-final.png`,
`glasses-06-stale-new-renderer.png`, `glasses-09-sent-ack-final.png`, and
`phone-dashboard-final.png`. These screenshots and the SDK are ignored local
artifacts. Paired glass-side reconnect evidence remains open.

The user's follow-up review identified two visual defects: the `!` was off
centre in the `REQUEST CHANGED` triangle, and button text was not centred in
both axes. The warning mark is now drawn as a geometrically centred stem and
dot rather than as a font glyph. All `focus_box` labels use horizontal centre
alignment and a four-pixel optical adjustment for the large font's glyph box.
The final build was reloaded in Desktop Studio with `Scan to install` visible;
new framebuffer captures are
`glasses-2026-10-14-buttons-final.png`,
`glasses-2026-10-14-confirmation-final.png`, and
`glasses-2026-10-14-warning-final.png`. The user approved these visual
corrections on 2026-10-14. This approval covers the Desktop Studio renderer,
not physical MemoMind One hardware or the remaining reconnect test.

## Paired package-restart probe — 2026-10-14

The current candidate was reloaded into Desktop Studio `0.1.0` for an
interruption probe. The staged phone package and the canonical artifact had
the same SHA-256 (`79d3fb8c5b0eb95d880ffee6ab8626f15da6b64e8305bc22995af0ddc71dd72c`);
the Mapping-B GMP was the `e23a60be72b96f9c0a0d25eed41c72ef0fafc710ba720beaef6e3bea4ba655a1`
build above. This matters because an earlier Studio selection still pointed
at a stale phone package without the structured Event log; that selection was
replaced before the observations below.

| Time (Studio local) | Observation |
|---|---|
| 11:35:58 | Phone session A completed sending `task-cancel`, revision 1. The HUD was advanced to the separate `CONFIRM?` screen. No `decision.received` appeared in the phone Event log. |
| 11:36:43 | The glass package selector was changed to `Not selected`. Studio rebuilt the paired runtime. A different phone session B logged `device.connection` with `connected:false`, then `scenario.reset` with `pendingDiscarded:false`. |
| 11:37:00 | The glass package was selected again. A third phone session C logged `connected:true`; the UI showed `No run yet`, and the glass HUD was quiet. No old confirmation or automatic decision was observed. |
| 11:37:20 | A *fresh* `task-cancel` request was explicitly started in the new session. |
| 11:38:51 | After single tap, two double taps, Back from confirmation and two more Back actions, the phone test reported `PASS — cancel emitted no decision`; its structured result was `{"passed":true,"decisionsReceived":0,"event":"scenario.cancel.verified"}`. |

The Desktop Studio UI and its local `studio-20261014-093155-20592.log` are the
evidence sources. The latter records package-share restarts at 11:36:43 and
11:37:00; the structured phone entries above were observed in Studio's Web
Logs/Event log. They are not present in the separate `phonesdk`/`glasssdk`
files, which were empty for this run. No raw Studio logs or screenshots are
committed.

**Evidence boundary:** changing the glass package selector restarts the
paired Studio packages, including the phone plugin. It is not a live
Bluetooth disconnect/reconnect delivered to an already-running GMP. In
particular, `pendingDiscarded:false` belongs to a *new* phone session and
cannot prove that the armed old session handled a disconnect event. This
probe confirms safe reconstruction after a package restart and a fresh
cancel-without-send path; it does **not** close the paired glass-side
reconnect gate. Desktop Studio exposes no documented connection toggle for
that paired GMP test. M2 therefore remains `IN PROGRESS`, and PR #8 remains
draft until a supported disconnect/reconnect stimulus (or physical-device
evidence) proves the full path.
