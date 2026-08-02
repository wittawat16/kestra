#!/usr/bin/env python3
"""Run kestra-exam's own Process against the fixture, mechanically.

    python3 build-exam.py create      # SKILL.md §Process steps 1-7
    python3 build-exam.py regenerate  # SKILL.md §Regeneration (delta-scoped)

This is the eval's stand-in for the agent that a real kestra-exam pass would be:
every *judgment* (which check, which assertion, which class, the unexaminable
reason) is hand-written in `exam-template.py`; every *derived value* (the anchor
triple, the fingerprints, the provenance cells, the red-proof cells, the
coverage arithmetic, both sha256s) is computed here from the skill's own scripts
and from `red-proof.json`, never typed. A hand-typed hash in an eval would make
the eval prove nothing.

Nothing is written inside the skill repo. The exam dir goes to
$KESTRA_EXAMS_ROOT (the eval sets it to $KX_ROOT/exams), which `exam_paths.py`
echoes as `exams_root_overridden: yes` on every run.
"""
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent
FIX = EVAL_DIR / "fixtures"
WORKFLOW = EVAL_DIR.parent.parent
SKILL = WORKFLOW / "kestra-exam"
S = SKILL / "scripts"
EXTRACTOR_SRC = WORKFLOW / "kestra-build" / "scripts" / "requirement_surface.py"

ROOT = Path(os.environ.get("KX_ROOT", "/tmp/kx36"))
REPO = ROOT / "repo"
RUN = REPO / "workflows" / "runs" / "tally-refund"

sys.path.insert(0, str(S))
import exam_anchor          # noqa: E402
import exam_delta           # noqa: E402
import exam_paths           # noqa: E402

VERDICT_CONTRACT = """A verdict is emitted only when the anchor triple recomputes equal (see §Anchor);
otherwise REFUSED — stale anchor, and no verdict line is written at all.
PASS iff C-0 passed AND every must-flip and must-hold check passed AND no check
reported an infrastructure red.  FAIL if any check failed behaviorally.
BLOCKED if the run exited 2 (harness).  Unexaminable rows never pass or fail;
they are listed by AC id.  U>0 ⇒ the evidence clause is MANDATORY: a PASS with
U>0 and no clause is a malformed verdict, i.e. a gate failure.

--- verdict (appended by the gate runner; unfilled above this line) ---
verdict:   PASS | FAIL | BLOCKED | REFUSED
evidence:  full | degraded — <U> unproven of <F> must-flip
coverage:  <M>/<N> ACs executably covered; unexaminable: <AC ids>
run:       <ISO-8601 Z> · exam.py sha256 <12> · exit <code>"""


def sh(*argv, **kw):
    p = subprocess.run([str(a) for a in argv], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, universal_newlines=True, **kw)
    return p.returncode, p.stdout, p.stderr


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# reading the authored exam without touching the seam
# --------------------------------------------------------------------------

def checks_meta(exam_py):
    """Every @check declaration, in order of appearance, by AST — so the
    manifest's rows cannot disagree with the exam's own declarations, and
    reading them touches no seam."""
    out = []
    for node in ast.parse(Path(exam_py).read_text()).body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and getattr(dec.func, "id", "")
                    == "check"):
                continue
            kw = {k.arg: ast.literal_eval(k.value) for k in dec.keywords}
            doc = ast.get_docstring(node) or ""
            out.append({"id": kw["id"], "ac": kw["ac"], "class": kw["cls"],
                        "provenance": kw["provenance"],
                        "unexaminable": kw.get("unexaminable", ""),
                        "title": doc.strip().splitlines()[0] if doc else ""})
    return out


def surface_of(exam_dir):
    mod, path = exam_anchor.load_extractor(exam_dir, RUN, REPO)
    return mod, mod.extract_surface((RUN / "0-spec.md").read_text()), path


def provenance_map(surface):
    """The Coverage Map's own `Source` cell per AC — `"<AC> | <Source>"` is
    exactly what the extractor emits, so nothing is re-parsed here."""
    return {ac: (row.split(" | ", 1)[1] if " | " in row else "—")
            for ac, row in surface.ac_rows}


def raw_section(spec_text, heading):
    """The raw lines of one `## ` section — verbatim, not the extractor's
    normalized units, because §Read rule quotes the spec as written."""
    out, on = [], False
    for line in spec_text.splitlines():
        if line.startswith("## "):
            on = line.strip() == heading
            continue
        if on:
            out.append(line)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


