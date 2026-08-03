## Parent

https://github.com/arkaphat/arkaphat-builder/issues/39

## Problem Statement

Copy installs of the skill set can become stale after the source repository changes. The only
current way to refresh a copy is the mutating `--update` operation, so a user or CI job cannot
answer the simpler question "is the installed set current?" without copying, pulling, deleting,
or compiling files. A stale install silently runs old skill behavior.

## Solution

Add a read-only `--check` mode to the installer. It inspects the active skill set in the selected
global or project scope, reports every missing or drifted skill, validates that symlink installs
still point at this repository, and confirms retired skills are absent. The command never changes
the source tree or target tree. It returns a stable success code only when the declared install is
current, a drift code when any declared condition is false, and a usage code for incompatible
arguments.

## User Stories

1. As a skill maintainer, I want to check a global copy install without changing it, so that I can
   know whether a refresh is needed before starting work.
2. As a project owner, I want to check a project-scoped install, so that the project uses the same
   skills I reviewed in the repository.
3. As a symlink user, I want the check to validate the link target, so that a moved or dangling
   link cannot look current merely because a directory with the same name exists.
4. As a copy-install user, I want modified, missing, and unexpected declared files reported, so
   that stale behavior is visible instead of silently accepted.
5. As an installer maintainer, I want the check to cover every active skill and no retired skill,
   so that the declared install contract stays aligned with the installer inventory.
6. As a user with unrelated skills in the same directory, I want those skills ignored, so that a
   check of this repository does not claim ownership of another installation.
7. As a Python-skill user, I want ordinary interpreter caches and Finder metadata ignored, so that
   harmless runtime artifacts do not create false drift.
8. As a CI author, I want a non-zero drift result and a concise per-skill report, so that freshness
   can be gated without parsing prose or mutating the workspace.
9. As a maintainer, I want invalid combinations rejected before any filesystem operation, so that
   `--check` cannot accidentally turn into update, uninstall, copy, or link behavior.
10. As a maintainer, I want existing install, update, uninstall, force, and link behavior to stay
    unchanged, so that the new observation mode does not alter established workflows.

## Acceptance Criteria

- [ ] `install.sh --check` and `install.sh --check --project <path>` inspect the declared active
      skills and return 0 only when every copy or symlink is current and no retired skill exists.
- [ ] The check reports all missing, modified, extra non-ignored, wrong-target, dangling, and
      retired-skill findings and returns 1; it does not stop after the first finding.
- [ ] `__pycache__/`, `*.pyc`, and `.DS_Store` do not count as copy drift; unrelated skill folders
      are ignored.
- [ ] `--check` rejects `--link`, `--force`, `--update`, and `--uninstall` with usage exit 2 before
      touching source or target paths.
- [ ] The command is observationally pure: it does not create directories, pull, copy, delete,
      compile, or rewrite any source/target file.
- [ ] Existing installer modes retain their current behavior, including global/project scope and
      copy/link/update/uninstall paths.
- [ ] English and Thai installer documentation describe the new mode, scope, findings, exclusions,
      and exit codes consistently.
- [ ] A black-box test suite exercises the CLI through real subprocess and temporary filesystem
      seams, including current copy, drifted copy, correct/wrong/dangling symlink, cache exclusion,
      retired skill, unrelated skill, missing target, invalid combinations, and no-mutation proof.

## Implementation Decisions

- The only public seam is the existing installer CLI; no new library API or daemon is introduced.
- The declared active inventory is the installer’s existing 16-skill list. Retired entries are
  checked as negative obligations, while unknown sibling skills are outside this feature’s ownership.
- Copy freshness is a recursive comparison with only the three named ephemeral exclusions. A
  symlink is current only when its resolved target is the canonical source directory for that skill.
- The check reports every skill before returning its aggregate result. Exit 0 means no findings, exit
  1 means at least one environmental drift/error, and exit 2 means invalid command usage.
- `--project` remains the only scope selector accepted with `--check`; the check discovers the
  installed transport instead of accepting a requested transport mode.
- The feature is predicted `kestra-build: full` because source and installed trees are a paired
  external reality constraint and a false-green freshness result silently preserves stale behavior.

## Testing Decisions

- Tests observe the CLI and filesystem effects, not shell helper implementation details.
- The suite uses temporary HOME/project roots and the real installer subprocess. It fingerprints
  source and target trees before and after every check to prove observational purity.
- Red proof must fail because `--check` is absent before implementation. Green proof must cover all
  acceptance criteria and preserve existing installer mode smoke tests.
- The exam uses the same single CLI seam, derives one check per requirement, and remains a local,
  throwaway artifact outside the worktree.

## Out of Scope

- A machine-readable JSON output format.
- Selective installation, a new installer backend, or Codex-specific installation targets.
- Changing the skill inventory, retired-skill policy, or existing mutating installer semantics.
- Re-running or editing historical evaluation entries.

## Further Notes

This is the real feature used for Wave 5 dogfood in #39. The chain must use the shipped
to-spec, kestra-spec, to-tickets, kestra-build, kestra-run, and kestra-exam forms with no hand patch.
The exam gate is manual and explicitly throwaway/non-deliverable; its measured result is recorded
only in the new Wave 5 finale evaluation entry and run artifacts.

