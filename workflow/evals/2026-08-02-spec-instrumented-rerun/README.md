# Eval — kestra-spec, instrumented re-run in its Wave-2 grown shape + the reopen-tripwire thresholds

Wave 1 of the prep-chain implementation (spec: `arkaphat/arkaphat-builder#31`, ticket: `#33`). Not an
ablation and not an OLD-vs-NEW comparison — a **measurement**. Spec #31's Implementation Decisions
make the ordering binding: *"the instrumented re-run is the first item, before any skill file
changes"*, and *"Threshold numbers are set at measurement time."* This directory is that measurement
and those numbers. No skill file changes in this wave.

The question being answered is narrow and it is not "is the spec good". It is: **has the kestra-spec
pass, once it carries the Wave-2 template obligations, grown heavy enough that the parked seam
question (split kestra-spec, or leave it whole) has to reopen before Wave 2 reshapes the skill?**

## 1. What was measured, and how

### Three agents, one feature

The feature is a live operator console over the repo's in-memory retry queue — chosen because it
forces `needs_ui` *and* `needs_sa` to fire honestly (a whole new set of screens; two architecture
choices the idea deliberately leaves unresolved), which every prior kestra-spec eval failed to do.
`2026-07-31-spec-ablation-cherny/README.md` closes by naming exactly this gap: *"Doesn't test the
flagged-work sections … a UI- or BA-heavy idea is the next fixture needed."*

**Up front, because it gates the verdict:** the *target codebase* is still the 74-line cherny
fixture, which #31's Wave-1 qualifier explicitly excludes. The intent-layer and flag qualifiers hold
literally; the codebase one does not. This is not a footnote — it is a standing precondition on
§6's NOT FIRED, spelled out there and in §8.

| Agent | Role | Measured subject? |
|---|---|---|
| `a4e7bb76c372cbc12` | wrote `idea-operator-console.md` (the post-grilling rough idea) and the fixture copy | **no** — setup |
| `a2159129daab815de` | **to-spec pass** — rough idea → vetted-shaped spec ticket (`to-spec-pass/spec-ticket.md`) | **yes** |
| `a636ab804a0b8eb1e` | **kestra-spec pass in grown shape** — ticket → `spec-pass/0-spec.md` | **yes** |

All three ran as workflow subagents on **opus** (claude-opus family), clean-room: each began from an
empty context with only its own prompt, and each read the real skill file off disk
(`workflow/kestra-spec/SKILL.md` for the spec pass, `~/.claude/skills/to-spec/SKILL.md` for the
to-spec pass) rather than being handed a paraphrase. Context window: **200,000 tokens**.

### The grown shape, hand-simulated

Wave 1 ships no skill edits, so the six Wave-2 template obligations were imposed on the pass by
prompt and verified present in the output. All six landed:

| # | Obligation (spec #31) | Where it landed in `spec-pass/0-spec.md` |
|---|---|---|
| 1 | `## External Interface` section | line 26 — HTTP boundary as the primary seam, five routes, queue-module seam as secondary, "deliberately absent seams" enumerated |
| 2 | `Source` column in the AC Coverage Map | line 578 — header is `\| AC \| Source \| Covered by (files/steps) \|`; all 38 rows carry it |
| 3 | Provenance rule on every intent line the raise adds | lines 5–11 — a provenance key (`US-n` / `ID§x` / `TD` / `FN` / `OOS` / `PS` / `⚠ inferred` / `verified:<probe>`); **11** `⚠ inferred` marks, **49** `verified:probe-*` citations |
| 4 | `## Exit Criteria` — two-clause stop head line + one `progress:` fragment per loop-shaped check | line 677 — head line is *"every AC-1..AC-38 passes … **or** two consecutive attempt rounds pass without the relevant progress number below moving, at which point stop and summon the human"*; **6** `progress:` fragments; four single-shot checks explicitly carry none |
| 5 | Recorded mode-prediction fact | line 699 — `## Mode Prediction`, `full`, with the reason stated |
| 6 | Delimiter precondition (stable section delimiters, no bare `##` inside the requirement surface) | lines 13–16 — asserted, and mechanically re-checked by the pass itself (fence-open count 0, `^## ` yields exactly the 21 template sections) |

