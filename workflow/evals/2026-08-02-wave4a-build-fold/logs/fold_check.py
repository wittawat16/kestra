#!/usr/bin/env python3
"""Eval harness — the mechanical half of ticket-fold.md's F1-F4 and
validator_split §A4, run as a command so this eval's claims are exit codes.

WHY THIS FILE EXISTS, AND WHAT IT IS NOT
    Written when the shipped workflow/kestra-build/scripts/validate_workflow.py
    implemented the anchor triple (§A1-A3) and the exit_criteria.progress FAIL
    (§A5) only, so that a README claiming "the fold refuses" would not be quoting
    an intention: it implemented the missing §A4 half here, in the eval directory,
    with the FAIL texts copied verbatim from
    workflow/kestra-build/references/ticket-fold.md.

    **§A4 has since been ported into validate_workflow.py from this file** (same
    checks, same texts), and the driver now runs the shipped validator on the same
    mutants — so the §A4 legs below are a second, independent implementation of
    checks the product now owns, kept because a port is worth diffing against the
    reference it came from. What is still eval-only, and stays so: F0/F1's
    git-side recompute-vs-recompute against the raise commit (needs git and a
    committed spec), the mid-run re-fold guard (kestra-build's own refusal, not a
    property of a finished artifact), and the progress owner-resolution ladder
    (the fold resolves the owner; the validator grades the copy it left behind).

    It is eval scaffolding, not a deliverable, and it is deliberately NOT
    installed anywhere. Stdlib only. It imports requirement_surface and
    validate_workflow's parse_yaml FROM THE RUN FOLDER (the frozen copies F5
    emits) and never from ~/.claude/skills or the skill directory — one
    normalizer, one parser, the run's own vintage.

Usage:
    python3 fold_check.py values <run-folder>            # F1-F4 compute, first-fold table
    python3 fold_check.py check  <run-folder> [--refold] [--raise-copy PATH]
"""
import hashlib
import re
import sys
from pathlib import Path

SOURCE_LABEL = re.compile(r"\s*\(Source:\s*[^()]*\)\s*$")
BLOCK = re.compile(
    r"<!-- ticket:begin (\S+) sha256:([0-9a-f]{64}) -->(.*?)<!-- ticket:end \1 -->", re.S)
BEGIN = re.compile(r"<!-- ticket:begin (\S+) sha256:([0-9a-f]{64}) -->")
STAGE_ID = re.compile(r"^\s*-\s+id:\s*(\S+)\s*$", re.M)
PROGRESS_BULLET = re.compile(r"^\s*[-*]\s+progress:\s*(.+)$")
BULLET_ANY = re.compile(r"^\s*[-*]\s+")
ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
TICKET_KEYS = ("id", "ref", "body_sha256", "ac_hash", "verified_against", "verified_at")


def load(run):
    """Import the run folder's own frozen extractor + YAML-subset parser."""
    sys.path.insert(0, str(run))
    import requirement_surface as rs
    import validate_workflow as vw
    return rs, vw


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def short(v):
    return str(v)[:12]


def normalize_ac(rs, line):
    """A ticket AC line, normalized exactly as requirement_surface._units does
    (list marker, checkbox, whitespace), then the trailing explicit Source label
    stripped with the narrow regex. Returns (normalized, explicit_source|None)."""
    s = rs._ws(rs._CHECKBOX.sub("", rs._BULLET.sub("", line.strip())))
    m = SOURCE_LABEL.search(s)
    explicit = None
    if m:
        explicit = m.group(0).strip()[len("(Source:"):].rstrip(")").strip()
        s = SOURCE_LABEL.sub("", s)
    return s, explicit


def section(text, heading):
    """Body lines of a '## <heading>' section, up to the next '## '."""
    out, on = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            on = line[3:].strip().lower() == heading.lower()
            continue
        if on:
            out.append(line)
    return out


def ticket_acs(rs, text):
    return [normalize_ac(rs, ln) for ln in section(text, "Acceptance criteria") if ln.strip()]


