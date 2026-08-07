# TKT-9 — implementation notes: provider-failure handling on reversal

Scope: the `money_pending` transition in `src/reversals/service.js`, plus the ambiguous-outcome
surface in `src/payments/provider-client/index.js`. AC-4 only.

## The split AC-4 hides

AC-4 says "the call fails → order unchanged, retry-able error". The spec's EC-1 and the state
machine say a **timeout is not a failure** — the provider does not guarantee that a timeout means
the reversal did not happen. So the provider call has three outcomes, not two, and only two of them
are AC-4's:

| Outcome | State | Order | Customer sees |
|---|---|---|---|
| Explicit decline / 4xx | `refused` (terminal) | untouched | retry-able error |
| Transport error with no request issued (connect refused, DNS, pre-flight) | `refused` | untouched | retry-able error |
| Timeout / ambiguous (5xx after send, socket cut mid-flight) | `pending_verification` | untouched | **"we're confirming this"** — not retry-able |

Presenting the third case as retry-able is how a double refund happens; the reconciler
(`jobs/reconcile/pending-verification.js`) owns it from there.

## Failure paths handled

1. **Pre-call refusal** — balance/scope/window/currency guards run before the provider is touched,
   so the common failure never reaches the provider at all.
2. **Provider declines** — record the provider's own reason on the reversal, transition to
   `refused`, no downstream effect, one customer notification with reason.
3. **Provider ambiguous** — persist `pending_verification` keyed by the idempotency key *before*
   returning, notify finance (not the customer per the notification matrix), issue no retry.
4. **Persistence fails after an ambiguous provider outcome** — cannot lose the key; write the
   reversal row inside the same transaction that issues the call's audit record, and fail the
   request closed with a page-severity alert rather than returning success.

## Guards

| Guard | Detects | On violation |
|---|---|---|
| Balance bound `amount ≤ provider_balance`, read in this request | over-reversal before any call | refuse + alert, call never issued |
| Idempotency-key uniqueness, checked before any external call | duplicate request | return existing record; alert if same key + different params |
| No-retry guard in **both** the retry worker and the request handler | any path attempting to re-issue a `pending_verification` reversal | refuse + alert |
| State-transition guard on the declared machine | forcing `money_pending` → `money_done` without a provider record in the same response | refuse the transition + alert |
| Zero-downstream assertion on the `refused` branch | tax/stock/loyalty/ledger touched on a failed money leg | halt; the order must be byte-identical to its pre-request state |
| Flag value pinned at saga start | `reversals.unified` flipping mid-flight | saga completes on the start-time value |

Not in this ticket: the reconciler itself (EC-1's resolution), `ledger_pending` (EC-10 — that path
is post-success), and the fraud-hold deferral (EC-15).