**Two-commit front job, also simulated.** Materialization ran as commit 1 = verbatim, commit 2 = the
raise, but as *files*, not as git objects: the pass copied the ticket to
`spec-pass/0-spec-verbatim.md` and recorded `sha256`. Re-checkable here:

```
$ shasum -a 256 to-spec-pass/spec-ticket.md spec-pass/0-spec-verbatim.md
6fdcee78ec16b752854f52eb01629e1c2d4fc3878c747dee6ece55be6ed090f4  to-spec-pass/spec-ticket.md
6fdcee78ec16b752854f52eb01629e1c2d4fc3878c747dee6ece55be6ed090f4  spec-pass/0-spec-verbatim.md
```

No `git commit` was run by either agent (verified by replaying every `Bash` call in both
transcripts). What the simulation costs, it costs in the *raise*; what it does not exercise is the
commit-message/URL leg of stories 5–6. That leg is Wave 2's to prove.

### The extraction method

Numbers come from the raw API transcripts, not from what the agents said about themselves.
`extract_usage.py` (copied here, stdlib only) is the whole instrument:

```
python3 extract_usage.py \
  ~/.claude/projects/-Users-arkaphatp-Documents-HUN-dev-hun-registry-skill-kestra/\
0311f967-596c-4138-ae8d-aaa0e98efffb/subagents/workflows/wf_dc271539-ca8
```

Definitions, exactly as the script computes them:

- **requests** — assistant messages carrying a `usage` block (one per API request).
- **tool_calls** — `tool_use` blocks in assistant messages.
- **output_tokens** — Σ `usage.output_tokens` over all requests.
- **peak_context** — `max` over requests of
  `input_tokens + cache_read_input_tokens + cache_creation_input_tokens + output_tokens`.
  Cache reads are counted as occupancy, because occupancy is what exhausts a window; a cached token
  still sits in it. This is the fullest the window got at any single moment of the pass.
- **wall_s** — last transcript timestamp minus first.

