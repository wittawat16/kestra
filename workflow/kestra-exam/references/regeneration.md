# Regeneration — delta scope, carry-over, and the exam dir's history

Read this when a spec changed after the exam was created, when `exam_delta.py` prints `scope: full`, or
when deciding whether a check may keep its old red proof.

The rule the whole file serves: **a spec edit re-proves only what it invalidated.** Re-proving a whole
exam over a reworded paragraph is the tax that makes people stop editing specs, and an exam nobody dares
regenerate stops being evidence.

---

## 1. The map is already in the manifest

The AC→check map is the `AC` column of `## Checks`. There is no second artifact to keep in sync.

What `## Delta map` adds is fingerprints: a moved `surface_hash` says only *that* the requirement text
changed, never *which AC*. Per-section and per-AC fingerprints turn that into a per-requirement answer.

Every fingerprint comes from the extractor's own output — `sha256("\n".join(surface.sections[name]) +
"\n")` per section, `sha256(row)` per Coverage-Map row where `row` is exactly what
`requirement_surface._ac_rows` emits. **No second normalization exists anywhere in kestra-exam**, which
is why column reorders, checkbox flips, list-marker changes and reflowed paragraphs are already
non-events, guaranteed by the extractor's own pinned tests rather than by a rule restated here.

---

## 2. The plan

```bash
python3 -B <skill>/scripts/exam_delta.py <run-dir> <exam-dir>
```

Exit `0` on any successful analysis — **read the `scope:` line for the outcome**, not the exit code;
exit `1` means the analysis itself could not run (usage, unreadable manifest, no `## Delta map`).

```
scope: delta
why:        AC-4 changed, AC-9 added, AC-6 removed
regenerate: C-3 C-7
new-ac:     AC-9   (ACs with no check row yet — author one each)
delete:     C-11
carry:      C-0 C-1 C-2 C-5
re-anchor:  surface 9a1c4e77b210 -> 4de7f0c9a883 ; raise 1f2a9c04 -> 8b90ee31 ; extractor v1 -> v1
generation: 1 -> 2
red-proof:  every regenerated must-flip needs a FRESH red proof in a new disposable clone at the new raise commit; C-0 runs regardless of --only
```

`new-ac:` lists ACs that gained a fingerprint but own no check row yet — an added AC needs a **new**
check id, which the plan cannot invent for you.

---

## 3. Four scopes, decided in full

### `delta` — AC rows changed / added / removed

Regenerate exactly the checks whose `AC` cell names them. A removed AC **deletes** its checks, and the
deletion is recorded in the regeneration comment so a shrinking exam is visible rather than merely
smaller.

### `full` — the `## External Interface` fingerprint moved

The declared seam itself moved, and every surviving check is driven through it. Regenerate **every
check whose AC still exists**, and delete checks for ACs removed in the same spec edit. This is not
delta-able and the plan says so rather than pretending: a surviving check written against the old seam
either fails to reach the new one (an infrastructure red that proves nothing) or reaches it accidentally,
which is worse. A removed AC cannot be regenerated into the new one-row-per-current-AC manifest.

Re-run `python3 -B exam.py --audit-seam` after rewriting `SEAM` **and** the manifest's quoted External Interface
block; a `full` regeneration that updates the seam but not the quote leaves the audit passing against
stale text.

### `re-anchor` — Functional Requirements / Edge Cases / Runtime Invariants moved, no AC row and no External Interface moved

Regenerate **nothing**. Rewrite the anchor triple, commit in the exam dir, edit the pointer in place.
Checks are keyed one-per-AC, and those sections are the prose the ACs paraphrase.

**Never silent.** The regeneration comment records:

```
re-anchored only; FR/EC/RI moved without an AC row — verify the Coverage Map still paraphrases them
```

Whether the prose still says what the ACs claim it says is human judgment, not a check to automate —
the same posture as "slice boundaries intact vs redrawn". The line exists so a human is asked, not so a
machine can decide.

A moved `## AC Coverage Map` section fingerprint with no moved AC row means the rows were **reordered**;
that is presentation, so it also lands in `re-anchor`.

### `current` — nothing moved

No regeneration, no re-anchor, no pointer edit, no commit. `generation` does not advance.

---

## 4. Carry-over

**A check carries over only on an identical `(check id, normalized AC row)`.** Anything else is
regenerated.

* A regenerated `must-flip` needs a **fresh** red proof: its old Red-proof cell is cleared and re-run in
  a **new** disposable clone at the **new** raise commit.
* A carried-over row keeps its **original** red-proof timestamp. That is honest and visible — the
  timestamp itself shows the evidence predates this generation, which is strictly better than restamping
  it with a date on which nothing was measured.
* The delta red proof is invoked as `python3 -B exam.py --only C-3 C-7 --repo <clone>`, and **C-0 runs
  regardless of `--only`**, because a delta red proof with no smoke is void by exactly the same rule as
  a full one.

---

## 5. The pointer, always

Edited **in place**: same issue or same file, `generation` incremented, one comment (or one appended
`.pointer.log` line) per regeneration:

```
regenerated C-3,C-7 (AC-4 changed, AC-9 added); deleted C-11 (AC-6 removed);
surface 9a1c… → 4de7…; raise 1f2a… → 8b90…; generation 1 → 2
```

A regeneration never opens a second pointer, and `>1` stays a hard fail resolved by hand — see
[`gate-procedure.md`](gate-procedure.md) §4 for the exact text and for why the comment is the artifact
the body-edit check depends on.

---

## 6. The exam dir's history

One feature is one independent git history, so a regeneration is one small commit and an audit reads one
log.

```
exam(<slug>): create from surface <hash12> @ raise <sha12>
exam(<slug>): regenerate C-3,C-7 for surface <hash12> @ raise <sha12>
exam(<slug>): re-anchor to surface <hash12> @ raise <sha12>
```

* Never `git commit --amend`, and never squash: the superseded generation *is* the audit trail. A
  regeneration that rewrote history would make "which requirement text was this red proof taken against"
  unanswerable — the one question the whole design exists to answer.
* No remote is ever added; `exam_paths.assert_no_remote()` re-checks this on every invocation, because a
  remote republishes the evidence.
* Identity comes from global git config. A commit that fails for a missing identity is a loud stop, not
  something this skill configures on a user's behalf.

Completion criterion for a regeneration: `git -C <exam-dir> log --oneline | wc -l` increased by exactly
1, the pointer's `exam_commit` was refreshed to that new full `HEAD` before the gate,
`exam_anchor.py` exits 0, and `exam_delta.py` re-run now prints `scope: current`.
