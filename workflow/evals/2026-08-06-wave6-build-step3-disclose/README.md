# Eval — kestra-build, step 3 disclosed behind a gate table (Wave 6)

`kestra-build/SKILL.md`'s step 3 was **335 lines inside one ordered-list item**, read in full on
every invocation in either mode. Wave 6 moved the branch-specific rules out — two into the existing
`references/full-mode-stages.md`, five into a new `references/stage-derivation.md` — and replaced
the fifteen lines of prose that were the file's only read gate with a six-row table keyed to facts
step 2 already computes.

**This is disclosure, not deletion, and that inverts the burden of proof.** The
[2026-07-31 ablation](../2026-07-31-build-ablation-antipatterns/) deleted 174 lines and could only
get cheaper. A disclosed reference gets cheaper only if a run **declines to open it**; if every run
opens everything, Wave 6 costs strictly more than before — the pointer text, plus a `Read` turn,
plus the file. So the question this eval exists to answer is the *direction* of the delta, not its
size.

Commits under test: `b82a4c7` · `88bbe06` · `b03029d` · `5656499` · `bcc2bbd`, against `dd4077d`.

---

## The answer, up front

**The gate works. The saving does not show up in tokens, and on lite the measurement went the wrong
way.** Four real invocations, 2 specs × 2 skill versions:

| | tokens | tool calls | wall | mode | refs opened |
|---|---:|---:|---:|---|---|
| run 1 · `before` · full | 158,623 | 35 | 620s | full | 4 |
| run 2 · `after` · full | 159,578 | 33 | 623s | full | 4 |
| | **+0.6%** | −2 | +3s | agree | same 4 |
| run 3 · `before` · lite | 144,954 | 31 | 594s | lite | 3 |
| run 4 · `after` · lite | 155,639 | 34 | 725s | lite | 3 |
| | **+7.4%** | +3 | +131s | agree | same 3 |

Three findings, in order of how much they should change what anyone does next:

1. **No run opened a file the gate told it not to.** Run 2's audit line names the skip in as many
   words — `skipped: stage-derivation.md (no row fired)`. Run 4's names the row that fired —
   `mode: lite and needs_devops: false` → open nothing. The mechanism the wave was built on
   behaved exactly as designed, in both modes.
2. **The `before` skill's prose gate already worked too.** Run 3 opened only the three
   unconditional references and declined `full-mode-stages.md` on its own, obeying the prose at
   `dd4077d:386-400`. So Wave 6 did **not** buy "stops a wasteful read" — that read was already
   not happening. What it bought is 20% less text in the lite prefix and a mechanical trigger for
   four rules that previously had none at all.
3. **The addressable prize is smaller than this design's noise.** Leg 07 does the arithmetic: the
   entire lite text saving is 15,895 characters ≈ **3,974 tokens ≈ 2.7% of one measured run**. The
   observed lite delta was +7.4%. **A single sample per cell cannot resolve a 2.7% effect against
   run-to-run variance several times larger**, and the +7.4% cannot be blamed on extra reads
   because no extra read happened.

**So: the structural claim is proven and the cost claim is not.** This eval must not be cited as
evidence that Wave 6 made `kestra-build` cheaper. It is evidence that Wave 6 made it *smaller*
without changing what it produces — see the equivalence section — and that measuring a disclosure
wave this way does not work.

---

## Half A — mechanical, deterministic, no model involved

```
sh workflow/evals/2026-08-06-wave6-build-step3-disclose/logs/run-legs.sh
```

Nine legs, literal output in `logs/`. Consecutive re-runs produce identical bytes, with one
deliberate exception: leg 04 records the short SHA of `HEAD`, so it changes when `HEAD` moves.

