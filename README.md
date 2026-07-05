# kestra-build / kestra-run — TDD-locked workflow pipeline

These two skills work together as a **generator + orchestrator** for building and running a
"stage machine" that actually enforces TDD (not just asking the AI nicely to write tests first).
It freezes tests once written, restricts which files each stage may touch, and commits per stage
so you can always roll back or resume.

```
spec (0-spec.md)
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

Neither skill has a hard dependency on any other skill — if a stage's brief wants to suggest a
specialized skill (e.g. an implement skill, a review skill), that only ever appears as a
"suggestion" inside the brief text. Whatever gets spawned to do that stage's work still runs fine
if that skill isn't installed.

## Installation

This repo *is* the skill — clone it and run `install.sh` to copy (or symlink) the `kestra-build/`
and `kestra-run/` folders into wherever Claude Code auto-discovers skills. No extra config needed:

```bash
git clone <this-repo-url> kestra-workflow-skills
cd kestra-workflow-skills

./install.sh                        # install globally — available in every project (~/.claude/skills/)
./install.sh --project ~/code/app   # install for one project only (<path>/.claude/skills/)
./install.sh --link                 # symlink instead of copy — `git pull` here updates it in place
./install.sh --force                # overwrite an existing install
./install.sh --update               # pull the latest code (git pull here), then refresh the install
./install.sh --uninstall            # remove it (pass the same --project flag used at install time)
```

### Updating to the latest version

If you installed with **`--link`** — nothing extra to do, just `git pull` in this repo; the
symlink already points here.

If you installed with **copy** (the default) — run `./install.sh --update` (add `--project <path>`
too if you did a project-scoped install): it `git pull`s the latest code in this repo first
(skipped if the repo has uncommitted local changes, so it never clobbers work in progress), then
copies the update over the existing install — no need for `--force` or to uninstall first.

Restart Claude Code (or start a new session) afterward so the updated skill gets picked up. No
external dependencies to install — kestra-build's dry-run script (`validate_workflow.py`) only
needs a plain `python3`, no PyYAML or any third-party package.

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
3. Derive the stage list from the actual spec, not a fixed template. The minimal skeleton:
   `spec-review → generate-tests (🔒 freeze) → implement[-per-component] → {verify, review} → done`
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
4. Fill in every stage's fields: `id`, `depends_on`, `brief`, `write_scope`, `exit_criteria`,
   `on_fail`, `freeze_after`.
5. Write `workflow.yaml` + `state.json`.
6. **Always dry-run first**: `python3 kestra-build/scripts/validate_workflow.py <output-dir>` — a
   zero-LLM structural check (no PyYAML, no AI judgment) that catches 7 main things:
   - Missing `on_fail.target` on a `write_scope: []` + `action: fixing` stage
   - `write_scope` overlapping a path that was already frozen as a test path
   - Independent stages whose `write_scope`s collide (a real risk if they run in parallel)
   - `freeze_after: true` missing, or set on more than one stage
   - Dependency cycles / unreachable stages
   - `exit_criteria` or `on_fail` missing required fields
   - `state.json` not matching the stage ids in `workflow.yaml`

   `FAIL` = must be fixed before showing the user, `WARN` = surfaced but not blocking.

7. Shows both files plus a plain-language walkthrough of the stage sequence so the user can
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
| [`kestra-run/references/enforcement.md`](kestra-run/references/enforcement.md) | The exact real commands used for every check (write_scope diff, test-hash, commit-per-stage, rollback) |
| [`kestra-run/references/efficiency-notes.md`](kestra-run/references/efficiency-notes.md) | Why each efficiency shortcut is safe (not spawning a fresh agent every stage, resuming instead of respawning, etc.) |

## What's intentionally "not done"

- **kestra-build never runs anything** — it doesn't write real code, commit, or call any skill.
- **kestra-run never generates a workflow itself** — if the file doesn't exist yet, it says so
  instead of improvising one.
- **Neither skill hard-depends on any specific specialized skill/agent** — any skill name that
  might be suggested in a stage's `brief` is only ever a suggestion ("try it if it's there"), never
  a requirement, so a generated `workflow.yaml` can move to a different machine/session with a
  different skill set and keep working.

## License

See [LICENSE](LICENSE)
