import { createGMPlugin } from '../vendor/gm-plugin-web-sdk.esm.js';

import { createAgentHudAuditLog } from './audit-log.js';
import { REQUEST_CHANNEL, encodeRequest, encodeResult } from './protocol.js';
import { createSessionId } from './round-trip.js';
import { createTestScenarioController } from './test-scenarios.js';

const SESSION_ID = createSessionId();
const audit = createAgentHudAuditLog({
  sessionId: SESSION_ID,
  write: (...args) => console.info(...args),
  record: appendEventLog,
});

const gm = createGMPlugin();
const connectedButtons = [...document.querySelectorAll('[data-connected]')];
const cancelButton = document.querySelector('#send-cancel');
const verifyCancelButton = document.querySelector('#verify-cancel');
const staleButton = document.querySelector('#send-stale');
const supersedeButton = document.querySelector('#supersede-stale');
const duplicateButton = document.querySelector('#send-duplicate');
const status = document.querySelector('#status');
const evidence = document.querySelector('#evidence');
const eventLog = document.querySelector('#event-log');
let connected = false;
let activeMode = null;
let unsubscribeMessage;
let unsubscribeConnection;
let unsubscribeLifecycle;
let subscriptionId;

function appendEventLog(entry) {
  const lines = eventLog.textContent === 'No events yet.'
    ? []
    : eventLog.textContent.split('\n');
  lines.push(JSON.stringify(entry));
  eventLog.textContent = lines.slice(-30).join('\n');
}

function show(message, state = '') {
  status.textContent = message;
  status.dataset.state = state;
}

function refreshControls() {
  for (const button of connectedButtons) button.disabled = !connected;
  verifyCancelButton.disabled = !connected || activeMode !== 'cancel';
  supersedeButton.disabled = !connected || activeMode !== 'stale';
}

function resetForInterruption(message) {
  audit('scenario.reset', { reason: message, pendingDiscarded: activeMode !== null });
  activeMode = null;
  scenarios.reset();
  refreshControls();
  evidence.textContent = 'Pending test discarded. Start a fresh scenario.';
  show(message, 'error');
}

async function sendOutcome(
  decision,
  resultStatus,
  { originalStatus = null, reason = '' } = {},
) {
  audit('result.send.started', {
    decision_id: decision.decision_id,
    task_id: decision.task_id,
    revision: decision.revision,
    status: resultStatus,
    original_status: originalStatus,
    reason,
  });
  try {
    await gm.plugin.sendMessage(REQUEST_CHANNEL, encodeResult({
      decision_id: decision.decision_id,
      task_id: decision.task_id,
      revision: decision.revision,
      status: resultStatus,
      original_status: originalStatus,
      reason,
    }));
    evidence.textContent = JSON.stringify({ decision, resultStatus, originalStatus, reason }, null, 2);
    if (activeMode === 'cancel') {
      show('FAIL — cancel test emitted a decision', 'error');
    } else if (resultStatus === 'ERROR' && reason === 'simulated_ack_loss_after_accept') {
      show('Ambiguous result injected — double tap to review, then double tap to retry');
    } else {
      show(`${resultStatus} — correlated result returned to glasses`,
        resultStatus === 'ACCEPTED' || originalStatus === 'ACCEPTED' ? 'pass' : 'error');
    }
    audit('result.send.completed', {
      decision_id: decision.decision_id,
      task_id: decision.task_id,
      revision: decision.revision,
      status: resultStatus,
    });
  } catch (error) {
    audit('result.send.failed', {
      decision_id: decision.decision_id,
      task_id: decision.task_id,
      revision: decision.revision,
      error: error.message,
    });
    show(`Decision received; result failed: ${error.message}`, 'error');
  } finally {
    refreshControls();
  }
}

const scenarios = createTestScenarioController({
  onResult(decision, resultStatus, options) {
    audit('decision.received', {
      decision_id: decision.decision_id,
      task_id: decision.task_id,
      revision: decision.revision,
      action_id: decision.action_id,
      classified_as: resultStatus,
    });
    void sendOutcome(decision, resultStatus, options);
  },
  onRejected(reason) {
    audit('decision.rejected', { reason });
    evidence.textContent = `Ignored: ${reason}`;
  },
});

