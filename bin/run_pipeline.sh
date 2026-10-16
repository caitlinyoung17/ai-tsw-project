#!/usr/bin/env bash
# Run the TSW pipeline on a PDF/.txt file or a folder of them.
# Usage: bin/run_pipeline.sh <file-or-folder> [pipeline flags...]
#        bin/run_pipeline.sh --folder <existing run folder> [pipeline flags...]   (resume)
# Defaults to --steps 1,1.5,2,3,4 for new runs unless --steps is given.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/bin/setup_env.sh"

ARGS=()
INPUT=""
if [ $# -gt 0 ] && [[ "$1" != -* ]]; then INPUT="$1"; shift; fi
ARGS=("$@")

HAS_STEPS=0
for a in "${ARGS[@]+"${ARGS[@]}"}"; do [ "$a" = "--steps" ] && HAS_STEPS=1; done
# When resuming (--folder), let the CLI pick its own default (skips step 1).
[ $HAS_STEPS -eq 0 ] && [ -n "$INPUT" ] && ARGS+=(--steps 1,1.5,2,3,4)

if [ -n "$INPUT" ]; then
  [ -e "$INPUT" ] || { echo "Path not found: $INPUT" >&2; exit 1; }
  # We cd into src/ below, so make the path absolute first.
  if [ -d "$INPUT" ]; then INPUT="$(cd "$INPUT" && pwd)"; else INPUT="$(cd "$(dirname "$INPUT")" && pwd)/$(basename "$INPUT")"; fi
  # The pipeline takes a folder, so stage a lone file in one.
  if [ -f "$INPUT" ]; then
    STAGE="$(mktemp -d)"
    trap 'rm -rf "$STAGE"' EXIT
    cp "$INPUT" "$STAGE/"
    INPUT="$STAGE"
  fi
  # Native Windows Python needs a Windows-style path, not Git Bash's /tmp/...
  if command -v cygpath >/dev/null 2>&1; then INPUT="$(cygpath -w "$INPUT")"; fi
  ARGS+=(--input "$INPUT")
fi

cd "$ROOT/src"
python -m pipeline "${ARGS[@]}"
