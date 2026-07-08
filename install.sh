#!/usr/bin/env bash
# Installer for this repo's Claude Code skills (grouped by folder — workflow/,
# productivity/, etc. — see the SKILLS array below for the current list).
#
# Copies (or symlinks) each skill folder into a Claude Code skills directory so
# they're auto-discovered — either globally (~/.claude/skills/, available in
# every project) or scoped to one project (<project>/.claude/skills/). Each
# skill installs flat by its own folder name regardless of which group folder
# it lives in here, since that's the layout Claude Code actually discovers.
#
# Usage:
#   ./install.sh                    # install globally, copy (default)
#   ./install.sh --project <path>   # install into <path>/.claude/skills
#   ./install.sh --link             # symlink instead of copy (tracks repo updates)
#   ./install.sh --force            # overwrite an existing install
#   ./install.sh --update           # pull latest + refresh an existing install in place
#   ./install.sh --uninstall        # remove a previous install (global by default)
#   ./install.sh -h | --help
#
# Examples:
#   ./install.sh                                # ~/.claude/skills/<skill-name>, one per skill below
#   ./install.sh --project ~/code/my-app         # ~/code/my-app/.claude/skills/...
#   ./install.sh --link                          # symlink so `git pull` here updates the skill everywhere
#   ./install.sh --update                        # git pull this repo, then refresh the global copy install
#   ./install.sh --update --project ~/code/my-app  # same, for a project-scoped install
#   ./install.sh --uninstall --project ~/code/my-app
#
# --update vs --link:
#   A --link install already stays current — `git pull` in this repo is enough,
#   nothing to re-copy. --update exists for a *copy* install: it pulls this repo
#   (if it's a clean git checkout) and then re-copies each skill folder over
#   the existing install. Running --update against a --link install just verifies
#   the symlink still points here (or fixes it if the repo moved) — it will not
#   silently turn your symlink into a copy.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Source paths, grouped by folder (e.g. workflow/). Installed flat by basename
# under the target skills dir — Claude Code discovers skills one level deep,
# so the group folder is repo-organization only, not part of the install layout.
SKILLS=(
  workflow/kestra-build workflow/kestra-run
  productivity/givename
  meta/meta-pm meta/meta-ba meta/meta-designer meta/meta-sa meta/meta-architect
  meta/meta-dev meta/meta-qa meta/meta-review meta/meta-security meta/meta-devops
  meta/meta-debug
)

MODE="copy"          # copy | link
SCOPE="global"        # global | project
PROJECT_DIR=""
FORCE=0
UNINSTALL=0
UPDATE=0

usage() {
  sed -n '2,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --project)
      SCOPE="project"
      PROJECT_DIR="${2:-}"
      if [ -z "$PROJECT_DIR" ]; then
        echo "error: --project requires a path" >&2
        exit 2
      fi
      shift 2
      ;;
    --link)
      MODE="link"
      shift
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --uninstall)
      UNINSTALL=1
      shift
      ;;
    --update)
      UPDATE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument '$1'" >&2
      usage
      exit 2
      ;;
  esac
done

if [ "$SCOPE" = "global" ]; then
  TARGET_DIR="$HOME/.claude/skills"
else
  # Normalize to an absolute path so messages/symlinks are unambiguous.
  PROJECT_DIR="$(cd "$PROJECT_DIR" 2>/dev/null && pwd || true)"
  if [ -z "$PROJECT_DIR" ]; then
    echo "error: --project path does not exist" >&2
    exit 1
  fi
  TARGET_DIR="$PROJECT_DIR/.claude/skills"
fi

if [ "$UNINSTALL" = "1" ]; then
  removed=0
  for skill in "${SKILLS[@]}"; do
    dest="$TARGET_DIR/$(basename "$skill")"
    if [ -e "$dest" ] || [ -L "$dest" ]; then
      rm -rf "$dest"
      echo "removed: $dest"
      removed=1
    fi
  done
  if [ "$removed" = "0" ]; then
    echo "nothing to uninstall under $TARGET_DIR"
  fi
  exit 0
fi

if [ "$UPDATE" = "1" ] && [ -d "$SCRIPT_DIR/.git" ]; then
  if git -C "$SCRIPT_DIR" diff --quiet 2>/dev/null && git -C "$SCRIPT_DIR" diff --cached --quiet 2>/dev/null; then
    echo "pulling latest changes in $SCRIPT_DIR ..."
    if ! git -C "$SCRIPT_DIR" pull --ff-only; then
      echo "warn: git pull failed — continuing with the local working tree as-is" >&2
    fi
  else
    echo "note: $SCRIPT_DIR has local changes — skipping git pull, updating from the working tree as-is"
  fi
fi

mkdir -p "$TARGET_DIR"

for skill in "${SKILLS[@]}"; do
  src="$SCRIPT_DIR/$skill"
  dest="$TARGET_DIR/$(basename "$skill")"

  if [ ! -d "$src" ]; then
    echo "error: expected $src to exist — run this script from the repo root" >&2
    exit 1
  fi

  existing="none"
  if [ -L "$dest" ]; then
    existing="link"
  elif [ -e "$dest" ]; then
    existing="copy"
  fi

  if [ "$existing" != "none" ]; then
    if [ "$UPDATE" = "1" ]; then
      # A symlink install already tracks this repo live — nothing to re-copy,
      # unless the user explicitly asked to switch modes (--link on a copy
      # install, or the reverse) or the link is stale (repo moved).
      if [ "$existing" = "link" ] && [ "$MODE" = "copy" ] && [ "$(readlink "$dest")" = "$src" ]; then
        echo "up to date (symlink): $dest -> $src"
        continue
      fi
      rm -rf "$dest"
    elif [ "$FORCE" = "1" ]; then
      rm -rf "$dest"
    else
      echo "error: $dest already exists — pass --force or --update to refresh it, or --uninstall first" >&2
      exit 1
    fi
  fi

  if [ "$MODE" = "link" ]; then
    ln -s "$src" "$dest"
    echo "linked: $dest -> $src"
  else
    cp -R "$src" "$dest"
    echo "copied: $src -> $dest"
  fi
done

py_scripts=()
for skill in "${SKILLS[@]}"; do
  dest="$TARGET_DIR/$(basename "$skill")"
  while IFS= read -r -d '' f; do
    py_scripts+=("$f")
  done < <(find "$dest/scripts" -maxdepth 1 -name '*.py' -print0 2>/dev/null)
done

if [ "${#py_scripts[@]}" -gt 0 ]; then
  if command -v python3 >/dev/null 2>&1; then
    python3 -m py_compile "${py_scripts[@]}"
    find "$TARGET_DIR" -name '__pycache__' -maxdepth 4 -exec rm -rf {} + 2>/dev/null || true
    echo "sanity check: scripts compile OK"
  else
    echo "note: python3 not found on PATH — skipped compiling scripts/*.py (the skills still work; any dry-run validator scripts need python3 at use time)"
  fi
fi

echo
skill_names="$(for s in "${SKILLS[@]}"; do basename "$s"; done | paste -sd, - | sed 's/,/, /g')"
if [ "$UPDATE" = "1" ]; then
  echo "Updated $skill_names under: $TARGET_DIR"
else
  echo "Installed $skill_names under: $TARGET_DIR"
fi
if [ "$SCOPE" = "global" ]; then
  echo "Available in every project. Restart Claude Code (or start a new session) to pick them up."
else
  echo "Available in project: $PROJECT_DIR"
fi
