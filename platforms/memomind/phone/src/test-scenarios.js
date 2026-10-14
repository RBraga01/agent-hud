import { createRoundTripController } from './round-trip.js';

const TASKS = Object.freeze({
  cancel: Object.freeze({
    task_id: 'task-cancel',
    revision: 1,
    title: 'Cancel safety check',
    short_context: 'Open this request, then go back. Nothing must be sent.',
    actions: Object.freeze([
      Object.freeze({ action_id: 'approve', label: 'Approve' }),
      Object.freeze({ action_id: 'inspect', label: 'Inspect' }),
    ]),
  }),
  stale: Object.freeze({
    task_id: 'task-stale',
    revision: 3,
    title: 'Stale request check',
    short_context: 'Open confirmation before the phone sends revision 4.',
    actions: Object.freeze([
      Object.freeze({ action_id: 'approve', label: 'Approve' }),
      Object.freeze({ action_id: 'inspect', label: 'Inspect' }),
    ]),
  }),
  duplicate: Object.freeze({
    task_id: 'task-duplicate',
    revision: 3,
    title: 'Duplicate-safe retry',
    short_context: 'The first result will be ambiguous. Review before retrying.',
    actions: Object.freeze([
      Object.freeze({ action_id: 'approve', label: 'Approve' }),
      Object.freeze({ action_id: 'inspect', label: 'Inspect' }),
    ]),
  }),
});

function cloneTask(task) {
  return {
    ...task,
    actions: task.actions.map((action) => ({ ...action })),
  };
}

export function createTestScenarioController({
  onResult = () => {},
  onRejected = () => {},
} = {}) {
  let mode = null;
  let activeTask = null;
  let decisionsReceived = 0;
  let ambiguousResultSent = false;

  const controller = createRoundTripController({
    onAccepted(decision) {
      decisionsReceived += 1;
      if (mode === 'duplicate' && !ambiguousResultSent) {
        ambiguousResultSent = true;
        onResult(decision, 'ERROR', {
          reason: 'simulated_ack_loss_after_accept',
        });
        return;
      }
      onResult(decision, 'ACCEPTED', {});
    },
    onDuplicate(decision, originalStatus) {
      decisionsReceived += 1;
      onResult(decision, 'DUPLICATE', { originalStatus });
    },
    onStale(decision) {
      decisionsReceived += 1;
      onResult(decision, 'STALE', {});
    },
    onInvalidAction(decision) {
      decisionsReceived += 1;
      onResult(decision, 'INVALID_ACTION', {});
    },
    onConflict(decision) {
      decisionsReceived += 1;
      onResult(decision, 'ERROR', { reason: 'id_conflict' });
    },
    onRejected,
  });

  return {
    begin(nextMode) {
      const template = TASKS[nextMode];
      if (!template) throw new RangeError(`unknown test scenario: ${nextMode}`);
      mode = nextMode;
      activeTask = cloneTask(template);
      decisionsReceived = 0;
      ambiguousResultSent = false;
      controller.arm(activeTask);
      return cloneTask(activeTask);
    },

    supersede() {
      if (mode !== 'stale' || !activeTask) {
        throw new Error('stale scenario is not active');
      }
      activeTask = { ...activeTask, revision: activeTask.revision + 1 };
      controller.arm(activeTask);
      return cloneTask(activeTask);
    },

    verifyCancel() {
      return {
        passed: mode === 'cancel' && decisionsReceived === 0,
        decisionsReceived,
      };
    },

    reset() {
      mode = null;
      activeTask = null;
      decisionsReceived = 0;
      ambiguousResultSent = false;
      controller.disarm();
    },

    receive(message) {
      return controller.receive(message);
    },
  };
}
