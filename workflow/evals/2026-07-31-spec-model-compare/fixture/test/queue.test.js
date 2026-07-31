import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createQueue, enqueue, registerHandler, step } from '../src/queue.js';

test('runs a registered handler', () => {
  const seen = [];
  registerHandler('email', (p) => seen.push(p));
  const q = createQueue();
  enqueue(q, { id: 1, type: 'email', payload: 'a' });
  assert.equal(step(q).status, 'ok');
  assert.deepEqual(seen, ['a']);
});

test('retries a throwing handler', () => {
  registerHandler('boom', () => { throw new Error('nope'); });
  const q = createQueue();
  enqueue(q, { id: 2, type: 'boom', payload: null });
  assert.equal(step(q).attempts, 1);
  assert.equal(q.pending.length, 1);
});
