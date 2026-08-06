# Stage-derivation rules only some specs reach

Every rule here is mandatory where it applies and dead weight where it isn't, which is why it lives
outside `SKILL.md` step 3 rather than inside it. Step 3's gate table names the spec fact that sends
you to each section; if no gate row fired, you are not missing anything — go on to step 4.

**Sections 1 and 3–5 are gated.** Section 2 is background for a rule that is inline in step 3
because it applies to every run — nothing sends you there, and skipping it costs you nothing.

**The five sections:** 1. splitting `design-tests` out · 2. verdict artifacts, background only ·
3. a wide refactor · 4. batches that can't stay green alone · 5. a repo-declared pre-merge gate

---

## 1. Splitting `design-tests` out of `generate-tests`

*Reached when: the user wants to approve the scenario list before any test code exists, or the spec
is too large for one spawn to write the table plus all test code. Otherwise step 3's default — the
same-spawn scenario table — is the whole answer.*

Be honest about what a separate stage with `exit_criteria.type: artifact_exists` actually buys:
nobody reviews that table (nothing gates on more than its existence, and `kestra-run`'s default
HITL posture auto-advances through an `artifact_exists` check), so a coverage gap in the table
would translate 1:1 into the frozen tests exactly as it would without the split — the split buys
decomposition (a smaller, focused spawn per stage), not assurance, and presenting it as the latter
is the defect this rule used to have. The same-spawn table still gets you the traceability
benefit — `test-review` and a human glancing at the diff can recognize a missing scenario as a
missing table row — at zero extra spawn cost, and `on_fail.target: generate-tests` can legally
edit both the table and the tests together since they're the same stage's `write_scope`.

