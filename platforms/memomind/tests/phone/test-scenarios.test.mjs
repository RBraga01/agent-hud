import assert from 'node:assert/strict';
import test from 'node:test';

import { RESPONSE_CHANNEL, encodeDecision } from '../../phone/src/protocol.js';
import { createTestScenarioController } from '../../phone/src/test-scenarios.js';

function decision(task, overrides = {}) {
  return {
    channel: RESPONSE_CHANNEL,
    data: encodeDecision({
      decision_id: 'manual-session:1',
      task_id: task.task_id,
      revision: task.revision,
      action_id: task.actions[0].action_id,
      ...overrides,
    }),
  };
}

test('cancel scenario passes only while no decision has crossed the bridge', () => {
  const results = [];
  const scenarios = createTestScenarioController({
    onResult: (...args) => results.push(args),
  });
  const task = scenarios.begin('cancel');

  assert.deepEqual(scenarios.verifyCancel(), { passed: true, decisionsReceived: 0 });
  scenarios.receive(decision(task));
  assert.deepEqual(scenarios.verifyCancel(), { passed: false, decisionsReceived: 1 });
  assert.equal(results[0][1], 'ACCEPTED');
});

test('stale scenario supersedes revision 3 and rejects its late decision', () => {
  const results = [];
  const scenarios = createTestScenarioController({
    onResult: (...args) => results.push(args),
  });
  const original = scenarios.begin('stale');
  const updated = scenarios.supersede();

  assert.equal(original.revision, 3);
  assert.equal(updated.revision, 4);
  scenarios.receive(decision(original));
  assert.equal(results[0][1], 'STALE');
});

test('duplicate scenario models an ambiguous first result then acknowledges replay', () => {
  const results = [];
  const scenarios = createTestScenarioController({
    onResult: (...args) => results.push(args),
  });
  const task = scenarios.begin('duplicate');
  const message = decision(task);

  scenarios.receive(message);
  scenarios.receive(message);

  assert.deepEqual(
    results.map(([, status, options]) => [status, options]),
    [
      ['ERROR', { reason: 'simulated_ack_loss_after_accept' }],
      ['DUPLICATE', { originalStatus: 'ACCEPTED' }],
    ],
  );
});

test('lifecycle reset disarms the previous request and ignores its late decision', () => {
  const results = [];
  const rejected = [];
  const scenarios = createTestScenarioController({
    onResult: (...args) => results.push(args),
    onRejected: (reason) => rejected.push(reason),
  });
  const task = scenarios.begin('duplicate');

  scenarios.reset();

  assert.equal(scenarios.receive(decision(task)), false);
  assert.deepEqual(results, []);
  assert.deepEqual(rejected, ['unrelated-decision']);
});