This is a different instrument from the earlier evals in this folder, which quote harness-reported
"subagent tokens" (e.g. cherny's 143,246 / 139,514). **Do not compare across the two** — see
§8.

## 2. Numbers

| | **kestra-spec — grown shape** | **to-spec — paired pass** | ratio (to-spec ÷ spec) |
|---|---:|---:|---:|
| Requests | 65 | 27 | 41.5% |
| Tool calls | 31 | 16 | 51.6% |
| Output tokens | 55,913 | 26,692 | 47.7% |
| **Peak context** | **113,004** | **64,785** | 57.3% |
| Peak as % of the 200k window | **56.50%** | 32.39% | — |
| Wall time | 818 s | 393 s | 48.0% |

Chain totals across the two measured passes: 92 requests · 47 tool calls · 82,605 output tokens ·
1,211 s wall.

Artifacts produced: raised `0-spec.md` = **745 lines / 21 `##` sections / 38 ACs**, with **all 52** of
the ticket's user stories traced (`US-1`…`US-52` each appear at least once in the raise);
`spec-ticket.md` = **430 lines / 52 stories**; verbatim copy `sha256`-identical to the ticket;
**7** open items (OI-1…OI-7).

Footnote — the fixture author (`a4e7bb76c372cbc12`) measured 19 requests · 11 tool calls · 7,205
output tokens · peak 48,496 (24.25% of window) · 150 s. **Excluded from the subjects**: it authored
the idea and staged the fixture, work that in a real run is the human's, not the chain's.

## 3. Flags evidence — `needs_ui` and `needs_sa` both fired

`## Flags` (line 661) records `needs_ba: false` · `needs_ui: true` · `needs_sa: true` ·
`needs_devops: false`. The flags are not the evidence; the sections they gate are.

**`needs_ui: true` → step-3 UI work is real, not a stub.**

- `### Component Audit` (line 283) — nine components (`StatusBanner`, `SummaryGrid`, `FilterBar`,
  `MessageTable`, `DetailPanel`, `PayloadBlock`, `ConfirmPanel`, `EmptyState`, `ErrorState`), each
  with a reuse verdict, a token reference, and a story citation. Every row reads `new`, and the
  section says why in a checkable way: *"There is no CSS, no component, no token, no design system,
  and no markup of any kind in this repo today — verified, not assumed"*, backed by a `find` over the
  whole four-file tree.
- `### Token Mapping` (line 300) — a hardcoded baseline (`--oc-bg`/`--oc-fg`/`--oc-muted`/`--oc-rule`,
  `--oc-ok`/`--oc-warn`/`--oc-bad`, a 3-step spacing scale, `--oc-tap: 44px`, `--oc-maxw`), plus a
  glyph vocabulary (`●` LIVE / `▲` STALE / `✕` ERROR / `✓` MOVED / `◍` COMPLETED / `…` TRUNCATED) so
  colour is never load-bearing.
- `### Screen States` (line 319) — a 5-view × 4-state table, all 20 cells filled. The three cells that
  cannot exist are marked **"Impossible by design, stated not skipped"** with the reason (fully
  server-rendered ⇒ no artificial loading state), which is the honest form of a filled cell.
- The UI work is carried into testable form as `AC-29`…`AC-33`, not left as prose.

**`needs_sa: true` → three decisions, each with a 3-approach table.**

- `## Solution Architecture` (line 331). **Decision 1** — state access: A direct reference (chosen) /
  B event hook / C snapshot file, rejected against `US-43`/`US-45`/`US-28`. **Decision 2** —
  freshness transport: A polled fragment (chosen) / B SSE / C timed full reload. **Decision 3** — the
  in-flight representation, *decided on execution evidence*, not on reading (see §7).
- Followed by integration contracts, data-model impact (three additive fields), and NFR targets
  carrying measured numbers (`0.35 ms` per summary at 10k; `~8 KB` vs `~431 KB` payload at
  `ROW_CAP = 200`), each tagged `verified:probe-c`.

**`needs_ba: false`, in the spec's own words** — *"the ticket settles every domain rule (requeue
semantics, three outcomes, id resolution, enqueue-time immutability, filter whitelist, error
retention) and both stakeholder roles across 52 stories; nothing is vague on what. The residual gaps
are numeric thresholds, not rules — bounced upstream in OI-5/OI-6 rather than authored here."* That
is the posture spec #31 asks for (`needs_ba` on genuine intent-silence bounces upstream, it does not
author business rules inline), and it fired correctly: the two genuinely unset numbers (`POLL_MS`,
`STALE_MS`) left as `⚠ inferred` defaults *and* bounced, rather than laundered into a Business Rules
section.

**Mode prediction: `full`** (line 699), reason recorded — two seams, 38 ACs including a security-shaped
escaping sweep and a conservation invariant, so the write-tests/freeze-tests split is load-bearing.

## 4. The token-neutrality instrument (spec #31, story 3)

Story 3 wants *"the PM work moved up, roughly token-neutral"* to become a number. The paired pass is
that instrument, and this is the honest reading of what it now shows and does not show.

**What the pairing establishes.** The moved-up front half is a real, measured, roughly-half-sized
pass: to-spec costs 47.7% of the raise's output tokens, 41.5% of its requests, and 57.3% of its peak
context, on the same feature, same model, same day. The two halves of the new chain sum to 82,605
output tokens and 1,211 s. Both halves fit in one window with room to spare; neither is a runaway.

**What it does not establish.** There is **no third arm**. Neutrality is a claim about
*new-total vs old-total* — the chain (to-spec + raise) against today's single kestra-spec pass driven
straight off `idea-operator-console.md` with no vetted ticket. That run was not performed. Nothing
here licenses "the chain is token-neutral"; what is licensed is "the instrument for that claim is
built, calibrated, and its first half is on the record". The missing arm is one clean-room subagent
away and is the obvious first addition if Wave 2 wants the claim itself.

Two further limits worth stating plainly: (a) the split is *not* free by construction — the ticket is
read in full by the raise pass, so the intent layer is paid for twice, once to write and once to
read; the pairing measures that double payment but cannot say whether it beats the single pass; (b)
the to-spec pass wrote its "ticket" as a file and no human vetted it, so the vet-loop cost — the part
of the design that actually justifies moving PM work upstream — is measured at zero here and is not
zero in reality.

