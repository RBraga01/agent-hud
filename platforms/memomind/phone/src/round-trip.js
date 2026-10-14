import { RESPONSE_CHANNEL, decodeDecision } from './protocol.js';

const IDENTIFIER = /^[A-Za-z0-9._:-]+$/;

export function createSessionId(
  randomUUID = () => globalThis.crypto.randomUUID(),
) {
  const value = randomUUID();
  if (typeof value !== 'string' || !IDENTIFIER.test(value)) {
    throw new TypeError('randomUUID must return a canonical identifier');
  }
  const sessionId = `mm:${value}`;
  if (sessionId.length > 100) throw new RangeError('session identifier is too long');
  return sessionId;
}

function sameDecision(left, right) {
  return left.decision_id === right.decision_id &&
    left.task_id === right.task_id &&
    left.revision === right.revision &&
    left.action_id === right.action_id;
}

export function createRoundTripController({
  onAccepted = () => {},
  onDuplicate = () => {},
  onStale = () => {},
  onInvalidAction = () => {},
  onConflict = () => {},
  onRejected = () => {},
} = {}) {
  let pending = null;
  const seen = new Map();

  return {
    arm(request) {
      pending = {
        task_id: request.task_id,
        revision: request.revision,
        actionIds: new Set(request.actions.map((action) => action.action_id)),
      };
    },

    disarm() {
      pending = null;
    },

    receive(message) {
      if (!message || message.channel !== RESPONSE_CHANNEL) return false;
      let decision;
      try {
        decision = decodeDecision(message.data);
      } catch {
        onRejected('invalid-decision');
        return false;
      }
      if (!pending || decision.task_id !== pending.task_id) {
        onRejected('unrelated-decision');
        return false;
      }

      const prior = seen.get(decision.decision_id);
      if (prior) {
        if (sameDecision(prior.decision, decision)) {
          onDuplicate(decision, prior.status);
        } else {
          onConflict(decision);
        }
        return true;
      }

      if (decision.revision !== pending.revision) {
        seen.set(decision.decision_id, { decision, status: 'STALE' });
        onStale(decision);
        return true;
      }
      if (!pending.actionIds.has(decision.action_id)) {
        seen.set(decision.decision_id, { decision, status: 'INVALID_ACTION' });
        onInvalidAction(decision);
        return true;
      }

      seen.set(decision.decision_id, { decision, status: 'ACCEPTED' });
      onAccepted(decision);
      return true;
    },
  };
}
