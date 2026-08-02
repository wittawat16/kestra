# `manifest.md` — seven sections, fixed order, verdict contract last

Read this while writing or regenerating a manifest. One file, Markdown, hand-parseable — repo-native,
greppable, diffable, the same stance `validate_workflow.py` takes by hand-parsing the YAML subset it
needs rather than importing a parser.

Section order is **fixed** so a regeneration is a bounded diff, and so the verdict is always a tail
append that touches nothing above it.

---

## 1. `# Exam manifest — <feature-slug>`

The title line, and nothing else in the section.

## 2. `## Anchor`

```markdown
| Field | Value |
|---|---|
| raise_commit | <40-hex> |
| surface_hash | <64-hex> |
| extractor_version | 1 |
| origin_key | github.com__arkaphat__kestra |
| feature_slug | order-cancellation-refund |
| spec_path | workflows/runs/<slug>/0-spec.md |
| exam_script_sha256 | <64-hex> |
| generated_at | <ISO-8601 Z> |
| generation | 1 |
```

`exam_anchor.py` parses this table, so the two-column pipe shape and the exact field names are load-
bearing.

**Why the manifest hashes `exam.py` and not itself:** a self-hash is a self-certification. The pointer
holds both hashes (`exam_script_sha256` and `manifest_sha256`), so the pair is closed across two
artifacts and neither one certifies itself.

## 3. `## Read rule`

Three things, in this order:

1. The in-surface sections, named **by pointing** at `requirement_surface.SURFACE_SECTIONS` — never
   restated. That module is the single owner of the boundary; a copy here would be a second boundary
   that drifts silently.
2. The never-read list: `## Files to Touch`, `## Codebase Survey`, `## Solution Architecture`, and the
   Coverage Map's `Covered by (files/steps)` column.
3. A **verbatim fenced quote** of the `## External Interface` lines the `SEAM` encodes.

The quote is load-bearing, not decoration: `exam.py --audit-seam` extracts the fenced block from this
section and requires `seam.target()` to appear in it verbatim.

## 4. `## Checks`

Seven columns, this exact header:

```markdown
| AC | Check | Class | Provenance | Red-proof | Failure signature | Unexaminable |
|----|-------|-------|------------|-----------|-------------------|--------------|
| —    | C-0  | must-hold    | —          | n/a — must-hold                       | —                                              | — |
| AC-4 | C-3  | must-flip    | ⚠ inferred | red 2026-08-02T14:02:55Z behavioral    | `CheckFailure: exit 1 != 0 @ tally --refund`   | — |
| AC-7 | C-9  | must-hold    | US-3       | n/a — must-hold                       | —                                              | — |
| AC-11| C-12 | must-flip    | US-6       | **born-green — `unproven`**           | —                                              | — |
| AC-2 | C-5  | must-flip    | US-1       | **red … infrastructure — `unproven`** | `SeamUnavailable: cannot spawn python3 src/tally.py` | — |
| AC-13| C-14 | unexaminable | ID§2       | —                                     | —                                              | invariant fires only on disk-full; the CLI seam cannot induce it |
```

**The `AC` column *is* the AC→check map.** `exam_delta.py` reads it; there is no second artifact.

**Red-proof is a closed set** — five values, so it is greppable and countable:

| Cell | Means |
|---|---|
| `n/a — must-hold` | measured green on the pre-implementation tree, as its class says |
| `red <ISO> behavioral` | the seam answered and the answer was wrong — **the only value that is proof** |
| ``red <ISO> infrastructure — `unproven` `` | the seam was never reached, so the red says nothing about this check's ability to go green |
| ``**born-green — `unproven`**`` | a `must-flip` that passed at red-proof time |
| ``void — C-0 red at red-proof (harness) — `unproven` `` | the whole red-proof is void; every `must-flip` row carries this |

**Failure signature** — the first line of the recorded red proof, backticked, ≤120 characters,
**verbatim from `red-proof.json`**. Never retyped, never tidied. Empty ⇒ `—`.

**Provenance** mirrors the Coverage Map's `Source` cell; a check derived from an `⚠ inferred`
requirement line is marked `⚠ inferred`, because the requirement behind it originated in a spec pass
rather than upstream.

**Unexaminable** is filled iff `Class` is `unexaminable`, and names *why the declared seam cannot
induce the condition* — not why it is hard.