| Leg | Result |
|---|---|
| `00-line-budget` | `SKILL.md` **921 → 749**, step 3 **335 → 163**; `full-mode-stages.md` 189 → 275; `stage-derivation.md` new at 163 |
| `01-move-fidelity` | **173/180 moved lines byte-identical**; 7 rewritten, each printed; 2 spans split rather than moved, 1 reworded sentence each |
| `02-links` | 102 relative links, **0 dangling**; both new files indexed in both READMEs; 33/33 headings |
| `03-gate-coverage` | the 4 gated sections are exactly the 4 a gate row names; **no dangling row, no orphan section** |
| `04-suites` | 15 / 80 / 55 / 9 OK; `validate_workflow.py` PASS on `runs/order-cancellation-refund`; `git diff --check` clean, scoped away from this `logs/` dir so the leg cannot report on its own output |
| `05-frozen` | the 2026-07-31 vendored copies untouched — 0 commits, 0 uncommitted changes |
| `06-vendor-provenance` | `before-skill/` and `after-skill/` byte-identical to `dd4077d` and `bcc2bbd`; spec and fixture byte-identical to the 2026-07-31 eval's |
| `07-token-proxy-budget` | the same budget in **words and characters**, because a line is not a token; plus what the whole saving is worth against a real run |
| `08-run-equivalence` | half B's equivalence bar applied mechanically to all four generated workflows, and all four validated under **both** vendored validators |

### The read budget, three ways

Leg 00 counts lines. A table row is denser than the prose it replaced, so a line count could
flatter the wave — leg 07 recounts in words and characters, which track tokens far more closely.

| Run shape | lines | words | chars |
|---|---:|---:|---:|
| `mode: lite`, no devops | −172 (−18.7%) | −2,375 (−19.8%) | **−15,895 (−20.0%)** |
| `mode: full`, typical | −86 (−7.7%) | −1,218 (−8.5%) | **−8,329 (−8.9%)** |
| full + wide refactor + repo gate | +77 (+6.9%) | +808 (+5.7%) | **+3,955 (+4.2%)** |

Words and chars move *further* than lines in the saving direction and *less far* in the penalty
direction, so the line count understates the wave rather than flattering it. The one place the
trade goes the other way is the gate itself, isolated and printed rather than buried: the prose
gate was 15 lines / 188 words / 1,291 chars, the table is **8 lines / 240 words / 1,494 chars** —
nearly half the lines, and *more* words. That is the "lines are not tokens" effect with nothing
else mixed in, and it costs a couple of hundred characters against a saving two orders of
magnitude larger.

`SKILL.md` at 749 sits between the 2026-07-31 ablation's two variants — `full-skill/` 897,
`minimal-skill/` 723 — i.e. back inside the range that eval measured, having drifted to 921 above
both.

### The 7 rewritten lines, and why they are not a fidelity failure

Every one is a direction or path reference that relocation broke. They are listed in
`logs/01-move-fidelity.log` in full; the whole set is:

```
(see **Inputs**)                          -> (see `SKILL.md`'s **Inputs**)
emitted by step F5 above                  -> emitted by `SKILL.md`'s step F5
`references/design-principles.md`         -> `design-principles.md`
triggers `test-review` by the table above -> ... by the rule above
rejected by step 7's validator            -> rejected by `SKILL.md` step 7's validator
(see the table above)                     -> (see `SKILL.md` step 2's script-eligibility table)
the defect this bullet ...          (×2)  -> the defect this rule ...
```

### A defect this eval's own arithmetic caught

Computing leg 00 exposed a bug in the gate table two commits after it shipped. One row read *"any
stage you generate will write a verdict artifact → stage-derivation.md §2"*. `review` is mandatory
in **both** modes, so that row fires on every run — it would have sent every lite build into the
one file the gate exists to keep closed, dropping the lite saving from 18.7% to about 2%.

The row was wrong because the content behind it was misfiled. Section 2 held both the *reasoning*
for the verdict shape (skippable) and the rule a numeric finding must satisfy (needed on every run).
`bcc2bbd` brings the rule back inline and deletes the row. This is exactly the failure mode the
plan's own dead-point list named — *"disclosure can invert the sign"* — and half A found it only
because the budget was computed rather than asserted.

