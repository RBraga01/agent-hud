# Implementation plan: Agent HUD Companion

Date: 2026-10-19
Status: proposal for human review; **no implementation is authorized yet**

## Goal and approved boundaries

Build an independent Agent HUD companion for connection setup, diagnostics and recovery. The phone is not an agent dashboard or execution host. Only when the selected glasses are unpaired/unavailable may it show a verified pending decision for deliberate review. Healthy glasses mean no phone queue. The normative experience and transitions are in [`../specs/2026-10-19-companion-app-ux-design.md`](../specs/2026-10-19-companion-app-ux-design.md) and [`../../design/ai-states/agent-hud-companion.md`](../../design/ai-states/agent-hud-companion.md).

Proposed stack, to confirm at this plan review: Flutter/Dart for one shared mobile UI and state core, Android as the first runnable target, platform-specific adapters only for credentials, local-network access and notifications. iOS remains source/layout-ready but is not a tested or distributable deliverable without its own toolchain, device and distribution validation. No T.I.O. dependency. Do not claim any physical glasses or background alerts work until the relevant end-to-end gate passes. Flutter's [platform guide](https://docs.flutter.dev/platform-integration) supports the shared-codebase approach, while its [accessibility testing guide](https://docs.flutter.dev/ui/accessibility/accessibility-testing) provides automated checks; neither substitutes for device tests.

Every code step below is a **microstep capped at 50 changed lines**. If the indicated action needs more, split it into successive tests and implementation edits in the named files before execution. Each phase is a separate mergeable increment, with feature gates keeping unfinished controls unavailable. Exact `companion/` paths are proposed future files; they do not exist yet.

## Pre-implementation decisions and risks

1. The current gateway's generic `device_last_seen` is updated by any `GET /tasks`, including a phone poll; it cannot establish selected-glasses presence. Use authenticated per-device identity/heartbeat, not generic activity. Verify that `devices_payload().last_seen` has suitable freshness semantics before treating it as health.
2. `GET /tasks` currently emits `X-Tasks-Version` only with a persistent store. The companion needs an explicit, monotonic, completeness-bearing snapshot contract across all gateway modes. A version alone does not prove completeness.
3. Current `control/control.js` maps a non-list `tasks.tasks` to `[]` while marking online. That safety bug must be corrected before any shared client behavior or contract is trusted. The browser Control remains separate from the new companion UI.
4. A phone send must be refused by the gateway when the selected glasses are healthy or when its decision/revision has changed. The gateway needs an atomic eligibility and idempotency check; a UI-only preflight has a race. Preserve compatibility with existing glasses callers and stable `request_id` semantics. The proposed mobile `decision_id` must map unambiguously to that gateway idempotency key.
5. Confirm the secure phone-auth integration and Android background-delivery feasibility in a bounded prototype before promising either in product copy. No credential or task text enters logs, analytics or notification bodies.

## Phase 0 — trustworthy gateway boundary (minimum safe slice)

Deliverable: a backwards-compatible, test-covered gateway contract that distinguishes current complete data, selected-device health, and decision eligibility. The existing Control no longer renders a malformed list as calm. No companion code or public compatibility claim yet.

| Step (each ≤50 changed lines) | File | Action and why | Dependencies | Risk |
|---|---|---|---|---|
| 0.1 Contract vectors | `core/companion_snapshot.schema.json` | Define version, completeness, selected environment, task revision and error semantics; make missing data unverified, not empty. | None | High |
| 0.2 Contract tests | `tests/test_companion_snapshot_contract.py` | Add invented valid, empty, malformed, partial, stale and out-of-order vectors before server changes. | 0.1 | Low |
| 0.3 Snapshot response | `stub_server/server.py` | Emit the contract consistently for all gateway modes without changing existing glasses' `/tasks` parsing; use a separate versioned endpoint if additive fields cannot remain compatible. | 0.2 | High |
| 0.4 Device identity tests | `tests/test_auth.py` | Prove only authenticated selected-glasses activity advances that device's health; phone reads do not. | 0.1 | Medium |
| 0.5 Device health | `stub_server/auth.py` | Expose trustworthy per-device freshness/identity to gateway policy, with expired/revoked devices excluded. | 0.4 | High |
| 0.6 Eligibility tests | `tests/test_decision_contract.py` | Cover healthy-glasses race, changed revision/action, duplicate idempotency key, unknown response and legacy glasses send. | 0.3, 0.5 | High |
| 0.7 Atomic send gate | `stub_server/policy.py` | Make phone continuity eligibility, revision, offered-action and idempotency checks one authoritative gateway decision; do not weaken glasses behavior. | 0.6 | High |
| 0.8 Server wiring | `stub_server/server.py` | Pass authenticated caller/device identity to the atomic policy gate; prevent check/send races while preserving legacy glasses calls. | 0.7 | High |
| 0.9 Control regression test | `tests/test_control_page.py` | First demonstrate malformed-as-empty and require visible unverified state. | 0.2 | Low |
| 0.10 Control fix | `control/control.js` | Keep last-known state visibly unverified when `/tasks` is not a list; never coerce it to a verified empty list. | 0.9 | Medium |

