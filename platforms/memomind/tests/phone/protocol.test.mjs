import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  decodeDecision,
  decodeRequest,
  decodeResult,
  encodeDecision,
  encodeRequest,
  encodeResult,
} from '../../phone/src/protocol.js';

const vectors = JSON.parse(
  await readFile(new URL('../../protocol/vectors.json', import.meta.url), 'utf8'),
);

const hex = (bytes) => Buffer.from(bytes).toString('hex');

test('request codec preserves the complete canonical task envelope', () => {
  const encoded = encodeRequest(vectors.request.value);
  assert.equal(hex(encoded), vectors.request.hex);
  assert.deepEqual(decodeRequest(encoded), vectors.request.value);
});

test('decision codec preserves 53-bit canonical identity fields', () => {
  const encoded = encodeDecision(vectors.decision.value);
  assert.equal(hex(encoded), vectors.decision.hex);
  assert.deepEqual(decodeDecision(encoded), vectors.decision.value);
});

test('rejects identifiers and revisions outside the canonical contract', () => {
  assert.throws(
    () => encodeRequest({ ...vectors.request.value, task_id: 'x'.repeat(129) }),
    /task_id is too long/,
  );
  assert.throws(
    () => encodeRequest({ ...vectors.request.value, revision: 9007199254740992 }),
    /revision/,
  );
  assert.throws(
    () => encodeRequest({
      ...vectors.request.value,
      actions: [
        { action_id: 'approve', label: 'Approve' },
        { action_id: 'approve', label: 'Again' },
      ],
    }),
    /unique/,
  );
});

test('result codec preserves correlation and retry semantics', () => {
  const result = vectors.result.value;
  assert.equal(hex(encodeResult(result)), vectors.result.hex);
  assert.deepEqual(decodeResult(encodeResult(result)), result);
  assert.throws(
    () => encodeResult({ ...result, original_status: 'ACCEPTED' }),
    /original_status/,
  );
  assert.throws(
    () => encodeResult({ ...result, status: 'DUPLICATE' }),
    /original_status/,
  );
  const deliveryUnknown = {
    ...result,
    status: 'ERROR',
    reason: 'transport timeout',
  };
  assert.deepEqual(decodeResult(encodeResult(deliveryUnknown)), deliveryUnknown);
});