def write_exam(exam_dir, anchor, prov):
    text = (FIX / "exam-template.py").read_text()
    subs = {"@@EXAM@@": exam_dir.name, "@@RAISE@@": anchor["raise_commit"],
            "@@SURFACE@@": anchor["surface_hash"], "@@REPO@@": str(REPO),
            '"@@VER@@"': str(anchor["extractor_version"])}
    for ac, source in prov.items():
        subs[f"@@PROV:{ac}@@"] = source
    for k, v in subs.items():
        text = text.replace(k, v)
    left = [t for t in text.split("@@") if t.startswith(("PROV:", "EXAM", "RAISE"))]
    if left:
        raise SystemExit(f"FAIL: unsubstituted template placeholders: {left}")
    (exam_dir / "exam.py").write_text(text)
    return exam_dir / "exam.py"


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------

RED_PROOF_PENDING = "pending — the red proof has not run yet"


def red_cell(meta, row):
    """The closed five-value Red-proof vocabulary, decided by measurement."""
    if meta["class"] == "unexaminable":
        return "—"
    if meta["class"] == "must-hold":
        return "n/a — must-hold"
    when = row.get("red_proof_at", "")
    if row["result"] == "blocked":
        return "void — C-0 red at red-proof (harness) — `unproven`"
    if row["result"] == "pass":
        return "**born-green — `unproven`**"
    if row["red_kind"] == "behavioral":
        return f"red {when} behavioral"
    return f"**red {when} infrastructure — `unproven`**"


def is_unproven(meta, row):
    return meta["class"] == "must-flip" and not (
        row["result"] == "fail" and row["red_kind"] == "behavioral")


def manifest_text(exam_dir, anchor, meta, rows, surface, mod, stage1=False):
    slug = exam_dir.name
    by_id = {r["id"]: r for r in (rows or [])}
    acs = [ac for ac, _ in surface.ac_rows]
    ac_checks = {}
    for m in meta:
        ac_checks.setdefault(m["ac"], []).append(m)
    missing = [ac for ac in acs if ac not in ac_checks]
    if missing:
        raise SystemExit(f"FAIL: manifest defect — ACs with no check row: {missing}")

    L = [f"# Exam manifest — {slug}", "", "## Anchor", "", "| Field | Value |",
         "|---|---|"]
    for k in ("raise_commit", "surface_hash", "extractor_version", "origin_key",
              "feature_slug", "spec_path", "exam_script_sha256", "generated_at",
              "generation"):
        L.append(f"| {k} | {anchor[k]} |")
    L += ["", "## Read rule", "",
          "In surface, and the only sections read: the five named by",
          "`requirement_surface.SURFACE_SECTIONS` (that module is the single owner of the",
          "boundary; this manifest never restates the list). Run",
          "`python3 -c 'import requirement_surface as r; print(r.SURFACE_SECTIONS)'` beside this",
          "file to read it back.", "",
          "Never read, and not read while writing this exam: `## Files to Touch`,",
          "`## Codebase Survey`, `## Solution Architecture`, and the Coverage Map's",
          "`Covered by (files/steps)` column. No file under `src/` was opened.", "",
          "The `## External Interface` lines the `SEAM` encodes, verbatim from",
          f"`{anchor['spec_path']}` — `exam.py --audit-seam` requires `seam.target()` to appear",
          "in this block:", ""]
    # A `~~~` fence, because the quoted lines carry ``` fences of their own and a
    # ``` wrapper would close at the first of them — `exam.py --audit-seam` reads
    # the fenced block, so the wrong fence silently truncates the quote.
    L.append("~~~")
    L += raw_section((RUN / "0-spec.md").read_text(), "## External Interface")
    L.append("~~~")

    L += ["", "## Checks", "",
          "| AC | Check | Class | Provenance | Red-proof | Failure signature | Unexaminable |",
          "|----|-------|-------|------------|-----------|-------------------|--------------|"]
    unproven_ids = []
    for m in meta:
        if stage1:
            cell, sig = RED_PROOF_PENDING, "—"
        else:
            row = by_id[m["id"]]
            if m["class"] == "must-hold" and row["result"] != "pass":
                raise SystemExit(
                    f"FAIL: manifest defect — {m['id']} is declared must-hold but "
                    f"the red proof measured {row['result']}: {row['signature']}")
            cell = red_cell(m, row)
            sig = f"`{row['signature']}`" if row["signature"] else "—"
            if is_unproven(m, row):
                unproven_ids.append(m["id"])
        L.append(f"| {m['ac']} | {m['id']} | {m['class']} | {m['provenance']} | "
                 f"{cell} | {sig} | {m['unexaminable'] or '—'} |")

    sections, ac_fps = exam_delta.current_fingerprints(exam_dir, RUN, REPO)
    L += ["", "## Delta map", "", "### Section fingerprints", "",
          "| Section | sha256-12 |", "|---|---|"]
    for name in mod.SURFACE_SECTIONS:
        if name in sections:
            L.append(f"| {name} | {sections[name]} |")
    L += ["", "### AC fingerprints", "", "| AC | sha256-12 |", "|---|---|"]
    for ac in acs:
        L.append(f"| {ac} | {ac_fps[ac]} |")

    K = len([ac for ac in acs
             if all(m["class"] == "unexaminable" for m in ac_checks[ac])])
    N, M = len(acs), len(acs) - K
    F = len([m for m in meta if m["class"] == "must-flip"])
    H = len([m for m in meta if m["class"] == "must-hold"])
    U = len(unproven_ids)
    L += ["", "## Coverage", "",
          f"ACs in surface: {N} · executably covered: {M} · unexaminable: {K} · "
          f"must-flip: {F} (unproven: {U}) · must-hold: {H}", "",
          "## Verdict contract", "", VERDICT_CONTRACT, ""]
    return "\n".join(L), {"N": N, "M": M, "K": K, "F": F, "H": H, "U": U,
                          "unproven_ids": unproven_ids,
                          "unexaminable_acs": [ac for ac in acs if all(
                              m["class"] == "unexaminable" for m in ac_checks[ac])]}


