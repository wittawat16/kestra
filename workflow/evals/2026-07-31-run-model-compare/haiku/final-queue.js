// In-memory retry queue consumed by a single worker loop.
// Messages are { id, type, payload, attempts, tier, error }.

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

// Pulls one message and runs its handler. On throw, the message goes back to
// the tail of the queue with attempts incremented, or to dropped if free-tier.
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
      if (message.tier !== 'free') throw new Error('Invariant violation: free-tier branch but message.tier !== "free"');
      message.error = (err instanceof Error) ? err.message : String(err);
      if (!message.error) throw new Error('Invariant violation: dropped message has no error string');
      queue.dropped.push(message);
      return { status: 'dropped', id: message.id, tier: 'free', attempts: message.attempts };
    } else {
      queue.pending.push(message);
      return { status: 'retry', id: message.id, tier: 'paid', attempts: message.attempts };
    }
  }
}

export function getMetrics(queue) {
  const metrics = { paid: { succeeded: 0, dropped: 0 }, free: { succeeded: 0, dropped: 0 } };

  queue.done.forEach((msg) => {
    const tier = msg.tier === 'free' ? 'free' : 'paid';
    metrics[tier].succeeded += 1;
  });

  queue.dropped.forEach((msg) => {
    const tier = msg.tier === 'free' ? 'free' : 'paid';
    metrics[tier].dropped += 1;
  });

  return metrics;
}
