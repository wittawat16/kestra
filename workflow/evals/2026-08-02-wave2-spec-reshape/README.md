# Eval — Wave 2, the reshaped `kestra-spec`: chain-marker-conditional validation, the two-commit raise, and the standalone path

Ticket [#35](https://github.com/arkaphat/arkaphat-builder/issues/35) (Wave 2 of the prep-chain
implementation, parent [#31](https://github.com/arkaphat/arkaphat-builder/issues/31)).

Unlike the two spec evals dated before it, **this one runs no LLM passes.** Wave 2's deliverable is
machinery — a marker, a conditional validator, two commit shapes, a discovery predicate, a bounce —
and machinery is falsifiable by command. The eval's job is to run the commands and keep the literal
output, exactly the standard `kestra-run` holds itself to: *every enforcement decision must come from
a command that was actually run.* Where a claim cannot be settled by a command (does a live reshaped
pass actually behave this way?) it is listed in §9 as not established, not softened.

Everything below was produced by running the commands shown, on the working tree of branch
`arkaphat/prep-chain-impl`, against these subjects:

| Subject | Path | State |
|---|---|---|
| the reshaped skill | `workflow/kestra-spec/SKILL.md` | 541 lines (+285/−41 vs `HEAD`, after the round-1 fixes) |
| its reference | `workflow/kestra-spec/references/chain-provenance.md` | 109 lines, new |
| the validator | `workflow/kestra-build/scripts/validate_spec.py` | 437 lines (+266/−5 vs `HEAD`, after the round-1 fixes) |
| the extractor | `workflow/kestra-build/scripts/requirement_surface.py` | +7/−3 (`_canonical` → `canonical_heading`), `EXTRACTOR_VERSION` still `1` |
| new fixtures | `fixtures/` | 28 `.md` files |
| the worked example | `workflow/runs/order-cancellation-refund/0-spec.md` | repaired per D9 |
| the Wave-1 grown shape | `workflow/evals/2026-08-02-spec-instrumented-rerun/spec-pass/0-spec.md` | unmodified |

Environment: macOS 25.5.0, `python3` stdlib only, `git 2.50.1`, `jq 1.7.1`, `gh` read-only.
`python3 -m py_compile` on both scripts: clean. `python3 workflow/kestra-build/scripts/test_requirement_surface.py`:
`Ran 12 tests … OK`.

---

## 1. The validator matrix — 43 files, one command each

Driver: [`logs/run-matrix.py`](logs/run-matrix.py); full literal output (every command line, every
`FAIL`/`WARN` line, every exit code): [`logs/validator-matrix.log`](logs/validator-matrix.log), 326 lines.

Each row is `python3 workflow/kestra-build/scripts/validate_spec.py <spec> <repo-root>`. The
repo-root argument matters — it is what the Files-to-Touch path check resolves against — so it is
recorded per row in the log rather than assumed. Pre-existing eval specs are given the root their
own Files-to-Touch column was written against (their eval's `fixture/` dir, or the repo root for the
two specs whose rows are repo-relative); getting this wrong manufactures FAILs that belong to the
harness, not the validator, and the first run of this matrix did exactly that before the roots were
fixed.

### 1a. New fixtures — 28 files, 14 marked / 10 unmarked / 4 degenerate markers

| Fixture | Marker | FAIL | WARN | exit | The one line it produces |
|---|---|---|---|---|---|
| `conforming-chained.md` | yes | 0 | 0 | 0 | *(silent)* |
| `no-source-column-chained.md` | yes | 1 | 0 | 1 | `FAIL: no 'Source' column in the AC Coverage Map header …` |
| `no-source-column-standalone.md` | no | 0 | 1 | 0 | same text, `WARN` |
| `empty-source-cells-chained.md` | yes | 1 | 0 | 1 | `FAIL: 2 AC Coverage Map row(s) have an empty 'Source' cell — a green column that lies` |
| `empty-source-cells-standalone.md` | no | 0 | 1 | 0 | same text, `WARN` |
| `no-ac-coverage-map-chained.md` | yes | 1 | 0 | 1 | `FAIL: no 'AC Coverage Map' section found — the Source column check cannot run` |
| `no-ac-coverage-map-standalone.md` | no | 0 | 1 | 0 | same text, `WARN` |
| `no-external-interface-chained.md` | yes | 1 | 0 | 1 | `FAIL: no '## External Interface' section — kestra-exam must run at the seam …` |
| `no-external-interface-standalone.md` | no | 0 | 1 | 0 | same text, `WARN` |
| `empty-external-interface-chained.md` | yes | 1 | 0 | 1 | `FAIL: '## External Interface' is empty — name the seam tests may drive …` |
| `empty-external-interface-standalone.md` | no | 0 | 1 | 0 | same text, `WARN` |
| `no-mode-prediction-chained.md` | yes | 1 | 0 | 1 | `FAIL: no recorded mode-prediction fact …` |
| `no-mode-prediction-standalone.md` | no | 0 | 1 | 0 | same text, `WARN` |
| `two-mode-lines-chained.md` | yes | 1 | 0 | 1 | `FAIL: 2 mode-prediction lines — exactly one is allowed` |
| `two-mode-lines-standalone.md` | no | 0 | 1 | 0 | same text, `WARN` |
| `unclosed-fence-chained.md` | yes | 1 | 0 | 1 | `FAIL: unclosed code fence — the requirement surface would be silently truncated (false-fresh hash)` |
| `unclosed-fence-standalone.md` | no | 0 | 1 | 0 | same text, `WARN` |
| `bare-heading-in-surface-chained.md` | yes | 1 | 0 | 1 | `FAIL: '## Notes' is not a template section heading — a bare '## ' … truncates the surface` |
| `bare-heading-in-surface-standalone.md` | no | 0 | 1 | 0 | same text, `WARN` |
| `four-obligations-missing-chained.md` | yes | **4** | 0 | 1 | all four obligations, all `FAIL` |
| `four-obligations-missing-standalone.md` | no | 0 | **4** | 0 | all four obligations, all `WARN` |
| `mode-without-reason-chained.md` | yes | 0 | 1 | 0 | `WARN: the mode-prediction line records no reason for the mode` — warn **in both modes** by design |
| `no-precondition-line-chained.md` | yes | 0 | 1 | 0 | `WARN: no 'Delimiter precondition:' line in the preamble — prose only …` — warn in both modes |
| `plural-external-interfaces-chained.md` | yes | 2 | 0 | 1 | `FAIL: no '## External Interface' section …` + `FAIL: '## External Interfaces' is not a template section heading …` |
| `marker-valueless-chained.md` | partial | 1 | 0 | 1 | `FAIL: chain marker 'Spec-ticket:' present but malformed ('')` |
| `marker-malformed-chained.md` | partial | 1 | 0 | 1 | `FAIL: … malformed ('<ticket-url>')` — the unsubstituted placeholder |
| `marker-duplicate-chained.md` | partial | 1 | 0 | 1 | `FAIL: 2 'Spec-ticket:' marker lines in the preamble — exactly one is allowed` |
| `marker-below-preamble.md` | partial | 1 | 0 | 1 | `FAIL: 'Spec-ticket:' line outside the preamble …` |

**Fixture totals: 19 FAILs, 15 WARNs, 15 non-zero exits over 28 files.** Every FAIL and every
non-zero exit in the whole 43-file matrix comes from this block.

### 1b. Pre-existing specs — 15 files, 0 FAILs, 0 non-zero exits

`HEAD:` is the same file run through `git show HEAD:…/validate_spec.py` (the pre-Wave-2 validator),
so the two columns isolate what Wave 2 actually changed.

| Spec | Marker | FAIL | WARN | exit | pre-Wave-2 validator (F/W/exit) |
|---|---|---|---|---|---|
| `workflow/runs/order-cancellation-refund/0-spec.md` (repaired) | no | 0 | 5 | 0 | 1 / 0 / 1 |
| `2026-08-02-spec-instrumented-rerun/spec-pass/0-spec.md` (grown shape) | no | 0 | **0** | 0 | 0 / 0 / 0 |
| `2026-08-02-spec-instrumented-rerun/spec-pass/0-spec-verbatim.md` | no | 0 | 13 | 0 | 0 / 4 / 0 |
| `2026-08-02-spec-instrumented-rerun/to-spec-pass/spec-ticket.md` | no | 0 | 13 | 0 | 0 / 4 / 0 |
| `2026-07-28-batch-chunk-lite/0-spec.md` | no | 0 | 4 | 0 | 0 / 0 / 0 |
| `2026-07-28-dlq-retry-cap/new/0-spec.md` | no | 0 | 4 | 0 | 0 / 0 / 0 |
| `2026-07-28-dlq-retry-cap/old/0-spec.md` | no | 0 | 4 | 0 | 0 / 0 / 0 |
| `2026-07-31-build-ablation-antipatterns/spec/0-spec.md` | no | 0 | 4 | 0 | 0 / 0 / 0 |
| `2026-07-31-build-model-compare/0-spec.md` | no | 0 | 4 | 0 | 0 / 0 / 0 |
| `2026-07-31-spec-ablation-cherny/full/0-spec.md` | no | 0 | 4 | 0 | 0 / 0 / 0 |
| `2026-07-31-spec-ablation-cherny/minimal/0-spec.md` | no | 0 | 4 | 0 | 0 / 0 / 0 |
| `2026-07-31-spec-ablation-cherny-2/full/0-spec.md` | no | 0 | 4 | 0 | 0 / 0 / 0 |
| `2026-07-31-spec-ablation-cherny-2/minimal/0-spec.md` | no | 0 | 4 | 0 | 0 / 0 / 0 |
| `2026-07-31-spec-model-compare/opus/0-spec.md` | no | 0 | 4 | 0 | 0 / 0 / 0 |
| `2026-07-31-spec-model-compare/sonnet/0-spec.md` | no | 0 | 4 | 0 | 0 / 0 / 0 |

**Pre-existing totals: 0 FAILs, 75 WARNs, 0 non-zero exits.** No spec in the repo that passed before
Wave 2 fails after it — the story-24 guarantee ("a hand-written or foreign spec is still valid") is
measured, not asserted. The eleven `0 / 4 / 0` rows are the four new obligations firing as WARNs on
old-shape specs, which is the standalone contract working.

Three rows are worth reading rather than skimming:

- **The grown-shape Wave-1 spec is the only pre-existing file that produces literally nothing** — 0
  FAILs, 0 WARNs, exit 0, even unmarked. It was hand-simulated in Wave 1 against #31's prose, before
  any of this code existed, and it satisfies all four obligations plus the prose precondition line.
  That is the strongest single number here: the checks were written from the same prose the spec was
  written from, independently, and they agree.
- **The two ticket-shaped files** (`0-spec-verbatim.md` and its source `spec-ticket.md`) produce 13
  WARNs each. They are *tickets*, not specs — no Files to Touch, no Runtime Invariants, no Coverage
  Map, and five to-spec-shaped headings (`## Solution`, `## User Stories`, `## Implementation
  Decisions`, `## Testing Decisions`, `## Further Notes`) that the known-heading sweep does not
  recognise. All 13 stay WARN and exit stays 0 — which is the honest answer for a file that was never
  claimed to be a 0-spec, but it does mean the heading sweep is noisy when pointed at the wrong
  artifact. See §8, finding 3.
- **The worked example** is the only pre-existing file whose behaviour Wave 2 *changed*: 1 FAIL / exit
  1 → 0 FAILs / 5 WARNs / exit 0. That is D9, and it is broken out in §6.

### 1c. Total

**43 files · 19 FAILs · 90 WARNs · 15 non-zero exits — all 19 FAILs and all 15 non-zero exits inside
`fixtures/`.**

---

## 2. AC 1's falsifiability pair — marker present ⇒ FAIL, marker absent ⇒ WARN

AC 1 of #35 is *"All template obligations present and mechanically checked (chain marker present ⇒
FAIL, absent ⇒ WARN)"*. A check that only ever WARNs would pass a careless reading of that. The
fixture set makes it falsifiable by construction: **ten twin pairs, each differing by exactly one
line.**

```
$ for base in four-obligations-missing no-external-interface no-source-column empty-source-cells \
              no-ac-coverage-map no-mode-prediction two-mode-lines unclosed-fence \
              bare-heading-in-surface empty-external-interface; do
    printf '%s: ' "$base"; diff "$base-standalone.md" "$base-chained.md" | tr '\n' ' '; echo
  done
                                        # (newlines folded to keep one pair per line)
four-obligations-missing:  3a4 > > Spec-ticket: https://github.com/arkaphat/arkaphat-builder/issues/35
no-external-interface:     3a4 > > Spec-ticket: https://github.com/arkaphat/arkaphat-builder/issues/35
no-source-column:          3a4 > > Spec-ticket: https://github.com/arkaphat/arkaphat-builder/issues/35
empty-source-cells:        3a4 > > Spec-ticket: https://github.com/arkaphat/arkaphat-builder/issues/35
no-ac-coverage-map:        3a4 > > Spec-ticket: https://github.com/arkaphat/arkaphat-builder/issues/35
no-mode-prediction:        3a4 > > Spec-ticket: https://github.com/arkaphat/arkaphat-builder/issues/35
two-mode-lines:            3a4 > > Spec-ticket: https://github.com/arkaphat/arkaphat-builder/issues/35
unclosed-fence:            3a4 > > Spec-ticket: https://github.com/arkaphat/arkaphat-builder/issues/35
bare-heading-in-surface:   3a4 > > Spec-ticket: https://github.com/arkaphat/arkaphat-builder/issues/35
empty-external-interface:  3a4 > > Spec-ticket: https://github.com/arkaphat/arkaphat-builder/issues/35
```

**10/10 pairs: identical bytes apart from the marker line; identical message text; severity flips
`WARN` → `FAIL` and exit `0` → `1` in every pair.** The headline instance, quoted literally from
[`logs/validator-matrix.log`](logs/validator-matrix.log):

```
$ python3 validate_spec.py fixtures/four-obligations-missing-standalone.md .
WARN: no 'Source' column in the AC Coverage Map header — every AC must cite its intent-layer origin (US-n / ID§x / ⚠ inferred)
WARN: no '## External Interface' section — kestra-exam must run at the seam this section declares; without it the exam guesses (permanent false-fail risk)
WARN: no recorded mode-prediction fact — '## Mode Prediction' must carry a line 'kestra-build mode: `full`|`lite`' with the reason
WARN: '## Notes' is not a template section heading — a bare '## ' inside a requirement-surface section body truncates the surface; use '### ' for a subsection, or fence a literal
exit=0

$ python3 validate_spec.py fixtures/four-obligations-missing-chained.md .
FAIL: no 'Source' column in the AC Coverage Map header — every AC must cite its intent-layer origin (US-n / ID§x / ⚠ inferred)
FAIL: no '## External Interface' section — kestra-exam must run at the seam this section declares; without it the exam guesses (permanent false-fail risk)
FAIL: no recorded mode-prediction fact — '## Mode Prediction' must carry a line 'kestra-build mode: `full`|`lite`' with the reason
FAIL: '## Notes' is not a template section heading — a bare '## ' inside a requirement-surface section body truncates the surface; use '### ' for a subsection, or fence a literal
exit=1
```

Exactly 4 WARNs / exit 0 standalone, exactly 4 FAILs / exit 1 chained, from one added line.

Two deliberate non-flips are also measured, and they are the interesting negative controls: a
mode line with no stated reason, and a missing prose `Delimiter precondition:` line, stay `WARN`
even under the marker (`mode-without-reason-chained.md`, `no-precondition-line-chained.md`, both
exit 0). Grading prose is not the script's job, and the prose line adds no enforcement — the
enforcement is the extractor call.

### The four degenerate markers

`partial marker ⇒ FAIL` is the rule lifted from `validate_workflow.py`'s partial anchor triple, and
it is what stops "just delete the URL" from becoming a way to downgrade a chain spec to WARNs. All
four behave:

```
marker-valueless-chained.md   FAIL: chain marker 'Spec-ticket:' present but malformed ('') — a partial marker is a FAIL …
marker-malformed-chained.md   FAIL: chain marker 'Spec-ticket:' present but malformed ('<ticket-url>') — …
marker-duplicate-chained.md   FAIL: 2 'Spec-ticket:' marker lines in the preamble — exactly one is allowed
marker-below-preamble.md      FAIL: 'Spec-ticket:' line outside the preamble — it must sit above the first '## ' …
```

`marker-malformed-chained.md` is the realistic one: the template's `<ticket-url>` placeholder copied
through unsubstituted. It FAILs rather than reading as standalone.

---

## 3. The verbatim check (D3), both legs

No live ticket is involved — Wave 1 left a real pair on disk: `to-spec-pass/spec-ticket.md` (what the
to-spec pass produced, standing in for the `gh … --json body --jq .body` stream) and
`spec-pass/0-spec-verbatim.md` (what commit 1 would have materialized). Literal output:
[`logs/verbatim-check.log`](logs/verbatim-check.log).

**PASS leg:**

```
$ cat …/to-spec-pass/spec-ticket.md | tr -d "\r" > /tmp/t35/ticket-body.md
$ diff -u …/spec-pass/0-spec-verbatim.md /tmp/t35/ticket-body.md
diff exit=0   <- PASS: byte-identical after the one declared normalization
$ sha256sum <both>
6fdcee78ec16b752854f52eb01629e1c2d4fc3878c747dee6ece55be6ed090f4  …/spec-pass/0-spec-verbatim.md
6fdcee78ec16b752854f52eb01629e1c2d4fc3878c747dee6ece55be6ed090f4  /tmp/t35/ticket-body.md
CR bytes in the materialized file: 0  (so tr -d "\r" is a verified no-op on this pair)
```

430 lines, 0 CR bytes, one hash. The `Ticket-body-sha256:` line D7 puts in commit 1's message would
be `6fdcee78…` — the offline fallback when the tracker is unreachable.

**FAIL leg** — one character changed on a `/tmp` copy (`triage-labels.md` → `tpiage-labels.md`):

```
$ diff -u …/spec-pass/0-spec-verbatim.md /tmp/t35/ticket-body-tampered.md
@@ -1,7 +1,7 @@
 <!-- triage labels as they would be applied: `enhancement` (category) + `ready-for-agent` (state).
-     No `docs/agents/issue-tracker.md` or `docs/agents/triage-labels.md` exists in this repo, so the
+     No `docs/agents/issue-tracker.md` or `docs/agents/tpiage-labels.md` exists in this repo, so the
       canonical label vocabulary is assumed. -->
diff exit=1   <- FAIL: hard stop, no handoff
$ sha256sum /tmp/t35/ticket-body-tampered.md
78828029c6b7e3ab37e9c857a65e375b6e381756166923bcc659e2ab96399caf
```

This is the argument for `diff` over a hash comparison, in one screen: the hash says *changed*, the
diff says *what*, for free, at the moment the human has to choose between the two honest fixes.

**Also verified against the live tracker, read-only:** `gh issue view 35 --repo … --json body --jq
.body` returns 1486 bytes with **0 CR bytes** today (sha256 `a3f514e0…`). So `tr -d '\r'` is
currently a no-op on this tracker — which is the point of declaring it anyway: the day someone edits
a body in the web UI it stops being one, and a normalization that only sometimes applies is not a
normalization.

---

## 4. Raise-commit discovery (D7) — five legs in a scratch repo

Two commits minted in `/tmp/t35/scratch` per D7's shapes (nothing in this repo was committed).
Literal output: [`logs/raise-discovery.log`](logs/raise-discovery.log).

```
$ git log --oneline
7c706a2 spec(operator-console): raise vetted ticket into 0-spec.md
3c04d75 spec(operator-console): materialize vetted ticket verbatim
```

| Leg | Situation | Command result | Design says |
|---|---|---|---|
| A | one raise | `count=1` → `PASS exactly-one` | proceed |
| B | wrong ticket URL in the predicate | `count=0` | HARD FAIL — never anchor to a hand-picked SHA |
| C | subject matches but the body line does not (`^Vetted-by:` against commit 1) | `count=0` | `--all-match` really does AND the two `--grep`s |
| D | a re-raise **stacked** instead of reset | `count=2`, two SHAs printed | HARD FAIL — ambiguous by construction, never take the newer |
| E | an identical raise on a sibling branch | current branch `1`, `--all` `2` | why the predicate is current-branch-only |

Leg E is the one that would have been easy to get wrong and is now measured:

```
--- leg E (proper): identical raise on a sibling branch ---
current-branch matches: 1
with --all: 2
```

Adding `--all` to be "thorough" converts a healthy repo into a permanent HARD FAIL the moment anyone
branches. Leg C confirms the anchoring assumption D7 rests on — `git log -E --grep='^…'` anchors per
message *line*, so `^Spec-ticket: <url>$` matches a trailer inside the body, not just the subject.

**Composition with D3 also holds mechanically:**

```
$ git show --format='%s' --stat $R^
spec(operator-console): materialize vetted ticket verbatim
 workflows/runs/operator-console/0-spec.md | 1 +
verbatim body at <raise>^: [body]
```

`<raise>^` *is* commit 1, so the verbatim check needs no second search — provided nothing is
committed between the two, which is a rule in SKILL.md and not something any command here can
enforce.

---

## 5. The chain marker vs the Wave-1 grown shape (D1)

**Is the Wave-1 grown-shape spec marked? No.**
`workflow/evals/2026-08-02-spec-instrumented-rerun/spec-pass/0-spec.md` carries no `> Spec-ticket:`
line and is classified `standalone` by the recogniser. That is correct and expected rather than a
gap: the file was **hand-simulated** in Wave 1, by an agent working from #31's prose, weeks before
the marker was decided. It is not a chain artifact and must not claim to be one — a spec gets the
marker only from a real raise over a real vetted ticket.

The honest consequence, stated rather than buried: **the grown-shape spec is evidence that the
obligations are writable and mutually consistent, not that the chain produced them.** Its 0/0/exit-0
row in §1b is a strong signal (it satisfies all four checks with nothing hand-tuned to them) but it
is not a chain end-to-end. That arrives in Wave 5.

**The marker is provably outside the requirement surface** — D1's central claim, re-verified here
rather than taken from the design record ([`logs/surface-hash.log`](logs/surface-hash.log)):

```
$ python3 requirement_surface.py …/spec-pass/0-spec.md --hash
e1c70ae8e3f6810cd8d85503f91b31e851aa9eb79af1f7da1c3c93dc159acc27
# same file, one '> Spec-ticket: …' line injected into the preamble on a /tmp copy
$ python3 requirement_surface.py /tmp/t35/grown-marked.md --hash
e1c70ae8e3f6810cd8d85503f91b31e851aa9eb79af1f7da1c3c93dc159acc27
```

Byte-identical, and equal to the value the design record cites. Same result on the fixture twins,
where the *only* difference is the marker:

```
four-obligations-missing   standalone=d17688be…  chained=d17688be…
no-external-interface      standalone=0d01c2ca…  chained=0d01c2ca…
```

**The extractor rename did not move a hash either** — `_canonical` → `canonical_heading` is why
`EXTRACTOR_VERSION` stays `1`, and that is checkable:

| Spec | `HEAD` extractor | working-tree extractor |
|---|---|---|
| grown shape | `e1c70ae8…` | `e1c70ae8…` |
| worked example | `f3afabe1…` | `f3afabe1…` |

The D9 fixture repair is also surface-neutral: the pre-repair and post-repair worked example both
hash `f3afabe1…`, because the repair touched a Files-to-Touch row and a preamble note, both out of
surface.

---

## 6. The worked-example repair (D9), before and after

[`logs/worked-example-d9.log`](logs/worked-example-d9.log). Two changes, one to the validator and one
to the fixture, and the log shows why both were needed.

```
$ python3 <HEAD validator> <HEAD 0-spec.md> .        # before, both sides
FAIL: Files to Touch row '*(n/a — example spec)*' marked '—' but the path does not exist on disk
exit=1

$ python3 <new validator> <HEAD 0-spec.md> .          # validator fix alone already clears the FAIL
WARN: Files to Touch row 1 names no file path ('*(n/a — example spec)*') — the path-existence check cannot run on it
WARN: no 'Source' column in the AC Coverage Map header …
WARN: no '## External Interface' section …
WARN: no recorded mode-prediction fact …
WARN: no 'Delimiter precondition:' line in the preamble …
exit=0

$ python3 <new validator> <repaired 0-spec.md> .      # the shipped state
… same five WARNs, first one now quoting '*(none — illustrative spec, no repo attached)*'
exit=0
```

Post-repair, quotable in the PR's `## Verification`: **`workflow/runs/order-cancellation-refund/0-spec.md`
— 0 FAILs, 5 WARNs, exit 0.**

The `git diff` is 5 insertions / 1 deletion: the placeholder row is replaced with a path-less one that
says *why* it is path-less, and a preamble note records the deliberate exclusion from Wave-2 template
growth (`*(Pre-Wave-2 template shape, kept as the standalone/foreign-shape exemplar …)*`). The
exclusion is load-bearing rather than laziness — `requirement_surface.py`'s "BOTH SPEC SHAPES"
docstring names this exact file as the old-shape artifact, so growing it would invalidate the
docstring and delete the only real (non-fixture) file exercising the absent-section path.

Note the ordering the log makes visible: **the validator correctness fix is what clears the FAIL; the
fixture edit is cosmetic honesty on top of it.** The repaired row still names no path, so a validator
without the path-less skip would FAIL on the repaired fixture too — which is exactly what the
`HEAD:1/0/1` column in §1b shows when the pre-Wave-2 validator is pointed at the repaired file.

---

## 7. The standalone path (D5) and the end-of-pass check point (D6)

[`logs/step8-emission.log`](logs/step8-emission.log).

**Standalone is not vestigial, measured two ways.** First, a conforming spec with the marker line
stripped — the same file the chain would produce, minus its provenance — passes clean:

```
$ grep -v '^> Spec-ticket:' fixtures/conforming-chained.md > /tmp/t35/conforming-standalone.md
$ diff /tmp/t35/conforming-standalone.md fixtures/conforming-chained.md
3a4
> > Spec-ticket: https://github.com/arkaphat/arkaphat-builder/issues/35   (the only difference)
$ python3 validate_spec.py /tmp/t35/conforming-standalone.md .
exit=0        (no output)
```

Second, the deficient standalone twin from §2 exits 0 with exactly the four WARNs. Together those are
the standalone contract: *nothing about the four checks blocks a hand-written spec, and a hand-written
spec that meets the template is silent.* Ten of the 28 fixtures, the worked example, and all eleven
pre-existing eval specs run this path.

**D6's exact step-8 invocation works from the emitted copy:**

```
$ cp <scripts-dir>/requirement_surface.py <scripts-dir>/validate_spec.py $RUN/
$ python3 $RUN/validate_spec.py $RUN/0-spec.md <repo-root>
validate_spec exit=0
$ python3 $RUN/requirement_surface.py $RUN/0-spec.md >/dev/null
surface exit=0
```

Copy-per-run holds: the emitted `validate_spec.py` imports the emitted `requirement_surface.py` from
beside it, with no reference to `~/.claude/skills/`.

**The ImportError fallback degraded further than D10 describes** — see §8, finding 2, and the
round-1 fix recorded there.

---

## 8. Three things that did not behave as designed

Reported as found; the eval itself only measures. **Round-1 review update:** findings 1 and 2 were
fixed in the change set afterwards — each carries its fix below, with the re-run output. Finding 3
still stands.

**1 — the D2 vetted-read `jq` expression errors on the absent case, instead of returning empty.**
The expression in `SKILL.md:78` (verbatim from the design record) ends
`… |sort_by(.createdAt)|last|[.createdAt,…,(.body|split("\n")[0])]|@tsv`. With no `VETTED-FOR-KESTRA`
comment on the ticket, `last` is `null` and `split` raises. Run against the real #35
([`logs/vetted-gate.log`](logs/vetted-gate.log)):

```
$ gh issue view 35 --repo arkaphat/arkaphat-builder --json comments --jq '…as specified…'
split cannot be applied to: null
exit=1
```

"No vet comment" is the single most common gate outcome and it is the one the expression cannot
express: exit 1 with a jq error is indistinguishable from a network failure, a bad repo name, or an
auth problem, so an agent reading only the exit code cannot tell *bounce with the paste-ready command*
from *retry/escalate*. A `select(.!=null)` before the array constructor restores empty-output/exit-0,
verified both ways:

```
$ … |sort_by(.createdAt)|last|select(.!=null)|[…]|@tsv
exit=0 (empty output = no vet comment)
# and it still picks the newest when one exists (synthetic input, local jq):
2026-08-02T00:00:00Z	arkaphat	VETTED-FOR-KESTRA: a3f514e0…
exit=0
```

**Round-1 fix (R1-1):** the `select(.!=null)` now ships in `kestra-spec/SKILL.md` step 0a, with the
paragraph that makes the contract explicit — *empty output plus `exit=0` is the "no vet comment"
signal; a non-zero exit means the read failed, so retry or escalate rather than bounce.* This is a
measured correction to D2's design record, not a silent deviation.

**2 — without `requirement_surface.py`, check 4 vanished silently even under the marker.** *(Fixed
in round 1 — the measurement and then the fix, below.)*
D10 specifies the ImportError fallback as `get_section` matching plus one WARN that heading matching
is approximate. What happened as measured here is that the delimiter check was skipped entirely, in
both modes:

```
== unclosed-fence-chained, extractor ABSENT beside validate_spec.py
WARN: requirement_surface.py not found beside this script — heading matching is approximate
WARN: delimiter-precondition check skipped — it needs requirement_surface.py
exit=0
== unclosed-fence-chained, extractor PRESENT
FAIL: unclosed code fence — the requirement surface would be silently truncated (false-fresh hash)
exit=1
```

Same flip for `bare-heading-in-surface-chained` (`exit=0` → `exit=1`). So a **chain** spec whose
requirement surface is silently truncated passed the gate when the extractor was missing. It was
announced (two WARNs, not silence) and D6's resolution order looks in `$RUN/` first, where step 8 just
put both files — but the two files can drift apart in a hand-assembled run folder, and the failure
mode this check exists to catch (a false-fresh `surface_hash` reaching Wave 3/4) is exactly the kind
that is invisible downstream.

**Round-1 fix (R1-2), taking the FAIL option:** "cannot run" now reports through the same chain
conditional as everything else the marker governs — FAIL when marked, WARN when unmarked. *Not-run
is not passed*, and the standalone contract is untouched. Re-run with the extractor absent:

```
== unclosed-fence-chained, extractor ABSENT beside validate_spec.py
WARN: requirement_surface.py not found beside this script — heading matching is approximate
FAIL: delimiter-precondition check cannot run — requirement_surface.py is not beside this script, so a silently truncated requirement surface would pass as fresh. Copy requirement_surface.py next to validate_spec.py (kestra-spec emits both together) and re-run
exit=1
== unclosed-fence-standalone, extractor ABSENT
WARN: … (same sentence, WARN)
exit=0
```

`bare-heading-in-surface-chained` behaves the same (`exit=1`). Both `SKILL.md` step 8 ("copy both
files or neither") and the validator docstring record the rule; the full re-run is in
[`fixtures/validator-run-log.txt`](fixtures/validator-run-log.txt) §6. Every extractor-*present*
result is unchanged — the 43-file matrix re-ran byte-identical.

**3 — the known-heading sweep is noisy on non-spec Markdown.**
Pointed at a to-spec ticket, it reports five to-spec section headings (`## Solution`, `## User
Stories`, `## Implementation Decisions`, `## Testing Decisions`, `## Further Notes`) as "not a
template section heading". All WARN, exit 0, so nothing breaks — but if a run folder ever holds a
ticket-shaped file at a spec path *with* a marker, those five become FAILs whose text
("truncates the surface") misdescribes the problem. Low severity; noted because `TEMPLATE_SECTIONS` is
the kind of list that gets copied.

---

## 9. Scope of evidence — what this eval does not establish

- ❌ **No live reshaped-`kestra-spec` pass was run.** Every number here comes from a script, a
  fixture, or a scratch repo. Nothing measures whether an agent handed the 541-line SKILL.md actually
  performs step 0's gate, produces two commits in the right order, runs step 8 before commit 2, or
  bounces instead of inventing a business rule. That is the Wave-5 dogfood (#31 story 27), and until
  it runs, the skill text is unexercised prose with a mechanically-verified *substrate*.
- ❌ **The vetted gate (D2) was never exercised end-to-end**, because doing so requires posting a
  `VETTED-FOR-KESTRA:` comment and this eval is read-only on GitHub by rule. What is measured: the
  read command against a real ticket with no vet comment (§8 finding 1), the body-hash pipeline
  (`a3f514e0…`, 0 CR bytes), and the newest-wins selection on synthetic input. The match, mismatch and
  local-file-tracker legs are unmeasured.
- ❌ **The bounce (D4) is entirely unmeasured.** `BLOCKED_ON_INTENT`, the two-clause discriminator, and
  the `BOUNCE-<n>` entry shape are prose in SKILL.md with no mechanical check anywhere — the validator
  does not read the status line, and no fixture carries a bounce. Whether the discriminator actually
  keeps the stop narrow (bounce on undecided branches, `⚠ inferred` on missing numbers) is a judgment
  call that only a live pass on an intent-silent ticket can test. Wave 1's grown-shape pass is the
  only evidence in the direction of "narrow", and it is indirect: `needs_ba: false`, with OI-5/6/7
  handling missing constants by inference.
- ❌ **The verbatim check ran against a stand-in, not a tracker.** `to-spec-pass/spec-ticket.md` is a
  committed file, so the `gh … | tr -d '\r'` half of the pipeline was exercised separately (§3) rather
  than as one stream. CRLF handling is therefore reasoned about, not observed: no tracker body with
  actual CR bytes was tested.
- ❌ **Discovery was demonstrated in a two-commit toy repo**, not on real history. Legs A–E cover the
  predicate's own logic; they say nothing about behaviour after a rebase, a squash merge, a
  cherry-pick, or a `filter-branch`, all of which rewrite the subject/trailer pair the predicate keys
  on. D7's ">1 ⇒ resolve by naming the intended SHA" is the documented escape hatch and it is untested.
- ❌ **No downstream consumer read any of this.** `kestra-exam` does not exist yet (Wave 3), and
  `validate_workflow.py`'s anchor triple is Wave 4. That the marker sits outside the surface is
  measured (§5); that a Wave-4 anchor and the extractor's input are the same object is a design claim
  with no consumer to check it against.
- ❌ **Fixtures are minimal by construction** — ~2.5 KB each, one defect apiece. They prove the checks
  discriminate; they do not prove the checks behave on a 745-line real spec with nested tables and
  fenced YAML. The grown-shape spec is the only large file in the matrix, and it exercises the pass
  path only.
- ⚠️ **n=1 on the honest-agreement result.** "Wave 1's hand-simulated grown shape satisfies all four
  checks" is one file written by one agent from the same prose the checks came from. Convergent, not
  independent.

---

## 10. Artifacts

- `fixtures/` — 28 fixture specs (14 marked, 10 unmarked, 4 degenerate markers) + the implementer's
  own `validator-run-log.txt`. Ten of them are twin pairs differing by one line; **do not edit one
  half of a pair without the other**, or §2's falsifiability argument silently stops holding.
- `logs/run-matrix.py` — the driver for §1: the file list, the per-file repo-root choice, and the
  `HEAD`-validator comparison. Rerunnable; writes to `/tmp/t35/`.
- `logs/validator-matrix.log` — 326 lines, every command and every line of output behind §1.
- `logs/verbatim-check.log` — §3, both legs.
- `logs/raise-discovery.log` — §4, legs A–E.
- `logs/surface-hash.log` — §5, the marker-injection hash comparison.
- `logs/step8-emission.log` — §7 and §8 finding 2: emitted-copy run, the extractor-absent
  degradation on two chained fixtures, and (appended) the round-1 re-run after "cannot run" became
  a FAIL under the marker.
- `logs/vetted-gate.log` — §8 finding 1 and the live body-hash pipeline.
- `logs/worked-example-d9.log` — §6, including the full `git diff` of the repair.