# --------------------------------------------------------------------------
# red proof
# --------------------------------------------------------------------------

def red_proof(exam_dir, raise_sha, only=(), label="create"):
    clone = ROOT / f"redproof-clone-{label}"
    shutil.rmtree(clone, ignore_errors=True)
    for argv in (["git", "clone", "-q", "--no-hardlinks", str(REPO), str(clone)],
                 ["git", "-C", str(clone), "checkout", "-q", raise_sha]):
        code, _, err = sh(*argv)
        if code != 0:
            raise SystemExit(f"FAIL: {' '.join(argv)} -> {code}: {err}")
    args = ["--repo", str(clone)] + (["--only", *only] if only else [])
    code_j, out_j, err_j = sh("python3", exam_dir / "exam.py", *args, "--json")
    code_h, out_h, err_h = sh("python3", exam_dir / "exam.py", *args)
    print(f"red-proof ({label}) json exit={code_j} human exit={code_h}")
    if err_j.strip():
        print(err_j.strip())
    data = json.loads(out_j)
    for row in data["checks"]:
        row["red_proof_at"] = data["started_at"]
    human = (f"$ python3 exam.py {' '.join(args)}\n{out_h}{err_h}"
             f"exit={code_h}\n")
    shutil.rmtree(clone, ignore_errors=True)
    return data, human, code_h


def unproven_reasons(meta, rows):
    by_id = {r["id"]: r for r in rows}
    out = []
    for m in meta:
        row = by_id[m["id"]]
        if not is_unproven(m, row):
            continue
        if row["result"] == "pass":
            why = ("born green — the AC was already satisfied on the "
                   "pre-implementation tree, so this red proof shows no flip. "
                   "Class stays must-flip; the evidence is degraded, not the class.")
        elif row["result"] == "blocked":
            why = ("void — C-0 was red at red-proof time, so no other check's "
                   "result is evidence of anything.")
        else:
            why = ("infrastructure red — the seam was never reached, so the red "
                   "says nothing about this check's ability to go green.")
        out.append(f"unproven {m['id']} ({m['ac']}): {why}")
    return out


# --------------------------------------------------------------------------
# pointer (local-file transport)
# --------------------------------------------------------------------------

def write_pointer(fields, exam_dir, anchor, generation):
    body = "\n".join([
        exam_anchor.POINTER_MARKER,
        f"exam_dir: {exam_dir}/",
        f"exam_script_sha256: {sha256(exam_dir / 'exam.py')}",
        f"manifest_sha256: {sha256(exam_dir / 'manifest.md')}",
        f"raise_commit: {anchor['raise_commit']}",
        f"surface_hash: {anchor['surface_hash']}",
        f"extractor_version: {anchor['extractor_version']}",
        f"recorded_at: {now_iso()}",
        f"generation: {generation}",
    ]) + "\n"
    Path(fields["pointer_file"]).write_text(body)
    return body


def commit(exam_dir, subject):
    for argv in (["git", "-C", str(exam_dir), "add", "-A"],
                 ["git", "-C", str(exam_dir), "commit", "-q", "-m", subject]):
        code, out, err = sh(*argv)
        if code != 0:
            print(f"FAIL: {' '.join(argv[:4])} -> {code}\n{out}{err}")
            return code
    print(f"committed: {subject}")
    return 0


