---
name: kestra-spec
description: >
  Produce the build-ready 0-spec.md that kestra-build reads, plus an acceptance-tests.csv table a
  non-engineer can execute and sign off before any test code exists. Two input modes, decided
  mechanically: in-chain, a human-vetted tracker ticket is checked for the vet, materialized
  verbatim, then raised into 0-spec.md as a second commit; standalone (no ticket named), a
  hand-written idea gets one short clarifying pass and the same files in one commit. Use this
  whenever the user wants a spec kestra-build can consume without an agent guessing at gaps:
  "raise this vetted ticket into 0-spec.md", "materialize issue #123 into a spec", "turn this
  idea into a build-ready spec for kestra-build", or right after a /grilling session when
  producing the spec artifact is the next step. A chain ticket that is silent on intent bounces
  back upstream instead of having the rule invented here.
---

# kestra-spec — One-Pass, Build-Ready Spec for kestra-build

**Role:** Turn a vetted tracker ticket (in-chain) or a sharpened idea (standalone) into the
`0-spec.md` that `kestra-build` reads to derive a `workflow.yaml` — one pass, covering PM
(spec-sharpening), BA (business rules), design notes, and SA (architecture decisions) inline plus a
verified codebase survey, so no `kestra-build` stage agent has to guess. Plus a second file,
`acceptance-tests.csv`: the same acceptance criteria rendered as steps a person with no access to
the code can execute and sign off. Separate:
[`meta-designer`](../../meta/meta-designer/SKILL.md), which produces an actual openable artifact
(HTML mockup/wireframe) that this skill's Design Notes feed into, not compete with.

---

## Input — two modes, decided mechanically

**In-chain** iff the invocation names a tracker ticket: a URL, `#N` plus the repo, or a named local
tracker file shaped `<NN>-<slug>.md`. **Standalone** otherwise. Never search the tracker for a ticket
nobody named — no named ticket *is* the standalone signal, and guessing one is how unvetted intent
gets in.

| | In-chain | Standalone |
|---|---|---|
| Intent comes from | the named ticket, human-vetted (step 0) | a hand-written idea or `/grilling` output, plus this session's clarifying pass |
| Vetted gate | required — no vet, no work | none |
| Commits | two: verbatim, then the raise | one: the raise |
| `> Spec-ticket:` / `> Vetted:` preamble lines | URL-backed only; a local-file chain stays unmarked | never written |
| `needs_ba` silence on intent | bounce upstream | ask the human, here and now, cite the answer `Q<n>` |
| End-of-pass validator (step 9) | URL-backed: five FAILs; local-file: WARN because it is deliberately unmarked | the same five print WARN — the documented standalone contract |

**Standalone is a first-class path, not a degraded one.** The vetted gate exists because in-chain
nobody is watching the moment intent is invented; standalone has the human in the loop by
construction — they invoked it, in this session, and they answer the questions. Same behavior,
different guarantee.

**Standalone with no grilling behind it and the ask is still rough** ("add CSV export"): run a short
clarifying pass first — scope, error states, obvious ambiguity — before writing anything. Skip it
when the input already arrived pre-sharpened. Every fact it settles is cited `Q<n>` in the spec.

---

## Process — one continuous pass, one sitting, two output files

### 0. In-chain only: check the vet, then materialize the ticket

Standalone skips this whole step.

**Local-file tracker branch.** When the named ticket is `<NN>-<slug>.md`, load
[`references/chain-provenance.md`](references/chain-provenance.md) §3 and use its sibling `.vet`
hash gate and `tr -d '\r'` materialization instead of the GitHub commands below. Missing/stale vet is
the same gate bounce; it never downgrades the file to standalone. Commit the verbatim body and then
the raise as the same two adjacent commits, with the repo-relative path in both commit messages'
`Spec-ticket:` trailer. The reference gives the exact two commit messages, local vet attribution,
verbatim proof and subject-only discovery command; do not substitute GitHub identity or timestamps
that the `.vet` artifact does not contain. Do **not** write a spec preamble marker: that marker
accepts URLs only, so the five conditional checks WARN for this deliberately unmarked chain. The
rest of step 0 is the URL-backed branch.

**a. The URL-backed vet.** kestra-spec is **read-only on the tracker** — it never comments, labels, edits or
closes, so it cannot approve its own input. The vetted signal is a comment on the ticket whose first
line is `VETTED-FOR-KESTRA: <sha256 of the ticket body at vet time>`; newest such comment wins. Read
it, and compute the live body hash with the same pipeline the materialization uses:

