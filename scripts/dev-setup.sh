#!/bin/sh
# Developer setup for Vesper Relay: a project .venv on Python 3.11+.
# Safe to run repeatedly. POSIX sh; macOS and Linux. Never uses sudo.
#
#   sh scripts/dev-setup.sh          set up .venv, then run the tests and plan facts
#   sh scripts/dev-setup.sh --check  only report whether .venv is ready; change nothing
#
# No activation needed: call .venv/bin/python3 directly.

set -u

MIN_LABEL="3.11"
VENV_PY=".venv/bin/python3"

ROOT=$(cd "$(dirname "$0")/.." && pwd) || exit 1
cd "$ROOT" || exit 1

supported() {  # supported <python>: true if it runs and is 3.11+
    "$1" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1
}

version_of() {
    "$1" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo "unusable"
}

check_venv() {
    if [ ! -e "$VENV_PY" ]; then
        echo "dev-setup: NOT READY: $VENV_PY is missing. Run: sh scripts/dev-setup.sh"
        return 1
    fi
    if ! supported "$VENV_PY"; then
        echo "dev-setup: NOT READY: $VENV_PY is $(version_of "$VENV_PY"), need $MIN_LABEL+. Run: sh scripts/dev-setup.sh"
        return 1
    fi
    echo "dev-setup: ready: $VENV_PY is Python $(version_of "$VENV_PY")"
    return 0
}

if [ "${1:-}" = "--check" ]; then
    check_venv
    exit $?
elif [ $# -gt 0 ]; then
    echo "usage: sh scripts/dev-setup.sh [--check]" >&2
    exit 2
fi

changes=""
note_change() { changes="${changes}  - $1
"; }

find_python() {
    for name in python3.13 python3.12 python3.11 python3; do
        path=$(command -v "$name" 2>/dev/null) || continue
        if supported "$path"; then
            echo "$path"
            return 0
        fi
    done
    return 1
}

install_instructions() {
    cat >&2 <<'EOF'
dev-setup: no Python 3.11+ found (tried python3.13, python3.12, python3.11, python3).
Install one, then run this script again:
  macOS:          install Homebrew (https://brew.sh), then: brew install python@3.12
                  or use the installer from https://www.python.org/downloads/
  Debian/Ubuntu:  apt install python3.12 python3.12-venv
  Fedora:         dnf install python3.12
  Any OS:         uv python install 3.12   (https://docs.astral.sh/uv/)
This script does not use sudo or change the system Python.
EOF
}

# 1. A Python 3.11+ to build the venv from (only needed if the venv is missing or too old).
need_venv=0
if [ ! -e "$VENV_PY" ] || ! supported "$VENV_PY"; then
    need_venv=1
fi

if [ "$need_venv" -eq 1 ]; then
    if ! BASE_PY=$(find_python); then
        if [ "$(uname -s)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
            echo "dev-setup: no Python 3.11+ found; running: brew install python@3.12"
            brew install python@3.12 || { install_instructions; exit 1; }
            BASE_PY="$(brew --prefix python@3.12)/bin/python3.12"
            if ! supported "$BASE_PY"; then
                echo "dev-setup: $BASE_PY is not usable after brew install." >&2
                install_instructions
                exit 1
            fi
            note_change "installed python@3.12 with Homebrew"
        else
            install_instructions
            exit 1
        fi
    fi
    echo "dev-setup: using $BASE_PY (Python $(version_of "$BASE_PY"))"

    # 2. Create .venv, or recreate it in place if its Python is too old or broken.
    if [ -d .venv ]; then
        echo "dev-setup: recreating .venv ($VENV_PY is $(version_of "$VENV_PY"), need $MIN_LABEL+)"
        action="recreated"
        clear_flag="--clear"
    else
        echo "dev-setup: creating .venv"
        action="created"
        clear_flag=""
    fi
    # $clear_flag is unquoted on purpose: it expands to nothing when empty.
    if ! "$BASE_PY" -m venv $clear_flag .venv; then
        echo "dev-setup: '$BASE_PY -m venv .venv' failed." >&2
        echo "  On Debian/Ubuntu, install the matching venv package, e.g.: apt install python3.12-venv" >&2
        exit 1
    fi
    if ! supported "$VENV_PY"; then
        echo "dev-setup: $VENV_PY is still not Python $MIN_LABEL+ after setup." >&2
        exit 1
    fi
    note_change "$action .venv with Python $(version_of "$VENV_PY")"
else
    echo "dev-setup: .venv already uses Python $(version_of "$VENV_PY")"
fi

# 3. Keep .venv out of Git.
if ! grep -qxE '/?\.venv/?' .gitignore 2>/dev/null; then
    if [ -s .gitignore ] && [ -n "$(tail -c 1 .gitignore)" ]; then
        echo >> .gitignore
    fi
    echo ".venv/" >> .gitignore
    note_change "added .venv/ to .gitignore"
fi

# 4. Optional tools needed by later plan tasks: report only, never install.
tool_line() {  # tool_line <command> <brew install command> <first task>
    if command -v "$1" >/dev/null 2>&1; then
        printf '  %-14s found      (needed from %s)\n' "$1" "$3"
    else
        printf '  %-14s missing    (needed from %s)  install: %s\n' "$1" "$3" "$2"
    fi
}
echo
echo "Optional tools (not installed by this script):"
tool_line go     "brew install go"            "P1-T5"
tool_line node   "brew install node"          "P1-T6"
tool_line pnpm   "brew install pnpm"          "P1-T6"
if command -v docker >/dev/null 2>&1 || command -v colima >/dev/null 2>&1; then
    found=""
    command -v docker >/dev/null 2>&1 && found="docker"
    command -v colima >/dev/null 2>&1 && found="${found:+$found + }colima"
    printf '  %-14s found      (needed from %s)  %s\n' "docker/colima" "P1-T9" "$found"
else
    printf '  %-14s missing    (needed from %s)  install: %s\n' "docker/colima" "P1-T9" "brew install colima docker"
fi

# 5. Prove the environment works.
echo
echo "dev-setup: running $VENV_PY -B -m unittest discover -s tests"
if "$VENV_PY" -B -m unittest discover -s tests; then tests="passed"; else tests="FAILED"; fi

if [ -f docs/plan/verify-facts.sh ]; then
    echo
    echo "dev-setup: running sh docs/plan/verify-facts.sh"
    if PYTHON="$VENV_PY" sh docs/plan/verify-facts.sh; then facts="all hold"; else facts="DRIFT (see above)"; fi
else
    facts="skipped (docs/plan/verify-facts.sh not present)"
fi

echo
echo "Summary"
echo "  Python:      $VENV_PY $(version_of "$VENV_PY")"
if [ -n "$changes" ]; then
    echo "  Changes:"
    printf '%s' "$changes" | sed 's/^/  /'
else
    echo "  Changes:     none (already set up)"
fi
echo "  Unit tests:  $tests"
echo "  Plan facts:  $facts"

[ "$tests" = "passed" ] || exit 1
case "$facts" in DRIFT*) exit 1 ;; esac
exit 0
