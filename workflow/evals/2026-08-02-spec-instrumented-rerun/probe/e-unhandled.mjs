import { createQueue, enqueue, registerHandler, step } from '/tmp/eval33/fixture/src/queue.js';
registerHandler('probe-async2', async () => { throw new Error('async boom, no listener'); });
const q = createQueue();
enqueue(q, { id: 'x', type: 'probe-async2', payload: null });
console.log('D5 step result:', JSON.stringify(step(q)), '| done:', q.done.length);
setTimeout(() => console.log('D5 process SURVIVED the rejection'), 100);