```bash
gh issue view <N> --repo <R> --json comments \
  --jq '[.comments[]|select(.body|test("^VETTED-FOR-KESTRA: [0-9a-f]{64}"))]|sort_by(.createdAt)|last|select(.!=null)|[.createdAt,.author.login,(.body|split("\n")[0])]|@tsv'
gh issue view <N> --repo <R> --json body --jq .body | tr -d '\r' | sha256sum | cut -d' ' -f1
```

`select(.!=null)` is load-bearing, not decoration: without it, an unvetted ticket makes `last` null,
`split` raises, and the read exits 1 with a jq error indistinguishable from a bad repo name, an auth
failure or a dropped network — the one outcome the gate most needs to recognize. With it, **empty
output plus `exit=0` *is* the "no vet comment" signal**; a non-zero exit means the read itself
failed, so retry or escalate rather than bounce.

Completion criterion: the vet comment's hex equals the live body hash.

* **Equal** → proceed, carrying `<login>`, `<createdAt>` and the first 12 hex into the preamble.
* **No such comment** (empty output, `exit=0`) → **gate bounce**: stop here, commit nothing, and
  print the line for the human to paste as a comment —
  `echo "VETTED-FOR-KESTRA: $(gh issue view <N> --repo <R> --json body --jq .body | tr -d '\r' | sha256sum | cut -d' ' -f1)"`
  If the ticket itself is thin or missing, `to-spec` is the suggested tool for writing it — a
  suggestion only; kestra-spec never requires it to be installed.
* **Hashes differ** → same stop, different sentence: "the ticket body changed after the vet
  (`<vet-12>` ≠ `<body-12>`) — re-vet the current text."

Binding the approval to a content hash is what makes it mean *vetted this text*: a body edited after
the vet is caught, and a thin ticket can't launder itself through a citable URL. Named residual — a
token can post that comment, so this does not prove a human typed it. What it does buy: kestra-spec
never writes it, the approval names exact text, and the artifact is visible, attributed and dated.

**b. The URL-backed verbatim commit (commit 1).** Write the ticket body to the spec path unmodified, and emit
the run's own copies of the two scripts step 9 runs (copy-per-run: a check that reads this run in
six months must not change its answer because a skill was reinstalled since):

```bash
RUN=<repo>/workflows/runs/<feature-id>; mkdir -p "$RUN"
gh issue view <N> --repo <R> --json body --jq .body | tr -d '\r' > "$RUN"/0-spec.md
cp <scripts-dir>/requirement_surface.py <scripts-dir>/validate_spec.py "$RUN"/   # <scripts-dir>: see step 9
```

`tr -d '\r'` is the **one** declared normalization — GitHub returns web-authored bodies with CRLF
and a repo file must not carry it. Nothing else is normalized; more would make "verbatim"
negotiable. Then commit exactly those files:

```
spec(<feature-id>): materialize vetted ticket verbatim

Spec-ticket: <url>
Ticket-body-sha256: <hex>
Also emits this run's copies of requirement_surface.py and validate_spec.py.
```