## 5. TRIPWIRE THRESHOLDS

Spec #31 names two axes and defers the numbers to now: *"If measured numbers hit the tripwire (pass
weight approaching the per-spawn floor, or peak context nearing exhaustion), the seam question
reopens before any later wave proceeds."*

### Axis A — pass weight vs. the per-spawn floor

**Pass weight** here is not what the pass *cost*; it is what the chain makes **every later spawn
carry**. Under today's kestra-run, the context pack pastes the raised `0-spec.md` into every stage
spawn — the tax `2026-07-31-spec-ablation-cherny/README.md` already flagged as *"a real, recurring
tax, not a one-time stylistic issue"*. So pass weight = the token weight of `spec-pass/0-spec.md`.

**Measuring it, method stated.** The repo forbids third-party dependencies, so there is no tokenizer
on hand. The weight is therefore bracketed by two figures that are both reproducible from stdlib and
from the transcript:

| | figure | basis |
|---|---:|---|
| File size | 62,163 chars / 62,751 bytes / 745 lines | `wc` |
| **Floor estimate** | **15,541 tokens** | `chars ÷ 4`, the standard English-prose heuristic. Optimistic here: this file is table-, backtick- and identifier-dense (`AC-29`, `--oc-space-2`, `US-44`), all of which tokenize worse than prose. |
| **Ceiling estimate** | **27,689 tokens** | Harness-anchored. The single `Write` turn that emitted the file reported `output_tokens = 27,240` for 61,155 chars of body; scaled to the final 62,163-char file ⇒ 27,689. A genuine over-count — that request's `output_tokens` also covers the tool-call JSON envelope and the turn's own reasoning — hence a ceiling. |

**The floor it is compared against.** From `2026-07-31-run-live-implement-context-pack/README.md`:
one real `implement` stage spawn cost **121,081 tokens**, and that eval marks it *"hard — this
orchestrator returned early and the child's completion arrived as its own separate notification, so
this number is harness-verified"*. Its sibling figure (~146,000, MINIMAL) is explicitly self-reported
prose the README itself says not to read as precise, so the harness-verified 121,081 is the number
used. For scale, the same eval puts the orchestrator around it at 168,871 / 172,756 and one stage's
all-in at ~289,952.

> **THRESHOLD A — the seam question reopens when the raised `0-spec.md` reaches 36,324 tokens, i.e.
> 30% of the 121,081-token measured per-spawn floor.** The estimator that decides "reached": the
> harness-anchored ceiling when a harness figure is available, `chars ÷ 4` otherwise — consistent
> with the "at most 22.9%" reading below. At the ceiling rate this pass measured (0.445 tok/char),
> the threshold corresponds to ≈ 82,000 chars, ≈ 1,000 lines at today's density.

**Why 30%, argued from the data rather than from taste.**

1. *Below 30%, a split is unlikely to pay — bounded by what this repo has actually measured.* The
   ablation series bounds one specific lever: **prose-size levers inside a pass**, measured against
   that pass's own total. Cutting ~85% of kestra-spec's instruction text moved cost **−2.6%**
   (cherny); the two run-live orchestrator variants sit **2.3%** apart (168,871 vs 172,756); the dlq
   eval put **first-pass-only per-spawn cost** **<0.5%** apart (785,597 OLD vs 782,000 NEW — that
   eval's headline OLD-vs-NEW *total* was **−32.6%**, driven by a removed fixing loop, not by prose).
   Scope note, stated because the inference does not carry for free: removing spec content from a
   *downstream* context pack is a different lever — it mechanically removes up to ~22.9% of pack
   occupancy and is **not** bounded by that noise band. What reason 1 claims is only the weaker
   thing: this repo has never observed a prose-size change worth acting on, so a component under a
   third of a spawn is a poor bet to re-architect around. The threshold's weight rests on reasons 2–3.
2. *At 30%, the spec stops being one component and becomes the dominant one.* The pack is spec +
   stage brief + frozen test content + prior diff. At ~36k the spec alone roughly equals everything
   else static in the pack combined — which is precisely the condition the seam question was parked
   on ("does the whole spec still belong in every spawn").
3. *It is not set under today's reading.* A threshold below 22.9% would be pre-fired by its own
   baseline — an alarm that is already ringing when you install it detects nothing. 30% is the
   nearest round figure above the conservative estimate that clears reason 1.

**Does today's measurement cross it?** **No.** 15,541–27,689 tokens = **12.8%–22.9%** of the floor.
Even taking the ceiling, the raised spec sits **8,635 tokens** under the line — headroom of
**1.31×** (it could grow ~31% and still not fire). Read honestly, though, the conservative estimate
is already **76% of the way to the threshold**, on a feature whose target codebase is four files.

### Axis B — peak context vs. exhaustion

**Measured: 113,004 of 200,000 = 56.50%.** One detail matters for how to read it: the peak was reached
on the pass's **final** request (context climbed 25,535 → 113,004 monotonically; the top five values
are 109,395 / 109,804 / 109,928 / 109,928 / 113,004). This is steady accumulation, not a spike — the
pass ended at its own high-water mark, and nothing compacted.

