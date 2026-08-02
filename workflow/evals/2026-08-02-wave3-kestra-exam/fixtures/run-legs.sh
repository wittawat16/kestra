#!/bin/sh
# Every leg of the Wave-3 kestra-exam eval, one command at a time, literal
# output into ../logs/.  Re-run with:
#
#     sh workflow/evals/2026-08-02-wave3-kestra-exam/fixtures/run-legs.sh
#
# Writes only to $KX_ROOT (default /tmp/kx36) and to ../logs/ + ../exam/ inside
# the eval directory.  The real user-level exams root is never touched: every
# invocation runs under KESTRA_EXAMS_ROOT=$KX_ROOT/exams, which exam_paths.py
# echoes as `exams_root_overridden: yes`.
#
# THE SWEEP TOKEN IS NEVER WRITTEN IN THIS REPO.  Sweep S2 forbids the token in
# any commit message and S1/S3 forbid it outside the skill's own two exempt
# paths, so this eval builds it at run time ($TOK) and every sweep runs with
# `grep -q` so no hit text can land in a log either.  An eval that spelled the
# token would make the sweeps it is testing fail.
set -u

FIX=$(cd "$(dirname "$0")" && pwd)
EVAL_DIR=$(cd "$FIX/.." && pwd)
UPSTREAM=$(cd "$EVAL_DIR/../../.." && pwd)
S="$UPSTREAM/workflow/kestra-exam/scripts"
LOGS="$EVAL_DIR/logs"

ROOT=${KX_ROOT:-/tmp/kx36}
REPO="$ROOT/repo"
RUN="$REPO/workflows/runs/tally-refund"
export KESTRA_EXAMS_ROOT="$ROOT/exams"
TOK=$(printf 'kestra%sexams' '/')
TMPO="$ROOT/.out"
# No __pycache__ anywhere: importing the skill's scripts must not write into the
# skill repo, and the exam dir's git status must stay honest.
export PYTHONDONTWRITEBYTECODE=1

# $ROOT is created HERE, before leg 0, because run() redirects into $ROOT/.out:
# on a machine where the root does not pre-exist, creating it after leg 0 left the
# script with no fixture at all and it aborted at `. "$ROOT/shas.env"`.
mkdir -p "$LOGS" "$EVAL_DIR/exam" "$ROOT"

hdr() { printf '\n=== %s ===\n\n' "$*"; }
run() {
  printf '$ %s\n' "$*"
  "$@" >"$TMPO" 2>&1
  c=$?
  cat "$TMPO"
  printf 'exit=%s\n\n' "$c"
  return $c
}

# ---------------------------------------------------------------- leg 0: fixture
{
  hdr "leg 0 — build the fixture repo (three tree states as real commits)"
  # make-fixture.sh starts with `rm -rf "$ROOT"`, which unlinks $ROOT/.out while
  # run() still holds it open — so leg 0 alone parks its capture file under $LOGS,
  # or the fixture output is lost and the log carries a `cat: … No such file` line.
  TMPO="$LOGS/.out0"; run sh "$FIX/make-fixture.sh"; TMPO="$ROOT/.out"
  printf '$ git -C <repo> remote get-url origin\n'
  git -C "$REPO" remote get-url origin
  printf '\n$ python3 --version ; git --version ; uname -sr\n'
  python3 --version; git --version; uname -sr
} > "$LOGS/fixture.log" 2>&1
rm -f "$LOGS/.out0"
mkdir -p "$ROOT"          # make-fixture.sh rm -rf'd it and rebuilt only $REPO's parents
. "$ROOT/shas.env"
cp "$RUN/0-spec.md" "$ROOT/0-spec.pristine"
EXAM=$(python3 "$S/exam_paths.py" "$REPO" "$RUN" --no-transport \
       | grep '^exam_dir: ' | cut -d' ' -f2)
PTR="${EXAM}.pointer"

# ------------------------------------------------- leg 1: create + the red proof
{
  hdr "leg 1 — kestra-exam Process steps 1-7 against the fixture"
  printf 'KESTRA_EXAMS_ROOT=%s\n' "$KESTRA_EXAMS_ROOT"
  run python3 "$FIX/build-exam.py" create
} > "$LOGS/create.log" 2>&1
cp "$EXAM/red-proof.log" "$LOGS/red-proof.log" 2>/dev/null
cp "$EXAM/red-proof.json" "$LOGS/red-proof.json" 2>/dev/null

# --------------------------------------------------- legs 2-3: green and broken
clone_at() {   # clone_at <sha> <dir>
  rm -rf "$2"
  git clone -q --no-hardlinks "$REPO" "$2" && git -C "$2" checkout -q "$1"
}
{
  hdr "leg 2 — the same exam at the implemented commit (the flip is real)"
  clone_at "$IMPL" "$ROOT/clone-impl"
  printf 'clone at IMPL=%s\n\n' "$IMPL"
  run python3 "$EXAM/exam.py" --repo "$ROOT/clone-impl"
  run python3 "$EXAM/exam.py" --repo "$ROOT/clone-impl" --json
} > "$LOGS/green.log" 2>&1
{
  hdr "leg 3 — the same exam at implemented-broken (non-vacuity)"
  clone_at "$BROKEN" "$ROOT/clone-broken"
  printf 'clone at BROKEN=%s\n\n' "$BROKEN"
  run python3 "$EXAM/exam.py" --repo "$ROOT/clone-broken"
  run python3 "$EXAM/exam.py" --repo "$ROOT/clone-broken" --json
} > "$LOGS/broken.log" 2>&1

