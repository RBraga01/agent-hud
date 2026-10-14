const MAGIC_A = 0x41;
const MAGIC_H = 0x48;
const VERSION = 2;
const REQUEST = 1;
const DECISION = 2;
const RESULT = 3;
const HEADER_BYTES = 6;
const MAX_ID_BYTES = 128;
const MAX_SESSION_BYTES = 100;
const MAX_TITLE_BYTES = 63;
const MAX_CONTEXT_BYTES = 127;
const MAX_LABEL_BYTES = 16;
const MAX_REASON_BYTES = 256;
const MAX_REVISION = Number.MAX_SAFE_INTEGER;

export const REQUEST_CHANNEL = 0x4148;
export const RESPONSE_CHANNEL = 0x4149;

const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });
const IDENTIFIER = /^[A-Za-z0-9._:-]+$/;

function textBytes(value, field, maximum, { allowEmpty = false, identifier = false } = {}) {
  if (typeof value !== 'string' || (!allowEmpty && value.length === 0)) {
    throw new TypeError(`${field} must be ${allowEmpty ? 'a string' : 'a non-empty string'}`);
  }
  if (identifier && !IDENTIFIER.test(value)) {
    throw new TypeError(`${field} must be a canonical identifier`);
  }
  const bytes = encoder.encode(value);
  if (bytes.length > maximum) throw new RangeError(`${field} is too long`);
  return bytes;
}

function revisionValue(value) {
  if (!Number.isSafeInteger(value) || value < 0 || value > MAX_REVISION) {
    throw new RangeError('revision must be an integer from 0 to 2^53-1');
  }
  return value;
}

function packet(type, payload) {
  const bytes = new Uint8Array(HEADER_BYTES + payload.length);
  bytes.set([MAGIC_A, MAGIC_H, VERSION, type], 0);
  new DataView(bytes.buffer).setUint16(4, payload.length, false);
  bytes.set(payload, HEADER_BYTES);
  return bytes;
}

function payloadFor(bytes, type) {
  if (!(bytes instanceof Uint8Array) || bytes.length < HEADER_BYTES) {
    throw new TypeError('packet must be a Uint8Array with a complete header');
  }
  if (
    bytes[0] !== MAGIC_A || bytes[1] !== MAGIC_H ||
    bytes[2] !== VERSION || bytes[3] !== type
  ) {
    throw new Error('unsupported Agent HUD packet');
  }
  const size = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
    .getUint16(4, false);
  if (size !== bytes.length - HEADER_BYTES) {
    throw new Error('Agent HUD packet length mismatch');
  }
  return bytes.subarray(HEADER_BYTES);
}

function writeText(payload, offset, bytes) {
  payload[offset] = bytes.length;
  payload.set(bytes, offset + 1);
  return offset + 1 + bytes.length;
}

function readText(payload, cursor, field, maximum, options = {}) {
  if (cursor.offset >= payload.length) throw new Error(`missing ${field}`);
  const size = payload[cursor.offset++];
  if (cursor.offset + size > payload.length) throw new Error(`invalid ${field}`);
  const value = decoder.decode(payload.subarray(cursor.offset, cursor.offset + size));
  cursor.offset += size;
  textBytes(value, field, maximum, options);
  return value;
}

function writeRevision(payload, offset, revision) {
  new DataView(payload.buffer, payload.byteOffset, payload.byteLength)
    .setBigUint64(offset, BigInt(revision), false);
  return offset + 8;
}

function readRevision(payload, cursor) {
  if (cursor.offset + 8 > payload.length) throw new Error('missing revision');
  const value = new DataView(
    payload.buffer, payload.byteOffset + cursor.offset, 8,
  ).getBigUint64(0, false);
  cursor.offset += 8;
  if (value > BigInt(MAX_REVISION)) throw new Error('revision exceeds 2^53-1');
  return Number(value);
}

function writeLongText(payload, offset, bytes) {
  new DataView(payload.buffer, payload.byteOffset, payload.byteLength)
    .setUint16(offset, bytes.length, false);
  payload.set(bytes, offset + 2);
  return offset + 2 + bytes.length;
}

