# Enforcement — exact commands, not just the idea of them

Every check here must be a real command you actually run, with the real output pasted before you
act on it. This file exists so you don't improvise slightly-wrong versions of these from memory —
the whole design depends on these being precise.

**What's in here**, in the order a stage needs it:

- **Building the context pack** — before a spawn
- **Anchored surface check** — once per batch, before spawning
- **`write_scope` check** — the diff, and snapshotting a violation before reverting it
- **Test-hash** — computing the freeze and checking it
- **Semantic-diff hashing** — `seen_diffs` no-progress detection, then declared progress, then
  failure-signature hashing (`seen_failures`, diagnostic only)
- **Commit-per-stage**, then **Rollback**

## Building the context pack (before a spawn)

The pack SKILL.md's step 2 requires is assembled from commands you already have to run anyway.
Gather it immediately before spawning, not once per stage-with-retries — a stale pack misleads.

```bash
# 0. Spec handoff. Set PACK_MODE=slim only after both proofs pass; otherwise set it to full.
case "$PACK_MODE" in
  slim) printf '%s\n' "source_spec=$SPEC" "surface verified against $RAISE; read on demand" ;;
  full) cat "$SPEC" ;;
  *) echo "MISMATCH: pack mode was not proven"; exit 1 ;;
esac

# 1. Starting state: run the stage's own exit_criteria.run yourself first.
#    Capture the exit code — for a pre-implementation stage a NON-zero code is the expected,
#    informative answer, not a failure to hide.
<the stage's exit_criteria.run command>; echo "exit=$?"

# 2. What the most recent CODE-touching stage actually did — not just "the previous stage":
#    a stage right after a no-diff stage (implement-* after freeze-tests, whose own commit is
#    essentially a state.json update) needs the diff from further back, or this pastes a near-empty
#    diff and omits the one that matters. <prev-sha> is that commit, recorded in state.json /
#    findable via `git log --oneline` by skipping any stage whose diff --name-only was empty.
git diff --name-only <prev-sha>^ <prev-sha>
git diff -U0 <prev-sha>^ <prev-sha>
# For implement-*, also resolve and paste the frozen suite's file list (the freeze stage's
# write_scope, resolved to real paths) — that's what it's implementing against.

# 3. Verdict artifact from the previous stage, and its verdict line only.
ls <run-folder>/*verdict*.md
grep -m1 '^VERDICT:' <run-folder>/<prev-stage>-verdict.md

# 4. Anything already computed or built for this run.
ls -1 <run-folder>/evidence/ <run-folder>/harness/ 2>/dev/null
```

Paste the real output of each into the spawn prompt. Nothing here reads a language-specific file —
`exit_criteria.run` comes from `workflow.yaml`, the rest is `git` and `ls` — so this works
unchanged in any repo.

## Anchored surface check — once per batch, before spawning

Read `source_spec` and the three `spec_anchor` values from `workflow.yaml`. When the anchor is
present, require a complete triple, run the freshness comparison, and only then use the run
folder's frozen validator to prove the ticket-block shape:

```bash
RUN=<run-folder>; SPEC=<source_spec>; RAISE=<spec_anchor.raise_commit>
RECORDED_HASH=<spec_anchor.surface_hash>; RECORDED_VERSION=<spec_anchor.extractor_version>

(
  RAISED_SPEC=$(mktemp) || exit 1
  trap 'rm -f -- "$RAISED_SPEC"' EXIT
  git cat-file -e "$RAISE^{commit}" || exit 1
  python3 -c "import sys; sys.path.insert(0, '$RUN'); import requirement_surface as r; sys.exit(0 if r.EXTRACTOR_VERSION == $RECORDED_VERSION else 1)" \
    || exit 1
  CURRENT_HASH=$(python3 "$RUN/requirement_surface.py" "$SPEC" --hash) || exit 1
  git show "$RAISE:$SPEC" > "$RAISED_SPEC" || exit 1
  RAISED_HASH=$(python3 "$RUN/requirement_surface.py" "$RAISED_SPEC" --hash) || exit 1
  [ "$CURRENT_HASH" = "$RAISED_HASH" ] && [ "$RAISED_HASH" = "$RECORDED_HASH" ]
) || { echo "MISMATCH: anchored requirement surface is stale or unverifiable"; exit 1; }

python3 "$RUN/validate_workflow.py" "$RUN" \
  || { echo "MISMATCH: anchor or embedded ticket validation failed"; exit 1; }
```

