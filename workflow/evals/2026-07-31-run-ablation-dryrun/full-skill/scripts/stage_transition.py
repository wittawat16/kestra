#!/usr/bin/env python3
"""Pure, zero-LLM reference implementation of kestra-run's per-stage fail/pass
decision (SKILL.md steps 1/3/5/6 — test-hash check, mechanical verify,
on-pass commit bookkeeping, on-fail attempt/escalation bookkeeping).

kestra-run itself has no engine like this — the loop in SKILL.md is followed by
whichever Claude gets spawned to orchestrate a real run, using real `git
diff`/`sha256sum`/exit-code commands. That's correct for the parts that
genuinely need judgment (writing code, reviewing a diff), but the fixing/
reworking/escalation *decision* itself is fully mechanical: given a stage's
on_fail config, its prior attempt/seen_diffs state, and this attempt's
outcome (write_scope respected? exit_criteria passed? diff hash), the next
state is a pure function with no ambiguity. Extracting it here means that
decision can be tested exhaustively without spawning a single subagent —
same reasoning as why kestra-build has validate_workflow.py instead of asking
an LLM to eyeball whether a generated workflow.yaml is well-formed.

Scope: single-stage transitions only. Multi-stage sibling-failure combining
(SKILL.md step 6's "more than one stage in this batch failed and shares the
same on_fail.target" rule) is NOT modeled here — that requires reasoning
about a batch of stages at once, not a single stage's own history, and is
left for a follow-up eval category.

`escalate_at` semantics: a repeated diff (the same normalized hash seen
before) gets a grace window of retries rather than an immediate stop — it
only forces `reworking` once `attempt >= escalate_at`. Below that
threshold, a repeat is treated like any other still-under-`max_attempts`
failure: retry. `max_attempts` remains an independent, unconditional
ceiling regardless of repeat status.

No reasoning-effort escalation: an earlier draft of SKILL.md prescribed
spawning each retry at one reasoning-effort tier higher than the last.
Checked against the actual Agent tool schema this environment provides —
`description`, `prompt`, `isolation`, `model`, `run_in_background`,
`subagent_type` — there is no `effort` parameter to set on that path. An
instruction with no mechanical way to execute either gets silently ignored
or faked via prompt text ("reason harder") — the latter is exactly the
kind of unverifiable vibes-based behavior kestra-run's own design principles
exist to rule out. Left out rather than kept as documentation-only cruft.
"""


def transition(on_fail, prior, result):
    """
    on_fail: dict from workflow.yaml's on_fail block for this stage —
        {'action': 'fixing'|'reworking'|'blocked', 'max_attempts': int,
         'escalate_at': int, 'target': str|None, 'reason': str|None}
        max_attempts/escalate_at required when action == 'fixing'.
        reason required when action in ('reworking', 'blocked').

    prior: this stage's current state.json entry —
        {'attempt': int, 'seen_diffs': list[str]}

    result: this attempt's real, already-executed outcome —
        {'write_scope_ok': bool, 'exit_criteria_passed': bool,
         'diff_hash': str|None}
        diff_hash is the normalized-diff hash for this attempt, or None
        when the stage produced no diff to hash (write_scope: [] and
        exit_criteria failed for a reason other than a code change, e.g.
        a command that isn't diff-shaped).

    Returns: {'stage_status': 'passed'|'fixing'|'reworking'|'blocked',
              'attempt': int, 'seen_diffs': list[str], 'reason': str|None}
    """
    action = on_fail.get("action")
    if action not in ("fixing", "reworking", "blocked"):
        raise ValueError(f"invalid on_fail.action: {action!r}")

    passed = bool(result.get("write_scope_ok")) and bool(result.get("exit_criteria_passed"))
    if passed:
        return {
            "stage_status": "passed",
            "attempt": prior["attempt"],
            "seen_diffs": list(prior["seen_diffs"]),
            "reason": None,
        }

    # A write_scope violation is a failure regardless of exit_criteria —
    # the orchestrator reverts the offending paths and this attempt still
    # counts against the retry budget. No special-casing needed here since
    # `passed` above already required write_scope_ok to be true.

    if action == "reworking":
        return {
            "stage_status": "reworking",
            "attempt": prior["attempt"],
            "seen_diffs": list(prior["seen_diffs"]),
            "reason": on_fail.get("reason"),
        }
    if action == "blocked":
        return {
            "stage_status": "blocked",
            "attempt": prior["attempt"],
            "seen_diffs": list(prior["seen_diffs"]),
            "reason": on_fail.get("reason"),
        }

    # action == "fixing"
    if on_fail.get("max_attempts") is None:
        raise ValueError("on_fail.action == 'fixing' requires max_attempts")
    if on_fail.get("escalate_at") is None:
        raise ValueError("on_fail.action == 'fixing' requires escalate_at")
    max_attempts = on_fail["max_attempts"]
    escalate_at = on_fail["escalate_at"]
    new_attempt = prior["attempt"] + 1
    diff_hash = result.get("diff_hash")
    seen_diffs = list(prior["seen_diffs"])
    repeated = diff_hash is not None and diff_hash in seen_diffs

    # A repeat past its grace window stops immediately, independent of
    # max_attempts — this is the "early" stop escalate_at exists for.
    if repeated and new_attempt >= escalate_at:
        return {
            "stage_status": "reworking",
            "attempt": new_attempt,
            "seen_diffs": seen_diffs,
            "reason": "same diff repeated at/after escalate_at — no progress, frozen spec/tests suspected",
        }

    if diff_hash is not None and diff_hash not in seen_diffs:
        seen_diffs.append(diff_hash)

    if new_attempt >= max_attempts:
        return {
            "stage_status": "reworking",
            "attempt": new_attempt,
            "seen_diffs": seen_diffs,
            "reason": f"max_attempts ({max_attempts}) exhausted",
        }

    # Either a genuinely new diff, or a repeat still inside its grace
    # window (new_attempt < escalate_at) — both get another attempt.
    return {
        "stage_status": "fixing",
        "attempt": new_attempt,
        "seen_diffs": seen_diffs,
        "reason": None,
    }