# ----------------------------------------- leg 4: C-0 red voids the whole proof
{
  hdr "leg 4 — the seam entry point is gone: C-0 red, everything else blocked"
  clone_at "$IMPL" "$ROOT/clone-nosrc"
  rm -f "$ROOT/clone-nosrc/src/tally.py"
  printf 'removed src/tally.py from the clone at IMPL\n\n'
  run python3 "$EXAM/exam.py" --repo "$ROOT/clone-nosrc"
  run python3 "$EXAM/exam.py" --repo "$ROOT/clone-nosrc" --json
  printf 'NOTE: C-0 red_kind here is `behavioral`, not `infrastructure` — deleting the\n'
  printf 'script still spawns the interpreter, which exits 2, so a Result exists and the\n'
  printf 'seam counts as reached. The void rule keys on C-0 *result*, never on its red\n'
  printf 'kind, so the proof is void either way. Leg 4b reaches the infrastructure arm.\n'
} > "$LOGS/smoke-red.log" 2>&1

# --------------------------------- leg 4b: a genuine infrastructure red
{
  hdr "leg 4b — an unspawnable seam: SeamUnavailable => infrastructure red"
  rm -rf "$ROOT/exam-infra"; cp -R "$EXAM" "$ROOT/exam-infra"
  rm -rf "$ROOT/exam-infra/.git"
  sed 's/argv_prefix=\["python3", "src\/tally.py"\]/argv_prefix=["python3-does-not-exist", "src\/tally.py"]/' \
      "$EXAM/exam.py" > "$ROOT/exam-infra/exam.py"
  printf '$ diff <(exam.py) <(exam-infra/exam.py)\n'
  diff "$EXAM/exam.py" "$ROOT/exam-infra/exam.py"
  printf '\n'
  run python3 "$ROOT/exam-infra/exam.py" --repo "$ROOT/clone-impl"
  run python3 "$ROOT/exam-infra/exam.py" --repo "$ROOT/clone-impl" --json
} > "$LOGS/infra-red.log" 2>&1

# ------------------------------------------------------------ leg 5: every mode
{
  hdr "leg 5 — the six modes and the exit-code ladder"
  run python3 "$EXAM/exam.py" --list
  run python3 "$EXAM/exam.py" --audit-seam
  run python3 "$EXAM/exam.py" --only C-2 --repo "$ROOT/clone-impl" --json
  printf 'NOTE above: --only C-2 ran C-0 as well — C-0 runs regardless of --only.\n\n'
  run python3 "$EXAM/exam.py" --only C-99 --repo "$ROOT/clone-impl"
  run python3 "$EXAM/exam.py" --bogus-flag
  run python3 -O "$EXAM/exam.py" --repo "$ROOT/clone-impl"
  hdr "leg 5b — --audit-seam fails when the manifest's quoted seam does not match"
  rm -rf "$ROOT/exam-auditneg"; cp -R "$EXAM" "$ROOT/exam-auditneg"
  rm -rf "$ROOT/exam-auditneg/.git"
  sed 's|python3 src/tally.py|python3 src/other.py|' "$EXAM/manifest.md" \
      > "$ROOT/exam-auditneg/manifest.md"
  run python3 "$ROOT/exam-auditneg/exam.py" --audit-seam
  hdr "leg 5c — the fixture spec through kestra-build's own spec validator"
  run python3 "$UPSTREAM/workflow/kestra-build/scripts/validate_spec.py" \
      "$RUN/0-spec.md" "$REPO"
} > "$LOGS/modes.log" 2>&1

# ------------------------------------------------------ leg 6: verdict + U>0
{
  hdr "leg 6 — the verdict a gate runner would emit, and its two sharp edges"
  python3 - "$EXAM" "$ROOT/clone-impl" <<'PY'
import hashlib, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
exam, tree = Path(sys.argv[1]), sys.argv[2]
rp = json.loads((exam / "red-proof.json").read_text())
man = (exam / "manifest.md").read_text()
cov = [l for l in man.splitlines() if l.startswith("ACs in surface:")][0]
print("manifest ## Coverage:", cov)
print("red-proof.json summary:", json.dumps(rp["summary"]))
gate = subprocess.run(["python3", str(exam / "exam.py"), "--repo", tree,
                       "--json"], capture_output=True, text=True)
g = json.loads(gate.stdout)
print("gate-run summary:      ", json.dumps(g["summary"]), "exit", gate.returncode)
U = rp["summary"]["unproven"]
F = len([c for c in rp["checks"] if c["class"] == "must-flip"])
unex = [c["ac"] for c in rp["checks"] if c["class"] == "unexaminable"]
M = len({c["ac"] for c in rp["checks"] if c["class"] != "unexaminable"} - {"—"})
N = M + len(unex)
sha = hashlib.sha256((exam / "exam.py").read_bytes()).hexdigest()
ok = (g["smoke"]["result"] == "pass"
      and not any(c["result"] == "fail" for c in g["checks"])
      and not any(c["red_kind"] == "infrastructure" for c in g["checks"]))
verdict = "PASS" if ok else ("BLOCKED" if g["summary"]["exit_code"] == 2 else "FAIL")
block = "\n".join([
    "--- verdict (appended by the gate runner; unfilled above this line) ---",
    f"verdict:   {verdict}",
    f"evidence:  degraded — {U} unproven of {F} must-flip" if U else "evidence:  full",
    f"coverage:  {M}/{N} ACs executably covered; unexaminable: {', '.join(unex)}",
    f"run:       {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} · "
    f"exam.py sha256 {sha[:12]} · exit {g['summary']['exit_code']}"])
print("\n--- the verdict block, computed from the artifacts ---")
print(block)
print("\nSHARP EDGE 1 — which U the evidence clause must use.")
print("  red-proof.json summary.unproven =", U, "(1 born-green must-flip)")
print("  gate-run    summary.unproven =", g["summary"]["unproven"],
      "(every must-flip passes on a green tree)")
print("  A gate reading U from its own run would report `degraded —",
      g["summary"]["unproven"], "unproven of", F, "must-flip` on a perfect delivery.")
print("  exam_harness.summarize's docstring says the manifest's cells come only from")
print("  red-proof.json; gate-procedure.md §6 says `whenever U > 0` without naming which.")
print("\nSHARP EDGE 2 — appending the verdict invalidates the pointer's manifest_sha256.")
before = hashlib.sha256((exam / "manifest.md").read_bytes()).hexdigest()
ptr = dict(l.split(": ", 1) for l in
           (exam.parent / (exam.name + ".pointer")).read_text().splitlines()
           if ": " in l)
after_text = man.rstrip("\n") + "\n" + block + "\n"
after = hashlib.sha256(after_text.encode()).hexdigest()
Path(sys.argv[1] + "/../../../manifest-with-verdict.md").write_text(after_text)
print("  pointer manifest_sha256:", ptr["manifest_sha256"])
print("  sha256 manifest.md now :", before, "(match:", before == ptr["manifest_sha256"], ")")
print("  sha256 after appending :", after, "(match:", after == ptr["manifest_sha256"], ")")
print("  gate-procedure.md §5 reads that mismatch as `the evidence table was edited")
print("  after recording` => refusal. So the first gate run's own append makes every")
print("  later gate run refuse, unless the runner rewrites the pointer after appending.")
PY
  printf '\nexit=%s\n' "$?"
} > "$LOGS/verdict.log" 2>&1
mv "$ROOT/manifest-with-verdict.md" "$LOGS/manifest-with-verdict.md" 2>/dev/null

