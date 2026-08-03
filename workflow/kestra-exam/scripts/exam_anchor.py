#!/usr/bin/env python3
"""The anchor triple: compute it, compare it, and refuse when it moved.

WHY THIS FILE EXISTS
    A verdict says "the delivered work matches what was asked". That sentence is
    only true against a named requirement text. The anchor triple — raise_commit
    (40-hex) · surface_hash (64-hex) · extractor_version (int) — names it, and
    comparing it is repeated deterministic work whose hand-redo produces the one
    error nobody catches: a *false-fresh* verdict, certifying delivery against a
    superseded requirement.

    The triple is recorded in three places that must agree:
      1. `<exam-dir>/manifest.md`  §Anchor      — authoritative
      2. the pointer body (tracker ticket or `<slug>.pointer`) — durable mirror
      3. `<exam-dir>/exam.py`      ANCHOR = {…} — so a bare script run self-reports
    Disagreement among the three is itself a refusal; otherwise a tamper that
    edits one copy reads as fresh.

FRESHNESS IS COMPUTED FROM THE WORKING TREE, NOT `HEAD`
    An uncommitted human edit to 0-spec.md is exactly what this check exists to
    catch, and it is what every spawned subagent would read.

EVERY FAIL-CLOSED ARM IS A REFUSAL, NEVER A SKIP
    partial anchor · raise commit unreachable or not exactly-one · extractor
    version differs · anchor copies disagree · extractor missing. Each prints
    the same three-field block plus a named cause, and exits 2. A comparison
    that cannot run counts as a mismatch.

WHAT DOES NOT MOVE THE ANCHOR
    Everything outside `requirement_surface.SURFACE_SECTIONS` — that module is
    the single owner of the boundary and this file never restates the list.

Usage:
    python3 -I -B exam_anchor.py <run-dir> <exam-dir> [--pointer-body <file>]
    python3 -I -B exam_anchor.py <run-dir> <exam-dir> --creatable

Exit 0 fresh (or creatable) · 1 create-time hard stop · 2 REFUSED · 3 unreadable.
`--pointer-body` is required whenever no `<slug>.pointer` sits beside the exam
dir: on the GitHub transport the gate runner fetches it first
(`gh issue view <N> --repo <R> --json body --jq .body > /tmp/pointer.txt`).
Not comparing the pointer copy would be a skip, and there are no skips here.
"""
import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

POINTER_MARKER = "<!-- kestra-exam-pointer v1 -->"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_PTR_LINE = re.compile(r"^(\w+):\s*(\S+)$")
_TICKET = re.compile(r"^>\s*Spec-ticket:\s*(\S+)\s*$")
_ERE_META = r".^$*+?()[]{}|\\"

VERSION_NOTE = ("hashes are not comparable across extractor versions — "
                "re-derive, never diff")


class Unreadable(Exception):
    """An input could not be read at all — exit 3."""


class Refused(Exception):
    """A fail-closed arm fired — exit 2, with a named cause."""


# --------------------------------------------------------------------------
# reading the three recorded copies
# --------------------------------------------------------------------------

def _norm(anchor):
    out = {}
    for k in ("raise_commit", "surface_hash", "extractor_version"):
        v = anchor.get(k)
        out[k] = str(v).strip() if v is not None else ""
    return out


def read_manifest_anchor(manifest_path):
    """The `## Anchor` pipe table of a manifest.md, as a `field: value` dict."""
    p = Path(manifest_path)
    if not p.exists():
        raise Unreadable(f"no manifest at {p}")
    fields, in_section = {}, False
    for line in p.read_text().splitlines():
        if line.startswith("## "):
            in_section = line.strip().lower() == "## anchor"
            continue
        if in_section and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and not set(cells[0]) <= set("-: "):
                fields[cells[0].lower()] = cells[1].strip("`")
    if not fields:
        raise Unreadable(f"{p} has no '## Anchor' table")
    return fields


def read_pointer_anchor(text):
    """A pointer body's fields. A body whose first line is not the v1 marker is
    malformed — never treated as "assume defaults"."""
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines or lines[0].strip() != POINTER_MARKER:
        raise Refused("pointer body is malformed — its first line must be "
                      f"exactly `{POINTER_MARKER}`")
    fields = {}
    for line in lines[1:]:
        m = _PTR_LINE.match(line.strip())
        if m:
            fields[m.group(1).lower()] = m.group(2)
    return fields


