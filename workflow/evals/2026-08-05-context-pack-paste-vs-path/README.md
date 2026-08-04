# 2026-08-05 — context pack: full paste vs. path-only

Tests the load-bearing claim in PR #4's มติ 3: that a spawn which is *told where* `0-spec.md` is
will read it when it needs to, so pasting the whole spec into every pack is avoidable cost.

`kestra-run`'s current rule pastes `source_spec` verbatim into every spawn, on the reasoning that
"can read" and "will read" are different things and the gap fails silently. This eval asks whether
that reasoning still holds on a current model.

## Design

**Probe — natural, not planted.** `order-cancellation-refund/0-spec.md` already states, in the
Reality Constraints "does **not** guarantee" column and nowhere else:

> That a refund call is idempotent by default; that prior-refund totals are immediately consistent
> after a write; **that a timeout means the refund did *not* happen**

That last clause decides whether an implementation is correct: treating a provider timeout as
"refund failed, safe to retry" double-refunds the customer. It appears in no AC, no business rule,
and no edge case — so a ticket brief sliced from AC-4 ("refund call fails → order stays `paid`,
customer sees a retry-able error") carries no trace of it. Nothing was added to the spec for this
eval; the file is used as it stands in the repo.

**Arms**

| Arm | Pack contents |
|---|---|
| A — paste | ticket brief + full `0-spec.md` text pasted verbatim (today's rule) |
| B — path | ticket brief + the spec's path and one line saying it can be read (มติ 3's rule) |

**Stages** — `implement-backend` (the case มติ 3 argues is safest to narrow) and `review` (the case
that needs the whole picture). If B holds on implement but fails on review, the answer is a
per-stage rule rather than a blanket one.

**Reps** — 3 per arm per stage, 12 spawns total. Whether a spawn opens a file it was merely told
about is plausibly stochastic; n=1 cannot separate a tendency from a coin flip.

**Deliverable per spawn** is a short markdown artifact, not real code: the spec's own Files-to-Touch
section says it is illustrative and not wired to a real codebase, so no implementation could compile
regardless. The probe is about which constraints reach the output, which a plan states as plainly as
code would.

## Measured

1. **Did it read?** — whether the transcript shows a Read of `0-spec.md`. Descriptive only.
2. **Did the timeout-ambiguity constraint reach the output?** — the actual verdict. Graded on
   whether the artifact treats a provider timeout as an ambiguous outcome requiring reconciliation
   or an idempotency key, versus assuming it means no refund occurred.
3. Tokens and wall-clock per arm.

Measure 2 is the one that decides anything. A spawn can open the file and still miss the clause;
reading is a means, not the property under test.

## Known limits

**Both arms are handed their pack as a file to read**, identically, rather than pasted into the
spawn prompt — arm A's pack is ~11k characters and inlining it would cost that much context per
spawn on the orchestrator side too. The confound is that having just read one file makes reading a
second one marginally more likely. It applies to both arms equally, and it biases *toward* arm B
succeeding, which is the safe direction: an arm B failure under a bias favouring it is a stronger
result than one under neutral conditions.


Answers for one model on one spec. `workflow.yaml` is frozen and portable — it may execute later on
a different model — so even a clean sweep for arm B argues for a model-conditional rule, not an
unconditional one. Stated here so a positive result isn't over-read later.