def progress_bullets(text):
    """(value, ...) from '## Exit Criteria', wrapped continuation lines joined
    with a single space — the only permitted transform."""
    values, open_value = [], False
    for line in section(text, "Exit Criteria"):
        m = PROGRESS_BULLET.match(line)
        if m:
            values.append(m.group(1).strip())
            open_value = True
        elif not line.strip() or BULLET_ANY.match(line) or line.startswith("**"):
            open_value = False
        elif open_value:
            values[-1] += " " + line.strip()
    return values


def derive(run):
    """F1-F3: everything the fold computes, with nothing read back from
    workflow.yaml. (rs, vw, surface, per-ticket dict, problems, warnings)"""
    rs, vw = load(run)
    problems, warnings = [], []
    surface = rs.extract_surface((run / "0-spec.md").read_text())
    rows = dict(surface.ac_rows)
    sources = {ac_id: row.split(" | ")[1] if " | " in row else ""
               for ac_id, row in surface.ac_rows}
    claims = {}
    tickets = {}
    for path in sorted((run / "tickets").glob("*.md")):
        tid = path.stem
        matched = []
        for n, (text, explicit) in enumerate(ticket_acs(rs, path.read_text()), 1):
            if text not in rows:
                problems.append(
                    f'ticket {tid} AC {n} "{text}" matches no row in the spec\'s AC Coverage Map — '
                    f"the slice set and the raised spec disagree. Either the spec moved after "
                    f"slicing (re-run to-tickets over the current spec — a suggestion, if "
                    f"installed), or the AC was edited on the tracker. kestra-build does not "
                    f"reconcile this; it stops.")
                continue
            if not sources[text]:
                problems.append(
                    f'sliced AC "{text}" resolves to an AC Coverage Map row with an empty Source '
                    f"cell — a green column that lies (validate_spec.py flags the same fact on the "
                    f"spec side).")
            elif explicit is not None and explicit != sources[text]:
                problems.append(
                    f'ticket {tid} AC {n} claims (Source: {explicit}) but the AC Coverage Map row '
                    f'says "{sources[text]}" — the map is the single owner; a ticket may echo it, '
                    f"never contradict it.")
            matched.append(text)
            claims.setdefault(text, []).append(tid)
        ordered = [row for ac_id, row in surface.ac_rows if ac_id in set(matched)]
        tickets[tid] = {
            "path": path,
            "body_sha256": sha256_file(path),
            "ac_hash": hashlib.sha256(("\n".join(ordered) + "\n").encode("utf-8")).hexdigest(),
            "ac_ids": matched,
            "sources": [sources[t] for t in matched],
        }
    for ac_id, _ in surface.ac_rows:
        owners = claims.get(ac_id, [])
        if not owners:
            warnings.append(f'AC Coverage Map row "{ac_id}" is covered by no ticket in this set')
        elif len(owners) > 1:
            warnings.append(f'AC Coverage Map row "{ac_id}" is claimed by {owners}')
    return rs, vw, surface, tickets, problems, warnings


def refresh_table(tickets, recorded, raise_commit):
    w = max([len(t) for t in tickets] + [6])
    lines = [f"{'ticket'.ljust(w)}  body_sha256   ac_hash                verified_against  status"]
    for tid, t in sorted(tickets.items()):
        prior = recorded.get(tid)
        if prior is None:
            status, was = "new", ""
        elif prior.get("body_sha256") == t["body_sha256"] and prior.get("ac_hash") == t["ac_hash"]:
            status, was = "unchanged", ""
        else:
            status = "refreshed"
            was = "" if prior.get("ac_hash") == t["ac_hash"] else f" (was {short(prior.get('ac_hash'))}…)"
        lines.append(f"{tid.ljust(w)}  {short(t['body_sha256'])}…  "
                     f"{(short(t['ac_hash']) + '…' + was).ljust(21)}  {short(raise_commit)}…      {status}")
    return "\n".join(lines)