function readLongText(payload, cursor, field, maximum) {
  if (cursor.offset + 2 > payload.length) throw new Error(`missing ${field}`);
  const size = new DataView(
    payload.buffer, payload.byteOffset + cursor.offset, 2,
  ).getUint16(0, false);
  cursor.offset += 2;
  if (cursor.offset + size > payload.length) throw new Error(`invalid ${field}`);
  const value = decoder.decode(payload.subarray(cursor.offset, cursor.offset + size));
  cursor.offset += size;
  textBytes(value, field, maximum, { allowEmpty: true });
  return value;
}

function canonicalActions(actions) {
  if (!Array.isArray(actions) || actions.length < 1 || actions.length > 2) {
    throw new RangeError('actions must contain one or two entries');
  }
  const seen = new Set();
  return actions.map((action, index) => {
    if (action === null || typeof action !== 'object') {
      throw new TypeError(`actions[${index}] must be an object`);
    }
    const action_id = textBytes(
      action.action_id, `actions[${index}].action_id`, MAX_ID_BYTES,
      { identifier: true },
    );
    if (seen.has(action.action_id)) throw new RangeError('action IDs must be unique');
    seen.add(action.action_id);
    const label = textBytes(action.label, `actions[${index}].label`, MAX_LABEL_BYTES);
    return { action_id, label };
  });
}

export function encodeRequest({
  session_id, task_id, revision, title, short_context, actions,
}) {
  const session = textBytes(session_id, 'session_id', MAX_SESSION_BYTES, { identifier: true });
  const task = textBytes(task_id, 'task_id', MAX_ID_BYTES, { identifier: true });
  const heading = textBytes(title, 'title', MAX_TITLE_BYTES);
  const context = textBytes(short_context, 'short_context', MAX_CONTEXT_BYTES, { allowEmpty: true });
  const encodedActions = canonicalActions(actions);
  revisionValue(revision);
  const actionBytes = encodedActions.reduce(
    (total, action) => total + 2 + action.action_id.length + action.label.length, 0,
  );
  const payload = new Uint8Array(
    1 + session.length + 1 + task.length + 8 + 1 + heading.length +
    1 + context.length + 1 + actionBytes,
  );
  let offset = writeText(payload, 0, session);
  offset = writeText(payload, offset, task);
  offset = writeRevision(payload, offset, revision);
  offset = writeText(payload, offset, heading);
  offset = writeText(payload, offset, context);
  payload[offset++] = encodedActions.length;
  for (const action of encodedActions) {
    offset = writeText(payload, offset, action.action_id);
    offset = writeText(payload, offset, action.label);
  }
  return packet(REQUEST, payload);
}

export function decodeRequest(bytes) {
  const payload = payloadFor(bytes, REQUEST);
  const cursor = { offset: 0 };
  const session_id = readText(payload, cursor, 'session_id', MAX_SESSION_BYTES, { identifier: true });
  const task_id = readText(payload, cursor, 'task_id', MAX_ID_BYTES, { identifier: true });
  const revision = readRevision(payload, cursor);
  const title = readText(payload, cursor, 'title', MAX_TITLE_BYTES);
  const short_context = readText(payload, cursor, 'short_context', MAX_CONTEXT_BYTES, { allowEmpty: true });
  if (cursor.offset >= payload.length) throw new Error('missing actions');
  const count = payload[cursor.offset++];
  if (count < 1 || count > 2) throw new Error('invalid action count');
  const actions = [];
  const seen = new Set();
  for (let index = 0; index < count; index += 1) {
    const action_id = readText(payload, cursor, `actions[${index}].action_id`, MAX_ID_BYTES, { identifier: true });
    const label = readText(payload, cursor, `actions[${index}].label`, MAX_LABEL_BYTES);
    if (seen.has(action_id)) throw new Error('action IDs must be unique');
    seen.add(action_id);
    actions.push({ action_id, label });
  }
  if (cursor.offset !== payload.length) throw new Error('invalid request payload');
  return { session_id, task_id, revision, title, short_context, actions };
}

