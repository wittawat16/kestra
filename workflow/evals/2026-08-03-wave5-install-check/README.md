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
| Scrutinize rounds and C/M/m per round | 2 rounds: R1 `1/0/1` (Major/Minor; no Critical), R2 `0/0/0` |
| Deviations | 1: Luna Max implementation attempts timed out; controller fallback stayed within the frozen write scope |