def carrier_lines(tickets, raise_commit, version, at):
    return [f"Verified-against: {short(raise_commit)}… · ac_hash: {short(t['ac_hash'])}… · "
            f"extractor: v{version} · fold: {at}" for _, t in sorted(tickets.items())]


def cmd_values(run):
    rs, vw, surface, tickets, problems, warnings = derive(run)
    print(f"F1  extractor_version: {rs.EXTRACTOR_VERSION}")
    print(f"F1  surface_hash(0-spec.md): {surface.surface_hash}")
    print(f"F2  ac_rows in the map: {len(surface.ac_rows)}")
    for tid, t in sorted(tickets.items()):
        print(f"F2  {tid}: {len(t['ac_ids'])} AC(s) matched, sources={t['sources']}")
        print(f"F3  {tid}.body_sha256 = {t['body_sha256']}")
        print(f"F3  {tid}.ac_hash     = {t['ac_hash']}")
    for w in warnings:
        print(f"WARN: {w}")
    for p in problems:
        print(f"FAIL: {p}")
    print("\nF4 refresh table (first fold — nothing recorded yet):")
    print(refresh_table(tickets, {}, "<F0 raise commit>"))
    return 1 if problems else 0


def cmd_check(run, refold=False, raise_copy=None):
    rs, vw, surface, tickets, problems, warnings = derive(run)
    raw = (run / "workflow.yaml").read_text()
    wf = vw.parse_yaml(raw)
    anchor = wf.get("spec_anchor") or {}
    recorded = {t.get("id"): t for t in (wf.get("tickets") or []) if isinstance(t, dict)}

    # --- the one hard guard: a re-fold mid-run is a reworking-class event ---
    if refold:
        import json
        state = json.loads((run / "state.json").read_text())
        live = sorted(sid for sid, s in (state.get("stages") or {}).items()
                      if s.get("status") != "pending")
        if live:
            print(f"FAIL: refusing to re-fold — stages [{', '.join(live)}] are past 'pending'. A "
                  f"ticket\nchanged mid-run; the honest paths are (a) let kestra-run escalate to "
                  f"reworking (the design's one\nguaranteed human stop, which resets counters and "
                  f"unlocks the freeze), or (b) git reset --hard to the\npre-run commit and "
                  f"re-fold from there (destructive — confirm first). kestra-build does not\n"
                  f"reconcile a live run with a moved ticket.")
            return 1

    # --- F1 surface freshness: recompute vs recompute, never hash vs hash ---
    if str(anchor.get("extractor_version") or "").strip() != str(rs.EXTRACTOR_VERSION):
        problems.append(f"spec_anchor.extractor_version {anchor.get('extractor_version')} ≠ this "
                        f"run's EXTRACTOR_VERSION {rs.EXTRACTOR_VERSION} — not comparable; re-fold")
    elif surface.surface_hash != str(anchor.get("surface_hash") or "").strip():
        problems.append(f"spec_anchor.surface_hash {short(anchor.get('surface_hash'))} ≠ the "
                        f"surface of 0-spec.md recomputed now {short(surface.surface_hash)} — the "
                        f"spec moved since the fold; re-fold, do not edit the anchor")
    if raise_copy:
        as_raised = rs.extract_surface(Path(raise_copy).read_text()).surface_hash
        verdict = "equal — proceed" if as_raised == surface.surface_hash else "DIFFERENT — stop"
        print(f"F1  working tree {surface.surface_hash}")
        print(f"F1  as raised    {as_raised}   [{verdict}]")
        if as_raised != surface.surface_hash:
            problems.append("the spec's surface moved between the raise commit and the working "
                            "tree — re-raise (kestra-spec), or re-anchor to the current raise if "
                            "the human judges the slice boundaries intact (never automated)")

    # --- §A4 the tickets: map ---
    raise_commit = str(anchor.get("raise_commit") or "").strip()
    for tid, t in sorted(tickets.items()):
        rec = recorded.get(tid)
        if rec is None:
            problems.append(f"tickets/{tid}.md exists but no tickets[] entry names it — the map "
                            f"and the files are one fact")
            continue
        for key in TICKET_KEYS:
            if not str(rec.get(key) or "").strip():
                problems.append(f"tickets['{tid}'] is partial — '{key}' is missing")
        if str(rec.get("body_sha256")).strip() != t["body_sha256"]:
            problems.append(f"tickets['{tid}'].body_sha256 {short(rec.get('body_sha256'))} ≠ "
                            f"sha256(tickets/{tid}.md) {short(t['body_sha256'])} — re-fold")
        if str(rec.get("ac_hash")).strip() != t["ac_hash"]:
            problems.append(f"tickets['{tid}'].ac_hash {short(rec.get('ac_hash'))} ≠ recomputed "
                            f"{short(t['ac_hash'])} — re-fold")
        if str(rec.get("verified_against")).strip() != raise_commit:
            problems.append(f"tickets['{tid}'].verified_against "
                            f"{short(rec.get('verified_against'))} ≠ spec_anchor.raise_commit "
                            f"{short(raise_commit)} — the ticket map was refreshed against a "
                            f"different raise; re-fold")
        if not ISO_Z.match(str(rec.get("verified_at") or "")):
            problems.append(f"tickets['{tid}'].verified_at is not ISO-8601 UTC "
                            f"(YYYY-MM-DDTHH:MM:SSZ): '{rec.get('verified_at')}'")
    for tid in recorded:
        if tid not in tickets:
            problems.append(f"tickets[] entry '{tid}' has no tickets/{tid}.md")

    # --- §A4 the embedded blocks, read from the RAW text (the parsed brief is lossy) ---
    stage_at = [(m.start(), m.group(1)) for m in STAGE_ID.finditer(raw)]

    def owning_stage(offset):
        owner = "<before the first stage>"
        for pos, sid in stage_at:
            if pos < offset:
                owner = sid
        return owner

    matched_blocks = list(BLOCK.finditer(raw))
    if len(BEGIN.findall(raw)) != len(matched_blocks):
        problems.append("a ticket:begin delimiter has no matching ticket:end for the same id — a "
                        "partial delimiter, same family as a partial anchor")
    per_stage = {}
    for m in matched_blocks:
        tid, hex_, body = m.group(1), m.group(2), m.group(3)
        stage = owning_stage(m.start())
        per_stage.setdefault(stage, []).append(tid)
        path = run / "tickets" / f"{tid}.md"
        if not path.exists():
            problems.append(f"stage '{stage}' embeds ticket '{tid}' but tickets/{tid}.md does not "
                            f"exist")
            continue
        on_disk = sha256_file(path)
        if hex_ != on_disk:
            problems.append(f"ticket '{tid}' body changed since the fold (file {short(on_disk)} ≠ "
                            f"brief {short(hex_)}) — re-fold, never hand-edit the brief")
        if " ".join(body.split()) != " ".join(path.read_text().split()):
            problems.append(f"stage '{stage}' embedded ticket block does not match "
                            f"tickets/{tid}.md — the brief was hand-edited; re-fold")
        for seq in (" #", "---"):
            if any((seq in ln if seq == " #" else ln.strip() == seq) for ln in body.splitlines()):
                warnings.append(f"stage '{stage}' embedded ticket body contains '{seq}', which "
                                f"this repo's YAML-subset parser strips from the *parsed* brief — "
                                f"consumers must read the brief from the raw file")
        if tid not in recorded:
            problems.append(f"stage '{stage}' embeds ticket '{tid}' which is absent from tickets:")
    for stage, ids in per_stage.items():
        if len(ids) > 1:
            problems.append(f"stage '{stage}' embeds {len(ids)} ticket blocks {ids} — a brief with "
                            f"two blocks has no unambiguous owner for on_fail.target routing")
    for tid in tickets:
        if not any(m.group(1) == tid for m in matched_blocks):
            problems.append(f"ticket '{tid}' is embedded in no stage brief")

    # --- exit_criteria.progress: verbatim copy + owner resolution ---
    stages = wf.get("stages") or []
    by_id = {s.get("id"): s for s in stages if s.get("id")}
    owners_seen = {}
    for value in progress_bullets((run / "0-spec.md").read_text()):
        cmd = re.search(r"`([^`]+)`", value)
        cmd = cmd.group(1) if cmd else None
        exact = [sid for sid, s in by_id.items()
                 if cmd and " ".join(str((s.get("exit_criteria") or {}).get("run") or "").split())
                 == " ".join(cmd.split())]
        contains = [sid for sid, s in by_id.items()
                    if cmd and " ".join(cmd.split())
                    in " ".join(str((s.get("exit_criteria") or {}).get("run") or "").split())]
        named = [sid for sid in by_id if sid in value]
        if len(exact) == 1:
            owner, how = exact[0], "exact match"
        elif len(contains) == 1:
            owner, how = contains[0], "unique containment"
        elif len(named) == 1:
            owner, how = named[0], "named stage"
        else:
            cands = sorted(set(exact) | set(contains) | set(named))
            print(f'ASK: the spec bullet "progress: {value}" resolves to {len(cands)} candidate '
                  f"stage(s) {cands} — name the owner.")
            problems.append('the spec declares a loop-shaped check ("progress: …") that no stage '
                            "owns — kestra-run would have nothing to compare across attempts, so "
                            "clause 2 of the stop condition could never fire.")
            continue
        got = str((by_id[owner].get("exit_criteria") or {}).get("progress") or "")
        print(f"progress → '{owner}' by {how}: "
              f"{'byte-equal to the spec bullet' if got == value else 'NOT VERBATIM'}")
        if got != value:
            problems.append(f"stage '{owner}' exit_criteria.progress is not the spec bullet "
                            f"verbatim:\n  spec:  {value!r}\n  stage: {got!r}")
        if owner in owners_seen:
            problems.append(f"two progress bullets both resolved to stage '{owner}' — two stages "
                            f"comparing the same number is two answers to one question")
        owners_seen[owner] = value
        if (by_id[owner].get("on_fail") or {}).get("action") != "fixing":
            warnings.append(f"the metric on '{owner}' will never be compared — this stage does "
                            f"not retry")
    for sid, s in by_id.items():
        p = (s.get("exit_criteria") or {}).get("progress")
        if p and sid not in owners_seen:
            problems.append(f"stage '{sid}' carries exit_criteria.progress that no spec bullet "
                            f"produced — the copy is derived, not authored")

    print()
    print("F4 refresh table:")
    print(refresh_table(tickets, recorded, raise_commit))
    print()
    for line in carrier_lines(tickets, raise_commit,
                              anchor.get("extractor_version"),
                              (recorded.get(sorted(tickets)[0]) or {}).get("verified_at", "?")
                              if tickets else "?"):
        print(line)
    print()
    for w in warnings:
        print(f"WARN: {w}")
    for p in problems:
        print(f"FAIL: {p}")
    if problems:
        print(f"\n{len(problems)} problem(s) found — the fold refuses.")
        return 1
    print(f"FOLD OK — {len(tickets)} slices, {len(matched_blocks)} embedded blocks, anchor triple "
          f"present, {len(warnings)} warning(s).")
    return 0


def main():
    if len(sys.argv) < 3:
        print(__doc__.rsplit("Usage:", 1)[-1].strip())
        sys.exit(2)
    mode, run = sys.argv[1], Path(sys.argv[2]).resolve()
    args = sys.argv[3:]
    raise_copy = args[args.index("--raise-copy") + 1] if "--raise-copy" in args else None
    if mode == "values":
        sys.exit(cmd_values(run))
    if mode == "check":
        sys.exit(cmd_check(run, refold="--refold" in args, raise_copy=raise_copy))
    print(f"unknown mode: {mode}")
    sys.exit(2)


if __name__ == "__main__":
    main()
