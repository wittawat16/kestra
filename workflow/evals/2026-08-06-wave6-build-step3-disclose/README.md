# Eval — kestra-build, step 3 disclosed behind a gate table (Wave 6)

`kestra-build/SKILL.md`'s step 3 was **335 lines inside one ordered-list item**, read in full on
every invocation in either mode. Wave 6 moved the branch-specific rules out — two into the existing
`references/full-mode-stages.md`, five into a new `references/stage-derivation.md` — and replaced
the eleven lines of prose that were the file's only read gate with a seven-row table keyed to facts
step 2 already computes.

**This is disclosure, not deletion, and that inverts the burden of proof.** The
[2026-07-31 ablation](../2026-07-31-build-ablation-antipatterns/) deleted 174 lines and could only
get cheaper. A disclosed reference gets cheaper only if a run **declines to open it**; if every run
opens everything, Wave 6 costs strictly more than before — the pointer text, plus a `Read` turn,
plus the file. So the question this eval exists to answer is the *direction* of the delta, not its
size.

Commits under test: `b82a4c7` · `88bbe06` · `b03029d` · `5656499` · `bcc2bbd`, against `dd4077d`.

---

## Half A — mechanical, deterministic, no model involved

```
sh workflow/evals/2026-08-06-wave6-build-step3-disclose/logs/run-legs.sh
```

Seven legs, literal output in `logs/`. Every one of them re-runs to the same bytes.

| Leg | Result |
|---|---|
| `00-line-budget` | `SKILL.md` **921 → 749**, step 3 **335 → 163**; `full-mode-stages.md` 189 → 275; `stage-derivation.md` new at 163 |
| `01-move-fidelity` | **173/180 moved lines byte-identical**; 7 rewritten, each printed; 2 spans split rather than moved, 1 reworded sentence each |
| `02-links` | 102 relative links, **0 dangling**; both new files indexed in both READMEs; 33/33 headings |
| `03-gate-coverage` | the 4 gated sections are exactly the 4 a gate row names; **no dangling row, no orphan section** |
| `04-suites` | 15 / 80 / 55 / 9 OK; `validate_workflow.py` PASS on `runs/order-cancellation-refund`; `git diff --check` clean |
| `05-frozen` | the 2026-07-31 vendored copies untouched — 0 commits, 0 uncommitted changes |
| `06-vendor-provenance` | `before-skill/` and `after-skill/` byte-identical to `dd4077d` and `bcc2bbd`; spec and fixture byte-identical to the 2026-07-31 eval's |

### The read budget, by the branch a spec takes

| Run shape | before | after | Δ | opens |
|---|---:|---:|---:|---|
| `mode: lite`, no devops | 921 | **749** | **−172 (−18.7%)** | nothing |
| `mode: full`, typical | 1110 | **1024** | **−86 (−7.7%)** | `full-mode-stages.md` |
| full + wide refactor + repo gate | 1110 | **1187** | **+77 (+6.9%)** | both |

The maximal branch pays about 7% more lines. It is the only branch that reaches every rule, and it
now reaches them through one on-demand read instead of carrying them in every prefix. Lines are not
tokens and a table row is denser than the prose it replaced, so whether that trades favourably is
half B's question, not half A's.

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

**Not yet run.** This section is the protocol; results replace it.

There is no runner. The 2026-07-31 eval was two real, complete, manual invocations against vendored
skill copies, hand-diffed, and cost ~265k + ~240k subagent tokens over 822s + 646s. Wave 6 keeps
that shape and adds a second spec, because the branch where the predicted saving is largest — lite
— is the one that eval's fixture cannot reach.

**2 × 2, fixture held constant.**

| | `before-skill/` (`dd4077d`) | `after-skill/` (`bcc2bbd`) |
|---|---|---|
| `spec-full/0-spec.md` | run 1 | run 2 |
| `spec-lite/0-spec.md` | run 3 | run 4 |

- `fixture/` — the 2026-07-31 `queue-worker` fixture, byte-identical: plain ESM, `node --test`,
  one source file, and a `CLAUDE.md` that states conventions but declares **no** mandatory
  pre-merge gate.
- `spec-full/0-spec.md` — that eval's 254-line `needs_ba: true` priority-tier spec, verbatim. It
  derived `mode: full` off two rows of the condition table under both variants there.
- `spec-lite/0-spec.md` — **new to this eval**, 181 lines, a retry cap on the same pristine
  `src/queue.js`. Written so every row of the lite/full table reads false and there is no judgment
  call: one component, Reality Constraints affirmatively stating the only collaborator is an in-repo
  `Map` that tests populate with real functions, invariants whose violation is asserted rather than
  silent, all four `needs_*` flags false, no request for full. `validate_spec.py` gives it the same
  five WARNs and the same exit 0 as `spec-full`, so the two sit on the same mechanical footing.

**Recorded per run:** subagent tokens · tool calls · wall time · **which reference files it opened**
· the audit line it emitted. The reference list is the direct test of the gate design; the audit
line is the only artifact proving the table was consulted rather than skimmed.

**Equivalence bar:** `after`'s `workflow.yaml` must match `before`'s on stage ids, `depends_on`,
`write_scope`, exactly one `freeze_after`, `exit_criteria`, and `on_fail` target/caps. Both must
pass `validate_workflow.py` with 0 warnings. A mode disagreement between `before` and `after` on the
same spec is a regression, not a result.

**The 2026-07-31 numbers are not a baseline.** They were measured against a 897-line
`full-skill/SKILL.md`; the file had drifted to 921 by `dd4077d`. `before` has to be re-run.

---

## What this eval will not establish

- ❌ **Five of the nine disclosed rules are invisible to this fixture.** The spec is
  single-component, `needs_ui: false`, `needs_devops: false`, and the repo declares no pre-merge
  gate, so the runs exercise the `spec-review` depth rule, the `test-review` fold-in, the verdict
  shape, and the same-spawn scenario table — and are structurally blind to the `design-tests` split,
  both refactor sections, the repo-gate stage, `deploy-readiness`, and splitting `review`. Those are
  covered *mechanically* by legs 01 and 03 and **not behaviourally**, the same N/A caveat the parent
  eval declared for ~40% of its own list.
- ❌ **n = 1 per cell.** Four runs is one sample each. A single run's token count moves for reasons
  unrelated to the skill, so treat a delta under about 5% as noise.
- ❌ **Single model.** Says nothing about whether a gate table survives a weaker or faster model —
  and step 2's own war story is that a smaller model skims prose instructions to checklist. A lookup
  table has less to force compliance than the fill-in table that story is about.
- ❌ **Neither generated `workflow.yaml` is executed.** Structural validity is checked; no
  `kestra-run` pass confirms a real implementation attempt behaves as the briefs expect.

## Artifacts

- `logs/run-legs.sh`, `logs/0*.log` — half A, re-runnable
- `before-skill/`, `after-skill/` — full copies of `kestra-build/` at `dd4077d` and `bcc2bbd`,
  provenance asserted in leg 06. Full copies rather than partial because `references/` and
  `scripts/` have to resolve normally for a run to be real.
- `spec-full/`, `spec-lite/`, `fixture/` — the inputs
