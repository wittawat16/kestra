#!/usr/bin/env python3
"""The regeneration plan: which checks a spec change actually invalidated.

WHY THIS FILE EXISTS
    A moved `surface_hash` tells you *that* the requirement text changed, never
    *which AC*. Without that answer a spec edit re-proves the whole exam, which
    is the tax that makes people stop editing specs — and re-deriving the answer
    by hand over- or under-regenerates, both silently.

    The AC->check map is not a second artifact: it is already the `AC` column of
    the manifest's `## Checks` table. What `## Delta map` adds is fingerprints,
    per section and per AC row, so the diff is per-requirement.

    Every fingerprint comes from the extractor's own output —
    `sha256("\\n".join(surface.sections[name]) + "\\n")` per section and
    `sha256(row)` per Coverage-Map row, where `row` is exactly what
    `requirement_surface._ac_rows` emits (`"<AC> | <Source>"`). There is no
    second normalization anywhere in kestra-exam, which is why a column reorder,
    a checkbox flip, a list-marker change or a reflowed paragraph is already a
    non-event.

THREE SCOPES, DIFFERENT BLAST RADIUS
    delta      AC rows changed/added/removed ⇒ regenerate exactly their checks.
    full       `## External Interface` moved ⇒ the seam itself moved, and every
               check is driven through it. Not delta-able; the plan says so.
    re-anchor  Functional Requirements / Edge Cases / Runtime Invariants (or the
               Coverage Map's row *order*) moved with no AC row and no External
               Interface change ⇒ regenerate nothing, rewrite the anchor. Those
               sections are the prose the ACs paraphrase; re-proving an exam over
               a rewording is the tax this scope exists to refuse. Never silent:
               the regeneration comment records that FR/EC/RI moved without an AC
               row, so a human can confirm the Coverage Map still paraphrases them.
    current    nothing moved — no regeneration and no re-anchor.

CARRY-OVER
    A check carries over only on an identical `(check id, normalized AC row)`.
    Anything else is regenerated, and a regenerated `must-flip` needs a *fresh*
    red proof in a fresh disposable clone at the **new** raise commit. Carried
    rows keep their original red-proof timestamp — honest and visible: the
    timestamp shows the evidence predates this generation.

Usage:
    python3 exam_delta.py <run-dir> <exam-dir>

Exit 0 on any successful analysis (read the `scope:` line for the outcome) ·
1 on a usage or read error.
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exam_anchor import (Refused, Unreadable, _git, compute_now,  # noqa: E402
                         discover_raise, load_extractor,
                         read_manifest_anchor)

FP = 12  # sha256-12: enough to diff, short enough to read in a table


def fp(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:FP]


def current_fingerprints(exam_dir, run_dir, repo_root):
    """(section fingerprints, AC fingerprints) for the working-tree spec."""
    mod, _ = load_extractor(exam_dir, run_dir, repo_root)
    spec = Path(run_dir) / "0-spec.md"
    if not spec.exists():
        raise Unreadable(f"no 0-spec.md at {spec}")
    surface = mod.extract_surface(spec.read_text())
    sections = {name: fp("\n".join(surface.sections[name]) + "\n")
                for name in mod.SURFACE_SECTIONS if name in surface.sections}
    acs = {ac_id: fp(row) for ac_id, row in surface.ac_rows}
    return sections, acs


def recorded_fingerprints(manifest_path):
    """The two `## Delta map` sub-tables, as they were written at generation."""
    sections, acs, where = {}, {}, None
    for line in Path(manifest_path).read_text().splitlines():
        s = line.strip()
        if s.startswith("## "):
            where = "delta" if s.lower() == "## delta map" else None
        elif where and s.startswith("### "):
            low = s.lower()
            where = ("sections" if "section" in low
                     else "acs" if "ac" in low else "delta")
        elif where in ("sections", "acs") and s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) >= 2 and not set(cells[0]) <= set("-: ") \
                    and cells[1].lower() not in ("sha256-12", "sha256"):
                (sections if where == "sections" else acs)[cells[0]] = cells[1]
    return sections, acs


def ac_to_checks(manifest_path):
    """The `## Checks` table's `AC` column — the AC->check map itself."""
    mapping, in_section, header = {}, False, None
    for line in Path(manifest_path).read_text().splitlines():
        s = line.strip()
        if s.startswith("## "):
            in_section = s.lower() == "## checks"
            header = None
            continue
        if not in_section or not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if set(s) <= set("-:| "):
            continue
        row = dict(zip(header, cells))
        mapping.setdefault(row.get("ac", "—"), []).append(row.get("check", "?"))
    return mapping


