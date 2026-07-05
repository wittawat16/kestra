#!/usr/bin/env python3
"""Mechanical, zero-LLM dry-run check for a workflow.yaml + state.json pair.

No third-party dependencies (PyYAML is frequently unavailable in a plain
python3 install) — parses the constrained YAML subset kestra-build actually
emits: block mappings, block/inline sequences, quoted/bare scalars, and
folded (">") or literal ("|") block scalars for `brief`. It does not aim to
be a general YAML parser.

Usage:
    python3 validate_workflow.py <dir-containing-workflow.yaml-and-state.json>

Exits 0 and prints "PASS" if the stage graph is structurally sound. Exits 1
and prints every problem found otherwise. This never asks an LLM's opinion —
every check here is a graph/set operation, on purpose: it's the same
"mechanical, not judged" standard kestra-run's own enforcement holds itself to,
just applied before the first stage ever runs instead of after.
"""
import sys
import re
import json
import fnmatch
from pathlib import Path


# ---------------------------------------------------------------------------
# Minimal YAML-subset parser
# ---------------------------------------------------------------------------

def _strip_comment(line):
    in_s = in_d = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            if i == 0 or line[i - 1] in (" ", "\t"):
                return line[:i]
    return line


def _parse_scalar(s):
    s = s.strip()
    if s == "" or s == "~" or s == "null":
        return None
    if s == "[]":
        return []
    if s == "true":
        return True
    if s == "false":
        return False
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        items = [_parse_scalar(x) for x in _split_flow(inner)]
        return items
    return s


def _split_flow(inner):
    parts, depth, cur, in_s, in_d = [], 0, "", False, False
    for ch in inner:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch in "[{" and not in_s and not in_d:
            depth += 1
        elif ch in "]}" and not in_s and not in_d:
            depth -= 1
        if ch == "," and depth == 0 and not in_s and not in_d:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def parse_yaml(text):
    raw_lines = text.split("\n")
    lines = []
    for ln in raw_lines:
        ln = _strip_comment(ln).rstrip()
        if ln.strip() == "" or ln.strip() == "---":
            continue
        lines.append(ln)

    pos = [0]

    def peek_indent():
        return _indent(lines[pos[0]]) if pos[0] < len(lines) else -1

    def skip_block_scalar(base_indent):
        # consumes a folded/literal block scalar body, returns joined text
        collected = []
        while pos[0] < len(lines):
            ln = lines[pos[0]]
            if ln.strip() == "" or _indent(ln) > base_indent:
                collected.append(ln.strip())
                pos[0] += 1
            else:
                break
        return " ".join(collected)

    def parse_block(min_indent):
        if pos[0] >= len(lines):
            return None
        first_indent = peek_indent()
        if first_indent < min_indent:
            return None
        stripped = lines[pos[0]].strip()

        if stripped.startswith("- "):
            return parse_sequence(first_indent)
        return parse_mapping(first_indent)

    def parse_sequence(seq_indent):
        items = []
        while pos[0] < len(lines) and peek_indent() == seq_indent and lines[pos[0]].strip().startswith("- "):
            ln = lines[pos[0]]
            content = ln.strip()[2:]
            if ":" in content and not content.strip().startswith(("[", '"', "'")):
                # inline mapping start, e.g. "- id: foo"
                fake_indent = seq_indent + 2
                lines[pos[0]] = " " * fake_indent + content
                item = parse_mapping(fake_indent)
                items.append(item)
            else:
                pos[0] += 1
                items.append(_parse_scalar(content))
        return items

    key_val_re = re.compile(r"^([A-Za-z0-9_\-\.]+):\s*(.*)$")

    def parse_mapping(map_indent):
        result = {}
        while pos[0] < len(lines) and peek_indent() == map_indent:
            ln = lines[pos[0]]
            stripped = ln.strip()
            if stripped.startswith("- "):
                break
            m = key_val_re.match(stripped)
            if not m:
                pos[0] += 1
                continue
            key, rest = m.group(1), m.group(2)
            pos[0] += 1
            if rest == "" :
                # nested block, or a following block scalar
                if pos[0] < len(lines) and peek_indent() > map_indent:
                    result[key] = parse_block(map_indent + 1)
                else:
                    result[key] = None
            elif rest in (">", "|", ">-", "|-", ">+", "|+"):
                result[key] = skip_block_scalar(map_indent)
            else:
                result[key] = _parse_scalar(rest)
        return result

    return parse_block(0)


# ---------------------------------------------------------------------------
# Structural checks
# ---------------------------------------------------------------------------

