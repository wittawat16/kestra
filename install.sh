#!/usr/bin/env bash
# Installer for the kestra-build / kestra-run Claude Code skills.
#
# Copies (or symlinks) kestra-build/ and kestra-run/ into a Claude Code
# skills directory so they're auto-discovered — either globally
# (~/.claude/skills/, available in every project) or scoped to one
# project (<project>/.claude/skills/).
#
# Usage:
#   ./install.sh                    # install globally, copy (default)
#   ./install.sh --project <path>   # install into <path>/.claude/skills
#   ./install.sh --link             # symlink instead of copy (tracks repo updates)
#   ./install.sh --force            # overwrite an existing install
#   ./install.sh --uninstall        # remove a previous install (global by default)
#   ./install.sh -h | --help
#
# Examples:
#   ./install.sh                                # ~/.claude/skills/kestra-build, kestra-run
#   ./install.sh --project ~/code/my-app         # ~/code/my-app/.claude/skills/...
#   ./install.sh --link                          # symlink so `git pull` here updates the skill everywhere
#   ./install.sh --uninstall --project ~/code/my-app

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS=(kestra-build kestra-run)

MODE="copy"          # copy | link
SCOPE="global"        # global | project
PROJECT_DIR=""
FORCE=0
UNINSTALL=0

usage() {
  sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
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
    dest="$TARGET_DIR/$skill"
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

mkdir -p "$TARGET_DIR"

for skill in "${SKILLS[@]}"; do
  src="$SCRIPT_DIR/$skill"
  dest="$TARGET_DIR/$skill"

  if [ ! -d "$src" ]; then
    echo "error: expected $src to exist — run this script from the repo root" >&2
    exit 1
  fi

  if [ -e "$dest" ] || [ -L "$dest" ]; then
    if [ "$FORCE" = "1" ]; then
      rm -rf "$dest"
    else
      echo "error: $dest already exists — pass --force to overwrite, or --uninstall first" >&2
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

if command -v python3 >/dev/null 2>&1; then
  python3 -m py_compile "$TARGET_DIR/kestra-build/scripts/validate_workflow.py" \
                        "$TARGET_DIR/kestra-run/scripts/stage_transition.py"
  find "$TARGET_DIR" -name '__pycache__' -maxdepth 4 -exec rm -rf {} + 2>/dev/null || true
  echo "sanity check: scripts compile OK"
else
  echo "note: python3 not found on PATH — skipped compiling scripts/*.py (kestra-build still works; the dry-run validator needs python3 at use time)"
fi

echo
echo "Installed kestra-build and kestra-run under: $TARGET_DIR"
if [ "$SCOPE" = "global" ]; then
  echo "Available in every project. Restart Claude Code (or start a new session) to pick them up."
else
  echo "Available in project: $PROJECT_DIR"
fi
