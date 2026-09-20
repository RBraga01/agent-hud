# Platform boundaries

The normative Agent HUD decision contract lives under `core/`. A platform owns
its runtime, rendering, input mapping and transport binding. Passing the common
vectors proves decision-contract conformance; it does not imply shared runtime
code or physical-hardware validation.

| Platform | Implementation | Validation |
|---|---|---|
| Raven Prism | Implemented in `platforms/raven/agent_hud/` | Simulator validated |
| Brilliant Labs Halo | Private prototype; no source in this repository | Emulator validated |
| MemoMind One | Research | Not validated |

Validation labels progress independently: research, simulator/emulator
validated, hardware validated.
