# Rough idea (post-grilling) — cap the retry queue's pending size

Settled in discussion, ready for a spec:

- The queue must not let `pending` grow past a configured `maxQueueSize` (e.g. 100) via new
  `enqueue()` calls.
- When `enqueue()` is called while `pending` is already at the cap, the new message must not
  silently disappear — the caller needs to find out it wasn't accepted.
- A message returning from `step()` after a failed handler (attempts incremented) re-enters
  `pending` at the tail — that return path must never be blocked by the cap, even if `pending` is
  already exactly at the cap when the retry re-enters. The cap only gates brand-new `enqueue()`
  calls, not messages returning from a retry.
- Skipped messages (no handler registered for their `type`) sitting in `pending` count toward the
  cap like any other message — they aren't special-cased.
- Operators want visibility into how often `enqueue()` calls get rejected by the cap, so they can
  tell whether the configured size is too small.
- Out of scope: resizing the cap at runtime; persisting rejected messages anywhere.