def read_exam_anchor(exam_py):
    """`ANCHOR = {...}` from exam.py, without importing it (importing would run
    the exam's module-level seam construction)."""
    p = Path(exam_py)
    if not p.exists():
        raise Unreadable(f"no exam.py at {p}")
    try:
        tree = ast.parse(p.read_text())
    except SyntaxError as e:
        raise Unreadable(f"{p} does not parse: {e}") from None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "ANCHOR"
                for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                raise Unreadable(f"{p}: ANCHOR is not a literal dict") from None
    raise Unreadable(f"{p} declares no module-level ANCHOR")


# --------------------------------------------------------------------------
# recomputing the current surface
# --------------------------------------------------------------------------

def extractor_candidates(exam_dir, run_dir, repo_root):
    return [Path(exam_dir) / "requirement_surface.py",
            Path(run_dir) / "requirement_surface.py",
            Path(repo_root) / "workflow/kestra-build/scripts/requirement_surface.py",
            Path.home() / ".claude/skills/kestra-build/scripts/requirement_surface.py"]


def load_extractor(exam_dir, run_dir, repo_root):
    """First candidate that exists wins. None ⇒ a refusal, not a WARN: an
    unanchored exam certifies nothing, so kestra-exam cannot degrade the way
    kestra-spec's optional validator does."""
    cands = extractor_candidates(exam_dir, run_dir, repo_root)
    for c in cands:
        if c.exists():
            spec = importlib.util.spec_from_file_location(
                "kestra_requirement_surface", c)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod, c
    raise Refused("extractor missing — no requirement_surface.py at any of:\n"
                  + "\n".join(f"    {c}" for c in cands))


def compute_now(exam_dir, run_dir, repo_root):
    """(surface_hash, extractor_version) from the **working tree** 0-spec.md."""
    spec = Path(run_dir) / "0-spec.md"
    if not spec.exists():
        raise Unreadable(f"no 0-spec.md at {spec}")
    mod, _ = load_extractor(exam_dir, run_dir, repo_root)
    try:
        surface = mod.extract_surface(spec.read_text())
    except mod.SurfaceError as e:
        raise Unreadable(f"{spec} cannot be extracted honestly: {e}") from None
    return surface.surface_hash, mod.EXTRACTOR_VERSION


# --------------------------------------------------------------------------
# raise-commit discovery — exactly one match, never a hand-picked SHA
# --------------------------------------------------------------------------

def _ere(s):
    return "".join("\\" + c if c in _ERE_META else c for c in s)


def _git(args, cwd):
    p = subprocess.run(["git", "-C", str(cwd)] + args, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, universal_newlines=True)
    # Porcelain status owns its two leading columns. Removing only record-ending
    # newlines keeps ` M manifest.md` distinguishable from `M  manifest.md`.
    return p.returncode, p.stdout.rstrip("\r\n"), p.stderr.rstrip("\r\n")


def spec_ticket(spec_path):
    """The `> Spec-ticket:` URL from the preamble (above the first `## `), or
    None. >1 match is a malformed marker, not an ambiguity to resolve."""
    hits = []
    for line in Path(spec_path).read_text().splitlines():
        if line.startswith("## "):
            break
        m = _TICKET.match(line)
        if m:
            hits.append(m.group(1))
    if len(hits) > 1:
        raise Refused(f"{spec_path} carries {len(hits)} `> Spec-ticket:` "
                      "preamble lines — ambiguous by construction")
    return hits[0] if hits else None


def discover_raise(repo_root, slug, run_dir):
    """The one commit whose 0-spec.md a surface_hash is computed over.

    Current branch only — `--all` finds sibling-branch raises and manufactures a
    spurious >1. Chain subject first; a spec with no `> Spec-ticket:` marker
    then retries the standalone subject, which is the raise a hand-written spec
    actually has. A *marked* spec never falls back."""
    url = spec_ticket(Path(run_dir) / "0-spec.md")
    chain = [f"^spec\\({_ere(slug)}\\): raise vetted ticket into 0-spec\\.md$"]
    if url:
        chain.append(f"^Spec-ticket: {_ere(url)}$")
    args = ["log", "-E", "--all-match", "--format=%H"] + \
           [f"--grep={g}" for g in chain]
    code, out, err = _git(args, repo_root)
    if code != 0:
        raise Unreadable(f"git log failed in {repo_root}: {err}")
    shas = out.split()
    if not shas and not url:
        code, out, err = _git(
            ["log", "-E", "--format=%H",
             f"--grep=^spec\\({_ere(slug)}\\): write 0-spec\\.md from a "
             f"hand-written idea$"], repo_root)
        shas = out.split()
    if len(shas) != 1:
        which = f"{slug} @ {url}" if url else f"{slug} (standalone)"
        raise Refused(
            f"raise commit is not exactly one: {len(shas)} match {which} on this "
            f"branch ({' '.join(s[:12] for s in shas) or 'none'}). A re-raise "
            "replaces its predecessor rather than stacking; resolve by naming "
            "the intended SHA explicitly, never by picking the newest.")
    return shas[0]


