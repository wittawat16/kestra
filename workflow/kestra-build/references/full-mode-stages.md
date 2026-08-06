# Full-mode-only stage guidance

Read this file **only** when `mode: full` — none of it applies to a `mode: lite` workflow, since
lite's fixed shape (`generate-tests → freeze-tests → implement → {verify, review} → done`) never
contains `test-review`, more than one `implement-*` stage, or a shared-contract stage. If you're
deriving stages for a `lite` spec with no devops flag, skip this file entirely and go back to
`SKILL.md` step 3's inline rules — opening this file costs real tokens for content you won't use.

Two exceptions, both apply regardless of mode: `deploy-readiness` below (it appends to a lite
workflow too, on `needs_devops: true` — see its section for what changes), and the evidence-artifact
convention (writing an expensive computation's result to `<run-folder>/evidence/`), which matters
for a `lite` workflow whenever `review` or `verify` needs to run something costly. If one of those
is the only reason you are here, read just that section and skip the rest.

---

## `spec-review` — what it must actually check

**`spec-review` is the cheapest gate in the whole file — don't generate it as a formality.**
The obvious version of this stage checks that the spec file exists, is non-empty, and contains
an acceptance-criteria heading. That passes for any spec-shaped document, including one that's
confidently wrong, which makes it a stage that costs a step and buys nothing. Consider where
this stage sits: it runs before a single test exists, so a defect it catches costs one edit to
one document, while the same defect caught after the freeze costs a `reworking` bounce, and
caught after release costs whatever the release costs. Nothing else in the file has that ratio.
Give it real content to check: that the spec's **Runtime Invariants** each name what actually
happens on violation (and that none of them resolve to "log it and carry on," which is the
absence of an invariant described in the vocabulary of having one); that its **Reality
Constraints** are either filled in or explicitly marked not-applicable with a reason —
especially what each external dependency does *not* guarantee, since an empty answer there is
the seed of a test double that is never wrong in testing and never right in production; and
that these don't contradict the acceptance criteria or each other (an AC asserting an exact
result while a dependency is documented as not guaranteeing completeness is a contradiction
someone has to resolve now, not during implementation). Keep the enforcement mechanical the
same way `review` does it: the brief asks for the analysis and a written verdict artifact, and
`exit_criteria` greps that artifact for the verdict line. This is the same list `kestra-spec`'s
own step-6 self-check runs before handing the spec over — deliberately, so a spec produced by
that skill arrives having already cleared it and this stage costs one cheap pass instead of a
bounce; keep the two lists in sync if you change either. When the spec lacked these sections
and you inferred them (see `SKILL.md`'s **Inputs**), say so in the brief so this stage reviews the inference
rather than assuming a human already blessed it.

**Chain a mechanical pre-check ahead of the verdict grep.** This stage's `exit_criteria` runs the
run folder's **own** copy of `validate_spec.py`, emitted by `SKILL.md`'s step G2 (the single owner of
that `cp`, which emits all three scripts on every run, in either form) alongside `workflow.yaml`/`state.json` —
same convention as `harness/` and `evidence/` — so the frozen
`exit_criteria` field carries no dependency on the `kestra-build` skill being installed on
whatever machine later executes the workflow. Every path in it is repo-root-relative and the
command runs from the repo root, so set `exit_criteria.run` to
`python3 <run-folder>/validate_spec.py <source_spec> . && grep -q '^VERDICT: CLEAR$' <run-folder>/spec-verdict.md`
— the `.` is that repo root, the base the spec's Files-to-Touch paths resolve against.
The script only FAILs (non-zero exit) on facts that are both format-independent and fixable
within spec-review's own `write_scope` (the spec file itself) — a Files-to-Touch row marked
`edit`/`exists` whose path is absent; everything else (missing sections, empty columns, an
unparseable table) prints as `WARN` and never fails, so a foreign-format spec or `kestra-build`'s
own inferred-sections path still passes the mechanical layer. Because `kestra-run`'s context
pack already runs `exit_criteria.run` before every spawn (see its step 2), a `FAIL` line lands
in the reviewer's hands before it burns a single turn discovering the same thing itself. State
the delineation explicitly in the brief — **do not** reuse `test-review`'s "the mechanical checks
already ran, don't re-derive them" sentence verbatim, because the two stages' mechanical and
judgment layers don't split the same way: `test-review`'s script and its subagent check disjoint
things, while `validate_spec.py` and this stage's subagent read the *same* columns at different
depths. Say instead: "the mechanical layer verified presence/existence only — the semantic
content of every column is still yours to judge: no on-violation resolving to log-and-continue,
no contradiction between invariants/edge-cases/ACs, every AC testable, every checkable claim
actually run." A reviewer told the checks "already ran" in the borrowed phrasing can rationally
skip that semantic read, which is exactly the false-CLEAR-over-a-real-defect failure this whole
stage exists to prevent. Give it the same `on_fail` shape as `review`
too: `action: fixing`, `max_attempts: 2`, `escalate_at: 2`, `write_scope` covering both
`source_spec` itself (there's no separate stage to `target` the way `review` targets an
`implement-*` stage) and the `<run-folder>/spec-verdict.md` the brief tells it to write,
falling through to `reworking` only once that's exhausted or the same diff repeats — see
`design-principles.md`'s "Default HITL posture" for why a brief this substantive
shouldn't skip straight to the one human stop on its first finding.

## `test-review`

**Add a `test-review` stage between `generate-tests` and `freeze-tests` when — and only when — the
tests will contain test doubles.** The trigger is causal rather than a matter of taste: the defects
this stage exists to catch are all forms of *a double not matching the thing it stands in for*, and
a feature that fakes nothing cannot have them. Read the spec's **Reality Constraints**: if it lists
external dependencies, or names a pair of paths that must agree, generate the stage. If it lists
neither — pure logic over the project's own types — don't; that isn't cutting a corner, it's
declining to check for a bug that can't occur. Treat the answer as read off the spec, the same way
the `needs_*` flags are, not as a judgment call to re-open.

Everything mechanically detectable belongs in `generate-tests`'s `exit_criteria` instead — a linter
can't be talked out of its answer, so it needs no independent reviewer. What lands here is the part
that requires reading the doubles against the real thing they imitate. Give the stage
`write_scope: []` and `on_fail.action: fixing` with `target: generate-tests`, which is the same
mechanism `review` uses against `implement-*`: the reviewer owns no files but can direct a bounded
number of fixes inside the stage that does. This works only because the freeze hasn't happened yet
— after `freeze-tests`, no such loop is legal.

Ask the brief for a table with a row per risk below, each marked applicable or not with `file:line`
evidence, rather than a prose write-up. A prose reviewer reports what it noticed; a table forces an
answer for the rows it didn't. Where a row is applicable, the finding is what the double claims
versus what the dependency actually does per the spec's Reality Constraints.

| Risk | The double... | Recognized as |
|---|---|---|
| Ordering / preconditions | accepts any call sequence, while the real dependency enforces one | integration contract tests; consumer-driven contracts |
| Response realism | only ever returns complete, well-formed, happy-path data | test-double fidelity; prefer fakes over hand-written stubs |
| Type / shape drift | is hand-typed to an assumed shape rather than the real one | the "Mocks Aren't Stubs" fidelity gap |
| Path parity | stands in for one of two paths that must agree, with nothing comparing them | characterization / golden-master comparison |
| Own shared logic | replaces a guard or invariant this codebase owns, so the real one goes unexercised | inverse of "don't mock what you don't own"; Humble Object |
| Non-determinism | lets a live clock, RNG, locale, or environment leak into the test | non-hermetic (flaky) test; clock injection |

Sourcing and full citations for these are in
[`test-quality-taxonomy-research.md`](test-quality-taxonomy-research.md). They recur widely enough
to be worth asking about every time doubles exist, but they are a starting point rather than a
closed set — a data pipeline's characteristic failure is schema drift, a web app's is authorization
and N+1 queries, and neither is in the table. Tell the brief to add rows the spec and codebase
imply, and to say plainly when a row was added.

Give the brief one more sentence for the case where this stage runs again after a `fixing` attempt
on `generate-tests`: "On a re-review after a fixing attempt (the context pack will include the fix
diff and your own prior findings), verify the findings are addressed and review the changed lines
and their interactions with the rest of the suite; do not re-derive relations between unchanged
files already cleared, which the orchestrator's `write_scope` enforcement guarantees are unchanged."
This caps the recheck's cost without weakening it — a full-file re-review after a one-line fix has
no more to find than a scoped one, since nothing outside the diff could have changed.

