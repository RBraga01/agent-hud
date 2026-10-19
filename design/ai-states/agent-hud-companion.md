# Agent HUD companion — gateway-derived decision states

This is a user-facing agent-information touchpoint, but it does not call a model or stream generated tokens. The gateway supplies snapshots of tasks. The seven AI-output categories are accounted for below; “streaming” is intentionally absent rather than simulated. Any later live generated-output UI needs a separate state design.

| State | Visual and exact pt-PT copy | Action | Transition |
|---|---|---|---|
| Loading | Small progress indicator beside the last known status: “A verificar pedidos…”; no empty-state claim or send control. | “Cancelar” stops the foreground refresh and retains the timestamped previous state. | Complete current list -> Success or Empty; incomplete list -> Partial; timeout -> Error. |
| Streaming | Not presented: the gateway has no token stream and this app has no generated-answer surface. No cursor, token animation or “a escrever” copy is allowed. | None. | Loading goes directly to Success, Empty, Partial or Error. |
| Success | Verified complete, current decision count: “1 decisão pendente” or “{n} decisões pendentes”; in continuity mode only, show “Rever pedido”. | “Rever pedido” opens a fresh detail read; sending remains unavailable until detail review and separate confirmation. | New gateway snapshot -> Success, Empty or Partial; connection loss -> Error with last-known timestamp. |
| Error | Red failure icon and “Gateway inacessível” / “Não é possível confirmar pedidos neste momento”; preserve last-known timestamp and disable sending. | “Diagnosticar ligação” and “Atualizar estado” (data fetch only). | Refresh -> Loading; verified response -> Success, Empty or Partial. |
| Partial | Amber incomplete marker and “Não foi possível confirmar todos os pedidos”; stale/out-of-order variant “Informação por confirmar”. Known rows may remain visibly last-known, but sending is disabled. | “Atualizar estado” (data fetch only). | Complete, current refresh -> Success or Empty; further failure -> Error/Partial. |
| Uncertain | Amber delivery-unknown panel after send: “Não sabemos se o pedido chegou ao gateway”. Never claim failure or success. Explain “Antes de reenviar, reveja o pedido e confirme a ação.” | “Tentar novamente” opens review only; “Voltar” exits. Review starts a fresh complete read, shows the full request and previous action, and requires deliberate re-selection plus separate “Confirmar nova tentativa”. There is no direct resend. | Same task/revision/content/action, verified current -> review -> confirmation -> resend original `decision_id`; changed/absent/partial/stale/out-of-order -> block old retry; renewed uncertainty -> stay Uncertain. |
| Empty | Calm verified state “Sem decisões pendentes agora”; only after a complete, current, in-order gateway list. In normal mode, Home still shows connection health rather than a decision feed. | “Ver ligações”. | New pending request -> Success; loss/partial/stale read -> Error/Partial, never remain silently Empty. |

## Edge cases

- A zero-length or non-list gateway body is Error, not Empty.
- A malformed, truncated, old or out-of-order list is Partial, even if zero valid requests remain; it disables decision sending.
- Long detail text scrolls; cut-off text is visibly marked and cannot be approved without opening the full current detail.
- Multiple simultaneous refreshes do not reorder a newer observation behind an older one. The app discards a late response to an earlier request and rejects a lower gateway snapshot version or task revision.
- A second tap during a send is ignored. After unknown delivery, the user must freshly review the unchanged task and explicitly confirm a new attempt; only then may it use the original decision ID.
- Final confirmation triggers another complete, in-order read from the selected gateway before any send; failed revalidation leaves the decision unsent and returns to review.
- If the task revision changes during review or confirmation, the old confirmation is discarded and the user reads the new version.
- If the app is backgrounded mid-review, returning requires current gateway revalidation before confirmation.

## Primary Home-state precedence

Configuration, authenticated gateway reachability, snapshot integrity and selected-glasses health are independent inputs. Render the first applicable primary state below. A higher-priority warning invalidates any lower-priority decision action; a fresh observation, never a cached zero, is required to recover.

