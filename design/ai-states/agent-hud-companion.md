# Agent HUD companion — gateway-derived decision states

This is a user-facing agent-information touchpoint, but it does not call a model or stream generated tokens. The gateway supplies snapshots of tasks. The seven AI-output categories are accounted for below; “streaming” is intentionally absent rather than simulated. Any later live generated-output UI needs a separate state design.

| State | Visual and exact pt-PT copy | Action | Transition |
|---|---|---|---|
| Loading | Small progress indicator beside the last known status: “A verificar pedidos…”; no empty-state claim. | “Cancelar” stops the foreground refresh and retains the timestamped previous state. | Complete current list -> Success or Empty; incomplete list -> Partial; timeout -> Error. |
| Streaming | Not presented: the gateway has no token stream and this app has no generated-answer surface. No cursor, token animation or “a escrever” copy is allowed. | None. | Loading goes directly to Success, Empty, Partial or Error. |
| Success | Verified current decision count: “1 decisão pendente” or “{n} decisões pendentes”; in continuity mode only, show “Rever pedido”. | “Rever pedido” opens a fresh detail read. | New gateway snapshot -> Success, Empty or Partial; connection loss -> Error with last-known timestamp. |
| Error | Red failure icon and “Gateway inacessível” / “Não é possível confirmar pedidos neste momento”; preserve last-known timestamp. | “Diagnosticar ligação” and “Tentar novamente”. | Retry -> Loading; verified response -> Success, Empty or Partial. |
| Partial | Amber incomplete marker and “Não foi possível confirmar todos os pedidos”; known rows may remain visibly last-known, but sending is disabled. | “Tentar novamente”. | Complete refresh -> Success or Empty; further failure -> Error/Partial. |
| Uncertain | Amber delivery-unknown panel after send: “Não sabemos se o pedido chegou ao gateway”. Never claim failure or success. | “Tentar novamente” with the same decision ID, or “Voltar”. | Accepted retry -> “Enviado ao gateway”; stale/refused -> explicit result; renewed uncertainty -> stay Uncertain. |
| Empty | Calm verified state “Sem decisões pendentes agora”; only after a complete current gateway list. In normal mode, Home still shows connection health rather than a decision feed. | “Ver ligações”. | New pending request -> Success; loss/partial read -> Error/Partial, never remain silently Empty. |

## Edge cases

- A zero-length or non-list gateway body is Error, not Empty.
- A malformed or truncated list is Partial, even if zero valid requests remain.
- Long detail text scrolls; cut-off text is visibly marked and cannot be approved without opening the full current detail.
- Multiple simultaneous refreshes do not reorder a newer observation behind an older one.
- A second tap during a send is ignored; an unknown-delivery retry uses the original decision ID.
- If the task revision changes during review or confirmation, the old confirmation is discarded and the user reads the new version.
- If the app is backgrounded mid-review, returning requires current gateway revalidation before confirmation.