> **THRESHOLD B — the seam question reopens when peak context reaches 140,000 tokens, i.e. 70% of the
> 200,000-token window.**

**Why 70%, argued from the data.** The pass's largest atomic allocation is a single turn: the one
`Write` that emitted the entire `0-spec.md`, **27,240 output tokens**. Such a turn charges the window
twice — once as output while it is being produced, and again on the next request when it echoes back
as input. One max-size turn round-trip therefore needs ≈ **54,480 tokens** of free window. A pass
that cannot absorb one more of those is a pass that can be forced into a mid-pass compaction, and a
*compacted spec pass is the specific failure this repo cannot tolerate*: the raise's credibility rests
on `verified:probe-*` and codebase reads it performed early, and compaction drops exactly that
evidence while leaving the confident prose in place. `200,000 − 54,480 = 145,520`; rounded down to
the clean **140,000 / 70%**. At that line the headroom is exactly **1.10** max-turn round-trips — the
last point at which one more full-file rewrite still fits.

**Does today's measurement cross it?** **No.** 113,004 = 56.50%, leaving **26,996 tokens** (13.50
percentage points) of margin — **1.60** max-turn round-trips of headroom, versus the 1.10 the
threshold defends. The pass could grow **23.9%** before firing.

### Threshold summary

| Axis | Threshold | Set by | Today | Margin | Crossed? |
|---|---:|---|---:|---:|---|
| A — pass weight vs per-spawn floor | **36,324 tokens** (30% of 121,081) | harness-verified implement-spawn cost, `2026-07-31-run-live-implement-context-pack`; prose-lever noise band from the cherny/dlq ablations (reasons 2–3 carry the weight) | 15,541–27,689 (12.8–22.9%) | 1.31× at the ceiling estimate | **no** |
| B — peak context vs exhaustion | **140,000 tokens** (70% of 200,000) | this pass's own 27,240-token max turn ⇒ 54,480-token round-trip reserve | 113,004 (56.50%) | 1.60 round-trips vs 1.10 defended | **no** |

## 6. VERDICT

> ## Tripwire: NOT FIRED

- **Axis A (pass weight):** the raised `0-spec.md` weighs 15,541–27,689 tokens, at most 22.9% of the
  121,081-token measured per-spawn floor, below the 36,324-token threshold — so the seam question
  does **not** reopen on pass weight.
- **Axis B (peak context):** the pass peaked at 113,004 of 200,000 tokens (56.50%), below the 140,000
  threshold with 1.60 max-turn round-trips of headroom — so the seam question does **not** reopen on
  context exhaustion.

Consequence, stated so no one has to infer it: **Wave 2 proceeds** — subject to the precondition
below. kestra-spec is reshaped without first reopening the split. Both thresholds are now standing
numbers — any later wave that produces a `0-spec.md` at or over 36,324 tokens, or a spec pass peaking
at or over 140,000, reopens the seam question at that point, before the wave it appeared in
continues.

### Precondition on this verdict — the fixture deviation is unresolved

