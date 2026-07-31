// In-memory retry queue consumed by a single worker loop.
// Messages are { id, type, payload, attempts, tier }.

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

// On throw: paid tier (including missing/unrecognized tier) requeues to the
// tail of pending, indefinitely; free tier drops into `dropped` after its
// one attempt.
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
        throw new Error('free-tier drop attempted for a non-free message');
      }
      message.error = err.message;
      if (!(message.attempts >= 1 && typeof message.error === 'string' && message.error.length > 0)) {
        throw new Error('cannot drop message without a recorded failure');
      }
      queue.dropped.push(message);
      return { status: 'dropped', id: message.id, tier: 'free', attempts: message.attempts };
    }

    queue.pending.push(message);
    return { status: 'retry', id: message.id, tier: 'paid', attempts: message.attempts };
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
