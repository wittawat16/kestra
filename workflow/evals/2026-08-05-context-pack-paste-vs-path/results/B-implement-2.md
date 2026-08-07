# TKT-4 — refund-failure handling on cancellation (implementation notes)

## Shape
Cancellation runs as an ordered saga, not a DB transaction — the refund and the inventory release
live in two external systems. Order of operations is chosen so the *reversible* side goes last:

1. Acquire the order row with an optimistic lock on `status` + version (loses to a concurrent ship).
2. Derive an idempotency key from `(order_id, cancellation_attempt_id)`; look it up first.
3. Compute `refund = total − already_refunded`, read from the provider's prior-refund record.
4. Issue the refund. **Only on a confirmed success** release the reservation and flip status to
   `cancelled` in one local commit.

Inventory release never precedes the refund: releasing is the step with no clean compensation once
stock is re-sold, whereas an unissued refund leaves the order exactly as it was.

## Failure paths
* **Refund returns a definite failure (4xx / declined).** No state written. Order stays `paid`,
  reservation untouched, customer gets a retry-able error. This is the clean case.
* **Refund times out or 5xx's.** The provider does *not* guarantee a timeout means the refund did
  not happen — so this is ambiguous, not a failure. Do not release inventory, do not flip status,
  do not retry blindly with a fresh key. Persist the attempt as `refund_pending` keyed by the
  idempotency key, return the same retry-able error, and let a reconciler re-query the provider for
  that key before any second call.
* **Refund succeeded but inventory release fails.** Order is refunded; release is retried by the
  reconciler against the same reservation id (release-twice is an error at the service, so the
  retry must be guarded by reading reservation state first). Status stays `paid` until both land.
* **Charge not yet settled.** Refund is refused upstream; treat as definite failure, message the
  customer to retry later rather than surfacing a provider error.
* **Duplicate cancel.** Idempotency-key hit returns the stored cancellation state; no second
  provider call is made.

## Guards
| Guard | Condition detected | On violation |
|---|---|---|
| Atomicity check | refund state and reservation state disagree after the saga | halt, leave order `paid`, alert — never persist a half-cancelled order |
| Idempotency key | key already seen | refuse; return stored state. Same key + different params → refuse and alert |
| Refund bound | `refund > total − already_refunded` | refuse before the provider call, alert |
| Status transition | source status not `paid`/`processing` | refuse the transition and alert; never force the target status |
| Ambiguous-outcome guard | timeout/5xx with no confirmed provider result | block any further refund call for that order until reconciled |

None of these log-and-continue: each either refuses the operation or halts and alerts.
