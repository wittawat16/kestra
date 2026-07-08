# Claude Code skills

*[อ่านเป็นภาษาไทย](README-th.md)*

A small collection of Claude Code skills, organized into groups by folder. This repo *is* the
skills — clone it and run `install.sh` once to install every skill in it (no per-skill install; it
installs the whole set in one go).

## Groups

| Group | Skills | What it's for |
|---|---|---|
| [`workflow/`](workflow/README.md) | `kestra-build`, `kestra-run` | Generator + orchestrator for a TDD-locked "stage machine" — turns a feature spec into `workflow.yaml`/`state.json`, then runs it with mechanical (not AI-judgment) checks at every step. |
| [`productivity/`](productivity/README.md) | `givename` | Suggests names (variables, files, branches, commits, new projects/skills) by reading the actual naming convention nearby first. |

Each group's own README has the full detail — what each skill does, how to use it, and its
reference docs. New groups get their own top-level folder the same way (see "Adding a new skill"
below).

## Installation

Clone the repo and run `install.sh` to copy (or symlink) every skill folder into wherever Claude
Code auto-discovers skills — either globally (`~/.claude/skills/`, available in every project) or
scoped to one project (`<project>/.claude/skills/`).

```bash
git clone <this-repo-url> claude-skills
cd claude-skills

./install.sh                        # install globally — available in every project (~/.claude/skills/)
./install.sh --project ~/code/app   # install for one project only (<path>/.claude/skills/)
./install.sh --link                 # symlink instead of copy — `git pull` here updates it in place
./install.sh --force                # overwrite an existing install
./install.sh --update               # pull the latest code (git pull here), then refresh the install
./install.sh --uninstall            # remove it (pass the same --project flag used at install time)
```

Each skill installs **flat** by its own folder name under the target skills dir, regardless of
which group folder it lives in here — that's the layout Claude Code actually discovers. So
`workflow/kestra-build/` becomes `~/.claude/skills/kestra-build/`, `productivity/givename/`
becomes `~/.claude/skills/givename/`, and so on.

### Updating to the latest version

If you installed with **`--link`** — nothing extra to do, just `git pull` in this repo; the
symlink already points here.

If you installed with **copy** (the default) — run `./install.sh --update` (add `--project <path>`
too if you did a project-scoped install): it `git pull`s the latest code in this repo first
(skipped if the repo has uncommitted local changes, so it never clobbers work in progress), then
copies the update over the existing install — no need for `--force` or to uninstall first.

Restart Claude Code (or start a new session) afterward so the updated skills get picked up. No
external dependencies to install — `kestra-build`'s dry-run script (`validate_workflow.py`) only
needs a plain `python3`, no PyYAML or any third-party package; the other skills need nothing at all.

## Adding a new skill

Each group is just a top-level folder containing one or more skill directories (`<group>/<skill-name>/SKILL.md`).
To add a skill to an existing group, drop it in that folder and add its path
(e.g. `productivity/new-skill-name`) to the `SKILLS` array in `install.sh` — the script installs
each entry flat by its basename, so the group folder is purely for organizing this repo, not part
of the installed layout. To start a new group, create a new top-level folder and follow the same
pattern.

## License

See [LICENSE](LICENSE)