---

## Half B — four real `kestra-build` invocations

There is no runner. Each run is a real, complete, manual invocation against a vendored skill copy,
told to resolve every relative pointer inside that copy and to open references only as the SKILL.md
instructs. The four prompts are identical apart from three paths: the skill, the spec, the output
dir. **2 × 2, fixture held constant.**

| | `before-skill/` (`dd4077d`) | `after-skill/` (`bcc2bbd`) |
|---|---|---|
| `spec-full/0-spec.md` | run 1 | run 2 |
| `spec-lite/0-spec.md` | run 3 | run 4 |

- `fixture/` — the 2026-07-31 `queue-worker` fixture, byte-identical: plain ESM, `node --test`,
  one source file, and a `CLAUDE.md` that states conventions but declares **no** mandatory
  pre-merge gate.
- `spec-full/0-spec.md` — that eval's 254-line `needs_ba: true` priority-tier spec, verbatim.
- `spec-lite/0-spec.md` — **new to this eval**, 181 lines, a retry cap on the same pristine
  `src/queue.js`. Written so every row of the lite/full table reads false and there is no judgment
  call. `validate_spec.py` gives it the same five WARNs and the same exit 0 as `spec-full`.

Runs 1 and 2 were executed as a concurrent pair, then runs 3 and 4 as a second concurrent pair.
**Wall time is therefore not comparable** to the 2026-07-31 eval's sequential 822s / 646s, and the
+131s on the lite pair is worth less than its size suggests. Tokens and tool calls are unaffected
by concurrency and are the numbers to read.

**The 2026-07-31 figures are not a baseline.** They were measured against a 897-line
`full-skill/SKILL.md`; the file had drifted to 921 by `dd4077d`, which is why `before` was re-run.

### What each run opened, and what it said about it

The reference list is the direct test of the gate design; the audit line is the only artifact
proving the table was consulted rather than skimmed. Both were required in every run's final block.

| Run | Opened | Declined |
|---|---|---|
| 1 · before · full | `design-principles` · `workflow-schema` · `state-schema` · `full-mode-stages` | — |
| 2 · after · full | the same four | `stage-derivation` · `ticket-fold` · `test-quality-taxonomy-research` |
| 3 · before · lite | `design-principles` · `workflow-schema` · `state-schema` | `full-mode-stages` |
| 4 · after · lite | the same three | `full-mode-stages` · `stage-derivation` · `ticket-fold` · `test-quality-taxonomy-research` |

The three files every run opens are mandated elsewhere in the Process — `design-principles.md` by
the read-once-per-session rule, `workflow-schema.md` by step 5, `state-schema.md` by step 6 — and
are outside step 3's gate. **The gate's whole job is the fourth and fifth entries, and it did it in
both directions:** run 2 opened `full-mode-stages.md` because `mode: full` fired, and skipped
`stage-derivation.md` because nothing did; run 4 skipped both because the `lite` + no-devops row
says *open nothing*. Every skip was named out loud in the audit line, unprompted.

Both `after` runs also volunteered the reasoning for a skip rather than just the fact — run 2
distinguished the unconditional reads from the gated one explicitly. That is the compliance artifact
the plan predicted a *lookup* table would lack, and it appeared without being asked for beyond
"emit your audit line."

### Equivalence — the bar the wave had to clear

Applied mechanically in leg 08 rather than eyeballed. **Both pairs pass, and both modes agree** —
a mode disagreement on the same spec would have been a regression, not a result.

```
full: run-1-before-full  vs  run-2-after-full
  mode : full vs full  AGREE      stages: 8 vs 8      freeze_after=true: 1 vs 1
  renamed: implement-tier-retry-policy -> implement-tier-retry
  differences after normalising path frame and renames: none

lite: run-3-before-lite  vs  run-4-after-lite
  mode : lite vs lite  AGREE      stages: 6 vs 6      freeze_after=true: 1 vs 1
  renamed: verify -> verify-acceptance-criteria
  differences: generate-tests write_scope gains "test-scenarios.md"
```

