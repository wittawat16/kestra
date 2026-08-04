# [order-lifecycle-reversals] Spec — cancellation, returns, and partial reversals

> Status: READY_FOR_BUILD | Created: 2026-08-05 | Next: kestra-build

---

## Overview
One reversal engine behind customer cancellation, agent-initiated returns, and partial line-item
refunds, so money movement, stock movement, tax reversal, and loyalty adjustment stay consistent
with each other across every path that can undo part or all of an order.

## Problem Statement
* Cancellation, returns, and support credits each move money through their own code path today.
  Three implementations of "how much can we give back" have drifted; two of them read the local
  `orders.already_refunded` column, one reads the provider, and they disagree during settlement.
* Tax reversal runs nightly from a report rather than at reversal time, so a same-day cancel and
  re-purchase produces a tax filing entry that nets to the wrong jurisdiction.
* Loyalty points are deducted on cancel but not on partial refund, which support has been fixing by
  hand at roughly forty tickets a month.
* Goal: one reversal path, one source of truth for reversible balance, and every downstream effect
  (tax, loyalty, stock, ledger, notification) either applied together or not at all — with every
  divergence detected at reversal time rather than by month-end reconciliation.

## Functional Requirements
* [ ] A reversal request names an order, a reason code, and either a full-order scope or an explicit
  set of line items with quantities.
* [ ] Customers may self-service full cancellation of unshipped orders and per-line returns of
  delivered orders inside the returns window; agents may do either at any time with a reason code
  from the agent-only set.
* [ ] Every reversal computes its money amount from the payment provider's own record of prior
  reversals, never from a locally cached total.
* [ ] Reserved stock is released for unshipped lines; delivered lines move to `awaiting_return` and
  only re-enter available stock on warehouse receipt.
* [ ] Tax is reversed proportionally per line at the rate recorded on the original invoice, not the
  rate current at reversal time.
* [ ] Loyalty points earned on reversed value are clawed back; points already spent produce a
  negative balance rather than a refusal.
* [ ] Every reversal writes one double-entry ledger transaction whose legs sum to zero.
* [ ] A reversal that cannot complete every downstream effect leaves the order exactly as it was.
* [ ] Customers receive one notification per reversal, never one per downstream effect.
* [ ] Multi-currency orders reverse in the order's original currency at the original captured rate.

## Edge Cases & Error States
* **EC-1 — Payment provider timeout on the reversal call:** the outcome is unknown, not failed. The
  reversal is parked in `pending_verification` keyed by the idempotency key and a reconciler
  re-queries; no downstream effect is applied and no retry is issued until the re-query settles it.
* **EC-2 — Partial reversal exceeding the remaining reversible balance:** refused before any
  provider call, with the computed remaining balance in the error.
* **EC-3 — Reversal of a line that is mid-shipment:** the shipment wins; the line is rejected with a
  pointer to the returns flow, and the rest of the requested lines proceed.
* **EC-4 — Tax service unavailable:** the whole reversal is refused. A money movement without its
  matching tax reversal is a filing defect, so this is not a degrade-and-continue case.
* **EC-5 — Loyalty service unavailable:** the reversal proceeds and the loyalty adjustment is queued
  as a compensating job, because loyalty is recoverable after the fact and money is not.
* **EC-6 — Duplicate reversal request with the same idempotency key:** returns the existing reversal
  record; a same key with different parameters is refused and alerted.
* **EC-7 — Order already fully reversed:** no-op returning the existing terminal state.
* **EC-8 — Warehouse receives a returned line that was never marked `awaiting_return`:** accepted
  into stock, flagged for manual review; refusing physical goods already in the building helps
  nobody.
* **EC-9 — Currency rate missing for a historical order:** refused; reversing at today's rate would
  silently move money between the customer and the business.
* **EC-10 — Ledger write fails after a successful provider reversal:** the money has moved and
  cannot be un-moved, so the reversal is marked `ledger_pending` and alerted at page severity; it is
  never rolled back and never silently dropped.
* **EC-11 — Reason code retired between request creation and processing:** processed under the code
  as it existed at request time.
* **EC-12 — Concurrent full-order and per-line reversal:** the first to acquire the order lock wins;
  the second re-reads and either refuses (nothing left) or proceeds on the remainder.

* **EC-13 — Provider settles a charge after the reversal was refused as unsettled:** the refusal
  stands; the customer must re-request. Auto-resurrecting a refused reversal would move money on a
  request nobody re-confirmed.
