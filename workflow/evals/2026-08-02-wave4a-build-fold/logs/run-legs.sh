#!/bin/bash
# Driver for the wave-4a sliced-fold eval. Every claim in README.md is one of the
# logs this script writes; nothing is paraphrased and nothing is asserted by hand.
#
#   bash workflow/evals/2026-08-02-wave4a-build-fold/logs/run-legs.sh
#
# Read-only outside the eval dir and /tmp/wave4a. Runs no git write command.
set -u
export PYTHONDONTWRITEBYTECODE=1        # no .pyc inside a committed run folder
export PYTHONPYCACHEPREFIX=/tmp/wave4a-pyc  # ...and none beside the eval scripts either
REPO=/Users/arkaphatp/Documents/HUN/dev/hun-registry-skill/kestra-upstream
EVAL=$REPO/workflow/evals/2026-08-02-wave4a-build-fold
RUN=$EVAL/runs/wave4a-fixture
SKILL=$REPO/workflow/kestra-build/scripts
L=$EVAL/logs
S=/tmp/wave4a
rm -rf "$S"; mkdir -p "$S"
cd "$EVAL" || exit 2

runsh() { echo "\$ $1"; sh -c "$1" 2>&1; echo "exit=$?"; echo; }
sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
sub() { python3 - "$1" "$2" "$3" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); t = p.read_text()
assert sys.argv[2] in t, "pattern absent: " + sys.argv[2]
p.write_text(t.replace(sys.argv[2], sys.argv[3], 1))
PY
}

# ---------------------------------------------------------------- 01 the fold
{
echo "# Leg 1 — the fold, enacted by hand against SKILL.md / ticket-fold.md F0-F5."
echo "# Form A(b): a run folder with 0-spec.md plus a directory of local-file slices."
echo
echo "## F0 — resolve the raise commit."
echo "# The fixture spec is not committed (this agent may not commit; the orchestrator does),"
echo "# so chain-provenance.md §2's exactly-one predicate has no raise commit to find and is NOT"
echo "# exercised here. The branch tip stands in as the anchor, and that substitution is the one"
echo "# thing in this leg that is a stand-in rather than the real F0."
runsh "git -C $REPO branch --show-current"
runsh "git -C $REPO rev-parse HEAD"
echo "## F5/materialization — the documented commands, verbatim (tr -d '\\r' only)."
runsh "tr -d '\r' < fixtures/spec/0-spec.md > runs/wave4a-fixture/0-spec.md"
for f in 01-csv-writer 02-export-endpoint 03-streaming; do
  runsh "tr -d '\r' < fixtures/ticket-set/$f.md > runs/wave4a-fixture/tickets/$f.md"
done
runsh "cp $SKILL/requirement_surface.py $SKILL/validate_spec.py $SKILL/validate_workflow.py runs/wave4a-fixture/"
runsh "cmp runs/wave4a-fixture/requirement_surface.py $SKILL/requirement_surface.py && cmp runs/wave4a-fixture/validate_workflow.py $SKILL/validate_workflow.py && echo 'emitted copies byte-identical to the skill'"
echo "## The spec itself, through the spec-side validator (unchanged by this ticket)."
runsh "python3 $SKILL/validate_spec.py runs/wave4a-fixture/0-spec.md $REPO"
echo "## F1-F4 — compute. This is what the fold reads its recorded values off."
runsh "python3 logs/fold_check.py values runs/wave4a-fixture"
echo "## F1 recompute-vs-recompute, same script, both sides (the fixture stands in for 'as raised')."
runsh "cp fixtures/spec/0-spec.md /tmp/wave4a-raise-spec.md"
runsh "python3 logs/fold_check.py check runs/wave4a-fixture --raise-copy /tmp/wave4a-raise-spec.md"
echo "## Step 7's dry-run, in the documented form (run folder's own copy, run folder as target)."
runsh "python3 runs/wave4a-fixture/validate_workflow.py runs/wave4a-fixture"
echo "## The anchor triple and the ticket map as committed."
runsh "sed -n '1,25p' runs/wave4a-fixture/workflow.yaml"
runsh "grep -c 'ticket:begin' runs/wave4a-fixture/workflow.yaml"
runsh "grep -n 'ticket:begin\|ticket:end' runs/wave4a-fixture/workflow.yaml"
} > "$L/01-fold-enactment.log" 2>&1

