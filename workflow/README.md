# workflow/ — kestra-spec, kestra-build & kestra-run

These three skills work together as a **spec-sharpener + generator + orchestrator** for building
and running a "stage machine" that actually enforces TDD (not just asking the AI nicely to write
tests first). It freezes tests once written, restricts which files each stage may touch, and
commits per stage so you can always roll back or resume.

```
sharpened idea (from /grilling — or /wayfinder first, when the effort is too big for one session)
   │
   ▼
┌─────────────┐   writes 0-spec.md — testable ACs (optionally Given-When-Then/BDD), needs_*
│ kestra-spec  │   flags, business rules, design notes, and a verified codebase survey — one pass
└──────┬──────┘
       │
       ▼
┌─────────────┐   writes workflow.yaml + state.json, then stops
│ kestra-build │   never runs a stage, writes code, or commits
└──────┬──────┘
       │
       ▼
┌─────────────┐   reads state.json → spawns a subagent per stage
│ kestra-run   │ → verifies mechanically (git diff / exit code / sha256sum)
└─────────────┘ → commits each passing stage → stops at a real stop condition
```

None of the three skills has a hard dependency on any other skill — if a stage's brief wants to
suggest a specialized skill (e.g. an implement skill, a review skill), that only ever appears as a
"suggestion" inside the brief text. Whatever gets spawned to do that stage's work still runs fine
if that skill isn't installed.

---

## kestra-spec — the spec sharpener

**Location:** [`kestra-spec/`](kestra-spec/) · detail: [`kestra-spec/SKILL.md`](kestra-spec/SKILL.md)

### What it does

