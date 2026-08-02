import { createQueue, enqueue, registerHandler, step } from '/tmp/eval33/fixture/src/queue.js';

// F1: message conservation — does any step() path drop a message?
registerHandler('f-ok', () => {});
registerHandler('f-bad', () => { throw new Error('x'); });
const q = createQueue();
const ids = [];
for (let i = 0; i < 60; i++) {
  const type = ['f-ok', 'f-bad', 'f-nohandler'][i % 3];
  enqueue(q, { id: `m${i}`, type, payload: i }); ids.push(`m${i}`);
}
for (let i = 0; i < 500; i++) step(q);
const seen = new Set([...q.pending, ...q.done].map(m => m.id));
console.log('F1 conserved:', seen.size === ids.length, '| pending+done =', q.pending.length + q.done.length, 'of', ids.length);
console.log('F1 no-handler msgs still circulating w/ attempts 0:',
  q.pending.filter(m => m.type === 'f-nohandler').every(m => m.attempts === 0));
console.log('F1 f-bad attempts grew:', Math.max(...q.pending.filter(m => m.type === 'f-bad').map(m => m.attempts)));

// F2: never-enqueued vs drained-empty are distinguishable
const fresh = createQueue();
const drained = createQueue();
enqueue(drained, { id: 'd1', type: 'f-ok', payload: null }); step(drained);
console.log('F2 fresh  pending/done:', fresh.pending.length, fresh.done.length);
console.log('F2 drained pending/done:', drained.pending.length, drained.done.length);
console.log('F2 distinguishable by (pending===0 && done===0):',
  (fresh.pending.length === 0 && fresh.done.length === 0) !== (drained.pending.length === 0 && drained.done.length === 0));

// F3: requeue semantics — move index k to 0; length, attempts, enqueue time, relative order preserved
function requeue(queue, rawId) {
  const id = String(rawId);
  const i = queue.pending.findIndex(m => String(m.id) === id);
  if (i !== -1) { const [m] = queue.pending.splice(i, 1); queue.pending.unshift(m); return { outcome: 'moved', id }; }
  if (queue.done.some(m => String(m.id) === id)) return { outcome: 'already-completed', id };
  return { outcome: 'no-such-message', id };
}
const r = createQueue();
[0,1,2,3,4].forEach(i => enqueue(r, { id: i, type: 'f-ok', payload: null, attempts: i, enqueuedAt: 100 + i }));
const before = r.pending.map(m => m.id), beforeLen = r.pending.length;
const res = requeue(r, '3');   // string id from a URL against numeric stored id
const after = r.pending.map(m => m.id);
console.log('F3 outcome:', res.outcome, '| before:', JSON.stringify(before), '-> after:', JSON.stringify(after));
console.log('F3 length unchanged:', r.pending.length === beforeLen,
  '| attempts preserved:', r.pending[0].attempts === 3,
  '| enqueuedAt preserved:', r.pending[0].enqueuedAt === 103,
  '| others relative order kept:', JSON.stringify(after.slice(1)) === JSON.stringify(before.filter(x => x !== 3)));
console.log('F3 head is what step() takes next:', r.pending[0].id === 3);
console.log('F3 done-id  ->', requeue(r, 'nope').outcome, '| completed ->', (() => { const z = createQueue(); enqueue(z,{id:'c',type:'f-ok',payload:null}); step(z); return requeue(z,'c').outcome; })());