# --------------------------------------------------------------------------
# the two modes
# --------------------------------------------------------------------------

def common():
    fields = exam_paths.derive(REPO, RUN)
    for k, v in fields.items():
        print(f"{k}: {v}")
    return fields, Path(fields["exam_dir"])


def create():
    fields, exam_dir = common()
    exam_dir.mkdir(parents=True, exist_ok=True)
    for name in ("exam_harness.py", "exam_anchor.py"):
        shutil.copyfile(S / name, exam_dir / name)
    print("\nextractor candidates, in resolution order:")
    for c in exam_anchor.extractor_candidates(exam_dir, RUN, REPO):
        print(f"  {'EXISTS ' if c.exists() else 'absent '} {c}")
    shutil.copyfile(EXTRACTOR_SRC, exam_dir / "requirement_surface.py")
    print(f"copied extractor from {EXTRACTOR_SRC} (the fixture repo is not the "
          "skill repo, so candidate 3 cannot resolve — see the eval README)")

    code, out, err = sh("python3", exam_dir / "exam_anchor.py", RUN, exam_dir,
                        "--creatable")
    print(f"\n$ exam_anchor.py --creatable\n{out}{err}creatable exit={code}")

    mod, surface, _ = surface_of(exam_dir)
    raise_sha = exam_anchor.discover_raise(REPO, exam_dir.name, RUN)
    anchor = {"raise_commit": raise_sha, "surface_hash": surface.surface_hash,
              "extractor_version": mod.EXTRACTOR_VERSION,
              "origin_key": fields["origin_key"],
              "feature_slug": fields["feature_slug"],
              "spec_path": "workflows/runs/tally-refund/0-spec.md",
              "exam_script_sha256": "", "generated_at": now_iso(),
              "generation": 1}
    print(f"\nraise_commit: {raise_sha}\nsurface_hash: {surface.surface_hash}\n"
          f"extractor_version: {mod.EXTRACTOR_VERSION}")

    exam_py = write_exam(exam_dir, anchor, provenance_map(surface))
    anchor["exam_script_sha256"] = sha256(exam_py)
    meta = checks_meta(exam_py)

    # Stage 1: §Anchor + §Read rule only, so --audit-seam has its quoted block.
    # Transient: the red-proof cells cannot exist before the red proof, and a
    # cell outside the closed vocabulary is never committed or hashed.
    stage1, _ = manifest_text(exam_dir, anchor, meta, None, surface, mod,
                              stage1=True)
    (exam_dir / "manifest.md").write_text(stage1)
    for args in (["--list"], ["--audit-seam"]):
        code, out, err = sh("python3", exam_py, *args)
        print(f"\n$ exam.py {' '.join(args)}\n{out}{err}exit={code}")

    data, human, rp_exit = red_proof(exam_dir, raise_sha)
    data["generations"] = [{"generation": 1, "started_at": data["started_at"],
                            "only": None}]
    reasons = unproven_reasons(meta, data["checks"])
    (exam_dir / "red-proof.json").write_text(json.dumps(data, indent=2) + "\n")
    (exam_dir / "red-proof.log").write_text(
        human + "".join(r + "\n" for r in reasons))
    print("\n".join(reasons) or "no unproven rows")

    text, counts = manifest_text(exam_dir, anchor, meta, data["checks"], surface,
                                mod)
    (exam_dir / "manifest.md").write_text(text)
    if counts["U"] != data["summary"]["unproven"]:
        raise SystemExit(f"FAIL: manifest U={counts['U']} but red-proof.json "
                         f"summary.unproven={data['summary']['unproven']}")
    print(f"\ncoverage: {counts}")
    print(f"exam.py sha256:    {sha256(exam_py)}")
    print(f"manifest.md sha256:{sha256(exam_dir / 'manifest.md')}")

    body = write_pointer(fields, exam_dir, anchor, 1)
    print(f"\n--- {fields['pointer_file']} ---\n{body}")

    sh("git", "init", "-q", str(exam_dir))
    commit(exam_dir, f"exam({exam_dir.name}): create from surface "
                     f"{anchor['surface_hash'][:12]} @ raise {raise_sha[:12]}")
    code, out, err = sh("git", "-C", str(exam_dir), "log", "--oneline")
    print(f"$ git -C <exam-dir> log --oneline\n{out}exit={code}")
    code, out, _ = sh("git", "-C", str(exam_dir), "remote")
    print(f"$ git -C <exam-dir> remote\n{out}(empty={not out.strip()}) exit={code}")
    code, out, err = sh("python3", exam_dir / "exam_anchor.py", RUN, exam_dir)
    print(f"\n$ exam_anchor.py <run> <exam>\n{out}{err}anchor exit={code}")
    return 0 if code == 0 else 1