Tests: unit contract/parser, health and policy tests; integration `GET /tasks` and decision POST with auth/TLS, legacy glasses vectors, failed feeder and races; E2E browser Control with malformed tasks and fresh empty tasks. Gate: no missing/partial/stale/out-of-order response can mean verified zero or authorize a phone send; no generic phone polling can mark glasses healthy. Run relevant pytest files, full pytest, Ruff, publication hygiene.

## Phase 1 — Android shell and truthful read-only state

Deliverable: installable development build with Estado/Ligações/Ajuda, B light/A dark, selected environment and all Home states driven by invented fixtures or the Phase 0 read-only API. Decision controls remain disabled; no physical device claims.

| Step (each ≤50 changed lines) | File | Action and why | Dependencies | Risk |
|---|---|---|---|---|
| 1.1 Scaffold | `companion/pubspec.yaml` | Create Flutter app with pinned, reviewed dependencies and test tooling; Android first. | Phase 0 contract | Medium |
| 1.2 Theme tokens | `companion/lib/theme/companion_theme.dart` | Encode Warm Clarity B and Quiet Signal A with identical hierarchy and non-colour indicators. | 1.1 | Low |
| 1.3 Navigation | `companion/lib/app.dart` | Three bottom destinations and selected-environment header; no dashboard feed. | 1.2 | Low |
| 1.4 State reducer | `companion/lib/state/home_state.dart` | Pure priority reducer for blocked, unavailable, unverified, partial, uncertain, continuity and healthy. | 1.1, Phase 0 | High |
| 1.5 Snapshot adapter | `companion/lib/gateway/snapshot_client.dart` | Parse complete/current/versioned observations fail-closed; reject late or lower versions, including resume/switch. | 1.4 | High |
| 1.6 Read-only screens | `companion/lib/screens/status_screen.dart` | Vertical status/diagnosis layout; healthy Home has no count or queue. | 1.3–1.5 | Medium |
| 1.7 Tests | `companion/test/home_state_test.dart` | Table-test every priority edge and stale/empty distinction. | 1.4–1.6 | Low |

Tests: unit priority/reorder reducer; widget both themes, healthy-no-queue, 200% text; integration with fake gateway returning empty/partial/stale/offline; E2E Android emulator launch, navigation and environment visibility. Gate: read-only state remains truthful and no action can send.

## Phase 2 — secure gateway onboarding and sources

Deliverable: user can connect a selected gateway through QR or manual address, verify certificate identity, authenticate, inspect source setup and run an honest synthetic test. Skipped steps remain visible; no unsafe QR credential shortcut.

| Step (each ≤50 changed lines) | File | Action and why | Dependencies | Risk |
|---|---|---|---|---|
| 2.1 Gateway discovery input | `companion/lib/screens/gateway_setup_screen.dart` | QR/manual address flow with malformed-QR and no-discovery explanations. | Phase 1 | Medium |
| 2.2 Trust check | `companion/lib/gateway/trust_store.dart` | Explicit pin/fingerprint comparison and mismatch block; no silent trust or failover. | 2.1 | High |
| 2.3 Phone auth | `companion/lib/gateway/phone_auth.dart` | Platform-protected credential/session path compatible with gateway passkeys and one-time bootstrap token. | 2.2, Phase 0 | High |
| 2.4 Gateway auth contract | `stub_server/server.py` | Add only the setup/auth surfaces proven necessary by the phone prototype; preserve current security gates. | 2.3 | High |
| 2.5 Sources | `companion/lib/screens/sources_screen.dart` | Guide/verify Codex, Claude Code and read-only GitHub feeder truthfully; allow defer. | 2.3 | Medium |
| 2.6 Test flow | `companion/lib/screens/setup_test_screen.dart` | Independent gateway/auth/device/source results using invented sample data; no real decision send. | 2.5 | Medium |
| 2.7 Tests | `companion/test/onboarding_test.dart` | Cover pin mismatch, expired auth, setup token, skipped steps and independent test results. | 2.1–2.6 | Low |

