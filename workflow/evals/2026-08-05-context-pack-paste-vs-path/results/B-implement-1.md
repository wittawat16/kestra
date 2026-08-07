# TKT-4 — Refund-failure handling on cancellation: implementation notes

## Shape
`cancelOrder(orderId, idempotencyKey)` runs as one unit: acquire order row with an optimistic
lock on `status` + `version` → assert cancellable → compute refund amount → call provider →
release inventory → commit `cancelled`. Nothing is persisted as `cancelled` until the refund is
confirmed settled; on any failure the transaction rolls back and the order is left in `paid`.

Ordering is forced by the provider: refund first, inventory release second. Inventory release is
reversible by re-reserving; a refund is not reversible, so it must be the step whose outcome is
known before anything else is committed.

## Failure paths
| Path | Handling |
|---|---|
| Provider 5xx / rejection (definite failure) | Roll back, order stays `paid`, return retry-able error to customer |
| Provider **timeout** (indeterminate) | Treat as *unknown*, not failure — do **not** roll forward or retry blindly; mark the cancellation attempt `pending_reconciliation`, return retry-able error, reconcile against the provider's refund record before any further attempt |
| Charge not yet settled | Refuse before calling; surface "not yet refundable, try again shortly" |
| Inventory release fails after a successful refund | Compensating action, not silent rollback: refund already happened, so record it, alert, and drive release via a retry worker — the order does not stay `paid` in this case |
| Concurrent ship | Optimistic-lock version bump loses; cancel is refused and routed to Returns |
| Duplicate cancel | Idempotency key hit returns the existing cancellation state, no provider call |

## Guards
| Guard | Condition detected | On violation |
|---|---|---|
| Atomicity guard | Refund state and reservation state disagree at post-commit check | Halt, leave order `paid`, alert — never leave a half-applied cancellation |
| Idempotency guard | Cancellation key already seen (checked *before* any provider call) | Refuse duplicate, return existing state; alert if the same key arrives with different parameters |
| Refund-bound guard | `refund > total − already_refunded`, computed from the provider's prior-refund record | Refuse, never issue the call, alert — holds even when local state is wrong |
| Status-transition guard | Target transition is not `paid`/`processing` → `cancelled` | Refuse the transition and alert; never force the status |
| Settlement precondition | Charge unsettled at call time | Refuse before the provider call |

Note on the prior-refund read: the provider does not promise immediate consistency after a write,
so the refund-bound guard reads it as a *bound*, and any timeout-era attempt reconciles first
rather than trusting a freshly-read total.

## Tests
Failure is induced deliberately (injected 5xx and injected timeout) — clock and provider ids
pinned; the timeout case asserts order still `paid`, no inventory released, no second refund on
the retry that follows.