def regenerate():
    fields, exam_dir = common()
    old = exam_anchor.read_manifest_anchor(exam_dir / "manifest.md")
    plan = exam_delta.plan(RUN, exam_dir)
    print(f"\n$ exam_delta.py <run> <exam>\n{plan}\n")
    fields_by_key = dict(
        (line.split(":", 1)[0].strip(), line.split(":", 1)[1].strip())
        for line in plan.splitlines() if ":" in line)
    scope = fields_by_key["scope"]
    regen = [t for t in fields_by_key["regenerate"].split() if t != "-"]
    if scope not in ("delta", "full"):
        raise SystemExit(f"FAIL: this eval only regenerates delta/full; got {scope}")

    mod, surface, _ = surface_of(exam_dir)
    raise_sha = exam_anchor.discover_raise(REPO, exam_dir.name, RUN)
    generation = int(old["generation"]) + 1
    anchor = {"raise_commit": raise_sha, "surface_hash": surface.surface_hash,
              "extractor_version": mod.EXTRACTOR_VERSION,
              "origin_key": fields["origin_key"],
              "feature_slug": fields["feature_slug"],
              "spec_path": "workflows/runs/tally-refund/0-spec.md",
              "exam_script_sha256": "", "generated_at": now_iso(),
              "generation": generation}
    exam_py = write_exam(exam_dir, anchor, provenance_map(surface))
    anchor["exam_script_sha256"] = sha256(exam_py)
    meta = checks_meta(exam_py)

    prior = json.loads((exam_dir / "red-proof.json").read_text())
    data, human, _ = red_proof(exam_dir, raise_sha, only=regen,
                               label=f"gen{generation}")
    fresh = {r["id"]: r for r in data["checks"]}
    merged = []
    for row in prior["checks"]:
        merged.append(fresh[row["id"]] if row["id"] in fresh else row)
    data["checks"] = merged
    sys.path.insert(0, str(exam_dir))
    import exam_harness                                   # noqa: E402
    data["summary"] = exam_harness.summarize(merged)
    data["generations"] = prior.get("generations", []) + [
        {"generation": generation, "started_at": data["started_at"],
         "only": regen}]
    reasons = unproven_reasons(meta, merged)
    (exam_dir / "red-proof.json").write_text(json.dumps(data, indent=2) + "\n")
    with (exam_dir / "red-proof.log").open("a") as fh:
        fh.write(f"\n--- generation {generation}: fresh red proof for "
                 f"{' '.join(regen)} at raise {raise_sha[:12]} ---\n")
        fh.write(human + "".join(r + "\n" for r in reasons))
    print("\n".join(reasons) or "no unproven rows")

    text, counts = manifest_text(exam_dir, anchor, meta, merged, surface, mod)
    (exam_dir / "manifest.md").write_text(text)
    body = write_pointer(fields, exam_dir, anchor, generation)
    with Path(fields["pointer_log"]).open("a") as fh:
        fh.write(f"{now_iso()} regenerated {','.join(regen)} "
                 f"({fields_by_key['why']}); surface "
                 f"{old['surface_hash'][:8]}… → {anchor['surface_hash'][:8]}…; "
                 f"raise {old['raise_commit'][:8]}… → {raise_sha[:8]}…; "
                 f"generation {old['generation']} → {generation}\n")
    print(f"--- {fields['pointer_file']} ---\n{body}")
    print(f"--- {fields['pointer_log']} ---")
    print(Path(fields["pointer_log"]).read_text(), end="")
    commit(exam_dir, f"exam({exam_dir.name}): regenerate {','.join(regen)} for "
                     f"surface {anchor['surface_hash'][:12]} @ raise "
                     f"{raise_sha[:12]}")
    code, out, _ = sh("git", "-C", str(exam_dir), "log", "--oneline")
    print(f"$ git -C <exam-dir> log --oneline\n{out}")
    print(f"coverage: {counts}")
    code, out, err = sh("python3", exam_dir / "exam_anchor.py", RUN, exam_dir)
    print(f"\n$ exam_anchor.py <run> <exam>\n{out}{err}anchor exit={code}")
    return 0 if code == 0 else 1


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "create":
        sys.exit(create())
    if mode == "regenerate":
        sys.exit(regenerate())
    print(__doc__)
    sys.exit(3)