def fnmatch_overlap(pattern_a, pattern_b):
    """Conservative overlap check for write_scope globs.

    Two globs are treated as overlapping unless their literal (non-wildcard)
    directory prefixes are provably disjoint. This deliberately errs toward
    flagging a possible collision — a false positive here just means a human
    double-checks two write_scopes that were fine; a false negative would let
    a real collision through silently, which is the worse failure mode.

    When one side is a concrete path (no wildcard at all — e.g. a specific
    file an implement stage lists by name), match it against the other side
    with real glob semantics (`fnmatch`) instead of the directory-prefix
    heuristic. This is the common case in practice: an implement stage's
    write_scope is often exact filenames, and a test freeze scope is often a
    suffix glob like `**/*.test.tsx` — those two only really collide if the
    concrete file's name actually matches the glob, not just because it
    lives in the same directory as files that would.
    """
    def has_wildcard(p):
        return "*" in p or "?" in p or "[" in p

    if not has_wildcard(pattern_a) and not has_wildcard(pattern_b):
        return pattern_a == pattern_b
    if not has_wildcard(pattern_a):
        return fnmatch.fnmatch(pattern_a, pattern_b)
    if not has_wildcard(pattern_b):
        return fnmatch.fnmatch(pattern_b, pattern_a)

    def prefix(p):
        parts = []
        for seg in p.split("/"):
            if "*" in seg or "?" in seg:
                break
            parts.append(seg)
        return "/".join(parts)

    pa, pb = prefix(pattern_a), prefix(pattern_b)
    if pa == "" or pb == "":
        return True
    return pa.startswith(pb) or pb.startswith(pa)


