#!/usr/bin/env bash
# Ensure a working virtualenv exists with dependencies installed.
# Safe to run repeatedly; only reinstalls when requirements.txt changes.
# Usage: bin/setup_env.sh        (run directly)
#        source bin/setup_env.sh  (also activates .venv in the caller's shell)
_setup_env() {
  local root venv stamp py cand
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  venv="$root/.venv"
  stamp="$venv/.requirements.sha"

  # Windows venvs (Git Bash / VS Code terminal) use Scripts/ instead of bin/.
  local vbin="bin"
  case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) vbin="Scripts" ;; esac
  [ -d "$venv/Scripts" ] && vbin="Scripts"

  # An interrupted or moved venv leaves a broken python; rebuild it.
  if [ -d "$venv" ] && ! "$venv/$vbin/python" -c "import sys" >/dev/null 2>&1; then
    echo "[setup] Existing .venv is broken; recreating it."
    rm -rf "$venv"
  fi

  if [ ! -d "$venv" ]; then
    py=""
    # On Windows, `python3` is often a Microsoft Store stub; the version check
    # below rejects it, and `py -3` (the Python launcher) is tried as a fallback.
    for cand in python3.12 python3.11 python3.13 python3.10 python3.9 python3 python; do
      if command -v "$cand" >/dev/null 2>&1 &&
         "$cand" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
        py="$cand"; break
      fi
    done
    if [ -z "$py" ] && command -v py >/dev/null 2>&1 &&
       py -3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
      py="py -3"
    fi
    if [ -z "$py" ]; then
      echo "[setup] Python 3.9+ is required but was not found." >&2
      echo "        Install it from https://www.python.org/downloads/ and retry." >&2
      return 1
    fi
    echo "[setup] Creating virtual environment with $($py --version)..."
    $py -m venv "$venv" || { echo "[setup] Failed to create .venv" >&2; return 1; }
  fi

  # shellcheck disable=SC1091
  source "$venv/$vbin/activate"

  local want have
  if command -v shasum >/dev/null 2>&1; then
    want="$(shasum "$root/requirements.txt" | cut -d' ' -f1)"
  elif command -v sha256sum >/dev/null 2>&1; then
    want="$(sha256sum "$root/requirements.txt" | cut -d' ' -f1)"
  else
    want="$(python -c "import hashlib,sys; print(hashlib.sha1(open(sys.argv[1],'rb').read()).hexdigest())" "$root/requirements.txt")"
  fi
  have="$(cat "$stamp" 2>/dev/null || true)"
  if [ "$want" != "$have" ] || ! python -c "import portkey_ai, pdfminer, openpyxl, rapidfuzz" >/dev/null 2>&1; then
    echo "[setup] Installing dependencies (first run may take a minute)..."
    python -m pip install --quiet --upgrade pip &&
    python -m pip install --quiet -r "$root/requirements.txt" || {
      echo "[setup] Dependency install failed. Check your network and retry." >&2
      return 1
    }
    echo "$want" > "$stamp"
  fi
}
_setup_env
_rc=$?
unset -f _setup_env
# `return` only works when sourced; fall back to exit when executed.
return $_rc 2>/dev/null || exit $_rc
