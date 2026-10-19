# Agent HUD companion app — UX design

Date: 2026-10-19
Status: proposed for user review; no implementation approved

## Product role

The companion app is an independent, public-facing Agent HUD product. It has no dependency on the private T.I.O. project. Its primary job is to configure and verify connections, explain failures, and help recover them. It is not a second agent dashboard or an agent execution host. Agent work belongs to the agent tools and gateway, not to the glasses or phone.

The one operational exception is continuity: when no glasses are paired or the selected glasses are unavailable, the phone may show and answer currently pending human decisions from the selected gateway. When the glasses are healthy, the Home screen does not show a decision queue.

This design targets Android first with an iOS-ready shared layout. It does not claim an installed mobile app, physical-glasses validation, background notification delivery, or a live Halo bridge. Raven is simulator-validated; Halo is emulator-validated. Device cards must show their actual validation status until physical end-to-end tests justify a stronger claim.

## Principles and boundaries

1. Quiet is verified, not inferred: a complete empty gateway response is different from unreachable, malformed, truncated, or stale data.
2. Selecting a decision action never sends it. Only a separate confirmation does.
3. “Enviado ao gateway” means gateway acceptance, not completion of the agent's later work.
4. The phone never chooses another gateway automatically. Every screen and notification identifies the selected environment.
5. Device availability is observed separately from its cause. A timeout says “Óculos indisponíveis”; “Sem bateria” requires actual device telemetry.
6. The app never invents an agent action or changes the action label supplied by the gateway.
7. No task text is retained as an offline copy on the phone. A disconnected screen may retain the last in-memory snapshot during that session, marked with its observation time, but cannot send from it.

## Visual direction and navigation

- Light theme: Warm Clarity (B), warm ivory surface, dark ink text, restrained coral action accent and teal connection accent.
- Dark theme: Quiet Signal (A), midnight/navy surfaces, light text and restrained cyan connection accent. Both themes use identical information hierarchy, text, icon shapes and interactions. Follow the OS theme by default; provide a manual override in settings.
- Green/teal means a connection was just verified; amber means partial, stale or attention needed; red is reserved for a failed connection or send. Every meaning also has an icon and explicit text.
- Minimum touch target: 48 by 48 logical pixels. Respect large text and reduced-motion settings. Long detail text scrolls within the page; fixed confirmation controls remain accessible.
- Bottom navigation: Estado, Ligações, Ajuda. Ligações contains Gateway, Óculos and Fontes; Ajuda opens the recovery guides for the selected environment and device. The earlier “Dispositivos” mockup label is superseded by “Ligações” because sources and gateway need equal access.
- No account avatar, chat composer, agent activity feed, or one-tap approval on the Home screen.

### State screen layout

On a narrow phone, use one vertical column: app title and selected environment; glasses status; gateway status; conditional pending-decision card; contextual diagnostic steps; bottom navigation. The pending-decision card exists only when glasses are absent/unavailable and the gateway has returned a complete, current list. On a tablet, keep the same reading order in a centered content column no wider than 600 logical pixels. Do not place status and decision panels side by side where one could be overlooked.

Normal Home copy: “Ligações prontas” / “Ver ligações”. There is no decision count or queue. The user can deliberately open Ligações to inspect devices and sources.

Partial-setup copy: “Configuração parcial” / “Óculos por adicionar” / “Adicionar óculos”. Gateway and source work may be complete without glasses; the app never calls the overall setup complete.

Continuity copy: “Óculos indisponíveis” / “Última ligação há {tempo}” / “Gateway ligado” / “{n} decisão pendente” or “{n} decisões pendentes” / “Rever pedido” / “Diagnóstico”. Battery steps say “Verificar bateria” and show a measured percentage only if the device exposes one; otherwise they explain how to check manually.

Gateway failure copy: “Gateway inacessível” / “Última sincronização: {hora}” / “Não é possível confirmar pedidos neste momento” / “Diagnosticar ligação”. A stale zero is never rendered as “0 pendentes”.

Incomplete-response copy: “Não foi possível confirmar todos os pedidos” / “Tentar novamente”. Previously known requests may be shown as last-known information with a timestamp; sending is disabled until a complete current read succeeds.

## Initial setup flow

The user-approved order is gateway, secure phone connection, glasses, sources, end-to-end test. The user may postpone glasses and finish gateway/source setup, leaving a visible partial state.

### 1. Connect gateway

Screen title: “Ligar gateway”. Instruction: “No computador, abra o gateway.” Primary action: “Ler QR”. Secondary action: “Introduzir endereço”. The QR is a proposed gateway setup surface containing only a gateway address and certificate fingerprint; it is not a login credential or an authorization to approve work. Manual entry leads to the same certificate check. The app must not suggest exposing a loopback-only gateway automatically. Network access requires gateway authentication and TLS, as in the current gateway policy.

No QR or discovery result: “Não foi possível encontrar o gateway” with actions “Introduzir endereço” and “Verificar computador e rede”. A malformed QR is rejected and explained, not treated as an empty setup.

### 2. Protect the phone connection

Screen title: “Proteger ligação”. Display the selected gateway identity and the observed certificate fingerprint. Instruction: “Confirme que a impressão digital coincide com a mostrada no computador.” Primary action: “Criar chave neste telemóvel” (or “Entrar com chave” for a registered phone). A mismatch blocks progress with “A identidade do gateway não coincide” and “Voltar”; there is no unsafe override. A gateway's first network registration may additionally require its one-time setup token shown locally on the computer. The QR never bypasses this gate. Re-pairing or revocation requires recent authentication.