Tests: unit QR parser/trust/auth policy; integration real local TLS gateway with invented credentials; E2E Android emulator QR and manual flows, mismatch block, re-auth and partial setup. Gate: no network gateway without auth and TLS; no QR bypass or credential leakage. If platform credential support fails the prototype, stop and revise this phase before enabling onboarding.

## Phase 3 — compatible-device catalogue and diagnostics

Deliverable: selectable Raven/Halo cards with honest simulator/emulator status, requirements and diagnosis, plus extensible capability records. A live pair/“Ligado” action is feature-gated until physical-device evidence exists.

| Step (each ≤50 changed lines) | File | Action and why | Dependencies | Risk |
|---|---|---|---|---|
| 3.1 Capability registry | `companion/lib/devices/device_catalog.dart` | Model supported setup/diagnostic capabilities and validation level; never infer a universal connection. | Phase 2 | Medium |
| 3.2 Device setup | `companion/lib/screens/device_setup_screen.dart` | Guided Raven/Halo paths and “Adicionar depois”, with unavailable live controls explained. | 3.1 | Medium |
| 3.3 Health adapter | `companion/lib/devices/device_health.dart` | Use selected authenticated device ID and freshness only; distinguish absent telemetry from low battery. | 3.1, Phase 0 | High |
| 3.4 Diagnosis | `companion/lib/screens/diagnostics_screen.dart` | Contextual next steps for gateway, auth, selected glasses and sources. | 3.2–3.3 | Medium |
| 3.5 Tests | `companion/test/device_health_test.dart` | Prove phone polling cannot make glasses healthy, threshold edges, no invented battery/compatibility claims. | 3.3–3.4 | Low |

Tests: unit capability/health clock boundaries; integration paired-device heartbeat through authenticated gateway; E2E Android emulator device selection, no-hardware guidance, reconnect and diagnostics. Gate: labels reflect actual evidence; physical pairing remains off until repeatable Raven/Halo hardware tests and any required bridge exist.

## Phase 4 — foreground continuity, read-only first

Deliverable: when glasses are unpaired or verified absent, phone can inspect **only** complete/current pending requests; no sending yet. Healthy Home still has no queue, transient uncertainty exposes none.

| Step (each ≤50 changed lines) | File | Action and why | Dependencies | Risk |
|---|---|---|---|---|
| 4.1 Continuity reducer | `companion/lib/state/continuity_state.dart` | Gate entry on selected gateway, auth, snapshot integrity and device health/absence window. | Phases 1, 3 | High |
| 4.2 Detail reader | `companion/lib/gateway/task_detail_client.dart` | Fresh complete per-task read, revision/action validation and request ordering; no cached authority. | 4.1 | High |
| 4.3 Detail UI | `companion/lib/screens/decision_detail_screen.dart` | Full vertically scrollable title/source/detail/actions; visibly disable selection until data is verified. | 4.2 | Medium |
| 4.4 Tests | `companion/test/continuity_test.dart` | Cover no glasses, transient miss, sustained absence, gateway loss, stale/out-of-order/partial and reconnection. | 4.1–4.3 | Low |

Tests: unit state and detail parser; integration reordered/delayed fake-gateway responses; E2E Android emulator from unavailable glasses to full read-only detail and back to healthy. Gate: incomplete/old/out-of-order never appears empty or selectable; no send endpoint is called.

## Phase 5 — deliberate decision and safe recovery

Deliverable: separate selection/confirmation/send states, gateway-gated send, truthful accepted/refused/changed/unknown results, and review-before-retry using the same ID. Reconnection invalidates an open phone confirmation.

