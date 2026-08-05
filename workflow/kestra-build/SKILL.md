---
name: kestra-build
description: >
  This skill should be used when the user asks to "generate a workflow from this spec", "turn this
  spec into a workflow.yaml", "produce a workflow.yaml + state.json", "design a TDD-locked pipeline
  definition", "make a generator output with stages, exit criteria, and on_fail blocks", "fold this
  sliced ticket set into one long-run workflow", "embed the ticket bodies into the stage briefs",
  "re-fold — issue #47 changed", "record the anchor triple / Verified-against / ac_hash for these
  slices", references
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

**A spec plus a sliced ticket set is a third input shape** — one `0-spec.md`, N tickets, one
`workflow.yaml` whose stages each own one slice. Decide which of three forms you were handed before
doing anything else, the same way `kestra-spec` decides in-chain vs. standalone:

| Form | The invocation names | Do |
|---|---|---|
| **A — sliced fold** | a run folder with `0-spec.md` **plus** the slice set: GitHub refs (`#N` / URLs) with the repo, or a directory of local-file tickets | the fold below, in full |
| **B — monolithic fold** | a run folder with `0-spec.md` only | the ordinary Process below; no `tickets:` block, and `spec_anchor` only if the spec carries a `> Spec-ticket:` preamble marker |
| **C — chain-marked, no set named** | a chain-marked `0-spec.md`, no slices | ask **once**: "this spec is chain-marked `<url>` — name the sliced ticket set, or fold monolithically?" |

**Never search the tracker for tickets nobody named.** No named set *is* the monolithic signal, and
guessing a set is how scope no human vetted gets frozen into a workflow. This is verbatim the rule
`kestra-spec`'s Input section already holds, kept identical on purpose.

---

## Folding a sliced ticket set — run F0–F5 before the Process below

Form A only; form B skips this whole section. These are the **fold-start** steps, labelled F0–F5 so
they never read as the numbered Process steps further down. Exact commands, regexes, hashes and
refusal texts: [`references/ticket-fold.md`](references/ticket-fold.md) — open it now if you are
folding a set, it is the file this section points at for every detail it deliberately doesn't repeat.

**Before F0, guard an existing run before overwriting anything.** If `state.json` exists, its frozen
tooling must exist too; run `python3 "$RUN"/validate_workflow.py "$RUN" --refold-guard`. Any
non-`pending` stage refuses the fold. A first fold has no `state.json` and skips this command; an
existing state without the run's validator is unreadable, not permission to continue.

**F0. Materialize the slices, then resolve the raise commit.** Copy every slice into
`<run>/tickets/<id>.md` with `tr -d '\r'` and nothing else — the same one declared normalization
`kestra-spec` step 0b uses, so "verbatim" means the same thing at both ends of the chain. This is the
**only** point in the whole run where the tracker is read; everything downstream reads
`tickets/*.md`, which is what lets `kestra-run` work with no network and no `gh`. `id` is the
tracker's own identifier (`issue-<N>`, or the local file's basename), never derived from the title —
a retitled ticket must not orphan its file on the next fold. Then resolve the raise commit with
`kestra-spec`'s `references/chain-provenance.md` §2 exactly-one predicate; 0 or >1 matches ⇒ that
file's hard-fail messages verbatim, never a hand-picked SHA.

**F1. Prove the spec hasn't moved since the raise** — recompute both sides, never compare a stored
hash to a fresh one:

```bash
python3 "$RUN"/requirement_surface.py "$RUN"/0-spec.md --hash                   # working tree
git show <raise>:<spec-path> > /tmp/kestra-fold-raise-spec.md
python3 "$RUN"/requirement_surface.py /tmp/kestra-fold-raise-spec.md --hash     # as raised
```

Different ⇒ **stop**, print both hashes plus the extract diff, and name the two honest paths:
re-raise (`kestra-spec`), or re-anchor to the current raise if the human judges the slice boundaries
still intact. **Whether the boundaries survived is never automated** — the hash says the surface
moved, the diff says which rows, the human says whether the slicing still holds.

