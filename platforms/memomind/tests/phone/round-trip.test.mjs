import assert from 'node:assert/strict';
import test from 'node:test';

import { RESPONSE_CHANNEL, encodeDecision } from '../../phone/src/protocol.js';
import { createRoundTripController, createSessionId } from '../../phone/src/round-trip.js';

const TASK = {
  task_id: 'task-42',
  revision: 3,
  actions: [
    { action_id: 'approve', label: 'Approve' },
    { action_id: 'inspect', label: 'Inspect' },
  ],
};

function message(overrides = {}) {
  return {
    channel: RESPONSE_CHANNEL,
    data: encodeDecision({
      decision_id: 'session-a:1',
      task_id: TASK.task_id,
      revision: TASK.revision,
      action_id: 'inspect',
      ...overrides,
    }),
  };
}

test('creates a fresh canonical session identifier', () => {
  const values = [
    '11111111-1111-4111-8111-111111111111',
    '22222222-2222-4222-8222-222222222222',
  ];
  assert.equal(
    createSessionId(() => values.shift()),
    'mm:11111111-1111-4111-8111-111111111111',
  );
  assert.equal(
    createSessionId(() => values.shift()),
    'mm:22222222-2222-4222-8222-222222222222',
  );
});

test('accepts either offered action exactly once', () => {
  const accepted = [];
  const duplicates = [];
  const rejected = [];
  const controller = createRoundTripController({
    onAccepted: (decision) => accepted.push(decision),
    onDuplicate: (decision, originalStatus) => duplicates.push([decision, originalStatus]),
    onRejected: (reason) => rejected.push(reason),
  });
  controller.arm(TASK);

  assert.equal(controller.receive(message()), true);
  assert.equal(controller.receive(message()), true);
  assert.equal(accepted.length, 1);
  assert.equal(duplicates.length, 1);
  assert.equal(duplicates[0][1], 'ACCEPTED');
  assert.deepEqual(rejected, []);
});

test('classifies stale, invalid-action and id-conflict decisions', () => {
  const outcomes = [];
  const rejected = [];
  const controller = createRoundTripController({
    onStale: (decision) => outcomes.push(['STALE', decision]),
    onInvalidAction: (decision) => outcomes.push(['INVALID_ACTION', decision]),
    onConflict: (decision) => outcomes.push(['ERROR', decision]),
    onRejected: (reason) => rejected.push(reason),
  });
  controller.arm(TASK);

  assert.equal(controller.receive(message({ decision_id: 'stale', revision: 2 })), true);
  assert.equal(
    controller.receive(message({ decision_id: 'invalid', action_id: 'invented' })),
    true,
  );
  assert.equal(controller.receive(message({ decision_id: 'shared' })), true);
  assert.equal(
    controller.receive(message({ decision_id: 'shared', action_id: 'approve' })),
    true,
  );
  assert.deepEqual(outcomes.map(([status]) => status), [
    'STALE', 'INVALID_ACTION', 'ERROR',
  ]);
  assert.deepEqual(rejected, []);
});

test('ignores unrelated and late decisions after disarm', () => {
  const rejected = [];
  const controller = createRoundTripController({
    onRejected: (reason) => rejected.push(reason),
  });
  controller.arm(TASK);
  assert.equal(controller.receive(message({ task_id: 'other' })), false);
  controller.disarm();
  assert.equal(controller.receive(message({ decision_id: 'late' })), false);
  assert.deepEqual(rejected, ['unrelated-decision', 'unrelated-decision']);
});