* **EC-14 — Reversal spanning lines in two currencies:** refused; split into one reversal per
  currency so each carries a single captured rate.
* **EC-15 — Order reversed while a fraud hold is active:** the money leg is deferred to the hold's
  resolution; stock and tax still apply, because holding stock hostage to a fraud review costs the
  business more than the disputed amount.
* **EC-16 — Warehouse receipt arrives for a line already credited by a prior receipt:** the second
  receipt is recorded but credits nothing, and is flagged; duplicate physical scans are common.
* **EC-17 — Reversal request references a line id from a different order:** refused with both order
  ids named, and alerted — this pattern is either a client bug or an enumeration attempt.
* **EC-18 — Ledger read-after-write returns the pre-write state:** the reversal does not treat the
  absence as a failed write; it re-reads after the dependency's stated consistency delay before
  concluding anything.
* **EC-19 — Notification service returns a delivery receipt for a notification never sent:** ignored;
  delivery receipts are advisory and never gate a reversal's completion.
* **EC-20 — Reason code requires dual approval and only one approval is present:** parked in
  `awaiting_approval`, no external call issued, expiring after 72 hours.
* **EC-21 — Loyalty clawback would exceed a configured negative floor:** clamped to the floor and
  flagged; an unbounded negative balance has repeatedly turned into a support escalation.
* **EC-22 — Backfill and a live reversal touch the same order concurrently:** the live reversal wins
  the lock; the backfill skips and re-queues the order.
* **EC-23 — Feature flag `reversals.unified` flips mid-saga:** the saga completes under the flag
  value read at its start; re-reading mid-flight would produce a half-old, half-new reversal.
* **EC-24 — Provider returns a reversal record the ledger has never seen:** treated as a real money
  movement that this system failed to record, alerted at page severity, never silently adopted.

## Runtime Invariants
*(must hold every time this runs — a violation halts, refuses, or alerts; never proceeds silently.)*
| Invariant — what must be true | Detected at runtime by | On violation |
|---|---|---|
| Reversed money never exceeds the provider's remaining reversible balance | Assert `amount ≤ provider_balance` immediately before the provider call, using a value read in the same request | Refuse and alert; never issue the call |
| Money movement and ledger entry are never separated for longer than the reconciler window | Post-commit check comparing provider reversal records to ledger transactions, plus the `ledger_pending` marker | Alert at page severity; the reversal stays visibly incomplete rather than being marked done |
| Tax reversal accompanies every money reversal | Transaction boundary spanning the tax call and the reversal record | Halt the reversal; leave the order untouched |
| A ledger transaction's legs sum to zero | Assert on the transaction before commit | Refuse the write and alert — an unbalanced ledger is unrecoverable downstream |
| Stock is never credited for a line that has not been physically received | Guard on the receipt event's provenance (warehouse scan id required) | Refuse the stock credit and alert |
| No order is reversed twice for the same idempotency key | Key uniqueness check before any external call | Refuse the duplicate, return the existing record; alert if the key was reused with different parameters |
| Reversal state transitions follow the declared machine | Guard on every transition | Refuse the transition and alert rather than forcing the target state |
| A `pending_verification` reversal is never retried by any path | Guard in the retry worker and in the request handler | Refuse the retry and alert — retrying an unknown-outcome payment is how double refunds happen |

## Business Rules  *(needs_ba: true)*

* **BR-1 — Self-service scope is bounded by fulfilment state.**
  ```
  Given an order with no shipped lines
  When the customer requests a full reversal
  Then it is accepted as a cancellation
  ```
  ```
  Given an order with at least one delivered line
  When the customer requests a full reversal
  Then the unshipped lines cancel and the delivered lines are offered as returns instead
  ```

* **BR-2 — Reversible balance comes from the provider, never from local state.**
  ```
  Given an order of 120.00 with a 30.00 prior support credit recorded at the provider
  When a full reversal is requested
  Then 90.00 is reversed
  ```
  ```
  Given the same order whose local already_reversed column still reads 0.00
  When a full reversal is requested
  Then it is still 90.00 that is reversed, and the local column is corrected
  ```

* **BR-3 — Tax reverses at the invoice rate, not today's rate.**
  ```
  Given a line invoiced at a 7% rate that has since changed to 8%
  When that line is reversed
  Then the tax reversed is 7% of the line value
  ```
  ```
  Given a line whose jurisdiction no longer exists at reversal time
  When that line is reversed
  Then the original jurisdiction code is used and the reversal is flagged for filing review
  ```

