# M0 — Cross-platform decision contract: verified

Date: 2026-09-20. Work is on local branch `work/m0-decision-contract`; no push,
merge, repository visibility change or platform directory migration was made.

## Gate evidence

The same **22 language-neutral vectors** produce exactly the same canonical
decisions, transport attempts and correlated results in Raven Python and the
independently implemented private Halo Lua runtime. IDs are deterministic only
in the tests. All eight normative files are byte-identical and pinned by hash.

- Contract source commit: `4f0e2eeb9ba3d574942790b92df212c421e28dd0` (local).
- Contract version: `1.0.0`, M0 offered-action profile.
- Decision vector SHA-256:
  `90660a039ecc00cec7685234128e2d7976a8228c5b2518b902c2e92c73451f1d`.
- Raven evidence: `m0-conformance-raven.json`.
- Halo evidence is stored only in the private project.

| Verification | Result |
|---|---|
| Raven pre-change baseline | 814 passed, 2 skipped; 91.07% coverage |
| Raven after M0 | 878 passed, 2 skipped; 90.98% coverage |
| Raven lint | All checks passed |
| Actual Raven Qt app | All 22 normative vectors passed |
| Gateway conformance | 9 cases passed |
| JSON Schemas | 8 tests passed |
| Halo emulator | 49 passed, including all 23 original tests |
| Cross-runtime comparison | PASS: 22 identical cases, 8 identical normative files |
| Raven visual comparison | Four PNGs byte-identical to baseline, clock fixed |

After isolating the capture's activation preference, the 100 activation/app/
visual tests also passed together. Both clock and double-blink preference are
fixed in the capture fixture, so earlier preference tests cannot contaminate it.

The full Raven run used `pytest -q --cov --cov-report=term
--cov-report=json:docs/m0-raven-coverage.json`. Coverage measures the existing
framework-free surface; it does not claim a Lua coverage percentage. The two
new Python adapters each measured 88% statement coverage.

## What was proved

Focus and selection do not send. Confirmation emits once. Cancel, unknown action
and stale selection do not send. Secondary actions retain their identity. Retry
reuses the frozen decision ID/content. Mismatched ACKs are ignored. DUPLICATE
preserves its original outcome. ACCEPTED is a receipt, never task completion.
Updates after sending do not erase the in-flight decision. Gateway checks cover
stale versions, invalid actions, conflicting ID reuse and duplicate receipt.

Tests invoke production navigation, confirmation and serialization. The Qt tests
exercise actual app callbacks with the network replaced at the send boundary.
Halo vectors execute the Lua app in the emulator and capture outbound BLE;
separate tests exercise single/double/long button and tap inputs. This is not
two test-only state machines agreeing with each other.

## Behavior preservation and discovered defects

The baseline tag is `baseline/raven-pre-m0-2026-09-20`; details and existing
image/GIF hashes are in `m0-baseline.md`. Four newly captured UI states compare
identically under `m0-screenshots/baseline/` and `m0-screenshots/current/`.

Two abnormal Raven paths were intentionally corrected: duplicate direct confirm
callbacks could allocate a second decision, and a lower task revision could
replace a newer observation. Normal visuals, navigation and legacy HTTP payloads
remain. Therefore the gate passes for the intended user behavior, with these
explicit safety corrections rather than an absolute no-behavior-change claim.

## Scope and limits

- `core/` contains schemas, vectors and documentation, no shared runtime library.
- Raven still uses legacy HTTP `request_id`, projected to canonical `decision_id`.
- `CanonicalGateway` is a local compatibility API, not a new public endpoint. It
  namespaces its internal Policy cache IDs with `canonical:`; retries must use
  the same adapter instance/binding. Existing HTTP authentication/TLS is unchanged.
- Gateway idempotency is bounded/in-memory, not durable exactly-once execution.
- M0 handles one or two offered actions. Audio and optional payload extensions
  have not been certified; unsupported payload is rejected instead of discarded.
- Halo protocol binding, host framing, Lua source and screenshots remain private.
- Neither implementation gains a hardware-validation badge from this milestone.
- The proprietary Raven Framework and the Brilliant SDK were not committed.

## Reproduce and next gate

```powershell
.venv/Scripts/python.exe -m pytest -q --cov --cov-report=term
.venv/Scripts/python.exe -m ruff check .
```

For the private comparison, run the private Halo suite and its
`tools/verify_m0.py --raven <local-agent-hud-checkout>` against fresh evidence.
The copied core is pinned to the commit above; a hash mismatch fails validation.

The next migration step can reorganize Raven into a platform boundary while
preserving these tests and deployment packaging. Publishing/importing the Halo
adapter remains a separate decision with a source/license/history review.