Both "no"s above were measured on the **74-line cherny fixture**, i.e. on precisely the codebase
#31's Wave-1 text excludes: *"realistic fixture — not the 74-line one — where `needs_ui`/`needs_sa`
actually fire"*. The two `needs_*` qualifiers fired honestly; the codebase qualifier was not met.
This matters beyond bookkeeping because the bias runs **upward on both axes** (§8): a real repo
enlarges the Codebase Survey, the raise, and the peak — and Axis A's conservative estimate already
sits at **76%** of Threshold A. The verdict is therefore not robust to the deviation; it is
plausible that a compliant fixture flips Axis A.

A self-disclosure inside this README is not a spec amendment. So, stated as a gate rather than a
caveat:

> **Wave 2 may rely on NOT FIRED only after one of:**
> **(a)** the spec-pass arm is re-run on a non-trivial fixture and Axis A is re-measured against it —
> the missing arm is one clean-room subagent away, same instrument, same instructions; **or**
> **(b)** explicit human acceptance of the fixture deviation is recorded on `#31`/`#33` (a spec-level
> amendment of the Wave-1 qualifier), not here.
>
> Until (a) or (b) lands, read the verdict in its literal, narrower form: **"not fired on the
> cheapest realistic codebase."** Neither remedy is applied in this directory — recording (b)
> requires a human, and (a) is a new measurement, not an edit.

## 7. Qualitative findings worth carrying

**The raise caught a material defect in the vetted ticket, by running code.** The ticket's
`ID§Chosen-1` "Accepted consequence" paragraph relies on a retained in-flight mark so that *"the first
successful poll after the handler returns name[s] the message that was eating the worker"*, while its
`ID§Modules` section specifies the mark is **cleared** when the message leaves the handler. Both
cannot hold. `probe/b-inflight.mjs` settles it by execution, not by argument: a real `http` server, a
705 ms synchronous handler, three polls fired *during* the block — **zero** requests served mid-step,
all three served afterwards at **+712 / +715 / +719 ms**, each reading `inFlight: null`. A mark
cleared on handler exit is observable by no HTTP request, ever. It is dead data.

The pass resolved it in-spec (`Solution Architecture` Decision 3 — a retained **last-step record**
`{id, startedAt, durationMs, outcome}`, chosen as the smallest change that makes the ticket's own
promised mitigation true, with the literal reading rejected as "dead data" and dropping the concept
rejected as "silently drops a promised behaviour") **and** bounced it upstream as **OI-4**, so the two
documents get reconciled rather than left disagreeing.

What this says about the raise step, and it is the finding to carry:

- **The raise is the first point in the chain where intent meets an executing runtime.** to-spec,
  and the human vet after it, are both reading exercises. A self-contradiction between two prose
  paragraphs eleven sections apart survives both. It did not survive `node`.
- **The fix-in-place + bounce-upstream pair is the right shape and it worked.** The build is not
  blocked on an upstream round-trip, and the defect is not silently absorbed. Contrast the failure
  mode where the raise had simply implemented `ID§Modules` literally: a field written on every step
  that no view could ever display, shipped green.
- **Evidence density is the mechanism, not diligence.** Six probes produced **49** `verified:probe-*`
  citations across the spec (a:15, c:12, d:9, f:7, b:4, e:2) — including the two NFR numbers and the
  `303`-follow behaviour that make several ACs assertable at all. The probes are cheap; they are what
  turns "read and reasoned" into "ran it".
