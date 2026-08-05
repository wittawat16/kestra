#!/bin/sh
# Every leg of the Wave-4b kestra-run eval, one command at a time, literal output
# into ../logs/.  Re-run with:
#
#     sh workflow/evals/2026-08-03-wave4b-run-slim/fixtures/run-legs.sh
#
# Writes only to $KX_ROOT (default /tmp/kx38) and ../logs/.  The fixture is the
# Wave-4a build-fold fixture (an anchored sliced fold with three embedded ticket
# briefs) materialized into a real git repo so `git show <raise>:<spec>` and
# `git cat-file -e` are real commands against real commits, not simulations.
#
# What this eval grades: the run-side procedures #38 adds to kestra-run —
# the pre-spawn surface check (fail-closed, every arm), the slim context pack
# (brief + provision only, spec on demand), the progress clause-2 escalation
# predicate, and the snapshot-before-revert recipe.  All of them are prose in
# SKILL.md/enforcement.md; every leg here runs the *commands* that prose
# mandates and records the real exit codes.
set -u

FIX=$(cd "$(dirname "$0")" && pwd)
EVAL_DIR=$(cd "$FIX/.." && pwd)
UPSTREAM=$(cd "$EVAL_DIR/../../.." && pwd)
SRC="$UPSTREAM/workflow/evals/2026-08-02-wave4a-build-fold/runs/wave4a-fixture"
LOGS="$EVAL_DIR/logs"

ROOT=${KX_ROOT:-/tmp/kx38}
REPO="$ROOT/repo"
RUN="$REPO/run"
TMPSPEC="$ROOT/raise-spec.md"
export PYTHONDONTWRITEBYTECODE=1
GITC="git -c user.email=eval@local -c user.name=eval"

mkdir -p "$LOGS" "$ROOT"
FAILURES=0
expect() { # expect <desc> <want-exit> <got-exit>
  if [ "$2" -eq "$3" ]; then printf 'ASSERT OK: %s (exit %s)\n' "$1" "$3"
  else printf 'ASSERT FAIL: %s (want exit %s, got %s)\n' "$1" "$2" "$3"; FAILURES=$((FAILURES+1)); fi
}

