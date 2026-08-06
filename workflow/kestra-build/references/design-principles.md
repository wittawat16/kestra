# Design principles — condensed from the Hermes orchestration notes

Read this once before generating `on_fail` blocks, `freeze_after` flags, or branching conditions.
The workflow.yaml you produce is only as sound as your grasp of *why* each field exists.

## What this system actually buys you (and what it doesn't)

Baseline to compare against: a single unstructured prompt with no stages, no artifacts, no
verification. Against that baseline, a generated stage machine is unambiguously better on every
axis — context management, an audit trail, real verification points, resumability. That's the whole
case for existing. Everything past that baseline is refinement, not the core argument.

**Hallucination** is reduced mechanically, not eliminated: narrower per-stage scope plus real
artifacts (spec, tests, error logs) as input instead of "remember everything" lowers the chance of
guessing. The trap runs the other way too — scope a stage's context *too* thin and it hallucinates
requirements it can't see. The target is "scoped enough to be complete," not "as small as possible."

**False positives** need to be split carefully:
- Tests written after or alongside the code just *relocate* the false positive to the test itself —
  a green build on spec-violating code, backed by a test with a shallow assertion, is worse than an
  honest red because it now carries fake evidence.
- Tests written first and frozen close the biggest source of false positives outright
  (implementation confirmation bias) rather than merely moving it.
- TDD only closes half the gap: a test is only as strong as the spec it was derived from. An edge
  case the spec never considered produces a test that never considered it either — the
  implementation can miss that case and still go green. That residual belongs to spec review /
  spec-to-test traceability, not to the stage machine.

**Safe framing when describing this system:** "manages context and makes decisions checkable /
turns trust in the AI into trust in evidence, and narrows + surfaces the places you still have to
trust it." **Do not claim** "this fixes hallucination" or "this fixes false positives" — if the
system ever ships something wrong behind a green build, people will believe that green build
completely, because you set the expectation that it can't lie.

## Tests cover the anticipated; guards cover the rest

A frozen test suite is derived from acceptance criteria, and acceptance criteria enumerate cases
someone thought of. That's not a defect in how the tests were written — it's what a test *is*. The
consequence is worth stating plainly because it bounds what this whole machine can promise: for any
condition nobody imagined, there is no test, the implementation passes everything, and the first
encounter with that condition happens in production.

The complement to a test is a **runtime invariant**: a check the running system performs on itself,
which halts, refuses, or alerts rather than proceeding when something that must be true isn't. Where
a test answers "did we handle the cases we listed," an invariant answers "are we still in a state
where proceeding makes sense at all" — and it keeps answering long after the last test ran, against
inputs no one enumerated.

This distinction has a mechanical consequence for stage generation, which is why it lives here
rather than in a style guide: **no `exit_criteria` can verify that a guard exists.** The criteria
are the tests, the tests came from the anticipated cases, and an implementation with no guards at
all satisfies them completely. So the requirement has to travel in the `implement-*` stage's
`brief`, and the check for it has to be `review`'s judgment on the diff. It is the one obligation in
the design that no mechanical gate can carry, and pretending otherwise produces a pipeline that is
green, thorough-looking, and silent about the thing most likely to break it.

## Why the freeze comes after the tests are read, not when they're written

`freeze_after` exists to stop an implementation from editing a test into agreement with broken code.
That threat requires an implementation to exist. When the tests are first written, none does — so
locking at that instant defends against nothing, while giving up the only cheap window to fix a
defect *in the tests themselves*.

The asymmetry is what settles it. Before the freeze, a bad test is a bounded `fixing` loop against
the stage that wrote it. After, the only legal response is `reworking` — unlock, regenerate,
re-freeze, reset counters — which is deliberately the design's guaranteed human stop. Same defect,
same fix, radically different cost, decided entirely by which side of the lock it was noticed on.

Hence the split: a stage writes the tests, an optional reviewer reads them while they're still
editable, and a separate stage performs the freeze as an explicit act of acceptance. The freeze
stage writes nothing; it owns the test paths only so the test-hash has something to snapshot, and
re-runs the tests' own static checks against the exact commit being locked. Nothing about the
invariant weakens — there is still exactly one `test_hash`, still exactly one stage that may set it,
and still no legal path for `fixing` to touch a test path afterward. What changes is only *when* the
door closes: after someone has looked, rather than before.

