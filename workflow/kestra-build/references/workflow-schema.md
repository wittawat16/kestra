# `workflow.yaml` schema

One file per feature. Read `design-principles.md` before filling in `on_fail` / `freeze_after` —
the fields only make sense in light of *why* they exist.

**What's in here**, so one field doesn't cost you 700 lines:

- **Paths** — the one repo-root frame `write_scope`, `exit_criteria` and every `brief` share
- **Top-level** — `feature`, `source_spec`, `mode`, and `spec_anchor` + `tickets` (the anchor triple
  and the ticket map, for a sliced fold only)
- **Per-stage fields** — `model` · `effort` · `brief` · `exit_criteria` · the verdict artifact ·
  `on_fail` · `branches`
- **Worked example** — csv-export, complete and copyable; the longest section by far
- **The `design` stage** — not in the worked example, since csv-export has no UI

## Paths — repo-root-relative, all of them

`write_scope` is matched against `git diff --name-only HEAD`, and git prints every path from the
repo root whatever directory it runs in. The frame is git's, not one this schema picked, so the
only spelling that can ever match is the repo-root-relative one:
`workflows/runs/csv-export/spec-verdict.md`, not `spec-verdict.md`. (`<run-folder>` below expands
the same way — `workflows/runs/csv-export`.) The run's own `validate_workflow.py` FAILs a
`write_scope` entry starting `./`, `../`, or `/`.

**The orchestrator runs `exit_criteria.run` from the repo root**, so one frame covers the whole
stage: every path inside `run`, `exit_criteria.artifact`, `branches.artifact_exists`, and every
file a `brief` tells the stage to write or read. Spell all of them out from the repo root and a
stage's scope, its gate, and its instructions name the same file — which is what makes the gate a
gate.

