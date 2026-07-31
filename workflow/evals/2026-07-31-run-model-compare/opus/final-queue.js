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

// Pulls one message and runs its handler. On throw, a paid-tier message goes
// back to the tail of the queue with attempts incremented; a free-tier message
// gets exactly one attempt and is moved to `dropped`.
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
    const tier = message.tier === 'free' ? 'free' : 'paid';
    message.attempts += 1;

    if (tier === 'paid') {
      queue.pending.push(message);
      return { status: 'retry', id: message.id, tier, attempts: message.attempts };
    }

    if (message.tier !== 'free') {
      throw new Error(
        `drop path reached for tier ${JSON.stringify(message.tier)}; only a literal 'free' may drop`,
      );
    }

    message.error = err?.message || String(err);

    if (message.attempts < 1 || typeof message.error !== 'string' || message.error === '') {
      throw new Error(
        `refusing to drop message ${message.id} without a recorded attempt and error`,
      );
    }

    queue.dropped.push(message);
    return { status: 'dropped', id: message.id, tier, attempts: message.attempts };
  }
}

export function getMetrics(queue) {
  const metrics = {
    paid: { succeeded: 0, dropped: 0 },
    free: { succeeded: 0, dropped: 0 },
  };

  for (const message of queue.done) {
    metrics[message.tier === 'free' ? 'free' : 'paid'].succeeded += 1;
  }
  for (const message of queue.dropped) {
    metrics[message.tier === 'free' ? 'free' : 'paid'].dropped += 1;
  }

  return metrics;
}
