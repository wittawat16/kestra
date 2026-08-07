# TKT-4 — Refund-failure handling on cancellation (implementation notes)

## Shape
`CancelOrderService.cancel(orderId, idempotencyKey)` runs the whole cancellation inside one
transaction boundary. The refund call is the only step that leaves the process, so it is ordered
*first among side effects* and its outcome gates everything else: no status write, no inventory
release, no event emission happens until the provider returns a definitive success. On any
non-success the transaction rolls back and the method returns a `RefundFailed` result the API
layer renders as a retry-able 503 ("refund failed, try again") — never a partial 200.

## Failure paths handled
| Path | Detection | Behaviour |
|---|---|---|
| Provider 5xx / explicit decline | non-2xx response from refund client | roll back, order stays `paid`, retry-able error, alert |
| Provider timeout / connection reset | client timeout with no response body | roll back, order stays `paid`, retry-able error, **plus** reconciliation job enqueued — a timeout does not mean the refund didn't happen (spec: provider "does not guarantee that a timeout means the refund did *not* happen) |
| Refund succeeded, inventory release failed | release call throws inside the same boundary | compensate by voiding/reversing the refund via the provider; if compensation also fails, halt and alert loudly — this is the half-applied state the spec forbids |
| Charge not settled yet | provider rejects refund-against-unsettled-charge | refuse cancellation with a distinct non-retry-able message; do not retry blindly |
| Concurrent ship during cancel | optimistic lock / version check on order row at commit | cancel loses, transaction aborts, customer routed to Returns |

## Guards installed (condition → on violation)
1. **Atomicity guard** — post-commit consistency check compares refund state to reservation state.
   Violation → halt, leave order `paid`, alert. Never leave a half-applied cancellation.
2. **Idempotency guard** — cancellation idempotency key checked *before* any provider call, and
   passed through to the provider (which is not idempotent by default). Violation → refuse the
   duplicate, return the existing cancellation state; if the same key arrives with different
   parameters, refuse **and** alert.
3. **Refund-bound guard** — read prior-refund totals from the provider, assert
   `refund ≤ total − already_refunded` before issuing. Violation → refuse, never issue the call,
   alert. Because prior-refund totals are not immediately consistent after a write, a stale read
   can only ever make this bound tighter, never looser; ties are refused, not rounded through.
4. **Status-transition guard** — only `paid`/`processing` → `cancelled` is permitted. Violation →
   refuse the transition and alert; never force the target status.

Each guard refuses or halts. None of them logs and continues.

## Testing the failure path
Deliberately induced provider failure (fake client returning 5xx, and a separate one that hangs
past the timeout) — pinned clock and pinned provider-assigned identifiers, money as minor-unit
integers. Assert order status is still `paid`, no reservation released, error is retry-able.
