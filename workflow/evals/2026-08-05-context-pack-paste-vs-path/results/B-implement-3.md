# TKT-4 — refund-failure handling on cancellation (implementation notes)

## Shape
Cancellation runs as a saga with an explicit ordering: **validate → reserve intent → refund →
release inventory → commit status**. Nothing mutates order status or inventory until the refund
is known-settled. On any failure the order stays `paid` and the caller gets a retry-able error
(`REFUND_FAILED`, retryable=true) carrying the same idempotency key so a retry is safe.

## Failure paths
| Path | Handling |
|---|---|
| Provider 5xx / connection error | No state change; return retry-able error. |
| **Timeout** | Treated as *indeterminate*, not failure — the provider does not guarantee a timeout means the refund didn't happen. Do **not** retry blindly: reconcile by querying the refund by idempotency key; only after it resolves absent do we allow reissue. |
| Charge not settled yet | Refuse up front (a refund can only be issued against a settled charge); error says "try again shortly", retry-able. |
| Prior-refund total stale | Provider prior-refund totals are not immediately consistent; read them from the provider (not our cache) at issue time and treat a disagreement as a refuse, not a guess. |
| Refund succeeded, inventory release failed | Release is not synchronous and double-release is an error. Retry release with the reservation id (idempotent by id-check, never blind re-call); if it stays unresolved, halt and alert — do not roll the order back to `paid` after money moved. |
| Cancel racing a shipment | Optimistic lock on order status/version; ship wins, cancel refuses and routes to Returns. |
| Duplicate cancel | Idempotency key lookup returns the existing cancellation state; no second provider call. |

## Guards (condition detected → what happens on violation)
1. **Atomicity guard** — post-commit consistency check comparing refund state against reservation
   state. Violation (one applied, not the other): halt, leave order `paid` where possible, alert.
   Never leave a half-cancelled order in place.
2. **Idempotency guard** — key checked before any provider call. Violation (key already used):
   refuse and return the existing cancellation state; if the key was reused with *different*
   parameters, refuse and alert (that is a caller bug, not a retry).
3. **Refund bound guard** — assert `refund ≤ total − already_refunded` against the provider's own
   prior-refund record. Violation: refuse, never issue the call, alert. Holds even when our local
   order total is wrong.
4. **Status transition guard** — only `paid`/`processing` → `cancelled`. Violation: refuse the
   transition and alert; never force the target status.

All four refuse-or-halt; none log-and-continue. Alerts fire on the invariant breaches (1–4), not
on ordinary provider failures, which are expected and merely retried by the customer.
