# Agent HUD for MemoMind One

MemoMind One is the third in-repository Agent HUD ecosystem. This directory is
an **experimental paired implementation** built against the public MemoMind
plugin platform at commit
`f74ee53eb70b008e665adfd81ff8a78a344a4ecb`.

The official builders compile the glasses C code to a GMP and package the phone
JavaScript as an MMPKG. The paired implementation has completed the original
M1.5 and M2B round trips in MemoMind Desktop Studio. The current source adds the
canonical v2 task envelope, exact result semantics, safe retry, both input-map
journeys, restart guards and a native multi-object 600 × 350 LVGL renderer.
Those additions pass native and official-SDK checks. Phone lifecycle
interruption and runtime reconstruction are also verified in the official
Browser Studio. The corrected renderer was captured in Desktop Studio and
visually approved on 2026-10-14; the earlier functional single-label UI was
rejected as not matching Agent HUD. Physical MemoMind One validation remains open.

M2A–M2E are implemented. The SDK-independent C core runs all shared lifecycle
vectors, and the bound M2B build completed the Mapping B flow in Desktop Studio:
request, single-tap open, three deliberate double taps, correlated phone ACK,
then `Sent`. M2F visual review is complete; paired glass-side reconnect
evidence is still required before full simulator parity is marked complete.

## Architecture

```text
Agent HUD gateway (not connected in M1.5)
                 │
     phone-side JavaScript plugin
     validates task/revision/action
                 │ channels 0x4148 / 0x4149
                 ▼
       glasses-side C GMP runtime
     renders HUD and handles buttons
```

The repository's platform-neutral contract remains under [`core/`](../../core/).
MemoMind SDK types stay inside this directory. ADR 0001 places the in-memory UI
state machine on the glasses and gateway transport, authoritative request cache
and duplicate/stale validation on the phone. Confirmation/send intent is never
persisted; a reload returns the glasses to `QUIET` and requires fresh review.

## What M1.5 proves

The minimal round-trip deliberately avoids the complete Agent HUD interface:

```text
phone sends { task_id: "42", revision: 3, display_code: 1 }
  → glasses display "1"
  → single tap only changes focus text
  → double tap prepares action "test"
  → glasses return a stable decision_id
  → phone accepts the matching decision once
```

Back cancels without sending. A repeated double tap after an accepted transport
does not send again. The phone rejects a duplicate `decision_id`, an unrelated
task, a stale revision, or an action other than the one it armed.

The GMP message `bt_send` success is treated only as transport acceptance. It is
not displayed as gateway `Sent`, because the M1.5 probe does not yet reach the
Agent HUD gateway.

In the current M2B build, the phone returns a correlated application result
after validating the decision. Only that result can move the glasses from
`SEND` to `ACK`. This is still a synthetic phone-side acceptance, not a live
gateway integration.

## Build and test

Clone the public SDK at the exact pinned commit. The SDK is a separate
dependency and must remain ignored:

```powershell
Set-Location platforms/memomind
git clone https://github.com/memomind-open/plugin-open-platform.git vendor/plugin-open-platform
git -C vendor/plugin-open-platform checkout f74ee53eb70b008e665adfd81ff8a78a344a4ecb

npm test
python -m pytest tests/test_m1_5_round_trip.py -q
python -m pytest tests/test_state_machine_conformance.py -q
python -m pytest tests/test_m2_adapters.py -q
python vendor/plugin-open-platform/GlassSDK/build.py build --project glasses
```

On Windows, the complete repeatable preparation path is:

```powershell
.\tools\prepare-studio.ps1
```

It verifies the pinned SDK commit, runs all 19 MemoMind tests, builds the GMP,
packages the MMPKG, checks paired metadata and prints both SHA-256 hashes. The
Studio build uses Mapping B. Mapping A is implemented and covered by native
physical-journey tests, but is not yet claimed as a Studio-tested profile.

### Manual safety scenarios in Desktop Studio

The phone workspace exposes three dedicated scenarios. Run them independently:

1. **Cancel sends nothing:** select `Start cancel test`, then use single tap,
   double tap, double tap and Back. Select `Verify no decision received` on the
   phone; it must report `PASS`.
2. **Stale revision is blocked:** select `Start stale test`, reach confirmation
   with single tap and two double taps, then select `Supersede with revision 4`
   on the phone. The HUD must show `Stale`; no decision may cross the bridge.
3. **Duplicate confirmation is idempotent:** select `Start duplicate-safe
   retry`, then use single tap and three double taps. The injected ambiguous
   result must show an error. Double tap once to review the retry and once more
   to confirm it. The phone must return `DUPLICATE` with original status
   `ACCEPTED`, and the HUD must finish at `Sent` using the same decision ID.