If no `<scripts-dir>` resolves (step 9's three candidates all miss), the `cp` does not run — then
**drop that last body line**: commit 1 carries only `0-spec.md`, and step 9 will WARN that the
mechanical layer was skipped. A commit message that records an emission which did not happen is
exactly the provenance line this skill exists to prevent.

Completion criterion: commit 1 exists and `git show <c1>:<RUN>/0-spec.md | sha256sum` equals
`<hex>`. **Nothing may be committed between commit 1 and the raise** — that is what makes commit 1
always `<raise>^`, and step 10 depends on it.

### 1. Sharpen into testable acceptance criteria (PM pass)

Each requirement testable by QA without a follow-up question ("users can filter" ❌ → "filter
returns results in <200ms on 10k rows" ✅). Add missing error states/edge cases. Cut non-essential
scope into **Out of Scope**. Mark genuine unknowns `⚠️ OPEN`.

**Every intent line this pass adds cites its source story or carries `⚠ inferred`.** An intent line
is any line asserting what the system must do — an FR bullet, an edge case, an invariant row, an AC,
a Coverage-Map row, an External Interface operation. A line with neither is a defect, not a style
miss: the Source column without this rule is a mechanically-green column that lies. (`kestra-run`
holds the run-time half of the same rule: if code reality contradicts an `⚠ inferred` line, suspect
the line.)

**Prefer Given-When-Then for behavior-under-a-condition ACs**, not pure thresholds:
```
Given a paid order
When the customer cancels it
Then the payment is refunded in full
And the order status becomes "cancelled"
```
Matters most where `needs_ba: true` — forces every branch into its own visible line instead of
hiding inside prose. Skip it for pure data-shape/perf ACs.

**Give every AC and every edge case a stable id** — `AC-1`, `AC-2`…, `EC-1`, `EC-2`… (business
rules already get `BR-n` in step 3; design states get `DS-n` under `needs_ui`). Step 7's table and
`kestra-build`'s `generate-tests` both reference these ids, and "the third bullet under Acceptance
Criteria" is not a reference that survives one edit to the list. Ids are append-only: a deleted AC
leaves its number retired rather than renumbering the ones after it.

### 2. Set the flags — mechanically

* `needs_ba` — complex domain/business rules, multi-stakeholder requirements, spec vague on *what*.
* `needs_ui` — **any** new/changed page, route, modal, form, interactive element, or visible
  state — a single added button qualifies.
* `needs_sa` — 2+ services, competing approaches with lasting consequences, or explicit NFRs.
* `needs_devops` — new/changed env vars, migrations, feature flags, infra.

Once derived, each flag's value is a fact for step 3 to act on, not a judgment call to reopen.

### 3. Do the flagged work inline — real content, not a stub

* **`needs_ba`** → BR-1, BR-2… each with example + counter-example (Given-When-Then). Stakeholder/
  role/locale variations. New ACs for anything the rule makes testable. In-chain, where the ticket
  is silent on *which outcome is correct* for a branch this feature must take, **bounce** instead —
  the **Bounce** section below owns that shape. Standalone, ask the human now and cite the answer
  `Q<n>`.
* **`needs_ui`** → Read `CLAUDE.md` + the actual token/component source before naming anything.
  Component audit (reuse w/ real import path, or new + why), real token names, breakpoints if
  multi-device, all 4 screen states (empty/loading/success/error) per view — say why if one's
  impossible, don't skip silently. Add design ACs (component + token + state + viewport).
* **`needs_sa`** → 2–3 approaches, concrete trade-offs, chosen one justified (cost/complexity/risk),
  NFR targets, integration contracts, data-model impact.
* **`needs_devops`** → just make sure Edge Cases/Functional Requirements name the env
  vars/migrations/flags involved — the deploy checklist itself is `deploy-readiness`'s job later.

Flag `false` → do nothing for it.

### 4. Survey the real codebase and verify every file path (architect pass)

* Read the real code in every directory/file this feature touches before deciding anything.
* **Verify every file in "Files to Touch" exists** (`ls`/`find`/read) before writing it down. New
  files follow the nearest existing convention — name which file you patterned it after.
* A chosen `needs_sa` approach is a hard constraint here — a conflict goes back to step 3, not
  routed around silently.
* Every AC maps to at least one concrete implementation step — incomplete mapping means fix it now.
* **For every AC that names a runnable check, actually run it now** — don't take the spec's own
  wording as given.
* **Read the code behind each Runtime Invariant's on-violation behaviour**, even outside this
  feature's own files (a plugin loader, a supervisor, a deploy policy) — an unchecked on-violation
  claim sends the implementer and reviewer looking for a behavior that cannot happen. Step 6 grades
  this; do the work here.
* List new dependencies and name risks (shared files, race conditions, fragile migrations)
  explicitly.

### 5. Name what the world won't guarantee, and what must hold at runtime

Acceptance criteria cover cases someone thought of; this step covers the ones nobody did.

* **Runtime invariants.** Enforced *forever*, against inputs nobody predicted. Test: if this
  condition went false and the system carried on, would anyone find out before the damage was
  done? If no, name the condition, how it's detected at runtime, and what happens on violation
  (halt/refuse/alert). "Logged, then continues" is not an invariant — it's a comment wearing one's
  clothes.
* **What each external dependency actually does — and doesn't guarantee.** Enforced ordering/
  preconditions, real returned types/shapes, and — the part people skip — what completeness/
  consistency it does *not* promise. The standard test doubles get judged against later.
* **Pairs of paths that must agree.** Replay vs. live, cached vs. computed, sync vs. async — name
  the pair, what "equivalent" means, what may legitimately differ.
* **Non-deterministic inputs: pinned or floating.** Clock, randomness, timezone/locale, network,
  filesystem, env — for each one this feature reads, say which, and why.

Grounding: [`../kestra-build/references/test-quality-taxonomy-research.md`](../kestra-build/references/test-quality-taxonomy-research.md)
— a starting point, not a complete list; add whatever this codebase's own history says belongs.

### 6. Self-check against the list `spec-review` will grade this by

Keep this list in sync with `kestra-build`'s spec-review brief — change one, change both.

1. Each Runtime Invariant vs. the Edge Cases/ACs describing the same condition — no contradictions
   (e.g. an invariant that halts where an edge case says "no-op").
2. No invariant's on-violation action is "log and continue."
3. Each AC is testable without a follow-up question — exact inputs named, not "the right subset."
4. Each "does not guarantee" column is filled.
5. **Every claim in items 1–4 was verified by actually running the command or reading the real code
   in step 4 — not just cross-checked on paper.** A spec can pass 1–4 by being internally consistent
   and still be wrong about what the world does; this item is what closes that gap. Don't broaden
   this into running the full test suite — that's the verify stage's job, later, on frozen tests
   that don't exist yet.

Fix what this turns up. Anything unresolved → **Open Items** — an honest open item passes
`spec-review`, a contradiction doesn't.

### 7. Render the acceptance criteria as a table a non-engineer can execute

Same content, different reader. `0-spec.md` is written for the stage agents; this table is written
for whoever has to *approve* what will be tested — a QA lead, a product owner, a client — before
any test code exists and while a change is still cheap.

Why here and not later: the only other place this sign-off could live is a `human_approval` stop
inside the generated workflow — a human stop in a pipeline whose default is zero, sitting where a
rejected row costs a `reworking` bounce instead of an edit. Doing it here folds the approval into
the moment a human already reads the spec, and leaves the generated workflow fully automatic
(`kestra-build` generates no approval-collecting stage precisely because this file exists).

* **One row per scenario, every row carrying the id it came from** — `AC-n`, `BR-n`, `EC-n`,
  `DS-n`. Every id enumerated in the spec appears in at least one row; a row whose id resolves to
  nothing is scope you invented, not a bonus test.
* **Split an AC that hides more than one outcome.** "Refunded, inventory released, all in one
  atomic operation" needs the happy-path row *and* a row that fails when the operation is only
  half-applied — one row per AC would let a half-working implementation pass, which is the exact
  false positive the table exists to catch.
* **The Expected Result bar:** could a person with no access to the code disagree with the tester
  about whether it passed? If yes, rewrite it. "Moves smoothly" fails; "within 500ms", "403
  Forbidden shown", "row disappears from the list" pass. This is step 6 item 3 applied to a reader
  who can't fall back on reading the implementation — an AC that survives here is testable in a
  stronger sense than one that only survives the spec's own review.
* **Test Data holds literal values**, never "valid input".
* **A row nobody intends to automate is marked `Manual` with a reason** — an unmarked row and a
  deliberately-manual one are indistinguishable otherwise.
* **Runtime Invariants get a row only where the violation is observable from outside.** One
  detected by an internal assertion has no black-box row; say so rather than inventing one.

An id you cannot write a row for is a finding, not a rounding error: either the AC isn't testable
(fix it in step 1) or it's genuinely internal (say which, in **Open Items**).

**Run the two-direction check before you call the table done — don't eyeball it.** Step 6 item 5's
standard applies here too, and this is the one claim in the whole skill you can settle with a
command:

```bash
python3 - <<'PY'
import re, csv
from pathlib import Path
d = Path("<run-folder>")
ids = set(re.findall(r"\b(?:AC|BR|EC|DS)-\d+\b", (d / "0-spec.md").read_text()))
refs = set()
for row in csv.DictReader((d / "acceptance-tests.csv").open(newline="")):
    refs |= set(re.findall(r"\b(?:AC|BR|EC|DS)-\d+\b", row["Source Ref"] or ""))
print("uncovered:", sorted(ids - refs), "| unresolved:", sorted(refs - ids))
PY
```

Both lists empty, or every remaining entry explained in **Open Items** — nothing else counts as
done. Measured on this skill's own first real run: the check found six ids whose rows existed but
whose `Source Ref` named only the AC and not the edge case it also covered — invisible to reading,
obvious to the command. Use `csv.DictReader`, never `cut -d,` or `split(",")`: a quoted cell
containing a comma silently truncates under both, and a coverage gate that always passes is worse
than no gate.

**Never write a concrete id number in prose that isn't a real reference — use the placeholder form
`AC-<n>` instead.** A sentence describing a *fixture* ("a spec with ids AC-1, AC-2, BR-1") is
indistinguishable from a definition to the check above: the same run reported a business-rule id
that existed nowhere but inside one AC's own example text, on a spec with `needs_ba: false`.
**Backticks do not help** — the regex sees inside code spans, so quoting a phantom id leaves it just
as visible; only changing the digits to `<n>` removes it. Confirmed by re-running the check after
wrapping one in backticks: still reported. The cost of the convention is nothing; the cost of
skipping it is a phantom id that gets either a fabricated test row or an Open Item explaining a
non-problem.

### 8. Write both files

`0-spec.md` at the spec path (in-chain this **overwrites** the verbatim body committed in step 0b —
that overwrite *is* the raise, and it is why the raise is inspectable as one git diff). Every section
step 3 produced content for gets folded in under its own heading below — no separate
`ba.md`/`design.md`/`sa.md`/`1-plan.md`. Plus `acceptance-tests.csv` from step 7, beside it.

Three sections of `0-spec.md` carry writing rules a template placeholder can't express:

* **`## External Interface`** — everything downstream derives its tests from this section, so a seam
  named too vaguely to drive is a permanent false-fail generator. Name the seam concretely enough to
  call, and name the *deliberately absent* seams too: without them, whatever reads this section
  invents one.
* **`## Exit Criteria`** — one `progress:` fragment per loop-shaped check, and each fragment names a
  **number**, never a state. "tests green" ❌; "number of failing assertions reported by `npm test` —
  must reach 0, from a baseline of 2 passing / 0 failing" ✅. `kestra-run` compares that number
  across attempt rounds and `kestra-build` copies the fragment into the owning stage's
  `exit_criteria`; a state has nothing to compare. Checks that are genuinely single-shot pass/fail
  carry no fragment and get listed together in the closing bullet.
* **`## Mode Prediction`** — exactly one `kestra-build mode:` line, `full` or `lite`, with the reason
  that decided it.

### 9. Run the mechanical check on your own output — before committing the raise

`spec-review` fires only after the fold, and lite mode folds it into `generate-tests`, so a lite run
would invoke the validator zero times and anything derived from the raise would be built on an
unchecked surface. Run it here instead, from the run's own copies:

```bash
RUN=<repo>/workflows/runs/<feature-id>
cp <scripts-dir>/requirement_surface.py <scripts-dir>/validate_spec.py "$RUN"/   # in-chain: already done in step 0b
python3 "$RUN"/validate_spec.py "$RUN"/0-spec.md <repo-root>; echo "validate_spec exit=$?"
python3 "$RUN"/requirement_surface.py "$RUN"/0-spec.md >/dev/null; echo "surface exit=$?"
```

`<scripts-dir>`, first hit wins: `$RUN/` → `<repo>/workflow/kestra-build/scripts/` →
`~/.claude/skills/kestra-build/scripts/`. None of the three → print one WARN, skip the mechanical
layer, self-apply the step 6 checklist, and continue; kestra-spec must not hard-depend on
kestra-build being installed, so this is never a hard stop. **Copy both files or neither** — with
`validate_spec.py` present but `requirement_surface.py` missing, the delimiter check has no way to
run, and on a chained spec it reports that as a FAIL rather than skipping (a truncated surface
hashed as fresh is invisible downstream). Fix it by copying the sibling, never by dropping the
marker.

Completion criterion: both lines print `exit=0`, with no `FAIL:` in the output. A FAIL → fix the
spec and re-run. Never commit the raise over a FAIL, and never edit the validator to make a spec
pass. For a URL-backed chain the five template checks (Source column, External Interface, mode-prediction fact,
Exit Criteria, delimiter precondition) are FAILs; standalone they print as WARNs — that is the standalone contract,
not a defect to chase. `kestra-build` overwrites both copies with its own at generation time; a
genuine skill-version difference shows up there as a git diff instead of hiding.

### 10. Commit the raise, then prove the verbatim commit intact

**Standalone:** one commit — `spec(<feature-id>): write 0-spec.md from a hand-written idea` —
carrying `0-spec.md`, `acceptance-tests.csv`, and this run's two script copies. No `Spec-ticket:`
line, no vet claim, no verbatim commit. Done; go to Handoff.

**URL-backed chain:** commit 2 modifies exactly one path, `0-spec.md`, so "the raise is one git
diff" stays literally true; `acceptance-tests.csv` rides along as a brand-new file, which adds a
line to the commit without adding one to that diff:

```
spec(<feature-id>): raise vetted ticket into 0-spec.md

Spec-ticket: <url>
Vetted-by: <login> @ <createdAt>
```

Then the **verbatim check** — same pipeline as step 0b, run against what was actually committed:

```bash
gh issue view <N> --repo <R> --json body --jq .body | tr -d '\r' > /tmp/kestra-spec-ticket-body.md
git show "$(git rev-parse <raise-sha>^)":<spec-path> | diff -u - /tmp/kestra-spec-ticket-body.md
```

Completion criterion: `diff` exits 0 — byte-identical after the one declared normalization. It
prints what diverged for free; the durable offline record is commit 1's `Ticket-body-sha256`
(`git show <c1>:<spec-path> | sha256sum`) for when the tracker is unreachable.

**Local-file chain:** use §3 of
[`references/chain-provenance.md`](references/chain-provenance.md) for commit 2 and the same
committed-parent proof, reading the ticket with `tr -d '\r' < <ticket>` instead of `gh`. The local
commit records the `.vet` path and hash as artifact attribution; it never invents a login or
`createdAt`. Completion is still `diff` exit 0.

A non-empty diff is a **hard stop, no handoff**, with exactly two honest fixes: (a) re-materialize —
`git reset --hard <c1>^` (destructive; confirm with the user first) and re-run the pass; or (b) if
the ticket genuinely changed mid-pass, stop and bounce, because the vet no longer covers the text.
Editing the committed verbatim file to match, or amending commit 1, is banned — that is "patch the
test to match broken code" wearing spec clothing.

**Downstream discovery:** the raise commit is found by an exactly-one-match convention, and a
re-raise replaces its predecessor rather than stacking. Read
[`references/chain-provenance.md`](references/chain-provenance.md) when something asks *which commit
is the raise* (a re-raise, an anchor being recorded, a downstream skill resolving provenance), or
when the tracker is a local file rather than GitHub.

---

## Bounce — intent-silence goes back upstream

In-chain only, and narrow by construction. **Bounce when the ticket does not say which outcome is
correct for a branch the feature must take** — an AC cannot be written without inventing the rule.

**A missing number, threshold, name, copy string or filename is not a bounce**: pick a sane default,
mark the line `⚠ inferred`, record a non-blocking `OI-n`, and keep going.

When a bounce fires:

1. **Finish both commits anyway** — the work is preserved, the raise stays inspectable, provenance
   stays intact.
2. Set the preamble to `Status: BLOCKED_ON_INTENT`.
3. Write one entry per bounce under `## Open Items`, in this exact shape:
   `* **BOUNCE-<n> — needs_ba intent silence.** Question: <the undecided branch, as Given-When-?>. Blocks: <AC ids>. Needs: <role who decides>. Resolution: add the rule to the ticket upstream (to-spec is the suggested tool, if installed), re-vet, re-run kestra-spec.`
4. **Do not hand off to kestra-build**, and say so plainly to the user.
5. Never author the rule, never pick a default for it, never write to the tracker.

The gate bounce in step 0a uses the same vocabulary but fires before any work, so it commits nothing.
A flagged-but-continuing state is deliberately not an option here: the default workflow has zero
`human_approval` stages, so nothing downstream would ever read the flag and the build would proceed
on invented intent — this session is the last boundary where a human is guaranteed present.

---

## Output: `0-spec.md` + `acceptance-tests.csv`

Default: `<repo>/workflows/runs/<feature-id>/` (next to `kestra-build`'s output, and beside
this run's emitted `requirement_surface.py` / `validate_spec.py`). Ask if the repo uses a different
convention.

**Written for `kestra-build`'s stage-derivation pass and every generated stage's spawned subagent,
not a human approver** — `kestra-run`'s context pack pastes this file's full text into *every single
spawn* (see `kestra-run`'s `SKILL.md` step 2), so every sentence here is paid for again on every
stage. Bias hard toward density: bullet fragments over full sentences, never restate a heading's own
words in the prose under it. This changes *density*, never *content* — every fact the template asks
for still has to be there in full; cutting a fact to save a sentence just relocates the cost to
whichever stage discovers the gap later, at a worse exchange rate. No emoji in headings — a
decorative prefix is pure overhead for a subagent grepping section names.

```markdown
# [<feature-id>] Spec — <feature title>

> Status: READY_FOR_BUILD | BLOCKED_ON_INTENT | Created: YYYY-MM-DD | Next: kestra-build
> Spec-ticket: <full ticket URL>  *(URL-backed chain only — omit for local-file chain and standalone; the URL and nothing else on the line)*
> Vetted: <login> @ <ISO-8601> · vet sha256 <first-12>  *(URL-backed chain only — omit for local-file chain and standalone)*
> Provenance key: `US-n` = user story · `ID§x` = ticket Implementation Decisions subsection · `TD`/`FN`/`OOS`/`PS` = Testing Decisions / Further Notes / Out of Scope / Problem Statement · `IDEA§x` / `Q<n>` = idea heading / this session's clarifying answer (standalone) · `⚠ inferred` = originated by this pass, nothing upstream behind it · `verified:<probe>` = confirmed by running code in step 4
> Delimiter precondition: every `## ` at column 0 outside a code fence is a template section heading; no line inside a requirement-surface section body begins with `## `; subsections use `### `; every code fence is closed.

---

## Overview
[one line: what this delivers, why.]

## External Interface
*(the seam the tests may drive — and only this seam.)*
* **Primary ([new|existing]):** [the seam, named concretely enough to call]
  * `[operation / route / entry point]` — [inputs] → [status or return shape] → [side effect]
* **Secondary (existing, reused not extended):** [seam] — [what it covers; why it isn't extended]
* **Deliberately absent seams:** [what tests may not drive — so nothing invents one]
* **Not an interface:** [private/unexported — internal by intent]
* No export is added solely to make something testable.

## Problem Statement
* [current behaviour]
* Goal: [measurable outcome]

## Functional Requirements
* [ ] [requirement — specific enough to implement] ([source])
* [ ] [behavioral requirement — Given-When-Then where it clarifies a scenario, else a bullet fragment] ([source])

## Edge Cases & Error States
* **EC-1 — [edge case]:** [how it's handled] ([source])
* **EC-2 — [failure mode]:** [expected behaviour] ([source])

## Runtime Invariants
*(must hold every time this runs — a violation halts, refuses, or alerts; never proceeds silently.)*
| Invariant — what must be true | Detected at runtime by | On violation |
|-------------------------------|------------------------|--------------|
| [condition] ([source]) | [the actual check, and where it sits in the flow] | [halt / refuse / alert — who finds out] |

## Business Rules  *(only if needs_ba: true)*
* **BR-1:** [rule + example + counter-example, Given-When-Then] ([source])
* Stakeholder variations: [role/locale/state → behaviour difference]

## Design Notes  *(only if needs_ui: true)*
### Component Audit
| Component | Reuse? | Token ref | Notes |
|-----------|--------|-----------|-------|
| `[Name]` | reuse `@path/to/Component` | `token.name` | [usage] |
| `[Name]` | new | `token.name` | [why existing ones didn't fit] |
### Token Mapping
* [usage]: `token.name` (or "no design system" — hardcoded baseline noted)
### Screen States
| View | Empty | Loading | Success | Error |
|------|-------|---------|---------|-------|
| [Name] | [desc] | [desc] | [desc] | [desc] |

## Solution Architecture  *(only if needs_sa: true)*
Chosen approach: [A] — [one-sentence rationale]
| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| [A] | ... | ... | chosen |
| [B] | ... | ... | rejected — [why] |
* Integration contracts: [service A → service B: what's exposed/consumed]
* Data model impact: [new tables/columns/migrations — or "none"]
* NFR targets: [latency / throughput / fault-tolerance / compliance]

## Codebase Survey
* Explored: [dirs/files actually read]
* Integrate with: [existing modules/patterns/conventions to follow]

## Reality Constraints
*(what the world outside this feature actually does — verified by running/reading, not assumed.
Omit a subsection only when genuinely not applicable, and say so.)*

### External dependencies
| Dependency | Enforced ordering / preconditions | Types & shapes actually returned | Does **not** guarantee |
|------------|-----------------------------------|----------------------------------|------------------------|
| `[name]` | [e.g. X must be released before Y — or "none known"] | [real types as observed/documented] | [completeness / ordering / uniqueness / timeliness it won't promise] |

### Paths that must agree
* `[path A]` ↔ `[path B]` — equivalent means: [what must match] · may differ: [what's allowed to
  diverge, and why] — *(or "none — single path")*

### Non-deterministic inputs
| Input | Pinned or floating in tests | Why |
|-------|-----------------------------|-----|
| [clock / randomness / timezone / locale / network / filesystem / env] | pinned \| floating | [reason] |

## Files to Touch
| File | Change | Verified? | Why |
|------|--------|-----------|-----|
| src/... | edit | exists | ... |
| src/... | new | follows pattern at src/... | ... |

## Dependencies
* [new packages / schema changes / migrations — or "none"]

## Acceptance Criteria
* [ ] **AC-1:** [testable, measurable — includes design ACs; Given-When-Then for behavioral ACs]

## AC Coverage Map
| AC | Source | Covered by (files/steps) | Test rows |
|----|--------|--------------------------|-----------|
| AC-1 | [US-n / ID§x / TD / FN / OOS / PS / IDEA§x / Q<n> / ⚠ inferred] | [file(s) / step] | TC-001, TC-002 |

## Risks & Watch-outs
* [shared files, race conditions, migrations needing care — or "none"]

## Out of Scope
* [explicitly excluded — point to future work if relevant]

## Flags
* `needs_ba`: [true|false] — [reason]
* `needs_ui`: [true|false] — [reason]
* `needs_sa`: [true|false] — [reason]
* `needs_devops`: [true|false] — [reason]

## Exit Criteria
**Stop condition:** [completion clause] — **or** two consecutive attempt rounds pass without the
relevant progress number below moving, at which point stop and summon the human rather than attempt
a third.

* progress: [the number that must move] — must reach [target], from a baseline of [baseline].
* Single-shot pass/fail, no progress number: [the checks that deliberately carry none].

## Mode Prediction
* **kestra-build mode:** `full` — [the reason that decided it]  *(or `lite` — exactly one such line)*

## Open Items
* [anything genuinely unresolvable — or "none"]
```

### `acceptance-tests.csv`

Header, exactly — column order is load-bearing, `kestra-build`'s `generate-tests` reads it
positionally:

```
Test Case ID,Source Ref,Module/Feature,Test Case Title,Preconditions,Test Steps,Test Data,Expected Result,Priority,Test Type,Automation
```

| Column | Rule |
|---|---|
| Test Case ID | `TC-NNN`, append-only — never renumber an existing row |
| Source Ref | a real id from the spec: `AC-3`, `BR-1`, `EC-2`, `DS-1` |
| Test Case Title | what is being proven, action-shaped — not "test the cancel button" |
| Preconditions | exact state to set up, with concrete records/ids |
| Test Steps | numbered, executable by someone who has never seen the feature |
| Test Data | literal values |
| Expected Result | observable and decidable without reading the code |
| Priority | High (core) / Medium (supporting) / Low |
| Test Type | Functional / Security / Performance / Usability |
| Automation | `Auto`, or `Manual — [reason]` |

Execution results never come back into this file — it's the approved contract. They belong in a
separate `acceptance-results.csv` (`Test Case ID,Actual Result,Status,Tester Name,Execution
Date,Comments`), written at run time, joined on Test Case ID.

---

## Stopping rule

Done once:
- Every AC is testable without a follow-up question
- Every intent line this pass added cites a source (`US-n` / `ID§x` / `IDEA§x` / `Q<n>` / …) or
  carries `⚠ inferred`; every **AC Coverage Map** row has a non-empty `Source` cell
- **External Interface** names the primary seam, the deliberately absent seams, and what is not an
  interface
- **Exit Criteria** carries the two-clause stop condition plus one `progress:` fragment per
  loop-shaped check, each naming a number, a target and a baseline
- **Mode Prediction** carries exactly one `kestra-build mode:` line with its reason
- Every flagged section (`needs_ba`/`needs_ui`/`needs_sa`) that's `true` has real content
- Every row in **Files to Touch** verified to exist (or placed per a named existing pattern)
- Every AC maps to at least one file/step in the coverage map
- **Runtime Invariants** names the on-violation action for each row, none of them "log and continue"
- **Reality Constraints** filled in or explicitly marked not-applicable with a reason — especially
  "does not guarantee"
- **Step 6 ran, including item 5** — every checkable claim was actually run or read against real
  code, not just cross-checked on paper
- Every AC, BR, edge case, and design state carries an id, and every id appears in at least one
  row of `acceptance-tests.csv` — or is named in **Open Items** as observable-from-inside-only
- Every `Source Ref` in the table resolves to an id that exists in `0-spec.md`
- **Step 7's two-direction check was actually run**, output pasted — not asserted from reading
- **Step 9 ran clean** — `exit=0` from both scripts, or the one documented WARN when no
  `<scripts-dir>` exists
- In-chain: the vet matched, both commits exist with nothing committed between them, and step 10's
  `diff` printed nothing
- No silent gaps — unresolved → **Open Items**

Non-empty **Open Items** → say so plainly at handoff. Any `BOUNCE-` entry ⇒ `Status:
BLOCKED_ON_INTENT` ⇒ no handoff at all.

## Handoff

→ **A human, first.** `acceptance-tests.csv` is the artifact they sign off — this is the approval
point that keeps the generated workflow free of a mid-run `human_approval` stop. Say plainly that
approving it freezes what will be tested, and that a change after `kestra-build` runs costs a
`reworking` bounce rather than an edit.

→ Then `kestra-build`, which reads `0-spec.md` directly and can skip straight to deriving stages.
Its `generate-tests` brief translates each approved row 1:1 into test code with the Test Case ID
embedded in the test name, so coverage stays checkable by grep — and it generates no
approval-collecting `design-tests` stage, since the approval already happened here. (It may still
split one out for context size on an oversized spec; that split collects nothing.)

Unless the status line says `BLOCKED_ON_INTENT` — then there is no handoff in either direction; it
goes back upstream, to whoever owns the rule the ticket didn't decide.

**If the spec changes after approval** — `spec-review` rewording an AC, a new edge case — the table
is stale the moment an id it references changes meaning. Regenerate the affected rows and get them
re-approved rather than letting the two drift; the ids are what make the drift detectable at all.
