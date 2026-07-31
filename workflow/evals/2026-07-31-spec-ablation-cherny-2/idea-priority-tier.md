# Rough idea (post-grilling) — tier-based retry policy for the queue

Settled in discussion, ready for a spec:

- Every enqueued message now carries a `tier`: `'paid'` or `'free'`.
- **Paid-tier messages:** on handler failure, behave exactly as today — increment `attempts`, go
  back to the tail of `pending`, retried indefinitely. Paid customers' SLA guarantees eventual
  delivery.
- **Free-tier messages:** on handler failure, do **not** go back to `pending`. Move to a new
  `dropped` list instead, keeping the message and its (single) failure. Free tier has no retry SLA —
  one attempt only.
- **Messages with no `tier` field** (from a caller that hasn't been updated yet): treat as `'paid'`
  — the safer default, since silently downgrading an un-migrated caller's messages to free-tier
  drop-on-failure would be a regression nobody asked for.
- The no-handler/"skip" path is unaffected by tier — a message with no registered handler for its
  `type` stays in `pending` untouched regardless of `tier`, same as today.
- Operators want to see, per tier, how many messages succeeded vs. got dropped — so they can tell
  whether the free tier's one-shot policy is actually costing them a meaningful failure rate.
- Out of scope: letting free-tier messages retry a configurable number of times (it's exactly one
  attempt, no config knob); resurrecting dropped messages back into `pending`.