# --------------------------------------------------- leg 7: staleness refusal
{
  hdr "leg 7 — staleness: one refusal per fail-closed arm, all three fields shown"
  printf -- "--- 7a fresh baseline ---\n"
  run python3 "$EXAM/exam_anchor.py" "$RUN" "$EXAM"

  printf -- "--- 7b an in-surface change: one AC row's Source cell ---\n"
  sed 's/^| AC-1 | US-1 |/| AC-1 | US-1, US-4 |/' "$ROOT/0-spec.pristine" > "$RUN/0-spec.md"
  printf '$ diff <(pristine) <(mutated)\n'; diff "$ROOT/0-spec.pristine" "$RUN/0-spec.md"
  printf '\n'
  run python3 "$EXAM/exam_anchor.py" "$RUN" "$EXAM"

  printf -- "--- 7c out-of-surface changes only: Files to Touch + Out of Scope ---\n"
  sed 's/^| `data\/mixed.csv` |.*/| `data\/mixed.csv` | — (unchanged; the refund row already exists) |/' \
      "$ROOT/0-spec.pristine" > "$RUN/0-spec.md"
  printf 'Also out of scope: a --csv-dialect flag.\n' >> "$RUN/0-spec.md"
  printf '$ diff <(pristine) <(mutated)\n'; diff "$ROOT/0-spec.pristine" "$RUN/0-spec.md"
  printf '\n'
  run python3 "$EXAM/exam_anchor.py" "$RUN" "$EXAM"
  printf 'Both halves of story 21 in one leg: an AC row moves the anchor, the whole\n'
  printf 'provision layer does not.\n\n'
  cp "$ROOT/0-spec.pristine" "$RUN/0-spec.md"

  printf -- "--- 7d anchor copies disagree: the pointer is tampered ---\n"
  cp "$PTR" "$ROOT/pointer.good"
  sed 's/^surface_hash: ./surface_hash: 0/' "$ROOT/pointer.good" > "$PTR"
  run python3 "$EXAM/exam_anchor.py" "$RUN" "$EXAM"

  printf -- "--- 7e the pointer body loses its v1 marker ---\n"
  grep -v 'kestra-exam-pointer v1' "$ROOT/pointer.good" > "$PTR"
  run python3 "$EXAM/exam_anchor.py" "$RUN" "$EXAM"
  cp "$ROOT/pointer.good" "$PTR"

  printf -- "--- 7f a partial anchor: manifest raise_commit truncated ---\n"
  cp "$EXAM/manifest.md" "$ROOT/manifest.good"
  sed 's/^| raise_commit | \(........\).*/| raise_commit | \1 |/' "$ROOT/manifest.good" \
      > "$EXAM/manifest.md"
  run python3 "$EXAM/exam_anchor.py" "$RUN" "$EXAM"
  cp "$ROOT/manifest.good" "$EXAM/manifest.md"

  printf -- "--- 7g exam.py's own ANCHOR disagrees with the manifest ---\n"
  cp "$EXAM/exam.py" "$ROOT/exam.good"
  sed 's/"raise_commit": "./"raise_commit": "0/' "$ROOT/exam.good" > "$EXAM/exam.py"
  run python3 "$EXAM/exam_anchor.py" "$RUN" "$EXAM"
  cp "$ROOT/exam.good" "$EXAM/exam.py"

  printf -- "--- 7h the extractor resolves nowhere (all four candidates) ---\n"
  mv "$EXAM/requirement_surface.py" "$ROOT/requirement_surface.away"
  mkdir -p "$ROOT/fakehome"
  printf '$ HOME=%s python3 exam_anchor.py <run> <exam>\n' "$ROOT/fakehome"
  HOME="$ROOT/fakehome" python3 "$EXAM/exam_anchor.py" "$RUN" "$EXAM" 2>&1
  printf 'exit=%s\n\n' "$?"
  mv "$ROOT/requirement_surface.away" "$EXAM/requirement_surface.py"

  printf -- "--- 7i back to fresh, nothing left mutated ---\n"
  run python3 "$EXAM/exam_anchor.py" "$RUN" "$EXAM"
} > "$LOGS/stale-anchor.log" 2>&1

