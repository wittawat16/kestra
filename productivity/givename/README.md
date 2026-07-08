# givename

Ask it to name something — a variable, a function, a file, a git branch, a commit, a new
project/feature/skill — and it reads the actual naming convention around it first (casing,
verb/noun shape, prefixes, sibling names) instead of reciting generic naming advice.

## What you get

Always the same shape: exactly **5 candidates, ordered shortest to longest**, as a numbered list,
each with a one-line reason tied to real evidence it looked at (a `grep`, a `git log`, an `ls`) —
never a name pulled from generic best-practice with no grounding in the actual repo/file/branch
history.

```
Convention found: kebab-case, noun-first, grouped by folder (see workflow/kestra-build, workflow/kestra-run)
Evidence: ls productivity/, workflow/

Suggestions (shortest → longest):
1. `changelog` — ...
2. `changelog-gen` — ...
3. `git-changelog` — ...
4. `changelog-writer` — ...
5. `git-changelog-writer` — ...
```

If the evidence is too thin to infer a convention (e.g. a fresh repo with no branch history yet),
it says so plainly and falls back to the relevant ecosystem-standard convention instead of
inventing a house style that isn't there. If the evidence is mixed (half the file is `camelCase`,
half is `snake_case`), it flags the conflict instead of silently picking a side.

## How to use

Just ask, with whatever context you have:

```
"what should I call this branch — fixing the login timeout bug"
"this variable holds the list of stages ready to run, what should I name it"
"naming a new skill under productivity/ that generates changelogs from git log, any ideas"
```

It'll look at what's actually nearby (sibling files, `git log`/`git branch`, existing identifiers
in the same file or folder) before answering — see [`SKILL.md`](SKILL.md) for exactly what it
checks per category.

## What it doesn't do

- Doesn't lecture on generic naming theory (avoid abbreviations, be descriptive, etc.) — the value
  here is matching the *local* convention, not a naming-101 refresher.
- Doesn't guess a convention out of thin air when there isn't enough evidence to find one — it says
  so and falls back to ecosystem defaults instead.

## Installation

This skill lives in the same repo as `kestra-build`/`kestra-run`, under `productivity/givename/`.
From the repo root:

```bash
./install.sh                        # install all skills in this repo globally (~/.claude/skills/)
./install.sh --project ~/code/app   # install for one project only (<path>/.claude/skills/)
./install.sh --link                 # symlink instead of copy — `git pull` here updates it in place
```

`install.sh` installs every skill in the repo (not just this one) flat by name under the target
skills dir — see the repo root [`README.md`](../../README.md#installation) for the full flag
reference (`--force`, `--update`, `--uninstall`) and how updates work.
