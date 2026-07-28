---
name: meta-debug
description: Four-mantra debugging discipline — reproduce, trace the fail path, falsify the hypothesis, cross-reference every breadcrumb — applied in order before any fix is proposed. Trigger proactively whenever debugging starts: a bug report, something broken/throwing/failing, a request to debug or investigate, a pasted stack trace, or a fix loop that keeps failing the same way without converging.
---

# meta-debug — Debugging Discipline (Reproduce → Trace → Falsify → Cross-reference)

**Role:** Root-cause a real failure before anyone proposes a fix. Reproduce it reliably, trace exactly where it breaks, try to disprove your own theory before trusting it, and keep every experiment in this session cross-referenced against every other one.

Self-contained — use directly for any bug. It's also the escalation path when a fix loop stops converging: `meta-qa`'s circuit breaker firing after five loops, or a `kestra-run` `fixing` loop burning attempts on the same diff before it escalates to `reworking`. Both are the same signal — the loop is guessing rather than root-causing, which is exactly what this discipline exists to stop.

---

## Recite this — verbatim, as the first thing in your first response

> **Mantra:**
> 1. **First is reproducibility.** Can the issue be reproduced reliably?
> 2. **Know the fail path.** Debugger first; then source trace + knob enumeration; then in-code instrumentation.
> 3. **Question your hypothesis.** What would disprove it?
> 4. **Every run is a breadcrumb.** Cross-reference all of them.

Then begin work.

---

## 1. Reproduce reliably

Build a runnable repro before anything else.

- **Reliable repro** → capture the exact steps, inputs, and environment as a runnable artifact: failing test, curl script, CLI invocation, replay harness.
- **Flaky repro** → the bug is not yet debuggable. Raise the rate first: loop the trigger, parallelise, add stress, narrow timing windows, inject sleeps. 50% flake is debuggable; 1% is not.
- **No repro at all** → stop. Say so explicitly. Ask the user for env access, captured artifacts (HAR, log dump, core), or permission to instrument. Do **not** proceed to hypothesise.

Target: a fast (1–5 s), deterministic pass/fail signal. Pin time, seed the RNG, freeze network, isolate filesystem.

## 2. Know the fail path

Once reproducible, find *where* the code breaks and *what stops it from breaking*. The differential narrows the search. Try in this order — escalate only when the prior tactic fails.

1. **Attach a debugger.** If the env supports it, attach and step to the failure site. One breakpoint beats ten logs. Do this **before** turning any knobs.
2. **Source trace + knob enumeration.** If no debugger (or it can't reach the bug), trace the code path end-to-end and list every knob that can influence the outcome:
   - config flags, env vars, feature toggles
   - branch conditions, input shape
   - timing, concurrency, build options
   Each knob is a candidate axis to flip in the differential. Flip one at a time.
3. **In-code instrumentation.** If outside knobs can't move the failure, go inside: `printf` / log statements at the suspected fail site, dump the relevant internal state. Tag every probe with a unique prefix (e.g. `[DBG-a4f2]`) so cleanup is a single grep. Let the trace show where reality diverges from your model.

## 3. Falsify the hypothesis

When a candidate root cause surfaces, scrutinise it **before** testing it.

- Does it actually explain the symptom end-to-end? Walk it through.
- What is the simplest **proof**? What is the cleanest **disproof**?
- Run the **disproof first**. If the hypothesis survives, it's real. If it dies, you saved yourself from chasing a phantom.
- Generate 3–5 ranked hypotheses, not one. Single-hypothesis thinking anchors on the first plausible idea.

## 4. Every run is a breadcrumb

Maintain a running **ledger** of every experiment in this session. Each entry: what changed, what happened, what it ruled in or out.

- When a new hypothesis surfaces, walk the ledger. Does it hold for **every** prior observation, not just the most recent?
- If any past run contradicts it, the hypothesis is wrong or incomplete — refine or discard.
- When in doubt, design the **single experiment** whose outcome makes it certain. Run that next, instead of churning on adjacent runs.
- Update the ledger after every run. It is your memory across the session.

---

## Operating rules

Recite the mantra verbatim once, in your first response, then don't repeat it — it's a constraint you carry through the session, not advice to keep delivering back to the user. If asked to skip it, skip the recital and still apply the four steps.

The four gates, in order — each is a "do not proceed until":

1. No fix proposed before a reliable repro exists. Catch yourself skipping ahead → return to step 1.
2. No hypothesis tested before the fail path is narrowed.
3. No hypothesis committed to before a disproof was attempted.
4. No hypothesis declared correct until it holds against every prior breadcrumb.

---

## Handoff

- Root cause confirmed (step 3 disproof survived, step 4 ledger agrees) → hand the fix to `meta-dev` (or apply it directly if called standalone, outside the pipeline) — this skill's job ends at a *proven* root cause and a well-scoped fix, not at re-verifying the fix itself.
- Fix applied → back to `meta-qa` for independent re-verification. Never self-certify a debugging session's own fix as done.
- No reliable repro obtainable even after raising the flake rate → surface that explicitly to whoever called this (caller or user), same as `meta-qa`'s circuit breaker — an honest "can't reproduce yet" beats a guessed fix.
