# workflow/ — kestra-spec, kestra-build, kestra-run & kestra-exam

These four skills work together as a **spec-sharpener + generator + orchestrator** for building
and running a "stage machine" that actually enforces TDD (not just asking the AI nicely to write
tests first). It freezes tests once written, restricts which files each stage may touch, and
commits per stage so you can always roll back or resume.

```
a human-vetted tracker ticket (in-chain)  ·  or a sharpened idea from /grilling (standalone)
                                             (/wayfinder first, if it's too big for one session)
   │
   ▼
┌─────────────┐   in-chain: checks the vet → commits the ticket verbatim → raises it into
│ kestra-spec  │   0-spec.md as a 2nd commit · standalone: one clarifying pass, one commit
└──────┬──────┘   either way: testable ACs, needs_* flags, External Interface, Exit Criteria,
       │          business rules, design notes, a verified codebase survey — one pass
       │
       ├───────────▶ kestra-exam (opt-in, only where the mode below is `full`): derives
       │             one check per AC from 0-spec.md, red-proofed before any code exists
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

None of these skills has a hard dependency on any other skill — if a stage's brief wants to
suggest a specialized skill (e.g. an implement skill, a review skill), that only ever appears as a
"suggestion" inside the brief text. Whatever gets spawned to do that stage's work still runs fine
if that skill isn't installed. `kestra-exam` is the opt-in fourth skill in this folder: it is keyed
off the mode `kestra-build` already recorded (`full` ⇒ exam, `lite` ⇒ deliberately none) and names
the other three only as suggestions.

---

## kestra-spec — the spec sharpener

**Location:** [`kestra-spec/`](kestra-spec/) · detail: [`kestra-spec/SKILL.md`](kestra-spec/SKILL.md)

### What it does

In one pass, produces a single `0-spec.md`: testable acceptance criteria, explicit error states,
the `needs_ba`/`needs_ui`/`needs_sa`/`needs_devops` flags `kestra-build` reads, the test seam
(**External Interface**), the stop condition (**Exit Criteria**), business rules (when `needs_ba:
true`), design notes (when `needs_ui: true`), solution-architecture decisions (when `needs_sa:
true`), and a codebase survey with every file path verified to exist.

Where the `meta/` group splits this same work across five skills and five files, `kestra-spec`
does it as one continuous pass, one file — so nobody has to remember to chain five skills by hand,
and `kestra-build`'s stage agents don't have to guess at gaps left by a handoff.

### Two input modes, decided mechanically

**In-chain** iff the invocation names a tracker ticket (a URL, `#N` plus the repo, or a named local
tracker file `<NN>-<slug>.md`). **Standalone** otherwise. It never goes looking for a ticket nobody
named — no named ticket *is* the standalone signal, and guessing one is how unvetted intent gets in.

| | In-chain | Standalone |
|---|---|---|
| Intent comes from | the named ticket, human-vetted | a hand-written idea or `/grilling` output, plus this session's clarifying pass |
| Vetted gate | required — no vet, no work | none |
| Commits | two: the ticket verbatim, then the raise | one: the raise |
| `> Spec-ticket:` / `> Vetted:` preamble lines | URL-backed only; local-file chains stay unmarked | never written |
| `needs_ba` silence on intent | bounces upstream | asked here and now, answer cited `Q<n>` |
| End-of-pass validator | URL-backed: five `FAIL`s; local-file: `WARN` because deliberately unmarked | the same five print `WARN` |

**Standalone is a first-class path, not a degraded one.** The vetted gate exists because in-chain
nobody is watching the moment intent gets invented; standalone has the human in the loop by
construction — they invoked it, in this session, and they answer the questions. Same behavior,
different guarantee. Standalone keeps the whole clarifying pass: a rough ask ("add CSV export")
still gets a short scope/error-state/ambiguity interview before anything is written.

A named local tracker file remains in-chain: its sibling `.vet` supplies the content-hash gate and
it still produces the two adjacent commits. It omits the URL-only preamble marker, so its five
conditional validator checks WARN; that is a transport limitation, not permission to skip vetting.

### The vetted gate, and the two-commit raise (in-chain)

`kestra-spec` is **read-only on the tracker** — it never comments, labels, edits or closes, so it
cannot approve its own input. The vetted signal is a comment on the ticket whose first line is
`VETTED-FOR-KESTRA: <sha256 of the ticket body at vet time>`, produced once by a human and pasted
in; the newest such comment wins, and its hash must equal the live body hash. Binding the approval
to a content hash is what makes it mean *vetted **this** text*: a body edited after the vet is
caught, and a thin ticket can't launder itself through a citable URL. Named residual: a token can
post that comment, so it doesn't prove a human typed it — what it buys is that `kestra-spec` never
writes it, the approval names exact text, and the artifact is visible, attributed and dated.