**F2. Match every ticket AC against the spec's `## AC Coverage Map`, and read each AC's Source off
the matched row.** Normalize the ticket line exactly as `requirement_surface._units` does, then strip
a trailing label with `\s*\(Source:\s*[^()]*\)\s*$` and nothing wider. An unmatched ticket AC **refuses
the fold** (the slice set and the raised spec disagree, and reconciling them is a human's call); an
empty `Source` cell on a matched row stops too; a ticket label contradicting the row stops, printing
both. Map rows covered by no ticket, or by two, are WARNs that must appear in the audit line. The map
is the single owner of the AC→Source mapping — a slice may echo it, never restate it independently,
because a second copy can drift while both still look populated.

**F3–F4. Compute `ac_hash` per slice, then refresh and *print* the marker table** — `body_sha256`,
`ac_hash`, `verified_against` (= F0's raise SHA), `verified_at` (ISO-8601 UTC) for every slice,
including rows whose status is `unchanged`. A refresh nobody can see is indistinguishable from a
refresh that did not run.

**F5. Emit this run's frozen tooling and commit it with the workflow:**

```bash
cp <skill-scripts-dir>/requirement_surface.py <skill-scripts-dir>/validate_spec.py \
   <skill-scripts-dir>/validate_workflow.py "$RUN"/
```

All three, on **every** fold including form B — this is the single owner of that `cp`, referenced by
the `spec-review` bullet and by step 7 rather than repeated. `kestra-spec` already emits the first
two; overwriting them is idempotent, and a genuine skill-version difference then shows up as a git
diff instead of hiding. The third is not optional: `validate_workflow.py` imports
`requirement_surface` as a same-directory sibling with no path setup, so run from the skill directory
it would bind the *skill's* extractor and quietly defeat the per-run freeze. A check that reads this
run in six months must not change its answer because a skill was reinstalled since.

**Then record what F0–F4 produced, in `workflow.yaml`:** the `spec_anchor` triple beside
`source_spec`, the `tickets:` map, and each owning stage's `brief` carrying its ticket body verbatim
between `<!-- ticket:begin <id> sha256:<64 hex> -->` / `<!-- ticket:end <id> -->` delimiters, with the
stage's own instructions strictly below the block. Field grammars, the embedded-block rules, and the
two parser traps that decide how it's all verified:
[`references/workflow-schema.md`](references/workflow-schema.md). Stage `depends_on` ordering comes
from each slice's `## Blocked by`, never from filename order.

**Any ticket-body change ⇒ re-fold; there is no hand-edit path.** A re-fold is a plain re-run of
kestra-build over the same run folder (no flag, no CLI) and overwrites `workflow.yaml`,
`tickets/*.md`, the emitted scripts, and `state.json`. It has to be a re-fold rather than a patched
brief because only the fold re-runs the freeze/`write_scope` validation, the anchor recompute, and the
`ac_hash` refresh — a hand-patched brief carries current words behind a stale anchor. Say that in the
brief's own footer too, so the rule travels with the artifact into every spawn.

**One hard guard: refuse to re-fold a live run.** If any stage in the existing `state.json` is past
`pending`, stop and print the refusal in `ticket-fold.md` §4 — the honest paths are letting
`kestra-run` escalate to `reworking`, or a destructive reset to the pre-run commit. Overwriting
`state.json` mid-run destroys the resume checkpoints and orphans the commits that were the rollback
points, so this is a `reworking`-class event, not a regeneration: enforce it before F0 with the
run's `validate_workflow.py --refold-guard`, escalate upward, never patch sideways.

**Print the tracker-side line; never post it.** One line per slice in the closing report —
`Verified-against: <sha…> · ac_hash: <hex…> · extractor: v<N> · fold: <ISO-8601>` — for a human to
paste. kestra-build produces artifacts and stops; it doesn't even commit, so writing to an external
tracker is outside its contract, and its sibling `kestra-spec` is read-only on the tracker for the
same reason. Named residual: a human who never pastes leaves that ticket anchorless, visible only at
the next fold.

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
| Runtime Invariants is non-trivial | the spec's **Runtime Invariants** having rows whose violation is silent in production | a dedicated `spec-review` earns its round-trip when there's something to contradict |
| The user asked for full | their words | their call, not yours |

`needs_devops: true` is **not** a row in this table — it doesn't decide lite vs. full, because
`deploy-readiness` is a stage that appends to either shape (see below), not one that requires the
full machine around it. A devops-flagged spec that trips none of the rows above still gets the lite
stage list, plus `deploy-readiness` before `done`.

Ambiguity resolves toward **full** — the cost of a wrong `lite` is a missed defect, the cost of a
wrong `full` is a slower run. State which condition (or the absence of all of them) decided it when
you show the workflow to the user, so the choice is auditable rather than a mood.

**One more factor: is the root cause established, or still to be found?** Every row above describes
the *shape of the risk* — components, doubles, invariants — and none of them asks how much of the
problem the spec already solved before arriving here. A spec that arrives with a reproduced failure,
the responsible `file:line`, and a fix direction already spelled out is a fundamentally different
task from one with an open design space, even when the two have identical risk shapes by the table's
own terms. The stages that pay for themselves on the second kind are the discovery stages
(`spec-review` finding a wrong assumption, `test-review` catching a double that drifted); on the
first kind, those same stages mostly re-derive a conclusion someone already reached — measured
directly: a `mode: full` run on a fully-diagnosed 300-line fix spent 37.5% of all subagent tokens on
four rounds of `spec-review` alone, three of which were the spec catching up to facts the
originating issue already stated.

This is a **guarded row-override**, not a tiebreaker to consult only when the table already looks
close — the table triggers `full` on **any** row holding, so a factor that only acts "when otherwise
borderline" can in practice never fire and was dead weight as written. The override applies only
under all three of: (a) a pasted, **executed** repro command with real output — not a prose
assertion of the bug; (b) the responsible `file:line`; (c) a stated fix direction — the same bar
`kestra-spec` step 6 item 5 already holds a spec to ("execution-verified", not self-consistency-only).
For a foreign spec that never went through `kestra-spec`, fold "is the root cause already established
and reproduced?" into the single user question step 4 already asks — it costs no extra round-trip.

**Which rows the override can touch, and which it never can:** "2+ independent components", `needs
devops`, and "the user asked for full" are **never** overridden — none of them are about *discovery*
risk in the first place, so a known root cause says nothing about whether they still hold. "Runtime
Invariants is non-trivial" **is** safe to override as written — the invariant guards this factor
would otherwise force a dedicated `spec-review` round-trip for are already preserved regardless,
via the lite-mode `generate-tests`-brief fold (see the lite table above), so overriding this row
loses no coverage. "The tests will contain test doubles" needs one more guard before it's safe to
override: the spec's Reality Constraints must **affirmatively state** the fix needs no test double
(real fixtures suffice) — re-verified the same static way the test-review fold-in above already
verifies its own premise, not assumed from the root-cause finding alone. A confirmed root cause says
nothing about whether the *fix* touches an external dependency; only the Reality Constraints section
can say that. Without that fourth guard, drop test doubles from the overridable set entirely.

Record which condition fired — root-cause override, or the base table's own verdict — in the same
audit line either way: "root cause was pre-established; overriding the doubles/invariants row; chose
lite" is exactly the kind of reasoning this rule exists to make visible instead of silent.

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
| `verify` | kept | script-eligible by default (see the script-eligibility table in step 2 below) — `write_scope: []` with an `exit_criteria.run`, which kestra-run executes directly (see its efficiency notes) |
| `review` | kept, unconditional | passing tests say nothing about injection/authn/secrets or a missing runtime guard. This is the one judgment stage lite keeps, and the reason lite is still safe to use |
| `deploy-readiness` | **appended when `needs_devops: true`** | not a lite/full distinction — see below |

Net effect on a typical single-component feature: three subagent-bearing stages instead of six or
seven, with the freeze and the security/correctness review both intact.

**Do not invent further savings.** Merging `verify` into `review`, skipping `review` because the
diff looks small, or dropping `freeze-tests` to save a commit are not lite — they're the full
machine with its load-bearing parts removed. Lite is a fixed, named shape, not a license to trim
per-spec.

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

   **Then settle script-eligibility, here and once — not per-stage as you go.** Same
   mechanical-table pattern as the flags above, checked once so the per-stage bullets in step 3
   don't each re-derive it. A stage is **script-eligible** — no subagent, `exit_criteria` alone
   decides pass/fail — only when **both** hold: it produces no real diff of new work
   (`write_scope: []`, or for `freeze-tests`, a `write_scope` kept only so the test-hash covers it
   while the stage's own diff stays empty), **and** its `exit_criteria` settles pass/fail without
   anyone judging content. Missing either condition means a real subagent every time. This table is
   the single source of truth — the per-stage bullets below point back to it instead of re-arguing
   eligibility; they still carry the implementation-specific instructions (what a script-only
   stage's brief should say, what its `exit_criteria.run` should invoke) that this table doesn't
   repeat.

   | Stage type | Script-eligible? | Condition | Notes |
   |---|---|---|---|
   | `spec-review` | No — mechanical pre-check only | `write_scope` covers `source_spec`; `exit_criteria.run` chains `validate_spec.py` (a script) + a verdict grep | the script proves presence/existence only (e.g. Files-to-Touch paths exist); judging contradictions/on-violation wording still needs a subagent |
   | `generate-tests` | No | writes real test code | creative work |
   | `design` (`needs_ui: true`) | No | writes `design.md`/artifact | creative work |
   | `design-tests` (rare split) | No | writes the scenario table | creative work, even though `exit_criteria.type` can be `artifact_exists` |
   | `freeze-tests` | **Yes** | `write_scope` = the same test paths (kept only so the hash covers them); the stage itself writes no new diff — `exit_criteria` re-runs `generate-tests`'s own static checks against the exact commit being frozen | mechanical re-check, not a review; `on_fail: reworking`, never `fixing` |
   | `implement-*` | No | writes real code | creative work |
   | `define-shared-contract` | No | writes the shared file | small, but still a design decision |
   | `verify` | **Usually yes** | `write_scope: []`; `exit_criteria.run` is the frozen suite's own exit code | a subagent is only needed for the genuinely-uncovered ACs the brief's binary check flags — see step 4's `verify` brief guidance |
   | `review` | No | `write_scope: []`, but the verdict requires reading the diff for correctness/security judgment | the one judgment stage lite keeps; never script-only |
   | `test-review` | No, or dropped entirely | `write_scope: []`; judges test-double fidelity | when the fold-in condition holds (real fixtures + a cross-file self-check in `generate-tests`'s own brief), drop the stage rather than trying to script it |
   | `deploy-readiness` | No | reads diff + spec, judges devops risk | folded into `review`'s brief by default; still judgment either way |
   | repo-declared pre-merge test gate (sibling) | **Yes** | `write_scope: []`; `exit_criteria.run` invokes the repo's own documented command | give it no work-describing brief — "kestra-run runs `exit_criteria.run` directly; spawn nothing" |
   | `done` | **Yes** | `write_scope` scoped to one summary file; `exit_criteria.type: artifact_exists` | `kestra-run` writes the summary itself from `state.json`/`git log`, no spawn |

3. **Derive the stage list from what the spec actually needs** — don't default to a fixed phase set.
   **If step 2 settled on `mode: lite`, the stage list is already fixed** by the lite shape above —
   generate exactly those stages and skip ahead to step 4; the per-stage guidance below still
   applies in full to each stage lite keeps (`generate-tests`'s exit_criteria polarity,
   `freeze-tests`'s write_scope, `review`'s verdict artifact and `on_fail.target`), so read it for
   those, not for whether to add more stages.

   **Then settle which references this spec needs, here and once** — off the facts step 2 already
   recorded, same mechanical-table pattern as step 2's own two tables. Open the rows that fired and
   nothing else: measured directly, skipping a file whose branch this spec cannot reach is the
   difference between `kestra-build` staying flat-cost on a trivial spec and paying a fixed tax on
   every one for guidance that never applied.

   | Fact, already settled in step 2 | Open | For |
   |---|---|---|
   | `mode: lite` **and** `needs_devops: false` | **nothing** | the bullets below are the whole story |
   | `mode: full` | [`references/full-mode-stages.md`](references/full-mode-stages.md) | what `spec-review` must actually check · `test-review`, its risk table, and the condition under which its check folds into `generate-tests` and the stage isn't generated · the harness contract · evidence artifacts · sibling `implement-*` · the shared-contract stage · splitting `review` per component |
   | `needs_devops: true`, **either** mode | that same file's `deploy-readiness` **section only** | the exact trigger wording, the default fold into `review`'s brief, and the two freshness enforcement points that fold depends on |
   | the user wants to approve the scenario list before any test code exists, **or** the spec is too large for one spawn | [`references/stage-derivation.md`](references/stage-derivation.md) § 1 | when a real `design-tests` stage is justified, and what it must look like when it is |
   | any stage you generate will write a verdict artifact | that same file's § 2 | why the shape inline below is that shape, and what a finding asserting a number additionally owes |
   | the spec is a wide refactor or a batched migration | that same file's §§ 3–4 | the two legal shapes for a batch whose blast radius reaches test files, and how each batch's own gate stays honest |
   | the codebase survey found a pre-merge test gate the repo's own docs declare mandatory | that same file's § 5 | generating it as a stage with `exit_criteria` rather than leaving it as a suggestion in a brief |

   **Name what you opened in the mode/stage audit line** — "references opened: none (lite, no
   devops)", "references opened: full-mode-stages.md + stage-derivation.md §5". A table consulted
   silently leaves nothing behind to check, which is the same reason step 2's flag table has to
   appear in your output rather than being filled in mentally.
   A minimal TDD-honest skeleton looks like:
   `spec-review → generate-tests → freeze-tests (freeze point) → implement[-per-component] →
   {verify, review} → done`. Add stages only when the spec calls for them (e.g. a UI-facing spec
   adds a design stage before `generate-tests`; multiple independent components each get their own
   `implement-*` stage so their `write_scope`s don't collide).
   - **Writing the tests and freezing them are two stages, not one** — and `freeze-tests` is
     script-eligible (see the table above): it writes no new diff, so its `exit_criteria` alone
     decides pass/fail. It's tempting to put
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

     **Choose the freeze stage's `write_scope` deliberately; it defines the test-hash.**
     `generate-tests`'s own `write_scope` should include whatever runner plumbing the suite needs to
     be collectible at all (a `conftest.py`, a `jest.config`, a `pythonpath` entry) — that's right for
     `generate-tests` — but copying the same
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
   - **Default: have `generate-tests` write its own scenario table as a first artifact in the same
     spawn** (AC/BR/edge-case → scenario title → Given/When/Then, 1:1 traceable), *before* writing
     test code — not as a separate `design-tests` stage.
   - **`spec-review` is the cheapest gate in the whole file — don't generate it as a formality.**
     An existence-only check (the file exists, is non-empty, has an acceptance-criteria heading)
     passes for any spec-shaped document, including a confidently wrong one. What it must actually
     check, the `validate_spec.py` pre-check chained ahead of the verdict grep, and its `on_fail`
     shape are in [`references/full-mode-stages.md`](references/full-mode-stages.md)'s
     `spec-review` section.
   - **`test-review` — including the condition under which its check folds into `generate-tests`
     and the stage isn't generated at all — plus the harness contract, evidence-artifact reuse,
     and sibling `implement-*` / shared-contract stages are covered in
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
       (`spec-review`, `test-review`, `review`).** Ask for, in order: the verdict line, exactly
       `VERDICT: CLEAR` or `VERDICT: CHANGES_REQUESTED` as the first line; then a findings table with
       one row per finding — severity, the claim in one line, and `file:line`; then paths into
       `<run-folder>/evidence/` for anything that took real computation to establish.
       Why that shape, what to tell the brief so a reviewer doesn't drop findings to comply, and what
       a numeric finding additionally owes:
       [`references/stage-derivation.md`](references/stage-derivation.md) section 2.
     - **When there are 2+ sibling `implement-*` stages**, `review` (and sometimes `verify`) needs
       splitting one-per-component so `on_fail.target` has an unambiguous single stage to route a
       fix to — see the "Splitting `review`" section of
       [`references/full-mode-stages.md`](references/full-mode-stages.md) for the full reasoning.
       Never applies under `mode: lite`, which has exactly one `implement-*` stage by definition.
   - **If the spec's `needs_devops` flag is true, add the deploy checklist** — see
     [`references/full-mode-stages.md`](references/full-mode-stages.md)'s `deploy-readiness` section
     for the exact trigger wording, what the checklist checks, and the default: fold it into
     `review`'s own brief and verdict artifact (with mechanically-enforced freshness) rather than a
     separate stage, falling back to a standalone `deploy-readiness` stage only when that enforcement
     can't be wired in or the user wants a distinct milestone. Either shape appends to **either**
     mode: on a `mode: lite` spec it's the one addition before `done` (the lite table above already
     reflects this); it's never itself a reason to choose `full`.
   - **End with a mechanical `done` stage**, not `waiting_approval` — `write_scope` scoped to a
     single summary file, `exit_criteria.type: artifact_exists` on a generated completion summary.
     Script-eligible (see the table above): by the time execution reaches it, every judgment-bearing
     check already ran and already had its own escalation path; there's nothing left for a human to
     approve that hasn't already been mechanically or automatically checked. **Brief the `done` stage to include a per-stage
     token/wall-time table in the completion summary**, sourced from whatever the orchestrator
     already tracked while running the workflow (it does not need to re-derive this — kestra-run's
     own progress tracking already has it). Measured directly: on an 8-stage `mode: full` run fixing
     two pre-diagnosed bugs, the cost/rigor trade-off (~803k subagent tokens / ~27min, against an
     estimated 100k–180k / 10–15min for a single ungated fix) only became visible because the user
     asked for it after the fact — without the table in the summary by default, every run's
     mode-vs-cost trade-off stays invisible unless someone remembers to ask. Add two more columns
     when the data supports them: **attempt count** (free and accurate today — kestra-run already
     tracks it per stage) and **spawn type** (fresh / resumed / none) — but only populate the
     spawn-type column for a stage whose attempts all happened within one session; across a
     pause/resume, say "N/A — multi-session resume, not tracked" for that row rather than
     reconstructing a guess. These calibration columns are what turns the ~150k resume-vs-respawn
     threshold and the 3/2 attempt caps from one measured run each into something with real
     cross-run data behind it.
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
   already proves the property, say so in the brief and let it stop there. **For `verify` specifically,
   write the brief as a binary check, not a blanket instruction** — see the worked example's
   `verify-acceptance-criteria` brief in `references/workflow-schema.md`: it can't be decided at
   generation time whether the frozen suite fully covers every AC, since the tests don't exist yet
   when you write this brief. So the brief itself asks the spawned agent to make that determination
   *at run time*, against the real test files: if every AC in the Coverage Map maps to a real,
   running assertion, say so and stop — that's exit_criteria.run's exit code being the whole
   verification, and kestra-run can skip spawning this stage on a future run of the same shape (see
   its efficiency notes). Only the genuinely uncovered ACs, if any, get a manual runtime exercise.
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
   - **Carry what step 7's dry-run already learned into `generate-tests`'s brief, instead of letting
     it evaporate.** Verifying the exact `exit_criteria.run` command standalone and identifying the
     runner-plumbing files a test-runner needs to even collect the suite (a `conftest.py`,
     `pytest.ini`, a `jest.config`, a `pythonpath` entry) are both things `kestra-build` already does
     at generation time. Put the verified command and the plumbing-file list into the `generate-tests` brief as a
     sentence, so the spawned agent starts already knowing what a passing collection looks like
     instead of re-discovering the project's runner setup from scratch.
   - **A polarity check that only verifies syntax can still pass a suite that's actually
     uncollectable.** Confirmed by direct testing: in an ESM/Node project, a test file statically
     importing a named export that doesn't exist yet (`import { getMetrics } from '../src/queue.js'`)
     is a link-time `SyntaxError` — and it collapses the *entire file* into one failure, not just the
     scenarios that reference the missing export (`node --check` never catches this; it's pure syntax
     checking and doesn't resolve imports). Two changes this implies: tell `generate-tests`'s brief to
     reference any not-yet-existing export through a namespace import (`import * as mod from '...'`)
     instead of a named one, so each scenario still fails on its own assertion rather than the whole
     file collapsing at once; and don't let the polarity `exit_criteria` rely on syntax-plus-content
     greps alone — run the real test command and grep its output for the module system's own
     no-such-export error text (`does not provide an export named`, for Node ESM), so a whole-file
     collapse reads as a real defect in the tests, not the expected pre-implementation red.
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
   - **Give `generate-tests` and every `implement-*` brief an explicit comment-discipline
     instruction — this is not covered by any mechanical check, so it has to be said.** Default to
     no comments; write one only when the *why* is genuinely non-obvious from the code itself (a
     hidden constraint, a workaround for a specific bug, a reason a simpler approach doesn't work) —
     never one that restates what a well-named identifier already says. Two failure modes to name
     explicitly, both real and both compound: **(1)** a multi-line comment block where one line would
     do — a spawned agent left to its own judgment tends to over-explain a non-obvious constraint
     across three or four lines when one covers it. **(2)** a comment that references *this specific
     run* — a task, a spec, an AC id, or (worst) a copy-provenance path like "copied from
     `workflows/runs/<other-feature-id>/...`". That kind of reference belongs in the commit message,
     never the file: it rots the moment the referenced run is archived or deleted, and it means
     nothing to the next feature that copies the same pattern forward. Both failure modes now compound
     directly with the richer context pack — every over-commented line in a frozen test or an
     implementation file gets re-pasted, verbatim, into every subsequent spawn that reads that file's
     diff (`test-review`, `verify`, `review`, and any `fixing` retry), so a comment that costs one
     line to write costs that line again on every stage downstream of it.
5. **Write `workflow.yaml`** — schema and a full worked example in `references/workflow-schema.md`.
   - **Copy every `progress:` bullet out of the spec's `## Exit Criteria` onto the one stage that
     owns it**, as `exit_criteria.progress`, verbatim. The spec declares the metric, kestra-build
     copies it, `kestra-run` compares it across attempt rounds — so a reworded metric is a different
     metric, and a dropped one leaves clause 2 of the spec's stop condition unable to ever fire. The
     owner-resolution ladder (exact match → unique containment → named stage → ask the user once →
     stop the fold), the two fold-time consistency checks, and the exact FAIL text are in
     `references/workflow-schema.md`'s `exit_criteria.progress` section. A stage with no `progress:`
     is the normal case; don't invent one.
6. **Write `state.json`** — initial state matching the stage list, schema + example in
   `references/state-schema.md`. All stages start `pending`, `test_hash: null`, `seen_diffs: []`.
7. **Dry-run it before showing it to the user.** Run
   `python3 <run-folder>/validate_workflow.py <run-folder>` — the run's **own** copy, emitted by step
   F5, not the skill's: the checker imports `requirement_surface` as a same-directory sibling with no
   path setup, so running it from the skill directory binds the skill's extractor and defeats the
   per-run freeze the emit exists to create. (The in-place `python3
   workflow/kestra-build/scripts/validate_workflow.py <dir>` invocation documented in `CLAUDE.md`
   stays valid as a convenience; if it reports an extractor-version mismatch, that is a true signal
   about this run, not a bug in the check.) It is a dependency-free, zero-LLM
   structural check (no third-party packages, works with a plain `python3`) that catches structural
   mistakes mechanically: a post-freeze `write_scope`
   overlapping the frozen test paths (pre-freeze stages are correctly exempt — they own those paths
   on purpose), a missing `on_fail.target` on a `write_scope: []` fixing stage, a dependency cycle,
   a stage unreachable from any start stage, `freeze_after: true` on more than one stage or on a
   stage whose `write_scope` is empty (which would snapshot nothing), and independent stages with
   colliding `write_scope`s that kestra-run might run in parallel. On a sliced fold it additionally
   re-runs the fold's own arithmetic: the anchor triple's shape and freshness (absent ⇒ WARN, partial
   or stale ⇒ FAIL), every embedded ticket block against `tickets/<id>.md` and against
   `tickets[].body_sha256`, each `verified_against` against `spec_anchor.raise_commit`, each `ac_hash`
   against a recomputed surface, and `exit_criteria.progress` being non-empty where present. **This is
   where a first fold's refusal actually bites** — on a re-fold F0–F4 refuse before anything is
   overwritten, but on a first fold there is no prior `workflow.yaml` to check against, so the
   mechanical half of F1–F3 lands here: after the artifacts are written, and before they are shown,
   committed, or handed off. Accepted cost, worth stating rather than hiding: a first fold over a
   mismatched slice set wastes one derivation pass. This is a
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
spec lives). Ask if the repo has a different convention already. A sliced fold adds
`<run-folder>/tickets/<id>.md` per slice plus the three emitted scripts (step F5) — all of them
committed with the workflow, because a hash recorded against a file that isn't in the commit proves
nothing later.

## What kestra-build does not do

- Does not execute the workflow, call any skill, write application code, or commit anything.
- Does not write to the tracker. It reads a ticket once, at F0, to materialize `tickets/<id>.md`, and
  it *prints* the `Verified-against:` line for a human to paste — it never comments, labels, edits or
  closes, the same read-only posture `kestra-spec` holds.
- Does not edit a ticket body, and does not slice a spec into tickets. Whatever produced the slices
  (`to-tickets` is the suggested tool, *if installed*) owns their shape; a mismatch between a slice and
  the spec is a stop, not something to reconcile by rewriting either side.
- Does not re-fold a run whose `state.json` shows any stage past `pending` — that is a
  `reworking`-class event (see the fold section's hard guard), not a regeneration.
- Does not add a `human_approval` stage on its own initiative — the default template has none (see
  `references/design-principles.md`'s "Default HITL posture"). If the user wants a manual milestone
  beyond that default, ask, don't assume.
- Does not replace whatever spec→plan→build→review agent/skill pipeline you already use — if the
  user wants agents dispatched and running right now, point them there instead.
