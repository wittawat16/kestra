import http from 'node:http';
import { createQueue, enqueue, registerHandler, step } from '/tmp/eval33/fixture/src/queue.js';

// Simulate the ticket's proposed additive change: step() marks in-flight and CLEARS it
// when the message leaves the handler by either path.
function stepWithInflight(queue, clock = Date.now) {
  const message = queue.pending.shift();
  if (!message) return { status: 'idle' };
  const handler = new Map(HANDLERS_VIEW).get(message.type);
  if (!handler) { queue.pending.push(message); return { status: 'skipped', id: message.id }; }
  queue.inFlight = { id: message.id, startedAt: clock() };      // mark
  try {
    handler(message.payload);
    queue.done.push(message);
    return { status: 'ok', id: message.id };
  } catch (err) {
    message.lastError = { message: String(err && err.message ? err.message : err), at: clock() };
    message.attempts += 1;
    queue.pending.push(message);
    return { status: 'retry', id: message.id };
  } finally {
    queue.inFlight = null;                                       // clear on either path
  }
}
const HANDLERS_VIEW = new Map();
HANDLERS_VIEW.set('slow', () => { const end = Date.now() + 700; while (Date.now() < end) {} });

const q = createQueue();
enqueue(q, { id: 'slow-1', type: 'slow', payload: null });

const observations = [];
const server = http.createServer((req, res) => {
  observations.push({ at: Date.now(), inFlight: q.inFlight, pending: q.pending.length });
  res.end('ok');
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const port = server.address().port;
console.log('B0 bound:', JSON.stringify(server.address()));

// Fire polls DURING the synchronous handler, then read what they saw.
const t0 = Date.now();
const polls = [
  fetch(`http://127.0.0.1:${port}/frag`),
  new Promise(r => setTimeout(() => r(fetch(`http://127.0.0.1:${port}/frag`)), 100)),
  new Promise(r => setTimeout(() => r(fetch(`http://127.0.0.1:${port}/frag`)), 300)),
];
const res = stepWithInflight(q);
console.log('B1 step returned:', res.status, 'after', Date.now() - t0, 'ms of blocking');
console.log('B2 observations served DURING the block:', observations.length);
await Promise.all(polls);
await new Promise(r => setTimeout(r, 50));
console.log('B3 total observations after block:', observations.length);
console.log('B4 what each poll saw -> inFlight:',
  JSON.stringify(observations.map(o => ({ dtMs: o.at - t0, inFlight: o.inFlight }))));
console.log('B5 VERDICT: any poll ever observed a non-null inFlight?',
  observations.some(o => o.inFlight !== null && o.inFlight !== undefined));
console.log('B6 retained lastError after retry path:', JSON.stringify(q.pending[0] && q.pending[0].lastError));
server.close();