- **The `⚠ inferred` rule earns its place.** 11 lines carry the mark, and the two that actually matter
  (`POLL_MS` / `STALE_MS` — the numbers that decide how fast "lost contact" becomes visible, i.e. the
  feature's stated reason to exist) were *both* marked inferred **and** bounced as OI-5. Without the
  rule they are two plausible constants nobody ever questions again.

## 8. What this eval does not establish

- **n=1, one model, one feature.** One measured pass per arm on opus. A data point, not a trend —
  the same caveat every round in this folder has flagged about itself. The thresholds inherit this:
  they are set from a single observation of each quantity.
- **Clean-room subagent, not a live session — and the bias has a direction.** Each agent started from
  an empty context with only its prompt. A real interactive session carries conversation history,
  prior file reads, and CLAUDE.md/skill preamble on top of the same work, so **a live kestra-spec pass
  on this feature would peak *higher* than 113,004, not lower**. Axis B's 56.50% is therefore a
  **lower bound** on real peak occupancy, and its 13.5-point margin is optimistic.
- **The target codebase is the 74-line fixture, which spec #31 asked not to use.** `fixture/` here is
  byte-identical to `2026-07-31-spec-ablation-cherny/fixture/` (`diff -r` clean; 74 lines across four
  files), while #31's qualifier reads *"realistic fixture — not the 74-line one"*. What was made
  realistic is the **intent layer** (a 99-line grilled idea → a 430-line, 52-story ticket → a 745-line
  raise) and the flag surface — both qualifiers about `needs_ui`/`needs_sa` hold literally. The
  codebase qualifier does not. Bias direction, again upward: a real repo makes the Codebase Survey
  step far more expensive (this pass read the *entire* tree in four `Read` calls) and would enlarge
  both the raise and the peak. **Both tripwire margins reported above are therefore optimistic**, and
  the honest reading of "NOT FIRED" is "not fired on the cheapest realistic codebase". Not merely
  disclosed here: it is a **gate on Wave 2's reliance on the verdict** — see §6 *Precondition on this
  verdict* for the two remedies (compliant re-run, or recorded acceptance on `#31`/`#33`).
- **Hand-simulated grown shape is a defensible bound, not the shipped Wave-2 artifact.** All six
  obligations were imposed by prompt and verified present in the output, but the Wave-2 SKILL.md that
  will eventually *carry* them does not exist yet. Its own prose adds instruction tokens this
  measurement does not include, and it may induce structure this pass did not. #31 says as much and
  accepts it; recorded here so the number is not over-claimed.
- **Two-commit materialization was simulated as files.** No `git commit` ran. The verbatim leg is
  proven by `sha256`; the commit-message/ticket-URL leg (stories 5–6) is unmeasured.
- **Prompt overhead is inside every number.** `requests`, `output_tokens` and `peak_context` include
  the orchestration prompt each subagent received and its structured return — this is the cost of the
  pass *as run*, not of the skill in isolation. Consistent across both arms, so the ratios in §2 are
  fair; the absolute totals are not "skill-only" figures.
- **The instrument changed between eval generations.** Earlier READMEs here quote harness-reported
  "subagent tokens" (cherny 143,246 / 139,514; run-live 121,081 / 168,871). Those are *totals of a
  different shape* from this eval's `output_tokens` and `peak_context`. The one cross-eval comparison
  made above — Axis A against 121,081 — is deliberate and single: a per-spawn total is exactly the
  right denominator for "how much of a spawn does the spec eat". Do not extend the comparison further.
- **Nothing downstream was run.** `0-spec.md` was never fed to kestra-build or kestra-run, so the
  claim that a 745-line spec is *usable* rests on inspection and on the pass's own self-checks, not on
  a build. Its `full` mode prediction is likewise unverified against kestra-build's condition table.

## 9. Artifacts

- `idea-operator-console.md` — the post-grilling rough idea that seeded both passes (99 lines).
- `to-spec-pass/spec-ticket.md` — the to-spec output, standing in for the vetted tracker ticket
  (430 lines, 52 user stories).
- `spec-pass/0-spec-verbatim.md` — materialization commit 1, `sha256`-identical to the ticket.
- `spec-pass/0-spec.md` — materialization commit 2, the raise (745 lines / 21 sections / 38 ACs /
  7 open items). **The measured pass weight.**
- `probe/` — the six executable probes the raise cites (`a`…`f`), plus `map.rows` (the AC Coverage
  Map extract) and `e.out` (the one probe whose stdout was captured to file; the rest were read from
  the transcript, and their figures appear inline in `0-spec.md` tagged `verified:probe-*`).
- `fixture/` — the target repo both passes read, copied per precedent (Node/ESM, stdlib only, four
  files).
- `extract_usage.py` — the measurement instrument, copied for provenance and re-runnable against the
  transcript directory named in §1.
