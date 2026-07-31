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

// Pulls one message and runs its handler. On throw: paid tier (including
// missing/unrecognized tier) retries indefinitely; free tier drops after
// exactly one attempt.
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
        throw new Error('invariant violated: entered free-tier branch without message.tier === "free"');
      }
      const error = err instanceof Error ? err.message : String(err);
      if (!(message.attempts >= 1) || !error) {
        throw new Error('invariant violated: dropped message missing attempts >= 1 or a non-empty error string');
      }
      queue.dropped.push({ ...message, error });
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
