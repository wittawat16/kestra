import { createQueue, enqueue, registerHandler, step } from '/tmp/eval33/fixture/src/queue.js';

// C1/C2: retained error on the throw path, and whether it travels into done on later success
let boom = true;
registerHandler('probe-flaky', () => { if (boom) throw new Error('handler exploded'); });
const q = createQueue();
enqueue(q, { id: 'f1', type: 'probe-flaky', payload: null });
step(q); // today: error discarded
console.log('C1 today, after failing step, message keys:', Object.keys(q.pending[0]));
boom = false;
step(q);
console.log('C2 after success, in done:', q.done.length === 1, '| keys:', Object.keys(q.done[0]));

// C3: payload rendering degrade paths — what actually throws / returns undefined
const circular = {}; circular.self = circular;
const cases = [
  ['object', { a: 1 }], ['array', [1, 2]], ['string', 'hi'], ['number', 42],
  ['null', null], ['undefined', undefined], ['circular', circular],
  ['bigint', 10n], ['function', () => {}], ['symbol-prop', { s: Symbol('x') }],
  ['Map', new Map([['k', 'v']])],
];
for (const [name, v] of cases) {
  let out;
  try { const s = JSON.stringify(v, null, 2); out = s === undefined ? 'RETURNS undefined' : `ok len=${s.length}`; }
  catch (e) { out = `THROWS ${e.constructor.name}: ${e.message.slice(0, 44)}`; }
  console.log(`C3 ${name.padEnd(12)} -> ${out}`);
}

// C4: escaping the five characters
const esc = (s) => String(s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
const hostile = `<script>alert("x")</script>&'`;
console.log('C4 escaped:', esc(hostile), '| raw "<script" survives:', esc(hostile).includes('<script'));

// C5: 10k scale — single-pass summary, and the cost of shift()
const big = createQueue();
const t0 = process.hrtime.bigint();
for (let i = 0; i < 10000; i++) enqueue(big, { id: i, type: `t${i % 12}`, payload: { i }, enqueuedAt: 1000 + i });
const t1 = process.hrtime.bigint();
function summarize(qq, now) {
  let maxAttempts = 0, oldest = null; const types = new Set();
  for (const m of qq.pending) {
    if (m.attempts > maxAttempts) maxAttempts = m.attempts;
    types.add(m.type);
    if (oldest === null || m.enqueuedAt < oldest) oldest = m.enqueuedAt;
  }
  return { pending: qq.pending.length, done: qq.done.length, types: types.size, maxAttempts,
           oldestWaitMs: oldest === null ? null : now - oldest };
}
const t2 = process.hrtime.bigint();
let s; for (let k = 0; k < 20; k++) s = summarize(big, 99999);
const t3 = process.hrtime.bigint();
console.log('C5 enqueue 10k:', Number(t1 - t0) / 1e6, 'ms | summary x20:', Number(t3 - t2) / 1e6,
  'ms | per-summary:', (Number(t3 - t2) / 1e6 / 20).toFixed(3), 'ms |', JSON.stringify(s));
// capped render cost vs uncapped
const t4 = process.hrtime.bigint();
const rowsCapped = big.pending.slice(0, 200).map(m => `<tr><td>${esc(m.id)}</td><td>${esc(m.type)}</td><td>${esc(m.attempts)}</td></tr>`).join('');
const t5 = process.hrtime.bigint();
const rowsAll = big.pending.map(m => `<tr><td>${esc(m.id)}</td><td>${esc(m.type)}</td><td>${esc(m.attempts)}</td></tr>`).join('');
const t6 = process.hrtime.bigint();
console.log('C5 render 200 rows:', Number(t5 - t4) / 1e6, 'ms | render 10000 rows:', Number(t6 - t5) / 1e6,
  'ms | bytes uncapped:', rowsAll.length, '| bytes capped:', rowsCapped.length);
// shift() cost on 10k (pre-existing, worker-side)
const t7 = process.hrtime.bigint(); big.pending.shift(); const t8 = process.hrtime.bigint();
console.log('C5 one shift() on 10k:', Number(t8 - t7) / 1e6, 'ms');
