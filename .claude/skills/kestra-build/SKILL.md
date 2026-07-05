---
name: kestra-build
description: >
  This skill should be used when the user asks to "generate a workflow from this spec", "turn this
  spec into a workflow.yaml", "produce a workflow.yaml + state.json", "design a TDD-locked pipeline
  definition", "make a generator output with stages, exit criteria, and on_fail blocks", references
  the Hermes orchestration notes, or wants a feature spec turned into an executable plan file
  before any code is written. Writes a workflow.yaml + state.json — a TDD-first stage machine with
  write-scope allowlists, a test-hash freeze, and a fixing→reworking escalation — then stops. Does
  NOT execute anything, call skills, write application code, or commit. If a workflow.yaml already
  exists and the user wants it run, executed, or resumed — that's kestra-run, not this skill.
---

# kestra-build — Workflow Generator

Turns a feature spec into a **`workflow.yaml` + `state.json`** pair: a declarative, TDD-first stage
machine that [`kestra-run`](../kestra-run/README.md) (the orchestrator) can execute deterministically.
kestra-build's job ends at the artifact. It never runs a stage, never calls a skill, never writes
application code, and never commits — that's kestra-run's job, not the generator's.

If the user actually wants agents dispatched and running right now — spec sharpened, code written,
verified — chain whatever specialized spec/plan/build/review skills or agents you have available
directly, not this. kestra-build is for when the shape of the pipeline itself is the deliverable.

---

## Why this shape (read before generating anything)

Three primitives make "freeze" real instead of aspirational. Every stage you generate must respect
all three, because the orchestrator that eventually reads your output has no other way to enforce
discipline than what you declared in the file:

1. **Write-scope allowlist** — enforced at apply time, not by asking the AI nicely. Each stage
   declares exactly which paths it may write. A `fixing` stage gets *code* paths, never test paths.
   If a stage's diff touches something outside its `write_scope`, the orchestrator rejects it — it
   doesn't matter what the stage "meant to do."
2. **Test-hash invariant** — the moment tests are generated and frozen, snapshot their hash into
   `state.json`. Every stage after that checks the hash before doing anything. A mismatch (AI
   silently "fixed" a test, or a human edited one by hand) halts the pipeline. This is what makes
   TDD a mechanical fact instead of a discipline you hope the model has.
3. **Commit-per-stage** — freeze, checkpoint, and rollback are the same commit. Each stage ends by
   committing code + artifacts + `state.json` together, with a commit message identifying the
   stage id (no `git tag` — the commit itself is the rollback point). Test freeze *is* the commit
   at the end of the tests stage. Rollback is `git reset` to that commit's SHA. Resume is reading
   `state.json` from `HEAD`. If you generate a stage without a clear commit point, the orchestrator
   has nothing to roll back to.

**Why TDD is a hard dependency, not a style choice:** tests written after/alongside code only move
false positives to the test itself (a green build on code that satisfies a shallow assertion is
*more* dangerous than an honest red, because now there's fake evidence backing it). Tests written
and frozen *before* implementation close that hole — the implementation stage can't rationalize its
way to green by narrowing what the test checks. What TDD does *not* fix: a spec that never
considered an edge case produces a test that never considered it either, and the implementation
stage will pass while missing that case. That residual risk belongs to spec review, not to this
generator — don't oversell what the stage machine catches.

**Why fixing escalates up, not sideways:** a failing test has exactly two honest resolutions —
fix the code, or admit the frozen spec/test was wrong. There's no third option where you patch the
test to match the broken code; that's the confirmation loop the whole design exists to prevent.
`fixing` may only ever touch non-test paths. When it's exhausted (attempt cap, or the same diff
reappearing — see `references/design-principles.md` for the semantic-diff no-progress check),
the *only* legal transition is `reworking`: unlock test-writing, go back to spec-review or
regenerate tests, re-freeze, reset attempt counters. Read `references/design-principles.md` before
you generate `on_fail` blocks — getting this transition wrong is the single most common way a
generated workflow quietly reintroduces the false-positive problem it was supposed to close.

Full source reasoning (state table, transition pseudocode, false-positive taxonomy) lives in
`references/design-principles.md` — read it once per session before generating stages, since the
`on_fail` and `freeze_after` fields you write are only correct if you understand why they exist.