**Only split into a real, separate `design-tests` stage in two cases**, both narrow: (1) the
user explicitly asks to approve the scenario list before any test code exists — then give it
`exit_criteria.type: human_approval` on the table, never `artifact_exists`, so the split
actually buys the assurance its name implies rather than recreating the same
assurance-without-a-mechanism gap one level up; or (2) the spec is genuinely too large for one
spawn to write the full scenario table plus all test code — context-size decomposition, the one
benefit user opt-in alone can't reach, since the user won't know to ask for it. Flag this case
explicitly in the mode/stage audit line ("spec too large for one spawn to write table plus all
test code — splitting for context size, not for coverage assurance") rather than silently
defaulting to it. In either case: `design-tests` writes nothing but the table,
`write_scope`d to that artifact only, `depends_on` the same stage `generate-tests` would have;
`generate-tests` then `depends_on: [design-tests]` and translates the approved table into real
test code 1:1 — its own judgment burden shrinks to "does this code match the plan," not "did I
think of everything." Two traps either way: if the `generate-tests` brief could already
enumerate every scenario by name up front (BRs, edge cases, states), a separate table just
duplicates the brief at the cost of a full extra spawn; and on a `needs_ui` spec, `design-tests`
must stay downstream of `design`, because design.md's screen states can't appear in a plan
written before design.md exists, while `generate-tests` is simultaneously forbidden from
inventing rows the plan lacks — a coverage gap with no legal path to close it.

## 2. Verdict artifacts — why that shape, and what a numeric finding owes

*Reached when: nothing sends you here — no gate row names this section, deliberately. Every rule a
verdict-writing brief needs is inline in step 3, because every workflow has at least one such stage
(`review` is mandatory in both modes), so a gate for it would fire on every run and this file would
stop being optional. What follows is only the reasoning: why the shape is that shape, and what one
measured run cost when a reviewer skipped it.*

Left unspecified, these come back as multi-page prose, and the stage spends turns composing
something no one reads that way: the gate greps a single line, and the only other consumer is a
later stage that needs the claims and where to check them. Give the reason in the brief rather
than just the format, because a reviewer told only "be brief" will drop findings to comply. The
shape has room for as many rows as there are findings; what it cuts is narration, not substance.
And say explicitly that a finding needing more explanation than a row holds gets its row *plus* a
short paragraph below the table — a format that suppresses a real finding has cost more than the
prose ever did.

**A reviewer challenging a numeric claim must state the quantity it measured and paste the
command.** On a real run, one `spec-review` pass (179,460 tokens) existed solely because a
reviewer measured a different quantity than the spec did — an `abs()`-symmetric, ungated
deviation where the spec meant a one-sided shortfall at the decisive comparison — reported it
as a defect, and withdrew it when asked to show its work. The asymmetry is what makes this
worth a line in the brief: stating the quantity costs the reviewer one sentence, while a
mismeasured finding costs a whole extra stage cycle to resolve. So: a numeric finding names
the quantity, the inputs, and the exact command or script, with the output pasted. A numeric
finding without them isn't a finding yet. **Widen this to any blocking finding that admits a
runnable check, not just numeric ones** — where possible, a blocking row carries a command
whose exit code flips once the finding is addressed. Keep it to "where possible": a
judgment-only finding (missing error handling, an unclear naming choice) has no such command,
and forcing one invites a reviewer to invent a fake one just to comply with the format. The
payoff shows up on a `fixing` retry: `kestra-run`'s scope-capped recheck (see its step 6) can
run that command directly instead of asking the reviewer to re-derive whether the finding was
addressed, which is exactly the "mechanical confirmation costs zero subagent turns" saving
that recheck cap exists to realize.

## 3. A wide refactor: `expand` → migrate-batch × N → `contract`

*Reached when: the spec is a wide refactor or a batched migration.*

**A wide refactor folds as `expand` → migrate-batch × N → `contract`, and needs no new
vocabulary — but a batch whose blast radius reaches call sites *inside test files* has exactly
two legal shapes.** Both obvious escapes weaken the freeze, and both are already mechanically
rejected by `SKILL.md` step 7's validator: giving a post-freeze migrate stage test paths in its
`write_scope` FAILs ("after the freeze, only a reworking pass may touch test paths"), and adding
a second `freeze_after: true` to re-freeze FAILs too ("more than one stage has
`freeze_after: true`"). There is no third shape, so pick one at fold time and **name the choice
in the mode/stage audit line**:
**(a) Pull the test-side migration in front of the freeze — the preferred shape.** The `expand`
stage's `write_scope` includes the test files the migration will touch, and it updates those call
sites to the new form *before* `freeze-tests` runs; the frozen hash then already covers the
migrated form and no batch ever touches a test path. Available whenever the blast radius is known
at fold time — which it normally is, because whatever sized the batches sized them by exactly
that radius.
**(b) Accept `reworking` as the honest path.** When a batch's test-side radius genuinely cannot
be known before the migration runs, don't invent a second freeze: let the batch hit the
write-scope rejection and escalate. `reworking` unlocks the test paths, re-freezes, and resets
the counters — the design's one guaranteed human stop, which is the correct price for a change
that alters what the frozen tests *mean*. Say so in that batch's brief up front, so the stop
reads as a designed outcome rather than a surprise.
Never pair (a) with a partial radius and "fix the rest later": a freeze covering some migrated
call sites and not others is precisely the false-positive shape the freeze exists to close.

## 4. Batches that can't stay green alone

*Reached when: the batches from section 3 land on a shared integration branch rather than each
being independently green on its own.*

**When batches can't stay green alone and land on a shared integration branch, fold the
weakening honestly instead of hiding it inside a green.** Each batch's `exit_criteria.run` is the
**narrowest command that is genuinely green for that batch alone** — the migrated package's own
tests, a type-check, a build of the touched target — never the full suite. **Never a full-suite
invocation weakened to pass:** no skip list, no `-k 'not migrated'`, no `--passWithNoTests`, no
`|| true`, no allow-fail flag. A green produced by narrowing the check is the exact false positive
this whole machine exists to prevent, and it is worse than a red because it leaves evidence
behind. The unmodified full-suite command belongs to **exactly one** stage: a final
`integrate-and-verify` that `depends_on` every batch, which is also the only stage a suite-level
`progress:` metric may be copied onto (a batch structurally cannot move the suite's number).
Each batch's brief states its own weakening in one sentence — *"this gate proves `<X>` only; the
suite is proven at `integrate-and-verify`"* — because without it a reader, or a `review` stage,
reads a batch's green as a suite green, which is the whole defect this rule exists to prevent.
And the `contract` stage (delete the old form) `depends_on: [integrate-and-verify]`, not the last
batch: deleting the compatibility shim before the suite has ever passed removes the only thing
keeping the intermediate states green.

## 5. A repo-declared mandatory pre-merge test gate

*Reached when: the codebase survey found a test gate the repo's own docs declare mandatory before
merge.*

**If the target repo declares its own mandatory pre-merge test gate, generate a stage that
runs it — don't leave it as a suggestion in a brief.** This is the canonical script-eligible
sibling stage (see `SKILL.md` step 2's script-eligibility table). Projects that have been burned by
doubles drifting from reality often already have the fix: a recorded contract suite, a local
fake of the real service, an integration target that must pass before merge, written down in
`CLAUDE.md` or the repo's own docs. Whether it exists is a fact to look up during the codebase
survey, not something to assume either way. When it does exist, the difference between a
mention in a `brief` and a stage with `exit_criteria` is the difference between a convention an
agent may recall and one it cannot skip — and a gate the project already declared mandatory is
exactly the kind that shouldn't depend on recall. Give it `write_scope: []`, an
`exit_criteria.run` that invokes whatever command the repo documents, and
`on_fail.action: fixing` with `target` pointing at the implement stage. Place it as a sibling
of `verify`/`review` — all three read the same finished diff and none of them writes code, so
chaining them only costs wall-clock. Name the gate as the repo documents it rather than
inventing a name, and if the documented command doesn't run standalone, say so instead of
generating a stage that can never pass. **Give this stage no work-describing brief** — or a
one-line brief stating only "kestra-run runs `exit_criteria.run` directly; spawn nothing" —
rather than judgment-sounding prose. `write_scope: []` means a subagent can change nothing here,
the exit code is identical no matter who runs it, kestra-run re-runs it unconditionally in step
3 regardless, and on failure the command's own output already feeds the fixing attempt's
context pack. A brief that reads like there's something to reason about triggers a spawn under
kestra-run's own "do the stage's work if the brief describes any" rule for zero benefit — this
is the canonical case that rule's efficiency note (see `kestra-run`'s
`references/efficiency-notes.md`) exists to let the orchestrator skip.
