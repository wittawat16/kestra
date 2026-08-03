> Spec-ticket: https://github.com/arkaphat/arkaphat-builder/issues/40
> Delimiter precondition: the requirement sections use the stable template headings above; no bare `##` appears inside a requirement body.

## Overview

Wave 5 dogfood feature: a read-only installer freshness check for the repository's declared skill
inventory. The user drives the existing installer CLI; no new library API or service is introduced.

## External Interface

The single external seam is the existing shell CLI:

- `./install.sh --check` checks the global target under the current `HOME`.
- `./install.sh --check --project <path>` checks the project-scoped target.
- The seam reports one status per declared skill and an aggregate summary on stdout/stderr, with
  exit `0` for current, `1` for any environmental drift or read error, and `2` for invalid usage.
- The exam and black-box tests may drive only this CLI seam and temporary filesystem roots. They do
  not call shell helpers, inspect implementation variables, or read the source files as a shortcut.
- Deliberately absent interfaces: JSON output, selective-skill filtering, a new installer backend,
  and any Codex-specific target. Existing mutating modes remain their own interfaces, unchanged.

## Problem Statement

Copy installs can become stale after the source repository changes. Today a user must invoke the
mutating `--update` path to discover or repair freshness, so a CI job cannot answer whether the
installed set is current without copying, pulling, deleting, or compiling files. A stale install
silently runs old skill behavior.

## Functional Requirements

- FR-1: `--check` accepts global scope or `--project <path>` scope and discovers the installed
  transport from the target rather than accepting a requested transport mode.
- FR-2: For every one of the 16 active skills, a regular-directory install is current only when its
  recursive contents agree with the source after ignoring `__pycache__/`, `*.pyc`, and `.DS_Store`.
- FR-3: For every active skill, a symlink install is current only when its resolved target is the
  canonical source directory for that skill; missing, wrong, and dangling links are findings.
- FR-4: Retired skill directories or links are negative obligations and produce findings; unrelated
  sibling skills are outside this feature's ownership and are ignored.
- FR-5: The check examines all declared skills before returning its aggregate result and reports
  every missing, modified, extra non-ignored, wrong-target, dangling, and retired finding.
- FR-6: `--check` rejects `--link`, `--force`, `--update`, and `--uninstall` with usage exit `2`
  before it touches source or target paths.
- FR-7: A current result returns `0`; any environmental drift, missing path, unreadable path, or
  retired entry returns `1`; invalid command usage returns `2`.
- FR-8: English and Thai installer documentation describes the command, scopes, findings,
  exclusions, purity guarantee, and exit codes consistently.

## Edge Cases & Error States

- A missing target directory reports the declared active skills as missing without creating it.
- A source path missing from the repository is reported as an error and returns `1`; the check does
  not try to repair the repository.
- A non-directory, unreadable, wrong-target, or dangling entry at an active skill destination is a
  finding, not a reason to stop checking the remaining skills.
- A non-ignored extra file inside an installed copy is drift; ignored cache and Finder entries are
  not drift.
- A project path that does not exist keeps the existing installer error behavior and performs no
  target operation.
- Unknown sibling skill directories remain untouched and do not affect the result.
- Combining `--check` with any mutating or transport-selection flag is a usage error before any
  filesystem operation.

## Runtime Invariants

| Invariant | Observable check | On violation |
|---|---|---|
| Check is observationally pure | source and target fingerprints are identical before and after every check | return `1`, report the attempted/read error, and never continue as current |
| Aggregate reporting is complete | all 16 active entries and all retired entries are visited after the first finding | return `1` with every finding; do not fail-fast |
| Exit status is truthful | `0` iff no declared finding exists; `1` for drift/read errors; `2` for usage | fail the command and the black-box test |
| Transport identity is truthful | symlink target is compared to the canonical source path, not merely basename or contents | report wrong/dangling link and return `1` |
| Ownership is bounded | only declared active/retired names are inspected; unrelated siblings remain unchanged | fail the scope test if an unrelated skill is reported or changed |

## Business Rules

- The installer inventory remains the sole owner of the 16 active and four retired names; this
  feature does not change that inventory.
- A copy can be current while containing the three named ephemeral artifact classes, but no other
  extra content is silently accepted.
- `--check` observes the actual installed transport. It never treats a requested `--link` or
  `--copy` preference as a check input.

## Design Notes

Use portable shell primitives already available to the installer environment. Keep the implementation
inside the existing installer entrypoint, with tests driving the process as a user would. Do not
introduce a third-party dependency or a machine-readable output schema.

## Solution Architecture

Argument parsing must recognize the check mode and reject incompatible flags before target resolution
or any mutation. The check path then resolves the same target directory as existing modes, evaluates
active entries and retired entries independently, accumulates findings, prints statuses, and exits
from the aggregate. Existing install/update/uninstall/link branches remain behaviorally unchanged.

## Codebase Survey

- The installer already owns the active and retired inventories, global/project target resolution,
  copy/link installation, update pull, uninstall, and Python compile cleanup.
- The bilingual root READMEs already document installer usage and are the established documentation
  seam for new modes.