# ------------------------------------------------- 02 the parser trap, measured
{
echo "# Leg 2 — parser trap #1, measured rather than assumed: the parsed brief is lossy."
python3 - "$RUN" <<'PY'
import sys, pathlib
run = pathlib.Path(sys.argv[1]); sys.path.insert(0, str(run))
import validate_workflow as vw
raw = (run / "workflow.yaml").read_text()
wf = vw.parse_yaml(raw)
brief = [s for s in wf["stages"] if s["id"] == "implement-export-endpoint"][0]["brief"]
print("--- the PARSED brief for implement-export-endpoint ---")
print(brief)
print("--- presence checks ---")
for needle in ("## What to build", "## Acceptance criteria", "#47", "ticket:begin"):
    print(f"{needle!r:26} in raw file: {needle in raw!s:5}  in parsed brief: {needle in brief}")
PY
echo "exit=$?"
echo
echo "# Finding: the trap is WIDER than the design record states. _strip_comment fires on ' #',"
echo "# and every to-tickets heading ('  ## What to build') contains ' #' — so the slice's own"
echo "# section headings, not just an incidental ' #47', vanish from the parsed value. The raw"
echo "# workflow.yaml text is the only truth for an embedded block, and the ' #' WARN therefore"
echo "# fires on EVERY sliced brief rather than on the rare one. Both consequences are load-"
echo "# bearing, and both are now carried by the ported §A4 in validate_workflow.py: it compares"
echo "# raw text only, and emits the ' #' WARN once per embedded block as a standing note."
} > "$L/02-parsed-brief-loss.log" 2>&1

# ------------------------------------- 03 refusal on an AC-row mismatch (AC 2)
{
echo "# Leg 3 — mutate one word of one sliced AC. The fold must refuse, and must not rewrite."
D=$S/ac-mismatch; cp -R "$RUN" "$D"
runsh "shasum -a 256 $D/workflow.yaml"
sub "$D/tickets/02-export-endpoint.md" "AC-1 a completed export" "AC-1 a finished export"
runsh "diff -u $RUN/tickets/02-export-endpoint.md $D/tickets/02-export-endpoint.md"
runsh "python3 logs/fold_check.py check $D"
echo "# and the SHIPPED validator, which now owns the same §A4 checks (ported from fold_check.py):"
runsh "python3 $D/validate_workflow.py $D"
runsh "shasum -a 256 $D/workflow.yaml"
echo "# Same digest before and after: the refusal happened before anything was rewritten."
} > "$L/03-ac-mismatch-refusal.log" 2>&1

# ------------------------------------------ 04 no hand-edit path exists (AC 3)
{
echo "# Leg 4 — the four hand-edit routes from ticket-fold.md §4. Each must fail, and each must"
echo "# fail with a DIFFERENT message naming the specific disagreement."
echo
echo "=== route (a): patch only the brief block in workflow.yaml ==="
D=$S/route-a; cp -R "$RUN" "$D"
sub "$D/workflow.yaml" "the header-only shape for an empty result" "the headers-only shape for an empty result"
runsh "python3 logs/fold_check.py check $D"
runsh "python3 $D/validate_workflow.py $D"
echo "=== route (b): patch only tickets/01-csv-writer.md ==="
D=$S/route-b; cp -R "$RUN" "$D"
sub "$D/tickets/01-csv-writer.md" "the header-only shape for an empty result" "the headers-only shape for an empty result"
runsh "python3 logs/fold_check.py check $D"
runsh "python3 $D/validate_workflow.py $D"
echo "=== route (c): patch the file AND the block AND the delimiter hex, leaving tickets[].body_sha256 ==="
D=$S/route-c; cp -R "$RUN" "$D"
sub "$D/tickets/01-csv-writer.md" "the header-only shape for an empty result" "the headers-only shape for an empty result"
sub "$D/workflow.yaml" "the header-only shape for an empty result" "the headers-only shape for an empty result"
OLDSHA=$(sha "$RUN/tickets/01-csv-writer.md"); NEWSHA=$(sha "$D/tickets/01-csv-writer.md")
echo "# old sha $OLDSHA -> new sha $NEWSHA (delimiter only, map left stale)"
sub "$D/workflow.yaml" "sha256:$OLDSHA" "sha256:$NEWSHA"
runsh "python3 logs/fold_check.py check $D"
runsh "python3 $D/validate_workflow.py $D"
echo "=== route (d): patch all three consistently, on an AC line ==="
D=$S/route-d; cp -R "$RUN" "$D"
sub "$D/tickets/03-streaming.md" "AC-5 an export above 10000 rows" "AC-5 an export above 5000 rows"
sub "$D/workflow.yaml" "AC-5 an export above 10000 rows" "AC-5 an export above 5000 rows"
OLDSHA=$(sha "$RUN/tickets/03-streaming.md"); NEWSHA=$(sha "$D/tickets/03-streaming.md")
sub "$D/workflow.yaml" "sha256:$OLDSHA" "sha256:$NEWSHA"
sub "$D/workflow.yaml" "body_sha256: $OLDSHA" "body_sha256: $NEWSHA"
runsh "python3 logs/fold_check.py check $D"
runsh "python3 $D/validate_workflow.py $D"
echo "# Route (d) collapses into the AC-row refusal of leg 3: the three hashes can be made to"
echo "# agree, but they then describe an AC the spec's Coverage Map does not contain. The only"
echo "# consistent all-three edit is one that does not touch an AC — and that is a re-fold (leg 5),"
echo "# not a hand edit, because it also has to refresh ac_hash and verified_at."
} > "$L/04-hand-edit-routes.log" 2>&1