These are simulator fixtures. They do not claim real-device debounce,
persistence, or delivery guarantees.

### Phone lifecycle scenarios in Browser Studio

Run the official PhoneSDK Browser Studio when testing phone-only lifecycle
semantics. Arm any safety scenario before each interruption, then inject:

- `suspended`, `stopped` and `failed` lifecycle states;
- device disconnect followed by reconnect;
- plugin `Reload`, including the renewed permission launch.

For every interruption the phone must disarm the request and show `Pending test
discarded. Start a fresh scenario.` Returning to `running` or reconnecting must
not restore it. A plugin reload must start with `No run yet` and a new
`session_id`. Browser Studio does not execute the glasses GMP, so these checks
are evidence for the phone runtime only; glass-side disconnect recovery still
requires the paired Desktop Studio.

The plugin's **Event log** panel retains the newest 30 structured phone-runtime
entries for Browser Studio evidence, including session identity, connection,
lifecycle, request, decision, result and reset events. The same entries are
also emitted to the plugin console with the `[AgentHUD]` prefix. Browser Studio
does not write these events to `Studio/logs/`; that directory belongs to the
separate Desktop Studio process.

Desktop Studio writes one matching `studio-*`, `phonesdk-*` and `glasssdk-*`
log set per process under:

```text
vendor/plugin-open-platform/Studio/logs/
```

Use the shared timestamp and process suffix to correlate a run. The SDK checkout
and its logs are intentionally gitignored, so durable conclusions from a trace
must be summarized in `../../docs/memomind-m1-5-results.md` before the local
logs are cleaned or the SDK checkout is replaced.

Prepare and package the phone side without committing the SDK runtime:

```powershell
New-Item -ItemType Directory -Force phone/vendor, artifacts | Out-Null
Copy-Item vendor/plugin-open-platform/PhoneSDK/examples/life-desk/vendor/gm-plugin-web-sdk.esm.js phone/vendor/
node vendor/plugin-open-platform/PhoneSDK/tools/build-mmpkg.mjs phone artifacts/agent-hud.mmpkg
```

Then check that the MMPKG and GMP declare the same paired application:

```powershell
python vendor/plugin-open-platform/.agents/skills/memomind-example-app/scripts/check_pair.py `
  --web artifacts/agent-hud.mmpkg `
  --glass glasses/manifest.json `
  --gmp glasses/.build/glasses/glasses.gmp