* **BR-4 — Loyalty clawback may go negative.**
  ```
  Given a customer with 50 points who earned 200 on the reversed order
  When the reversal completes
  Then the balance becomes -150 and future earnings offset it first
  ```
  ```
  Given a customer whose points were earned on a different order
  When this reversal completes
  Then only points attributable to reversed lines are clawed back
  ```

* **BR-5 — Partial reversals are line-scoped and quantity-scoped.**
  ```
  Given a line of quantity 3 at 20.00 each
  When 1 unit is reversed
  Then 20.00 plus its proportional tax reverses and the line remains open at quantity 2
  ```
  ```
  Given the same line
  When 4 units are requested
  Then the request is refused before any external call
  ```

* **BR-6 — Agent reversals carry an auditable reason.**
  ```
  Given an agent-initiated reversal with reason code goodwill_credit
  When it completes
  Then the agent id, reason code, and free-text justification are recorded immutably
  ```
  ```
  Given an agent-initiated reversal with a customer-only reason code
  When it is submitted
  Then it is refused with the allowed agent codes listed
  ```


* **BR-7 — Returns window is per line, measured from that line's delivery date.**
  ```
  Given a two-line order delivered 20 and 40 days ago with a 30-day window
  When the customer requests a return of both lines
  Then the first line is accepted and the second is refused as out of window
  ```
  ```
  Given a line never marked delivered
  When a return is requested
  Then it is refused as not-yet-delivered rather than out-of-window
  ```

* **BR-8 — Shipping is refunded only when the whole order reverses.**
  ```
  Given a full-order reversal
  When it completes
  Then the shipping charge reverses with it
  ```
  ```
  Given a partial line reversal
  When it completes
  Then shipping is untouched, because the parcel still shipped
  ```

* **BR-9 — A promotion applied across lines reverses proportionally.**
  ```
  Given a 10.00 discount spread across three lines of equal value
  When one line reverses
  Then 3.33 of discount reverses with it and the remaining discount stays at 6.67
  ```
  ```
  Given a discount tied to a single line
  When a different line reverses
  Then the discount is untouched
  ```

* **BR-10 — Gift-card tender reverses to the gift card, never to a card.**
  ```
  Given an order paid 40.00 by gift card and 60.00 by card
  When a 50.00 reversal occurs
  Then 40.00 returns to the gift card and 10.00 to the card
  ```
  ```
  Given an expired gift card
  When its portion would reverse
  Then a replacement card is issued for that value rather than moving it to the card
  ```

* **BR-11 — Marketplace-seller lines reverse against the seller's balance.**
  ```
  Given a line sold by seller S
  When it reverses
  Then the ledger debits S's balance and the platform's commission leg reverses proportionally
  ```
  ```
  Given a seller whose balance is insufficient
  When the line reverses
  Then the platform funds the reversal and records a receivable against the seller
  ```

* **BR-12 — Reversal reasons drive downstream reporting, not behaviour.**
  ```
  Given two reversals of identical scope with different reason codes
  When both complete
  Then their money, tax, stock, and ledger effects are identical
  ```
  ```
  Given a reason code in the fraud family
  When the reversal completes
  Then the only difference is that the fraud team receives a notification
  ```

* Stakeholder variations: finance may reverse outside the returns window with dual approval;
  marketplace-seller orders route the money leg to the seller's balance rather than the platform's,
  which changes the ledger legs but no other rule.

## Reality Constraints

### External dependencies
| Dependency | Enforced ordering / preconditions | Types & shapes actually returned | Does **not** guarantee |
|---|---|---|---|
| Payment provider | Reversal only against a settled charge; a charge settles asynchronously after capture | Provider-native ids as opaque strings; money as minor-unit integers; balances as a list of prior reversal records | That a reversal call is idempotent by default; that balances are immediately consistent after a write; **that a timeout means the reversal did not happen** |
| Tax service | Invoice must exist before its reversal; reversals must arrive in invoice order per jurisdiction | Rates as decimal strings, jurisdiction as an opaque code | That a rate looked up today matches the rate recorded on an old invoice; that a jurisdiction code still resolves |
| Inventory service | Reservation must exist before release; releasing twice is an error | Reservation ids and quantities as the service defines them | That release is synchronous; that released quantity is immediately visible as available |
| Warehouse events | A receipt event follows a physical scan | Scan id, line id, quantity, timestamp | That events arrive in order; that a receipt is not replayed; that every returned parcel produces exactly one event |
| Loyalty service | Account must exist before adjustment | Points as signed integers | That an adjustment is idempotent; that a negative balance is accepted without a follow-up call |
| Ledger | Transactions are append-only; a transaction is immutable once written | Transaction id, legs as signed minor-unit integers | That a write is retryable after an ambiguous failure; that reads immediately reflect a just-committed write |
| Notification service | None | Delivery receipt id | That a notification was delivered, or delivered once |
| FX rate store | Rate must exist for the order's capture date | Rate as a decimal string with 6 places | That historical rates are present for orders older than 24 months |

