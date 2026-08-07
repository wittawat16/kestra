# TKT-9 — provider-failure handling on reversal (AC-4)

## Shape
Handled inside the reversal saga (`src/reversals/service.js`) at the `money_pending` step, with the
ambiguous-outcome distinction surfaced by `src/payments/provider-client/index.js`. The provider call
is the saga's one uncompensatable step, so nothing downstream (tax, stock, loyalty, ledger,
notification) is attempted until the money leg has a *known* outcome.

## Three outcomes, not two — this is the crux
AC-4 says "fails … customer sees a retry-able error". Taken literally that is wrong for one of the
three cases, so the branch is split on outcome, not on "error":

| Provider outcome | State | Order left as-was? | What the customer sees |
|---|---|---|---|
| Explicit decline (settled charge, provider says no) | `refused` (terminal) | yes | retry-able error, per AC-4 |
| Transport/5xx error with a provable no-call (request never left, connect refused) | `refused` | yes | retry-able error |
| **Timeout / ambiguous** | `pending_verification` | yes | **not** retry-able — "we're confirming this" |

The provider contract explicitly does not guarantee that a timeout means the reversal did not
happen, so a timeout is an unknown outcome, not a failure. Presenting it as retry-able is how a
double refund happens. Flagging this as a spec tension for AC-4 vs EC-1, resolved in favour of EC-1.

## Guards

| Guard | Condition detected | On violation |
|---|---|---|
| Balance bound | `amount ≤ provider_balance`, read in the same request, asserted immediately before the call | Refuse + alert; the call is never issued |
| Idempotency-key uniqueness | Key already present before any external call | Return the existing record; alert if the same key carries different parameters |
| No-retry on `pending_verification` | A retry worker or a request handler targets a reversal in `pending_verification` | Refuse the retry and alert — enforced in *both* places, not just the worker |
| State-transition guard | Any transition not in the declared machine (e.g. `pending_verification → money_pending`) | Refuse the transition and alert; never force the target state |
| Downstream-effect gate | Any tax/stock/loyalty/ledger step invoked while the money leg is not `money_done` | Halt the saga; order untouched |
| Flag pinned at saga start | `reversals.unified` re-read mid-saga | Refuse the read; the value captured at start is authoritative |

## Rollback / "left exactly as it was"
No downstream effect runs before `money_done`, so on decline there is nothing to compensate — the
order is untouched by construction rather than by unwinding. That is the only version of AC-4 that
is safe, because the saga helper in `src/lib/saga/` assumes every step is compensatable and the
money leg is not.

## Reconciler
`jobs/reconcile/pending-verification.js` re-queries by idempotency key: record found and matching →
`money_done` and the saga resumes; none found after the window → `refused` (terminal). Finance is
notified on entry to `pending_verification` and on its resolution; the customer only on resolution.
Target: closed within 15 minutes.

## Not in this ticket
Fraud-hold deferral (AC-23), ledger-write failure after success (EC-10 / `ledger_pending`), and the
provider-record-the-ledger-never-saw alert (EC-24) — adjacent, separately ticketed.
