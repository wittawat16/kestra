# TKT-4 — Refund-failure handling on cancellation (implementation notes)

## Shape
Cancellation runs as one guarded unit: preflight guards → refund call → inventory release → status
transition, committed together. Nothing mutates order state until the provider confirms the refund.
Order the side effects so the *irreversible external* call (refund) happens last relative to local
state we can still roll back, and hold the local transaction open across it; on any provider error
the transaction rolls back and the order is left exactly as found (`paid`).

## Failure paths handled
1. **Provider timeout.** A timeout does *not* mean the refund didn't happen (spec: Reality
   Constraints). Treat as indeterminate: roll back local state, leave order `paid`, record the
   attempt against the idempotency key, surface a retry-able error. Retry reuses the *same* key so
   the provider dedupes rather than double-refunding.
2. **Provider 5xx / transport error.** Same rollback; retry-able error to the customer.
3. **Provider 4xx (rejected — e.g. charge unsettled, amount invalid).** Roll back, non-retry-able
   error, alert — retrying will not fix it.
4. **Inventory release fails after a successful refund.** Cannot roll back the refund locally →
   compensate: enqueue a durable release job keyed to the reservation, hold the order out of
   `cancelled`, and alert. Half-applied state must never be left silently.
5. **Concurrent ship during cancel.** Optimistic lock on order status/version; on version conflict
   the cancel loses, transaction aborts, customer routed to Returns.

## Guards
| Guard | Condition detected | On violation |
|---|---|---|
| Atomicity guard | Transaction/saga boundary around refund + release; post-commit check that refund state and reservation state agree | Halt, leave order `paid`, alert; never leave a half-applied cancellation |
| Idempotency key | Key present and unseen before any provider call | Refuse duplicate, return existing cancellation state; alert if same key arrives with different params |
| Refund-bound assertion | Compute uncredited balance from the provider's prior-refund record, assert `refund ≤ total − already_refunded` before issuing | Refuse, never issue the call, alert — holds even if local state is wrong |
| Status-transition guard | Only `paid`/`processing` → `cancelled` | Refuse the transition and alert; never force the target status |
| Optimistic lock | Order version changed since read (ship won) | Abort cancel, return Returns-flow rejection |

Every guard refuses or halts and alerts; none logs-and-continues.

## Test hooks
Clock and provider identifiers pinned. Provider latency floating, but the timeout path is exercised
by a deliberately induced failure — assert order still `paid`, no reservation released, error marked
retry-able, and a retry with the same idempotency key issues no second refund.