| Priority | State and entry evidence | Exit or next state | Decision availability |
|---|---|---|---|
| 1 | Setup blocked: no selected/trusted gateway or valid phone credential. | Explicitly select/trust and authenticate; fetch a new snapshot before evaluating the rest. | None. |
| 2 | Gateway unavailable: selected gateway cannot provide an authenticated current response. | Diagnose, then fresh authenticated complete/in-order snapshot and selected-device health check; recompute. | None; last observation is timestamped, not called empty. |
| 3 | Information unverified: gateway responds, but snapshot is incomplete, malformed, stale, out of order, or missing required version/completeness evidence. | “Atualizar estado” performs a fresh data read; verified snapshot allows recomputation. | None; neither zero nor known rows authorize sending. |
| 4 | Partial setup: no selected glasses have been paired, though gateway and phone connection are verified. | Pair and independently verify selected glasses, or remain in foreground-only continuity. | Verified current pending requests may be reviewed in foreground; no background alert. |
| 5 | Connection temporarily uncertain: selected paired glasses miss a health observation, but sustained absence is unproven. | Fresh device proof -> Healthy; at least 60 seconds plus two independent failed observations -> Continuity; gateway/snapshot failure -> higher-priority state. | No phone decision queue or send. |
| 6 | Continuity: selected paired glasses are absent for the sustained interval; gateway and task snapshot are current/complete. | Fresh device proof -> Healthy after gateway refresh; gateway/snapshot failure -> higher-priority state. | Verified current requests may be reviewed on phone, subject to final gateway arbitration. |
| 7 | Healthy: selected paired glasses and gateway are currently verified. | Missed device observation -> Temporarily uncertain; gateway/snapshot failure -> higher-priority state. | Home has no decision queue/count. |

Skipped sources remain checklist items and do not mask a paired device's connection state. A phone poll or generic gateway `device_last_seen` is not proof that the selected glasses are present; health must be tied to the authenticated selected device. Environment switching clears version comparisons, open decisions and alert eligibility and requires explicit selection. Recovery from an uncertain connection to continuity restarts the full absence threshold; recovery from any higher-priority warning requires current evidence. An incomplete/old/out-of-order response is never interpreted as an empty list.

## Decision state machine

This machine applies only when foreground continuity is eligible. Each forward edge uses the selected gateway identity and the same current task; a state change never silently submits or transfers an action.

| State | Entry and UI | Allowed transition and guard |
|---|---|---|
| Detail loading | “A verificar pedido…”; no action buttons. | Complete current, in-order detail with task revision and offered actions -> Detail; failure -> Partial/Error without send. |
| Detail | Show full current source, title, detail, revision/updated time and exact offered actions. | User explicitly chooses an offered action -> Selection. Changed/absent task -> Changed request. |
| Selection | Highlight choice but do not send; “Continuar” and “Cancelar”. | “Continuar” -> Confirmation; cancel -> Detail. New task revision or lost continuity -> invalidate choice. |
| Confirmation | Show task and chosen action separately; “Confirmar envio” and “Cancelar”. | “Confirmar envio” -> Revalidating. Cancel -> Detail without send. Background/resume, environment switch, glasses reconnection or higher-priority Home state closes confirmation without sending. |
| Revalidating | “A verificar e enviar…”; repeated taps disabled. | Fresh authenticated complete/in-order snapshot verifies same gateway, task ID, revision, content, action and continuity eligibility -> Sending. Any mismatch -> Changed request or information warning, without send. |
| Sending | One `decision_id` sent to gateway; repeated taps disabled. | Atomic gateway eligibility/revision/ID check -> Accepted or Refused; network outcome unknown -> Uncertain. A glasses reconnection now does not cancel or replay the in-flight request; wait for outcome. |
| Accepted | “Enviado ao gateway”; not agent completion. | Refresh current status; no implicit next action. |
| Refused | “O gateway recusou esta ação”; reason if safely available. | Refresh detail, diagnose or exit; no automatic resend. |
| Changed request | “O pedido mudou. Leia-o novamente.” The old action and confirmation are invalid. | Fresh complete detail -> Detail for a new deliberate choice; never retry the old decision. |
| Uncertain | “Não sabemos se o pedido chegou ao gateway”. | “Tentar novamente” -> Detail loading, never Sending. Same current task/revision/content/offered action permits deliberate re-selection -> separate “Confirmar nova tentativa” -> Revalidating -> Sending with the **original** `decision_id`. Otherwise block old retry. |

Final confirmation requires another current read, and the gateway makes the final atomic eligibility/revision decision to close the race with a glasses response. A selected-glasses reconnection during Detail, Selection or Confirmation invalidates the phone flow and shows “Óculos novamente ligados. Reveja o pedido nos óculos.”; a complete current gateway refresh precedes Healthy Home. If reconnection is observed after Sending begins, show the actual acceptance/refusal/unknown outcome first. Healthy glasses never grant the phone a retry shortcut. No notification tap, refresh, resume or repeated tap triggers Sending.
