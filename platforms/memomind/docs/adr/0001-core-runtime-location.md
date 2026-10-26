# ADR 0001 — Agent HUD core runtime location

- **Status:** Accepted
- **Date:** 2026-10-13
- **Decision gate:** M1.5
- **SDK evidence:** `memomind-open/plugin-open-platform` at
  `f74ee53eb70b008e665adfd81ff8a78a344a4ecb`

## Context

MemoMind applications are paired but do not share one execution environment.
The public SDK shows a native C GMP running on the glasses and a JavaScript H5
plugin running in the MemoMind phone application's WebView. The App Bridge
moves application messages between them. A successful bridge send proves
transport handoff to a running peer, not completion of Agent HUD business logic.

The GlassSDK documentation also states that GMP static/runtime state is reset
when the plugin reloads. The phone SDK exposes app-private key/value storage,
but the available documentation does not establish background execution,
delivery ordering, reconnect replay or durable exactly-once semantics.

Agent HUD must keep focus, selection and confirmation separate, must preserve
the reviewed task identity and revision, and must never resume a pending
confirmation as an automatic send after restart.

## Decision

Split responsibility across the pair:

```text
Agent HUD gateway
        │
        ▼
phone JavaScript: schema validation, authoritative request cache,
gateway transport, result correlation and duplicate/stale rejection
        │ canonical task/result messages
        ▼
glasses C: in-memory UI state machine, focus/activation separation,
confirmation snapshot and decision emission
```

The platform-neutral contract remains the source of truth under `core/`; no
MemoMind SDK type enters it. MemoMind's C state machine implements that contract
locally so that input cannot bypass confirmation even if the phone is delayed.
The JavaScript side remains authoritative for gateway-facing validation because
network/background capabilities have not been proven on the glasses.

Neither side persists a confirmation state or a pending send intent. On glasses
reload, sleep recovery or reconnect, the glasses core starts in `QUIET`. The
phone may resend the currently authoritative task, but the wearer must navigate,
select and confirm it again. A frozen in-flight decision may only be retried by
an explicit retry flow using the same `decision_id`.

## Evidence

| Claim | Evidence | Observed behavior | Interpretation | Remaining uncertainty |
|---|---|---|---|---|
| The glasses component executes as native code | Pinned `GlassSDK/README.md`, official build and Studio trace | RV32 GMP loads and receives display/input callbacks | Put the immediate UI safety state machine in C | Physical scheduling and resource behavior remain untested |
| The phone component executes as an H5 plugin | Pinned `PhoneSDK/docs/web-plugin/developer-guide.md` | JavaScript plugin loads in the phone simulator beside the GMP | Put gateway and durable-cache integration on the phone side | Background/locked/killed behavior remains untested |
| Bridge success is not business acknowledgement | Pinned `application-messaging.md` and M1.5 trace | Glasses transport acceptance precedes phone receipt validation | Keep `SEND` until a correlated Agent HUD result returns | Ordering/replay guarantees remain unknown |
| GMP state is not persistent across reload | Pinned GlassSDK documentation and reload behavior | Runtime/static state is reinitialized | Restart must return to `QUIET`, never resume `CONFIRMATION` | Sleep/wake and physical reboot still need measurement |
| Phone interruption must not preserve an armed request | Official Browser Studio lifecycle, connection and reload injection | Suspend, stop, failure and disconnect disarm the scenario; reload creates a new session | Treat every phone runtime generation as a new safety boundary | OS background/lock and real process-kill behavior remain untested |
| Shared lifecycle can execute without SDK types | `agent_hud_state.*` plus shared conformance vectors | All 22 lifecycle vectors pass in native C | The core boundary is viable on the glasses | Full UI and transport envelopes are not yet integrated |

## Consequences

- The same canonical task and decision fixtures can drive Raven, Halo and
  MemoMind without importing a shared runtime library.
- UI input remains safe when the phone is slow or temporarily unavailable.
- The phone must not display bridge acceptance as a completed decision.
- Restart recovery is intentionally conservative: review is repeated rather
  than reconstructing confirmation.
- Q17 is sufficiently answered for implementation placement. Q18 is now
  partially answered for the phone simulator but stays open for paired
  glass-side recovery, OS lifecycle and hardware. Q19 remains open until the
  delivery matrix is exercised in Studio and on hardware.

## Rejected alternatives

**Phone-only core.** Rejected because the glasses would then need to trust
remote state transitions for focus and confirmation, increasing latency and
making input safety dependent on the bridge.

**Glasses-only core and gateway client.** Rejected because public evidence does
not establish glasses networking, durable storage or background gateway access.

**Persist confirmation and resume it after restart.** Rejected because any
implicit transition from restored `CONFIRMATION` to `SEND` violates the Agent
HUD safety contract.