# ------------------------------------ leg 8: the four delta scopes + a regen
{
  hdr "leg 8 — exam_delta's four scopes, then a real delta regeneration"
  printf -- "--- 8a nothing moved ---\n"
  run python3 "$S/exam_delta.py" "$RUN" "$EXAM"

  printf -- "--- 8b prose the ACs paraphrase moved (Edge Cases) => re-anchor ---\n"
  sed 's/^- A CSV with a header and no data rows tallies/- A CSV whose header has no data rows tallies/' \
      "$ROOT/0-spec.pristine" > "$RUN/0-spec.md"
  diff "$ROOT/0-spec.pristine" "$RUN/0-spec.md"
  run python3 "$S/exam_delta.py" "$RUN" "$EXAM"

  printf -- "--- 8c the declared seam moved (External Interface) => full ---\n"
  sed 's|^python3 src/tally.py \[--refund\] <csv-path>|python3 src/tally.py [--refund] [--json] <csv-path>|' \
      "$ROOT/0-spec.pristine" > "$RUN/0-spec.md"
  diff "$ROOT/0-spec.pristine" "$RUN/0-spec.md"
  run python3 "$S/exam_delta.py" "$RUN" "$EXAM"

  printf -- "--- 8d one AC row moved => delta, and only its check regenerates ---\n"
  sed 's/^| AC-1 | US-1 |/| AC-1 | US-1, US-4 |/' "$ROOT/0-spec.pristine" > "$RUN/0-spec.md"
  diff "$ROOT/0-spec.pristine" "$RUN/0-spec.md"
  run python3 "$S/exam_delta.py" "$RUN" "$EXAM"

  printf -- "--- 8e FINDING: the map is a byte match, so a decorated AC cell silently\n"
  printf -- "    under-regenerates. Same spec change, one manifest whose AC column reads\n"
  printf -- "    'AC-1 — refund subtraction' instead of 'AC-1'. ---\n"
  rm -rf "$ROOT/exam-decorated"; cp -R "$EXAM" "$ROOT/exam-decorated"
  rm -rf "$ROOT/exam-decorated/.git"
  sed 's/^| AC-1 | C-1 |/| AC-1 — refund subtraction | C-1 |/' "$EXAM/manifest.md" \
      > "$ROOT/exam-decorated/manifest.md"
  diff "$EXAM/manifest.md" "$ROOT/exam-decorated/manifest.md"
  run python3 "$S/exam_delta.py" "$RUN" "$ROOT/exam-decorated"
  printf 'scope is still delta and the AC is still reported changed, but `regenerate:`\n'
  printf 'is empty — the AC->check map missed, so nothing would be re-proved. The\n'
  printf 'manifest AC cell must be a byte match for the spec Coverage Map AC cell.\n\n'

  printf -- "--- 8f the delta regeneration itself (SKILL.md §Regeneration) ---\n"
  run python3 "$FIX/build-exam.py" regenerate
  printf -- "--- 8g the regeneration is a bounded diff in the exam dir ---\n"
  printf '$ git -C <exam-dir> log --oneline\n'; git -C "$EXAM" log --oneline
  printf '\n$ git -C <exam-dir> diff --stat HEAD~1 HEAD\n'
  git -C "$EXAM" diff --stat HEAD~1 HEAD
  printf '\n$ git -C <exam-dir> diff HEAD~1 HEAD -- manifest.md exam.py\n'
  git -C "$EXAM" diff HEAD~1 HEAD -- manifest.md exam.py
  printf '\n$ git -C <exam-dir> remote\n'; git -C "$EXAM" remote
  printf '(empty)\n\n'
  printf -- "--- 8h the exam still runs, and the anchor is fresh at generation 2 ---\n"
  run python3 "$EXAM/exam.py" --repo "$ROOT/clone-impl"
  run python3 "$EXAM/exam_anchor.py" "$RUN" "$EXAM"
  run python3 "$S/exam_delta.py" "$RUN" "$EXAM"
} > "$LOGS/delta-regen.log" 2>&1