```

Generated `.gmp`, `.mmpkg`, copied SDK runtime and SDK checkout are ignored.

## Evidence status

Use only these labels for platform claims:

```text
PUBLICLY_ANNOUNCED
NOT_AVAILABLE_YET
UNKNOWN
CONFIRMED_BY_DOCS
CONFIRMED_BY_SIMULATOR
CONFIRMED_ON_HARDWARE
```

| Claim | Evidence | Observed behavior | Interpretation | Remaining uncertainty |
|---|---|---|---|---|
| C app and JS plugin can declare a pair | Official manifests, `check_pair.py`, and Studio pair selection | Studio reports `Recommended pair: glass protocols fully match` | `CONFIRMED_BY_SIMULATOR` | Physical install still untested |
| Glasses C source is ABI-compatible | Official GlassSDK build and Desktop Studio runtime log | GMP loaded and started; 1,828 B image and 88 B static RAM | `CONFIRMED_BY_SIMULATOR` | Hardware resource behavior untested |
| M1.5 wire format is identical in C and JS | Shared vectors, native tests, and Studio event trace | Request used channel `16712`; matching decision used `16713` and was decoded by the phone | `CONFIRMED_BY_SIMULATOR` | Delivery guarantees outside this run remain unknown |
| Single and double tap are distinct | Studio input trace and phone state | Single tap changed the HUD to `Focused` without a response; double tap emitted one response | `CONFIRMED_BY_SIMULATOR` | Real-hardware debounce behavior not tested |
| Full M1.5 round-trip works | Studio trace recorded on 2026-10-13 | `42 / 3 / test` arrived exactly once and displayed `PASS` | `CONFIRMED_BY_SIMULATOR` | M1.5 does not yet reach the live Agent HUD gateway |
| M2B Mapping B preserves confirmation separation | Studio trace recorded on 2026-10-13 | Single tap opened the request; three double taps traversed actions, confirmation and send; no decision was emitted before the third double tap | `CONFIRMED_BY_SIMULATOR` | Mapping A, head motion and physical debounce remain untested |
| Correlated phone ACK gates `Sent` | Paired Studio transport trace | Glasses emitted a 30-byte decision on channel `16713`; the phone returned a 28-byte result on channel `16712`, which the glasses received | `CONFIRMED_BY_SIMULATOR` | This is synthetic phone acceptance, not a live Agent HUD gateway |
| Duplicate decision is blocked | Restarted glasses side with phone session retained | Phone rejected replayed `m1-5:1` as `duplicate-decision` | `CONFIRMED_BY_SIMULATOR` | Persistence across app kill/device reboot remains unknown |
| Logical simulator canvas is 600 × 350 | Desktop Studio HUD metadata | Studio ran the GMP at `600 × 350`, `GRAY_4`, approximately 30 FPS | `CONFIRMED_BY_SIMULATOR` | Physical resolution, safe area and panel refresh remain separate unknowns |
| Phone lifecycle interruption discards pending approval | Official Browser Studio lifecycle injection on 2026-10-14 | `suspended`, `stopped` and `failed` each disarmed the active scenario; returning to `running` required a fresh test | `CONFIRMED_BY_SIMULATOR` | OS background/lock behavior and real process termination remain untested |
| Phone disconnect/reconnect does not replay a request | Official Browser Studio connection injection on 2026-10-14 | Disconnect disarmed the active scenario; reconnect enabled controls but did not restore it | `CONFIRMED_BY_SIMULATOR` | Paired glass-side recovery and Bluetooth delivery behavior remain untested |
| Phone runtime reconstruction starts a new session | Official Browser Studio plugin reload on 2026-10-14 | Armed state was lost, UI returned to `No run yet`, and `session_id` changed | `CONFIRMED_BY_SIMULATOR` | Companion-app kill and physical-device persistence remain untested |
| Paired package restart does not restore confirmation | Desktop Studio package-selector probe on 2026-10-14 | Removing and reselecting the glass package restarted both runtimes; the HUD returned to quiet and the phone required a fresh request | `CONFIRMED_BY_SIMULATOR` | This is not a live Bluetooth disconnect/reconnect delivered to an active GMP |

## Open lifecycle and transport gates

The following remain explicit M1 questions rather than assumptions:

- **Q17 — execution model:** confirm where the C GMP, Web plugin, background
  work, network calls, request cache and validation actually execute.
- **Q18 — persistence/restart:** test what survives app, simulator, glasses and
  phone restarts. Confirmation state must never resume by sending.
- **Q19 — delivery guarantees:** measure ordering, reliability, duplicate
  delivery, reconnect replay, acknowledgement, fragmentation and payload limits.

| State | Glasses app | Phone plugin | Expected behavior |
|---|---|---|---|
| Phone foreground | active | active | baseline |
| Phone background | unknown | unknown | test |
| Phone locked | unknown | unknown | test |
| Bluetooth reconnect | unknown | simulator-confirmed reset | no replayed approval |
| Glasses sleep/wake | recover | unknown | no implicit send |
| Glasses reboot | restart | recover | confirmation is not resumed |
| Phone app killed | unknown | restart | old request is not presented as new |

Do not normalize display or refresh discrepancies before measurement. Record
physical resolution, logical app resolution, safe drawable area and simulator
framebuffer separately. Likewise, distinguish panel refresh from application
render rate.

## Next gates

1. Interrupt the paired flow at confirmation, verify the glasses return to
   quiet/disconnected without sending, reconnect, and require a fresh request.
   Desktop Studio's package selector restarts both runtimes and cannot by
   itself close this gate; use a supported live connection stimulus or real
   hardware. The limited restart probe is documented in the evidence report.
2. Confirm the Mapping B trace still emits exactly once and that retry requires
   a new confirmation while reusing the decision ID.
3. Exercise background, lock and sleep cases that only Desktop Studio or
   physical hardware can represent; native restart safety is already covered.
4. Repeat the evidence run on a physical MemoMind One. Live gateway transport
   remains a later integration, matching Halo's present claim boundary.

Paired reconnect and physical-glasses validation are tracked in
[issue #10](https://github.com/RBraga01/agent-hud/issues/10). The experimental
port can be published without claiming either gate has passed.

The exact M1.5 simulator trace and measurements are recorded in
[`../../docs/memomind-m1-5-results.md`](../../docs/memomind-m1-5-results.md).
The execution placement and restart policy are frozen in
[`docs/adr/0001-core-runtime-location.md`](docs/adr/0001-core-runtime-location.md).

Agent HUD is independent and is not affiliated with MemoMind. The MemoMind SDK
and trademarks remain subject to their own terms.