## States (per stage)

| State | Meaning |
|---|---|
| `pending` | not started |
| `running` | a skill is doing the work |
| `verifying` | running exit criteria (test/lint/static check) |
| `passed` | verified, can proceed |
| `fixing` | verify failed — fix **code only**, tests stay locked |
| `reworking` | fix-loop exhausted — bounce **up** to spec/test regeneration |
| `waiting_approval` | HITL gate — stopped, waiting on a human |
| `blocked` | terminal — needs a human to intervene |

## Core transitions

```
verifying --pass--> passed
verifying --fail--> fixing

fixing:
  attempts += 1
  d = semantic_hash(proposed_diff)
  if attempts >= max_attempts:  -> reworking (reason=max_attempts)
  elif d in seen_diffs:         -> reworking (reason=no_progress)   # catches A→B→A loops
  else:
    seen_diffs.add(d)
    apply(code_only) -> verifying

reworking:
  unlock(test_write)
  goto spec-review or generate-tests     # top-down, never a patch to the existing test
  re-freeze()                            # new test-hash snapshot
  reset(attempts, seen_diffs)
```

**The one thing every generated `on_fail` must get right:** `fixing → reworking` is an escalation
upward, never sideways. `fixing` can only ever produce diffs to non-test paths. The moment it's
exhausted, the system is admitting "what we froze was wrong" and re-deriving from above — it is
never patching the test to match the code that's currently broken. If your generated workflow has a
`fixing` stage whose `write_scope` includes test paths, or a `reworking` stage that doesn't reset
`attempts`/`seen_diffs` and re-freeze, you've regenerated the exact failure mode TDD exists to close.

**The one decision this design deliberately leaves to a human or a hard threshold:** the
`fixing → reworking` transition itself — the moment the system accepts "the frozen artifact was
wrong." Everything else in the state machine can be fully automated.

## The three freeze primitives, and how they compose

| Concern | Actually implemented as |
|---|---|
| Freezing tests | commit + test-hash invariant + write-scope allowlist |
| Loop termination | `fixing` ↔ `reworking` transition + `seen_diffs` set |
| HITL (opt-in) | `human_approval` is just an `exit_criteria.type` whose "verification" is a human saying so — the orchestrator reads state, sees that type, and stops, exactly like resuming from a crash. Not a new subsystem. The generator's default template no longer includes any stage of this type — see "Default HITL posture" below. |
| Atomic rollback | the same commit-per-stage that implements freeze |

## Default HITL posture: human only guards the false-positive exit

The earlier version of this design treated `spec-review`, `review`, and the terminal
`waiting_approval` as HITL gates by default — a human had to sign off at each. That's no longer
the default. Confirmed by direct discussion: once a spec has already passed through whatever
upstream spec-sharpening and analysis skills you use (PM-style sharpening, business-analysis,
solution-architecture, design, as needed) with a human in that upstream loop, and once
`review`/`security` are themselves independent automated passes, a *second* human sign-off inside
the stage machine adds friction without adding a check that isn't already covered — **except** for
the one place no mechanical check can reach: knowing whether a persistently-failing stage means
"the code is wrong" or "the frozen spec/tests are wrong." That judgment call is what
`fixing → reworking` has always existed to make, and it already stops for a human by definition.
So the redesign is: collapse every other "let a human decide" point into that same mechanism
instead of inventing a second one.

Concretely, in kestra-build's default generated template:

- **`spec-review`** becomes a mechanical check on the spec artifact — `exit_criteria.type: command`
  greps a `VERDICT: CLEAR` / `VERDICT: CHANGES_REQUESTED` line the same way `review` does. This
  bullet originally described that check as trivial (e.g. "does `0-spec.md` have a non-empty
  `acceptance_criteria` list"), which is why it went straight to `reworking` on any failure — for a
  check that shallow, any failure really was a "what we're building from is fundamentally wrong"
  case. In practice the brief this generator writes for `spec-review` is not that shallow: it checks
  contradictions between Runtime Invariants and Edge Cases, unfilled Reality Constraints columns, AC
  testability, and (since the execution-verified self-check) whether the spec's own claims survive
  actually being run. Most of what it catches at that depth is exactly as fixable in place as what
  `review` catches in a diff — a missing file in Files-to-Touch, an uncounted reference, a stale
  cross-reference — not a case where the feature's intent itself is in question. So `spec-review`
  now gets the same bounded attempt `review` gets: `on_fail.action: fixing`, `max_attempts: 2`,
  `escalate_at: 2`, with `write_scope` covering `source_spec` itself (there's no separate
  implement-the-spec stage to `target`, unlike `review`, so `spec-review` owns that path directly
  rather than through a `target`). Only once that bounded loop is exhausted, or the same diff to the
  spec repeats without resolving the finding, does it fall through to `reworking` — still the one
  human stop, just reached the same way every other judgment stage reaches it instead of skipping
  straight there. A defect that genuinely calls the feature's own intent into question — not a fixable
  gap but a "we don't actually agree what this should do" — usually announces itself by failing to
  converge inside those two attempts, which is exactly what `reworking` is for.
- **`review`** (and `security` alongside it) spawns the same automated agents as before, but their
  verdict becomes a real artifact (`VERDICT: CLEAR` / `VERDICT: CHANGES_REQUESTED` on its own
  line) that `exit_criteria.type: command` greps for a real exit code — no human reads the diff
  before this passes. On `CHANGES_REQUESTED`, `on_fail.action: fixing` with `target:
  <implement-stage-id>` (see `workflow-schema.md`) gives the implementation stage a bounded number
  of attempts to address the findings, exactly like a failing test would. Only once that bounded
  loop is exhausted (or stuck repeating the same diff) does it fall through to `reworking` — the
  one and only human stop.
- **The terminal stage** (formerly `waiting_approval`) becomes a mechanical "everything upstream
  passed, write the completion summary" stage — a `write_scope` holding just that summary file, and
  `exit_criteria.type: artifact_exists` on it. Nothing left to approve; every judgment-bearing
  check already ran and already had its own escalation path.

`human_approval` is not removed from the schema — it stays available for a user who explicitly
wants a manual milestone (e.g. "I want to eyeball this myself before it touches production," a
`deploy-readiness` follow-up, or a spec with unusually high blast radius). But it is opt-in: only
add it when the user asks for that specific checkpoint, never as the generator's own default.

**Single invariant everything stands on:** `state.json` is the source of truth, and it always
travels with the commit. As long as that holds, the orchestrator that eventually reads your
generated workflow can stay dumb — read state, check hash, pick a stage, apply scoped, commit, loop.

## Conditional branching — keep it declarative

Branching belongs in the workflow (it is *not* the same thing as mid-run replanning — a defined-in-
advance fork is conservative and consistent with the "orchestrator stays dumb" thesis). But keep
every condition scoped to **artifact existence or exit code**, nothing richer. The moment a
condition needs its own debugging, the "declarative, freezable" property is gone and you've
smuggled a programming language into a YAML file. If a user's request needs real replanning
mid-run, say so explicitly — don't fake it with an over-expressive condition.

## No mid-workflow replanning

The apparent contradiction — "AI shouldn't control the workflow" vs. a Workflow Generator that *is*
AI deciding the whole plan upfront — resolves like this: the decision doesn't disappear, it just
moves to the front and gets frozen there. That's the trade being made: auditable and deterministic,
at the cost of not being able to replan once execution starts. The chosen mitigation for "the plan
turns out wrong mid-run" is exactly the two mechanisms above — conditional branching for paths
anticipated in advance, and `reworking` for bouncing back up to re-derive from spec. Nothing else.

## Vendor independence is structural, not behavioral

A generated `workflow.yaml` is portable across models/orchestrators as a *structure*. The prompts
any given stage's skill runs on are not — they're tuned per model. Don't imply that a portable
workflow file means identical results across every model that might execute it.

This is exactly why a stage's `brief` never hard-binds a specific skill by name or ID. Skills
aren't invoked from outside a Claude session — they're descriptions a spawned Claude reads and
decides to use on its own, the same triggering mechanism as any normal session. The generator runs
inside a live session and can see which skills are actually installed *right now*, so it's fine to
name a relevant one as a suggestion inside `brief` — but the workflow may execute later, on a
different machine, with a different skill set. A hard `skill:` field would make the frozen artifact
brittle to exactly the environment drift this section warns about.