## 5. `## Delta map`

```markdown
### Section fingerprints
| Section | sha256-12 |
|---|---|
| Functional Requirements | 3c91ab27de40 |
| Edge Cases & Error States | … |
| Runtime Invariants | … |
| AC Coverage Map | … |
| External Interface | … |
### AC fingerprints
| AC | sha256-12 |
|---|---|
| AC-1 | 9f2c1ab34de0 |
```

Fingerprints come **only** from the extractor's own output:
`sha256("\n".join(surface.sections[name]) + "\n")` per section, and `sha256(row)` per Coverage-Map row
where `row` is exactly what `requirement_surface._ac_rows` emits (`"<AC> | <Source>"`). First 12 hex
characters.

There is **no second normalization anywhere in kestra-exam**. That is why a column reorder, a checkbox
flip, a list-marker change and a reflowed paragraph are already non-events — the extractor's own pinned
tests own that behavior, and a second normalization here would quietly disagree with them.

Regenerate these tables in full on every generation; they are cheap and a partial refresh is a
guaranteed false `carry`.

## 6. `## Coverage`

One line:

```
ACs in surface: N · executably covered: M · unexaminable: K · must-flip: F (unproven: U) · must-hold: H
```

`N = M + K`. `U` is the count of `unproven`-flagged rows and must equal `summary.unproven` in
`red-proof.json`. Counts include `C-0` in `must-hold` and in `H`.

## 7. `## Verdict contract` — always the final section

Copy the rule text verbatim; the fill-in block below the delimiter is what a gate runner appends.

```markdown
A verdict is emitted only when the anchor triple recomputes equal (see §Anchor);
otherwise REFUSED — stale anchor, and no verdict line is written at all.
PASS iff C-0 passed AND every must-flip and must-hold check passed AND no check
reported an infrastructure red.  FAIL if any check failed behaviorally.
BLOCKED if the run exited 2 (harness).  Unexaminable rows never pass or fail;
they are listed by AC id.  U>0 ⇒ the evidence clause is MANDATORY: a PASS with
U>0 and no clause is a malformed verdict, i.e. a gate failure.

--- verdict (appended by the gate runner; unfilled above this line) ---
verdict:   PASS | FAIL | BLOCKED | REFUSED
evidence:  full | degraded — <U> unproven of <F> must-flip
coverage:  <M>/<N> ACs executably covered; unexaminable: <AC ids>
run:       <ISO-8601 Z> · exam.py sha256 <12> · exit <code>
```

The verdict is terminal by construction: it is the last section of the last file, so appending it
cannot perturb a fingerprint, a check row, or the anchor.

**Nor the pointer's `manifest_sha256`:** that hash is defined over this file from its first byte through
the **first** `--- verdict … ---` delimiter line, inclusive — not over the whole file — so an appended
verdict leaves it unchanged. The recipe, and why re-recording the pointer after an append was rejected
instead, live in [`gate-procedure.md`](gate-procedure.md) §5. A manifest carrying no delimiter line at
all is malformed: hard fail.

**Which `U` and `F` the clause uses:** the manifest's own `## Coverage` counts (§6) — where `U` was
filled from `red-proof.json`'s `summary.unproven` at red-proof time — and **never** the
`summary.unproven` of the gate run's own `exam.py --json`. That per-run number counts must-flip checks
with no behavioral red *in that run*, so it equals the must-flip total on a green delivery and would
stamp `degraded — 3 unproven of 3 must-flip` on perfect work (measured 1 vs 3, eval
`workflow/evals/2026-08-02-wave3-kestra-exam` finding F5).

---

## Manifest FAILs

A manifest is defective — fix it, do not work around it — when any of these hold:

* an AC in the Coverage Map owns **no** check row (this is what makes "the exam skipped the awkward AC"
  visible)
* a Red-proof cell is outside the five closed values
* a Failure signature does not appear verbatim in `red-proof.json`
* `Class` contradicts what the red proof measured (a `must-hold` that was red, a `must-flip` recorded
  `n/a — must-hold`)
* `## Coverage`'s `unproven: U` disagrees with `summary.unproven` in `red-proof.json`
* the manifest carries no `--- verdict … ---` delimiter line (§7)
* the seven sections are out of order, or `## Verdict contract` is not last
* a `PASS` verdict with `U > 0` and no `evidence: degraded` clause