async function deliver(task, message) {
  if (!connected) {
    audit('request.send.skipped', {
      task_id: task.task_id,
      revision: task.revision,
      reason: 'device-disconnected',
    });
    return;
  }
  evidence.textContent = JSON.stringify({ ...task, session_id: SESSION_ID }, null, 2);
  show('Sending canonical task to glasses…');
  audit('request.send.started', {
    task_id: task.task_id,
    revision: task.revision,
    mode: activeMode,
  });
  try {
    await gm.plugin.sendMessage(
      REQUEST_CHANNEL,
      encodeRequest({ ...task, session_id: SESSION_ID }),
    );
    audit('request.send.completed', {
      task_id: task.task_id,
      revision: task.revision,
      mode: activeMode,
    });
    show(message);
  } catch (error) {
    audit('request.send.failed', {
      task_id: task.task_id,
      revision: task.revision,
      mode: activeMode,
      error: error.message,
    });
    show(`Transport failed: ${error.message}`, 'error');
  } finally {
    refreshControls();
  }
}

function begin(mode, message) {
  activeMode = mode;
  audit('scenario.started', { mode });
  refreshControls();
  void deliver(scenarios.begin(mode), message);
}

async function supersedeStale() {
  if (activeMode !== 'stale') return;
  audit('scenario.superseded', { mode: activeMode });
  await deliver(
    scenarios.supersede(),
    'Revision 4 delivered — HUD must show Stale and no decision may be emitted',
  );
}

function verifyCancel() {
  const result = scenarios.verifyCancel();
  audit('scenario.cancel.verified', result);
  evidence.textContent = JSON.stringify(result, null, 2);
  show(
    result.passed
      ? 'PASS — cancel emitted no decision'
      : `FAIL — ${result.decisionsReceived} decision(s) crossed the bridge`,
    result.passed ? 'pass' : 'error',
  );
}

async function initialize() {
  audit('runtime.initialize.started');
  refreshControls();
  try {
    await gm.ready();
    unsubscribeMessage = gm.plugin.onMessage((message) => {
      audit('transport.message.received', {
        channel: message.channel,
        bytes: message.data?.byteLength ?? message.data?.length ?? null,
      });
      scenarios.receive(message);
    });
    unsubscribeConnection = gm.device.onConnection((event) => {
      connected = event.connected === true;
      audit('device.connection', {
        connected,
        pendingDiscarded: !connected && activeMode !== null,
      });
      if (connected) {
        refreshControls();
        show('Connected — start a fresh Agent HUD test');
      } else {
        resetForInterruption('Glasses disconnected — pending test discarded');
      }
    });
    unsubscribeLifecycle = gm.on('runtime.lifecycleChanged', (event) => {
      audit('runtime.lifecycle', {
        state: event.state,
        pendingDiscarded: event.state !== 'running' && activeMode !== null,
      });
      if (event.state !== 'running') {
        resetForInterruption(
          `Phone lifecycle ${event.state} — pending test discarded`,
        );
      } else {
        refreshControls();
        show('Phone lifecycle running — start a fresh Agent HUD test');
      }
    });
    subscriptionId = (await gm.device.subscribeEvents(['connection'])).subscriptionId;
    const info = await gm.device.getInfo();
    connected = info.connected === true;
    audit('runtime.initialize.completed', { connected });
    refreshControls();
    show(connected ? 'Ready for canonical Agent HUD test' : 'Waiting for glasses');
  } catch (error) {
    audit('runtime.initialize.failed', { error: error.message });
    show(`Bridge unavailable: ${error.message}`, 'error');
  }
}

cancelButton.addEventListener('click', () => begin(
  'cancel',
  'Cancel test — single tap, double tap, double tap, then Back',
));
verifyCancelButton.addEventListener('click', verifyCancel);
staleButton.addEventListener('click', () => begin(
  'stale',
  'Stale test — reach confirmation, then supersede from the phone',
));
supersedeButton.addEventListener('click', () => void supersedeStale());
duplicateButton.addEventListener('click', () => begin(
  'duplicate',
  'Duplicate test — single tap, then three deliberate double taps',
));
window.addEventListener('pagehide', () => {
  audit('runtime.pagehide', { pendingDiscarded: activeMode !== null });
  scenarios.reset();
  unsubscribeMessage?.();
  unsubscribeConnection?.();
  unsubscribeLifecycle?.();
  if (subscriptionId !== undefined) {
    void gm.device.unsubscribeEvents(subscriptionId).catch(() => undefined);
  }
});

void initialize();
