import assert from 'node:assert/strict';
import test from 'node:test';

import { createAgentHudAuditLog } from '../../phone/src/audit-log.js';

test('emits structured Agent HUD evidence with session and event data', () => {
  const entries = [];
  const audit = createAgentHudAuditLog({
    sessionId: 'mm:test-session',
    write: (...args) => entries.push(args),
  });

  audit('device.connection', { connected: false, pendingDiscarded: true });

  assert.deepEqual(entries, [[
    '[AgentHUD]',
    {
      event: 'device.connection',
      session_id: 'mm:test-session',
      connected: false,
      pendingDiscarded: true,
    },
  ]]);
});

test('does not allow event data to replace the canonical event or session', () => {
  const entries = [];
  const audit = createAgentHudAuditLog({
    sessionId: 'mm:canonical',
    write: (...args) => entries.push(args),
  });

  audit('runtime.lifecycle', {
    event: 'spoofed',
    session_id: 'mm:spoofed',
    state: 'stopped',
  });

  assert.equal(entries[0][1].event, 'runtime.lifecycle');
  assert.equal(entries[0][1].session_id, 'mm:canonical');
  assert.equal(entries[0][1].state, 'stopped');
});

test('records the same structured entry for an inspectable in-plugin log', () => {
  const recorded = [];
  const audit = createAgentHudAuditLog({
    sessionId: 'mm:visible-log',
    write: () => {},
    record: (entry) => recorded.push(entry),
  });

  audit('runtime.initialize.completed', { connected: true });

  assert.deepEqual(recorded, [{
    event: 'runtime.initialize.completed',
    session_id: 'mm:visible-log',
    connected: true,
  }]);
});