# ------------------------------------------------------- leg 9: pointer discipline
{
  hdr "leg 9 — one pointer record, edited in place; >1 is a hard fail"
  printf '$ cat <slug>.pointer\n'; cat "$PTR"
  printf '\n$ cat <slug>.pointer.log\n'; cat "${PTR}.log"
  printf '\ngeneration in the body and one appended log line per regeneration; the file\n'
  printf 'itself was rewritten, never duplicated.\n\n'
  printf '$ sha256sum exam.py manifest.md   (vs the two hashes in the pointer body)\n'
  shasum -a 256 "$EXAM/exam.py" "$EXAM/manifest.md"
  printf '\n'
  printf -- "--- 9a the design's multiplicity glob, as written ---\n"
  printf '$ ls <exams-root>/<key>/tally-refund.pointer*\n'
  ls "$EXAM".pointer* | while IFS= read -r f; do echo "$f"; done
  printf 'matches=%s\n' "$(ls "$EXAM".pointer* | wc -l | tr -d ' ')"
  printf 'FINDING: the glob in gate-procedure.md §4 matches `<slug>.pointer.log` too, so\n'
  printf 'the very first regeneration makes the multiplicity check report 2 and hard-fail\n'
  printf 'a healthy exam. The predicate has to exclude the .log sibling.\n\n'
  printf -- "--- 9b plant a second pointer ---\n"
  cp "$PTR" "${PTR}.bak"
  printf '$ ls <slug>.pointer* (excluding the .log sibling)\n'
  ls "$EXAM".pointer* | grep -v '\.pointer\.log$'
  n=$(ls "$EXAM".pointer* | grep -vc '\.pointer\.log$')
  printf 'matches=%s\n\n' "$n"
  cat <<EOF
FAIL: $n pointer records titled 'kestra-exam: tally-refund' ($(ls "$EXAM".pointer* | grep -v '\.pointer\.log$' | tr '\n' ' ')) — ambiguous by
construction. A regeneration edits the existing pointer in place; a second record is
forgery or confusion, and picking the newer one crowns the forgery. Close or retitle
the wrong one by hand, then re-run. Never auto-select, never take the newest.
EOF
  printf '\n(the local-transport form of the >1 hard fail: paths in place of issue\n'
  printf 'numbers, same text, same never-take-the-newest.)\n\n'
  printf -- "--- 9c newest-wins is refused, not applied ---\n"
  printf '$ ls -t <slug>.pointer* | head -1     # what recency WOULD pick\n'
  ls -t "$EXAM".pointer* | grep -v '\.pointer\.log$' | head -1
  printf '\n'
  rm -f "${PTR}.bak"
  printf -- "--- 9d back to exactly one ---\n"
  n=$(ls "$EXAM".pointer* | grep -vc '\.pointer\.log$')
  printf 'matches=%s\n' "$n"
} > "$LOGS/pointer-duplicate.log" 2>&1

# -------------------------------------------------------- leg 10: the hard stops
{
  hdr "leg 10 — origin keying and its hard stops (nothing is created)"
  printf -- "--- 10a the fixture origin keys cleanly ---\n"
  run python3 "$S/exam_paths.py" "$REPO" "$RUN"
  printf -- "--- 10b no origin remote at all ---\n"
  rm -rf "$ROOT/clone-noorigin"
  git clone -q --no-hardlinks "$REPO" "$ROOT/clone-noorigin"
  git -C "$ROOT/clone-noorigin" remote remove origin
  KESTRA_EXAMS_ROOT="$ROOT/exams-noorigin" \
    python3 "$S/exam_paths.py" "$ROOT/clone-noorigin" "$RUN" 2>&1
  printf 'exit=%s\n' "$?"
  printf '$ test ! -d %s ; echo $?\n' "$ROOT/exams-noorigin"
  test ! -d "$ROOT/exams-noorigin"; printf '%s (0 = nothing was created)\n\n' "$?"
  printf -- "--- 10c a file:// origin cannot be keyed (it has no host) ---\n"
  git -C "$ROOT/clone-noorigin" remote add origin "file://$ROOT/origin.git"
  KESTRA_EXAMS_ROOT="$ROOT/exams-noorigin" \
    python3 "$S/exam_paths.py" "$ROOT/clone-noorigin" "$RUN" 2>&1
  printf 'exit=%s\n\n' "$?"
  printf -- "--- 10d a bare local path origin, same stop ---\n"
  git -C "$ROOT/clone-noorigin" remote set-url origin "$ROOT/origin.git"
  KESTRA_EXAMS_ROOT="$ROOT/exams-noorigin" \
    python3 "$S/exam_paths.py" "$ROOT/clone-noorigin" "$RUN" 2>&1
  printf 'exit=%s\n\n' "$?"
  printf 'CONSEQUENCE for this eval: the fixture origin must be host-shaped with >=2\n'
  printf 'path segments, so it is https://git.example.test/kx-fixture/tally.git — a URL\n'
  printf 'that is never contacted (no fetch, no push, local transport).\n\n'
  printf -- "--- 10e a run folder whose basename is not a usable slug ---\n"
  mkdir -p "$REPO/workflows/runs/Tally_Refund"
  run python3 "$S/exam_paths.py" "$REPO" "$REPO/workflows/runs/Tally_Refund"
  rmdir "$REPO/workflows/runs/Tally_Refund"
  printf -- "--- 10f the exam repo has grown a remote ---\n"
  git -C "$EXAM" remote add origin https://git.example.test/leak/exams.git
  run python3 "$S/exam_paths.py" "$REPO" "$RUN"
  git -C "$EXAM" remote remove origin
  printf -- "--- 10g origin keying on six URL forms + the nested-group collision ---\n"
  run python3 "$FIX/keying.py"
} > "$LOGS/no-origin.log" 2>&1