export function encodeDecision({ decision_id, task_id, revision, action_id }) {
  const decision = textBytes(decision_id, 'decision_id', MAX_ID_BYTES, { identifier: true });
  const task = textBytes(task_id, 'task_id', MAX_ID_BYTES, { identifier: true });
  const action = textBytes(action_id, 'action_id', MAX_ID_BYTES, { identifier: true });
  revisionValue(revision);
  const payload = new Uint8Array(
    1 + decision.length + 1 + task.length + 8 + 1 + action.length,
  );
  let offset = writeText(payload, 0, decision);
  offset = writeText(payload, offset, task);
  offset = writeRevision(payload, offset, revision);
  writeText(payload, offset, action);
  return packet(DECISION, payload);
}

export function decodeDecision(bytes) {
  const payload = payloadFor(bytes, DECISION);
  const cursor = { offset: 0 };
  const decision_id = readText(payload, cursor, 'decision_id', MAX_ID_BYTES, { identifier: true });
  const task_id = readText(payload, cursor, 'task_id', MAX_ID_BYTES, { identifier: true });
  const revision = readRevision(payload, cursor);
  const action_id = readText(payload, cursor, 'action_id', MAX_ID_BYTES, { identifier: true });
  if (cursor.offset !== payload.length) throw new Error('invalid decision payload');
  return { decision_id, task_id, revision, action_id };
}

const RESULT_STATUS = {
  ACCEPTED: 1,
  STALE: 2,
  INVALID_ACTION: 3,
  ERROR: 4,
  DUPLICATE: 5,
};
const RESULT_NAME = Object.fromEntries(
  Object.entries(RESULT_STATUS).map(([name, value]) => [value, name]),
);

function validateResultStatus(status, original_status) {
  const duplicateOriginals = ['ACCEPTED', 'STALE', 'INVALID_ACTION'];
  if (status === 'DUPLICATE' && !duplicateOriginals.includes(original_status)) {
    throw new RangeError('DUPLICATE requires a terminal original_status');
  }
  if (status !== 'DUPLICATE' && original_status !== null) {
    throw new RangeError('original_status is only valid for DUPLICATE');
  }
  if (RESULT_STATUS[status] === undefined) throw new RangeError('unsupported result status');
}

export function encodeResult({
  decision_id, task_id, revision, status, original_status = null, reason = '',
}) {
  const decision = textBytes(decision_id, 'decision_id', MAX_ID_BYTES, { identifier: true });
  const task = textBytes(task_id, 'task_id', MAX_ID_BYTES, { identifier: true });
  const detail = textBytes(reason, 'reason', MAX_REASON_BYTES, { allowEmpty: true });
  revisionValue(revision);
  validateResultStatus(status, original_status);
  const originalCode = original_status === null ? 0 : RESULT_STATUS[original_status];
  const payload = new Uint8Array(
    1 + decision.length + 1 + task.length + 8 + 2 + 2 + detail.length,
  );
  let offset = writeText(payload, 0, decision);
  offset = writeText(payload, offset, task);
  offset = writeRevision(payload, offset, revision);
  payload[offset++] = RESULT_STATUS[status];
  payload[offset++] = originalCode;
  writeLongText(payload, offset, detail);
  return packet(RESULT, payload);
}

export function decodeResult(bytes) {
  const payload = payloadFor(bytes, RESULT);
  const cursor = { offset: 0 };
  const decision_id = readText(payload, cursor, 'decision_id', MAX_ID_BYTES, { identifier: true });
  const task_id = readText(payload, cursor, 'task_id', MAX_ID_BYTES, { identifier: true });
  const revision = readRevision(payload, cursor);
  if (cursor.offset + 2 > payload.length) throw new Error('missing result status');
  const status = RESULT_NAME[payload[cursor.offset++]];
  const originalCode = payload[cursor.offset++];
  const original_status = originalCode === 0 ? null : RESULT_NAME[originalCode];
  const reason = readLongText(payload, cursor, 'reason', MAX_REASON_BYTES);
  if (!status || cursor.offset !== payload.length) throw new Error('invalid result status');
  validateResultStatus(status, original_status);
  return { decision_id, task_id, revision, status, original_status, reason };
}