**The run folder lives inside the target repo** — that is what puts its artifacts into
`git diff --name-only HEAD` at all (`SKILL.md`'s **Output location**). A run folder outside the
repo never appears there, so `write_scope` cannot bound an artifact-writing stage and that stage
runs unenforced.

## Top-level

```yaml
feature: <feature-id>              # kebab-case, matches the spec's feature id
source_spec: <path>                # spec this workflow was derived from
spec_anchor: { ... }               # optional mapping — which commit of that spec, see below
mode: lite | full                  # which stage shape was derived — see SKILL.md's lite/full table
tickets: [ ... ]                   # optional list — the sliced ticket set folded in, see below
stages: [ ... ]                    # ordered list, see below — order is for readability only,
                                    # actual execution order comes from depends_on
```

`mode` is a **record of a decision, not a switch.** Nothing in the orchestrator reads it to change
behavior — every stage in the file is executed and enforced identically either way. It exists so
that whoever opens this file six weeks from now can see that the missing `test-review` was a
derivation choice made against a spec with no test doubles, rather than an omission. Changing the
value by hand does nothing; the stage list is the truth. If a lite workflow needs to become full —
a second component appears, a dependency gets mocked — regenerate from the spec rather than
hand-editing stages in, so the freeze and the write_scope non-overlap get re-validated by step 7.

### `spec_anchor` and `tickets` — the anchor triple and the ticket map

Both are optional and both are written by the fold, never by hand. `spec_anchor` says *which commit
of the spec* this workflow was derived from; `tickets` says *which slices* were folded into it. A
monolithic workflow (no ticket set) carries `tickets` not at all, and carries `spec_anchor` only when
its spec is chain-marked with a `> Spec-ticket:` preamble line.

`spec_anchor` sits immediately after `source_spec` and before `mode` — literally beside the spec
reference, so a reader sees which spec and which commit of it in one eyeful.

```yaml
feature: order-cancellation-refund
source_spec: workflow/runs/order-cancellation-refund/0-spec.md
spec_anchor:
  raise_commit: 4f1c0b9e2d7a5c3b8e6f0a1d2c3b4a5968778899
  surface_hash: e1c70ae8e3f6810cd8d85503f91b31e851aa9eb79af1f7da1c3c93dc159acc27
  extractor_version: 1
mode: full

tickets:
  - id: issue-47
    ref: https://github.com/<owner>/<repo>/issues/47
    body_sha256: 9f2c1a…<64 hex>
    ac_hash: 7ab13f…<64 hex>
    verified_against: 4f1c0b9e2d7a5c3b8e6f0a1d2c3b4a5968778899
    verified_at: 2026-08-02T09:14:03Z
```

| Field | Grammar | Where the value comes from |
|---|---|---|
| `spec_anchor.raise_commit` | `^[0-9a-f]{40}$` — full SHA, never abbreviated | `kestra-spec`'s `references/chain-provenance.md` §2 exactly-one-match predicate |
| `spec_anchor.surface_hash` | `^[0-9a-f]{64}$` | `extract_surface(<spec at raise_commit>).surface_hash` |
| `spec_anchor.extractor_version` | `^[1-9][0-9]*$` | `requirement_surface.EXTRACTOR_VERSION` of the run's own copy |
| `tickets[].id` | the same string as `tickets/<id>.md` and the brief delimiter's id | the tracker's own identifier, normalized (`ticket-fold.md` §1) |
| `tickets[].ref` | URL, or a repo-relative ticket path; not graded by the validator | the invocation |
| `tickets[].body_sha256` | `^[0-9a-f]{64}$` over the materialized `tickets/<id>.md` | the fold |
| `tickets[].ac_hash` | `^[0-9a-f]{64}$` | `ticket-fold.md` §3 F3 — one definition, stated there only |
| `tickets[].verified_against` | `^[0-9a-f]{40}$`, and must equal `spec_anchor.raise_commit` | the per-ticket last-checked marker |
| `tickets[].verified_at` | ISO-8601 UTC, `YYYY-MM-DDTHH:MM:SSZ` | the fold clock |

**Full SHAs, never abbreviated:** abbreviations collide, and every use of `raise_commit` /
`verified_against` is a byte-wise equality compare, not a lookup. An abbreviation would make a real
mismatch unprovable in exactly the case that matters.

**`verified_against` duplicating `raise_commit` is deliberate, not redundant.** It is the per-ticket
last-checked marker, it is the tuple the tracker-side `Verified-against:` line mirrors, and a
divergence between the two is a real checkable defect — a partial re-fold, or a hand edit — rather
than dead weight. A single shared value could not express "this ticket was checked against a
different raise than that one."

**Why the ticket map lives here and not in `state.json`:** `workflow.yaml` is the derived definition
and is immutable for the run's life; `state.json` is mutable run state the orchestrator rewrites at
every commit. Provenance the orchestrator must never rewrite belongs in the immutable file. See
`state-schema.md`, which records the same decision from the other side so nobody adds a second copy.

**Validator posture — monolithic absence is a WARN; sliced absence and partial are FAILs.** A
monolithic workflow from a standalone or hand-written spec may omit `spec_anchor` (story 24). A
sliced fold may not: its ticket map must bind to the vetted raise. Any present anchor with a missing,
empty, or malformed key is a FAIL because partial provenance proves nothing. The same split applies to a `tickets[]` entry missing any of its
five hash/marker fields, and to a `ticket:begin` delimiter with no matching `ticket:end`. This is the
precedent `validate_spec.py` and `chain-provenance.md` already cite as "validate_workflow.py's
partial anchor triple."

## Per-stage fields

| Field | Required | Values | Notes |
|---|---|---|---|
| `id` | yes | unique string | referenced by other stages' `depends_on` and `branches.goto` |
| `depends_on` | yes | list of stage ids | `[]` for the first stage(s); a stage only starts once every dependency is `passed` |
| `brief` | no | free text | plain-language instructions for whatever Claude gets spawned to do this stage's work. **Never a skill name or ID** — see note below |
| `write_scope` | yes | list of repo-root-relative glob patterns | paths this stage's diff may touch. `[]` means the stage produces no code diff (e.g. approval gates). Enforced at apply time by the orchestrator against `git diff --name-only HEAD` — not a promise the AI makes itself |
| `exit_criteria` | yes | object, see below | how the orchestrator decides `verifying` → `passed` vs `fixing` |
| `freeze_after` | no, default `false` | bool | set `true` **only** on the dedicated freeze stage, whose successful completion snapshots the test-hash into `state.json` and commits the freeze point. Exactly one stage per file has this set, and its `write_scope` must be non-empty — the hash is computed from that scope, so an empty one snapshots nothing and the invariant silently doesn't exist. Not the stage that *writes* the tests: that one stays unfrozen so its output can still be reviewed and fixed cheaply (see `design-principles.md`) |
| `on_fail` | yes | object, see below | what happens when `exit_criteria` fails |
| `branches` | no | list, see below | declarative conditional branching — optional, use sparingly |
| `model` | no | `"default"` \| a faster/cheaper model tier's id | which model kestra-run should spawn this stage's subagent with. Omit (or `"default"`) to inherit whatever model is running the orchestrator itself — that's correct for almost every stage. See `SKILL.md`'s model-routing guidance before setting anything else; this field exists for one narrow case (`implement-*`), not as a general cost knob |
| `effort` | no | `"default"` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` | reasoning-effort override for this stage's subagent, independent of `model` — same model, less/more thinking budget. Omit (or `"default"`) to inherit the orchestrator's own effort level. See the `effort` section below; auto-set only on `implement-*` under `mode: lite`, and only that one case |

### `model`

Model choice is a real trade — a faster/cheaper model finishes an `implement-*` stage in less
wall-clock and fewer tokens, but it also degrades judgment, and this workflow file has no way to
tell *how much* for the specific model you'd route to. Measured directly: the same spec-writing
task, run once on the orchestrator's own model and once on a smaller/faster one, produced a spec
that silently invented an unstated constant and marked **Open Items: none** — the exact failure
mode `kestra-spec`'s step 6 self-check exists to prevent — and picked a design the stronger model's
own spec had explicitly written down and rejected one paragraph earlier. That happened on a
spec-writing task, which is exactly the shape of `spec-review`, `test-review`, `review`, and
`generate-tests`: read something ambiguous, decide what it means, don't paper over the gap.

So the rule is narrow and stage-shaped, not a global toggle:

- **`implement-*` may set `model` to a faster tier.** Its output is never trusted on its own say-so
  — `verify` re-runs the frozen tests against it and `review` reads the diff independently, both
  still on the default model, and a wrong implementation just fails and loops through `fixing`
  rather than silently passing. The stage most exposed to a weaker model is also the one with the
  most mechanical re-checking already sitting downstream of it.
- **Every judgment stage stays on `"default"` — no exceptions.** `spec-review`, `test-review`,
  `review`, and `generate-tests` (translating an acceptance criterion into an assertion is exactly
  the kind of ambiguity-resolution that degraded above) keep the orchestrator's own model. Nothing
  downstream double-checks *whether* these stages reasoned correctly the way `verify`/`review`
  double-check `implement-*` — their output is the check.
- **Don't set it defensively "to be safe."** Only give `implement-*` a `model` override when the
  user has asked for faster/cheaper runs; the default (omit the field) already inherits the
  orchestrator's model, which is the safe choice for every stage including `implement-*`.

### `effort`

A separate axis from `model` — same model family, less or more reasoning budget per turn. Unlike
`model`, this one **does** get set automatically, in exactly one case, because the signal for when
it's safe is already computed for another reason: `mode: lite`.

- **`implement-*` under `mode: lite` defaults to `effort: low`.** `mode: lite`'s own precondition
  table (single component, no test doubles, no non-trivial Runtime Invariants) is already evidence
  the implementation itself doesn't need heavy reasoning — that's what earned it `lite` in the first
  place. And the same safety net that justifies `model` overrides on `implement-*` applies here
  unchanged: `verify` and `review` independently re-check the result at the orchestrator's own
  effort level, so a low-effort implementation that gets something wrong just fails and loops
  through `fixing` rather than silently passing.
- **`implement-*` under `mode: full` keeps `effort` unset (`"default"`).** `mode: full`'s own
  trigger conditions (test doubles, non-trivial invariants, 2+ components) describe *other* stages'
  complexity, not `implement-*`'s own — a full-mode workflow can still have a
  trivially simple `implement-*` (single file, e.g. because the complexity lived entirely in an
  external dependency `test-review` exists to check). `mode: full` is not evidence either way about
  `implement-*` specifically, so don't extend the lite-only default to it.
- **Every judgment stage keeps `effort` unset, same reasoning as `model`, no exceptions.**
  `spec-review`, `test-review`, `review`, and `generate-tests` never get an automatic `effort`
  override under any mode — nothing downstream re-checks *how well* these stages reasoned, so
  there's no safety net to catch a shallow pass the way there is for `implement-*`.
- **`model` is never touched by this rule.** Whatever `model` a stage already has (explicit or
  inherited) stays exactly as-is; `effort` is set independently and does not imply or require a
  `model` override, and a `model` override does not imply an `effort` override either — they're
  two separate knobs on the same stage, each with their own narrow rule above.

### `brief`

```yaml
brief: >
  Implement the CSV export endpoint per the frozen spec/tests. An implementation-focused skill,
  if you have one installed, fits this stage well.
```

Skills in Claude Code aren't invoked by ID from the outside — a skill is a description that shows
up in whatever Claude gets spawned to do the work, and *that Claude* decides whether to use it,
the same way skill-triggering works in any normal session. So `brief` is never a `skill:` field
pointing at a specific skill name as a hard dependency — if you write `skill: some-skill` and it
isn't installed wherever this workflow eventually executes, the stage has nothing to fall back to.

kestra-build still gets to use what it knows *right now*: at generation time, kestra-build is itself
running inside a Claude session and can see its own `available_skills`. If something genuinely
relevant is installed (a planning-focused skill for a plan stage, an implementation/verification
skill for an implement/verify stage, a code-review/security-review skill for a review stage), name
it **inside the brief text as a suggestion** — worth trying if it's there, harmless to ignore if it
isn't. The stage's enforcement (`write_scope`, `exit_criteria`, `on_fail`) stays entirely
skill-agnostic; `brief` is the only place that ever mentions a skill by name, and only as a hint.

#### Embedded ticket blocks (sliced folds only)

On a sliced fold, the stage that owns a slice carries **the whole ticket file, verbatim, between
machine-readable delimiters, as a literal block scalar**:

```yaml
    brief: |
      <!-- ticket:begin issue-47 sha256:9f2c1a…<64 hex> -->
      ## What to build
      …the byte content of tickets/issue-47.md, unaltered…
      ## Acceptance criteria
      - [ ] Refund is issued in full within the same request
      <!-- ticket:end issue-47 -->

      Folded in at build time from tickets/issue-47.md. Do not edit this block — see
      workflow-schema.md "re-fold, never hand-edit". Source for each AC above: the spec's AC
      Coverage Map (AC-3 → US-3, AC-4 → ID§refunds).

      <the stage's own instructions go here, BELOW the block>
```

Every rule here is mechanically checkable, which is the reason each one is shaped the way it is:

- **The whole file, not selected sections.** One rule, one hash, no extraction ambiguity to argue
  about later. `## Blocked by` riding along is harmless, and informative next to `depends_on`.
- **`|` literal, never `>` folded.** Both parse, but `|` keeps the checkbox lines readable for the
  human reading the diff — a folded body silently reflows the acceptance criteria into a paragraph.
- **The delimiter carries the id and the full 64-hex `sha256` of `tickets/<id>.md`**, not a 12-char
  short form: the check is an exact-match compare, and 64 characters once per stage is nothing next to
  a body that is re-pasted on every spawn.
- **The only permitted transform is the block-scalar indentation.** No re-wrapping, no whitespace
  normalization, no `#`-escaping, no trimming. Byte provenance dies the moment a transform is
  negotiable, and the `sha256` is what would stop meaning anything.
- **The stage's own instructions live strictly below `ticket:end`**, never interleaved, so the block
  stays one contiguous extractable region.
- **One ticket per stage, one stage-set per ticket.** Two stages may embed the *same* ticket (an
  `implement-*` / `verify-*` pair over one slice); a stage never embeds two tickets, because a brief
  with two blocks has no unambiguous owner for `on_fail.target` routing.
- **The `Source:` line under the block is derived, not authored** — the `AC → Source` pairs are read
  out of the spec's AC Coverage Map at fold time (see `ticket-fold.md` §2), so a reader can trace a
  requirement to its intent-layer origin without opening the spec.

##### Two parser traps that decide how this is verified

1. **`parse_yaml`'s pre-pass runs `_strip_comment` and drops `---` / blank lines over *every* raw
   line, block-scalar bodies included.** `_strip_comment` cuts at a `#` preceded by a space, and a
   block-scalar body is indented by definition, so **every `## …` heading in an embedded ticket loses
   itself in the parsed value** — this is a standing property of sliced briefs, not a rare case
   involving a `#47` reference (measured: 3 of 3 briefs in
   `../../evals/2026-08-02-wave4a-build-fold/logs/02-parsed-brief-loss.log`). A `---` horizontal rule
   goes the same way. The file on disk is intact throughout. Consequence: **the raw `workflow.yaml`
   text is the truth for an embedded block; the parsed brief is a lossy view.** Every check compares
   raw text, and `validate_workflow.py` emits one `WARN` per affected stage, so on a normal sliced
   fold expect one per embedded block — a standing note that the parsed view is lossy, not an alarm
   about that particular ticket. Blank-line collapse is accepted and harmless for prose.
2. **Do not "fix" trap 1 by escaping the ticket body.** Escaping breaks byte-identity, which is the
   only thing the `sha256` is protecting — trading a documented, warned-about parse loss for an
   undetectable content change.

#### re-fold, never hand-edit

An embedded block, its delimiter hash, and the matching `tickets[]` entry are **derived** — the
`tickets/<id>.md` file is the truth. A ticket that changes is re-folded (a plain re-run of
kestra-build over the same run folder); there is no hand-edit path, and `validate_workflow.py` FAILs
on every **inconsistent** hand edit rather than trusting the instruction — an edit made consistently
across all three copies is caught at the next fold's F0 re-materialization, not by the validator. The reason is the same one
`mode` gives above, one step stronger: a re-fold is what re-runs the freeze / `write_scope`
non-overlap validation, the anchor recompute, and the `ac_hash` refresh, so a hand-patched brief
holds current words behind a stale anchor and an un-revalidated freeze. Full detection matrix, the
four hand-edit routes it closes, and the mid-run refusal: `ticket-fold.md` §4.

### `exit_criteria`

```yaml
exit_criteria:
  type: command             # command | artifact_exists | human_approval
  run: "npm test"           # required when type: command — the orchestrator's verifying step
  artifact: "<run-folder>/design.md"  # required when type: artifact_exists
  progress: "<one spec bullet, verbatim>"   # optional — see below; absent is the normal case
```

- `command` — orchestrator runs `run` **from the repo root**, exit code 0 = pass. When `run` executes a real test suite
  (a `verify` stage, or any stage whose exit_criteria re-runs the frozen tests), prefer the test
  runner's own parallel-execution flag over a plain serial invocation — e.g. `pytest -n auto`
  (pytest-xdist), `jest --maxWorkers=<n>`, `go test -parallel <n>`, `vitest --pool=threads`. This
  still satisfies "one command, one real exit code" (the invariant this field exists to protect) —
  it's not a way to fan the test run out across multiple subagents, which would turn one exit code
  into several that the orchestrator would have to reconcile itself, reopening exactly the
  ambiguity this field is designed to close. Only use this when the target repo's test runner
  actually supports a parallel mode and the corresponding plugin/flag is available — verify that
  before writing it into `run`, the same "check it actually works standalone" discipline as any
  other `exit_criteria.run` command.
- `artifact_exists` — orchestrator checks the path exists (e.g. a design doc, a generated file).
- `human_approval` — orchestrator stops in `waiting_approval` and waits; a human's explicit
  approval is the only thing that flips it to `passed`. **Opt-in only** — see
  `design-principles.md`'s "Default HITL posture." The generator's default template never emits
  this type; only add it when the user explicitly asks for a manual milestone. Judgment-requiring
  stages (spec sanity, review, security) default to `command` against a verdict artifact instead
  (see the worked example below) — the fix loop and `fixing → reworking` remain the one place a
  human is always in the loop.

#### `exit_criteria.progress`

The number a `fixing` loop has to move. Division of labor: **the spec declares it, kestra-build copies
it, kestra-run compares it** across attempt rounds — that is what makes clause 2 of the spec's
two-clause stop condition ("two consecutive attempt rounds without the number moving") mechanical
instead of a feeling.

```yaml
    exit_criteria:
      type: command
      run: "npm test -- csv-export"
      progress: "number of failing assertions reported by `npm test` — must reach 0, from a baseline of 2 passing / 0 failing"
```

**The copy rule is exact and mechanical:**

- Source: the spec's `## Exit Criteria` section, every bullet matching
  `^\s*[-*]\s+progress:\s*(.+)$`. The captured group is the value.
- **Verbatim** — including the trailing period and the backticks. The only permitted transform is
  joining a wrapped continuation line with a single space, the same join `requirement_surface._units`
  does. No rewording, no shortening, no re-quoting: kestra-run compares a *number* across rounds, and
  a reworded metric is a different metric.
- The section's head line (the two-clause stop condition) is **not** copied anywhere. It is a
  spec-level fact about the whole run; duplicating it per stage would create N copies to drift.
- The closing "single-shot pass/fail, no progress number" bullet generates nothing. A stage without
  `progress:` is the normal case.

**Owner resolution — deterministic first, then ask; never guess:**

1. **Exact match** — the bullet's backticked command, whitespace-collapsed, equals some stage's
   `exit_criteria.run`, whitespace-collapsed ⇒ that stage.
2. **Unique containment** — exactly one stage's `exit_criteria.run` contains that command as a
   substring ⇒ that stage.
3. **Named stage** — the bullet text contains a stage id verbatim ⇒ that stage.
4. **0 or >1 candidates after 1–3 ⇒ ask the user once**, quoting the bullet and listing the candidate
   stage ids. Never attach it to the nearest-looking stage: a metric on the wrong stage is compared
   forever against a number that stage cannot move.
5. **Still unassignable ⇒ stop the fold:**
   ```
   FAIL: the spec declares a loop-shaped check ("progress: …") that no stage owns — kestra-run would
   have nothing to compare across attempts, so clause 2 of the stop condition could never fire.
   ```
   A declared metric silently dropped is exactly the "logs it, then continues" shape this design
   rejects everywhere else.

**Two fold-time consistency checks, both cheap:**

- Owner resolved but `on_fail.action != fixing` ⇒ WARN in the audit line: *"the metric on `<stage>`
  will never be compared — this stage does not retry."*
- Every `progress:` bullet lands on exactly one stage. A bullet assigned twice is a fold-time stop —
  two stages comparing the same number is two answers to one question.
- Expand–contract: a **suite-level** metric belongs on the final `integrate-and-verify` stage, never
  on an individual migrate batch, because a batch structurally cannot move the suite's number.

**Validator:** `progress` present but empty ⇒
`FAIL: stage '<id>' exit_criteria.progress is empty — omit the field or give it the spec's own
progress fragment` — same family as the existing "type is `command` but `run` is empty". Nothing
more: comparing the metric is kestra-run's job, and the validator must not pre-empt its semantics.

### The verdict artifact

Every stage whose gate greps a verdict writes the same shape, and the brief has to say so — left
unspecified these come back as multi-page prose that costs turns to compose and that nothing reads
in that form:

```markdown
VERDICT: CHANGES_REQUESTED

| Severity | Finding | Where |
|---|---|---|
| blocking | Guard for the "empty batch" invariant is missing entirely | src/alloc.ts:88 |
| minor | Error message names the old field | src/alloc.ts:141 |

Evidence: evidence/sweep-200k.md (command recorded in the file)
```

First line exactly `VERDICT: CLEAR` or `VERDICT: CHANGES_REQUESTED` — that's what `exit_criteria`
greps. The table takes as many rows as there are findings; a finding that genuinely needs more than
a row gets its row plus a short paragraph under the table. The point is to cut narration, never to
cap how much gets reported. A numeric finding also names the quantity it measured and pastes the
command that produced it — see the note in `SKILL.md`'s `review` guidance.

### `on_fail`

```yaml
on_fail:
  action: fixing            # fixing | reworking | blocked
  max_attempts: 3            # required when action: fixing
  escalate_at: 2              # required when action: fixing — a repeated diff (no progress) gets
                               # a grace window of retries below this attempt count; once attempt
                               # >= escalate_at, a repeat stops straight to reworking instead of
                               # retrying again, even if max_attempts hasn't been reached yet.
                               # NOTE: a diff can only repeat starting at attempt 2 (attempt 1 has
                               # nothing prior to compare against), so at the conventional value of
                               # 2 there is no actual grace window — a repeat escalates immediately.
                               # Set 3+ if you want a real grace window; 2 is "no tolerance."
  target: implement-x        # required when action: fixing AND this stage owns no code — a
                               # review/verify stage, whose write_scope holds only the verdict
                               # artifact it writes (or nothing at all). Names the upstream stage
                               # whose write_scope the fix attempt may touch. Omit when the stage
                               # owns the code its own fix would edit.
  reason: "short phrase"     # required when action: reworking or blocked — shown to the human
```

- `fixing` — orchestrator lets the stage retry, touching only `write_scope`, up to `max_attempts`.
  Every `fixing` stage must set both `max_attempts` and `escalate_at`; never leave it unbounded.
  A stage that owns no code (review, verify) can still use `action: fixing` — set `target` to the
  upstream implementation stage id. **`target`, not an empty `write_scope`, is what marks such a
  stage**: writing a verdict *is* a diff, so a stage whose brief orders one lists that path in its
  own `write_scope`, and `[]` is reserved for a stage that writes literally nothing. Get that wrong
  and the orchestrator reverts the verdict as a scope violation before `exit_criteria` greps it —
  the stage then cannot pass at all, on any attempt. The orchestrator: checks the fix attempt's
  diff against `target`'s `write_scope` **plus this stage's own** (the fix writes code, then this
  stage re-runs and rewrites its verdict), tells the fix subagent what
  this stage's failure output said (e.g. the `CHANGES_REQUESTED` findings), and re-runs *this*
  stage's own work + `exit_criteria` again afterward. `attempt`/`seen_diffs` are still tracked
  against this stage's own entry in `state.json`, same as any other `fixing` stage.
  **Keep `implement-*`'s `max_attempts`/`escalate_at` the same as every other stage (`3`/`2`), not
  higher.** Earlier guidance here gave `implement-*` a longer leash (`5`/`3`) on the assumption that
  more retries against frozen tests is strictly safer. Sourced research says otherwise for exactly
  this shape of loop — refining code against a test suite it can see repeatedly measurably
  *increases* test-overfitting the more rounds it runs, not just increases cost (see
  `workflow/research/tdd-in-ai-sdlc.md`). A longer leash on this specific stage trades a worse
  failure mode (code that games the frozen tests rather than satisfying them) for a lower `reworking`
  rate, which is the wrong trade.
- `reworking` — bounce **up** to spec-review or test-regeneration, unlock test paths, re-freeze,
  reset attempt counters. This is the *only* legal way test paths become writable again after
  `freeze_after` has fired, and the one place the design always stops for a human — see
  `design-principles.md`'s "Default HITL posture."
- `blocked` — terminal, needs a human. Rare in the default template now that `waiting_approval` is
  no longer a default stage; still available for a `human_approval` stage a user explicitly asked
  for, when the answer is "no."

### `branches` (optional — keep declarative)

```yaml
branches:
  - when: { exit_code: 0 }
    goto: implement-happy-path
  - when: { artifact_exists: "<run-folder>/design.md" }
    goto: generate-tests-with-ui-cases
```

Conditions may reference only an exit code or an artifact's existence — nothing more expressive.
If a real decision tree is needed beyond that, say so to the user rather than encoding it here.

---

## Worked example

Feature: *"add an endpoint that exports a user's data as CSV"* (same example kestra-build's README uses).

```yaml
feature: csv-export
source_spec: workflows/runs/csv-export/0-spec.md

stages:
  - id: spec-review
    depends_on: []
    brief: >
      Review workflows/runs/csv-export/0-spec.md for the defects that are cheap to fix now and
      expensive to fix after tests are frozen. Check that: every acceptance criterion is testable
      without a follow-up question; each Runtime Invariant names what actually happens on violation
      and none of them amount to "log it and continue"; the Reality Constraints subsections are
      either filled in or explicitly marked not-applicable with a reason, in particular what each
      external dependency does NOT guarantee; and none of these contradict each other or the
      acceptance criteria. Anything derived rather than stated by the spec is flagged as inferred in
      the brief above — review the inference itself, don't assume a human already approved it. Any
      numeric finding must name the exact quantity measured, the inputs, and the command/script used
      — paste its output; a numeric claim without them isn't a finding yet. Write the verdict to
      workflows/runs/csv-export/spec-verdict.md, first line exactly "VERDICT: CLEAR" or
      "VERDICT: CHANGES_REQUESTED", followed by findings.
    write_scope: ["workflows/runs/csv-export/0-spec.md", "workflows/runs/csv-export/spec-verdict.md"]
    exit_criteria:
      type: command
      # validate_spec.py is emitted into this run folder at generation time (see SKILL.md's
      # spec-review bullet) — it FAILs only on format-independent, spec-fixable facts (an
      # edit/exists row whose path is absent); everything else WARNs without failing. Its second
      # argument is the repo root the spec's Files-to-Touch paths resolve against; the command
      # runs from there, so `.` is it.
      run: "python3 workflows/runs/csv-export/validate_spec.py workflows/runs/csv-export/0-spec.md . && grep -q '^VERDICT: CLEAR$' workflows/runs/csv-export/spec-verdict.md"
    on_fail:
      action: fixing
      max_attempts: 2
      escalate_at: 2
      reason: >
        bounded attempt to fix the spec in place (see design-principles.md's "Default HITL
        posture") — falls through to reworking if unresolved after 2 attempts or the same diff
        repeats without progress

  - id: generate-tests
    depends_on: [spec-review]
    brief: >
      Write tests covering every acceptance criterion in the spec. No implementation exists yet —
      these tests must fail for the right reason (missing feature), not error out. Pin anything the
      spec's Reality Constraints marks as pinned rather than reading it live.
    write_scope: ["test/**"]
    exit_criteria:
      type: command
      run: "npm test -- --listTests csv-export && npx eslint test/csv-export --rule 'no-undef: error'"
    on_fail:
      action: fixing
      max_attempts: 3
      escalate_at: 2

  # Only generated when the spec's Reality Constraints list external dependencies or a pair of
  # paths that must agree — i.e. when the tests will contain doubles that can drift from reality.
  # A feature that fakes nothing can't have the defects this stage looks for; omit it there.
  # Note it comes BEFORE the freeze: findings here are a bounded fixing loop against
  # generate-tests, whereas the same finding after the freeze would cost a reworking bounce.
  - id: test-review
    depends_on: [generate-tests]
    brief: >
      Read the tests just written against the spec's Reality Constraints and report a table with one
      row per risk (ordering/preconditions, response realism, type/shape drift, path parity, own
      shared logic, non-determinism), each marked applicable or n/a with file:line evidence. Add
      rows this codebase's own conventions imply and say which you added. Judgment only — the
      mechanical checks already ran in generate-tests' exit_criteria; don't re-derive them. Write
      the verdict to workflows/runs/csv-export/test-verdict.md, first line exactly "VERDICT: CLEAR" or
      "VERDICT: CHANGES_REQUESTED", followed by findings. On a re-review after a fixing attempt
      (the context pack will include the fix diff and your own prior findings), verify the findings
      are addressed and review the changed lines and their interactions with the rest of the suite;
      do not re-derive relations between unchanged files already cleared, which write_scope
      enforcement guarantees are unchanged.
    write_scope: ["workflows/runs/csv-export/test-verdict.md"]   # the verdict it writes, nothing else
    exit_criteria:
      type: command
      run: "grep -q '^VERDICT: CLEAR$' workflows/runs/csv-export/test-verdict.md"
    on_fail:
      action: fixing
      max_attempts: 3
      escalate_at: 2
      target: generate-tests

  # The freeze is its own act, deliberately separate from writing the tests. It writes nothing —
  # it owns the test paths solely so the test-hash has something to snapshot, and re-runs the
  # tests' own checks against the exact commit being locked. on_fail is reworking, not fixing:
  # a failure here means something is wrong upstream, and patching it at the freeze point would
  # bypass the review that just approved these tests.
  - id: freeze-tests
    depends_on: [test-review]
    brief: >
      No edits. This stage exists to snapshot and commit the approved test suite as the frozen
      baseline every later stage is held to.
    write_scope: ["test/**"]
    freeze_after: true
    exit_criteria:
      type: command
      run: "npm test -- --listTests csv-export && npx eslint test/csv-export --rule 'no-undef: error'"
    on_fail:
      action: reworking
      reason: "tests no longer pass their own checks at the freeze point — resolve upstream, don't patch here"

  - id: implement-csv-export
    depends_on: [freeze-tests]
    brief: >
      Implement the CSV export endpoint against the frozen tests — do not modify test/**. Also
      install the checks listed under the spec's Runtime Invariants: each one detects its condition
      and halts, refuses, or alerts rather than proceeding. The frozen tests will pass whether or
      not those guards exist — they were derived from anticipated cases, and the guards exist for
      unanticipated ones — so their presence is on you here, not on the test run. An
      implementation-focused skill fits this stage well if you have one installed.
    write_scope: ["src/routes/**", "src/services/csv-export/**"]
    # model: <faster-tier-id>   # only when the user asked for faster/cheaper runs — see the
                                 # `model` section above. Omitted here; the default already inherits
                                 # the orchestrator's model, which is correct unless asked otherwise.
    exit_criteria:
      type: command
      run: "npm test -- csv-export"
    on_fail:
      action: fixing
      max_attempts: 3
      escalate_at: 2

  - id: verify-acceptance-criteria
    depends_on: [implement-csv-export]
    brief: >
      Before doing anything else, check the frozen test suite (now real, unlike at generation time)
      against the spec's AC Coverage Map: does every AC map to an assertion that actually exists and
      actually runs under exit_criteria.run? If yes for all of them, there is no judgment work here
      — say so plainly and stop; running exit_criteria.run's real exit code IS the verification,
      kestra-run can execute it directly without spawning you next time. If one or more ACs are NOT
      covered by any frozen assertion, name exactly which ones and exercise only those at runtime by
      hand, reporting what you observed against what the AC requires.
    write_scope: []
    exit_criteria:
      type: command
      run: "npm run test:e2e -- csv-export"
    on_fail:
      action: fixing
      max_attempts: 3
      escalate_at: 2
      target: implement-csv-export

  # Sibling of verify-acceptance-criteria, not its successor — both depend on implement-csv-export
  # directly so kestra-run can run them concurrently (neither writes code — verify writes nothing at
  # all, review writes only its own verdict — so there's nothing for them to collide on, and
  # review's diff is already final the moment
  # implement-csv-export passes — it doesn't need verify to finish first).
  - id: review
    depends_on: [implement-csv-export]
    brief: >
      Review the real diff since the last stage commit for correctness, edge cases, and
      injection/authn/secrets risk. Passing tests only prove the spec's own acceptance criteria —
      this stage exists to catch what the spec never thought to test for. Whatever code-review and
      security-review skills you have available both fit this stage well; try them, proceed with a
      direct review if none are available. Write the verdict to
      workflows/runs/csv-export/review-verdict.md as the first line, exactly: "VERDICT: CLEAR" or
      "VERDICT: CHANGES_REQUESTED", followed by findings.
    write_scope: ["workflows/runs/csv-export/review-verdict.md"]   # the verdict it writes, not the code it judges
    exit_criteria:
      type: command
      run: "grep -q '^VERDICT: CLEAR$' workflows/runs/csv-export/review-verdict.md"
    on_fail:
      action: fixing
      max_attempts: 3
      escalate_at: 2
      target: implement-csv-export

  # Conditional on the spec's needs_devops flag alone (never on scanning the spec text for
  # deploy-related keywords — see full-mode-stages.md's deploy-readiness section). DEFAULT shape:
  # fold this into `review` above instead of a standalone stage — review already writes
  # workflows/runs/csv-export/review-verdict.md, so it additionally writes
  # workflows/runs/csv-export/deploy-checklist.md and its exit_criteria becomes
  # `grep -q '^VERDICT: CLEAR$' workflows/runs/csv-export/review-verdict.md && test -f workflows/runs/csv-export/deploy-checklist.md`,
  # with freshness mechanically enforced (see full-mode-stages.md for both enforcement points). This standalone
  # block is the FALLBACK shape — use it only when that freshness enforcement can't be wired into
  # the target project/CI, or the user explicitly wants a distinct deploy milestone. When using the
  # fallback: depends on BOTH siblings, not just review — it needs the full diff to be
  # finished-and-passed, and verify-acceptance-criteria passing is part of that even though it ran
  # in parallel. Omit entirely when needs_devops is false.
  - id: deploy-readiness
    depends_on: [review, verify-acceptance-criteria]
    brief: >
      Produce a pre-deploy checklist for this diff: env vars, DB migration order + rollback,
      feature flags, infra changes, deploy order, rollback trigger, monitoring. Whatever
      devops-focused skill you have fits this stage well; try it, proceed with a direct checklist
      if not available.
    write_scope: ["workflows/runs/csv-export/deploy-checklist.md"]   # the checklist it produces
    exit_criteria:
      type: artifact_exists
      artifact: "workflows/runs/csv-export/deploy-checklist.md"
    on_fail:
      action: fixing
      max_attempts: 2
      escalate_at: 2

  - id: done
    depends_on: [deploy-readiness]   # or [review, verify-acceptance-criteria] when deploy-readiness was omitted
    brief: >
      Every upstream stage passed. Write a one-page workflows/runs/csv-export/completion-summary.md:
      what shipped, which commits, the review/security verdicts, and (if present) the deploy
      checklist location.
    write_scope: ["workflows/runs/csv-export/completion-summary.md"]
    exit_criteria:
      type: artifact_exists
      artifact: "workflows/runs/csv-export/completion-summary.md"
    on_fail:
      action: fixing
      max_attempts: 2
      escalate_at: 2
```

Notice: `generate-tests` and `freeze-tests` are the only stages with `write_scope` touching
`test/**`, and `freeze-tests` alone carries `freeze_after: true`. Both sit *before* the freeze
point, which is why owning test paths is legitimate for them — that's how tests get written and
revised while revising them is still a bounded `fixing` loop rather than a `reworking` bounce. Every
stage from the freeze onward is forbidden those paths: if `implement-csv-export`'s diff touches
`test/**`, the orchestrator rejects it regardless of intent. `test-review`, `review` and
`deploy-readiness` own **only the artifact each one writes** — they judge or report on work they
don't produce, and the artifact is the report, not the work. `verify-acceptance-criteria` is the
one true `[]`: it writes nothing at all, its `exit_criteria` command *is* the verification.
`test-review` still directs fixes through
`on_fail.target: generate-tests`, the same mechanism `review` uses against the implement stage; a
reviewer that could edit what it reviews wouldn't be an independent check at all.

`verify-acceptance-criteria` and `review` both `depends_on: [implement-csv-export]` directly — they
are **siblings, not a chain**. kestra-run's rule for running independent stages in parallel ("their
`write_scope`s can't collide by construction") applies to them directly: one is `[]` and the other
owns only its own verdict file, so there's
nothing to collide on, and neither needs the other's result to do its own job. Confirmed by direct
benchmarking: chaining them the "obvious" way (`review: depends_on: [verify-acceptance-criteria]`)
pays for a whole extra sequential subagent round-trip whenever both stages happen to need one, for
no correctness reason — `review`'s diff is already final the instant `implement-csv-export` passes.
Both `on_fail` to `fixing` with `target: implement-csv-export` — findings get a bounded number of
attempts to be addressed in the code, same as any failing check. **If both fail at once**, that's
still exactly one fix attempt on `implement-csv-export` with *both* stages' findings combined into
the brief, not two separate/competing fix attempts touching the same `write_scope` concurrently —
kestra-run's SKILL.md spells out the exact handling for this case. Either or both escalate to
`reworking` only once their own bounded loop is exhausted or stuck repeating the same diff.
`deploy-readiness` (and `done`, when `deploy-readiness` is omitted) waits on **both** siblings, not
just `review` — the full diff isn't actually finished-and-passed until verify has passed too, even
though it ran alongside review rather than after it. No stage in this example stops for a human
unless `reworking` is reached; see `design-principles.md`'s "Default HITL posture" for why that's
now the default, not the exception.

**This example is a monolithic, unanchored workflow, and stays one on purpose** — no `spec_anchor`,
no `tickets:`, no embedded ticket blocks, no `exit_criteria.progress`. That shape is still fully
valid: it is what a fold over a spec with no sliced ticket set produces, and what a hand-written or
standalone spec produces. The sliced-fold additions are all optional and all field-local — read
`spec_anchor` / `tickets` above for the map, "Embedded ticket blocks" for what an owning stage's
`brief` looks like, `exit_criteria.progress` for the copied metric, and
[`ticket-fold.md`](ticket-fold.md) for the procedure that fills them in.

---

## The `design` stage (not in the example above — csv-export has no UI)

`needs_ui: true` adds a `design` stage between `spec-review` and `generate-tests`, so the tests can
assert against decided components and states rather than invented ones. The worked example has no
UI and therefore no such stage, which left its shape unstated — confirmed the useful way, by two
independent generation runs both having to invent `write_scope`, `exit_criteria` type and `on_fail`
from scratch and both reaching for `deploy-readiness` as the closest pattern. It is the closest
pattern; here it is written down so it stops being a guess:

```yaml
  - id: design
    depends_on: [spec-review]
    brief: >
      The spec sets needs_ui: true. Produce <run-folder>/design.md: a component audit (reuse vs. new, with real
      import paths read from this codebase's actual component library), real token names read from
      the actual token source rather than invented hex values, and all four screen states
      (empty/loading/success/error) for every view this feature touches — including any state the
      spec's business rules imply, such as a rejected action, as its own explicit state rather than
      folded into a generic error. A UI-design-focused skill fits this stage well if one is
      installed.
    write_scope: ["<run-folder>/design.md"]
    exit_criteria:
      type: artifact_exists
      artifact: "<run-folder>/design.md"
    on_fail:
      action: fixing
      max_attempts: 2
      escalate_at: 2
```

Two things about this shape are deliberate rather than incidental. `exit_criteria` is
`artifact_exists` and not a verdict grep: the stage's output is a document to be *used* by the
stages after it, and whether it's any good is judged when `generate-tests` and `implement-*` try to
work from it — a verdict line here would be the stage grading its own homework. And `write_scope`
is the design artifact alone, never component source: a `design` stage that can edit `src/` has
quietly become an implementation stage that runs before the tests are frozen, which is the one
ordering the whole design exists to prevent.
