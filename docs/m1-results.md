# M1 — Raven platform boundary results

**Date:** 2026-09-20

**Branch:** `work/m1-platform-boundary`

**Implementation commit:** `6b624f4`

**Baseline:** M0 commit `5c6da46`

## Outcome

M1 passed. The Raven runtime moved from the repository root to
`platforms/raven/agent_hud/` without changing its public Python package name,
decision behavior, deploy surface, or rendered pixels.

The public Halo directory contains status metadata and documentation only. The
emulator implementation remains in its separate private repository; no Halo SDK,
vendor source, cache, binary, or private adapter was copied here.

## Verification evidence

| Gate | Result |
|---|---|
| Platform/deploy boundary tests | 7 passed |
| Full Raven suite | 881 passed, 2 skipped |
| Coverage | 90.98% (80% required) |
| Ruff | clean |
| Canonical Raven/Halo comparison | 22 identical cases; 8 normative files |
| Canonical vector SHA-256 | `90660a039ecc00cec7685234128e2d7976a8228c5b2518b902c2e92c73451f1d` |
| Raven visual regression | 4/4 PNGs byte-identical |
| Editable install/import | `agent_hud` resolves from `platforms/raven/agent_hud` |
| Wheel inspection | package, screens, assets, gateway and feeders included |
| Secret/vendor scan | no local paths, private keys, framework, vendor SDK, or private Halo runtime tracked |

The private Halo verifier ran against this Raven checkout and reported `PASS`.
This is emulator evidence, not physical-Halo validation.

## Visual evidence

The post-move captures are in [`docs/m0-screenshots/current/`](m0-screenshots/current/):

- [attention indicator](m0-screenshots/current/attention.png)
- [action menu](m0-screenshots/current/action-menu.png)
- [separate confirmation](m0-screenshots/current/confirmation.png)
- [sending acknowledgement](m0-screenshots/current/sending.png)

Their SHA-256 values exactly match the corresponding files under
`docs/m0-screenshots/baseline/`.

## Boundary now enforced

- Normative protocol: `core/`
- Raven runtime: `platforms/raven/agent_hud/`
- Raven deploy payload: `main.py` plus `platforms/raven/agent_hud/`
- Halo public surface: `platforms/halo/README.md` and `platform.json` only
- Halo runtime and Brilliant SDK: separate private repository

No push, merge, publication, hardware-validation claim, or repository-visibility
change was made.