def raise_reachable(repo_root, sha):
    code, _, _ = _git(["cat-file", "-e", sha + "^{commit}"], repo_root)
    return code == 0


def check_exam_commit(exam_dir, pointer):
    """Pin every committed exam artifact, not only exam.py and manifest.md.

    Verdict appends deliberately leave manifest.md unstaged and dirty; every
    other index/worktree change (including a helper edit or ignored untracked
    import shadow) is a refusal.
    """
    recorded = str(pointer.get("exam_commit") or "").strip()
    if not _HEX40.match(recorded):
        raise Refused("pointer exam_commit is missing or not a full 40-hex commit SHA")
    code, head, err = _git(["rev-parse", "HEAD"], exam_dir)
    if code != 0:
        raise Refused(f"exam commit cannot be resolved in {exam_dir}: {err}")
    if head != recorded:
        raise Refused(f"exam HEAD {head[:12]} != pointer exam_commit {recorded[:12]}")
    code, status, err = _git(["status", "--porcelain", "--untracked-files=all"], exam_dir)
    if code != 0:
        raise Refused(f"exam worktree status cannot be read in {exam_dir}: {err}")
    dirty = [line for line in status.splitlines() if line != " M manifest.md"]
    if dirty:
        raise Refused("exam worktree has unpinned changes outside the unstaged verdict "
                      f"append: {dirty}")
    code, ignored, err = _git(
        ["ls-files", "--others", "--ignored", "--exclude-standard"], exam_dir)
    if code != 0:
        raise Refused(f"exam ignored-path status cannot be read in {exam_dir}: {err}")
    if ignored:
        raise Refused("exam worktree has ignored unpinned paths that can shadow committed "
                      f"Python modules: {ignored.splitlines()}")


# --------------------------------------------------------------------------
# comparing
# --------------------------------------------------------------------------

def _block(recorded, now_hash, now_ver, cause):
    def row(label, rec, cur):
        op = "==" if rec == cur else "!="
        return f"  {label + ':':<19}recorded {rec} {op} current {cur}"
    return "\n".join([
        "REFUSED: exam is stale — no verdict emitted.",
        f"  cause:             {cause}",
        row("surface_hash", recorded["surface_hash"][:12], now_hash[:12]),
        row("raise_commit", recorded["raise_commit"][:8], recorded["_now_raise"][:8]),
        row("extractor_version", recorded["extractor_version"], str(now_ver)),
        "A verdict here would certify the delivered work against a superseded "
        "requirement.",
        "Regenerate the affected checks (kestra-exam regeneration is delta-scoped "
        "by the",
        "AC->check map), then re-run the gate. Do not edit the anchor to match.",
    ])


