# Wave 5 — `install.sh --check`

This is the lean finale entry for #39. It runs the real subprocess/filesystem suite and the
run-local validators through [`run-legs.sh`](run-legs.sh); it does not create an eval framework or
edit historical entries.

Measured result: final green implementation/evidence run recorded below.

| Evidence | Measured value |
|---|---|
| Chain legs | 9/9: to-spec, human vet, kestra-spec, exam, to-tickets, kestra-build, kestra-run, scrutinize/fix loop, manual/finale gate |
| Full-mode stages | 8/8 |
| Feature tests | 9/9 unittest cases; final suite exit 0 |
| Exam AC coverage / red proof / final passes / unproven | 6/8 ACs executable; AC-7/AC-8 unexaminable; red proof 5 must-flip with 1 unproven; final checks 7 pass (including smoke), 0 fail, current-run unproven 5; exit 0 |
| Scrutinize rounds and C/M/m per round | 2 rounds: R1 raised 2 findings, both disposed as false positives after fix (`review-verdict.md` rows 12-13; the per-severity split was never recorded, and the two artifacts that guessed it disagreed), R2 `0/0/0` — `state.json` records the final round only |
| Deviations | 2: Luna timed out on `generate-tests` and Luna Max on `implement-install-check`; both fell back to the controller, inside the frozen write scope (`state.json` spawn_type) |
