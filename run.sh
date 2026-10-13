#!/usr/bin/env bash
# Launch the interactive TSW pipeline prompt. Sets up the environment if needed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/bin/setup_env.sh"
exec python "$ROOT/bin/tui.py"