def compare(run_dir, exam_dir, pointer_text=None):
    """Returns (0, report) when fresh; raises Refused / Unreadable otherwise."""
    run_dir, exam_dir = Path(run_dir), Path(exam_dir)
    code, top, err = _git(["rev-parse", "--show-toplevel"], run_dir)
    if code != 0:
        raise Unreadable(f"{run_dir} is not inside a git repo: {err}")
    repo_root = Path(top)

    manifest = _norm(read_manifest_anchor(exam_dir / "manifest.md"))
    script = _norm(read_exam_anchor(exam_dir / "exam.py"))
    if pointer_text is None:
        local = exam_dir.parent / (exam_dir.name + ".pointer")
        if not local.exists():
            raise Unreadable(
                f"no pointer copy to compare: {local} does not exist and no "
                "--pointer-body was given. On the GitHub transport, fetch the "
                "ticket body first — a skipped pointer comparison is not a pass.")
        pointer_text = local.read_text()
    pointer_fields = read_pointer_anchor(pointer_text)
    check_exam_commit(exam_dir, pointer_fields)
    pointer = _norm(pointer_fields)

    recorded = dict(manifest)
    bad = [k for k, rx in (("raise_commit", _HEX40), ("surface_hash", _HEX64))
           if not rx.match(recorded[k])]
    if not recorded["extractor_version"].isdigit():
        bad.append("extractor_version")
    now_hash, now_ver = compute_now(exam_dir, run_dir, repo_root)
    recorded["_now_raise"] = recorded["raise_commit"]
    if bad:
        raise Refused(_block(recorded, now_hash, now_ver,
                             f"partial anchor — malformed or absent: "
                             f"{', '.join(bad)}"))

    for name, copy in (("pointer", pointer), ("exam.py", script)):
        diff = [k for k in ("raise_commit", "surface_hash", "extractor_version")
                if copy[k] != recorded[k]]
        if diff:
            raise Refused(_block(recorded, now_hash, now_ver,
                                 f"anchor copies disagree — manifest vs {name} "
                                 f"on {', '.join(diff)}; {name} says "
                                 + ", ".join(f"{k}={copy[k]}" for k in diff)))

    if not raise_reachable(repo_root, recorded["raise_commit"]):
        raise Refused(_block(recorded, now_hash, now_ver,
                             "raise commit unreachable — `git cat-file -e "
                             f"{recorded['raise_commit'][:12]}^{{commit}}` failed"))
    discovered = discover_raise(repo_root, exam_dir.name, run_dir)
    recorded["_now_raise"] = discovered

    if str(now_ver) != recorded["extractor_version"]:
        raise Refused(_block(recorded, now_hash, now_ver,
                             f"extractor version differs — {VERSION_NOTE}"))
    if now_hash != recorded["surface_hash"] or discovered != recorded["raise_commit"]:
        raise Refused(_block(recorded, now_hash, now_ver,
                             "surface or raise moved since the exam was written"))
    return 0, (f"FRESH: surface {now_hash[:12]} @ raise {discovered[:12]} · "
               f"extractor v{now_ver} — manifest, pointer and exam.py agree.")


def assert_creatable(run_dir, exam_dir):
    """Creation happens once. An existing exam dir whose manifest carries a
    *different* anchor is a hard stop directing to regeneration — creation never
    overwrites another exam's evidence."""
    exam_dir = Path(exam_dir)
    if not (exam_dir / "manifest.md").exists():
        return 0, f"CREATABLE: {exam_dir} holds no manifest.md yet."
    code, top, _ = _git(["rev-parse", "--show-toplevel"], run_dir)
    repo_root = Path(top) if code == 0 else Path(run_dir)
    recorded = _norm(read_manifest_anchor(exam_dir / "manifest.md"))
    now_hash, now_ver = compute_now(exam_dir, run_dir, repo_root)
    discovered = discover_raise(repo_root, exam_dir.name, run_dir)
    if (recorded["surface_hash"] == now_hash
            and recorded["raise_commit"] == discovered
            and recorded["extractor_version"] == str(now_ver)):
        return 0, (f"CREATABLE: {exam_dir} already anchors surface "
                   f"{now_hash[:12]} — re-running creation is idempotent.")
    raise Refused(
        f"FAIL: {exam_dir} already holds an exam anchored to surface "
        f"{recorded['surface_hash'][:12]} @ raise "
        f"{recorded['raise_commit'][:12]} · extractor "
        f"v{recorded['extractor_version']}, while the current anchor is "
        f"{now_hash[:12]} @ raise {discovered[:12]} · extractor v{now_ver}. "
        "Creation never overwrites another exam's evidence: "
        "run the delta regeneration instead (`python3 -B exam_delta.py "
        f"{run_dir} {exam_dir}`), which edits the pointer in place and keeps "
        "the exam's git history.")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = sys.argv[1:]
    pointer_text = None
    if "--pointer-body" in flags:
        i = flags.index("--pointer-body")
        if i + 1 >= len(flags):
            print("FAIL: --pointer-body needs a file", file=sys.stderr)
            sys.exit(3)
        body = Path(flags[i + 1])
        args = [a for a in args if a != str(body)]
        if not body.exists():
            print(f"FAIL: no pointer body at {body}", file=sys.stderr)
            sys.exit(3)
        pointer_text = body.read_text()
    if len(args) != 2:
        print(__doc__.rsplit("Usage:", 1)[-1].strip(), file=sys.stderr)
        sys.exit(3)
    try:
        if "--creatable" in flags:
            code, report = assert_creatable(args[0], args[1])
        else:
            code, report = compare(args[0], args[1], pointer_text)
    except Unreadable as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(3)
    except Refused as e:
        print(e, file=sys.stderr)
        sys.exit(1 if "--creatable" in flags else 2)
    print(report)
    sys.exit(code)


if __name__ == "__main__":
    main()
