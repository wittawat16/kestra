# Full-mode-only stage guidance

Read this file **only** when `mode: full` — none of it applies to a `mode: lite` workflow, since
lite's fixed shape (`generate-tests → freeze-tests → implement → {verify, review} → done`) never
contains `test-review`, more than one `implement-*` stage, or a shared-contract stage. If you're
deriving stages for a `lite` spec with no devops flag, skip this file entirely and go straight to
`SKILL.md` step 4 — opening this file costs real tokens for content you won't use.

Two exceptions, both apply regardless of mode: `deploy-readiness` below (it appends to a lite
workflow too, on `needs_devops: true` — see its section for what changes), and the evidence-artifact
convention just below this note.

The one exception: the evidence-artifact convention below (writing an expensive computation's
result to `<run-folder>/evidence/`) can matter for a `lite` workflow too, if `review` or `verify`
ever needs to run something costly. If that's the only reason you're here, read just that
subsection and skip the rest.

---

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
checks `evidence/` first and computes only what's missing. The command matters more than the
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
already applies to fold `meta-security` into one pass). `review` writes both `review-verdict.md` and
`deploy-checklist.md`; `exit_criteria.run` becomes
`grep -q '^VERDICT: CLEAR$' review-verdict.md && test -f deploy-checklist.md`. This fold is safe
**only** with checklist freshness mechanically enforced, not assumed:
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