- The repository uses stdlib-only Python tests and shell validators; no package manager or third-party
  runtime is required for this feature.

## Reality Constraints

| Dependency or paired reality | What it does | What it does not guarantee | Required response |
|---|---|---|---|
| Source skill tree and installed copy tree | filesystem comparison can observe bytes and names | a successful read does not prove the target will remain unchanged after the check | fingerprint before/after and fail if mutation is observed |
| Source directory and installed symlink target | `readlink` identifies the transport target | same basename or identical contents do not prove the link tracks this repository | require canonical target equality |
| `diff`/filesystem permissions | returns comparison or read errors | a non-zero command result distinguishes neither drift nor unreadable paths by itself | classify any non-zero result as a reported check failure and return `1` |
| cache and Finder metadata | can appear after normal local use | arbitrary extra files are not harmless by default | ignore only the three named patterns |

## Files to Touch

| Path | Change | Reason |
|---|---|---|
| `install.sh` | modify | add the `--check` parser and read-only aggregate check |
| `README.md` | modify | document English CLI behavior and examples |
| `README-th.md` | modify | keep Thai installer documentation in parity |
| `tests/test_install_check.py` | new | stdlib black-box subprocess/filesystem suite |
| `workflow/evals/2026-08-03-wave5-install-check/run-legs.sh` | new | lean finale command runner and measured evidence |
| `workflow/evals/2026-08-03-wave5-install-check/README.md` | new | finale eval entry with measured numbers and deviations |

## Dependencies

Only the existing shell environment and Python standard library used by the black-box suite are
required. The check may use the repository's existing portable filesystem utilities; no network,
GitHub API, package install, or third-party dependency is part of the feature.

## Acceptance Criteria

- [ ] AC-1: Both global and project-scoped check commands return `0` only when all 16 active entries
      are current and all retired entries are absent.
- [ ] AC-2: The command reports all missing, modified, extra non-ignored, wrong-target, dangling,
      and retired findings and returns `1` without stopping after the first finding.
- [ ] AC-3: `__pycache__/`, `*.pyc`, and `.DS_Store` are ignored while unrelated sibling skills are
      ignored and left unchanged.
- [ ] AC-4: Incompatible flags return usage exit `2` before source or target paths are touched.
- [ ] AC-5: Source and target fingerprints prove the check does not create, pull, copy, delete,
      compile, or rewrite files.
- [ ] AC-6: Existing copy/link/update/uninstall/force behavior remains green in smoke tests.
- [ ] AC-7: English and Thai documentation describe identical command semantics.
- [ ] AC-8: The black-box suite drives the real CLI and covers current copy, drifted copy, correct,
      wrong, and dangling symlink, cache exclusion, retired skill, unrelated skill, missing target,
      invalid combinations, and no-mutation behavior.

## AC Coverage Map

| AC | Covered by (files/steps) | Source |
|---|---|---|
| AC-1 | CLI current copy/symlink cases; global/project legs | US-1 / US-2 |
| AC-2 | aggregate drift matrix and all-status assertions | US-4 / US-8 |
| AC-3 | cache and unrelated-sibling fixture legs | US-6 / US-7 |
| AC-4 | invalid-combination subprocess legs | US-9 |
| AC-5 | before/after source-target fingerprints | US-1 / US-8 |
| AC-6 | existing installer mode smoke legs | US-10 |
| AC-7 | bilingual documentation parity check | US-10 |
| AC-8 | real subprocess/filesystem black-box suite and exam | US-3 / US-4 / US-8 |

## Risks & Watch-outs

- A shell comparison that treats any non-zero result as success would create a false-green freshness
  gate; tests must include unreadable and missing paths.
- A basename-only symlink check would accept a link to another checkout; the exam must include that
  wrong-target case.
- A broad extra-file exclusion would hide real drift; keep the exclusion list exactly three patterns.
- A check path that resolves target paths after mutation flags would violate the no-side-effect gate;
  invalid combinations must be rejected first.

## Out of Scope

- JSON output, selective installation, a new installer backend, Codex-specific targets, inventory
  changes, retired-policy changes, or changes to existing mutating semantics.
- Re-running or editing historical evaluation entries.

## Flags

- `needs_ba: false` — no business ambiguity remains in the vetted ticket.
- `needs_ui: false` — no UI surface.
- `needs_sa: false` — no service architecture or external API.
- `needs_devops: false` — no deployment milestone; the CLI is exercised locally.

## Exit Criteria

**Stop condition:** every single-shot check passes and the final status is current — **or** two consecutive attempt rounds pass without the relevant progress number below moving, at which point stop and summon the human rather than attempt a third.

- Single-shot pass/fail, no progress number: all CLI, purity, documentation, and existing-mode checks listed in AC-1 through AC-8.

## Mode Prediction

- **kestra-build mode:** `full` — source and installed trees are a paired external reality constraint, and a false-green freshness result silently preserves stale skill behavior.

## Open Items

- None. The user selected the single CLI seam, cache exclusions, one vertical ticket, and full-mode dogfood.