No vet, or a stale one → it stops before doing any work, commits nothing, and prints the line for
the human to paste. If the ticket itself is thin or missing, `to-spec` is the *suggested* tool for
writing it — a suggestion only, never a requirement, same rule as every other cross-skill mention
here.

With the vet in hand it makes exactly two commits, with nothing committed between them:

| Commit | Subject | What it carries |
|---|---|---|
| 1 | `spec(<feature-id>): materialize vetted ticket verbatim` | the ticket body written to `0-spec.md` unmodified, plus this run's own copies of `requirement_surface.py` and `validate_spec.py`. Message records `Spec-ticket: <url>` and `Ticket-body-sha256: <hex>` |
| 2 | `spec(<feature-id>): raise vetted ticket into 0-spec.md` | exactly one path — the raised `0-spec.md` overwriting the verbatim body, so the raise is literally one `git diff`. Message records `Spec-ticket:` and `Vetted-by:` |

`tr -d '\r'` is the one declared normalization (GitHub returns web-authored bodies with CRLF);
nothing else is normalized, because more would make "verbatim" negotiable. After commit 2 it
re-fetches the ticket and `diff`s it against commit 1's file — a non-empty diff is a hard stop, no
handoff, with two honest fixes only: re-materialize from scratch, or bounce because the ticket
genuinely changed mid-pass. Editing the committed verbatim file, or amending commit 1, is banned —
that's "patch the test to match broken code" wearing spec clothing. Which commit is *the* raise is
resolved by an exactly-one-match convention (a re-raise replaces its predecessor rather than
stacking), documented in [`kestra-spec/references/chain-provenance.md`](kestra-spec/references/chain-provenance.md).

### Bounce — intent-silence goes back upstream

In-chain, when the ticket doesn't say *which outcome is correct* for a branch the feature must
take, `kestra-spec` **bounces** rather than authoring the business rule inline: it finishes both
commits (the work is preserved and inspectable), sets the status line to `BLOCKED_ON_INTENT`,
writes one fixed-shape `BOUNCE-<n>` entry under **Open Items** naming the undecided branch, the ACs
it blocks and who decides — and does not hand off to `kestra-build`.

The discriminator is deliberately narrow. A missing number, threshold, name, copy string or
filename is **not** a bounce: pick a sane default, mark the line `⚠ inferred`, record a
non-blocking `OI-n`, keep going. Only a genuinely undecided *branch* stops the pass. Flagging and
continuing isn't an option, because the default workflow has zero `human_approval` stages, so a
"pending" flag would have no consumer and the build would proceed on invented intent.

### The provenance rule