Missing/partial fields, invalid ticket blocks, an unreachable raise, version drift, or either hash
mismatch is a hard stop and never enters `reworking`. With no `spec_anchor`, report that freshness
is not mechanically checkable and continue with the full-spec pack.

## write_scope check

After a subagent finishes a stage's work, compare what it actually touched against the stage's
`write_scope` globs:

```bash
# Everything changed since the last commit
git diff --name-only HEAD

# Compare each path against the stage's write_scope patterns (bash glob match).
# Example for write_scope: ["src/routes/**", "src/services/csv-export/**"]
VIOLATIONS=$(mktemp) || exit 1
trap 'rm -f -- "$VIOLATIONS"' EXIT
while IFS= read -r f; do
  case "$f" in
    src/routes/*|src/services/csv-export/*) ;;   # allowed — one case arm per write_scope glob
    *) printf 'VIOLATION: %s outside write_scope\n' "$f"
       printf '%s\n' "$f" >> "$VIOLATIONS" ;;
  esac
done < <({ git diff --name-only HEAD; git ls-files --others --exclude-standard; } | sort -u)
```

If anything printed as a violation, check whether it's a modified *tracked* file or a brand-new
*untracked* one — `git status --porcelain`'s first column tells you (` M`/`M ` = tracked change,
`??` = untracked). These need different revert commands; using the wrong one silently no-ops:

Snapshot only the paths already recorded in `$VIOLATIONS` into a fresh directory outside the repo,
verify every copy/patch, report that directory, and then revert the same path. Keeping the snapshot
outside the repo prevents the evidence itself from becoming the next attempt's scope violation.
Dirty files discovered while resuming remain user work and follow the existing say-so-first rule.

```bash
EVIDENCE=$(mktemp -d "${TMPDIR:-/tmp}/kestra-run-scope-<stage-id>-attempt-<n>.XXXXXX") || exit 1
printf 'scope-violation snapshot: %s\n' "$EVIDENCE"
while IFS= read -r f; do
  DEST="$EVIDENCE/$f"
  mkdir -p -- "$(dirname -- "$DEST")" || exit 1
  if [ -e "$f" ] || [ -L "$f" ]; then
    cp -pPR -- "$f" "$DEST" || exit 1
  else
    git diff --binary HEAD -- "$f" > "$DEST.patch" || exit 1
  fi
  if git ls-files --error-unmatch -- "$f" >/dev/null 2>&1; then
    git restore --source=HEAD --staged --worktree -- "$f" || exit 1
  else
    rm -f -- "$f" || exit 1
  fi
done < "$VIOLATIONS"
```

Then treat this attempt as failed (go to the `fixing` accounting in SKILL.md step 6) — don't
silently keep the out-of-scope change. Always check the exit code of the revert command itself;
a failed revert must not be treated as "handled."

`write_scope: []` means **zero** tolerance — any diff at all is a violation. Reserve it for a stage
that writes literally nothing, such as a `human_approval` gate. **A stage told to write a verdict
artifact is not one of those.** The verdict is a brand-new untracked file, `git ls-files --others`
above reports it, and under `[]` it is a violation — so it gets snapshotted and `rm -f`'d, and then
`exit_criteria` greps a file that no longer exists. That stage cannot pass on any attempt. Such a
stage lists its own verdict path in `write_scope`; `kestra-build` writes them that way.

**Never counted as any stage's diff: the run folder's own `state.json`.** The orchestrator rewrites
it every attempt and it stays uncommitted until the stage passes (see Commit-per-stage below), so
it appears in every diff while belonging to no stage. Exclude it from the comparison rather than
expecting it in a `write_scope` — the same reason the semantic-diff hash below excludes it.

