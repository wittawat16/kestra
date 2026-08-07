# TKT-9 — provider-failure handling on reversal (AC-4)

## The distinction the AC hides
AC-4 says "the provider's reversal call fails". The provider contract says a **timeout does not mean
the reversal did not happen**. So "fails" is two outcomes, not one, and only one of them is
retry-able:

| Provider outcome | State | Order | Customer |
|---|---|---|---|
| Explicit decline (settled response, no reversal record) | `money_pending → refused` | untouched | retry-able error |
| Timeout / ambiguous (no settled response) | `money_pending → pending_verification` | untouched | "we're confirming this" — **not** retry-able |
| Connection refused before the request was sent | `refused` | untouched | retry-able |

Treating a timeout as a decline is how double refunds happen; treating a decline as ambiguous parks
work that never needed parking. The branch is on *whether the request was provably not applied*, not
on whether an exception was thrown.

## Ordering that makes "left exactly as it was" true by construction
The money leg runs **first** in the saga, before tax/stock/loyalty/ledger. Nothing downstream has
been applied when the provider branch is reached, so "leave the order as it was" is the absence of
work rather than a compensation — which matters because the money leg is the one saga step that
cannot be compensated. The only writes on this path are to `reversals`/`reversal_lines` (the reversal
record's own state) and the audit row; the order and its lines are not touched.

## Guards

| Guard | Condition detected | On violation |
|---|---|---|
| Balance bound, immediately pre-call | `amount > provider_balance`, read in this same request | refuse + alert; call never issued |
| Idempotency-key uniqueness, pre-call | key already present | return existing record; if same key with different params → refuse + alert |
| No-retry on `pending_verification` | any retry worker or request handler touching a reversal in that state | refuse + alert — enforced in *both* places, since a guard only in the worker leaves the API path open |
| State-transition guard | transition not in the declared machine (e.g. `pending_verification → money_pending` without a matching reconciler record) | refuse the transition + alert; never force the target state |
| Refusal is terminal | a settlement/record arriving for an already-`refused` reversal | refusal stands, record the observation; the customer re-requests |
| Unrecognised provider record | reconciler sees a provider reversal the ledger never saw | alert at page severity; adopt nothing automatically |

None of these logs-and-continues; each one either refuses the operation or pages someone.

## Reconciler (closes the ambiguous case)
`jobs/reconcile/pending-verification.js` re-queries by idempotency key: record found and matching →
`money_done`, saga resumes at the tax leg; nothing found after the window → `refused`, terminal.
Target is 15 min. The reconciler is the *only* path out of `pending_verification`.

## Client contract
Decline and pre-send failure return a retry-able error carrying the reason. `pending_verification`
returns 202 with the reversal id and an explicitly non-retry-able marker, so a client that retries on
error doesn't reissue an unknown-outcome payment. Finance is notified on entry (customer is not);
customer is notified only when it resolves as done.

## Test notes
Clock and provider ids pinned; provider latency floating but the timeout path exercised explicitly —
an unexercised timeout path is exactly the one that ships wrong.