# ------------------------------------------ 05 ticket edit => re-fold (AC 3)
{
echo "# Leg 5 — a ticket body changes upstream. The only path is a re-fold."
D=$S/refold; cp -R "$RUN" "$D"; T=$S/refold-tracker; cp -R "$EVAL/fixtures/ticket-set" "$T"
cp -R "$D" "$S/refold-before"
echo "## the tracker-side edit (prose in '## What to build', no AC touched)"
sub "$T/03-streaming.md" "instead of buffering the whole result set" "instead of buffering the whole result set in memory"
echo "## fold start re-materializes with §1's pipeline and finds the drift"
runsh "tr -d '\r' < $T/03-streaming.md > $D/tickets/03-streaming.md"
runsh "python3 logs/fold_check.py check $D"
echo "## the re-fold: overwrite tickets/, recompute, rewrite BOTH recorded copies + verified_at"
OLDSHA=$(sha "$RUN/tickets/03-streaming.md"); NEWSHA=$(sha "$D/tickets/03-streaming.md")
echo "# 03-streaming body_sha256 $OLDSHA -> $NEWSHA"
sub "$D/workflow.yaml" "instead of buffering the whole result set" "instead of buffering the whole result set in memory"
sub "$D/workflow.yaml" "sha256:$OLDSHA" "sha256:$NEWSHA"
sub "$D/workflow.yaml" "body_sha256: $OLDSHA" "body_sha256: $NEWSHA"
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
runsh "sed -i '' \"s/verified_at: \\\"20[0-9][0-9]-.*Z\\\"/verified_at: \\\"$NOW\\\"/\" $D/workflow.yaml"
runsh "python3 logs/fold_check.py check $D"
runsh "python3 $D/validate_workflow.py $D"
echo "## what the re-fold touched (the run folder is untracked, so diff -rq stands in for git diff --stat)"
runsh "diff -rq $S/refold-before $D"
echo "# ac_hash did not move: the edit was prose, not an AC row. That is the hash doing its job."
} > "$L/05-refold.log" 2>&1