**Exception: a `fixing` retry with `on_fail.target` set.** A `review`/verify stage owns no code, so
it declares `on_fail: {action: fixing, target: implement-x}` — the fix attempt is legitimately
allowed to touch `implement-x`'s `write_scope`. When checking a fixing attempt spawned this way,
diff against `target`'s `write_scope` globs **plus the failing stage's own** — the fix writes the
code, then the stage re-runs and rewrites its verdict. **The trigger is `target` being set**, not
the failing stage's `write_scope` being empty. Everything else about the check is identical — same
tracked-vs-untracked revert distinction, same "treat as failed attempt" outcome on a violation.
Get this wrong (checking against the review stage's own scope alone) and every such fix attempt
reads as a 100% violation regardless of what the subagent actually did.

## Test-hash: computing and checking the freeze

The hashed paths are whatever `write_scope` the `freeze_after: true` stage used — don't invent a
separate list.

**One canonical formula, always — a single `find` over every root, one global sort, run from the
repo root.** `write_scope` often lists more than one root (e.g. `["test/**", "package.json",
"package-lock.json", "jest.config.js"]`). Confirmed by direct testing: two different but
each-internally-consistent ways
of handling multiple roots exist if you improvise — a single `find <all roots> | sort` over the
whole set, versus running `find` per root and concatenating the results in `write_scope`'s
declaration order without a global re-sort. Both produce a hash that matches itself on
re-verification, but they produce a **different** hash from each other for the identical file set —
so if a human, a different tool, or a resumed run ever recomputes the hash without knowing which of
the two methods the freezing run used, a perfectly-intact test suite reads as MISMATCH. Pick the
single-`find` form below and never the per-root-concatenation form.

**A second, easy-to-miss version of the same trap: working directory.** `write_scope` entries are
always written repo-root-relative (the same basis the `write_scope check` above uses —
`git diff --name-only HEAD` reports paths relative to the repo root regardless of cwd, never
relative to wherever you happen to be). Run the `find` below **from the repo root**, with the
`write_scope` paths exactly as declared — never from inside a directory a particular stage's
`exit_criteria.run` happens to `cd` into first. Confirmed by direct testing: hashing the identical
file from the repo root (`find workflow/evals/.../fixture/test/queue.test.js`) versus from inside
that stage's own working directory (`find test/queue.test.js`) produces two different hashes for
byte-for-byte identical content — the freeze and every later check must use the same cwd basis, and
repo root is the canonical one because that's where `write_scope` enforcement and every git command
in this file already run from.

```bash
# Build the root list from write_scope: a "dir/**" entry becomes "dir"; a literal filename entry
# is used as-is; entries that don't exist on disk are skipped (e.g. write_scope commonly lists both
# jest.config.js and jest.config.cjs to cover either convention, but only one will actually exist).
ROOTS=()
for p in "test/**" "package.json" "package-lock.json" "jest.config.js" "jest.config.cjs"; do
  p="${p%/\*\*}"
  [ -e "$p" ] && ROOTS+=("$p")
done
find "${ROOTS[@]}" -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}'
```

(the `for` list above is illustrative — substitute the actual frozen stage's `write_scope` entries)

For the common single-root case this collapses to exactly the same one-liner as before:

```bash
find test -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}'
```

Store the resulting hash string as `state.json`'s `test_hash`.

**Check (before any stage runs, once `test_hash` is non-null):** recompute with the *identical*
`ROOTS`-building logic (same `write_scope` entries, same existence check, same single `find` call),
then compare:

```bash
CURRENT=$(find "${ROOTS[@]}" -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')
[ "$CURRENT" = "$STORED_TEST_HASH" ] && echo "OK: hash matches" || echo "MISMATCH: halt"
```

A mismatch is a hard stop (SKILL.md step 1) — report it, don't try to reconcile it yourself. But
first rule out that the mismatch is an artifact of using a different root-combining method than
whichever run froze the hash, not an actual change to the frozen files — re-derive `ROOTS` from the
stage's own `write_scope` in `workflow.yaml` and use the single-`find` form above before concluding
the tests were actually touched.

## Semantic-diff hashing (for `seen_diffs` no-progress detection)

**Scope this to the stage's own `write_scope` paths — never bare `git diff HEAD`.** Confirmed by
direct testing: `fixing` attempts are *not* committed between retries (see Commit-per-stage
below — only a `passed` stage commits), so `state.json` itself sits uncommitted with a changing
`attempt` counter across every retry. A bare `git diff HEAD` includes that `state.json` churn, so
the hash comes out different on every attempt *even when the stage's actual code diff is
byte-for-byte identical* — silently defeating no-progress detection. Scope the diff to the
stage's `write_scope` globs (e.g. `src/**`) so only the stage's own output is hashed:

```bash
# Normalize before hashing so cosmetic re-runs of the same fix don't look "new".
# Replace `src/` with the stage's actual write_scope path(s) — exclude state.json and anything
# outside write_scope.
git diff HEAD -- src/ | grep -E '^[+-]' | grep -v '^[+-][+-][+-]' | sort | sha256sum | awk '{print $1}'
```

Compare this hash against the stage's `seen_diffs` list in `state.json`. Same hash reappearing =
no progress = escalate to `reworking` immediately, even if `attempt < max_attempts`.

### Declared progress

For a stage with `exit_criteria.progress`, capture the fresh attempt-0 pre-run output and extract
the named number before the first spawn; seed `progress_history` with `{attempt: 0, value: N}`.
After each failed attempt, append the value from that attempt's own captured output, or
`"unmeasured"` when it cannot be extracted. Compare adjacent entries toward the declared target:
strict improvement resets the count; equal, worse, or unmeasured increments it. When the last two
comparisons show no progress, enter the existing `reworking` stop before starting another attempt.

This block replaces the ordinary criterion invocation for a progress-bearing stage, so the command
runs once per round. Substitute only the metric-specific extraction command and numeric target named
by `exit_criteria.progress`; seed attempt `0` once, then use the real exit code to append only failed
attempts:

```bash
PROGRESS_OUTPUT=$(mktemp) || exit 1
trap 'rm -f -- "$PROGRESS_OUTPUT"' EXIT
STATE=<run-folder>/state.json; STAGE=<stage-id>
ATTEMPT=<0-or-current-attempt>; TARGET=<declared-numeric-target>
if <the stage's exit_criteria.run command> >"$PROGRESS_OUTPUT" 2>&1; then
  CRITERION_EXIT=0
else
  CRITERION_EXIT=$?
fi
cat "$PROGRESS_OUTPUT"

if [ "$ATTEMPT" -ne 0 ] && [ "$CRITERION_EXIT" -eq 0 ]; then
  PROGRESS_DECISION=passed
else
  if VALUE=$(<metric-specific extraction command> <"$PROGRESS_OUTPUT"); then :; else VALUE=unmeasured; fi
  if python3 - "$STATE" "$STAGE" "$ATTEMPT" "$VALUE" "$TARGET" <<'PY'
import json
import math
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
stage_id, raw_attempt, raw_value, raw_target = sys.argv[2:]
attempt = int(raw_attempt)
state = json.loads(path.read_text())
stage = dict(state["stages"][stage_id])
history = list(stage.get("progress_history", []))
if history and int(history[-1]["attempt"]) >= attempt:
    raise SystemExit("progress attempt must increase")
try:
    parsed_value = float(raw_value)
    value = parsed_value if math.isfinite(parsed_value) else "unmeasured"
except ValueError:
    value = "unmeasured"
history = [*history, {"attempt": attempt, "value": value}]
updated_stage = {**stage, "progress_history": history}
updated = {**state, "stages": {**state["stages"], stage_id: updated_stage}}
tmp = path.with_name(path.name + ".progress.tmp")
tmp.write_text(json.dumps(updated, indent=2) + "\n")
os.replace(tmp, path)

def distance(entry):
    try:
        value, target = float(entry["value"]), float(raw_target)
        return abs(value - target) if math.isfinite(value) and math.isfinite(target) else None
    except (TypeError, ValueError):
        return None

def no_move(before, after):
    old, new = distance(before), distance(after)
    return old is None or new is None or new >= old

stalled = (len(history) >= 3 and no_move(history[-3], history[-2])
           and no_move(history[-2], history[-1]))
raise SystemExit(3 if stalled else 0)
PY
  then
    PROGRESS_DECISION=continue
  else
    PROGRESS_RC=$?
    if [ "$PROGRESS_RC" -eq 3 ]; then
      PROGRESS_DECISION=reworking
    else
      echo "MISMATCH: progress history could not be updated"; exit 1
    fi
  fi
fi
```

`CRITERION_EXIT` remains the real pass/fail result; a later pass sets `PROGRESS_DECISION=passed`
without appending, and progress never turns a failed criterion green.
When `PROGRESS_DECISION=reworking`, take SKILL.md's existing `reworking` transition before starting
another attempt — this recipe does not create a second transition path.

### Failure-signature hashing (for `seen_failures`, diagnostic only)

Mirrors the recipe above but hashes the `exit_criteria.run` command's *failure output*, not the
diff — this catches a case `seen_diffs` structurally can't: a too-narrow `write_scope` or a broken
environment blocking every fix attempt identically, where each attempt still produces a genuinely
*different*, equally futile diff (so `seen_diffs` never repeats even though nothing is converging).
Normalize the same way — strip anything that varies for reasons unrelated to the actual failure
(timestamps, durations, absolute paths, PIDs) before hashing:

```bash
<exit_criteria.run command> 2>&1 | grep -viE '([0-9]{2}:){2}[0-9]{2}|took [0-9.]+ ?m?s|pid [0-9]+' \
  | sed -E 's#/[^ ]*/([a-zA-Z0-9_.-]+)#\1#g' | sha256sum | awk '{print $1}'
```

Append to the stage's `seen_failures` array in `state.json` (see `state-schema.md`). This is a
diagnostic signal only — it never changes a transition decision on its own, and its only consumer
is the `reworking` report's wording (see kestra-run `SKILL.md` step 6): surface the raw count as a
lead, never as a conclusion that overrides the default "the frozen spec/tests are the suspect."

## Commit-per-stage

Before the first commit in a repo that doesn't already have one, make sure build/test-runner
artifacts (`__pycache__/`, `*.pyc`, `.pytest_cache/`, `node_modules/`, etc.) are gitignored.
Confirmed by direct testing: a bare `git add -A` after running the exit-criteria test command
happily stages the test runner's own cache files alongside real output — noise that has nothing
to do with the stage's actual work.

Once a stage passes (mechanical checks above both clean):

```bash
git add -A
git commit -m "stage(<feature-id>): <stage-id> passed"
```

`state.json` must be part of that same commit — update it (status, test_hash if this was the
freeze stage, attempt/seen_diffs reset if this followed a `reworking`) and stage it alongside the
code changes before committing, not as a separate commit afterward. One commit per stage, always —
**with one exception**: when multiple stages that own no code pass in the same batch (e.g.
`verify`+`review`), combine them into a single commit naming every stage id
(`stage(<feature-id>): verify-acceptance-criteria, review passed`), since such a
stage's commit holds only its own verdict artifact and the `state.json` update — there's no
per-stage code state a separate commit would preserve. Name every id individually in the message so the rollback grep below still
resolves per stage.

No `git tag` per stage — the commit itself is the rollback point (see Rollback below). Tags
accumulate quickly across a multi-stage run without adding anything a commit SHA doesn't already
give you.

## Rollback

```bash
git log --oneline --grep "stage(<feature-id>): <stage-id> passed"   # find the commit SHA
git reset --hard <sha>
```

This is destructive — confirm with the user before running it, same as any other hard reset.
