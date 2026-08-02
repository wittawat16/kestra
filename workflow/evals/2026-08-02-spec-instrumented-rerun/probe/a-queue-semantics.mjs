import { createQueue, enqueue, registerHandler, step } from '/tmp/eval33/fixture/src/queue.js';

// PROBE A1: spread order in enqueue — does a caller-supplied attempts/enqueuedAt survive?
const q1 = createQueue();
enqueue(q1, { id: 'a', type: 't', payload: 1 });
enqueue(q1, { id: 'b', type: 't', payload: 1, attempts: 7, enqueuedAt: 123 });
console.log('A1 default-applied:', JSON.stringify(q1.pending[0]));
console.log('A1 caller-wins    :', JSON.stringify(q1.pending[1]));
console.log('A1 VERDICT caller-supplied attempts survives:', q1.pending[1].attempts === 7);

// PROBE A2: no registered handler -> back to tail, attempts NOT incremented, circulates forever
const q2 = createQueue();
enqueue(q2, { id: 'orphan', type: 'no-such-handler', payload: null });
const r1 = step(q2), r2 = step(q2), r3 = step(q2);
console.log('A2 statuses:', r1.status, r2.status, r3.status,
  '| attempts:', q2.pending[0].attempts, '| pending.len:', q2.pending.length, '| done.len:', q2.done.length);

// PROBE A3: async handler that rejects -> not caught, message lands in done, no retained error possible
process.on('unhandledRejection', (e) => console.log('A3 unhandledRejection observed:', e.message));
registerHandler('probe-async', async () => { throw new Error('async boom'); });
const q3 = createQueue();
enqueue(q3, { id: 'async-1', type: 'probe-async', payload: null });
const r4 = step(q3);
console.log('A3 status:', r4.status, '| done.len:', q3.done.length, '| pending.len:', q3.pending.length);

// PROBE A4: step() throws away the error today — nothing on the message records why
registerHandler('probe-throw', () => { throw new Error('why-it-failed'); });
const q4 = createQueue();
enqueue(q4, { id: 'th-1', type: 'probe-throw', payload: null });
step(q4);
console.log('A4 message after retry:', JSON.stringify(q4.pending[0]),
  '| has any error field:', Object.keys(q4.pending[0]).some(k => /err/i.test(k)));

// PROBE A5: duplicate ids are accepted, first-match-from-head is the only resolution
const q5 = createQueue();
enqueue(q5, { id: 'dup', type: 't', payload: 'first' });
enqueue(q5, { id: 'dup', type: 't', payload: 'second' });
console.log('A5 dup ids accepted:', q5.pending.length === 2,
  '| first match payload:', q5.pending.find(m => String(m.id) === 'dup').payload);

// PROBE A6: numeric id vs URL string
console.log('A6 1 === "1":', 1 === '1', '| String(1) === "1":', String(1) === '1');

// PROBE A7: step() is synchronous end-to-end (no await/thenable handling in source)
console.log('A7 step is async fn:', step.constructor.name === 'AsyncFunction');
