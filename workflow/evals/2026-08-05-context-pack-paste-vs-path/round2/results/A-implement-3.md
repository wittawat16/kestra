# TKT-9 — implementation notes: provider-failure handling on reversal

Scope: the `money_pending` step of the reversal saga in `src/reversals/service.js`, plus the
outcome typing it needs from `src/payments/provider-client/index.js`. Depends on TKT-3 (entry
point) and TKT-5 (reversible balance).

## Shape

The provider call returns a three-valued outcome, not a boolean: `confirmed` (provider record
present in the same response), `declined` (provider answered "no"), `ambiguous` (timeout,
connection reset, 5xx, or any response we cannot parse). The client today collapses the last two;
splitting them is the whole ticket. Keep the existing error shape for the capture path — that file
is shared with checkout — by adding the outcome as a new field rather than changing thrown errors.

`declined` → `refused`, terminal, nothing downstream applied, order untouched, customer sees a
retry-able error (the request may be re-submitted with a *new* idempotency key). `ambiguous` →
`pending_verification`, parked on the idempotency key, no downstream effect, no retry from any
path; `jobs/reconcile/pending-verification.js` re-queries and settles it to `money_done` or
`refused`. AC-4 is the `declined` branch; EC-1 is the `ambiguous` branch, and the distinction is
load-bearing because the provider does not guarantee that a timeout means the reversal did not
happen.

Ordering: money is the first externally-visible leg, so on `refused` there is nothing to
compensate — tax, stock, loyalty, ledger, and notification have not run. That is what makes "left
exactly as it was" cheap rather than a compensation problem. The saga helper in `src/lib/saga/`
assumes every step is reversible; the money step is registered with an explicit
`compensate: null` and the runner must refuse to schedule a compensation for it rather than
silently no-op.

## Guards

| Guard | Condition detected | On violation |
|---|---|---|
| Balance bound | `amount > provider_balance`, read in the same request, asserted immediately before the call | Refuse and alert; the call is never issued (AC-5, EC-2) |
| Ambiguity classifier | Provider outcome is not one of the three known values | Treat as `ambiguous` and park — fail closed, never as `declined` |
| No-retry on `pending_verification` | A retry worker or a request handler targets a reversal in `pending_verification` | Refuse the retry and alert; retrying an unknown-outcome payment is how double refunds happen |
| Idempotency-key uniqueness | Key already present before any external call | Return the existing record; alert if the same key arrives with different parameters (EC-6) |
| State-transition guard | Any transition not in the declared machine (e.g. `refused` → anything) | Refuse the transition and alert; never force the target state — covers EC-13, where a late settlement must not resurrect a refusal |
| Untouched-order assertion | After a `refused` outcome, any downstream effect recorded for this reversal | Alert at page severity; this means the saga leaked past its first step |

## Failure paths not in this slice, but which this slice must not break

Tax unavailable (EC-4 / AC-7) and ledger-write failure (EC-10) both live after `money_done`, so
they are out of scope here — but the `ambiguous` park must not be reachable from them, and the
`ledger_pending` marker must not be confused with `pending_verification`. Notification is fired
once per reversal, including on `refused`, and its delivery receipt never gates completion (EC-19).

## Determinism for the eventual tests

Clock, provider ids, and FX rates pinned; provider latency floating with the timeout path
exercised explicitly, since EC-1 can only be proven by an actually-ambiguous call.
