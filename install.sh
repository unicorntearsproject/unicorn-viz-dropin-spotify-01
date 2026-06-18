#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DROPIN_NAME="spotify-01"
INSTALL_ROOT="${UV_DROPINS_ROOT:-${HOME}/.local/share/unicorn-viz}"
UNINSTALL=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Spotify drop-in bundle installer

Usage:
  bash install.sh [options]

Options:
  --root <dir>      Base installation root (default: ~/.local/share/unicorn-viz)
  --uninstall       Remove the installed drop-in bundle
  --dry-run         Print actions without executing them
  -h, --help        Show this help text
EOF
}

log() {
  echo "[spotify-01] $*"
}

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "dry-run: $*"
    return 0
  fi
  "$@"
}

copy_item() {
  local source_path="$1"
  local target_path="$2"

  if [[ ! -e "$source_path" ]]; then
    echo "[spotify-01] ERROR: missing source item: $source_path" >&2
    exit 1
  fi

  run mkdir -p "$(dirname "$target_path")"

  if [[ -d "$source_path" ]]; then
    run mkdir -p "$target_path"
    run cp -a "$source_path/." "$target_path/"
  else
    run cp -a "$source_path" "$target_path"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      INSTALL_ROOT="$2"
      shift 2
      ;;
    --uninstall)
      UNINSTALL=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[spotify-01] ERROR: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if ! command -v playerctl >/dev/null 2>&1; then
  echo "[spotify-01] ERROR: playerctl must be installed and on PATH" >&2
  exit 1
fi

TARGET_DIR="${INSTALL_ROOT%/}/drop-ins/${DROPIN_NAME}"

if [[ "$UNINSTALL" -eq 1 ]]; then
  log "Removing ${TARGET_DIR}"
  run rm -rf "$TARGET_DIR"
  log "Uninstall complete"
  exit 0
fi

log "Installing into ${TARGET_DIR}"
run rm -rf "$TARGET_DIR"
run mkdir -p "$TARGET_DIR"

copy_item "${SCRIPT_DIR}/README.md" "${TARGET_DIR}/README.md"
copy_item "${SCRIPT_DIR}/__init__.py" "${TARGET_DIR}/__init__.py"
copy_item "${SCRIPT_DIR}/spotify_controller.py" "${TARGET_DIR}/spotify_controller.py"
copy_item "${SCRIPT_DIR}/docs" "${TARGET_DIR}/docs"

log "Install complete"