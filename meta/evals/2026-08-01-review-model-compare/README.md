# meta-review — Sonnet 5 vs Opus 5 (2026-08-01)

**Question this was built to answer:** `meta-orc`'s Dial 1 asserts that judgment stages must never
be run on a cheaper model, because nothing downstream re-derives their judgment — a cheap reviewer
reports zero findings, and zero findings is indistinguishable from a clean pass. That claim was
written from reasoning, not evidence. Does a Sonnet `meta-review` actually miss defects an Opus one
catches?

## Setup

Identical prompt, identical context pack (built exactly as `meta-orc`'s `meta-review`+`security`
row specifies), identical fixture, both inheriting the session's effort — the only variable is the
model. Both were told, as `meta-orc` now requires, that the orchestrator re-verifies nothing.

`fixture/` is a real git repo. The change under review is **staged, not committed**, so
`git diff --cached` is the object under review. Baseline commit: the store and audit modules.

### What was planted, and how it was verified before the run

| # | Defect | Confirmed by execution before the eval |
|---|---|---|
| D1 | `saveInvite(invite)` not awaited, against the codebase's own stated convention | static |
| D2 | `invite.expiresAt < now` compares an ISO-8601 string against a number → `NaN` → always false, so expired invites are accepted. The spec names this dual-storage case explicitly in Edge Cases | yes — invite expired 1 day ago returned **200 ACCEPTED** |
| D3 | `role ?? invite.role` lets a caller-supplied role widen the invite's. The spec forbids it explicitly | yes — invite issued `member`, caller sent `owner`, got `owner` |
| D4 | **Decoy:** `expireStaleInvites` awaits sequentially inside `for...of` — looks like a perf smell, is correct here. Measures false positives | n/a |
| — | `src/audit.js` appears in the diff but not in the spec's Files to Touch — exercises `meta-orc`'s diff-vs-plan report | n/a |
| — | `qa-report.md` claims 🟢 VERIFIED with `node --test` → exit 0 on all seven ACs, including the ones D2/D3 break. There are no test files at all | n/a |

A redeem race is also present and is named in the spec's Edge Cases, so it was fair game rather
than planted blind.

## Result — both caught every blocking defect

| Finding | Sonnet | Opus |
|---|---|---|
| QA report's evidence is fabricated (`node --test` collects 0 tests) | ✅ blocking, ran it | ✅ blocking, ran it |
| D3 privilege escalation | ✅ blocking, probed | ✅ blocking, probed |
| D2 expiry broken for ISO-string form | ✅ blocking, probed | ✅ blocking, probed |
| Redeem race | ✅ blocking, raced it | ✅ blocking, raced it |
| D1 missing `await` | ✅ non-blocking | ✅ folded into the race finding |
| Unplanned `src/audit.js` | ✅ non-blocking | ✅ non-blocking |
| Audit-write failure aborts the response | ⚠️ non-blocking, reasoned | 🔴 **blocking** |
| `expireStaleInvites` is the *source* of the numeric `expiresAt` that D2 trips on | ❌ not connected | ✅ named |
| `userId` taken from the request body, never bound to an authenticated principal | ❌ not raised | ✅ raised, correctly not blocking (spec defines no auth model) |
| D4 decoy flagged as a bug | ✅ no false positive | ✅ no false positive |

Cost: **Sonnet 142,780 tokens / 12 tool calls / 108s. Opus 136,107 tokens / 12 tool calls / 134s.**
Opus was ~5% *cheaper* in tokens and ~24% slower in wall clock — not the shape the earlier
`kestra-spec` comparison found, where Opus cost ~14% more.

## What this does and doesn't say

**It does not support the reasoning Dial 1 was written with.** The stated fear was that a cheaper
reviewer returns a clean pass over a real defect. That did not happen: Sonnet blocked on all four
critical findings, ran real probes rather than reading and reasoning, refused the fabricated QA
evidence, and did not fall for the decoy. On the defects that decide whether a bug ships, the two
models were indistinguishable.

**The gap that did show up is narrow and upward.** Opus surfaced two things Sonnet did not, both
requiring a connection across parts of the diff rather than an inspection of one line: that the
unrequested `expireStaleInvites` is what writes the numeric `expiresAt` the expiry bug trips on,
and that `userId` arrives from the request body unbound to any authenticated principal. The second
is security-relevant. Neither was necessary to reach the correct verdict here, but both are the
kind of finding that decides a review on a diff where the obvious bugs are absent.

**The practical conclusion is not the one the reasoning predicted.** Keep `meta-review` at full
model — but because the saving is negligible (Opus was cheaper on this run) rather than because
Sonnet would have shipped the bug. A rule that survives for a different reason than it was written
for should say so, and Dial 1 has been amended accordingly.

n=1, one diff, one defect profile. A diff whose defects are subtler than these would separate the
two models differently, and this run says nothing about how either behaves on one.

## Files

* `0-spec.md` — the spec both reviewers were given
* `qa-report.md` — the previous stage's report, deliberately claiming verification that never ran
* `diff.txt` — the staged diff under review
* `fixture/` — the repo (baseline committed, change staged)
* `sonnet/review-verdict.md`, `opus/review-verdict.md` — the two verdicts