### 3. Choose and set up glasses

Screen title: “Escolher óculos”. Each device card shows model, actual validation status, requirements and its own guided setup path. Current catalogue: Raven Prism (“Em validação — simulador”) and Brilliant Labs Halo (“Em validação — emulador”). Do not present either as physically tested. Primary action after selection: “Continuar”. Secondary action: “Adicionar depois”; this saves the gateway/source progress and leaves glasses incomplete. “Ver requisitos” opens the device-specific preparation and troubleshooting guide.

Raven guidance must account for its current one-time device token and gateway certificate trust, without pretending that the existing app can inject credentials into physical hardware. Halo guidance must not present emulator Bluetooth framing as a live gateway bridge. Any live pairing control stays unavailable until that device's end-to-end implementation and hardware validation exist. This is a release gate, not an optional warning that can be dismissed.

### 4. Configure sources

Screen title: “Ligar fontes”. Rows are “Codex”, “Claude Code” and “GitHub”, each with “Configurar” and a truthful capability/status label: “Ligado”, “Por configurar”, or “Falha na verificação”. The phone guides gateway-side setup and verifies the resulting source status; it does not read local agent files on the phone or silently install hooks on a computer. A source may be skipped with “Configurar depois”. GitHub's current feeder is a read-only review-request source; this screen must not imply that GitHub approvals can be sent through it.

### 5. Test and finish

Screen title: “Verificar configuração”. Primary action: “Fazer teste”. The test uses invented sample data and checks the gateway, phone authentication, selected device path if one exists, and configured source health independently. Results use “Pronto”, “Precisa de atenção”, or “Por configurar” per step; there is no blanket success if one step failed. An unpaired device remains “Óculos por adicionar”. Completion action: “Abrir Estado”. The app does not send a real decision during the test.

## Continuity and decision review

Entry condition: the selected glasses are not paired or have remained unavailable long enough to avoid a transient-disconnect alert, while the selected gateway is reachable. The phone displays the continuity layout. If the gateway is also unreachable, it shows recovery only: no current count, no decision submission, no claim that agents are still running.

Tap “Rever pedido” -> fetch its current task and revision -> show source, title, full detail, last update and exactly the gateway-offered actions -> select an action -> separate confirmation showing the action and task title -> “Confirmar envio” sends. “Cancelar” exits without sending. During the send, show “A enviar…” and disable repeated submission. If the revision changed, show “O pedido mudou. Leia-o novamente.” and return to detail. On acceptance, show “Enviado ao gateway”; on rejected action, show “O gateway recusou esta ação”; on unknown delivery, show “Não sabemos se o pedido chegou ao gateway”. Only the unknown-delivery case offers “Tentar novamente”, and it must reuse the same decision ID. Repeated taps while sending cannot create a second decision.

The phone never says “Aprovado”, “Concluído”, or “Implementado” solely because a send was accepted. A later verified task update can report later work. Device reconnection refreshes current gateway data before returning to normal Home; it does not replay or silently transfer any decision.

## Background alert policy

Default: one generic notification per pending decision revision only when a previously paired, selected pair of glasses has remained unavailable and the gateway has confirmed a current pending decision. A first-run partial setup with no paired glasses has foreground continuity but no background decision alerts. Proposed minimum absence window: 60 seconds, with at least two independent failed health observations. Text: “Agent HUD: uma decisão precisa de ti” (pluralized when appropriate). Tapping opens the current request detail after revalidation; it never opens confirmation or sends. No alert for a single transient disconnect, a stale list, an unreachable gateway, or a decision already answered on another device. Notification content contains no task title or private text.

If the Android background mechanism cannot reliably confirm both conditions, this alert is not presented as a guaranteed feature and its preference is not shown. Foreground recovery still works. iOS delivery is a later platform validation, not inferred from Android behavior.

## Failure, privacy and accessibility rules

- Missing gateway, certificate mismatch, expired sign-in, missing phone network permission, absent device, unsupported hardware, failed source, partial task list, stale revision and unknown send outcome each get a distinct explanation and next action.
- The app can show the last observed status with its timestamp, but cached text is never treated as current authority. A real empty current list alone can say “Sem decisões pendentes agora”.
- Setup progress may retain non-sensitive connection metadata. Secrets stay in platform-protected credential storage or the gateway; no credentials, raw agent state or task text are written to analytics or log files.
- All demo and test content is invented. No real user task appears in a screenshot, fixture or sample notification.
- All important status and action labels must remain legible at 200% text scale, with screen-reader labels and a non-colour indicator. Reduced motion removes decorative transitions without removing status changes.
- A user can switch gateway only through an explicit selection that names both environments; there is no automatic failover.

## Scope and validation gates

This spec fixes the experience, not current implementation status. A future implementation plan may split gateway setup surfaces, mobile UI, device adapters, notification delivery and hardware validation into separate increments. No production device card may say “Ligado” without a real, current handshake. No public claim of Raven or Halo physical compatibility precedes repeatable hardware testing. No background-alert claim precedes a working OS-permitted delivery path.

Before implementation, the state map in design/ai-states/agent-hud-companion.md is normative for gateway-derived decision information. Since the companion does not stream model tokens or generate AI responses, it must not fabricate a streaming animation or answer-confidence claim.

Acceptance for this design: a new user can connect or diagnose a gateway, defer glasses, understand exactly what remains incomplete, add available sources, run an honest test, and, only in continuity mode with a verified gateway, review and deliberately answer a pending decision. Normal mode remains a connection tool, not an agent dashboard.