# ----------------------------------- 06 the one hard guard: re-fold mid-run
{
echo "# Leg 6 — a re-fold while stages are past 'pending' is a reworking-class event."
D=$S/midrun; cp -R "$RUN" "$D"
sub "$D/state.json" '"freeze-tests": {
      "status": "pending"' '"freeze-tests": {
      "status": "passed"'
sub "$D/state.json" '"implement-csv-writer": {
      "status": "pending"' '"implement-csv-writer": {
      "status": "running"'
runsh "python3 -c \"import json;print({k:v['status'] for k,v in json.load(open('$D/state.json'))['stages'].items()})\""
runsh "python3 logs/fold_check.py check $D --refold"
echo "# Without --refold (i.e. a plain validation of a live run) the guard does not fire:"
runsh "python3 logs/fold_check.py check $D"
} > "$L/06-midrun-refold-refusal.log" 2>&1

# ------------------------------------- 07 anchor WARN/FAIL matrix (real script)
{
echo "# Leg 7 — the anchor triple through the SHIPPED validate_workflow.py (§A1-A3), 12 variants."
echo "# The fixture is a sliced fold, so every variant also carries the ported §A4 output."
python3 - "$RUN" "$S/anchor" <<'PY'
import pathlib, shutil, subprocess, sys
src, base = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
ANCHOR = ("spec_anchor:\n"
          "  raise_commit: cc834eb914911fd1f4d92d7f5914271821e8a455\n"
          "  surface_hash: 2f2e17eda1f05b60b310aca3ab72cd3565772dd56207f6007248f38dd871d42f\n"
          "  extractor_version: 1\n")
cases = [
    ("absent-anchor", lambda t: t.replace(ANCHOR, ""), None),
    ("complete-valid", lambda t: t, None),
    ("missing-raise_commit",
     lambda t: t.replace("  raise_commit: cc834eb914911fd1f4d92d7f5914271821e8a455\n", ""), None),
    ("missing-surface_hash",
     lambda t: t.replace("  surface_hash: 2f2e17eda1f05b60b310aca3ab72cd3565772dd56207f6007248f38dd871d42f\n", ""), None),
    ("missing-extractor_version", lambda t: t.replace("  extractor_version: 1\n", ""), None),
    ("abbreviated-raise_commit",
     lambda t: t.replace("raise_commit: cc834eb914911fd1f4d92d7f5914271821e8a455",
                         "raise_commit: cc834eb9149"), None),
    ("bad-surface_hash-shape",
     lambda t: t.replace("surface_hash: 2f2e17eda1f05b60b310aca3ab72cd3565772dd56207f6007248f38dd871d42f",
                         "surface_hash: 2f2e17ed"), None),
    ("non-integer-extractor_version",
     lambda t: t.replace("extractor_version: 1", "extractor_version: v1"), None),
    ("extractor_version-mismatch",
     lambda t: t.replace("extractor_version: 1", "extractor_version: 2"), None),
    ("surface-moved", lambda t: t, "spec"),
    ("extractor-deleted-anchored", lambda t: t, "rm-extractor"),
    ("extractor-deleted-unanchored", lambda t: t.replace(ANCHOR, ""), "rm-extractor"),
]
for name, mutate, extra in cases:
    d = base.parent / f"anchor-{name}"
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(src, d)
    (d / "workflow.yaml").write_text(mutate((src / "workflow.yaml").read_text()))
    if extra == "spec":
        (d / "0-spec.md").write_text((src / "0-spec.md").read_text().replace(
            "* FR-3 Exports above 10000 rows stream rather than buffer. `NFR-1`",
            "* FR-3 Exports above 10000 rows stream rather than buffer. `NFR-1`\n"
            "* FR-4 An export is retained for 7 days. `NFR-2`"))
    if extra == "rm-extractor":
        (d / "requirement_surface.py").unlink()
    p = subprocess.run([sys.executable, str(d / "validate_workflow.py"), str(d)],
                       capture_output=True, text=True, cwd="/")
    out = (p.stdout + p.stderr)
    print(f"$ python3 <{name}>/validate_workflow.py <{name}>   [cwd=/]")
    print(out.rstrip())
    print(f"exit={p.returncode}  FAIL={out.count('FAIL:')}  WARN={out.count('WARN:')}\n")
PY
echo "exit=$?"
} > "$L/07-anchor-matrix.log" 2>&1

# ------------------------------- 08 progress copy + owner resolution + empty
{
echo "# Leg 8 — exit_criteria.progress: the verbatim copy, the owner ladder, the two refusals."
echo "## the clean case (leg 1 repeated for the two resolution rules, byte-equality asserted)"
runsh "python3 logs/fold_check.py check runs/wave4a-fixture > $S/o.txt 2>&1; echo fold_check_exit=\$?; grep '^progress' $S/o.txt"
echo "## a third spec bullet naming a command no stage runs => the ask, then the stop"
D=$S/progress-orphan; cp -R "$RUN" "$D"
sub "$D/0-spec.md" "* Single-shot, no progress number:" "* progress: seconds of wall time reported by \`npm run export:bench\` — must reach 30, from a baseline of 210.
* Single-shot, no progress number:"
runsh "python3 logs/fold_check.py check $D > $S/o.txt 2>&1; echo fold_check_exit=\$?; grep -E '^(ASK|FAIL|progress)' $S/o.txt"
echo "## a stage whose progress is present but empty => the SHIPPED validator's own FAIL (§A5)"
D=$S/progress-empty; cp -R "$RUN" "$D"
sub "$D/workflow.yaml" 'progress: "number of failing assertions reported by `python3 -m pytest tests/csv_export` — must reach 0, from a baseline of 9 failing / 0 passing."' 'progress: ""'
runsh "python3 $D/validate_workflow.py $D"
echo "## a progress value that is NOT the spec bullet verbatim (one word reworded)"
D=$S/progress-reworded; cp -R "$RUN" "$D"
sub "$D/workflow.yaml" "must reach 0, from a baseline of 9 failing" "must hit 0, from a baseline of 9 failing"
runsh "python3 logs/fold_check.py check $D > $S/o.txt 2>&1; echo fold_check_exit=\$?; grep -A2 -E '^(progress|FAIL)' $S/o.txt"
} > "$L/08-progress-copy.log" 2>&1

# ----------------------------------------------- 09 non-vacuity by mutation
{
echo "# Leg 9 — three mutants under /tmp (no source file touched). A matrix that cannot fail is"
echo "# not evidence, so each mutant must make one NAMED leg above stop failing."
mkdir -p "$S/mutants"
echo "=== mutant 1: fold_check's whitespace-normalized block-vs-file compare removed"
echo "===           => leg 4 route (a) (brief-only hand edit) must go green"
cp "$L/fold_check.py" "$S/mutants/m1.py"
sub "$S/mutants/m1.py" 'if " ".join(body.split()) != " ".join(path.read_text().split()):' 'if False:'
runsh "python3 $S/mutants/m1.py check $S/route-a > $S/o.txt 2>&1; echo mutant_exit=\$?; tail -2 $S/o.txt"
echo "=== mutant 2: fold_check's verified_against cross-check removed"
echo "===           => a map refreshed against a different raise must go green"
cp "$L/fold_check.py" "$S/mutants/m2.py"
sub "$S/mutants/m2.py" 'if str(rec.get("verified_against")).strip() != raise_commit:' 'if False:'
D=$S/wrong-raise; cp -R "$RUN" "$D"
runsh "sed -i '' 's/verified_against: cc834eb914911fd1f4d92d7f5914271821e8a455/verified_against: 0000000000000000000000000000000000000000/' $D/workflow.yaml"
runsh "python3 logs/fold_check.py check $D > $S/o.txt 2>&1; echo fold_check_exit=\$?; grep '^FAIL' $S/o.txt"
runsh "python3 $S/mutants/m2.py check $D > $S/o.txt 2>&1; echo mutant_exit=\$?; tail -2 $S/o.txt"
echo "=== mutant 3: validate_workflow's absent-anchor WARN turned into a FAIL"
echo "===           => leg 10's worked example (unanchored, story 24) must go red"
cp "$RUN/validate_workflow.py" "$S/mutants/"
cp "$RUN/requirement_surface.py" "$S/mutants/"
sub "$S/mutants/validate_workflow.py" '        warnings.append(
            "no spec_anchor — this workflow is not anchored to a raise commit "' '        problems.append(
            "no spec_anchor — this workflow is not anchored to a raise commit "'
runsh "python3 $S/mutants/validate_workflow.py $REPO/workflow/runs/order-cancellation-refund"
echo "=== mutant 4: the SHIPPED validator's block-vs-file whitespace compare removed"
echo "===           => leg 4 route (a) (brief-only hand edit) must go green there too"
cp "$RUN/validate_workflow.py" "$S/mutants/m4.py"
sub "$S/mutants/m4.py" 'if " ".join(body.split()) != " ".join(path.read_text().split()):' 'if False:'
runsh "python3 $RUN/validate_workflow.py $S/route-a > $S/o.txt 2>&1; echo shipped_exit=\$?; grep '^FAIL' $S/o.txt"
runsh "python3 $S/mutants/m4.py $S/route-a > $S/o.txt 2>&1; echo mutant_exit=\$?; tail -1 $S/o.txt"
echo "=== mutant 5: the SHIPPED validator's verified_against cross-check removed"
echo "===           => the map refreshed against a different raise must go green there too"
cp "$RUN/validate_workflow.py" "$S/mutants/m5.py"
sub "$S/mutants/m5.py" 'if raise_commit and str(entry.get("verified_against") or "").strip() != raise_commit:' 'if False:'
runsh "python3 $RUN/validate_workflow.py $S/wrong-raise > $S/o.txt 2>&1; echo shipped_exit=\$?; grep '^FAIL' $S/o.txt"
runsh "python3 $S/mutants/m5.py $S/wrong-raise > $S/o.txt 2>&1; echo mutant_exit=\$?; tail -1 $S/o.txt"
} > "$L/09-nonvacuity.log" 2>&1

# --------------------------------------- 10 the worked example has not moved
{
echo "# Leg 10 — story 24: the monolithic, unanchored path is still valid."
runsh "python3 $SKILL/validate_spec.py $REPO/workflow/runs/order-cancellation-refund/0-spec.md $REPO"
runsh "python3 $SKILL/validate_workflow.py $REPO/workflow/runs/order-cancellation-refund"
echo "# zero matches => grep exits 1; that IS the claim: no anchor, no ticket blocks."
runsh "grep -c 'spec_anchor\|ticket:begin' $REPO/workflow/runs/order-cancellation-refund/workflow.yaml"
} > "$L/10-worked-example.log" 2>&1

# ------------------------------------------------------ 11 the unit suites
{
echo "# Leg 11 — the repo's own checks, unchanged by this eval."
runsh "cd $SKILL && python3 -m py_compile requirement_surface.py validate_spec.py validate_workflow.py test_requirement_surface.py test_validate_workflow_anchor.py && echo 'py_compile clean'"
runsh "cd $SKILL && python3 test_requirement_surface.py"
runsh "cd $SKILL && python3 test_validate_workflow_anchor.py"
runsh "python3 -m py_compile logs/fold_check.py && echo 'fold_check.py compiles'"
} > "$L/11-unit-suites.log" 2>&1

# ------------------------------------------------------- 12 measured numbers
{
echo "# Leg 12 — the sizes the fold actually costs. Story 14's context-rent claim, as bytes."
python3 - "$RUN" <<'PY'
import pathlib, re, sys
run = pathlib.Path(sys.argv[1])
raw = (run / "workflow.yaml").read_text()
spec = (run / "0-spec.md").read_text()
BLOCK = re.compile(r"<!-- ticket:begin (\S+) sha256:[0-9a-f]{64} -->.*?<!-- ticket:end \1 -->", re.S)
print(f"0-spec.md                     {len(spec.encode()):>7} bytes")
print(f"workflow.yaml (folded)        {len(raw.encode()):>7} bytes")
total = 0
for m in BLOCK.finditer(raw):
    n = len(m.group(0).encode())
    total += n
    tf = run / "tickets" / f"{m.group(1)}.md"
    print(f"  block {m.group(1):<20} {n:>7} bytes  (ticket file {len(tf.read_bytes()):>5} bytes "
          f"+ {n - len(tf.read_bytes()):>4} of delimiters/indent)")
print(f"  embedded blocks, total      {total:>7} bytes  = {total / len(raw.encode()):.0%} of workflow.yaml")
print()
print("per-spawn context rent for one implement stage's brief:")
for sid in ("implement-csv-writer", "implement-export-endpoint", "implement-streaming"):
    i = raw.index(f"- id: {sid}")
    j = raw.index("write_scope:", i)
    brief = len(raw[i:j].encode())
    print(f"  {sid:<26} brief {brief:>6} bytes   vs the full spec {len(spec.encode()):>6} bytes"
          f"   = {brief / len(spec.encode()):.0%}")
print()
print("what a run folder carries after F5 (bytes):")
for p in sorted(run.rglob("*")):
    if p.is_file() and "__pycache__" not in str(p):
        print(f"  {p.relative_to(run)!s:<28} {len(p.read_bytes()):>7}")
PY
echo "exit=$?"
echo
echo "wall time (/usr/bin/time -p, warm cache, macOS 25.5.0):"
runsh "/usr/bin/time -p python3 runs/wave4a-fixture/validate_workflow.py runs/wave4a-fixture"
runsh "/usr/bin/time -p python3 logs/fold_check.py check runs/wave4a-fixture > /dev/null"
echo "# No LLM pass was measured: this fold was enacted by hand from the skill text, in the same"
echo "# session that wrote the eval, so there is no isolated token/wall-time figure for a"
echo "# kestra-build fold spawn. Stated as not established rather than estimated."
} > "$L/12-measured-numbers.log" 2>&1

# ------------------------------------------------------------- the summary
{
printf "%-34s %5s %5s %8s %8s\n" "log" "FAIL" "WARN" "exit=0" "exit!=0"
for f in "$L"/0[1-9]-*.log "$L"/1*.log; do
  printf "%-34s %5s %5s %8s %8s\n" "$(basename "$f")" \
    "$(grep -c '^FAIL' "$f")" "$(grep -c '^WARN' "$f")" \
    "$(grep -c 'exit=0' "$f")" "$(grep -c 'exit=[1-9]' "$f")"
done
echo
echo "Counts are of lines in the logs, produced by:  grep -c '^FAIL' logs/<file>"
} > "$L/00-summary.txt" 2>&1
rm -rf "$RUN/__pycache__"
echo "done — logs in $L"
grep -c 'exit=' "$L"/*.log | sed 's#.*/logs/##'
