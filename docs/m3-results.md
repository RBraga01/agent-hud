# M3 — Halo integration results

**Date:** 2026-09-23

**Branch:** `work/m3-halo-integration`

**Raven baseline:** M1 commit `a3b01d6`

**Halo clean-export source:** private adapter commit `224d27f`

## Outcome

Halo is now a first-class platform under `platforms/halo/`. The import contains
the current MIT-licensed Lua runtime, emulator host framing, tests and reviewed
framebuffers. It does not contain the private Git history, a second copy of the
common contract, the Brilliant SDK, caches, binaries or machine-local paths.

The repository landing page now describes the multi-platform product. Raven and
Halo each have a complete platform guide. Raven's existing runtime, package name,
deploy surface, intended behaviour and simulator visuals are preserved, with the
two deliberate safety corrections recorded in `docs/m0-baseline.md`.

## Verification evidence

| Gate | Result |
|---|---|
| Root suite, local with Raven Framework available | 886 passed, 2 skipped |
| Root suite, public CI without the proprietary framework | 765 passed, 5 skipped on Python 3.10 and 3.12 |
| Root coverage | 90.98% local; 90.66% on Python 3.10 CI; 90.74% on Python 3.12 CI (80% required) |
| Shared Raven/gateway contract suite | 63 passed |
| Ruff | Clean |
| Halo integrated suite | 49 passed |
| Official Halo emulator suite | 51 passed |
| M0 conformance cases through Halo Lua | 23 passed |
| Reviewed Halo framebuffers | 9/9 byte-identical after regeneration |
| Local README links | All resolved |
| Raven deploy boundary | `main.py` plus `platforms/raven/agent_hud/` only |
| Halo dependency boundary | Pinned SDK ignored and absent from tracked files |

The local and public-CI counts differ because public automation deliberately does
not install the proprietary Raven Framework. Halo evidence uses
`halo-emulator 2.0.1` and Brilliant SDK commit
`f582b88bee798121c51bc483c2b0b4a85dd5e411`. It is emulator evidence, not
physical-Halo validation.

## Integrated boundary

- Common contract: `core/`
- Shared gateway and agent readers: `stub_server/` and `feeders/`
- Raven runtime: `platforms/raven/agent_hud/`
- Halo runtime: `platforms/halo/app/`
- Halo emulator environment and tests: `platforms/halo/pyproject.toml` and
  `platforms/halo/tests/`
- Reviewed Halo evidence: `platforms/halo/docs/images/`

## Remaining work

Physical Halo readability, button/tap ergonomics, real Bluetooth behaviour and
the live Halo-to-gateway bridge are not implemented or claimed. They remain
separate milestones because the public emulator cannot prove them.
