# Rough idea (post-grilling) — dead-letter path for the retry queue

Settled in discussion, ready for a spec:

- A message that has failed its handler **3 times** should stop being retried. It moves to a
  dead-letter list on the queue instead of going back to the tail of `pending`.
- Retries should be spaced out rather than immediate — a backoff based on attempt count, read off
  the wall clock.
- Dead-lettered messages keep their last error message so an operator can see why.
- A message whose `type` has **no registered handler** is left in the queue untouched and the worker
  moves on. That's a config problem, not a data problem, so nothing about the message changes and
  its attempt count is not touched.
- The worker must never silently keep processing a queue that contains messages it has no handler
  for. That state means a deploy shipped a message type without its handler, and somebody needs to
  find out.
- Operators want to be able to see that most messages get through without hitting the dead-letter
  path.
- Draining the dead-letter list back into `pending` after a fix is out of scope for now.