### Paths that must agree
* Customer self-service reversal ↔ agent-initiated reversal — equivalent means: identical money,
  tax, ledger, and stock effects for the same scope · may differ: permitted reason codes, whether
  the returns window is enforced, and who appears in the audit record.
* Live reversal ↔ nightly reconciler's replay of the same reversal — equivalent means: same ledger
  legs and same final reversal state · may differ: timestamps and the reconciler's own audit rows.

### Non-deterministic inputs
| Input | Pinned or floating in tests | Why |
|---|---|---|
| Clock | pinned | Returns-window and settlement checks are time-relative |
| Provider-assigned identifiers | pinned | Assertions must not depend on per-call generated values |
| FX rates | pinned | A floating rate makes money assertions non-reproducible |
| Provider latency / timeout | floating, but the timeout path must be exercised explicitly | EC-1 requires proving an unknown outcome is parked rather than retried |
| Warehouse event ordering | floating, with an explicit out-of-order case | The dependency does not promise ordering |


## Reversal State Machine
| From | Event | To | Guard |
|---|---|---|---|
| `requested` | validation passes | `validated` | scope resolvable, balance sufficient, window satisfied |
| `requested` | validation fails | `refused` | terminal; carries the failing guard's name |
| `validated` | dual approval required | `awaiting_approval` | reason code in the dual-approval set |
| `awaiting_approval` | second approval | `money_pending` | approver differs from requester |
| `awaiting_approval` | 72h elapsed | `expired` | terminal |
| `validated` | no approval required | `money_pending` | — |
| `money_pending` | provider confirms | `money_done` | provider record present in the same response |
| `money_pending` | provider declines | `refused` | terminal; nothing downstream applied |
| `money_pending` | provider times out | `pending_verification` | **no retry from any path** |
| `pending_verification` | reconciler finds record | `money_done` | record matches idempotency key |
| `pending_verification` | reconciler finds none after window | `refused` | terminal |
| `money_done` | tax reversed | `tax_done` | invoice-rate lookup succeeded |
| `money_done` | tax unavailable | `compensating` | money leg reversed back if still possible |
| `tax_done` | stock + loyalty + ledger applied | `reversed` | ledger legs sum to zero |
| `tax_done` | ledger write fails | `ledger_pending` | alert at page severity; never rolled back |
| any | operator intervention | `manual_review` | operator id recorded |

## Reason Codes
| Code | Who may use it | Dual approval | Downstream notification |
|---|---|---|---|
| `customer_changed_mind` | customer, agent | no | customer only |
| `item_not_needed` | customer, agent | no | customer only |
| `arrived_damaged` | customer, agent | no | customer, warehouse QA |
| `arrived_late` | customer, agent | no | customer, carrier ops |
| `wrong_item_sent` | agent | no | customer, warehouse QA |
| `goodwill_credit` | agent | no | customer |
| `pricing_error` | agent, finance | yes | customer, finance |
| `suspected_fraud` | agent, fraud team | yes | fraud team only |
| `chargeback_preempt` | finance | yes | finance only |
| `seller_cancelled` | marketplace ops | no | customer, seller |
| `regulatory_hold` | finance | yes | finance, legal |

## Notification Matrix
| Event | Customer | Agent | Seller | Finance |
|---|---|---|---|---|
| Reversal accepted | yes, once | no | if seller line | no |
| Reversal refused | yes, with reason | if agent-initiated | no | no |
| `pending_verification` entered | no | no | no | yes |
| `pending_verification` resolved as done | yes | no | if seller line | yes |
| `ledger_pending` entered | no | no | no | yes, page |
| Return received at warehouse | yes | no | if seller line | no |
| Loyalty clawback applied | yes, if balance goes negative | no | no | no |

## Solution Architecture  *(needs_sa: true)*
Chosen approach: A — one reversal service owning a saga per reversal, with the money leg first and
every other effect compensating.

