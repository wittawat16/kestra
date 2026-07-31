# Eval — kestra-build, FULL SKILL.md vs. anti-patterns section removed (narrow ablation)

Narrower than the kestra-spec ablations: same file, same everything else, **only** the
~172-line "## Anti-patterns — don't generate these" section removed (20 specific war-story
warnings, several with "confirmed by direct testing" evidence attached). Chosen because
kestra-build's content is mostly mechanical protocol (field names, schema, escalation semantics) —
a different risk profile from kestra-spec's narrative prose, where a wrong guess produces a
malformed `workflow.yaml` instead of just weaker prose.

**Setup:** both variants got a full copy of `kestra-build/` (so `references/`, `scripts/` all
resolve normally) — `full-skill/` unmodified, `minimal-skill/` with only the anti-patterns section
deleted. Same input spec (`spec/0-spec.md`, the `needs_ba: true` priority-tier spec from
`2026-07-31-spec-ablation-cherny-2/full/`), same target fixture. Each ran as a real, complete
kestra-build invocation — reading references on demand, actually running commands against the
fixture to verify `exit_criteria`, actually invoking `scripts/validate_workflow.py` for the step-7
dry run — not a shortcut summary.

## Results

| | FULL | MINIMAL (no anti-patterns) | Δ |
|---|---|---|---|
| Subagent tokens | 265,073 | 239,665 | **−9.6%** |
| Tool calls | 41 | 32 | **−22%** |
| Wall time | 822s | 646s | **−21%** |
| `validate_workflow.py` | PASS, 0 warnings | PASS, 0 warnings | same |

Bigger delta than either kestra-spec round (which were flat, ±3%). Plausible reason: the
anti-patterns section is a checklist an agent visibly cross-references against its own draft
mid-generation — more tool turns spent verifying against explicit named traps, not just more
tokens read once. Both variants independently derived `mode: full` off the same two table rows and
produced the same 7-stage shape (`spec-review → generate-tests → freeze-tests → implement →
{verify, review} → done`), correctly folding `test-review` into `generate-tests` rather than
generating a separate stage (this repo's real test design uses only real fixtures, per the SKILL's
own fold-in rule — which lives in step 3, **not** in the ablated section).

## Anti-pattern-by-anti-pattern check on MINIMAL's output

Checked all 20 anti-patterns from the removed section against `minimal-output/workflow.yaml`
directly (not against MINIMAL's own self-report). Anti-patterns requiring a shape this single-file,
no-UI, no-restart spec can't exercise (chaining sibling `implement-*`, `define-shared-contract`
misuse, `test-review` misplacement, in-process-restart-simulation trap) are marked N/A — this eval
says nothing about those, one way or the other.

| Anti-pattern | MINIMAL's actual output |
|---|---|
| `model`/`effort` cost-cutting on judgment stages | neither field set anywhere — correct |
| `mode: lite` chosen to dodge doubles | N/A — doubles row didn't fire toward lite either way |
| lite dropping freeze-tests/review, merging verify+review | N/A — mode is full |
| `write_scope` leaking test paths post-freeze | clean — `implement`/`verify`/`review`/`done` all correctly scoped |
| trivial existence-only `spec-review` | real verdict artifact + 4-point semantic check, same depth as FULL |
| `implement-*` brief silent on runtime invariants | both guards explicitly demanded, with the "tests can't catch this" reasoning stated |
| `on_fail` missing `max_attempts`/`escalate_at` | present on every fixing block |
| `write_scope` too narrow (missing test-runner plumbing) | correctly noted none needed (no config file for `node --test`) |
| review skipped | present, mandatory, unconditional |
| `review`/`verify` fixing without `target` | both carry `target: implement-queue-tier` |
| defaulting to `human_approval` | none anywhere; both use `command`/`artifact_exists` |
| hard-coded `skill:` field | none — skills named only inside brief text as suggestions |
| **`generate-tests` exit_criteria expecting tests to pass (wrong polarity)** | avoided — no `npm test` expecting exit 0 pre-implementation |
| **polarity fixed with a syntax-only check** | avoided, and arguably *exceeded* FULL — see below |
| freeze_after misplaced (on generate-tests, or on a write_scope:[] stage) | correctly on `freeze-tests` only, non-empty scope |
| chaining sibling `implement-*` | N/A — one component |
| `define-shared-contract` misuse | N/A — nothing shared |
| `test-review` after freeze / owning test paths | N/A — no `test-review` stage generated (correctly folded) |
| restart-simulation trap | N/A — no restart AC in this spec |
| AC-coverage presence lint overclaim | MINIMAL added a lighter version on its own (BR-id tagging + grep), correctly labeled presence-only |

