# TKT-4 — Implementation Notes: refund-failure handling on cancellation

## Shape
`cancelOrder(orderId, idempotencyKey)` runs as one unit of work. Order row is locked
(`SELECT ... FOR UPDATE` / optimistic version) for the whole span. Order of operations:
validate → compute amount → release inventory → issue refund → commit status change.
The refund (the only non-transactional, non-reversible step) goes **last**, so any local
failure before it rolls back for free, and a refund failure rolls back everything else.
Nothing is persisted as `cancelled` until the provider returns success.

## Guards

| # | Condition detected | Where | On violation |
|---|---|---|---|
| G1 | Duplicate cancellation: idempotency key already recorded | Before any provider call, in the same tx as the lock | Return the stored cancellation result; no second refund. If the key was reused with *different* params → refuse + alert (key collision, never silently overwrite) |
| G2 | Order not in `paid`/`processing` | After lock, before amount computation | Refuse with `ALREADY_SHIPPED` → Returns flow. Not retryable |
| G3 | `refund_amount > total − already_refunded` (prior-refund total read from provider, not local cache) | Before issuing refund | Refuse + alert; never call the provider. Holds even if local state is wrong |
| G4 | Status transition target ≠ `cancelled` from an allowed source | At the write | Refuse the transition + alert; never force the status |
| G5 | Post-commit: refund recorded but reservation still held (or inverse) | Async consistency check keyed off the cancellation record | Alert + halt further processing on that order; do not auto-repair silently |

## Failure paths

* **Refund 4xx / explicit decline** — deterministic failure. Roll back the tx (inventory
  release reverts with it), order stays `paid`, return `REFUND_FAILED` with `retryable: true`.
* **Refund timeout / 5xx** — the provider does *not* guarantee a timeout means no refund
  happened. So: roll back, keep order `paid`, and record a `refund_pending_verification`
  marker with the idempotency key. A reconciliation job re-queries the provider by that key;
  if the refund did land, it replays the cancellation to completion rather than refunding
  twice. Customer sees the same retryable error, and a retry reuses the same key (G1 absorbs it).
* **Inventory release fails** — refund not yet issued, so plain rollback; order stays `paid`.
* **Crash between refund success and commit** — the pending-verification marker plus the
  reconciliation job is what closes this window; without it the refund is invisible locally.
* **Concurrent ship** — the row lock plus a re-read of status inside the tx means ship wins;
  cancel loses and is routed to Returns (G2).

## Notes
* Idempotency key is client-supplied, persisted before the provider call, never derived
  from a timestamp.
* Clock and provider identifiers are injected, so the timeout path can be induced
  deliberately rather than waited for.
* Error surfaced to the customer distinguishes *retryable* (provider failure) from
  *terminal* (already shipped) — the UI needs that split for its error state.