| Approach | Pros | Cons | Verdict |
|---|---|---|---|
| A — reversal service with an explicit saga | One place to reason about ordering; compensations are named and testable; the ambiguous-payment case has somewhere to live | A new service boundary; saga state must be persisted and reconciled | chosen |
| B — distributed transaction across services | Conceptually simple | Two of the seven dependencies expose no transaction API at all | rejected — not implementable against the real dependencies |
| C — event-driven choreography | Loose coupling | No single place that knows whether a reversal finished; the invariants above become unobservable | rejected — the invariants are the point |

* Integration contracts: reversal service exposes `POST /reversals` (idempotency key required) and
  `GET /reversals/{id}`; consumes provider, tax, inventory, loyalty, ledger, notification, FX.
* Data model impact: new `reversals` and `reversal_lines` tables; `orders.already_refunded` retained
  but demoted to a cache corrected on every reversal.
* NFR targets: p99 under 4s for the synchronous path; reconciler closes any `pending_verification`
  within 15 minutes; zero tolerance for unbalanced ledger transactions.

## Codebase Survey
* Explored: `src/orders/`, `src/payments/provider-client/`, `src/inventory/`, `src/tax/`,
  `src/ledger/`, `src/loyalty/`, the nightly reconciler under `jobs/reconcile/`.
* Integrate with: the existing saga helper in `src/lib/saga/`, the provider client's existing
  idempotency-key support, and the ledger's balanced-transaction assertion helper.

## Files to Touch
| File | Change | Verified? | Why |
|---|---|---|---|
| src/reversals/service.js | new | follows pattern at src/orders/service.js | The saga and its state machine |
| src/reversals/balance.js | new | follows pattern at src/payments/amounts.js | Provider-sourced reversible balance |
| src/payments/provider-client/index.js | edit | exists | Expose prior-reversal records and the ambiguous-timeout outcome |
| src/tax/reversal.js | new | follows pattern at src/tax/invoice.js | Invoice-rate reversal |
| src/ledger/transactions.js | edit | exists | Reversal transaction shape |
| jobs/reconcile/pending-verification.js | new | follows pattern at jobs/reconcile/settlements.js | Closes EC-1 |

## Dependencies
* New tables `reversals`, `reversal_lines`; a backfill correcting `orders.already_refunded` from the
  provider; feature flag `reversals.unified` defaulting off.

## Acceptance Criteria
* [ ] **AC-1:** Given an unshipped order, when a full reversal is requested, then money, tax, stock,
  loyalty, and ledger effects all apply and the order reaches `reversed`.
* [ ] **AC-2:** Given an order with a prior provider-recorded credit, when a full reversal is
  requested, then the amount reversed is the provider's remaining balance, not the order total.
* [ ] **AC-3:** Given a line invoiced at a rate that has since changed, when it is reversed, then
  the invoice-time rate is used.
* [ ] **AC-4:** Given the payment provider's reversal call fails, when a reversal is attempted, then
  the order is left exactly as it was and the customer sees a retry-able error.
* [ ] **AC-5:** Given a reversal request that exceeds the remaining reversible balance, when it is
  submitted, then it is refused before any external call.
* [ ] **AC-6:** Given a duplicate idempotency key, when a reversal is requested, then the existing
  record is returned and no second money movement occurs.
* [ ] **AC-7:** Given the tax service is unavailable, when a reversal is attempted, then nothing is
  applied and the order is unchanged.
* [ ] **AC-8:** Given the loyalty service is unavailable, when a reversal is attempted, then the
  money and stock effects still apply and the loyalty adjustment is queued.
* [ ] **AC-9:** Given a partial line reversal of 1 of 3 units, when it completes, then the line
  remains open at quantity 2 with proportional tax reversed.
* [ ] **AC-10:** Given any completed reversal, when its ledger transaction is read, then its legs
  sum to zero.

* [ ] **AC-11:** Given a line delivered 40 days ago under a 30-day window, when a return is
  requested, then it is refused as out of window and other lines are unaffected.
* [ ] **AC-12:** Given a full-order reversal, when it completes, then the shipping charge reverses.
* [ ] **AC-13:** Given a partial line reversal, when it completes, then shipping is untouched.
* [ ] **AC-14:** Given a 10.00 discount spread across three equal lines, when one reverses, then
  3.33 of discount reverses.
* [ ] **AC-15:** Given a mixed gift-card and card tender, when a partial reversal occurs, then the
  gift-card portion is exhausted before the card is touched.
* [ ] **AC-16:** Given an expired gift card, when its portion reverses, then a replacement card is
  issued for that value.