---

## Inputs

kestra-build needs a spec with testable acceptance criteria. If the user hands you:
- **A structured spec** (e.g. an upstream PM/spec-sharpening skill's `0-spec.md`, with an
  `acceptance_criteria` list) — use it directly.
- **Prose or a rough ask** — sharpen it into a short numbered AC list first and show it back for a
  quick confirm before deriving stages. Don't silently invent acceptance criteria the user didn't say.

## Process

1. **Read or derive the spec.** Confirm the AC list with the user if you had to sharpen it yourself.
2. **Before writing any stage, fill in this exact table for the spec you're building for — as a
   literal table in your output, not a paraphrase or a mental note.** Confirmed by direct testing,
   three times: a smaller/faster model gets the *mechanical* parts of stage derivation right
   (write_scope non-overlap, sibling vs. chain, freeze_after placement) but silently drops
   conditional requirements that live in narrative prose. First attempt: told in prose to "write out
   yes/no for each flag first," it correctly reasoned through `needs_devops: false` (a flag whose
   correct handling is to do nothing) while still dropping `needs_ui: true` (a flag whose correct
   handling requires adding a stage) despite quoting that exact line elsewhere in its own output —
   a prose instruction to checklist is itself just more prose to skim past. Second attempt: the
   table below made it stop and address the flag, but it then treated the flag's *value* as still
   open to interpretation — reasoning "it's only one button, so no design stage needed" for a spec
   with `needs_ui: true`. **That reasoning is out of scope for this step.** These flags are set by
   whatever produced the spec (e.g. an upstream spec-sharpening step that sets `needs_ui: true` for
   *any* "new page, route, modal, OR changes to an existing screen layout, form, or interactive
   element" — a single added button already qualifies) precisely so this exact judgment call
   doesn't have to be re-litigated downstream. Treat each flag's `true`/`false` value as a decided
   fact handed to you, not a recommendation to weigh — the table's job is to force a *mechanical*
   value→stage mapping, not a second opinion on whether the upstream decision was proportionate to
   the work:

   | Flag | Value in spec | Stage added (id) — mechanical, not a judgment call |
   |------|---------------|------------------------------------------------------|
   | needs_ui | ? | *(true → a `design` stage exists; false → none; no in-between)* |
   | needs_ba | ? | ? |
   | needs_sa | ? | ? |
   | needs_devops | ? | ? |
   | (any other explicit stage request in the spec text) | ? | ? |

   Fill in every row for the actual spec before moving to stage derivation — a `Value` of `true` (or
   an explicit request in the spec text) with a `Stage added` of "none" is a contradiction you must
   resolve before continuing, not something to leave inconsistent. Include this table in what you
   show the user alongside the final workflow.yaml/state.json, so the inconsistency is visible to
   them too if you miss one.
3. **Derive the stage list from what the spec actually needs** — don't default to a fixed phase set.
   A minimal TDD-honest skeleton looks like:
   `spec-review → generate-tests (freeze point) → implement[-per-component] → {verify, review} →
   done`. Add stages only when the spec calls for them (e.g. a UI-facing spec adds a
   design stage before `generate-tests`; multiple independent components each get their own
   `implement-*` stage so their `write_scope`s don't collide).
   - **Independent components default to sibling `implement-*` stages, not a chain.** A monorepo
     feature touching e.g. `src/api/**` and `src/web/**` should get `implement-backend` and
     `implement-frontend` both `depends_on: [generate-tests]` directly — never one `depends_on` the
     other just because they're both "part of the same feature." Chaining independent work is pure
     wasted wall-clock: kestra-run already runs every stage in `current_stage` whose `write_scope`s
     don't overlap in parallel (the same rule that makes `verify`/`review` siblings below), so a
     spec-derived chain here throws away parallelism the orchestrator would otherwise give you for
     free. Only chain two `implement-*` stages when one's code genuinely can't be written until the
     other's lands (e.g. frontend calling an endpoint whose exact response shape isn't decided yet)
     — that's a real dependency, not just "same feature."
     - **Shared-contract stage for the one file both siblings need.** If two otherwise-independent
       components both have to touch the same file — a `shared/types.ts`, an OpenAPI schema, a
       proto definition — that alone doesn't justify chaining them or merging them into one stage.
       Insert a small upstream stage (e.g. `define-shared-contract`) whose `write_scope` is *only*
       that shared file. Both siblings `depends_on` this stage instead of each other, and only
       *read* the shared file from then on — reading a file another stage owns is not a
       `write_scope` collision, only writing it is. **Do not set `freeze_after: true` on this
       stage.** `freeze_after`/`test_hash` is a dedicated mechanism that exists only to protect the
       frozen *tests* from silent rewriting during `fixing` — there is exactly one `test_hash` in
       `state.json`, and it must snapshot the test suite, never anything else. The shared-contract
       file doesn't need that mechanism anyway: ordinary `write_scope` enforcement already protects
       it completely, since no stage after `define-shared-contract` ever lists that path in its own
       `write_scope` — there's nothing more to add. This keeps the bulk of the work
       (backend/frontend logic) parallel and isolates just the genuinely-contested file into its own
       short sequential step. Don't reach for this by default — most independent components share
       nothing; only add it when the spec genuinely requires a common contract both sides depend on.
   - **`verify` and `review` are siblings, not a chain — both `depends_on` the implement stage
     directly, not each other.** Confirmed by direct benchmarking: chaining them
     (`review: depends_on: [verify]`) costs a whole extra sequential subagent round-trip for no
     reason, because neither stage writes code (`write_scope: []` on both) — `review`'s diff is
     already final the moment `implement` passes, so it doesn't need to wait for `verify` to
     finish reading the same, unchanging diff. Making them siblings lets kestra-run's existing
     "independent stages with non-overlapping `write_scope` run in parallel" rule apply to them
     directly, cutting real wall-clock on every run where both happen to need a subagent (they
     often won't both need one — see the efficiency note in kestra-run's SKILL.md — but when they
     do, there's no reason to pay for it twice in sequence). The one wrinkle: if `verify` and
     `review` **both** fail and both `on_fail.target` the same `implement-*` stage, that's still
     one fix attempt with both sets of findings combined, not two competing ones — see
     `workflow-schema.md`'s note on this under `on_fail.target`.
   - **Default to zero `human_approval` stages.** Read `references/design-principles.md`'s
     "Default HITL posture" before generating `spec-review`, `review`, or the terminal stage — each
     of those defaults to a *mechanical* `exit_criteria` now (a sanity check, a verdict-artifact
     grep, a completion summary), not a stop-and-ask. The one place the design still always stops
     for a human is `fixing → reworking` once a bounded retry loop is exhausted or stuck — that
     stays as-is, it's not something this change touches. Only add an actual `human_approval` stage
     when the user explicitly asks for a manual milestone (e.g. "I want to sign off myself before
     this touches prod") — ask, don't assume, the same as any other scope decision.
   - **`review` is not optional — always include it, right before the terminal stage.** It's a
     mechanical exit_criteria stage (`write_scope: []`, no `freeze_after`) whose brief asks whatever
     gets spawned to review the real diff for correctness/edge-cases *and* injection/authn/secrets
     risk, writing a `VERDICT: CLEAR` / `VERDICT: CHANGES_REQUESTED` artifact that `exit_criteria`
     greps — naming whatever code-review and security-review skills you have available as suggested
     skills for this stage, the same "suggestion, not a hard binding" pattern as every other skill
     mention. Passing tests only prove the spec's own acceptance criteria; they say nothing about
     code quality or security holes the spec never thought to test for — that's a distinct risk
     `review` exists to catch, not something `verify` already covers. On `CHANGES_REQUESTED`,
     `on_fail.action: fixing` with `target: <the implement stage's id>` gives the implementation a
     bounded number of attempts to address the findings before this escalates to `reworking` — see
     `workflow-schema.md`'s `on_fail.target` field.
     - **When there are 2+ sibling `implement-*` stages, split `review` one-per-component instead
       of a single shared `review`** (e.g. `review-backend`/`review-frontend` alongside
       `implement-backend`/`implement-frontend`), each `depends_on` every implement stage (still
       reading the same final combined diff — review is read-only, so this doesn't cost extra
       coordination) but with `on_fail.target` pointed at *its own* component's implement stage.
       This resolves a real gap a single shared `review` can't: `on_fail.target` only accepts one
       stage id, so a monolithic `review` covering two independent components has no correct answer
       for which one a `CHANGES_REQUESTED` finding should route a fix to — defaulting to one
       component's implement stage (as if `implement-backend` were the answer) silently mis-routes
       any frontend-only finding, giving it a fix attempt against code that was never wrong. Splitting
       lets each review's findings land on the right target automatically because there's no longer
       an ambiguous case to resolve. Same split logic applies to `verify` if a spec's acceptance
       criteria are cleanly separable per component and a single combined `verify` would hit the
       same targeting ambiguity — don't apply it reflexively to `verify` when the criteria call for
       one true end-to-end check across components, though (that one may still want a single
       `on_fail.target` default with the ambiguity called out in its brief, same as before).
   - **If the spec sets (or implies) a devops-relevant flag — e.g. `needs_devops: true` from an
     upstream spec, or the spec text itself mentions env vars, DB migrations, feature flags, or
     infra changes — add a `deploy-readiness` stage** between `review` and the terminal stage.
     `write_scope: []`, brief asks for a pre-deploy checklist (env vars, migration order + rollback,
     feature flags, deploy order, monitoring), naming whatever devops-focused skill you have as the
     suggested skill. Skip this stage entirely when the spec has no such flag/signal — don't add it
     unconditionally the way `review` is unconditional.
   - **End with a mechanical `done` stage**, not `waiting_approval` — `write_scope` scoped to a
     single summary file, `exit_criteria.type: artifact_exists` on a generated completion summary.
     By the time execution reaches it, every judgment-bearing check already ran and already had its
     own escalation path; there's nothing left for a human to approve that hasn't already been
     mechanically or automatically checked.
4. **For every stage, fill in:** `id`, `depends_on`, `brief`, `write_scope`, `exit_criteria`,
   `on_fail`, and `freeze_after` (true only on the stage that generates tests — see schema for the
   full field list). Write `brief` as plain instructions for whatever Claude eventually gets
   spawned to do the stage's work — never a skill name as a hard dependency. You're generating this
   inside a live Claude session right now, so you can see your own `available_skills`; if one is
   genuinely relevant to a stage (e.g. an implementation-focused skill for an implement stage), name
   it *inside the brief text* as a suggestion worth trying, not as a required binding. The workflow
   may execute on a different machine with a different skill set later — the enforcement fields
   (`write_scope`, `exit_criteria`, `on_fail`) must keep working with or without any specific skill
   installed. **Keep each brief proportionate to what it's actually verifying new.** A brief that
   asks a stage to re-derive evidence the mechanical `exit_criteria` check already produces (e.g.
   "run the test suite and paste the output" when `exit_criteria.run` already does exactly that)
   just burns an extra subagent round-trip for zero new information — every stage's real work gets
   independently re-verified by kestra-run anyway, so the brief only needs to ask for what isn't
   already mechanically covered. Confirmed by direct benchmarking: a `verify` stage brief that says
   "also manually exercise the API end to end" pays off when it targets a property the frozen tests
   genuinely don't cover yet, but the same instruction applied blanket-style across every stage
   multiplies token/time cost without multiplying confidence. When a stage's automated exit_criteria
   already proves the property, say so in the brief and let it stop there.
5. **Write `workflow.yaml`** — schema and a full worked example in `references/workflow-schema.md`.
6. **Write `state.json`** — initial state matching the stage list, schema + example in
   `references/state-schema.md`. All stages start `pending`, `test_hash: null`, `seen_diffs: []`.
7. **Dry-run it before showing it to the user.** Run
   `python3 <skill-dir>/scripts/validate_workflow.py <output-dir>` — a dependency-free, zero-LLM
   structural check (no third-party packages, works with a plain `python3`) that catches exactly
   the mistakes this file's own anti-pattern list warns about: `write_scope` overlapping the frozen
   test paths, a missing `on_fail.target` on a `write_scope: []` fixing stage, a dependency cycle, a
   stage unreachable from any start stage, `freeze_after: true` on more than one stage, and
   independent stages with colliding `write_scope`s that kestra-run might run in parallel. This is a
   mechanical graph/set check, not a judgment call — the same "run the real command, don't eyeball
   the diff" standard kestra-run's own enforcement holds itself to, just applied here before the
   first stage ever executes instead of after. If it reports `FAIL`, fix the stage list and re-run
   before moving on — don't show a workflow to the user that this check already knows is broken. A
   `WARN` is worth mentioning to the user but isn't a blocker (e.g. a plausible write_scope overlap
   between two stages that are actually fine because their globs don't really collide in practice —
   the checker is deliberately conservative and can over-flag).
8. **Show both files plus a short plain-language walkthrough** of the stage sequence — what happens,
   in what order, and why a given stage got the `write_scope` or `on_fail` it did — so the user can
   sanity-check before treating it as frozen. Mention that step 7's dry-run passed (or note any
   `WARN`s that are worth a second look).

## Output location

Default to `<repo>/<feature-id>/workflow.yaml` and `<repo>/<feature-id>/state.json` next to the
spec you generated from (e.g. alongside `workflows/runs/<feature-id>/0-spec.md` if that's where the
spec lives). Ask if the repo has a different convention already.

## Anti-patterns — don't generate these

Most of the anti-patterns below are exactly what `scripts/validate_workflow.py` (step 7) checks for
mechanically — read them anyway, since the dry-run tells you *that* something's wrong, not why it
matters or how to fix it well.

- A stage's `write_scope` including test paths when that stage isn't `generate-tests` or an
  unlocked `reworking` pass. This is the single most common way to silently defeat the whole design.
- A "replan" stage, or any `on_fail`/branching condition that reads like a programming language.
  Branching stays declarative — conditions may only reference an artifact's existence or an exit
  code, nothing more expressive. If the user wants real replanning mid-run, say so explicitly rather
  than smuggling it in as a fancy condition.
- `generate-tests` (or whichever stage produces the frozen tests) missing `freeze_after: true`. That
  flag is the only thing that tells the orchestrator to snapshot the test-hash — skip it and the
  whole invariant silently doesn't exist.
- A `fixing` block without both `max_attempts` and `escalate_at`, or a `reworking` transition that
  doesn't reset `attempt`/`seen_diffs` and re-freeze. Half-specified transitions are how a generated
  workflow ends up looping forever or escalating too eagerly.
- A `write_scope` for an implementation stage that's too narrow to ever legitimately pass — e.g.
  scoping `implement-*` to `src/**` only when the test runner needs repo-root config (a
  `conftest.py`, `pytest.ini`, `pyproject.toml`'s `pythonpath`, a `test/__init__.py`) to resolve
  imports at all. Confirmed by direct testing: this produces a stage that fails identically on
  every attempt no matter what the implementation does, and burns through `max_attempts` into a
  `reworking` escalation that blames the wrong thing (the spec/tests look "wrong" when the real
  issue is a scoping gap). Test-runner plumbing needed for the tests to even be *collectible/
  runnable* belongs in the `generate-tests` stage's `write_scope` (it's test infrastructure, not
  application code) — verify the exact `exit_criteria.run` command actually succeeds standalone
  before freezing the stage list, don't assume it will.
- Chaining `implement-*` stages for independent components (`implement-frontend: depends_on:
  [implement-backend]`) just because they belong to the same feature or spec. If their
  `write_scope`s don't overlap, there's no reason for one to wait on the other — kestra-run's
  parallel-stage rule only kicks in when the stage list itself doesn't impose a false ordering.
  A generated workflow with this shape runs no faster than doing the whole feature as one stage,
  defeating the entire reason to split by component in the first place.
- Putting `freeze_after: true` on a `define-shared-contract` stage (or any stage other than the one
  that generates tests). Confirmed by direct testing: this makes `test_hash` snapshot the shared
  file instead of the test suite, so the frozen tests end up with zero protection against being
  silently rewritten during `fixing` — the exact false-positive hole the whole invariant exists to
  close. `write_scope` enforcement alone already protects a shared-contract file (no later stage's
  `write_scope` includes that path); it does not also need `freeze_after`.
- Reaching for a `define-shared-contract` stage (or, worse, merging independent components back
  into one `implement-*` stage) when nothing is actually shared. This split only earns its keep
  when two siblings truly can't avoid writing the same file — check `write_scope`s for a real
  overlap before adding it, don't add it defensively "just in case" a monorepo spec might share
  something.
- Skipping the `review` stage. Confirmed by direct testing: without it, a generated workflow's
  only quality gate after tests pass is whatever the terminal stage does — and since that's now a
  mechanical summary stage, not a human eyeballing the diff, there'd be *no* pass at all checking
  for injection/authn/secrets risk or correctness issues the spec's own ACs didn't happen to test
  for. `review` is cheap to add (`write_scope: []`, one more mechanical verdict-check stage) and
  closes a real gap, not a hypothetical one.
- A `review`/`verify`-type stage with `write_scope: []` and `on_fail.action: fixing` that omits
  `target`. Without it the orchestrator has no legal write_scope to apply the fix within — either
  the fix attempt silently violates `write_scope: []`, or the stage can never recover short of
  jumping straight to `reworking` on the first `CHANGES_REQUESTED`, which defeats the point of
  giving it a bounded retry at all.
- Defaulting `spec-review`, `review`, or the terminal stage back to `human_approval` out of habit.
  That was the old default; it isn't anymore. Read `references/design-principles.md`'s "Default
  HITL posture" before generating any of these three — a `human_approval` stage should only appear
  when the user explicitly asked for that specific checkpoint.
- A hard-coded `skill:`/`agent:` field naming a specific skill as a required dependency for a stage.
  Skills aren't invoked by ID from outside a Claude session — whatever Claude gets spawned decides
  for itself, the same way triggering works normally. A skill name only ever belongs inside `brief`
  as a suggestion; if it's missing at execution time, the stage must still be able to proceed.
- A `generate-tests` `exit_criteria` that actually *runs* the test suite expecting it to pass
  (exit 0). At this stage no implementation exists yet, so the tests are *supposed* to fail red —
  an exit_criteria phrased that way makes the stage structurally unable to ever pass, no matter how
  correct the tests are. Confirmed by direct testing: this is exactly why the worked example above
  uses `npm test -- --listTests <feature>` (enumerate matching tests, don't execute them) instead
  of `npm test`. For pytest, the equivalent trap is subtler — `pytest --collect-only` still imports
  the test module to discover its test functions, so it fails on the same `ModuleNotFoundError` a
  full run would; use something that doesn't import the implementation at all, like
  `python3 -m py_compile <test-file>` (syntax-checks the test without executing or importing it).
  Whatever language/framework the spec uses, verify the exact `exit_criteria.run` command can
  actually pass *before* any implementation exists — the same "run it standalone before freezing"
  discipline as the write_scope anti-pattern above, just checking polarity instead of scope.
- A `generate-tests` brief for an AC about surviving a restart (data/state must persist across a
  process going down and coming back up) that reaches for an in-process simulation — closing and
  reopening the same object/connection inside one continuous test process — instead of a real
  process restart. Don't reason your way into "a true OS-process restart is impractical inside a
  single test run" before checking: most test runners can spawn a real child process, send it a
  kill signal, and spawn a fresh one against the same on-disk state without much ceremony (Node:
  `child_process.spawn` + `SIGTERM` + wait-for-ready + spawn again; Python: `subprocess.Popen` +
  `.terminate()` + relaunch; most other stacks have an equivalent). Confirmed by direct
  benchmarking: a `with_skill` run's `generate-tests` stage wrote exactly this "impractical"
  reasoning and shipped an in-process close/reopen test, while a same-task baseline run (no
  orchestration, same AC) wrote a real spawn/kill/respawn test in one pass with no more effort. The
  in-process version only proves an object was recreated correctly — it doesn't prove the property
  the AC actually cares about (data surviving the *process* disappearing, not just an in-memory
  handle). Default to the real restart; only fall back to an in-process simulation if the specific
  runtime/environment genuinely can't manage a child process from within a test (rare, and say so
  explicitly in the brief when you do).

## What kestra-build does not do

- Does not execute the workflow, call any skill, write application code, or commit anything.
- Does not add a `human_approval` stage on its own initiative — the default template has none (see
  `references/design-principles.md`'s "Default HITL posture"). If the user wants a manual milestone
  beyond that default, ask, don't assume.
- Does not replace whatever spec→plan→build→review agent/skill pipeline you already use — if the
  user wants agents dispatched and running right now, point them there instead.