# ---------------------------------------------------- leg 11: the harness's tests
{
  hdr "leg 11 — the skill's own tests and py_compile"
  run python3 "$S/test_exam_harness.py"
  # py_compile with the .pyc redirected out of the repo — the check is the exit
  # code, and the default cfile would litter the skill's scripts/ directory.
  mkdir -p "$ROOT/pyc"
  printf '$ python3 -m py_compile-equivalent (cfile redirected to %s)\n' "$ROOT/pyc"
  OUT="$ROOT/pyc" python3 -c 'import os,py_compile,sys
d=os.environ["OUT"]
for f in sys.argv[1:]:
    py_compile.compile(f, cfile=os.path.join(d, os.path.basename(f)+"c"), doraise=True)
print("compiled", len(sys.argv)-1, "files")' \
      "$S/exam_harness.py" "$S/exam_paths.py" "$S/exam_anchor.py" \
      "$S/exam_delta.py" "$S/test_exam_harness.py" "$FIX/build-exam.py" \
      "$FIX/keying.py" "$EXAM/exam.py"
  printf 'compile exit=%s\n\n' "$?"
  printf 'line counts (wc -l):\n'
  wc -l "$UPSTREAM/workflow/kestra-exam/SKILL.md" \
        "$UPSTREAM/workflow/kestra-exam"/references/*.md \
        "$S"/*.py "$EXAM/exam.py" "$EXAM/manifest.md"
} > "$LOGS/harness-tests.log" 2>&1

# --------------------------------------------------------------- leg 12: sweeps
{
  hdr "leg 12 — the leak sweeps (token built at run time, every grep is -q)"
  printf 'exit semantics: 1 = clean, 0 = a hit, >=2 = the check itself failed.\n\n'
  EX1=':(exclude).claude/skills/kestra-exam/*'
  EX2=':(exclude)workflow/kestra-exam/*'
  printf -- "--- 12a S1 on this repo, WITHOUT the two path exemptions ---\n"
  printf '$ git grep -q --untracked "$TOK" -- .\n'
  git -C "$UPSTREAM" grep -q --untracked "$TOK" -- . ; printf 'exit=%s (0 = hit)\n\n' "$?"
  printf -- "--- 12b S1 with the exemption boundary (the two skill paths) ---\n"
  printf '$ git grep -q --untracked "$TOK" -- . ":(exclude).claude/skills/kestra-exam/*" ":(exclude)workflow/kestra-exam/*"\n'
  git -C "$UPSTREAM" grep -q --untracked "$TOK" -- . "$EX1" "$EX2"
  printf 'exit=%s (1 = clean)\n\n' "$?"
  printf 'So the exemption is load-bearing: the skill documents the path it forbids\n'
  printf 'elsewhere, and nothing outside those two paths carries the token — including\n'
  printf 'this eval, which builds the token at run time for exactly that reason.\n\n'
  printf -- "--- 12c S2, commit messages, no exemption at all ---\n"
  printf '$ git log --all --grep="$TOK" --oneline | wc -l\n'
  git -C "$UPSTREAM" log --all --grep="$TOK" --oneline | wc -l
  printf '\n'
  printf -- "--- 12d S3, history blobs: zsh unwrapped vs sh -c ---\n"
  printf '$ zsh -c <the recipe as written, unwrapped: unquoted $revs>\n'
  zsh -c 'cd "'"$UPSTREAM"'"; revs=$(git rev-list --all); git grep -q "'"$TOK"'" $revs -- . 2>&1 | head -1 | cut -c1-110'
  zsh -c 'cd "'"$UPSTREAM"'"; revs=$(git rev-list --all); git grep -q "'"$TOK"'" $revs -- . >/dev/null 2>&1; echo "exit=$? (>=2: the check itself failed, so it never ran)"'
  printf '$ sh -c <the same recipe, guarded and wrapped>\n'
  sh -c 'cd "'"$UPSTREAM"'"; revs=$(git rev-list --all)
         [ -n "$revs" ] || { echo "FAIL: no commits — the blob sweep did not run"; exit 9; }
         git grep -q "'"$TOK"'" $revs -- . "'"$EX1"'" "'"$EX2"'"; echo "exit=$? (1 = clean, 0 = a hit)"'
  printf '\n'
  printf -- "--- 12d-note FINDING: S3 hits on THIS repo while S1 reports clean, because\n"
  printf -- "    the token sits in two TRACKED files that \`--untracked\` silently skips.\n"
  printf -- "    S3's hit list, paths only, and the commit that added them: ---\n"
  sh -c 'cd "'"$UPSTREAM"'"; revs=$(git rev-list --all)
         git grep -l "'"$TOK"'" $revs -- . "'"$EX1"'" "'"$EX2"'" | cut -d: -f2- | sort -u'
  git -C "$UPSTREAM" log --oneline --diff-filter=A -- idea/flow-final.excalidraw idea/flow-final.svg
  printf '\n$ git grep -l "$TOK" -- idea/                              # tracked-only\n'
  git -C "$UPSTREAM" grep -l "$TOK" -- idea/; printf 'exit=%s (0 = hit)\n' "$?"
  printf '$ git grep -l --untracked "$TOK" -- idea/                  # S1 as written\n'
  git -C "$UPSTREAM" grep -l --untracked "$TOK" -- idea/; printf 'exit=%s (1 = a FALSE clean)\n' "$?"
  printf '$ git grep -l --untracked --no-exclude-standard "$TOK" -- idea/\n'
  git -C "$UPSTREAM" grep -l --untracked --no-exclude-standard "$TOK" -- idea/
  printf 'exit=%s (0 = hit, reached again)\n' "$?"
  printf '$ git ls-files -v idea/flow-final.svg          # H = tracked, not untracked\n'
  git -C "$UPSTREAM" ls-files -v idea/flow-final.svg
  printf '$ git check-ignore --no-index -v idea/flow-final.svg\n'
  git -C "$UPSTREAM" check-ignore --no-index -v idea/flow-final.svg
  printf '\nMechanism, measured end to end: `idea/` is listed in this repo`s local\n'
  printf '.git/info/exclude, and the two files are tracked anyway (H). `--untracked`\n'
  printf 'implies --exclude-standard, whose walk skips excluded paths *including tracked\n'
  printf 'ones*, so S1 never reads them. `git check-ignore` without --no-index reports\n'
  printf 'them as NOT ignored (it assumes tracked == not ignored), which is why the\n'
  printf 'condition is easy to miss by hand.\n\n'
  printf 'Consequence for the recipe, sharper than the residual as written: the residual\n'
  printf 'says --untracked skips gitignored files. Measured, it also skips TRACKED files\n'
  printf 'under an exclude rule, so S1 can report clean over a committed leak. S1 needs\n'
  printf 'either --no-exclude-standard (accepting node_modules noise) or a second pass\n'
  printf 'without --untracked; and on this repo S3 cannot pass until the two diagram\n'
  printf 'exports are re-exported without the path or added to the exemption list.\n\n'
  printf -- "--- 12e the case S3 exists for: a leak committed at N, removed at N+2 ---\n"
  LK="$ROOT/leakrepo"; rm -rf "$LK"; mkdir -p "$LK"
  G="git -c user.name=eval -c user.email=eval@example.test"
  $G init -q -b main "$LK"
  printf 'clean\n' > "$LK/a.md"; $G -C "$LK" add -A; $G -C "$LK" commit -q -m "N-1 clean"
  printf 'see $HOME/.%s/<key>/<slug>/ for the exam\n' "$TOK" > "$LK/b.md"
  $G -C "$LK" add -A; $G -C "$LK" commit -q -m "N adds a leaking path"
  printf 'clean again\n' > "$LK/b.md"; $G -C "$LK" add -A
  $G -C "$LK" commit -q -m "N+1 rewrites the file"
  $G -C "$LK" commit -q --allow-empty -m "N+2 unrelated"
  printf '$ git -C <leakrepo> grep -q --untracked "$TOK" -- .        # S1\n'
  git -C "$LK" grep -q --untracked "$TOK" -- .; printf 'exit=%s (1 = clean worktree)\n' "$?"
  printf '$ git -C <leakrepo> log --all --grep="$TOK" --oneline | wc -l   # S2\n'
  git -C "$LK" log --all --grep="$TOK" --oneline | wc -l
  printf '$ sh -c <S3 guarded> in <leakrepo>\n'
  sh -c 'cd "'"$LK"'"; revs=$(git rev-list --all)
         [ -n "$revs" ] || { echo "FAIL: no commits — the blob sweep did not run"; exit 9; }
         git grep -q "'"$TOK"'" $revs -- .; echo "exit=$? (0 = HIT: the blob is still in history)"'
  printf '\n'
  printf -- "--- 12f the same leak inside an exempt path stays clean under S3 ---\n"
  LK2="$ROOT/leakrepo-exempt"; rm -rf "$LK2"; mkdir -p "$LK2/workflow/kestra-exam"
  $G init -q -b main "$LK2"
  printf 'see $HOME/.%s/<key>/<slug>/ for the exam\n' "$TOK" > "$LK2/workflow/kestra-exam/SKILL.md"
  $G -C "$LK2" add -A; $G -C "$LK2" commit -q -m "the skill documents its own path"
  sh -c 'cd "'"$LK2"'"; revs=$(git rev-list --all)
         git grep -q "'"$TOK"'" $revs -- . "'"$EX2"'"; echo "S3 with exemption exit=$? (1 = clean)"
         git grep -q "'"$TOK"'" $revs -- .; echo "S3 without exemption exit=$? (0 = hit)"'
  printf '\n'
  printf -- "--- 12g the skill name never self-hits ---\n"
  printf '$ printf "kestra-exam skill" | grep -c "$TOK"\n'
  printf 'kestra-exam skill' | grep -c "$TOK"; printf 'grep exit=%s\n\n' "$?"
  printf -- "--- 12h S4: not applicable to this fixture, and why ---\n"
  printf 'the fixture origin is git.example.test, so exam_paths.transport() returns\n'
  printf '`local` and there is no chain tracker to sweep. The GitHub read predicates are\n'
  printf 'measured read-only below, against the real trackers.\n\n'
  run gh auth status
  printf '$ gh issue list --repo arkaphat/kestra --label kestra-exam --state all --limit 100 --json number,title,url --jq "[.[]|select(.title==\\"kestra-exam: tally-refund\\")]|length"\n'
  gh issue list --repo arkaphat/kestra --label kestra-exam --state all --limit 100 \
     --json number,title,url \
     --jq '[.[]|select(.title=="kestra-exam: tally-refund")]|length' 2>&1
  printf 'exit=%s\n\n' "$?"
  printf '$ gh issue list --repo arkaphat/arkaphat-builder --state all --limit 5 --search "$TOK" --json number --jq "[.[]|.number]"\n'
  gh issue list --repo arkaphat/arkaphat-builder --state all --limit 5 --search "$TOK" \
     --json number --jq '[.[]|.number]' 2>&1
  printf 'exit=%s\n' "$?"
  printf '(design-tracker hits, which is why D5 bounds the sweep to the chain tracker.)\n\n'
  printf -- "--- 12i this eval directory carries no occurrence of the token ---\n"
  printf '$ grep -rc "$TOK" <eval-dir> | grep -v ":0" | wc -l\n'
  grep -rc "$TOK" "$EVAL_DIR" 2>/dev/null | grep -v ':0$' | wc -l
  printf '(0 files with a non-zero count)\n'
} > "$LOGS/sweeps.log" 2>&1

# ------------------------------------------------------------- leg 13: installer
{
  hdr "leg 13 — the installer's SKILLS array and a --project install"
  printf '$ grep -n "kestra-" %s/install.sh\n' "$UPSTREAM"
  grep -n 'kestra-' "$UPSTREAM/install.sh"
  printf '\nWhether the SKILLS array lists kestra-exam decides whether install.sh can carry\n'
  printf 'it at all: a skill not listed there is invisible to the installer. The grep above\n'
  printf 'is the whole evidence and the test below is the consequence — this leg measures\n'
  printf 'the array rather than asserting a state, because the entry is owned by another\n'
  printf 'agent and moved during the wave. First measured 2026-08-02 with the entry absent\n'
  printf '(`test -d` = 1); re-run 2026-08-02 after the entry landed.\n\n'
  rm -rf "$ROOT/projinstall"; mkdir -p "$ROOT/projinstall"
  # bash, not sh: install.sh is a bash script (arrays, process substitution) and
  # `sh install.sh` dies at line 202 on `< <(find …)` — a harness error, not a
  # repo defect, and worth naming so nobody records it as one.
  run bash "$UPSTREAM/install.sh" --project "$ROOT/projinstall"
  printf '$ ls %s/.claude/skills\n' "$ROOT/projinstall"
  ls "$ROOT/projinstall/.claude/skills" 2>&1
  printf '\n$ test -d %s/.claude/skills/kestra-exam ; echo $?\n' "$ROOT/projinstall"
  test -d "$ROOT/projinstall/.claude/skills/kestra-exam"; printf '%s (0 = installed, 1 = absent)\n' "$?"
  printf '$ ls %s/.claude/skills | wc -l\n' "$ROOT/projinstall"
  ls "$ROOT/projinstall/.claude/skills" | wc -l
} > "$LOGS/install.log" 2>&1

# ------------------------------------------------------------- leg 14: wall times
{
  hdr "leg 14 — what the exam costs to run (wall time, this machine)"
  printf '$ time python3 exam.py --repo <clone-impl>          # 7 checks, 6 spawns\n'
  { time python3 "$EXAM/exam.py" --repo "$ROOT/clone-impl" >/dev/null 2>&1 ; } 2>&1
  printf '\n$ time python3 exam.py --only C-1 --repo <clone-impl>   # delta subset + C-0\n'
  { time python3 "$EXAM/exam.py" --only C-1 --repo "$ROOT/clone-impl" >/dev/null 2>&1 ; } 2>&1
  printf '\n$ time (git clone --no-hardlinks + checkout <raise>)   # the red-proof clone\n'
  rm -rf "$ROOT/clone-timing"
  { time clone_at "$RAISE" "$ROOT/clone-timing" ; } 2>&1
  printf '\n$ time python3 exam_anchor.py <run> <exam>\n'
  { time python3 "$EXAM/exam_anchor.py" "$RUN" "$EXAM" >/dev/null 2>&1 ; } 2>&1
  printf '\n$ time python3 exam_delta.py <run> <exam>\n'
  { time python3 "$S/exam_delta.py" "$RUN" "$EXAM" >/dev/null 2>&1 ; } 2>&1
  printf '\n$ time python3 test_exam_harness.py\n'
  { time python3 "$S/test_exam_harness.py" >/dev/null 2>&1 ; } 2>&1
  printf '\n$ time <S1 with exemptions>\n'
  { time git -C "$UPSTREAM" grep -q --untracked "$TOK" -- . \
      ':(exclude).claude/skills/kestra-exam/*' ':(exclude)workflow/kestra-exam/*' ; } 2>&1
  printf '\n$ time <S3 guarded, under sh -c>\n'
  { time sh -c 'cd "'"$UPSTREAM"'"; revs=$(git rev-list --all)
       git grep -q "'"$TOK"'" $revs -- . ":(exclude).claude/skills/kestra-exam/*" ":(exclude)workflow/kestra-exam/*"' ; } 2>&1
  printf '\nrecorded durations from the JSON artifacts (harness-measured, not wall):\n'
  python3 - "$EXAM" <<'PY'
import json, sys
from pathlib import Path
rp = json.loads((Path(sys.argv[1]) / "red-proof.json").read_text())
print("  red-proof.json duration_s:", rp["duration_s"],
      "· per-check:", {c["id"]: c["duration_s"] for c in rp["checks"]})
print("  red-proof generations:", rp["generations"])
PY
} > "$LOGS/timings.log" 2>&1

# ------------------------------------------------- copy the artifacts as evidence
for f in exam.py manifest.md red-proof.json red-proof.log; do
  cp "$EXAM/$f" "$EVAL_DIR/exam/$f"
done
cp "$PTR" "$EVAL_DIR/exam/tally-refund.pointer"
cp "${PTR}.log" "$EVAL_DIR/exam/tally-refund.pointer.log"
git -C "$EXAM" show HEAD~1:manifest.md > "$EVAL_DIR/exam/manifest-gen1.md"
git -C "$EXAM" log --stat > "$EVAL_DIR/exam/git-log.txt"
{
  printf '# what is in this directory\n\n'
  printf 'Byte copies of the exam dir as the eval left it (generation 2), taken from\n'
  printf '`$KX_ROOT/exams/<origin-key>/tally-refund/`. `manifest-gen1.md` is\n'
  printf '`git show HEAD~1:manifest.md` from the exam dir, i.e. generation 1 —\n'
  printf 'the exam dir is its own git repo, so its history is the generation history.\n'
  printf '`git-log.txt` is that log. The pointer pair are siblings of the exam dir,\n'
  printf 'never inside it.\n\nNot copied: exam_harness.py, exam_anchor.py and\n'
  printf 'requirement_surface.py, which are byte copies of the skill files already in\n'
  printf 'this repo (verified in logs/harness-tests.log).\n'
} > "$EVAL_DIR/exam/README.md"

echo "legs complete; logs in $LOGS"
ls -la "$LOGS"