**Zero violations found.** Every anti-pattern this spec's shape could actually trigger was avoided
just as well without the explicit list as with it.

## Where MINIMAL actually did *better*, not just equal

The two most load-bearing anti-patterns in the whole section — "don't run the test suite expecting
it to pass" and "don't solve that with a syntax-only check, ask for real static name resolution" —
are exactly the two MINIMAL never saw. Its own cost report describes arriving at the fix through
tool-use trial and error: "the naive syntax-check and naive-import approaches both failed for
documented reasons before the `vm.SourceTextModule` link-only approach worked." The result
(`scripts/check_test_link.mjs`, a genuine static link-check using Node's VM module API that resolves
import names against a synthetic stand-in module without executing any test body) is a **more
faithful realization of what the anti-pattern actually asks for** — "static analysis that resolves
names without executing or importing the implementation" — than FULL's own solution, which runs the
real tests and greps their output for specific error-message substrings (`ReferenceError`,
`is not a function`, …) — technically not static analysis, and fragile to error-message wording that
happens to fall outside the grep pattern. FULL had the instruction stated explicitly and produced a
looser fix than MINIMAL derived from first principles under the same underlying constraint (the
polarity requirement is *also* stated independently in step 7's "dry-run" discipline, which was
**not** removed — so MINIMAL wasn't flying fully blind, it had the requirement, just not the
worked-out failure mode or the suggested fix shape).

## What this does and doesn't establish

- ✅ On this spec, removing the entire anti-patterns section — including several "confirmed by
  direct testing" bullets — produced zero regressions against any anti-pattern the spec's shape
  could exercise, at meaningfully lower cost (−9.6% tokens, −22% tool calls) than kestra-spec's
  ablations showed.
- ✅ The single most specific, empirically-justified pair of bullets in the section (test polarity +
  syntax-only trap) turned out to be reconstructible from the surrounding step-7 dry-run discipline
  plus the agent's own tool-use — suggesting the anti-patterns section's value here is redundant
  with instructions living elsewhere in the file, not sole-source.
- ❌ **Single spec, single fixture, single model, single run each — n=1**, same caveat as every
  round before this. A different spec shape (2+ components, UI, restart/persistence AC) would
  exercise the ~40% of the list this run couldn't touch at all (see N/A rows above).
- ❌ Doesn't test whether the anti-patterns section still earns its keep on a **weaker/faster
  model** — the file's own `model` anti-pattern explicitly warns that a faster model was measured
  to silently drop unstated constraints on a different task; this eval used the same model for both
  variants and says nothing about that failure mode.
- ❌ Doesn't run either generated `workflow.yaml` through `kestra-run` — both look structurally
  correct and pass `validate_workflow.py`, but neither was actually executed end-to-end to confirm a
  real implementation attempt behaves as each spec's `implement-*` brief expects.

## Artifacts

- `spec/0-spec.md` — the input spec (reused from `2026-07-31-spec-ablation-cherny-2`)
- `fixture/` — the target codebase both runs read/verified against
- `full-skill/`, `minimal-skill/` — full copies of `kestra-build/`, differing only in whether
  `SKILL.md`'s anti-patterns section is present
- `full-output/`, `minimal-output/` — the two generated `workflow.yaml` + `state.json` pairs, plus
  each run's own shipped verification scripts
