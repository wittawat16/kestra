---
name: meta-orc
description: >
  Lightweight auto-chaining orchestrator for the meta/ role library (meta-spec, meta-designer,
  meta-dev, meta-test-writer, meta-qa, meta-test-review, meta-review, meta-security, meta-devops). Spawns each stage's
  subagent in sequence automatically, feeds each one the right context, and stops the moment
  any stage comes back non-clear (meta-qa PARTIAL/NOT_DONE, review CHANGES_REQUESTED) — no
  auto-retry, no write-scope allowlist, no test-hash freeze, no commit-per-stage. This is the
  fast/cheap alternative to kestra-build + kestra-run's TDD-locked stage machine: use it when a
  human reviewer already exists downstream and the mechanical enforcement isn't worth the
  overhead. Trigger on "orchestrate the meta skills", "chain meta-dev/meta-qa/meta-review for
  me", "run the meta pipeline end to end", "auto-run design then dev then qa then review",
  "meta-orc this", or whenever the user wants the meta/ role library run start-to-finish without
  manually invoking each skill themselves.
---

# meta-orc — Auto-Chain Orchestrator for the meta/ Role Library

**Role:** Run the `meta/` role skills back-to-back on one feature/fix, spawning each stage as a
subagent and wiring its output into the next stage's input — so the user doesn't have to
manually invoke `meta-dev`, then `meta-qa`, then `meta-review` themselves. It adds **sequencing
only**. It does not add write-scope enforcement, a test-hash freeze, or per-stage commits — those
are `kestra-build`/`kestra-run`'s job, and the whole reason this skill exists is to skip that
machinery when it isn't worth the overhead.

**Read this before using it:** [`meta/README.md`](../README.md) frames the role library as
deliberately un-orchestrated — "no fixed orchestrator chains them... call one directly, chain
them yourself." That's still true of the role skills themselves; none of them gained shared
machinery. `meta-orc` is an *opt-in* wrapper one level up — it doesn't change how any individual
`meta-*` skill works, it just automates the handoffs between them for the case where a user wants
that. Keep using the role skills directly when you want to drive a stage yourself, inspect an
intermediate result before proceeding, or run just one of them standalone.

---

## meta-orc vs. kestra-build + kestra-run — pick deliberately, not by default

| | `meta-orc` | `kestra-build` + `kestra-run` |
|---|---|---|
| Write-scope allowlist | none | enforced at apply time |
| Test-hash freeze | none | mechanical, halts on mismatch |
| Commit-per-stage | none — one working tree, user commits when ready | every stage, rollback-ready |
| Fix loop | none — first non-clear verdict stops and hands back to the user | bounded `fixing` retries, escalates to `reworking` |
| Artifact | a run summary in chat (and an optional log file) | `workflow.yaml` + `state.json`, resumable from disk |
| Best for | a task with a human reviewer downstream anyway, low/medium risk, root cause already clear, want speed | TDD-locked, auditable, resumable pipelines; higher-risk or multi-session work |

If the task would benefit from write-scope enforcement, a frozen-test invariant, or resumability
across sessions, say so and point the user at `kestra-build` instead — don't quietly run
`meta-orc` on something that actually wanted the heavier machine. When in doubt, ask.

---

## What actually exists in `meta/` — check before assuming

