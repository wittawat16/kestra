# Eval — kestra-spec, FULL prose vs. ABLATED (minimal) prompt, round 2 (needs_ba: true)

Follow-up to `2026-07-31-spec-ablation-cherny/`. That round's idea produced `needs_ba: false` on
both variants, so step 3's detailed `needs_ba` instructions (BR-1/BR-2… with example +
counter-example, stakeholder variations) never actually fired — the biggest untested chunk of the
skill's prose. This round plants a genuine multi-stakeholder business rule to force `needs_ba: true`
and see whether the ablated prompt's one-line version of that instruction ("business rules with
example + counter-example... not a stub") produces comparably real content to the full skill's
dedicated bullet.

Same fixture (fresh copy of the retry-queue Node/ESM app), same two prompt variants as round 1
(`full/` = real `kestra-spec/SKILL.md` verbatim, `minimal/` = the same ~40-line distillation from
round 1, unchanged). New idea: `idea-priority-tier.md` — paid-tier messages retry forever (today's
behavior), free-tier messages get exactly one attempt then move to a new `dropped` list, messages
with no/unrecognized tier default to paid (a real "safer default, don't silently regress an
un-migrated caller" rule), operators want per-tier succeeded/dropped visibility.

## Results

| | FULL | MINIMAL | Δ |
|---|---|---|---|
| Subagent tokens | 141,933 | 140,975 | −0.7% |
| Wall time | 225s | 256s | +14% |
| Tool calls | 10 | 11 | +1 |

Token cost flat again — second confirmation that prose length isn't the cost lever in this skill.
Wall time diverged a bit more than round 1 but in the opposite direction from what "more
instructions = more careful = slower" would predict, and both are within normal run-to-run noise for
a single sample each.

## Did both actually treat needs_ba as true, with real content?

**Yes, both.** FULL wrote BR-1 through BR-4 (paid-retries, free-drops-after-one, missing-tier-
defaults-to-paid, skip-path-ignores-tier), each with a Given-When-Then example + counter-example,
plus a 4-row stakeholder-variations list (paid customers, free customers, operators, un-migrated
callers). MINIMAL wrote the same four rules, same structure, same stakeholder list, comparable
depth — down to both independently choosing "un-migrated caller" as a named stakeholder, which
appears nowhere as that literal phrase in the idea (both inferred it from "regression nobody asked
for"). **The ablated prompt's one-line instruction was sufficient to produce the full BR treatment
— the step-3 detail wasn't load-bearing for getting real business-rule content out, at least on this
example.**

## Stopping-rule checklist

| Item | FULL | MINIMAL |
|---|---|---|
| Every AC testable without follow-up | ✅ 8 ACs | ✅ 13 ACs (finer-grained: split enqueue-normalization into its own ACs) |
| `needs_ba: true` → real content | ✅ BR-1..4 + stakeholders | ✅ BR-1..4 + stakeholders, equal depth |
| Files to Touch verified | ✅ both files read in full | ✅ both files read in full |
| Every AC maps to coverage-map row | ✅ 9/9 | ✅ 13/13 |
| Runtime Invariants name on-violation, none "log and continue" | ✅ 2 invariants, both halt | ✅ 2 invariants, both halt, routed through one named choke-point (`pushDropped`) |
| Reality Constraints filled or N/A+reason | ✅ filled | ✅ filled, **plus literal pasted `npm test` terminal output** |
| Step 6 self-check actually run | ⚠️ claims "(2/2 passing, see below)" — **no such block appears anywhere in the file**, a broken forward-reference | ✅ pastes the real command + real output verbatim under Reality Constraints |
| No silent gaps → Open Items | ✅ 1 honest open item (non-`Error` throw value) | ✅ 0 — resolved the same case with a `String(err)` fallback + a dedicated AC instead of deferring it |

**One concrete defect in FULL this round, none in MINIMAL:** FULL's Codebase Survey says npm test
was "verified green before this change (2/2 passing, see below)" — but no such evidence block exists
anywhere in the file. MINIMAL not only claims the run, it pastes the literal terminal output
(`✔ runs a registered handler`, `✔ retries a throwing handler`, `tests 2 / pass 2 / fail 0`). This is
the opposite of what the "more instructions produce more rigor" intuition would predict.

## Where they differed (both legitimate calls, not a defect either way)

- **FULL left the non-`Error`-throw case as an Open Item**; MINIMAL resolved it with a
  `String(err)` fallback and added a dedicated AC for it. The idea gives no guidance either way, so
  FULL's caution is defensible per the skill's own "honest gaps over confident guesses" mindset — but
  MINIMAL's choice is also defensible (a very standard JS idiom) and leaves `kestra-build` with one
  fewer thing to bounce back on. Score this a wash, not a MINIMAL win — unlike the missing-evidence
  defect above, which is unambiguous.
- MINIMAL designed a named `pushDropped()` choke-point that both Runtime Invariants route through;
  FULL's two invariants are separate inline guards at the same call site. MINIMAL's shape is slightly
  more implementation-ready (one place to look), but this is a design-taste difference, not a
  correctness gap in FULL.

## Combined with round 1

Two rounds now, one with all flags false, one with `needs_ba: true` — both show the same pattern:
mechanical checklist parity, flat cost, and if anything a slight edge to the ablated prompt on
concrete evidence and avoiding repetition. **Still untested: `needs_ui: true`** (would need a fixture
with an actual UI/design-token surface — this repo's available fixtures are all backend-only) and
`needs_sa: true`. Those remain the load-bearing candidates worth checking before trimming the skill's
step-3 `needs_ui`/`needs_sa` bullets specifically — nothing here says anything about them one way or
the other.

## Artifacts

- `idea-priority-tier.md` — the seed idea (paid/free tier business rule)
- `fixture/` — fresh copy of the same retry-queue fixture used in round 1
- `full/0-spec.md`, `minimal/0-spec.md` — the two produced specs
