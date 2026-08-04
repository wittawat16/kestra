VERDICT: CHANGES_REQUESTED

Reviewed `src/orders/cancellation.js` against the ticket brief and `workflow/runs/order-cancellation-refund/0-spec.md`
(Runtime Invariants, Reality Constraints, Edge Cases). The stated AC for TKT-4 is met on the *narrow*
reading — a thrown refund error leaves status `paid` and is marked retryable — but the surrounding
guarantees the spec attaches to that same path are not.

| Severity | Claim | file:line |
|---|---|---|
| Blocking | Timeout treated as "refund did not happen". Spec's provider row explicitly says a timeout does **not** guarantee the refund failed; marking every failure `retryable: true` invites a double refund on retry. | cancellation.js:34-36 |
| Blocking | No idempotency key on the cancellation request. Invariant 2 requires one checked *before* any provider call; nothing here prevents a second refund for the same cancellation. | cancellation.js:32-33 |
| Blocking | No atomicity between refund, inventory release, and status write. If `inventory.release` or `orders.setStatus` fails after a successful refund, the order is left refunded-but-`paid` — the exact half-cancelled state Invariant 1 and BR-3 forbid. No transaction/saga, no post-commit consistency check, no alert. | cancellation.js:33-39 |
| Blocking | Refund bound never asserted. Invariant 3 requires computing from the provider's prior-refund record and asserting `refund ≤ total − already_refunded` before issuing. Code trusts local `order.alreadyRefunded` and issues whatever subtraction yields — negative or over-balance amounts reach the provider. | cancellation.js:31 |
| High | Already-cancelled order is not a no-op. Spec requires returning the existing cancellation state; this throws `ORDER_NOT_CANCELLABLE`, indistinguishable from the shipped-order rejection. | cancellation.js:28-30 |
| High | No concurrency guard on the cancel-vs-ship race. Status is read, then written unconditionally with no optimistic lock/version check, so a shipment landing mid-flight loses — spec says ship must win. | cancellation.js:27,39 |
| Medium | Unsettled-charge rejection is misreported. Provider only refunds settled charges; that permanent rejection is surfaced as `REFUND_FAILED { retryable: true }`, sending the customer into an unbounded retry. | cancellation.js:34-36 |
| Medium | Original provider error is discarded — no `cause`, no alert. Invariants 1-3 all specify alerting on violation; nothing here is observable to an operator. | cancellation.js:35-36 |
| Low | Money units unverified. Spec says confirm minor-unit integers against the SDK; `order.total - order.alreadyRefunded` assumes matching units with no validation. | cancellation.js:31 |
| Low | Comment restates the code and the throw below it. | cancellation.js:35 |

Smallest correct shape: idempotency key checked first, already-cancelled short-circuit returning
existing state, provider-sourced balance assertion, refund + release + status under one
transaction/saga with compensation, and failure classification that distinguishes
permanent-reject (not retryable) from timeout (unknown outcome — reconcile, do not blind-retry).