* [ ] **AC-17:** Given a marketplace-seller line, when it reverses, then the seller's balance is
  debited and commission reverses proportionally.
* [ ] **AC-18:** Given a seller with insufficient balance, when their line reverses, then the
  platform funds it and records a receivable.
* [ ] **AC-19:** Given two reversals with different reason codes and identical scope, when both
  complete, then their ledger legs are identical.
* [ ] **AC-20:** Given a reason code requiring dual approval, when only one approval exists, then no
  external call is issued.
* [ ] **AC-21:** Given a dual-approval reversal unapproved for 72 hours, when the expiry runs, then
  it becomes `expired` and nothing was applied.
* [ ] **AC-22:** Given an approver equal to the requester, when the second approval is submitted,
  then it is refused.
* [ ] **AC-23:** Given a fraud hold on the order, when a reversal is requested, then stock and tax
  apply and the money leg defers.
* [ ] **AC-24:** Given a duplicate warehouse receipt for an already-credited line, when it arrives,
  then stock is credited exactly once.
* [ ] **AC-25:** Given a receipt event with no warehouse scan id, when it arrives, then no stock is
  credited.
* [ ] **AC-26:** Given a reversal spanning two currencies, when it is submitted, then it is refused.
* [ ] **AC-27:** Given an order older than 24 months with no stored FX rate, when a reversal is
  requested, then it is refused rather than reversed at today's rate.
* [ ] **AC-28:** Given the feature flag flips mid-saga, when the saga completes, then it used the
  value read at its start throughout.
* [ ] **AC-29:** Given a loyalty clawback that would breach the negative floor, when it applies,
  then the balance clamps to the floor and is flagged.
* [ ] **AC-30:** Given a provider reversal record the ledger has never seen, when the reconciler
  runs, then it alerts and records nothing automatically.

## AC Coverage Map
| AC | Covered by |
|---|---|
| AC-1 | src/reversals/service.js — saga happy path |
| AC-2 | src/reversals/balance.js |
| AC-3 | src/tax/reversal.js |
| AC-4 | src/reversals/service.js — provider failure branch |
| AC-5 | src/reversals/balance.js — bound assertion |
| AC-6 | src/reversals/service.js — idempotency guard |
| AC-7 | src/reversals/service.js — tax compensation |
| AC-8 | src/reversals/service.js — loyalty queue |
| AC-9 | src/reversals/service.js — line scoping |
| AC-10 | src/ledger/transactions.js |
| AC-11 | src/reversals/service.js — see AC text |
| AC-12 | src/reversals/service.js — see AC text |
| AC-13 | src/reversals/service.js — see AC text |
| AC-14 | src/reversals/service.js — see AC text |
| AC-15 | src/reversals/service.js — see AC text |
| AC-16 | src/reversals/service.js — see AC text |
| AC-17 | src/reversals/service.js — see AC text |
| AC-18 | src/reversals/service.js — see AC text |
| AC-19 | src/reversals/service.js — see AC text |
| AC-20 | src/reversals/service.js — see AC text |
| AC-21 | src/reversals/service.js — see AC text |
| AC-22 | src/reversals/service.js — see AC text |
| AC-23 | src/reversals/service.js — see AC text |
| AC-24 | src/reversals/service.js — see AC text |
| AC-25 | src/reversals/service.js — see AC text |
| AC-26 | src/reversals/service.js — see AC text |
| AC-27 | src/reversals/service.js — see AC text |
| AC-28 | src/reversals/service.js — see AC text |
| AC-29 | src/reversals/service.js — see AC text |
| AC-30 | src/reversals/service.js — see AC text |

## Risks & Watch-outs
* The backfill correcting `orders.already_refunded` reads every order's provider record; rate limits
  make a naive run take days.
* `src/payments/provider-client/index.js` is shared with the capture path; changing its error shape
  affects checkout.
* The saga helper in `src/lib/saga/` has never been used with a step that cannot be compensated
  (the money leg); its docs assume every step is reversible.

## Out of Scope
* Chargeback handling, subscription proration, and the agent UI for reversals.

## Flags
* `needs_ba`: true — six business rules with stakeholder variations.
* `needs_ui`: false — API only; the agent UI is out of scope.
* `needs_sa`: true — seven dependencies and a new service boundary.
* `needs_devops`: true — two new tables, a backfill, and a feature flag.

## Open Items
* Whether marketplace-seller reversals need dual approval like finance reversals — pending a policy
  decision.
