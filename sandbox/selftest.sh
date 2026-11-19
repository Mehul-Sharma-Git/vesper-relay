#!/bin/sh
# Sandbox selftest: from inside every operation, try to write outside /work, read the host
# home, reach the internet from a gate, and write to a read-only mount. Every attempt must
# fail. Usage, from the repository root:  sh sandbox/selftest.sh [docker|podman]
set -eu
cd "$(dirname "$0")/.."
PYTHON=${PYTHON:-.venv/bin/python3}
[ -x "$PYTHON" ] || PYTHON=python3
exec "$PYTHON" -B vesper.py sandbox selftest --backend "${1:-docker}"
