# TKT-9 — provider-failure handling on reversal (AC-4)

## Scope
The `money_pending` branch of the saga in `src/reversals/service.js`, plus the outcome
classification exposed by `src/payments/provider-client/index.js`. Depends on TKT-3 (entry point)
and TKT-5 (reversible balance).

## The one distinction everything hangs on
The provider client must return a **three-valued** outcome, not a boolean: `confirmed`,
`declined`, `unknown`. AC-4 ("left exactly as it was, retry-able error") is the `declined` path
only. A timeout is `unknown`, and per EC-1 / the state machine it goes to `pending_verification`
with no retry from any path — collapsing it into "failed" is how double refunds happen. The
provider explicitly does not guarantee that a timeout means the reversal did not happen.

## Paths
| Outcome | Transition | Downstream effects | Customer sees |
|---|---|---|---|
| provider confirms (record present in same response) | `money_pending → money_done` | continue saga | — |
| provider declines | `money_pending → refused` (terminal, carries failing guard) | none applied | retry-able error; a retry is a **new** reversal with a new idempotency key |
| provider times out / connection lost | `money_pending → pending_verification` | none applied | "we're confirming this" — not an error, not a retry prompt |
| provider 4xx on a malformed request | `refused` | none | non-retry-able error |

"Retry-able" means the customer may submit a fresh request; it never means this record is retried
in place. EC-13 stands: if the charge later settles, the refusal is not resurrected.

## Guards
| Guard | Condition detected | On violation |
|---|---|---|
| Balance bound (pre-call) | `amount > provider_balance` read in this same request | refuse + alert, provider call never issued (AC-5, EC-2) |
| Idempotency-key uniqueness (pre-call) | key already present | return existing record; alert if same key with different params (EC-6) |
| No-retry on `pending_verification` | retry worker or request handler touching a record in that state | refuse the retry + alert — asserted in **both** places, not just the worker |
| State-transition guard | any transition not in the declared machine | refuse the transition + alert; never force the target state |
| No-partial-effect | any tax/stock/loyalty/ledger call attempted while state ≠ `money_done` | halt; the order must be byte-identical to its pre-request form (AC-4) |
| Outcome classification | client returns a two-valued result, or `unknown` mapped to `declined` | fail closed at the boundary — treat as `unknown` and park |

## Rollback semantics
There is nothing to compensate on the decline path: money is the first leg, so a decline means no
effect has been applied yet and "leave the order as it was" is achieved by *not* having started.
The saga helper in `src/lib/saga/` assumes every step is reversible — the money step must be
registered as non-compensatable so the helper never invents a rollback for it.

## Persistence
The reversal record is written in `requested`/`validated`/`money_pending` before the provider call,
so a crash mid-call leaves a `money_pending` row the reconciler can find and move to
`pending_verification` rather than an invisible in-flight call.

## Tests this needs
Pinned clock, pinned provider ids; the timeout path exercised explicitly (floating latency, forced
timeout) to prove parking-not-retrying; a decline case asserting zero rows written to tax, stock,
loyalty, and ledger.

## Open
`refused` is terminal in the state machine while AC-4 says "retry-able error" — resolved above as
retry = new request, but worth confirming with the spec author before freezing tests.