def validate(workflow, state):
    problems = []
    warnings = []

    stages = workflow.get("stages") or []
    if not stages:
        return ["workflow.yaml has no stages"], warnings

    ids = [s.get("id") for s in stages]
    seen = set()
    for sid in ids:
        if not sid:
            problems.append("a stage is missing 'id'")
            continue
        if sid in seen:
            problems.append(f"duplicate stage id: {sid}")
        seen.add(sid)

    by_id = {s["id"]: s for s in stages if s.get("id")}

    # depends_on references exist
    for s in stages:
        sid = s.get("id", "<unknown>")
        deps = s.get("depends_on")
        if deps is None:
            problems.append(f"stage '{sid}' missing depends_on (use [] for a start stage)")
            deps = []
        for d in deps:
            if d not in by_id:
                problems.append(f"stage '{sid}' depends_on unknown stage '{d}'")

    # cycle detection
    def has_cycle():
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {sid: WHITE for sid in by_id}

        def visit(sid, chain):
            if color.get(sid) == GRAY:
                return chain + [sid]
            if color.get(sid) == BLACK:
                return None
            color[sid] = GRAY
            for d in (by_id[sid].get("depends_on") or []):
                if d in by_id:
                    result = visit(d, chain + [sid])
                    if result:
                        return result
            color[sid] = BLACK
            return None

        for sid in by_id:
            if color[sid] == WHITE:
                result = visit(sid, [])
                if result:
                    return result
        return None

    cycle = has_cycle()
    if cycle:
        problems.append(f"dependency cycle: {' -> '.join(cycle)}")

    # exactly one freeze_after: true
    frozen = [s["id"] for s in stages if s.get("freeze_after") is True]
    if len(frozen) == 0:
        warnings.append("no stage has freeze_after: true — no test-hash freeze point exists")
    elif len(frozen) > 1:
        problems.append(f"more than one stage has freeze_after: true: {frozen} — only the "
                         f"stage that generates/freezes tests should set this")

    frozen_scopes = []
    if frozen:
        frozen_scopes = by_id[frozen[0]].get("write_scope") or []

    # write_scope checks
    for s in stages:
        sid = s.get("id", "<unknown>")
        ws = s.get("write_scope")
        if ws is None:
            problems.append(f"stage '{sid}' missing write_scope (use [] if it produces no diff)")
            continue
        if frozen and sid != frozen[0]:
            for scope in ws:
                for fscope in frozen_scopes:
                    if fnmatch_overlap(scope, fscope):
                        problems.append(
                            f"stage '{sid}' write_scope '{scope}' overlaps the frozen test "
                            f"scope '{fscope}' owned by '{frozen[0]}' — only freeze_after and "
                            f"reworking may touch test paths"
                        )

    # pairwise overlap for stages that are NOT ordered relative to each other.
    # Skipped entirely when a cycle was already found above — ancestor chains
    # aren't well-defined until that's fixed, and the cycle problem alone is
    # enough to block treating this workflow as frozen.
    def ancestors(sid, memo={}, visiting=None):
        if visiting is None:
            visiting = set()
        if sid in memo:
            return memo[sid]
        if sid in visiting:
            return set()  # already reported as a cycle above; don't recurse forever
        visiting = visiting | {sid}
        result = set()
        for d in (by_id[sid].get("depends_on") or []):
            if d in by_id:
                result.add(d)
                result |= ancestors(d, memo, visiting)
        memo[sid] = result
        return result

    all_ids = list(by_id.keys()) if not cycle else []
    for i in range(len(all_ids)):
        for j in range(i + 1, len(all_ids)):
            a, b = all_ids[i], all_ids[j]
            if a in ancestors(b) or b in ancestors(a):
                continue  # ordered relative to each other, not a real collision risk
            ws_a = by_id[a].get("write_scope") or []
            ws_b = by_id[b].get("write_scope") or []
            if not ws_a or not ws_b:
                continue
            for sa in ws_a:
                for sb in ws_b:
                    if fnmatch_overlap(sa, sb):
                        warnings.append(
                            f"independent stages '{a}' and '{b}' have overlapping write_scope "
                            f"('{sa}' vs '{sb}') — if kestra-run may run them in parallel, this is "
                            f"a real collision risk, not just a style nit"
                        )

    # exit_criteria / on_fail shape
    valid_actions = {"fixing", "reworking", "blocked"}
    for s in stages:
        sid = s.get("id", "<unknown>")
        ec = s.get("exit_criteria")
        if not ec:
            problems.append(f"stage '{sid}' missing exit_criteria")
        else:
            t = ec.get("type")
            if t not in ("command", "artifact_exists", "human_approval"):
                problems.append(f"stage '{sid}' exit_criteria.type is missing/invalid: {t!r}")
            if t == "command" and not ec.get("run"):
                problems.append(f"stage '{sid}' exit_criteria.type is 'command' but 'run' is empty")
            if t == "artifact_exists" and not ec.get("artifact"):
                problems.append(f"stage '{sid}' exit_criteria.type is 'artifact_exists' but 'artifact' is empty")

        of = s.get("on_fail")
        if not of and (not ec or ec.get("type") != "human_approval"):
            problems.append(f"stage '{sid}' missing on_fail")
            continue
        if of:
            action = of.get("action")
            if action not in valid_actions:
                problems.append(f"stage '{sid}' on_fail.action is missing/invalid: {action!r}")
            if action == "fixing":
                if of.get("max_attempts") is None:
                    problems.append(f"stage '{sid}' on_fail.action=fixing missing max_attempts")
                if of.get("escalate_at") is None:
                    problems.append(f"stage '{sid}' on_fail.action=fixing missing escalate_at")
                ws = s.get("write_scope") or []
                target = of.get("target")
                if not ws and not target:
                    problems.append(
                        f"stage '{sid}' has write_scope: [] and on_fail.action=fixing but no "
                        f"'target' — the orchestrator would have nowhere to apply a fix"
                    )
                if target and target not in by_id:
                    problems.append(f"stage '{sid}' on_fail.target references unknown stage '{target}'")
            if action in ("reworking", "blocked") and not of.get("reason"):
                problems.append(f"stage '{sid}' on_fail.action={action} missing 'reason'")

    # human_approval stages skip on_fail by schema convention — nothing further to check there.

    # reachability: every stage should be reachable from a start stage ([] depends_on)
    starts = [s["id"] for s in stages if s.get("depends_on") == []]
    if not starts:
        problems.append("no stage has depends_on: [] — nothing can ever start")
    else:
        reached = set(starts)
        changed = True
        while changed:
            changed = False
            for s in stages:
                sid = s.get("id")
                if sid in reached:
                    continue
                deps = s.get("depends_on") or []
                if deps and all(d in reached for d in deps):
                    reached.add(sid)
                    changed = True
        unreachable = set(by_id) - reached
        if unreachable:
            problems.append(f"stages unreachable from any start stage: {sorted(unreachable)}")

    # state.json alignment
    if state is not None:
        state_stage_ids = set((state.get("stages") or {}).keys())
        workflow_ids = set(by_id.keys())
        if state_stage_ids and state_stage_ids != workflow_ids:
            missing_in_state = workflow_ids - state_stage_ids
            extra_in_state = state_stage_ids - workflow_ids
            if missing_in_state:
                problems.append(f"state.json missing stages present in workflow.yaml: {sorted(missing_in_state)}")
            if extra_in_state:
                problems.append(f"state.json has stages not present in workflow.yaml: {sorted(extra_in_state)}")

        if state.get("test_hash") not in (None, "null"):
            warnings.append("state.json.test_hash is not null at initial state — expected null before generate-tests runs")

    return problems, warnings


def main():
    if len(sys.argv) != 2:
        print("usage: python3 validate_workflow.py <dir-containing-workflow.yaml-and-state.json>")
        sys.exit(2)

    target = Path(sys.argv[1])
    wf_path = target / "workflow.yaml"
    state_path = target / "state.json"

    if not wf_path.exists():
        print(f"FAIL: {wf_path} not found")
        sys.exit(1)

    workflow = parse_yaml(wf_path.read_text())
    state = None
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except json.JSONDecodeError as e:
            print(f"FAIL: state.json is not valid JSON: {e}")
            sys.exit(1)
    else:
        print(f"WARN: {state_path} not found — skipping state.json alignment checks")

    problems, warnings = validate(workflow, state)

    for w in warnings:
        print(f"WARN: {w}")

    if problems:
        for p in problems:
            print(f"FAIL: {p}")
        print(f"\n{len(problems)} problem(s) found — fix before treating this workflow as frozen.")
        sys.exit(1)

    print(f"PASS — {len(workflow.get('stages') or [])} stages, structurally sound.")
    sys.exit(0)


if __name__ == "__main__":
    main()
