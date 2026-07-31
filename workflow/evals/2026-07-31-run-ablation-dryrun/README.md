# Eval — kestra-run, dry-run scenario test on the context-pack and scope-cap blocks

Not a live pipeline run (kestra-run does real git commits — too risky/expensive to ablate the way
kestra-spec/kestra-build were). Instead: a **judgment dry-run**. Same FULL-vs-MINIMAL SKILL.md
structure, but instead of generating a real artifact, both variants answer 6 situational questions
that specifically probe the two densest inline blocks in `kestra-run/SKILL.md` — the "context pack"
field list (~53 lines) and "scope-cap the recheck" 3-guard breakdown (~40 lines) — no Bash, no git,
no spawns.

**Why these two blocks specifically, not the whole file:** checked first — most of kestra-run's other
efficiency content (skip-the-spawn, wall-clock/install-caching, combining fix attempts, resume-vs-
respawn) is *already* a terse pointer to `references/efficiency-notes.md`, which holds the real
detail (measured numbers, the five-guard skip-the-spawn checklist, the 200,001-case sweep example).
There isn't much left to cut there — it's already lean. The context-pack and scope-cap blocks are
different: they're the **primary source**, not a duplicate of something already documented elsewhere
in the repo. Cutting them is a materially different, higher-risk kind of test than the kestra-build
anti-patterns cut (which had `validate_workflow.py` as a mechanical backstop) — there's no backstop
here, so if MINIMAL's compressed version lost real information, these are exactly the scenarios that
would expose it.

**MINIMAL's compression, concretely:** context-pack block collapsed from an elaborated walkthrough
with a measured-cost justification, per-field elaboration, and a separately-explained post-reworking
special case, into one dense paragraph naming every field once. Scope-cap's three labeled guards
(Baseline / Indirect effects / Boundaries, each with worked reasoning) collapsed into two sentences.
SKILL.md: 380 → 312 lines (−18%).

## The 6 scenarios

1. Context pack: which commit's diff to paste when the immediately-prior stage's commit is code-empty
2. Post-reworking pack scoping for `test-review` (must NOT be diff-only — cross-file job)
3. Post-reworking pack scoping for `review` (diff-only IS correct here — different from #2)
4. Scope-cap baseline: diff against the *last full-scope pass* commit, not the latest attempt's delta
5. Scope-cap indirect effects: a shared-helper-only fix diff still requires checking its unchanged
   callers
6. Scope-cap boundary: never applies across a `reworking` transition — always full review after

Q4 and Q5 are the two hardest — they require connecting an abstract rule ("last full-scope pass",
"indirect effects") to a concrete multi-attempt scenario, exactly the kind of judgment a compressed
instruction is most likely to lose.

## Results

| | FULL | MINIMAL | Δ |
|---|---|---|---|
| Subagent tokens | 118,443 | 114,871 | −3.0% |
| Tool calls | 0 | 0 | — |

Flat, like the kestra-spec rounds — no tool-cross-referencing effect here (this was a single-turn
Q&A task, not a multi-step generation task like kestra-build's, which is likely why that eval showed
a bigger delta and this one doesn't).

**All 6 answers correct, in both variants, with equivalent reasoning.** Both correctly:
- walked back past `freeze-tests`'s empty commit to `generate-tests`'s diff, and both also included
  the frozen test file list (Q1)
- refused to diff-only-scope `test-review`'s post-reworking pack while correctly diff-only-scoping
  `review`'s (Q2 vs Q3 — the one place a shallow compression could plausibly have collapsed two
  different rules into one)
- anchored the scope-cap baseline to attempt 1 (the last *full-scope* pass), explicitly reasoning
  that attempt 2 was itself a scoped recheck and therefore doesn't reset the baseline (Q4) — MINIMAL
  explicitly flagged this step as "requires reasoning to connect... not stated outright," which is
  itself evidence the compression didn't remove information that mattered, just labeled its own
  inference honestly
- required checking two zero-diff files whose shared dependency changed (Q5)
- required a full review, not a scope-capped one, immediately after a `reworking` transition (Q6)

Zero decision-quality gap on the two most compressed, highest-risk blocks in the file.

## What this does and doesn't establish

- ✅ On these 6 scenarios, compressing kestra-run's two densest **unbacked-by-a-reference-doc**
  blocks (context pack, scope-cap) to roughly a third of their original length produced identical
  correct judgment, including on the two scenarios designed to be hardest.
- ❌ **This is comprehension, not execution.** A dry-run Q&A tests whether the model can correctly
  reason about the rule when asked directly — it does not test whether the *live* orchestrator,
  mid-loop, under its own multi-step momentum, reliably composes the pack this way unprompted, or
  whether some real edge case outside these 6 scenarios (a multi-sibling batch fix, a spec too large
  to paste, a resumed-vs-respawned mid-transcript case) trips on the missing elaboration. The other
  two evals in this series tested real generated artifacts; this one deliberately didn't, because
  kestra-run's real artifacts are git commits on a real repo.
- ❌ n=1 set of scenarios, one model. A different/larger scenario set could still surface a gap these
  6 didn't hit.
- ❌ Doesn't touch the rest of the file (the loop's steps 1/3/4/5/7, Hard rules, Resuming) — those
  weren't ablated and this eval says nothing about them.

## Artifacts

- `full-skill/`, `minimal-skill/` — full copies of `kestra-run/`, differing only in the context-pack
  and scope-cap block density