### When the fold-in condition holds — and when it does not

**Reality Constraints listing an external dependency triggers `test-review` by the rule above
— but check what the *actual chosen test design* does before assuming that pass has real work
to do.** A spec can name an external dependency while `generate-tests` legitimately sidesteps
it (a real temp git repo instead of a mocked one, a real subprocess instead of a stub) — the
trigger condition is about what the spec's Reality Constraints *list*, not about what the tests
*actually contain*, so the two can diverge. Measured on a real run: a `test-review` stage
predicted in its own workflow-generation audit comment to be "fast/CLEAR-on-first-pass because
the test design uses real temp git repos, not mocks" ran twice anyway (~119k then ~105k tokens)
and was right both times — CLEAR with nothing to find. This is a *generation-time* decision, not
a run-time one: `kestra-build` makes it while writing `generate-tests`'s own brief, not after —
there is no run-time path where `kestra-run` drops or skips an already-generated `test-review`
stage; the stage list you emit is the stage list that runs (see design-principles.md and
`mode`'s "record of a decision" framing in `workflow-schema.md`). So: when the brief you are
writing for `generate-tests` mandates real fixtures (a real temp-repo helper, a real subprocess)
and its `exit_criteria` already enforces the absence of mock imports mechanically, don't generate
a `test-review` stage at all — fold its check into `generate-tests`'s own `exit_criteria` instead
(a static grep/check for real-fixture patterns — `execFile`, a real temp-repo helper — vs. mock-library
imports) rather than paying for a full separate subagent pass to confirm what the brief already
predicted. **This fold-in has one condition, not a blanket green light:** a real measured run
with no doubles at all still had its first `test-review` pass catch a genuine test-vs-test
contradiction (two frozen test files disagreeing about the same behavior) — a defect that is
double-independent and not something a mock-import grep can ever detect, since nothing about it
involves a double. So only take the fold when `generate-tests`'s own brief also gains an
explicit cross-file consistency self-check: "before finishing, cross-check assumptions shared
across test files — formats, fixtures, orderings — and name each pair you checked." If you omit
that instruction, say so plainly in the mode/stage audit line shown to the user ("test-review
folded in; cross-test-consistency is no longer independently reviewed") rather than letting the
loss pass silently — a self-check by the same stage that wrote the contradiction is weaker than
an independent reader catching it, and the user should get to see that trade-off, not just its
absence.

## Build the throwaway harness once per run, not once per stage — as a contract, never a bundled script

Proving a test is non-vacuous means mutating the code and checking the suite notices; the same goes
for a parity claim or a sweep over an input space. Measured on a real run, four separate agents each
wrote their own mutation harness, and each re-discovered from scratch which config files a sandbox
copy needs before the suite will even run there. The writing was never the expense — the
rediscovery was. And that knowledge is repo-specific, which is exactly why the fix is *not* to ship
a harness inside this skill: a harness has to be written in some language, and a Python one is dead
weight in a Go repo. Define the contract in the brief and let the first stage that needs one build
it in the project's own language:

- **takes** a set of mutants (a patch, or an edit described precisely enough to apply) plus the
  command that runs the suite
- **returns**, per mutant, whether the suite caught it — a surviving mutant is the finding
- **lives** in the run folder, e.g. `<run-folder>/harness/`, beside `state.json`; not in the repo's
  own source tree, and not in this skill

Tell every later stage's brief that the harness may already exist, where to look, and to extend it
rather than write a second one. Say plainly that it is scaffolding for this run and is not held to
the project's production standards — otherwise a stage will try to make it nice.

## Expensive evidence becomes an artifact other stages can read

*(relevant even outside `mode: full` — see the note at the top of this file)*

On one run, `review` ran a 200,001-case sweep against an exact oracle that `test-review` had
already run a variant of; neither could see the other's work, because there was nowhere to put it.
Add to the briefs: any computation costing more than a moment writes its result **and the exact
command that produced it** into `<run-folder>/evidence/`, and any stage about to compute something
checks `<run-folder>/evidence/` first and computes only what's missing. The command matters more than the
number — a result whose provenance isn't recorded can't be re-derived, and then a later stage is
trusting a figure it cannot check. Two guards worth stating in the brief: an `evidence/` file is
only valid for the commit it was computed against, so a stage reusing one after the code changed
must re-run it; and evidence is an input to judgment, never a substitute for it — a reviewer may
not clear a finding on the strength of an artifact it didn't verify or reproduce.

## Independent components default to sibling `implement-*` stages, not a chain

A monorepo feature touching e.g. `src/api/**` and `src/web/**` should get `implement-backend` and
`implement-frontend` both `depends_on: [freeze-tests]` directly — never one `depends_on` the other
just because they're both "part of the same feature." Chaining independent work is pure wasted
wall-clock: kestra-run already runs every stage in `current_stage` whose `write_scope`s don't
overlap in parallel (the same rule that makes `verify`/`review` siblings), so a spec-derived chain
here throws away parallelism the orchestrator would otherwise give you for free. Only chain two
`implement-*` stages when one's code genuinely can't be written until the other's lands (e.g.
frontend calling an endpoint whose exact response shape isn't decided yet) — that's a real
dependency, not just "same feature."

### Shared-contract stage for the one file both siblings need

If two otherwise-independent components both have to touch the same file — a `shared/types.ts`, an
OpenAPI schema, a proto definition — that alone doesn't justify chaining them or merging them into
one stage. Insert a small upstream stage (e.g. `define-shared-contract`) whose `write_scope` is
*only* that shared file. Both siblings `depends_on` this stage instead of each other, and only
*read* the shared file from then on — reading a file another stage owns is not a `write_scope`
collision, only writing it is. **Do not set `freeze_after: true` on this stage.**
`freeze_after`/`test_hash` is a dedicated mechanism that exists only to protect the frozen *tests*
from silent rewriting during `fixing` — there is exactly one `test_hash` in `state.json`, and it
must snapshot the test suite, never anything else. The shared-contract file doesn't need that
mechanism anyway: ordinary `write_scope` enforcement already protects it completely, since no stage
after `define-shared-contract` ever lists that path in its own `write_scope` — there's nothing more
to add. This keeps the bulk of the work (backend/frontend logic) parallel and isolates just the
genuinely-contested file into its own short sequential step. Don't reach for this by default — most
independent components share nothing; only add it when the spec genuinely requires a common
contract both sides depend on.

## Splitting `review` (and sometimes `verify`) per component

When there are 2+ sibling `implement-*` stages, split `review` one-per-component instead of a
single shared `review`** (e.g. `review-backend`/`review-frontend` alongside
`implement-backend`/`implement-frontend`), each `depends_on` every implement stage (still reading
the same final combined diff — review is read-only, so this doesn't cost extra coordination) but
with `on_fail.target` pointed at *its own* component's implement stage. This resolves a real gap a
single shared `review` can't: `on_fail.target` only accepts one stage id, so a monolithic `review`
covering two independent components has no correct answer for which one a `CHANGES_REQUESTED`
finding should route a fix to — defaulting to one component's implement stage (as if
`implement-backend` were the answer) silently mis-routes any frontend-only finding, giving it a fix
attempt against code that was never wrong. Splitting lets each review's findings land on the right
target automatically because there's no longer an ambiguous case to resolve. Same split logic
applies to `verify` if a spec's acceptance criteria are cleanly separable per component and a single
combined `verify` would hit the same targeting ambiguity — don't apply it reflexively to `verify`
when the criteria call for one true end-to-end check across components, though (that one may still
want a single `on_fail.target` default with the ambiguity called out in its brief, same as before).
`mode: lite` never has this problem — it has exactly one `implement-*` stage by definition, so
`review`/`verify` never need splitting.

## `deploy-readiness`

**Trigger, precisely:** the spec's `needs_devops` flag alone decides when it's present — never
overridden by keyword-scanning the spec text. Only fall back to scanning the spec text for NEW or
CHANGED env vars, DB migrations, feature flags, or infra changes (matching `kestra-spec`'s own flag
definition) when the spec is a foreign one with no flags table at all. "The spec text merely
*mentions* deploy-relevant terms" is not the trigger — an existing env var referenced but untouched
doesn't need a deploy checklist; a flag that's explicitly `false` should never be second-guessed by
a keyword hit elsewhere in the prose.

**Default: fold the checklist into `review`'s own brief and verdict artifact**, rather than a
separate stage — `review` already reads the same final diff a deploy-readiness pass would read, and
its value is read-and-report, not independence from `review` (the same reasoning `meta-review`
already applies to fold `meta-security` into one pass). `review` writes both
`<run-folder>/review-verdict.md` and `<run-folder>/deploy-checklist.md`; `exit_criteria.run` becomes
`grep -q '^VERDICT: CLEAR$' <run-folder>/review-verdict.md && test -f <run-folder>/deploy-checklist.md`.
This fold is safe **only** with checklist freshness mechanically enforced, not assumed:
- Revoke, for this combined stage specifically, the "a sibling that already passed doesn't need
  re-running" exemption `kestra-run`'s batch-fixing rule normally grants (see its step 6) — if a
  fixing attempt lands on `review`'s `on_fail.target` triggered by a *different* failing sibling
  (e.g. `verify`) after `review` itself already passed, the combined `review` stage re-runs too, so
  `deploy-checklist.md` never goes stale against a diff it was never written against.
- `done`'s `exit_criteria` additionally verifies `deploy-checklist.md` was written or committed at
  or after the last commit touching the implement stage's `write_scope` — a stale checklist fails
  `done` and routes back to `review` to refresh it, rather than silently shipping a checklist for an
  earlier diff.

**Keep `deploy-readiness` as its own stage instead** (between `review` and the terminal stage,
`write_scope: []`, brief asks for the checklist, naming whatever devops-focused skill you have as a
suggestion) whenever either enforcement point above can't be wired into the specific project/CI
setup, or the user explicitly asks for a distinct deploy milestone separate from code review. Skip
the stage/fold entirely when the spec has no devops flag — don't add it unconditionally the way
`review` is unconditional. Either shape appends to **either** mode: `needs_devops: true` is not a
row in `mode: lite`'s precondition table (see `SKILL.md`'s lite/full table) — a lite-shaped spec
that also sets `needs_devops: true` still gets the checklist (folded or standalone) before `done`,
on top of the lite stage list.
