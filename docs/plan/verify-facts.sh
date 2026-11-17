#!/bin/sh
# Checks that the code facts this plan relies on are still true.
# Run from the repository root:  sh docs/plan/verify-facts.sh
# Each line prints OK or DRIFT. A DRIFT line means the code changed since the plan was
# written (baseline commit b7da4d1, 2026-11-17): re-read the affected task and adapt it.

PLAN_DIR=$(dirname "$0")
# Use the project venv (Python 3.11+, see scripts/dev-setup.sh); set PYTHON to override.
# Falls back to python3 only when the venv doesn't exist.
if [ -z "${PYTHON:-}" ] && [ ! -e .venv/bin/python3 ]; then
    PYTHON=python3
fi
PYTHON=${PYTHON:-.venv/bin/python3}
fail=0

check() {  # check "<label>" "<task ids>" <command...>
    label=$1; tasks=$2; shift 2
    if "$@" >/dev/null 2>&1; then
        echo "OK     $label"
    else
        echo "DRIFT  $label  (affects $tasks)"
        fail=1
    fi
}

check "decode_provider_report lives in builder/review_gate.py" "P1-T1" \
    grep -q "def decode_provider_report" builder/review_gate.py
check "fixture reviewer replies decode (prose + fence, fixed in P1-T1)" "P1-T1, P1-T2" \
    "$PYTHON" -B -c "
import sys; sys.path.insert(0, '.')
from builder.review_gate import decode_provider_report
for name in ('preamble-fence.json', 'preamble-fence-2.json'):
    report = decode_provider_report(open('$PLAN_DIR/fixtures/pocket-todo/reviewer-replies/' + name).read())
    assert report['verdict'] == 'approve', name"
check "provider_command builds reviewer commands in builder/providers.py" "P1-T2, P1-T8" \
    grep -q "def provider_command" builder/providers.py
check "reviewers get a JSON Schema (review.schema.json, Claude --json-schema; P1-T2)" "P1-T8" \
    sh -c 'grep -q "json-schema" builder/providers.py && grep -q "review.schema.json" builder/runner.py && grep -q "review.schema.json" builder/planning.py && grep -q "structured_output" builder/review_gate.py'
check "checks may set a timeout (1-1800 s; default 45, 300 for VESPER_REGRESSION; P1-T3)" "P1-T5" \
    sh -c 'grep -q "Invalid timeout for check" builder/contracts.py && grep -q "timeout=check.get(\"timeout\"" builder/runner.py'
check "reviewer timeout and max turns are flags (--review-timeout/--review-max-turns; P1-T3)" "P1-T7, P1-T8" \
    sh -c 'grep -q "def review_limits" builder/providers.py && grep -q "\"--max-turns\", str(max_turns)" builder/providers.py && grep -q "timeout=review_timeout" builder/runner.py && grep -q -- "--review-max-turns" build_local.py && grep -q "review_limit_options(plan_review)" vesper.py'
check "gate env is a fixed allow-list" "P1-T4" \
    grep -q '"PYTHONDONTWRITEBYTECODE": "1"' builder/runner.py
check "gates are Python scripts only" "P1-T5" \
    grep -q 'script.endswith(".py")' builder/contracts.py
check "safe_path rejects node_modules" "P1-T6" \
    grep -q '"node_modules"' builder/contracts.py
check "inventory rejects linked or special paths" "P1-T6" \
    grep -q "Linked or special path is unsupported" builder/contracts.py
check "workers get Read/Edit/Write/Glob/Grep only" "P1-T10" \
    grep -q '"Read,Edit,Write,Glob,Grep"' builder/providers.py
check "--provider choices are claude/codex" "P1-T8" \
    grep -q 'choices=("codex", "claude")' build_local.py
check "review_bundle requires the four plan files" "P2-T5" \
    grep -q '"product.md", "design.md", "architecture.md", "decisions.md"' builder/contracts.py
check "validate_design lives in builder/team.py" "P4-T2" \
    grep -q "def validate_design" builder/team.py
check "role catalogue PROFILES in builder/team.py" "P1-T10, P3-T1" \
    grep -q "^PROFILES = {" builder/team.py
check "frontend role forbids new dependencies" "P4-T4" \
    grep -q "Do not add a new dependency" team/roles/frontend.md
check "repair commands exist" "P5-T3" \
    grep -q 'add_parser("repair-run")' vesper.py
check "repair uses typed VESPER_REPRO evidence with a failure id" "P5-T3" \
    grep -q 'RESULT_PREFIX = "VESPER_REPRO "' builder/repair.py
check "plan routing and critique live in builder/planning.py" "P2-T5, P4-T6, P4-T7" \
    grep -q "^IMPACTS = " builder/planning.py
check "approve requires an approving plan critique at full/focused depth" "P2-T2, P2-T5" \
    grep -q "Independent plan critique must approve" builder/runner.py
check "review_plan uses the same report decoder (parse bug applies)" "P1-T1, P1-T2" \
    grep -q "decode_provider_report(output.read_text" builder/planning.py
check "plan critique uses the review limits (P1-T3)" "P1-T7, P1-T8" \
    grep -q "log=log, timeout=review_timeout" builder/planning.py
check "review-plan --provider choices are claude/codex" "P1-T8" \
    grep -q 'choice.add_argument("--provider", choices=("codex", "claude"))' vesper.py
check "specialist evals call Codex CLI directly" "P1-T8, P5-T4" \
    grep -q "\['codex', 'exec'" examples/specialist_evals/run_evals.py
check "fixture architecture revision matches the technical-lead role" "P1-G, P4-T7" \
    "$PYTHON" -B -c "
import json, sys; sys.path.insert(0, '.')
from builder.team import profile
plan = json.load(open('$PLAN_DIR/fixtures/pocket-todo/plan/planning.json'))
sys.exit(0 if plan['architecture']['revision'] == profile('technical-lead')['revision'] else 1)"

echo
if [ "$fail" -eq 0 ]; then
    echo "All plan facts hold."
else
    echo "Some facts drifted. DRIFT on a task already marked done is expected (that task"
    echo "changed the code). DRIFT on a task still todo: see README.md, 'When the code has changed'."
fi
exit $fail
