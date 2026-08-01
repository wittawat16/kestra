# meta-dev — Sonnet 5 vs Opus 5 (2026-08-01)

**Question this was built to answer:** `meta-orc`'s Dial 1 says `meta-dev` is the *one* stage safe to
run cheaply, because `meta-qa` and `meta-review` re-check it. The two prior evals tested the stages
that must stay expensive. This one tests the claim in the other direction: does a cheaper model
actually produce worse code here?

Third in the series with `meta/evals/2026-08-01-review-model-compare/` and
`meta/evals/2026-08-01-spec-model-compare/`.

## Setup

Same spec, same starting code (`src/store.js` + `src/audit.js`), same effort, only the model varied.
Each model wrote `src/accept-invite.js` into its own directory with no sight of the other's work.

The spec is the one from the review eval — chosen because the *correct* implementation is already
known: that eval's fixture was a deliberately defective version of this exact feature, so its planted
defects become the exam. Does either model write the same bugs when implementing from scratch?

**The rubric was committed before either model ran** (`a1d1f4a`), so pass/fail could not be adjusted
to fit the output. Ten probes, all executed: both storage forms of `expiresAt`, caller-supplied role,
concurrent redemption, audit write, plus P5 as a guard against over-correcting the ISO case into
rejecting valid invites.

## Result — 10/10 for both

```
PASS P1  valid invite -> 200 + member          PASS P6  already redeemed -> 409
PASS P2  unknown token -> 404                  PASS P7  already a member -> 409
PASS P3  expired (numeric expiresAt) -> 410    PASS P8  caller role does NOT override invite role
PASS P4  expired (ISO-string expiresAt) -> 410 PASS P9  audit entry invite.accepted written
PASS P5  valid (ISO-string expiresAt) -> 200   PASS P10 concurrent accepts -> not both 200
```

Neither reproduced any of the three defects planted in the review eval. Both closed the
role-escalation hole *by construction* — neither accepted a caller-supplied role parameter at all,
which is stronger than the check the spec asked for. Both handled the dual-type `expiresAt`. Both
isolated the audit write so a failure can't roll back the membership. Both stayed inside the one
planned file and reported it.

Cost: **Sonnet 136,770 tokens / 9 tool calls / 71s. Opus 128,953 tokens / 10 tool calls / 66s.**
Opus ~6% cheaper and slightly faster — the third run in a row where the stronger model cost less.

## A bug in this grader, and why it's reported rather than quietly fixed

The pinned rubric called `acceptInvite({ body })`, copying the handler shape from the review eval's
defective fixture. **The spec never states the input shape** — it pins only the return shape
(`{ status, body }`). Both models independently chose flat arguments (`acceptInvite(token, userId)`
and `acceptInvite({ token, userId })`), which is within spec and arguably better, since it's what
removes the caller's ability to pass a role at all.

So the first run scored both 2/10 against a rubric that was wrong. The fix was a signature adapter
that detects the convention; **the ten criteria are unchanged**. The pre-run version stays in git
history at `a1d1f4a` — pinning the rubric is what made this visible as a rubric bug rather than a
model failure, which is the whole reason to pin it.

## Where they actually differed

The executable rubric was a tie, so the difference lives in what each did about the cases the spec
didn't enumerate.

**Unparseable `expiresAt`** (`nan-probe.mjs` — post-hoc, not part of the pinned rubric):

| `expiresAt` | Sonnet | Opus |
|---|---|---|
| `"not-a-date"` | **200 — invite honored** | 410 refused |
| `undefined` / `null` / `{}` | **200 — invite honored** | 410 refused |

Sonnet's `typeof x === 'number' ? x : Date.parse(x)` yields `NaN` for garbage, and every comparison
against `NaN` is false — so the expiry check *fails open* and an invite with a corrupt or missing
expiry is honored forever. Opus made `Number.isNaN` mean expired and **flagged it in its own QA
notes as an assumption the spec didn't ask for**. The spec names only the string/number pair, so
neither violates it; one fails open on a security-relevant check and the other fails closed and
says so.

**Concurrency approach.** Sonnet added an explicit per-token promise-chain lock. Opus claimed the
invite before the already-a-member check, relying on the store returning the object by reference,
and surfaced the consequence it bought: an already-a-member rejection now *spends* the invite. Every
stated AC still holds, and it named the trade as a spec question rather than deciding silently. Both
are legitimate; Opus's is the smaller diff (37 vs 49 lines) and the more consequential trade.

## What this says about Dial 1

**It supports the claim.** On everything the spec actually specified, the cheaper model was
indistinguishable — same verdict on all ten executable criteria, including the three traps. Where a
defect did appear, it was in territory the spec never covered.

But note precisely what would catch that defect. `meta-qa`'s ledger is keyed on acceptance criteria,
and no AC mentions a corrupt `expiresAt` — so QA would report a clean pass. It would fall to
`meta-review`'s judgment, reading the diff and asking what happens outside the enumerated cases. So
Dial 1's safety net does cover this, but through the judgment stage rather than the mechanical one —
which is a further reason not to economize on `meta-review`, and it lines up with what the review
eval found about where the cheaper model's ceiling actually is.

The same pattern now holds across all three evals: parity where the answer is inside the artifact,
a gap where the answer is outside it. Here "outside" is the input the spec didn't imagine.

**Limitation:** this varies the model only, with effort held equal, to stay comparable with the other
two evals. Dial 1 actually recommends `effort: low` on `meta-dev`, which this does not test. n=1.

## Files

* `0-spec.md` — the shared spec
* `grade.mjs` — the pinned rubric (pre-run version at `a1d1f4a`; current adds the signature adapter)
* `nan-probe.mjs` — the post-hoc unparseable-expiry probe
* `sonnet/`, `opus/` — each model's implementation plus its captured grader output