| Step (each ≤50 changed lines) | File | Action and why | Dependencies | Risk |
|---|---|---|---|---|
| 5.1 Pure decision FSM | `companion/lib/state/decision_flow.dart` | Encode Detail → Selection → Confirmation → Revalidating → Sending → outcome, with invalidation edges. | Phase 4 | High |
| 5.2 Stable ID mapping | `companion/lib/gateway/decision_client.dart` | Use gateway idempotency `request_id` as the same logical `decision_id` across unknown retries; no new ID for replay. | 5.1, Phase 0 | High |
| 5.3 Confirmation UI | `companion/lib/screens/decision_confirmation_screen.dart` | Separate explicit confirmation and disabled repeat taps; display action/task/environment. | 5.1 | Medium |
| 5.4 Result/review UI | `companion/lib/screens/decision_result_screen.dart` | “Tentar novamente” navigates to fresh full review, never sends; require re-selection and new confirmation. | 5.2–5.3 | High |
| 5.5 Race tests | `companion/test/decision_flow_test.dart` | Unknown/accepted/refused/changed, reconnect before send, reconnect in flight, resume, repeated tap, partial/late reads. | 5.1–5.4 | Low |
| 5.6 Gateway E2E | `tests/test_companion_decision_e2e.py` | Exercise atomic selected-device eligibility, glasses/phone race and same-ID dedup with invented tasks. | 5.2, Phase 0 | High |

Tests: unit every FSM transition; integration gateway acceptance/409/refusal/timeout/duplicate and reconnect race; E2E Android emulator inspect → select → confirm → send, then unknown → “Tentar novamente” → fresh review → reselect → confirm. Gate: no path from Uncertain or notification to Sending without deliberate review and confirmation; no phone send while selected glasses are healthy; acceptance copy never claims agent completion.

## Phase 6 — conditional background alerts and release validation

Deliverable: Android alerts only if reliable background verification of both selected-glasses absence and current gateway pending revision is demonstrated. Otherwise the notification feature stays hidden and foreground continuity remains usable. iOS is a separate later validation track, not implied by Android success.

| Step (each ≤50 changed lines) | File | Action and why | Dependencies | Risk |
|---|---|---|---|---|
| 6.1 Alert eligibility | `companion/lib/notifications/alert_policy.dart` | One alert per current decision revision after sustained selected-device absence; suppress stale/offline/answered cases. | Phases 3–5 | High |
| 6.2 Android adapter | `companion/android/app/src/main/kotlin/agenthud/companion/NotificationBridge.kt` | Implement OS-permitted background path only after feasibility proof; no secret/task title in payload. | 6.1 | High |
| 6.3 Notification UI | `companion/lib/notifications/notification_router.dart` | Include selected environment label; tap opens fresh detail, never confirmation/send. | 6.1–6.2 | Medium |
| 6.4 Accessibility tests | `companion/test/accessibility_test.dart` | Check semantics, labeled targets, target size and contrast in both themes on key states. | Phases 1–5 | Medium |
| 6.5 Release evidence | `docs/validation/companion-android.md` | Record actual narrow-device screenshots, 200% text, contrast, TalkBack, reduced motion, long strings, TLS/auth, notification and hardware results. | 6.1–6.4 | Medium |

Tests: unit alert dedup/eligibility and environment copy; integration background interruptions and tap revalidation; E2E Android physical/emulator lifecycle tests plus manual TalkBack, 200% text and screenshot review for continuity, confirmation, unknown, changed, incomplete and gateway error. Gate: no alert preference or delivery claim if background condition cannot be verified; no release claim without recorded accessibility and hardware evidence. Run full Python/Flutter suites, lint, publication hygiene, inspect tracked files for secrets/SDKs and check `git status`.

## Cross-phase acceptance checklist

- [ ] Android user can configure/diagnose selected gateway, phone auth, supported device and sources without T.I.O.; setup test reports each subsystem independently.
- [ ] Selected environment appears on every screen and notification; no automatic gateway selection or failover.
- [ ] Healthy glasses show no Home decision queue; partial setup is honest; transient uncertainty is not continuity.
- [ ] Incomplete, stale, malformed or out-of-order data never looks empty and never authorizes sending.
- [ ] Reconnection during phone confirmation invalidates it; a send already in flight waits for its true gateway outcome.
- [ ] “Tentar novamente” reviews fresh full detail, requires re-selection and separate confirmation, and preserves `decision_id`/gateway idempotency key.
- [ ] Acceptance means gateway receipt only; physical compatibility, notifications, iOS and accessibility are claimed only to the extent actually validated.

Implementation must not begin until this plan, particularly the proposed Flutter stack and gateway arbitration contract, is reviewed and explicitly approved.
