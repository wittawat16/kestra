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
- **A structured spec** (e.g. `kestra-spec`'s `0-spec.md`, or an upstream PM/spec-sharpening skill's
  output, with an `acceptance_criteria` list and populated `needs_*` flags) — use it directly.
- **Prose or a rough ask, with no spec yet** — don't sharpen it yourself here. Run the `kestra-spec`
  skill first (it produces the same kind of build-ready `0-spec.md` in one pass — testable ACs,
  flags, runtime invariants, dependency constraints, and a verified codebase survey — so stage
  derivation below isn't working from guesses), then come back and use its output. Only sharpen
  inline yourself if `kestra-spec` genuinely isn't available in this environment; if you do, sharpen
  into a short numbered AC list and show it back for a quick confirm before deriving stages — don't
  silently invent ACs the user didn't say.

**When a spec arrives without the sections this file expects.** Not every spec comes from
`kestra-spec` — a perfectly good `0-spec.md` from another tool, or one written before a section
existed, may carry acceptance criteria and flags but no **Runtime Invariants** and no **Reality
Constraints** (what external dependencies actually do and don't guarantee, pairs of paths that must
agree, non-deterministic inputs that need pinning). Those sections drive real stage content below,
so their absence is a gap to close rather than a section to skip. Derive what you honestly can from
the codebase survey and the spec's own text — a dependency the feature plainly calls, a scheduled
job that plainly reads the clock — then **label each derived item as inferred rather than
specified** when you show the workflow to the user. That distinction carries weight: something the
spec stated is a decision a human made and stands behind, while something you inferred is a
plausible guess that deserves a second look before it hardens into a stage's `exit_criteria`.
Presenting the two as equivalent is how a guess quietly acquires the authority of a requirement.

---

## Lite mode vs full mode — decide this before deriving stages

The full stage list buys one thing: it catches a **false pass that nobody would otherwise notice**
— an implementation that went green by narrowing a test, a double that was never wrong in testing
and never right in production, a security hole the acceptance criteria never thought to ask about.
That is worth several subagent round-trips on work where a silent wrong answer survives to
production. It is not worth them on work where the first run tells you the answer.

So the mode is a function of the spec, decided mechanically before step 3, not a preference:

**Generate `mode: full` if ANY of these hold. Otherwise generate `mode: lite`.**

| Condition | Read it off | Why full |
|---|---|---|
| 2+ independent components | the spec's Files-to-Touch spanning genuinely separate write scopes | sibling `implement-*`/`review-*` stages only exist to be split; lite has nothing to parallelize |
| The tests will contain test doubles | the spec's **Reality Constraints** listing any external dependency, or any pair of paths that must agree | this is the exact and only trigger for `test-review` — no doubles, no defect for it to find |
| `needs_devops: true` | the flags table | `deploy-readiness` has real content to check |
| Runtime Invariants is non-trivial | the spec's **Runtime Invariants** having rows whose violation is silent in production | a dedicated `spec-review` earns its round-trip when there's something to contradict |
| The user asked for full | their words | their call, not yours |

Ambiguity resolves toward **full** — the cost of a wrong `lite` is a missed defect, the cost of a
wrong `full` is a slower run. State which condition (or the absence of all of them) decided it when
you show the workflow to the user, so the choice is auditable rather than a mood.

### What lite actually is

Lite is the same machine with the same three primitives — **write-scope allowlist, test-hash
freeze, commit-per-stage — all still present, none of them optional.** A lite workflow is still
TDD-locked; the freeze stage still exists and still sets `freeze_after: true`. What lite drops are
the stages that had nothing to examine on this particular spec:

```
generate-tests → freeze-tests (freeze point) → implement → {verify, review} → done
```

| Full stage | In lite | Why |
|---|---|---|
| `spec-review` | **folded into `generate-tests`'s brief** | not dropped — the checks still run, they just don't get a subagent of their own. Ask the brief to reconcile the ACs against the spec's invariants/constraints and say plainly if it finds a contradiction, before writing a single test |
| `generate-tests` | kept | — |
| `test-review` | **dropped** | its trigger is the presence of test doubles, and the lite condition table already established there are none |
| `freeze-tests` | kept, unchanged | the freeze is the point of the whole thing; a "lite" mode that skips it is not this skill |
| `implement-*` | kept, exactly one, `effort: low` | the lite condition table already established there's one component and nothing heavy to reason about — set `effort: low` automatically here (never `model`, that stays opt-in — see the `effort`/`model` sections in `references/workflow-schema.md`) |
| `verify` | kept | costs no subagent — `write_scope: []` with an `exit_criteria.run`, which kestra-run executes directly (see its efficiency notes) |
| `review` | kept, unconditional | passing tests say nothing about injection/authn/secrets or a missing runtime guard. This is the one judgment stage lite keeps, and the reason lite is still safe to use |
| `deploy-readiness` | **dropped** | `needs_devops: false` was a precondition of choosing lite |

Net effect on a typical single-component feature: three subagent-bearing stages instead of six or
seven, with the freeze and the security/correctness review both intact.

**Do not invent further savings.** Merging `verify` into `review`, skipping `review` because the
diff looks small, or dropping `freeze-tests` to save a commit are not lite — they're the full
machine with its load-bearing parts removed, and each has its own entry in the anti-pattern list
below. Lite is a fixed, named shape, not a license to trim per-spec.

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

   | Flag | Value in spec | Consequence — mechanical, not a judgment call |
   |------|---------------|-----------------------------------------------|
   | mode | ? | *(the lite/full decision above — record which condition forced `full`, or note that none did)* |
   | needs_ui | ? | *(true → a `design` stage exists; false → none; no in-between)* |
   | needs_ba | ? | *(true → resolved upstream: the spec must already carry a Business Rules section — cite it, or raise its absence as a spec gap. No stage.)* |
   | needs_sa | ? | *(true → resolved upstream: the spec must already carry a Solution Architecture section — cite it, or raise its absence. No stage.)* |
   | needs_devops | ? | ? |
   | (any other explicit stage request in the spec text) | ? | ? |

   Two of these flags resolve to a stage and two resolve to *content that must already exist in the
   spec*, because the work they represent is done inline by whatever sharpened the spec rather than
   deferred to execution. That asymmetry is easy to misread as an inconsistency, so it's spelled out
   in the table itself: for `needs_ba`/`needs_sa` the mechanical check is "the corresponding section
   is present and non-empty," and a `true` flag with the section missing is a real defect to surface
   — the spec claims work was done that isn't in the file. Don't invent a stage to compensate;
   kestra-build has no vocabulary for one, and manufacturing a stage to satisfy a table is worse
   than reporting the gap.

   Fill in every row for the actual spec before moving to stage derivation. A `Value` of `true` with
   a `Consequence` that neither names a stage nor cites the spec section is a contradiction you must
   resolve before continuing, not something to leave inconsistent. Include this table in what you
   show the user alongside the final workflow.yaml/state.json, so the inconsistency is visible to
   them too if you miss one.
3. **Derive the stage list from what the spec actually needs** — don't default to a fixed phase set.
   **If step 2 settled on `mode: lite`, the stage list is already fixed** by the lite shape above —
   generate exactly those stages and skip ahead to step 4; the per-stage guidance below still
   applies in full to each stage lite keeps (`generate-tests`'s exit_criteria polarity,
   `freeze-tests`'s write_scope, `review`'s verdict artifact and `on_fail.target`), so read it for
   those, not for whether to add more stages. **Do not open
   [`references/full-mode-stages.md`](references/full-mode-stages.md) for a lite spec** — every
   stage it covers (`test-review`, sibling `implement-*`, shared-contract, `deploy-readiness`)
   is structurally impossible under the lite shape, so reading it costs real tokens for nothing a
   lite workflow can use. Measured directly: skipping it is the difference between `kestra-build`
   staying flat-cost on a trivial spec and paying a fixed tax for guidance that never applied. The
   rest of this step is the `mode: full` path, and it's where that file's content is actually
   needed — open it once you reach the bullets below that say so.
   A minimal TDD-honest skeleton looks like:
   `spec-review → generate-tests → freeze-tests (freeze point) → implement[-per-component] →
   {verify, review} → done`. Add stages only when the spec calls for them (e.g. a UI-facing spec
   adds a design stage before `generate-tests`; multiple independent components each get their own
   `implement-*` stage so their `write_scope`s don't collide).
   - **Writing the tests and freezing them are two stages, not one.** It's tempting to put
     `freeze_after: true` straight on `generate-tests` and save a step, and earlier versions of this
     file did exactly that. The reason to separate them: the freeze exists to stop an
     *implementation* from rewriting a test to make itself green, and no implementation exists yet
     when the tests are first written. Locking at that moment protects nothing that needs
     protecting, while removing the only cheap opportunity to fix a defect *in the tests* — after
     the lock, every such fix costs a `reworking` bounce, which is the design's one guaranteed
     human stop. So `generate-tests` owns the test paths and does not freeze; `freeze-tests` owns
     the same paths, sets `freeze_after: true`, and is the deliberate act of accepting what was
     written. It writes nothing — its `exit_criteria` re-runs the same static checks against the
     exact commit being frozen, which is worth doing precisely because that commit is the one every
     later stage will be held to.

     **Choose the freeze stage's `write_scope` deliberately; it defines the test-hash.** The
     anti-pattern list below tells you to give the test-writing stage whatever runner plumbing the
     suite needs to be collectible at all. That's right for `generate-tests` — but copying the same
     globs onto `freeze-tests` verbatim decides something else entirely, because everything in that
     scope becomes part of the hash, and any later change to it is a hard stop rather than a retry.
     A dependency manifest is the case where this bites: it holds test configuration *and* the
     dependency list, so freezing it means an unrelated version bump during implementation halts the
     pipeline with a message about frozen tests being tampered with. Freeze what determines what the
     tests *mean* — the test sources, and config that changes how they run — and keep churn-prone
     files out of it, even when the writing stage legitimately needed to create them. When a project
     genuinely can't separate the two, say so in the brief rather than leaving the next person to
     discover it from a confusing halt. Its `on_fail` is `reworking`, not `fixing`: if the tests no longer
     pass their own checks at the moment of freezing, something is wrong upstream and quietly
     patching them here would bypass whatever review already approved them.
   - **Optionally split `generate-tests` itself into a `design-tests` stage (scenario list) and a
     `generate-tests` stage (test code)** when the spec has enough ACs/BRs/edge cases that
     scenario-coverage gaps are a real risk on their own, independent of the code that will
     eventually express them — same reasoning as the writing/freezing split above, one level
     earlier. `design-tests` writes nothing but a table (AC/BR/edge-case → scenario title →
     Given/When/Then), `depends_on` the same stage `generate-tests` would have, `write_scope`d to
     that table artifact only, `exit_criteria.type: artifact_exists`. `generate-tests` then
     `depends_on: [design-tests]` and translates the approved table into real test code 1:1 —
     its own judgment burden shrinks to "does this code match the plan," not "did I think of
     everything," so a coverage gap is a one-row table edit instead of a rewritten test file. Skip
     this split on a small/simple spec — it's overhead when there's nothing near enough to a
     coverage gap to be worth a dedicated stage for. Two traps, both hit on a real attempt: if the
     `generate-tests` brief already enumerates every scenario by name (BRs, edge cases, states),
     the plan table just duplicates the brief at the cost of a full extra spawn — the split only
     pays when the brief *can't* enumerate everything up front; and on a `needs_ui` spec,
     `design-tests` must stay downstream of `design`, because running them as parallel siblings
     means design.md's screen states can't appear in a plan written before design.md exists, while
     `generate-tests` is simultaneously forbidden from inventing rows the plan lacks — a coverage
     gap with no legal path to close it.
   - **`spec-review` is the cheapest gate in the whole file — don't generate it as a formality.**
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
     and you inferred them (see **Inputs**), say so in the brief so this stage reviews the inference
     rather than assuming a human already blessed it.
   - **`test-review`, the harness contract, evidence-artifact reuse, and sibling `implement-*` /
     shared-contract stages are covered in
     [`references/full-mode-stages.md`](references/full-mode-stages.md) — open it now, this is the
     point in the process where you need it.** In short: add `test-review` only when the spec's
     Reality Constraints list external dependencies or a pair of paths that must agree; give any
     stage that needs to prove a test non-vacuous a shared, per-run mutation-harness *contract*
     (never a bundled script — it has to be written in the project's own language) living under
     `<run-folder>/harness/`; route expensive computation through `<run-folder>/evidence/` with the
     producing command recorded, so two stages never redo the same sweep; and give independent
     components sibling `implement-*` stages (never a chain) unless they share one contested file,
     in which case a small upstream `define-shared-contract` stage isolates just that file. The
     reference file has the full reasoning, the risk table `test-review`'s brief should use, and the
     measured evidence behind each rule — read it there rather than here.
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
     - **Specify the verdict artifact's shape in the brief — every stage that writes one
       (`spec-review`, `test-review`, `review`).** Left unspecified, these come back as multi-page
       prose, and the stage spends turns composing something no one reads that way: the gate greps a
       single line, and the only other consumer is a later stage that needs the claims and where to
       check them. Ask for, in order: the verdict line, exactly `VERDICT: CLEAR` or
       `VERDICT: CHANGES_REQUESTED` as the first line; then a findings table with one row per
       finding — severity, the claim in one line, and `file:line`; then paths into `<run-folder>/evidence/`
       for anything that took real computation to establish. Give the reason in the brief rather
       than just the format, because a reviewer told only "be brief" will drop findings to comply.
       The shape has room for as many rows as there are findings; what it cuts is narration, not
       substance. And say explicitly that a finding needing more explanation than a row holds gets
       its row *plus* a short paragraph below the table — a format that suppresses a real finding
       has cost more than the prose ever did.
     - **A reviewer challenging a numeric claim must state the quantity it measured and paste the
       command.** On a real run, one `spec-review` pass (179,460 tokens) existed solely because a
       reviewer measured a different quantity than the spec did — an `abs()`-symmetric, ungated
       deviation where the spec meant a one-sided shortfall at the decisive comparison — reported it
       as a defect, and withdrew it when asked to show its work. The asymmetry is what makes this
       worth a line in the brief: stating the quantity costs the reviewer one sentence, while a
       mismeasured finding costs a whole extra stage cycle to resolve. So: a numeric finding names
       the quantity, the inputs, and the exact command or script, with the output pasted. A numeric
       finding without them isn't a finding yet.
     - **When there are 2+ sibling `implement-*` stages**, `review` (and sometimes `verify`) needs
       splitting one-per-component so `on_fail.target` has an unambiguous single stage to route a
       fix to — see the "Splitting `review`" section of
       [`references/full-mode-stages.md`](references/full-mode-stages.md) for the full reasoning.
       Never applies under `mode: lite`, which has exactly one `implement-*` stage by definition.
   - **If the target repo declares its own mandatory pre-merge test gate, generate a stage that
     runs it — don't leave it as a suggestion in a brief.** Projects that have been burned by
     doubles drifting from reality often already have the fix: a recorded contract suite, a local
     fake of the real service, an integration target that must pass before merge, written down in
     `CLAUDE.md` or the repo's own docs. Whether it exists is a fact to look up during the codebase
     survey, not something to assume either way. When it does exist, the difference between a
     mention in a `brief` and a stage with `exit_criteria` is the difference between a convention an
     agent may recall and one it cannot skip — and a gate the project already declared mandatory is
     exactly the kind that shouldn't depend on recall. Give it `write_scope: []`, an
     `exit_criteria.run` that invokes whatever command the repo documents, and
     `on_fail.action: fixing` with `target` pointing at the implement stage. Place it as a sibling
     of `verify`/`review` — all three read the same finished diff and none of them writes, so
     chaining them only costs wall-clock. Name the gate as the repo documents it rather than
     inventing a name, and if the documented command doesn't run standalone, say so instead of
     generating a stage that can never pass.
   - **If the spec sets (or implies) a devops-relevant flag, add a `deploy-readiness` stage** —
     see [`references/full-mode-stages.md`](references/full-mode-stages.md) for what it checks and
     why. Never applies under `mode: lite`, which requires `needs_devops: false` as a precondition
     of choosing lite in the first place.
   - **End with a mechanical `done` stage**, not `waiting_approval` — `write_scope` scoped to a
     single summary file, `exit_criteria.type: artifact_exists` on a generated completion summary.
     By the time execution reaches it, every judgment-bearing check already ran and already had its
     own escalation path; there's nothing left for a human to approve that hasn't already been
     mechanically or automatically checked.
4. **Before writing briefs, ask the user once whether they have a preferred skill for any stage**
   (e.g. "use `meta-dev` for implementation", "use `meta-qa` for verify") — don't guess or default
   silently. This matters because of an observed failure mode: a brief that names a skill only
   generically ("an implementation-focused skill, if you have one installed, fits this stage well")
   was measured, across real `kestra-run` spawns, to never actually get picked up — the spawned
   subagent just does the work directly without invoking any skill, because generic phrasing gives
   it nothing concrete to match against. A named preference fixes this: put it in the brief as
   "Use the `<skill-name>` skill for this stage" rather than the generic hedge. If the user has no
   preference, keep the generic phrasing (still a suggestion, never a hard dependency — see below)
   and say so plainly rather than picking a skill on their behalf.
   **For every stage, fill in:** `id`, `depends_on`, `brief`, `write_scope`, `exit_criteria`,
   `on_fail`, `freeze_after` (true only on the freeze stage), and `model` (omit on every stage
   except optionally `implement-*` — see schema for the full field list and the reasoning behind
   the narrow scope). Write `brief` as plain instructions for whatever Claude eventually gets
   spawned to do the stage's work — never a skill name as a hard dependency. You're generating this
   inside a live Claude session right now, so you can see your own `available_skills`; if the user
   named a preferred skill for this stage, name it *inside the brief text* as an explicit
   instruction ("Use the `<skill-name>` skill"); otherwise, if one is genuinely relevant (e.g. an
   implementation-focused skill for an implement stage), name it as a suggestion worth trying, not
   as a required binding. The workflow may execute on a different machine with a different skill set
   later — the enforcement fields (`write_scope`, `exit_criteria`, `on_fail`) must keep working with
   or without any specific skill installed. **Keep each brief proportionate to what it's actually verifying new.** A brief that
   asks a stage to re-derive evidence the mechanical `exit_criteria` check already produces (e.g.
   "run the test suite and paste the output" when `exit_criteria.run` already does exactly that)
   just burns an extra subagent round-trip for zero new information — every stage's real work gets
   independently re-verified by kestra-run anyway, so the brief only needs to ask for what isn't
   already mechanically covered. Confirmed by direct benchmarking: a `verify` stage brief that says
   "also manually exercise the API end to end" pays off when it targets a property the frozen tests
   genuinely don't cover yet, but the same instruction applied blanket-style across every stage
   multiplies token/time cost without multiplying confidence. When a stage's automated exit_criteria
   already proves the property, say so in the brief and let it stop there.
   - **If the user asked for faster/cheaper runs, set `model` on `implement-*` stages only** — see
     `references/workflow-schema.md`'s `model` section for the full reasoning. In short:
     `implement-*`'s output is never trusted on its own say-so (`verify` and `review` both
     independently re-check it on the default model, and a wrong implementation just loops through
     `fixing`), so it's the one stage where a faster model's mistakes are cheap. Every judgment
     stage — `spec-review`, `test-review`, `review`, `generate-tests` — keeps `model` unset. Measured
     directly on a spec-writing task (the same shape of work those stages do): a faster model
     silently invented an unstated constant and reported zero open items where the default model
     had correctly flagged it, and picked an approach the default model's own analysis had already
     written down and rejected. Nothing downstream re-checks a judgment stage's reasoning the way
     `verify`/`review` re-check `implement-*`'s output, so that failure mode has nowhere to be
     caught. Don't set the field defensively when the user hasn't asked for it — omitting it already
     gives every stage the safe default.
   - **Set `effort: low` on `implement-*` automatically whenever `mode: lite` — this one isn't
     opt-in, unlike `model`.** See `references/workflow-schema.md`'s `effort` section for the full
     reasoning. In short: `mode: lite`'s own precondition table already establishes `implement-*`
     doesn't need heavy reasoning (single component, no doubles, trivial invariants), and the same
     `verify`/`review` safety net that makes `model` overrides safe on `implement-*` applies here
     too — a low-effort mistake just fails and loops through `fixing`. Under `mode: full`, leave
     `effort` unset on `implement-*`: full's own trigger conditions describe other stages'
     complexity, not necessarily this one's, so the signal doesn't transfer. Judgment stages
     (`spec-review`, `test-review`, `review`, `generate-tests`) never get an automatic `effort`
     override, same reasoning as `model` — nothing downstream re-checks how well they reasoned.
     `effort` and `model` are independent fields; setting one never implies or requires the other.
   - **If the source spec's ACs are written as Given-When-Then** (see `kestra-spec`), the
     `generate-tests` stage's brief should say so explicitly: write the frozen tests as BDD scenarios
     that mirror the spec's Given-When-Then structure one-to-one, in whatever the stack's idiomatic
     form is — Gherkin `.feature` files (Cucumber/Behave/SpecFlow) if that tooling is already present
     or the user wants it, otherwise plain `describe`/`it` (or the language's equivalent) blocks
     structured as Given/When/Then in the test body and names. This is a format instruction only —
     it changes nothing about the mechanics: the freeze still happens at `freeze-tests` and nowhere
     else, the test-hash still snapshots that stage's `write_scope`, and `fixing` is still barred
     from touching test paths once it has fired. The point is to keep the artifact readable as the
     same scenario a non-technical stakeholder already signed off on in the spec, so whoever reads
     the tests before the lock — `test-review`, or a human glancing at the diff — can recognize a
     missing business scenario as a missing paragraph rather than having to reverse-engineer intent
     from assertions. If the spec's ACs are plain testable prose instead, write
     ordinary unit/integration tests as usual; don't force Given-When-Then onto a spec that doesn't
     use it.
   - **An `implement-*` brief has to ask for the spec's runtime invariants as actual guards, not
     just for green tests.** This is the one instruction in a brief that can't be replaced by a
     mechanical check, and the reason is structural rather than incidental. The frozen tests were
     derived from the acceptance criteria, and the acceptance criteria describe conditions someone
     anticipated. A runtime invariant exists precisely for the conditions nobody anticipated — so an
     implementation that omits every guard still passes every test, by construction. `exit_criteria`
     can't catch it either, since the criteria are the tests. If the brief doesn't ask, nothing in
     the pipeline will, and the omission surfaces the first time production supplies an input the
     spec never imagined. So state it plainly in the brief: implement the feature against the frozen
     tests **and** install the checks the spec's **Runtime Invariants** section calls for, each one
     detecting its condition and halting, refusing, or alerting rather than proceeding — a guard
     that logs and continues satisfies the letter of the section while providing none of its value.
     When the spec named pairs of paths that must agree, or dependency behavior that isn't
     guaranteed, mention those in the brief too: they're constraints the implementation has to
     respect and the frozen tests may well not cover. Point the `review` stage's brief at the same
     section, since reading the diff for a missing guard is exactly the kind of judgment `review`
     exists to apply and `verify` structurally cannot.
5. **Write `workflow.yaml`** — schema and a full worked example in `references/workflow-schema.md`.
6. **Write `state.json`** — initial state matching the stage list, schema + example in
   `references/state-schema.md`. All stages start `pending`, `test_hash: null`, `seen_diffs: []`.
7. **Dry-run it before showing it to the user.** Run
   `python3 <skill-dir>/scripts/validate_workflow.py <output-dir>` — a dependency-free, zero-LLM
   structural check (no third-party packages, works with a plain `python3`) that catches exactly
   the mistakes this file's own anti-pattern list warns about: a post-freeze `write_scope`
   overlapping the frozen test paths (pre-freeze stages are correctly exempt — they own those paths
   on purpose), a missing `on_fail.target` on a `write_scope: []` fixing stage, a dependency cycle,
   a stage unreachable from any start stage, `freeze_after: true` on more than one stage or on a
   stage whose `write_scope` is empty (which would snapshot nothing), and independent stages with
   colliding `write_scope`s that kestra-run might run in parallel. This is a
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

- Setting `model` to a faster/cheaper tier on `spec-review`, `test-review`, `review`, or
  `generate-tests` to make a run cheaper. These are exactly the stages nothing downstream
  double-checks — their output *is* the check — and that's precisely the shape of task where a
  faster model was measured to silently invent an unstated answer and report zero open items where
  the default model had correctly flagged one. `model` belongs on `implement-*` only, where
  `verify`/`review` catch a wrong answer on the default model regardless of what wrote it.
- Setting `effort: low` on a judgment stage (`spec-review`/`test-review`/`review`/`generate-tests`),
  or on `implement-*` under `mode: full`. Same reasoning as the `model` anti-pattern above — the
  `mode: lite` precondition table is the only thing that makes `effort: low` safe on `implement-*`,
  and it doesn't hold for judgment stages or for `implement-*` under `mode: full`, which can still
  be a genuinely complex piece of work even when the *reason* the workflow is `full` lives elsewhere.
- Choosing `mode: lite` to make a run cheaper when a condition in the lite table actually holds —
  most often a spec whose Reality Constraints do list an external dependency, waved away as "only
  one mock." The doubles are exactly what `test-review` exists to read, so this doesn't save a
  redundant stage; it removes the only pass that would have caught the double drifting from the
  thing it stands in for. The table is read off the spec, the same as the `needs_*` flags.
- A "lite" workflow that drops `freeze-tests`, drops `review`, or merges `verify` into `review`.
  None of those are lite — lite drops stages that had nothing to examine on this spec, and every
  one of these three is load-bearing regardless of spec size. A file without `freeze_after` isn't
  TDD-locked at all; a file without `review` has no pass looking for injection/authn/secrets or a
  missing runtime guard.
- A stage's `write_scope` including test paths when that stage runs at or after the freeze point and
  isn't an unlocked `reworking` pass. This is the single most common way to silently defeat the
  whole design. Stages *before* the freeze — `generate-tests`, and `freeze-tests` itself — own those
  paths legitimately; that's how tests get written and revised while revising them is still cheap.
- A `spec-review` stage whose `exit_criteria` only proves the spec file exists and contains a
  heading. That check passes for any spec-shaped document, including a confidently wrong one, so the
  stage costs a step and buys nothing — while sitting at the single cheapest point in the file to
  catch a defect, before one test has been written. Give it a real verdict artifact to grep, the
  same shape `review` uses.
- An `implement-*` brief that asks only for the frozen tests to pass, on a spec that declares runtime
  invariants. The tests came from anticipated cases and the invariants exist for unanticipated ones,
  so an implementation with no guards at all goes green — there is no mechanical check anywhere in
  the file that would notice, which is exactly why the brief has to ask.
- A "replan" stage, or any `on_fail`/branching condition that reads like a programming language.
  Branching stays declarative — conditions may only reference an artifact's existence or an exit
  code, nothing more expressive. If the user wants real replanning mid-run, say so explicitly rather
  than smuggling it in as a fancy condition.
- No stage anywhere setting `freeze_after: true`, or the flag landing on a stage with an empty
  `write_scope`. That flag is the only thing that tells the orchestrator to snapshot the test-hash,
  and the hash is computed from the flagged stage's own `write_scope` — so a missing flag and a flag
  on a `write_scope: []` stage fail identically and silently, leaving a pipeline that looks
  TDD-locked and isn't. `scripts/validate_workflow.py` checks both.
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
- Putting `freeze_after: true` on a `define-shared-contract` stage (or any stage other than the
  freeze stage). Confirmed by direct testing: this makes `test_hash` snapshot the shared
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
  full run would. Whatever language/framework the spec uses, verify the exact `exit_criteria.run`
  command can actually pass *before* any implementation exists — the same "run it standalone before
  freezing" discipline as the write_scope anti-pattern above, just checking polarity instead of
  scope. When the spec is illustrative and there's no repo to run anything against — a worked
  example, a design sketch — you can't honor that discipline, so say plainly which commands and
  globs are unverified placeholders instead of presenting them as checked. An unverifiable command
  labelled as such is useful; the same command presented as verified is a trap for whoever runs it
  next.
- Solving that polarity problem with a **syntax-only** check and stopping there. A parse check
  (`python3 -m py_compile`, `node --check`, and friends) satisfies "passes before an implementation
  exists," which is why it's the tempting answer — but it accepts a test referencing a variable that
  was never defined, since that's a runtime error rather than a syntax error. Confirmed the
  expensive way: a frozen test suite passed exactly this check with an undefined name in it, and
  the defect surfaced during implementation, after the tests were locked and a fix therefore meant
  a `reworking` bounce. Ask instead for the property — *static analysis that resolves names without
  executing or importing the implementation* — and derive the command for the actual stack (many
  linters do this: pyflakes-style undefined-name checks, `no-undef` rules, a type-checker in
  no-emit mode). Fold the mechanically detectable test-quality risks into the same command while
  you're there, most usefully a check that tests don't read a live clock or other ambient state
  when the spec's Reality Constraints say those must be pinned. Anything a command can settle
  belongs here rather than in `test-review`: it costs no subagent, and unlike a reviewer it cannot
  be reasoned out of its answer.
- Putting `freeze_after: true` on `generate-tests`. This *was* the guidance and is now wrong — see
  the two-stage split in step 3. Freezing at the moment tests are written locks them before anyone
  has read them, and buys nothing, because the confirmation loop the freeze prevents needs an
  implementation to exist and none does yet.
- A `test-review` stage placed after `freeze-tests`, or one that owns test paths. Reviewing frozen
  tests is nearly pointless: the only legal response to a finding is `reworking`, so every typo
  becomes a human stop. And a reviewer that can edit what it reviews is not an independent check —
  it's the same agent grading its own homework, which is the failure mode `write_scope` exists to
  make impossible rather than merely discouraged.
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
