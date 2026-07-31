// In-memory retry queue consumed by a single worker loop.
// Messages are { id, type, payload, attempts }.

const HANDLERS = new Map();

export function registerHandler(type, fn) {
  HANDLERS.set(type, fn);
}

export function createQueue() {
  return { pending: [], done: [] };
}

export function enqueue(queue, message) {
  queue.pending.push({ attempts: 0, ...message });
}

// Pulls one message and runs its handler. On throw, the message goes back to
// the tail of the queue with attempts incremented.
export function step(queue) {
  const message = queue.pending.shift();
  if (!message) return { status: 'idle' };

  const handler = HANDLERS.get(message.type);
  if (!handler) {
    queue.pending.push(message);
    return { status: 'skipped', id: message.id };
  }

  try {
    handler(message.payload);
    queue.done.push(message);
    return { status: 'ok', id: message.id };
  } catch (err) {
    message.attempts += 1;
    queue.pending.push(message);
    return { status: 'retry', id: message.id, attempts: message.attempts };
  }
}