Takes a sharpened idea (normally the output of a `/grilling` session, or an equivalent
back-and-forth where ambiguity's already been interviewed out) and, in one pass, produces a single
`0-spec.md`: testable acceptance criteria, explicit error states, the `needs_ba`/`needs_ui`/
`needs_sa`/`needs_devops` flags `kestra-build` reads, business rules (when `needs_ba: true`),
design notes (when `needs_ui: true`), solution-architecture decisions (when `needs_sa: true`), and
a codebase survey with every file path verified to exist.

Where the `meta/` group splits this same work across five skills and five files, `kestra-spec`
does it as one continuous pass, one file — so nobody has to remember to chain five skills by hand,
and `kestra-build`'s stage agents don't have to guess at gaps left by a handoff.

### What comes before this: `/grilling`, and `/wayfinder` when the effort is bigger

`kestra-spec` expects the ambiguity to be gone already — it reads what was settled and doesn't
re-open it. Two upstream skills get you there, and they compose rather than compete:

* **`/grilling`** — one continuous interview, one question at a time, walking down the design tree
  and resolving dependencies between decisions as it goes. This is the normal entry point: a
  `0-spec.md` describes one feature, which is usually one session's worth of deciding.
* **`/wayfinder`** — for an effort *too big for one session and still wrapped in fog*, where you
  can't yet say how many features there are or which decisions block which. It doesn't answer the
  questions itself; it charts them as a map of tickets on the issue tracker and works them one at a
  time across sessions. `/grilling` is one of its four ticket types, and its default one — so
  reaching for wayfinder isn't skipping the grilling, it's scheduling several of them.

Wayfinder names its own destination per effort, and "a spec to hand off and iterate on" is one of
the shapes it lists — which is exactly the handoff into `kestra-spec`. Rule of thumb: if you can
already say what the feature *is* and only the details need sharpening, grill it and go. If you
don't yet know how many specs this becomes, chart it first, then bring each settled piece here.

### Runtime invariants & reality constraints

Passing tests only prove the cases someone anticipated, because the tests were derived from the
spec and the spec is where "anticipated" gets fixed. Two sections exist to cover the rest:

* **🛡️ Runtime Invariants** — conditions that must hold *every time the system runs*, enforced in
  production rather than verified once in a test. Each names the condition, how it's detected at
  runtime, and what happens when it's violated — halt, refuse, or alert. A check that logs and
  carries on doesn't count; that's the failure mode the section exists to prevent.
* **🌐 Reality Constraints** — what the world outside the feature actually does, which is the
  standard its test doubles get judged against: each external dependency's enforced call ordering,
  the types it really returns, and (the column people skip) what completeness or consistency it
  does **not** guarantee; any pair of code paths that must produce equivalent results, since a
  parity check can't be written unless someone declares the pair; and which non-deterministic
  inputs — clock, randomness, timezone, network, filesystem, environment — must be pinned in tests
  versus allowed to float.

Why these particular risks: [`kestra-build/references/test-quality-taxonomy-research.md`](kestra-build/references/test-quality-taxonomy-research.md)
maps them to established testing literature (hermetic tests, test-double fidelity, consumer-driven
contract testing, characterization/golden-master comparison). It's a well-supported starting point,
not a complete list — a data pipeline's dominant risk is schema drift and a web app's is
authorization, and neither appears there.

### Given-When-Then / BDD-style acceptance criteria

Acceptance criteria that describe *behavior under a condition* (not just a threshold or a data
shape) can be written as Given-When-Then instead of prose — this matters most when `needs_ba:
true`, since it forces every business-rule branch into its own explicit line instead of hiding it
inside a one-line requirement. `kestra-build`'s `generate-tests` stage mirrors this: when a spec's
ACs are Given-When-Then, the frozen tests are written as BDD scenarios (Gherkin or `describe`/`it`
blocks structured as Given/When/Then) that map 1:1 onto them — a format choice only, `freeze_after`
and the test-hash invariant work exactly the same either way. See
[`workflow/runs/order-cancellation-refund/`](runs/order-cancellation-refund/) for a worked example
spec + generated workflow using this format.

**It runs nothing** — it writes `0-spec.md` and stops. Hand it off to `kestra-build` next.

### Example usage

```
"write the spec for kestra-build for CSV export"
"turn this idea into 0-spec.md"
```

---

## kestra-build — the workflow generator

**Location:** [`kestra-build/`](kestra-build/) · more detail: [`kestra-build/README.md`](kestra-build/README.md), [`kestra-build/SKILL.md`](kestra-build/SKILL.md)

### What it does

Takes a feature spec (with clear acceptance criteria, or rough prose it'll help sharpen first)
and produces two files:

| File | What it is |
|---|---|
| `workflow.yaml` | A stage-by-stage plan custom to that feature — each stage declares which paths it may write (`write_scope`), how to check if it passed (`exit_criteria`), and what to do if it fails (`on_fail`) |
| `state.json` | The initial state — every stage `pending`, test hash still `null` |

**It runs nothing** — it writes the files and stops. If you actually want to run it, hand it off
to `kestra-run`.

### Principles it follows (important — read before editing a generated workflow)

1. **Write-scope allowlist** — enforced at apply time, not by asking the AI nicely not to touch
   other files. If a stage's diff strays outside its declared `write_scope`, the orchestrator
   reverts it immediately.
2. **Test-hash freeze** — the moment tests are done (`generate-tests`, with `freeze_after: true`)
   the hash of every test file gets snapshotted into `state.json`. Every stage after that must
   check the hash before doing anything. A mismatch (someone edited the tests outside the process)
   halts immediately — it's not just a retry.
3. **Commit per stage** — a stage that passes commits its code + `state.json` together in one
   commit. No separate tags — the commit itself is the rollback point (`git reset --hard <sha>`).

**Why TDD always comes first:** if tests are written alongside or after the code, the false
positive just moves into the test itself (a fake green build with a loose assertion is more
dangerous than an honest red, because it looks like there's evidence backing it up). Freezing
tests before implementation removes the shortcut of making the tests pass easily. (What TDD does
*not* fix: if the spec itself misses an edge case, the test misses it too — that risk belongs to
spec review, not the stage machine.)

**Why "fixing" escalates upward, not sideways:** a failing test has exactly two honest fixes — fix
the code, or admit the frozen spec/test was wrong. There's no third option of patching the test to
match the broken code. So a `fixing` stage may only touch non-test files. Once retries are
exhausted (`max_attempts`) or the same diff keeps reappearing (no progress, per `escalate_at`),
the only correct move is `reworking` — unlocking test-writing again, going back to spec-review or
regenerating tests, re-freezing, and resetting the attempt counter.

### How kestra-build works (condensed from SKILL.md)

1. Read/sharpen the spec until it has clear acceptance criteria.
2. Fill in a mechanical flag table (`needs_ui`, `needs_ba`, `needs_sa`, `needs_devops`, ...) to
   decide which stages are needed (e.g. `needs_ui: true` → must add a `design` stage before
   `generate-tests`).
3. Pick the **mode** — `lite` or `full` — before deriving any stage, off a fixed condition table
   rather than a feel for how much rigor the change deserves. Any one of these forces `full`: 2+
   independent components, Reality Constraints listing an external dependency or a pair of paths
   that must agree, `needs_devops: true`, runtime invariants whose violation would be silent in
   production, or an explicit request. None present → `lite`; ambiguity resolves toward `full`,
   since a wrong `lite` costs a missed defect while a wrong `full` costs a slower run.
   `lite` is `generate-tests → freeze-tests (🔒) → implement → {verify, review} → done` — the same
   machine with the stages that had nothing to examine removed, **not** with the safety removed:
   the write-scope allowlist, the freeze, commit-per-stage, and `review` all stay. It drops
   `test-review` and `deploy-readiness` (whose triggers `lite`'s own preconditions rule out) and
   folds `spec-review`'s checks into `generate-tests`'s brief instead of losing them. Typically
   three subagent-bearing stages instead of six or seven. The chosen mode is recorded as
   `mode: lite | full` in `workflow.yaml` — a note explaining why a stage is absent, not a switch
   anything reads at run time.
4. Derive the stage list from the actual spec, not a fixed template. The `full` skeleton:
   `spec-review → generate-tests → [test-review] → freeze-tests (🔒) → implement[-per-component] →
   {verify, review} → done`
   - Writing the tests and freezing them are **separate stages**. The freeze stops an
     *implementation* from editing a test into agreement with broken code, and no implementation
     exists when the tests are first written — so locking then protects nothing, while giving up the
     only cheap window to fix a defect in the tests. Before the lock that's a bounded retry; after
     it, the only legal response is a `reworking` bounce, the design's guaranteed human stop.
   - `test-review` fills that window, and is generated **only when the spec's Reality Constraints
     say the tests will contain doubles** — external dependencies, or a pair of paths that must
     agree. A feature that fakes nothing can't have the defects it looks for, so omitting it there
     isn't cutting a corner. It reviews against a six-row risk table (ordering, response realism,
     type drift, path parity, own shared logic, non-determinism), owns no files, and directs fixes
     back into `generate-tests` the same way `review` directs them into `implement-*`.
   - `spec-review` is a real gate, not a formality — it reviews the spec's runtime invariants and
     reality constraints for gaps and contradictions and writes a verdict artifact, the same shape
     `review` uses. It's the cheapest point in the whole file to catch a defect: one edit to one
     document, versus a `reworking` bounce once tests are frozen.
   - Independent components (e.g. backend/frontend) become sibling stages, not a chain, so
     kestra-run can actually run them in parallel.
   - `verify` and `review` are always siblings (both `depends_on` the implement stage directly).
   - The default has **zero** `human_approval` stages — the only place a human is always involved
     is `fixing → reworking` (see "Default HITL posture" in `references/design-principles.md`).
   - `review` is always a mandatory stage (it catches correctness/security issues tests alone
     don't cover).
   - If the spec involves deployment concerns (env vars, migrations, feature flags), a
     `deploy-readiness` stage gets added.
   - It ends with a mechanical `done` stage (writes a summary and stops — not `waiting_approval`).
5. Fill in every stage's fields: `id`, `depends_on`, `brief`, `write_scope`, `exit_criteria`,
   `on_fail`, `freeze_after`. An `implement-*` brief also has to ask for the spec's runtime
   invariants to be installed as real guards — the frozen tests came from anticipated cases and the
   guards exist for unanticipated ones, so an implementation with no guards at all still goes green.
   No mechanical check anywhere in the file would notice, which is why the brief has to say it.
6. Write `workflow.yaml` + `state.json`.
7. **Always dry-run first**: `python3 kestra-build/scripts/validate_workflow.py <output-dir>` — a
   zero-LLM structural check (no PyYAML, no AI judgment) that catches 7 main things:
   - Missing `on_fail.target` on a `write_scope: []` + `action: fixing` stage
   - `write_scope` overlapping a path that was already frozen as a test path
   - Independent stages whose `write_scope`s collide (a real risk if they run in parallel)
   - `freeze_after: true` missing, or set on more than one stage
   - Dependency cycles / unreachable stages
   - `exit_criteria` or `on_fail` missing required fields
   - `state.json` not matching the stage ids in `workflow.yaml`

   `FAIL` = must be fixed before showing the user, `WARN` = surfaced but not blocking.

8. Shows both files plus a plain-language walkthrough of the stage sequence so the user can
   sanity-check before treating it as "frozen."

### Example usage

```
"turn workflows/runs/csv-export/0-spec.md into a workflow.yaml"
```

---

## kestra-run — the orchestrator that runs the workflow

**Location:** [`kestra-run/`](kestra-run/) · more detail: [`kestra-run/README.md`](kestra-run/README.md), [`kestra-run/SKILL.md`](kestra-run/SKILL.md)

### What it does

Takes the `workflow.yaml` + `state.json` that kestra-build wrote and actually "runs" it: reads
state → spawns a subagent to do the stage's `brief` → **verifies the result with real commands**
(never by reading a diff and guessing) → commits if it passed → automatically moves to the next
stage.

### The one rule everything follows

> Every enforcement decision must come from a command that was actually run. Never read a diff and
> decide it looks fine.

Things like `git diff --name-only` against `write_scope`, `sha256sum` against the stored hash, the
real exit code of a test command — this is exactly why it's safe to let an AI be the orchestrator
here: every decision that matters is mechanical, not an opinion.

### The loop (per round)

1. **Check the test hash** (if `state.json.test_hash` isn't `null`) — a mismatch means an
   immediate stop, not a retry, because it means someone edited the frozen tests outside the
   process.
2. **Do the stage's work** — spawn a subagent (or do it directly if it's just a mechanical check
   with no judgment needed, e.g. a `review`/`verify` stage with `write_scope: []`) — the `done`
   stage can write its own summary directly from `state.json`/`git log` without spawning anything.
3. **Verify mechanically**, always in this order: `write_scope` (real diff, revert if it strayed
   out of bounds) → `exit_criteria` (run the actual command / check the actual artifact).
4. If `exit_criteria.type` is `human_approval` (only present when the user explicitly asked for a
   manual milestone in advance) → always stop and ask for real, never auto-approve.
5. **On pass** → stage becomes `passed`; if it's the freeze stage, store the test hash; commit
   (code + `state.json` in one commit); automatically move to whichever next stage now has all its
   dependencies satisfied.
6. **On fail** → increment `attempt`, check whether the diff repeats (`seen_diffs`):
   - Still under `max_attempts` and not a repeat past `escalate_at` → go back to step 2 (resume
     the same subagent if possible, rather than spawning fresh, to avoid re-paying re-orientation
     cost).
   - `max_attempts` exhausted, or the same diff repeats past `escalate_at` → **`reworking`** — the
     one stop condition that's guaranteed to always bring in a human.

### When it stops

- `fixing → reworking` — retries exhausted, or the same diff repeats with no progress (the one
  guaranteed stop).
- `blocked` — needs a human to unblock it.
- Test-hash mismatch — someone edited the frozen tests outside the process.
- `human_approval` — only for a workflow where the user explicitly asked for a manual milestone in
  advance (not the default).

Everything else runs continuously and automatically — it doesn't ask again at every stage, or
there'd be no point having an orchestrator.

### Example usage

```
/kestra-run csv-export
"run the workflow for inventory-sync"
"resume where csv-export left off"
```

If there's no `workflow.yaml` yet, it'll tell you to run `kestra-build` first — it won't improvise
one.

### Resuming

There's no separate "resume mode" — `state.json` plus the commit from the last passing stage
already is the checkpoint. Just tell kestra-run to continue; it reads `current_stage` fresh every
time.

---

## Further reference docs

| File | Contents |
|---|---|
| [`kestra-build/references/design-principles.md`](kestra-build/references/design-principles.md) | Where every state/transition comes from, the "Default HITL posture," why there's no mid-workflow replanning |
| [`kestra-build/references/workflow-schema.md`](kestra-build/references/workflow-schema.md) | Full field reference for `workflow.yaml`, with a complete worked example (csv-export) |
| [`kestra-build/references/state-schema.md`](kestra-build/references/state-schema.md) | Field reference for `state.json` |
| [`kestra-build/references/test-quality-taxonomy-research.md`](kestra-build/references/test-quality-taxonomy-research.md) | Why tests can pass while production breaks — six recurring test-fidelity failure modes mapped to established literature, with sources |
| [`kestra-run/references/enforcement.md`](kestra-run/references/enforcement.md) | The exact real commands used for every check (write_scope diff, test-hash, commit-per-stage, rollback) |
| [`kestra-run/references/efficiency-notes.md`](kestra-run/references/efficiency-notes.md) | Why each efficiency shortcut is safe (not spawning a fresh agent every stage, resuming instead of respawning, etc.) |
| [`docs/kestra-sequence.md`](docs/kestra-sequence.md) | Five mermaid sequence diagrams of the whole pipeline — the spec→build→run handoffs, kestra-run's per-stage loop, the freeze/commit path, the `fixing`→`reworking` escalation, and the three primitives behind the freeze ([`docs/`](docs/README.md)) |

## What's intentionally "not done"

- **kestra-spec never touches code or runs anything** — it writes `0-spec.md` and stops. It does
  cover the whole spec→plan front end inline, which is why the old PM/BA/SA/architect role skills
  were retired; `meta-designer` is the one that stayed, since it produces an openable artifact this
  skill doesn't.
- **kestra-build never runs anything** — it doesn't write real code, commit, or call any skill.
- **kestra-run never generates a workflow itself** — if the file doesn't exist yet, it says so
  instead of improvising one.
- **Neither skill hard-depends on any specific specialized skill/agent** — any skill name that
  might be suggested in a stage's `brief` is only ever a suggestion ("try it if it's there"), never
  a requirement, so a generated `workflow.yaml` can move to a different machine/session with a
  different skill set and keep working.