Only **ten** skills are live: `meta-spec`, `meta-designer`, `meta-test-writer`, `meta-dev`,
`meta-qa`, `meta-test-review`, `meta-review`, `meta-security`, `meta-devops`, `meta-debug`.
Four names that show up in some
`CLAUDE.md` configs — `meta-architect`, `meta-ba`, `meta-pm`, `meta-sa` — are **retired**:
`workflow/kestra-spec` now does all four of their jobs inline in a single pass (see
`install.sh`'s `RETIRED_SKILLS` and `meta/README.md`). `meta-orc` only ever spawns the ten real
skills. Note that `meta-spec` is *not* a revival of the retired four — it's a deliberately lean
AC-and-flags pass, and it escalates to `kestra-spec` rather than trying to cover what that
skill's invariant/constraint tables exist for. If a `CLAUDE.md` you're working from still references one of the retired four, flag that
as stale rather than trying to spawn a skill that no longer exists.

---

## Stage graph

```
        ┌─ no spec? ── meta-spec ──┐  ┌─ needs_ui? ── meta-designer ──┐  ┌─ tests_first? ── meta-test-writer ──┐
        │                           │  │                                │  │   (+ meta-test-review, if doubles)  │
(start)─┴───────────────────────────┴──┴────────────────────────────────┴──┴─────────────────────────────────────┴──▶ meta-dev ──▶ meta-qa ──▶ meta-review+security ──▶ needs_devops? ── meta-devops ──▶ (done)
```

* `meta-spec` runs first when the caller supplied a rough ask rather than a spec — it produces
  the acceptance criteria and the flags every later stage reads, so skipping it on a vague ask
  means every downstream stage guesses independently. Skip it when a usable spec already exists
  (`0-spec.md`, or an AC list with the flags already settled); read that spec's flags directly
  instead of re-deriving them. If `meta-spec` comes back saying the work should escalate to
  `kestra-spec`, **stop the chain and surface that** — it's a stop condition like any other
  non-clear verdict, not a suggestion to note and run past.
* `meta-designer` only runs when the feature touches UI (see flag table below). Its output
  (`design.md` + artifact) feeds both `meta-dev` (component/token constraints) and
  `meta-review` (token/component consistency check).
* `meta-test-writer` runs before `meta-dev` when `tests_first` is on — it writes the BDD scenario
  table and a deliberately-red test suite from the acceptance criteria, which `meta-dev` then
  implements against. Off by default: it costs a full extra spawn, and its payoff (an
  implementation that can't shape its own assertions) only matters when the ACs are substantive
  enough that a hollow test would actually slip past. **`meta-orc` cannot freeze what it
  writes** — nothing mechanically stops `meta-dev` from editing a test to pass, unlike
  `kestra-run`'s test-hash. Say that plainly when a user turns this on expecting TDD-lock; the
  honest answer is `kestra-build`, not a claim this skill can't back.
* `meta-test-review` is **not** in the default chain either. It belongs between "tests written"
  and "tests frozen," and `meta-orc` has no freeze step — so it only earns its spawn when
  `tests_first` is on **and** the suite fakes an external dependency (or straddles two paths that
  must agree). Without `tests_first` there are no pre-implementation tests for it to read at all.
* `meta-debug` is never auto-spawned. It's the tool you reach for **after** `meta-orc` stops on a
  `meta-qa` failure, when the failure looks like a real bug rather than a spec gap — see
  "On stop" below.
* `meta-review` and `meta-security` run as **one spawn**, per `meta-review`'s own guidance — an
  agent reading the diff for correctness already holds what the security checklist needs, so
  spawning them separately pays twice to read the same diff.

---

## Flags — read them off the spec, or derive and label as inferred

**When `meta-spec` ran (or a spec already exists), the flags are already set — use them
verbatim.** They're a decision someone stood behind; re-deriving them here just invites a second
opinion the pipeline has no way to reconcile. Only derive these yourself when the caller supplied
a rough ask and no spec stage ran, and in that case say plainly which values are inferred so the
user can correct one before the first spawn goes out.

| Flag | Trigger | Consequence |
|---|---|---|
| `needs_ui` | any new/changed page, route, modal, form, or interactive element — a single added button qualifies | `meta-designer` runs before `meta-dev`; its `design.md` is passed to `meta-dev` and `meta-review` |
| `needs_devops` | new/changed env vars, migrations, feature flags, or infra | `meta-devops` runs after `meta-review` passes |
| `tests_first` | **off unless asked** — the user requests tests-first/BDD/TDD, or the spec's ACs are already written Given-When-Then | `meta-test-writer` runs before `meta-dev`; `meta-test-review` follows it only if the suite fakes an external dependency |

`tests_first` is the one flag not inferred from the task's shape, because unlike the other two it
buys discipline rather than covering a surface — nothing in a task description tells you whether
the caller wants to pay a spawn for it. Default off; turn it on when asked, or when the ACs
arrive already in Given-When-Then form (that's the author signalling the intent), and say which
of the two triggered it.

---

## Process

### 1. Gather input, confirm the plan once

Read whatever the user handed you — a `0-spec.md`, a rough task description, an existing
`design.md`.

**If there's no usable spec, `meta-spec` is stage one** and the flags come out of it rather than
out of your own reading. That ordering matters most when `tests_first` is on: `meta-test-writer`
maps acceptance criteria 1:1 into scenarios, so a vague AC becomes a vague test, and no
downstream stage recovers what the spec never pinned down. Show the stage list this run will
actually execute (with which stages are skipped and why) **once**, before the first spawn — this
is the only confirmation point; once the user says go, the chain runs stage-to-stage without
asking again, same posture as `kestra-run`'s single up-front confirmation. When `meta-spec` is in
the list, note that stages after it are provisional: its flags decide the rest of the chain, so
the plan can legitimately change shape once it returns.

### 2. Spawn each stage in order

For each stage in the resolved list, spawn a subagent (Agent tool) whose prompt:
- Names the `meta-*` skill to use (e.g. "Use the `meta-dev` skill to implement the following...")
  — never hard-codes the skill's own instructions inline; let the subagent load them via Skill.
- Includes the **context pack** (below).
- Asks for the skill's own defined output format verbatim — `meta-orc` doesn't invent a report
  shape on top of what each skill already produces.

Run stages **sequentially, not in parallel** — each one's output is the next one's input, unlike
`kestra-run`'s independent-`write_scope` siblings. The one exception is the combined
`meta-review`+`meta-security` spawn, which is a single subagent doing both checklists in one
pass, not two spawns to parallelize.

**Context pack — what to hand each stage:**
- The task description / relevant `0-spec.md` sections, pasted in full — not a paraphrase.
- `design.md`'s path + key constraints, if `needs_ui` and a prior `meta-designer` stage produced
  one.
- The previous stage's output artifact, in full (implementation notes, verify report, review
  verdict) — the next stage's own skill already tells it to treat this as a claim to check, not a
  fact, so pasting it isn't the same as trusting it.
- `git diff --stat` since the chain started, once `meta-dev` has run — cheap, and lets every
  downstream stage orient on the real change instead of the prose describing it.

### 3. On stop — first non-clear verdict, no exceptions

The moment any stage returns something other than a clean pass —
`meta-qa`'s `🟠 PARTIAL` or `⛔ NOT_DONE`, `meta-review`/`meta-security`'s
`VERDICT: CHANGES_REQUESTED`, `meta-spec`'s escalation check saying this belongs in `kestra-spec`,
or a non-empty **Open Items** the rest of the chain would have to guess past — **stop the chain
immediately.** Don't retry the stage, don't route
around it, don't invent a fix-and-reverify loop of your own. Report to the user:
- which stage stopped it
- the stage's own verdict/evidence, quoted, not paraphrased
- a plain read on what kind of gap this looks like: a small fixable diff issue (send back to
  `meta-dev` once, with the specific finding), or something that looks like a real bug worth
  `meta-debug`'s reproduce → trace → falsify discipline (suggest it explicitly, don't invoke it
  yourself)

This mirrors why `kestra-run` keeps `reworking` as its one guaranteed human stop — a stage that
returns "not done" or "changes requested" is telling you something the pipeline doesn't have the
judgment to route around safely on its own. Resuming after a stop is manual: the user (or you,
told to continue) re-runs the stage that stopped, referencing what changed, then re-enters the
chain from there. There is no `state.json` to read back from — that persistence is a deliberate
trade against `kestra-run`, not an oversight; say so if a user seems to expect resumability.

### 4. On completion

Once every resolved stage has a clean pass, write a short run summary (in chat, or as
`meta-orc-log.md` next to the spec if one exists) — which stages ran, which were skipped and why,
final verdicts, and the real `git diff --stat`. This is the point where the user commits,
opens a PR, or hands off to whatever human review process the task actually needs — `meta-orc`
does not commit or push on its own.

---

## Optional stages — not in the default chain, insert deliberately

* **`meta-test-writer`** — gated on `tests_first` (see flag table). When on, it runs before
  `meta-dev` and its scenario table + red suite go into `meta-dev`'s context pack as the thing to
  implement against. `meta-dev`'s brief in that case should say the suite is the contract: make it
  green, and if a test looks *wrong*, raise it rather than edit it — `meta-orc` can't enforce that
  boundary mechanically, so the instruction is the only thing holding it.
* **`meta-test-review`** — only when `tests_first` is on **and** the suite it produced mocks an
  external dependency or straddles two paths that must agree (same trigger condition as its own
  `SKILL.md`). Slots between `meta-test-writer` and `meta-dev`. `meta-orc` has no freeze point, so
  there's no mechanical reason to always run it — it earns its spawn only when there's a real
  double to check.
* **`meta-debug`** — never auto-spawned; see "On stop" above. Also the right tool to reach for
  directly, standalone, any time a bug report shows up mid-chain that isn't really about the
  current stage's verdict (e.g. the user reports something broken while `meta-orc` is mid-run on
  something else).

---

## Mindset

- **Sequencer, not a second enforcement layer.** Every safety property this skill has comes from
  the individual `meta-*` skills' own "don't grade your own homework" discipline — `meta-orc`
  doesn't add write-scope, freezing, or independent re-verification of its own. If the user needs
  those, that's `kestra-build`/`kestra-run`, not this.
- **Honest about the trade.** Faster and cheaper because it skips real safety machinery — say so
  plainly when recommending it, don't let "orchestrated" imply "as safe as kestra."
  Never auto-select `meta-orc` over `kestra-build` — the pick is the user's, and the comparison
  table above is what informs it, not a default this skill applies silently.
- **One stop, not a loop.** The value of stopping immediately on the first non-clear verdict is
  that nothing gets papered over by an automatic retry the user never saw. An honest stop beats a
  quiet second attempt.

## Handoff

→ the user, always, at either a clean completion or the first stop. `meta-orc` never opens a PR,
never commits, and never re-invokes itself past a stop — the human decides what happens next.