def plan(run_dir, exam_dir):
    run_dir, exam_dir = Path(run_dir), Path(exam_dir)
    manifest = exam_dir / "manifest.md"
    code, top, err = _git(["rev-parse", "--show-toplevel"], run_dir)
    if code != 0:
        raise Unreadable(f"{run_dir} is not inside a git repo: {err}")
    repo_root = Path(top)

    now_sections, now_acs = current_fingerprints(exam_dir, run_dir, repo_root)
    old_sections, old_acs = recorded_fingerprints(manifest)
    if not old_acs and not old_sections:
        raise Unreadable(f"{manifest} has no '## Delta map' fingerprints — the "
                         "exam predates delta regeneration; regenerate in full")
    amap = ac_to_checks(manifest)

    changed = sorted(a for a in now_acs if a in old_acs
                     and now_acs[a] != old_acs[a])
    added = sorted(a for a in now_acs if a not in old_acs)
    removed = sorted(a for a in old_acs if a not in now_acs)
    ei_moved = now_sections.get("External Interface") != \
        old_sections.get("External Interface")
    other_moved = sorted(
        n for n in set(now_sections) | set(old_sections)
        if n != "External Interface" and now_sections.get(n) != old_sections.get(n))

    all_checks = [c for ids in amap.values() for c in ids]
    hit = [c for a in changed + added for c in amap.get(a, [])]
    gone = [c for a in removed for c in amap.get(a, [])]
    new_acs = [a for a in added if not amap.get(a)]

    if ei_moved:
        scope = "full"
        regen, delete, carry = sorted(set(all_checks)), [], []
    elif changed or added or removed:
        scope = "delta"
        regen = sorted(set(hit))
        delete = sorted(set(gone))
        carry = sorted(set(all_checks) - set(regen) - set(delete))
    elif other_moved:
        scope, regen, delete = "re-anchor", [], []
        carry = sorted(set(all_checks))
    else:
        scope, regen, delete = "current", [], []
        carry = sorted(set(all_checks))

    recorded = read_manifest_anchor(manifest)
    now_hash, now_ver = compute_now(exam_dir, run_dir, repo_root)
    try:
        new_raise = discover_raise(repo_root, exam_dir.name, run_dir)
    except Refused as e:
        new_raise = f"UNRESOLVED ({e.args[0].splitlines()[0]})"

    why = ", ".join([f"{a} changed" for a in changed]
                    + [f"{a} added" for a in added]
                    + [f"{a} removed" for a in removed]
                    + (["External Interface moved"] if ei_moved else [])
                    + ([f"{n} moved" for n in other_moved] if not
                       (changed or added or removed or ei_moved) else [])) or "nothing moved"

    lines = [f"scope: {scope}", f"why:        {why}"]
    if scope == "full":
        lines.append("note:       the declared seam moved — every check is "
                     "driven through it, so nothing is delta-able")
    if scope == "re-anchor":
        lines.append("note:       re-anchored only; FR/EC/RI moved without an "
                     "AC row — verify the Coverage Map still paraphrases them")
    lines += [f"regenerate: {' '.join(regen) or '-'}",
              f"new-ac:     {' '.join(new_acs) or '-'}   "
              "(ACs with no check row yet — author one each)",
              f"delete:     {' '.join(delete) or '-'}",
              f"carry:      {' '.join(carry) or '-'}",
              f"re-anchor:  surface {recorded.get('surface_hash', '')[:FP]} -> "
              f"{now_hash[:FP]} ; raise "
              f"{recorded.get('raise_commit', '')[:8]} -> {new_raise[:8]} ; "
              f"extractor v{recorded.get('extractor_version')} -> v{now_ver}"]
    if scope == "current":
        lines.append("generation: unchanged — nothing moved, so no regeneration, "
                     "no re-anchor and no pointer edit")
    else:
        lines += ["generation: {} -> {}".format(
            recorded.get("generation", "?"),
            int(recorded["generation"]) + 1
            if str(recorded.get("generation", "")).isdigit() else "?"),
            "red-proof:  every regenerated must-flip needs a FRESH red proof in "
            "a new disposable clone at the new raise commit; C-0 runs regardless "
            "of --only"]
    return "\n".join(lines)


def main():
    if len(sys.argv) != 3:
        print(__doc__.rsplit("Usage:", 1)[-1].strip(), file=sys.stderr)
        sys.exit(1)
    try:
        print(plan(sys.argv[1], sys.argv[2]))
    except (Unreadable, Refused) as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