Every intent line the sharpening pass adds cites its source or carries `⚠ inferred` — an intent
line being any line that asserts what the system must do (an FR bullet, an edge case, an invariant
row, an AC, an **AC Coverage Map** row, an External Interface operation). Sources are `US-n` (user
story), `ID§x` (the ticket's Implementation Decisions), `TD`/`FN`/`OOS`/`PS`, `IDEA§x` / `Q<n>`
(standalone: an idea heading, or an answer from this session's clarifying pass), or
`verified:<probe>` for something confirmed by running code. A line with neither a source nor
`⚠ inferred` is a defect, not a style miss: the AC Coverage Map's new `Source` column without the
rule behind it is a mechanically-green column that lies.

### The end-of-pass mechanical check

Before committing the raise, `kestra-spec` runs `validate_spec.py` and `requirement_surface.py` on
its own `0-spec.md`, from the copies it emitted into the run folder. `spec-review` fires only after
`kestra-build` has folded the spec into stages, and `lite` mode folds `spec-review` into
`generate-tests` — so a `lite` run would invoke the validator zero times, and anything derived from
the raise would be built on an unchecked surface. This is an additional, earlier check point, not a
replacement for the `spec-review` stage.

Five template obligations are checked **conditionally**, off the chain marker (the single
`> Spec-ticket:` preamble line, written by the raise and nowhere else): a `Source` column in the AC
Coverage Map, a `## External Interface` section with real content, exactly one recorded
mode-prediction fact, a `## Exit Criteria` section with its stop head and `progress:` fragments,
and the delimiter precondition. Marker present ⇒ `FAIL`; absent ⇒ `WARN`.
A marked spec is one this repo's own skill produced from a vetted ticket, so its template is a
contract; an unmarked spec is local-file-tracked, hand-written, standalone or foreign, and the same
missing section alone proves nothing — every pre-existing check behaves identically in both modes. If no copy of the
scripts can be found at all, it prints one `WARN`, self-applies the checklist and continues:
`kestra-spec` must not hard-depend on `kestra-build` being installed. Copy **both scripts or
neither**, though: with `validate_spec.py` present but `requirement_surface.py` missing, the
delimiter check cannot run at all, and *cannot run* reports through the same conditional — `FAIL`
under the marker, `WARN` without it. Not-run is not passed.

### What comes before this: `/grilling`, and `/wayfinder` when the effort is bigger

In-chain the upstream is the vetted tracker ticket itself, written with `to-spec` if you have it
(a suggestion, never a requirement). Standalone, `kestra-spec` expects the ambiguity to be mostly
gone already — it reads what was settled and doesn't re-open it. Two upstream skills get you there,
and they compose rather than compete:

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

* **Runtime Invariants** — conditions that must hold *every time the system runs*, enforced in
  production rather than verified once in a test. Each names the condition, how it's detected at
  runtime, and what happens when it's violated — halt, refuse, or alert. A check that logs and
  carries on doesn't count; that's the failure mode the section exists to prevent.
* **Reality Constraints** — what the world outside the feature actually does, which is the
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
spec + generated workflow using this format. That spec deliberately keeps the *pre-*two-mode
template shape — it's the unmarked standalone/foreign-shape exemplar, and the validator's five
conditional checks print `WARN` against it, which is the standalone contract demonstrated on a real
file. The current template lives in [`kestra-spec/SKILL.md`](kestra-spec/SKILL.md).

**It writes no code and runs no stage** — it writes `0-spec.md`, commits it (two commits in-chain,
one standalone), and stops. It is read-only on the tracker throughout. Hand it off to
`kestra-build` next — unless the status line says `BLOCKED_ON_INTENT`, in which case the handoff is
back upstream, to whoever owns the rule the ticket didn't decide.

### Example usage

```
"raise this vetted ticket into 0-spec.md: https://github.com/acme/app/issues/123"
"materialize issue #123 into a spec"
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

1. Read/sharpen the spec until it has clear acceptance criteria. Three input forms, decided
   mechanically before anything else: a run folder holding `0-spec.md` **plus** a named sliced
   ticket set (a *sliced fold* — GitHub refs, or a directory of local-file tickets); `0-spec.md`
   alone (a *monolithic fold*, unchanged); or a chain-marked spec with no set named, which asks
   **once** and **never searches the tracker for tickets nobody named** (guessing a set is how
   unvetted scope enters). On a sliced fold each ticket is copied verbatim into
   `<run>/tickets/<id>.md` (`tr -d '\r'` and nothing else — the same normalization `kestra-spec`
   uses, so "verbatim" means one thing at both ends of the chain), embedded in its stage brief
   between sha256 delimiters, and listed in a `tickets:` map anchored to the raise commit. Each
   sliced AC's Source label is resolved from the spec's own `## AC Coverage Map` rather than graded
   against a second vocabulary, and an AC matching no map row refuses the fold. This is the only
   point in an entire run where the tracker is read at all.
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
7. **Always dry-run first**: `python3 <run-folder>/validate_workflow.py <run-folder>` — the
   validator and `requirement_surface.py` are emitted into the run folder beside the spec, and the
   validator imports that sibling with no path setup, so a run folder stays self-checking wherever
   it is copied. A zero-LLM structural check (no PyYAML, no AI judgment) that catches:
   - Missing `on_fail.target` on a `write_scope: []` + `action: fixing` stage
   - `write_scope` overlapping a path that was already frozen as a test path
   - Independent stages whose `write_scope`s collide (a real risk if they run in parallel)
   - `freeze_after: true` missing, or set on more than one stage
   - Dependency cycles / unreachable stages
   - `exit_criteria` or `on_fail` missing required fields
   - `state.json` not matching the stage ids in `workflow.yaml`
   - The `spec_anchor` triple (`raise_commit` / `surface_hash` / `extractor_version`) — an absent
     anchor is a `WARN` (a standalone or hand-written spec simply isn't anchored), a **partial**
     one is a `FAIL`, and a recorded `surface_hash` that no longer matches the spec recomputed now
     is a `FAIL` telling you to re-fold, never to edit the anchor
   - On a sliced fold: every embedded ticket block against `tickets/<id>.md` by sha256, the
     `tickets:` map against the stage briefs in both directions, and each ticket's `ac_hash`
     against the recomputed surface — which is what makes "the fold refuses" a real exit code
     instead of an agent's promise

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
   process. On an anchored workflow, before every work round recompute the working and raise-side
   requirement surfaces and require both to match the recorded anchor. A malformed/unreachable
   anchor, failed recompute, or mismatch is a fail-closed hard stop, never a retry or `reworking`.
2. **Do the stage's work** — spawn a subagent (or do it directly if it's just a mechanical check
   with no judgment needed, e.g. a `review`/`verify` stage with `write_scope: []`) — the `done`
   stage can write its own summary directly from `state.json`/`git log` without spawning anything.
   An anchored sliced stage gets the slim pack (its proven single-ticket brief + provision layer,
   spec read on demand) only after this round's provenance and surface checks pass. Unanchored,
   monolithic, or ambiguous stages get the full spec verbatim; a failed anchored gate stops instead
   of falling back.
3. **Verify mechanically**, always in this order: `write_scope` (real diff; snapshot violating
   paths before reverting them, then fail the scope check) → `exit_criteria` (run the actual command
   / check the actual artifact).
4. If `exit_criteria.type` is `human_approval` (only present when the user explicitly asked for a
   manual milestone in advance) → always stop and ask for real, never auto-approve.
5. **On pass** → stage becomes `passed`; if it's the freeze stage, store the test hash; commit
   (code + `state.json` in one commit); automatically move to whichever next stage now has all its
   dependencies satisfied.
6. **On fail** → increment `attempt`, check whether the diff repeats (`seen_diffs`):
   - With `exit_criteria.progress`, measure attempt 0 from the real criterion before the first work
     round and store it as the first `progress_history` entry — never use a prose baseline. Append
     each failed attempt's measurement; two consecutive failed measurements that do not move toward
     the declared target route to `reworking` before the next attempt.
   - Still under `max_attempts` and not a repeat past `escalate_at` → go back to step 2 (resume
     the same subagent if possible, rather than spawning fresh, to avoid re-paying re-orientation
     cost).
   - `max_attempts` exhausted, or the same diff repeats past `escalate_at` → **`reworking`** — the
     one stop condition that's guaranteed to always bring in a human.

### When it stops

- `fixing → reworking` — retries exhausted, the same diff repeats, or two consecutive failed
  progress measurements do not move toward the target (the one guaranteed stop).
- `blocked` — needs a human to unblock it.
- Test-hash mismatch — someone edited the frozen tests outside the process.
- Anchored-surface mismatch — malformed/unreachable anchor or unequal raise/current surfaces;
  fail-closed, never `reworking`.
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

## kestra-exam — the spec-derived exam

**Location:** [`kestra-exam/`](kestra-exam/) · detail: [`kestra-exam/SKILL.md`](kestra-exam/SKILL.md)

### What it does

Turns the acceptance criteria already sitting in `0-spec.md` into a runnable exam: one check per AC
in a single `exam.py`, plus a `manifest.md` mapping every check back to its AC and the `Source` cell
it came from. The exam is **red-proofed** before any implementation exists — it runs in a disposable
clone at the raise commit, where each check has to fail for the right reason (a behavioral failure,
not a missing import), so a later green can't be an accident of the harness.

It reads only the in-surface sections of the spec (the ones `requirement_surface.py` extracts)
and deliberately never reads the implementation plan, the file list, or the code: an exam derived
from the implementation's shape stops being an independent derivation of the requirement.

What it does **not** claim: it covers what the spec asked for, never runtime invariants or the guards
that enforce them (`kestra-build/references/design-principles.md` owns those), and it is not a fix
for hallucination. The claim is narrower and checkable — it turns trust in the AI into trust in
evidence.

### When it runs, and when it does not

Opt-in, keyed off the mode `kestra-build` already recorded: `full` ⇒ build the exam, `lite` ⇒
deliberately no exam. A standalone (unmarked) spec is allowed too. Nothing else in the pipeline
depends on it — `kestra-spec`, `kestra-build` and `kestra-run` all run unchanged where it isn't
installed, and it names them only as suggestions.

### Where the exam lives

Outside the repo, in the user-level exams directory under `~/.kestra/`, keyed by origin and feature slug
(`<origin-key>/<feature-slug>/`) and `git init`'ed per feature — so
the exam is evidence *about* the work rather than one more file the work can quietly edit. The
`<origin-key>` is derived from `git remote get-url origin`; a repo with no `origin` is a hard stop
rather than a fallback name, because two clones or forks sharing a directory basename would otherwise
cross-wire onto one exam dir. One durable pointer record per exam — a `kestra-exam: <feature-slug>`
tracker ticket, or a local `.pointer` file on tracker-free repos — carries the hashes; it is edited
in place, and more than one match is a hard fail that is never resolved by taking the newer.

### Staleness refusal

Every run compares a triple — the spec's surface hash, the raise commit, the extractor version —
across the manifest, the pointer and `exam.py`. Any disagreement means **no verdict is emitted at
all**: it prints `REFUSED: exam is stale` and exits non-zero instead of reporting a pass or a fail
against a spec that has moved. A spec change is answered by regeneration (a delta plan naming exactly
which checks move, and which carry over untouched), never by editing the anchor.

Building the gate *runner* — the pre-delivery job that executes exams — is explicitly **not** part of
this skill, so nobody implements a phantom gate.

### Example usage

```
"build the exam for workflows/runs/csv-export"
"is the csv-export exam still fresh?"
"the spec changed — regenerate the exam"
```

---

## Suggested models, when spawning a skill as a subagent

Measured recommendations for whoever *spawns* one of these skills with a model to choose — a
suggestion to offer the user, not a default to pick silently. **None of them apply when a skill runs
inline in an already-active session**, because a skill cannot switch that session's model on its
own. That is why they live here rather than in the skill bodies, where they paid context load on
every invocation without ever being actionable by the agent reading them. `kestra-exam` has no
measurement, so it has no entry.

**`kestra-spec` — Opus 5.** Measured same-effort against Sonnet 5 on this same skill: Opus caught a
real spec defect (an execution-verified edge case, e.g. a spread-order default-overwrite bug) that
Sonnet's read-and-reason pass missed entirely, for ~14% more tokens.

**`kestra-build` — Sonnet 5.** Measured same-effort against Opus 5 on this same skill: cost came out
roughly a wash, and Sonnet's one real defect found (a wrong claim about ESM import failure behavior
baked into a generated brief) is now fixed in that skill's own `generate-tests` guidance, narrowing
the gap that motivated Opus elsewhere.

**`kestra-run` — Sonnet 5.** Measured same-effort against Opus 5 running the same live workflow end
to end: the orchestration logic itself (context-pack composition, mechanical verification, scoped
stopping) was identical and correct on both, and cost came out a wash — this layer showed no
model-sensitivity, so the cheaper default is the sane one. What a spawned *stage* subagent decides
is a separate question: see that stage's own `model` field in
[`kestra-build/references/workflow-schema.md`](kestra-build/references/workflow-schema.md).

Every figure above is a dated single-run measurement against the model generation available when it
was taken. Re-measure before relying on one.

## Further reference docs

| File | Contents |
|---|---|
| [`kestra-spec/references/chain-provenance.md`](kestra-spec/references/chain-provenance.md) | The chain marker's exact form and its degenerate cases, the exactly-one-match rule for finding the raise commit, re-raising after a bounce or a re-vet, and tracking on a local file instead of GitHub |
| [`kestra-build/references/design-principles.md`](kestra-build/references/design-principles.md) | Where every state/transition comes from, the "Default HITL posture," why there's no mid-workflow replanning |
| [`kestra-build/references/workflow-schema.md`](kestra-build/references/workflow-schema.md) | Full field reference for `workflow.yaml`, with a complete worked example (csv-export) |
| [`kestra-build/references/state-schema.md`](kestra-build/references/state-schema.md) | Field reference for `state.json` |
| [`kestra-build/references/ticket-fold.md`](kestra-build/references/ticket-fold.md) | The sliced fold in full — the three input forms, verbatim materialization, Source-label resolution off the AC Coverage Map, the fold-start steps F0–F5 with their exact refusal texts, and re-fold change detection |
| [`kestra-build/references/test-quality-taxonomy-research.md`](kestra-build/references/test-quality-taxonomy-research.md) | Why tests can pass while production breaks — six recurring test-fidelity failure modes mapped to established literature, with sources |
| [`kestra-build/references/full-mode-stages.md`](kestra-build/references/full-mode-stages.md) | The `mode: full` half of stage derivation — what `spec-review` must actually check, `test-review`'s risk table and the condition under which its check folds into `generate-tests` instead of becoming a stage, the per-run mutation-harness contract, the `evidence/` convention, sibling `implement-*` and the shared-contract stage, splitting `review` per component, and `deploy-readiness` (which appends to lite too) |
| [`kestra-build/references/stage-derivation.md`](kestra-build/references/stage-derivation.md) | The stage rules only some specs reach, one section per branch, each named by step 3's gate table — when a real `design-tests` stage is justified, why verdict artifacts have the shape they do and what a finding asserting a number owes, a wide refactor's two legal shapes, keeping each batch's own gate honest on a shared integration branch, and turning a repo-declared mandatory pre-merge gate into a stage |
| [`kestra-run/references/enforcement.md`](kestra-run/references/enforcement.md) | The exact real commands used for every check (write_scope diff, test-hash, commit-per-stage, rollback) |
| [`kestra-run/references/efficiency-notes.md`](kestra-run/references/efficiency-notes.md) | Why each efficiency shortcut is safe (not spawning a fresh agent every stage, resuming instead of respawning, etc.) |
| [`kestra-exam/references/exam-script-contract.md`](kestra-exam/references/exam-script-contract.md) | `exam.py`'s shape — `@check`, the `expect*` family (and why a bare `assert` is banned), the three seam kinds, the behavioral-vs-infrastructure red discriminator, the exit ladder and the `--json` schema |
| [`kestra-exam/references/manifest-schema.md`](kestra-exam/references/manifest-schema.md) | `manifest.md`'s seven sections in fixed order, every column, the closed Red-proof vocabulary, the fingerprint formulas and the verdict contract, verbatim |
| [`kestra-exam/references/gate-procedure.md`](kestra-exam/references/gate-procedure.md) | The pre-delivery gate — its sweeps and exemption boundary, pointer discipline, and hash-vs-pointer comparison; building the runner itself is out of scope |
| [`kestra-exam/references/regeneration.md`](kestra-exam/references/regeneration.md) | What moves when the spec moves — the delta map, the fingerprints, the four scopes, carry-over, and the exam-dir commit subjects |
| [`kestra-run/scripts/stage_transition.py`](kestra-run/scripts/stage_transition.py) | The fixing/reworking/escalation decision as a pure function — an executable spec for kestra-run's steps 1/3/5/6, exhaustively testable without spawning anything, the same way `validate_workflow.py` replaces eyeballing a generated workflow. Single-stage only; sibling-failure combining is deliberately not modeled. **Nothing imports it and its test suite is gone** — restoring one is an open gap, listed here so the file is at least findable |

## What's intentionally "not done"

- **kestra-spec never touches code and never runs a stage** — it writes `0-spec.md`, commits it,
  runs the two validator scripts on its own output, and stops. It does cover the whole spec→plan
  front end inline, which is why the old PM/BA/SA/architect role skills were retired;
  `meta-designer` is the one that stayed, since it produces an openable artifact this skill doesn't.
- **kestra-spec never writes to the tracker** — no comment, label, edit or close, so it cannot vet
  its own input. A missing or stale vet stops the pass instead.
- **kestra-spec never invents an undecided business rule in-chain** — a branch the ticket didn't
  decide bounces upstream as `BLOCKED_ON_INTENT`. `needs_ui` and `needs_sa` work stays inline as
  before; only genuine intent-silence bounces.
- **kestra-build never runs anything** — it doesn't write real code, commit, or call any skill.
- **kestra-run never generates a workflow itself** — if the file doesn't exist yet, it says so
  instead of improvising one.
- **kestra-build reads the tracker exactly once, read-only** — at fold time, to copy each *named*
  ticket verbatim into the run folder. It never edits, comments on, closes or slices a ticket, never
  searches for tickets nobody named, and never re-folds mid-run: a spec or ticket that moved is
  answered by re-folding from a clean state, not by patching a running workflow.
- **kestra-exam never builds the gate runner, and never emits a verdict against a moved spec** — it
  writes and red-proofs the exam, records the anchor triple, and the moment those copies disagree it
  refuses outright (no pass, no fail) and points at regeneration. It is also not pitched as a fix
  for hallucination; the narrower, checkable claim is that a verdict rests on evidence instead of on
  the AI's own report.
- **None of these skills hard-depends on any specific specialized skill/agent** — any skill name that
  might be suggested in a stage's `brief`, or named as the way to write the ticket upstream
  (`to-spec`), is only ever a suggestion ("try it if it's there"), never a requirement. So a
  generated `workflow.yaml` can move to a different machine/session with a different skill set and
  keep working, and `kestra-spec` still runs where `to-spec` and `kestra-build` aren't installed.
