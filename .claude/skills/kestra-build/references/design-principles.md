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

- **`spec-review`** becomes a mechanical sanity check on the frozen spec artifact (e.g. does
  `0-spec.md` have a non-empty `acceptance_criteria` list) — `exit_criteria.type: command`,
  `on_fail.action: reworking` (a malformed spec is exactly a "what we're building from is wrong"
  case, so it escalates the same way an exhausted `fixing` loop would).
- **`review`** (and `security` alongside it) spawns the same automated agents as before, but their
  verdict becomes a real artifact (`VERDICT: CLEAR` / `VERDICT: CHANGES_REQUESTED` on its own
  line) that `exit_criteria.type: command` greps for a real exit code — no human reads the diff
  before this passes. On `CHANGES_REQUESTED`, `on_fail.action: fixing` with `target:
  <implement-stage-id>` (see `workflow-schema.md`) gives the implementation stage a bounded number
  of attempts to address the findings, exactly like a failing test would. Only once that bounded
  loop is exhausted (or stuck repeating the same diff) does it fall through to `reworking` — the
  one and only human stop.
- **The terminal stage** (formerly `waiting_approval`) becomes a mechanical "everything upstream
  passed, write the completion summary" stage — `write_scope: []`, `exit_criteria.type:
  artifact_exists` on a generated summary file. Nothing left to approve; every judgment-bearing
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
