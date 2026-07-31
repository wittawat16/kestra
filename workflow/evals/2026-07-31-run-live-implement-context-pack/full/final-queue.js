// In-memory retry queue consumed by a single worker loop.
// Messages are { id, type, payload, attempts }.

const HANDLERS = new Map();

export function registerHandler(type, fn) {
  HANDLERS.set(type, fn);
}

export function createQueue() {
  return { pending: [], done: [], dropped: [] };
}

export function enqueue(queue, message) {
  queue.pending.push({ attempts: 0, ...message });
}

// Pulls one message and runs its handler. On throw, paid-tier messages
// (including missing/unrecognized tier) go back to the tail with attempts
// incremented; free-tier messages drop to queue.dropped after one attempt.
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
    const tier = message.tier === 'free' ? 'free' : 'paid';

    if (tier === 'free') {
      if (message.tier !== 'free') {
        throw new Error('free-tier branch entered for a non-free message');
      }
      message.error = err instanceof Error ? err.message : String(err);
      if (!(message.attempts >= 1 && message.error)) {
        throw new Error('refusing to drop message: missing attempts/error');
      }
      queue.dropped.push(message);
      return { status: 'dropped', id: message.id, tier, attempts: message.attempts };
    }

    queue.pending.push(message);
    return { status: 'retry', id: message.id, tier, attempts: message.attempts };
  }
}

export function getMetrics(queue) {
  const metrics = {
    paid: { succeeded: 0, dropped: 0 },
    free: { succeeded: 0, dropped: 0 },
  };

  for (const message of queue.done) {
    const tier = message.tier === 'free' ? 'free' : 'paid';
    metrics[tier].succeeded += 1;
  }
  for (const message of queue.dropped) {
    const tier = message.tier === 'free' ? 'free' : 'paid';
    metrics[tier].dropped += 1;
  }

  return metrics;
}