All four workflows PASS `validate_workflow.py` **under both vendored validators** — all eight
combinations exit 0, each with the same expected `no spec_anchor` WARN that a monolithic
hand-written spec should produce. Cross-validating matters here: an `after` workflow that only
passed the `after` validator would leave open whether the wave had quietly loosened a check.
`state.json` has the identical key shape across all four runs.

Two normalisations leg 08 applies, and why neither hides a regression:

- **Stage ids are free text derived from the spec.** `verify` vs `verify-acceptance-criteria` names
  the same `write_scope: []` sibling with the same `on_fail.target`. The rename is propagated
  through `depends_on` and `target` before comparison, so a *topology* change could not hide inside
  a rename.
- **The path frame is a per-run choice the skill never constrains** — see the defect below. Leg 08
  compares basenames so that it stays a structure check.

The one genuine behavioural difference is run 4 adding `test-scenarios.md` to `generate-tests`'s
`write_scope`: it materialised the scenario table as a gated artifact inside the same stage instead
of keeping it in the spawn. That is **permitted** by the rule both versions carry — `stage-derivation.md`
§1 says `on_fail.target: generate-tests` may edit table and tests together precisely because they
share one `write_scope` — and it is not the forbidden thing, which is splitting a separate
`design-tests` stage.

### Two pre-existing defects the runs surfaced, and one this eval created

Neither of the first two is a Wave 6 regression — both are present identically at `dd4077d` and at
`bcc2bbd`, and both were found *behaviourally*, by agents tripping over them, which is the thing
half A structurally cannot do. They are filed separately rather than fixed here, to keep the wave's
diff honest.

1. **F5 contradicts its own section header.** `SKILL.md:120` opens the fold-start section with
   "Form A only; form B skips this whole section," while `SKILL.md:175` — inside it — says the `cp`
   of the three scripts happens "on **every** fold including form B". A form-B run obeying the
   header never emits `validate_workflow.py`, and step 7's dry run against the run's own copy
   becomes impossible. **All four runs hit this; all four obeyed :175 over :120.** Four independent
   resolutions of the same contradiction in the same direction is a strong signal the intent is
   :175 and the header is the bug.
2. **No path frame is ever stated** for `write_scope` globs or `exit_criteria.run` working
   directories. The worked example mixes run-folder-relative (`validate_spec.py`, `spec-verdict.md`)
   with repo-relative (`npm test`, `src/routes/**`) — invisible while the run folder sits inside the
   target repo, which in this eval it does not. Two runs on the same spec picked two conventions:
   run 1 wrote `["src/queue.js"]` and `["../spec-full/0-spec.md"]`, run 2 wrote
   `["fixture/src/queue.js"]` and `["spec-full/0-spec.md"]`. **All four runs documented the
   convention they had to invent, in a header comment, unprompted** — run 4's is captioned
   `PATH CONVENTION for this run` and spells out that the harness put the run folder outside the
   repo. That is the right instinct, and it is also four independent pieces of evidence that the
   skill left them to invent one.
3. **The runs polluted the frozen copies, and leg 06 caught it.** Invoking the vendored
   `validate_spec.py` imports `requirement_surface` and drops a `.pyc` inside `before-skill/` and
   `after-skill/` — the exact byte-level drift leg 06 exists to reject. Leg 06 now sweeps
   `__pycache__` out of both vendored folders before checking, prints what it removed, and asserts
   provenance on what remains; anyone re-running half B should `export PYTHONDONTWRITEBYTECODE=1`
   so it never appears. Bytecode is generated, never authored, so removing it cannot destroy
   evidence — but a leg that checks byte-identity has to be told that, explicitly, once.

