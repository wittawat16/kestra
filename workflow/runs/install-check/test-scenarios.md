# Install-check red scenarios

| AC | Scenario | Given | When | Then |
|---|---|---|---|---|
| AC-1 | current copy and canonical link | fresh global and project installs | run `./install.sh --check` with matching scope | exit 0 and every declared active entry is current |
| AC-2 | aggregate drift | missing, modified, extra, unreadable, wrong/dangling, and retired entries | run one check | all findings are printed before exit 1 |
| AC-3 | exclusions | cache files and an unrelated sibling are present | run check | cache artifacts and unrelated skill do not cause drift |
| AC-4 | incompatible flags | a valid target exists | combine `--check` with each mutating flag | exit 2 before any path is touched |
| AC-5 | observational purity | source and target fingerprints are captured | run check, including invalid usage | fingerprints and directory existence are unchanged |
| AC-6 | existing modes | copy/link installs and existing force/update/uninstall paths | run smoke commands | pre-existing installer behavior remains green |
| AC-7 | bilingual contract | English and Thai usage pages are loaded | compare check semantics | command, scopes, exclusions, and exits agree |
| AC-8 | real seam coverage | temp HOME/project and real subprocesses | run the suite | all scenarios drive only `./install.sh` and record counts |

Runtime invariants exercised: missing target is an error without creation; invalid flags are parsed
before target resolution; symlinks compare canonical identity; findings aggregate; ignored files are
limited to `__pycache__/`, `*.pyc`, and `.DS_Store`; unrelated siblings are out of scope.