# The pre-spawn surface check, exactly as enforcement.md's recipe orders it.
# cwd must be the repo root.  Args: raise spec-rel-path run-dir recorded-version recorded-surface-hash
surface_check() {
  r=$1; spec=$2; rundir=$3; ver=$4; sh256=$5
  case "$r" in *[!0-9a-f]*|"") echo "MISMATCH: partial anchor — raise_commit fails grammar"; return 1;; esac
  [ ${#r} -eq 40 ] || { echo "MISMATCH: partial anchor — raise_commit is not 40 hex chars"; return 1; }
  [ -n "$ver" ] || { echo "MISMATCH: partial anchor — extractor_version missing"; return 1; }
  [ -n "$sh256" ] && [ ${#sh256} -eq 64 ] || { echo "MISMATCH: partial anchor — surface_hash missing or malformed"; return 1; }
  git cat-file -e "$r^{commit}" 2>/dev/null || { echo "MISMATCH: raise_commit unreachable in this repo"; return 1; }
  rv=$(python3 -c "import sys; sys.path.insert(0,'$rundir'); import requirement_surface as x; print(x.EXTRACTOR_VERSION)") \
    || { echo "MISMATCH: run-folder extractor unimportable"; return 1; }
  [ "$rv" = "$ver" ] || { echo "MISMATCH: extractor_version differs (recorded $ver vs run copy $rv) — hashes not comparable"; return 1; }
  h1=$(python3 "$rundir/requirement_surface.py" "$spec" --hash) || { echo "MISMATCH: working-tree recompute failed"; return 1; }
  git show "$r:$spec" > "$TMPSPEC" 2>/dev/null || { echo "MISMATCH: spec unreadable at raise commit"; return 1; }
  h2=$(python3 "$rundir/requirement_surface.py" "$TMPSPEC" --hash) || { echo "MISMATCH: raised-spec recompute failed"; return 1; }
  [ "$h1" = "$h2" ] || { echo "MISMATCH: surface moved — working $h1 vs raised $h2"; return 1; }
  [ "$h2" = "$sh256" ] || { echo "MISMATCH: recorded surface_hash disagrees with the recompute at raise_commit — the anchor was edited"; return 1; }
  echo "SURFACE OK: working == raised == recorded == $h1"; return 0
}

anchor_fields() { # reads $RUN/workflow.yaml into RAISE/SPEC/VER/SH256
  RAISE=$(grep -m1 '^  raise_commit:' "$RUN/workflow.yaml" | awk '{print $2}')
  SPEC=$(grep -m1 '^source_spec:' "$RUN/workflow.yaml" | awk '{print $2}')
  VER=$(grep -m1 '^  extractor_version:' "$RUN/workflow.yaml" | awk '{print $2}')
  SH256=$(grep -m1 '^  surface_hash:' "$RUN/workflow.yaml" | awk '{print $2}')
}

# ------------------------------------------------------------- leg 0: fixture repo
{
  echo "=== leg 0 — materialize the wave4a fixture into a real git repo ==="
  rm -rf "$REPO"; mkdir -p "$RUN"
  git init -q "$REPO"
  cp "$SRC/0-spec.md" "$RUN/"
  (cd "$REPO" && git add run/0-spec.md && $GITC commit -qm "raise: fixture spec")
  RAISE=$(git -C "$REPO" rev-parse HEAD)
  echo "raise commit: $RAISE"
  cp "$SRC/workflow.yaml" "$SRC/state.json" "$SRC/requirement_surface.py" \
     "$SRC/validate_spec.py" "$SRC/validate_workflow.py" "$RUN/"
  mkdir -p "$RUN/tickets"; cp "$SRC"/tickets/*.md "$RUN/tickets/"
  NEWH=$(python3 "$RUN/requirement_surface.py" "$RUN/0-spec.md" --hash)
  sed -i.bak \
    -e "s|^source_spec: .*|source_spec: run/0-spec.md|" \
    -e "s|^  raise_commit: .*|  raise_commit: $RAISE|" \
    -e "s|^  surface_hash: .*|  surface_hash: $NEWH|" \
    -e "s|^    verified_against: .*|    verified_against: $RAISE|" \
    "$RUN/workflow.yaml" && rm "$RUN/workflow.yaml.bak"
  (cd "$REPO" && git add -A && $GITC commit -qm "fold: workflow + state + frozen tooling")
  git -C "$REPO" log --oneline
  echo "exit=$?"
} > "$LOGS/00-fixture.log" 2>&1

cd "$REPO"
anchor_fields

# ------------------------------------------------------------- leg 1: clean check
{
  echo "=== leg 1 — pre-spawn surface check on a clean tree: must pass ==="
  echo "\$ surface_check $RAISE $SPEC run $VER <surface_hash>"
  surface_check "$RAISE" "$SPEC" "$RUN" "$VER" "$SH256"; c=$?
  echo "exit=$c"; expect "clean tree passes" 0 $c
} > "$LOGS/01-clean.log" 2>&1

# ------------------------------------------------------------- leg 2: moved surface
{
  echo "=== leg 2 — an AC edited in the working-tree spec: MISMATCH, hard stop ==="
  # Edit an AC cell in the ## AC Coverage Map — that table's AC/Source columns are IN
  # the surface; the Given-When-Then "## Acceptance Criteria" bullets are deliberately
  # OUT (requirement_surface.py's boundary), so editing those would NOT move the hash.
  # Measured here first: an edit to an AC bullet left the hash unchanged — correct
  # extractor behavior, wrong leg simulation.
  cp "$RUN/0-spec.md" "$ROOT/0-spec.pristine"
  sed -i.bak 's/an export of an empty result set returns a header-only CSV/an export of an empty result set returns an empty body/' "$RUN/0-spec.md" && rm "$RUN/0-spec.md.bak"
  echo "\$ diff pristine edited:"; diff "$ROOT/0-spec.pristine" "$RUN/0-spec.md"
  surface_check "$RAISE" "$SPEC" "$RUN" "$VER" "$SH256"; c=$?
  echo "exit=$c"; expect "moved surface is a MISMATCH" 1 $c
  cp "$ROOT/0-spec.pristine" "$RUN/0-spec.md"
  surface_check "$RAISE" "$SPEC" "$RUN" "$VER" "$SH256"; c=$?
  echo "exit=$c"; expect "restored tree passes again" 0 $c
} > "$LOGS/02-moved-surface.log" 2>&1

# ------------------------------------------------------------- leg 3: unreachable anchor
{
  echo "=== leg 3 — raise_commit unreachable: MISMATCH, fail-closed, never a skip ==="
  BAD=$(printf 'deadbeef%.0s' 1 2 3 4 5)
  echo "\$ surface_check $BAD ..."
  surface_check "$BAD" "$SPEC" "$RUN" "$VER" "$SH256"; c=$?
  echo "exit=$c"; expect "unreachable anchor is a MISMATCH" 1 $c
} > "$LOGS/03-unreachable.log" 2>&1

# ------------------------------------------------------------- leg 4: partial anchor
{
  echo "=== leg 4 — partial anchor (surface_hash deleted): run-side MISMATCH + validator FAIL ==="
  PART="$ROOT/partial-run"; rm -rf "$PART"; cp -R "$RUN" "$PART"
  grep -v '^  surface_hash:' "$RUN/workflow.yaml" > "$PART/workflow.yaml"
  PSH=$(grep -m1 '^  surface_hash:' "$PART/workflow.yaml" | awk '{print $2}')
  surface_check "$RAISE" "$SPEC" "$PART" "$VER" "$PSH"; c=$?
  echo "exit=$c"; expect "partial anchor is a MISMATCH before any command runs" 1 $c
  echo "\$ python3 $PART/validate_workflow.py $PART   # the fold-side view of the same defect"
  python3 "$PART/validate_workflow.py" "$PART"; c=$?
  echo "exit=$c"; expect "validate_workflow.py FAILs the partial anchor" 1 $c
} > "$LOGS/04-partial-anchor.log" 2>&1

# ------------------------------------------------------------- leg 5: extractor drift
{
  echo "=== leg 5 — recorded extractor_version 2 vs run copy 1: not comparable, MISMATCH ==="
  surface_check "$RAISE" "$SPEC" "$RUN" "2" "$SH256"; c=$?
  echo "exit=$c"; expect "extractor_version drift is a MISMATCH" 1 $c
} > "$LOGS/05-extractor-drift.log" 2>&1

# ------------------------------------------------------------- leg 5b: edited anchor hash
{
  echo "=== leg 5b — recorded surface_hash edited (arm 4): MISMATCH even though recomputes agree ==="
  FAKE=$(printf 'a%.0s' $(seq 1 64))
  surface_check "$RAISE" "$SPEC" "$RUN" "$VER" "$FAKE"; c=$?
  echo "exit=$c"; expect "edited recorded surface_hash is a MISMATCH" 1 $c
} > "$LOGS/05b-edited-anchor-hash.log" 2>&1

# ------------------------------------------------------------- leg 6: the slim pack
{
  echo "=== leg 6 — slim pack for implement-csv-writer: brief + provision only, spec on demand ==="
  PACK="$ROOT/pack-implement-csv-writer.txt"
  # brief: the stage's block from workflow.yaml, exactly as the fold emitted it
  awk '/^  - id: implement-csv-writer$/{f=1} f&&/^  - id: /&&!/implement-csv-writer/{exit} f' \
    "$RUN/workflow.yaml" > "$ROOT/stage-block.txt"
  {
    echo "## Stage brief (embedded ticket block, verbatim from workflow.yaml)"
    cat "$ROOT/stage-block.txt"
    echo "## Provision layer"
    grep -m1 'write_scope' "$ROOT/stage-block.txt"
    EC=$(grep -m1 '      run:' "$ROOT/stage-block.txt" | sed 's/^ *run: *//; s/"//g')
    printf 'pre-run exit_criteria: %s\n' "$EC"
    sh -c "$EC" >/dev/null 2>&1; printf 'pre-run exit=%s (pre-implementation: non-zero is the expected, informative answer)\n' "$?"
    echo "diff vs last code-touching commit: (none — no implement stage has run yet)"
    echo "evidence/: (empty)  harness/: (empty)"
    echo "## Spec"
    printf 'source_spec: %s — surface verified fresh this batch against %s — read sections on demand.\n' "$SPEC" "$RAISE"
  } > "$PACK"
  wc -l "$PACK"
  grep -c 'ticket:begin 01-csv-writer' "$PACK"; expect "pack carries the embedded ticket block" 0 $((1-$(grep -c 'ticket:begin 01-csv-writer' "$PACK")))
  grep -q 'write_scope' "$PACK"; expect "pack carries write_scope" 0 $?
  grep -q 'read sections on demand' "$PACK"; expect "pack carries the on-demand spec line" 0 $?
  grep -q 'object store does not guarantee read-after-write' "$PACK"; c=$?
  expect "spec body is NOT pasted (sentinel line absent)" 1 $c
  grep -q 'object store does not guarantee read-after-write' "$RUN/0-spec.md"; expect "…while the sentinel does exist in the spec" 0 $?
} > "$LOGS/06-slim-pack.log" 2>&1

# ------------------------------------------------------------- leg 7: progress clause 2
{
  echo "=== leg 7 — progress metric stalls two rounds: clause-2 escalation to reworking ==="
  # Three failed attempts, all reporting the same failing count, per the extraction recipe.
  for a in 1 2 3; do printf '2 failing, 1 passed\n' > "$ROOT/attempt$a.out"; done
  python3 - "$RUN/state.json" "$ROOT" <<'EOF'
import json, re, sys
state_path, root = sys.argv[1], sys.argv[2]
state = json.load(open(state_path))
stage = state["stages"]["implement-csv-writer"]
hist = stage.setdefault("progress_history", [])
target_direction_down = True  # "must reach 0"
no_progress = 0
for attempt in (1, 2, 3):
    out = open(f"{root}/attempt{attempt}.out").read()
    m = re.search(r"(\d+) fail", out)
    value = m.group(1) if m else "unmeasured"
    hist.append({"attempt": attempt, "value": value})
    if len(hist) >= 2:
        prev, cur = hist[-2]["value"], hist[-1]["value"]
        moved = (prev != "unmeasured" and cur != "unmeasured" and int(cur) < int(prev))
        no_progress = 0 if moved else no_progress + 1
        print(f"attempt {attempt}: value={value} prev={prev} moved={moved} consecutive_no_progress={no_progress}")
        if no_progress >= 2:
            print("ESCALATE: reworking — two consecutive attempt rounds without the number moving (clause 2)")
            json.dump(state, open(state_path, "w"), indent=2)
            sys.exit(3)
    else:
        print(f"attempt {attempt}: value={value} (baseline, nothing to compare)")
json.dump(state, open(state_path, "w"), indent=2)
EOF
  c=$?
  echo "exit=$c"; expect "clause 2 fires on the second stalled round" 3 $c
  echo "\$ python3 -c 'json… progress_history'   # the field as persisted in state.json"
  python3 -c "import json;print(json.load(open('$RUN/state.json'))['stages']['implement-csv-writer']['progress_history'])"
} > "$LOGS/07-progress-clause2.log" 2>&1

# ------------------------------------------------------------- leg 8: snapshot then revert
{
  echo "=== leg 8 — write_scope violation: snapshot to evidence/, then revert, tree clean ==="
  mkdir -p "$REPO/src"; printf 'oops = True\n' > "$REPO/src/stray.py"   # untracked, outside write_scope
  git status --porcelain
  SNAP="$RUN/evidence/scope-violations/implement-csv-writer-attempt-1"
  mkdir -p "$SNAP/src"
  cp "$REPO/src/stray.py" "$SNAP/src/stray.py"
  rm -f "$REPO/src/stray.py"; rmdir "$REPO/src" 2>/dev/null
  test -f "$SNAP/src/stray.py"; expect "snapshot copy exists in evidence/" 0 $?
  test -f "$REPO/src/stray.py"; expect "violating file is gone from the worktree" 1 $?
  git status --porcelain -- src/ | grep -q .; expect "worktree clean outside the run folder" 1 $?
} > "$LOGS/08-snapshot-revert.log" 2>&1

# ------------------------------------------------------------- leg 9: upstream regression
{
  echo "=== leg 9 — nothing upstream broke: tests + validator on the worked example ==="
  cd "$UPSTREAM"
  python3 workflow/kestra-build/scripts/test_requirement_surface.py 2>&1 | tail -1; echo "exit=$?"
  python3 workflow/kestra-build/scripts/test_validate_workflow_anchor.py 2>&1 | tail -1; echo "exit=$?"
  python3 workflow/kestra-build/scripts/validate_workflow.py workflow/runs/order-cancellation-refund; c=$?
  echo "exit=$c"; expect "worked example still PASSes" 0 $c
} > "$LOGS/09-upstream-regression.log" 2>&1

# ------------------------------------------------------------- verdict
{
  echo "legs 0-9 complete; assertion failures: $FAILURES"
  grep -h 'ASSERT' "$LOGS"/0*.log
} > "$LOGS/verdict.log" 2>&1
cat "$LOGS/verdict.log"
[ "$FAILURES" -eq 0 ]