### Why the tokens did not move

Worth stating plainly, because the temptation is to read +0.6% as "roughly free" and +7.4% as
"something broke." Neither is right.

- **The skill text is a small minority of a run.** ~4,000 tokens of addressable saving inside a
  ~150,000-token run is 2.7%. The other 97% is the spec, the fixture reads, the standalone command
  verification each run does, the generated YAML, and the run's own reasoning.
- **The +7.4% has no attributable cause among the things this eval records.** Every candidate was
  checked and each is ruled out or points the other way:

  | Candidate | Verdict |
  |---|---|
  | run 4 opened a file the gate should have closed | **ruled out** — same three references as run 3, both declined all four gated files |
  | run 4 did more standalone command verification | **ruled out** — both ran three polarity cases (correct red, ESM whole-file collapse, all-green/vacuous) |
  | run 4 produced a bigger artifact | **points the other way** — run 4's `workflow.yaml` is 20,026 chars vs run 3's 21,039, i.e. **4.8% smaller** |
  | run 4 made more tool calls | 34 vs 31, and 725s vs 594s — consistent with the token count, but a restatement of it, not an explanation |

  What is left is unobserved variation in the run's internal reasoning path. **That is the finding.**
  This eval records references opened, tool calls, artifacts, stage topology and mode, and *none of
  them* explains a 7.4% token swing — so whole-run tokens are not a usable metric for grading a
  change to skill text at this scale.
- **So +7.4% is not evidence of a cost regression, and +0.6% is not evidence of neutrality.** Both
  are inside the range this design cannot separate from noise. The honest report is *no measurable
  token effect, with an adverse and unexplained point estimate on lite*, and the design lesson is
  that an n=1 whole-run A/B cannot grade a 3% intervention. A future wave that wants a cost number
  should measure the **prefix** — the tokens the skill text itself contributes — not the run total.

---

## What this eval does not establish

- ❌ **Any claim about cost.** The point estimates are +0.6% (full) and +7.4% (lite), one sample per
  cell, against a maximum available saving of 2.7%. Grading a disclosure wave needs either many
  samples per cell or a harness that measures prefix tokens directly instead of whole-run tokens.
- ❌ **Five of the nine disclosed rules are invisible to this fixture.** Both specs are
  single-component, `needs_ui: false`, `needs_devops: false`, and the repo declares no pre-merge
  gate, so the runs exercise the `spec-review` depth rule, the `test-review` fold-in, the verdict
  shape, and the same-spawn scenario table — and are structurally blind to the `design-tests`
  split, both refactor sections, the repo-gate stage, `deploy-readiness`, and splitting `review`.
  Those are covered *mechanically* by legs 01 and 03 and **not behaviourally**, the same N/A caveat
  the parent eval declared for ~40% of its own list.
- ❌ **Single model.** Says nothing about whether a gate table survives a weaker or faster model —
  and step 2's own war story is that a smaller model skims prose instructions to checklist. A
  lookup table has less to force compliance than the fill-in table that story is about. The audit
  lines here are strong evidence *for* the design, on one model, four for four.
- ❌ **Neither generated `workflow.yaml` is executed.** Structural validity is checked under both
  validators; no `kestra-run` pass confirms a real implementation attempt behaves as the briefs
  expect.

## Artifacts

- `logs/run-legs.sh`, `logs/0*.log` — half A, re-runnable, byte-stable at a fixed `HEAD`
- `before-skill/`, `after-skill/` — full copies of `kestra-build/` at `dd4077d` and `bcc2bbd`,
  provenance asserted in leg 06. Full copies rather than partial because `references/` and
  `scripts/` have to resolve normally for a run to be real.
- `spec-full/`, `spec-lite/`, `fixture/` — the inputs
- `run-1-before-full/` … `run-4-after-lite/` — each run's `workflow.yaml`, `state.json`, and the
  three scripts its own F5 emitted
