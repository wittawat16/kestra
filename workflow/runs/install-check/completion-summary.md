# Install-check completion summary

Final gates are green for the AC-scoped `./install.sh --check` slice.

| Gate | Result | Evidence |
|---|---|---|
| Kestra chain | 9/9 legs | to-spec, human vet, two spec commits, exam, to-tickets, build, run, scrutinize/fix, manual/finale |
| Full-mode workflow | 8/8 stages | `workflow/runs/install-check/state.json` |
| Feature suite | 9/9 tests, exit 0 | `python3 -B -m unittest discover -s tests -p 'test_install_check.py'` |
| Final exam | 7 checks pass, 0 fail, exit 0 | `/private/tmp/kestra-wave5-exams/github.com__arkaphat__kestra/install-check/manifest.md` |
| Exam coverage | 6/8 executable; AC-7/AC-8 unexaminable | degraded evidence: red-proof 1 unproven of 5 must-flip |
| Scrutinize | Round 1 `0/1/1`, round 2 `0/0/0` (C/M/m) | `workflow/runs/install-check/review-verdict.md` |
| Deviations | 1 | Luna Max implementation attempts timed out; controller fallback stayed inside frozen scope |

Stage commits: `04fee2c`, `89393f8`, `b2cbc07`, `7766d3a`, `c568f22`, `37a9535`,
`96c5fc2`. Token counts were unavailable across the multi-session controller run and are omitted;
the persisted state records stage, attempt, and spawn type without guessing usage.
