# Eval — kestra-run, REAL live execution (FULL vs MINIMAL), scoped to implement-tier-retry

Follow-up to the dry-run Q&A round. This one is real: two isolated git repos (outside the kestra
repo entirely, under scratchpad — kestra-run does real commits, so this never touches the actual
project's git history), each seeded with an identical 3-commit history (baseline → generate-tests
passed [real code diff] → freeze-tests passed [state.json only, no code diff — the exact "walk back
past a no-diff commit" scenario Q1 tested]), then handed to a real orchestrator agent running either
the full `kestra-run/SKILL.md` or the ablated one from the dry-run round. Each orchestrator actually
read state.json, actually spawned a real nested subagent (via the Agent tool) to implement the
stage, actually ran `git diff`/`npm test`, and actually committed. Scoped to stop right after
`implement-tier-retry` passes — not the full 7-stage pipeline, to keep this bounded.

## Result: identical, verified independently (not just self-reported)

```
$ git log --oneline   (both repos)
stage(priority-tier): implement-tier-retry passed
stage(priority-tier): freeze-tests passed
stage(priority-tier): generate-tests passed
baseline: ...

$ npm test   (both repos, final tree)
pass 9, fail 0
```

Both correctly:
- walked back past the code-empty `freeze-tests` commit to `generate-tests`'s commit for the context
  pack's diff (Q1's prediction, now confirmed live, not just answered in Q&A)
- resolved and pasted the frozen test file's full content (not just its path)
- spawned a real implement subagent, independently re-ran `write_scope` diff and `npm test`
  themselves rather than trusting the subagent's claim (per SKILL.md's own "one rule")
- committed exactly one commit, touching only `src/queue.js` + `state.json`
- correctly advanced `current_stage` to `["verify-acceptance-criteria", "review"]` without actually
  running either — respecting the scoped stop instruction

## Cost — noisier than the other rounds, reported honestly

| | FULL | MINIMAL |
|---|---|---|
| Orchestrator (hard, harness-reported) | 168,871 | 172,756 |
| Nested implement subagent | 121,081 (hard — this orchestrator returned early and the child's completion arrived as its own separate notification, so this number is harness-verified) | ~146,000 (**self-reported by the child in its own prose**, relayed secondhand by the orchestrator — not independently confirmed the same way) |
| Total (best estimate) | ~289,952 | ~318,756 |

Take the "MINIMAL total" with a grain of salt — it rests on a number the child said about itself, not
a harness-confirmed figure the way FULL's child cost is. If anything this makes **the token story a
wash or even reversed** from every prior round (kestra-spec flat, kestra-build −9.6%, dry-run −3%) —
plausibly because a live orchestrator's real cost here is dominated by the nested implement spawn and
the orchestrator's own tool-call overhead (git/npm/file reads), not by how many words were in its own
prompt; the two ablated blocks (context pack, scope-cap) are read once and acted on, not re-consulted
repeatedly the way kestra-build's anti-patterns list apparently was.

## The real finding this round surfaced, independent of the ablation question

**Both orchestrators independently discovered and correctly worked around the same latent bug in the
test-hash setup**, unprompted: the seeded `test_hash` was computed with `cwd` inside the fixture
directory (`find test -type f ...`, path `test/queue.test.js`), but `write_scope` names the file with
a full repo-root-relative path (`workflow/evals/.../fixture/test/queue.test.js`). A strict
literal reading of `enforcement.md`'s canonical formula, run from the repo root as its own text
implies, produces a **different** hash for byte-identical content — the same "two internally
consistent methods, two different hashes" trap `enforcement.md` documents for multi-root
`write_scope` lists, but occurring here in a **single-file, single-root** case via a path-basis (cwd)
mismatch the doc doesn't call out. Both variants correctly diagnosed this as a hash-basis ambiguity
rather than a real test-tamper signal (avoiding a false hard-stop) — but that diagnosis took each of
them real debugging turns. This is a genuine, ablation-independent gap worth fixing in
`kestra-run/references/enforcement.md`: state explicitly that the hash must be computed **relative to
the same working directory `exit_criteria.run` uses** (the fixture root, when commands `cd` into it),
not just that multi-root ordering must be consistent.

## What this does and doesn't establish

- ✅ On the one scenario tested (Q1's context-pack decision), the dry-run's prediction held under
  real execution: both variants made the identical, correct decision with real git commands, not
  just when asked directly.
- ✅ Both variants produced byte-for-byte equivalent-quality implementations, independently verified
  (not self-reported) — same diff shape, same test outcome, same state.json update.
- ❌ **Did not test the scope-cap block live** (Q4/Q5's fixing-loop scenario) — that would require
  seeding a failed review + a partial fix + a second retry, a meaningfully bigger setup. This round
  covered only the context-pack half of the dry-run.
- ❌ Token comparison is noisier than every other round in this series, for a structural reason (one
  child's cost came from a hard notification, the other's from self-reported prose) — don't read the
  "MINIMAL total" figure as precise.
- ❌ n=1 scenario, one model, one scoped stage. Same caveat as every round before this.

## Artifacts

Left in scratchpad (not committed to the kestra repo — these are two real, if small, git histories
and shouldn't be added to the project's actual history): `kestra-run-live/full/`,
`kestra-run-live/minimal/`, each a self-contained git repo with the 4-commit history above.
