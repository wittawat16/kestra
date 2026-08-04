VERDICT: CHANGES_REQUESTED

Review of `src/reversals/service.js` against AC-4 and the spec sections it depends on
(EC-1, EC-4, EC-5, EC-10, Runtime Invariants, Reversal State Machine, Reality Constraints).

| Sev | Finding | file:line |
|---|---|---|
| blocking | Timeout is swallowed into the same `catch` as a decline and returned as `retryable: true`. The provider explicitly **does not guarantee that a timeout means the reversal did not happen** (Reality Constraints), so this is the double-refund path EC-1 and the "`pending_verification` is never retried by any path" invariant exist to prevent. The ambiguous outcome must park in `pending_verification` keyed by the idempotency key, apply nothing, and issue no retry. | service.js:6-9 |
| blocking | The comment "provider call did not go through — nothing was applied" states as fact exactly what the dependency contract refuses to promise. It will be read as licence to retry. | service.js:7 |
| blocking | No idempotency-key uniqueness check before the provider call — violates AC-6 and the "no order is reversed twice for the same idempotency key" invariant. A duplicate key issues a second money movement. | service.js:5 |
| blocking | `computeAmount(order, scope)` derives the amount from local order state. FR/BR-2/AC-2 require the provider's own record of prior reversals; `orders.already_refunded` is demoted to a cache. | service.js:3 |
| blocking | No `amount ≤ provider_balance` assertion immediately before the call (invariant 1, AC-5). An over-balance request reaches the provider instead of being refused beforehand. | service.js:3-5 |
| blocking | Steps after the provider call are bare sequential awaits with no saga/compensation. A throw from `tax.reverse` leaves money moved with no tax reversal — breaks the "tax reversal accompanies every money reversal" invariant and AC-7/EC-4's "order left exactly as it was". | service.js:10 |
| blocking | `ledger.write` failure propagates as an ordinary exception: no `ledger_pending` state, no page-severity alert, and no zero-sum assertion on the legs (EC-10, AC-10, invariants 2 and 4). | service.js:12 |
| blocking | Loyalty failure aborts the whole reversal. EC-5/AC-8 require the reversal to proceed with the adjustment queued as a compensating job — money is unrecoverable, loyalty is not. | service.js:13 |
| blocking | No state machine. It jumps from implicit `requested` to `reversed`, skipping `validated`/`money_pending`/`money_done`/`tax_done` and every guard — violates "reversal state transitions follow the declared machine". Dual-approval codes (AC-20/EC-20) therefore issue an external call with one approval. | service.js:14 |
| blocking | `inventory.release(order.reservationId)` releases the whole reservation regardless of scope, and does not route delivered lines to `awaiting_return`. Breaks partial reversals (AC-9) and credits stock never physically received (invariant 5). | service.js:11 |
| major | No order lock, so concurrent full/per-line reversals and the backfill can interleave (EC-12, EC-22). | service.js:2-14 |
| major | Feature flag `reversals.unified` is never read, let alone pinned for the saga's lifetime (AC-28/EC-23). | service.js:1 |
| major | No customer notification is emitted (FR: one notification per reversal; Notification Matrix). | service.js:14 |

AC-4 verdict specifically: **not met.** The AC's "left exactly as it was" holds only for an
explicit provider decline. This implementation applies the same handling to a timeout, where the
order may in fact have moved money, and hands the customer a retry button over it.

Smallest correct shape: classify the provider outcome into confirmed / declined / ambiguous;
`refused` for declined, `pending_verification` (no retry, no downstream effect) for ambiguous;
and run everything after the money leg inside the saga helper with named compensations, noting
`src/lib/saga/` has never carried a non-compensable step (Risks & Watch-outs).
