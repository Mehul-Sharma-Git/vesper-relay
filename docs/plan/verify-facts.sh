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
check "brain adapters claude-code/codex/gemini-cli in builder/brains/ build worker/reviewer/consult commands (P1-T8)" "P1-T9, P1-T10, P1-T11" \
    "$PYTHON" -B -c "
import sys; sys.path.insert(0, '.')
from builder.brains import ADAPTERS
assert set(ADAPTERS) == {'claude-code', 'codex', 'gemini-cli'}
for adapter in ADAPTERS.values():
    assert set(adapter.capabilities._fields) == {'edit_files', 'run_shell', 'strict_output', 'model_select',
                                                 'effort_select', 'usage_report', 'sandbox_login'}
    assert all(callable(getattr(adapter, name)) for name in
               ('worker_command', 'reviewer_command', 'consult_command', 'parse_result', 'environment'))"
check "reviewers get a JSON Schema (review.schema.json; --json-schema for strict-output brains; P1-T2, P1-T8)" "P3-T4" \
    sh -c 'grep -q "json-schema" builder/brains/claude_code.py && grep -q "if adapter.capabilities.strict_output else None" builder/brains/__init__.py && grep -q "review.schema.json" builder/runner.py && grep -q "review.schema.json" builder/planning.py && grep -q "structured_output" builder/review_gate.py'
check "checks may set a timeout (1-1800 s; default 45, 900 for VESPER_REGRESSION; P1-T3, P1-G)" "P1-T7" \
    sh -c 'grep -q "Invalid timeout for check" builder/contracts.py && grep -q "limit = check.get(\"timeout\", REGRESSION_TIMEOUT if check\[\"id\"\] == \"VESPER_REGRESSION\" else 45)" builder/runner.py && grep -q "^REGRESSION_TIMEOUT = 900$" builder/runner.py'
check "reviewer timeout and max turns are flags (--review-timeout/--review-max-turns; P1-T3)" "P1-T7" \
    sh -c 'grep -q "def review_limits" builder/providers.py && grep -q "\"--max-turns\", str(max_turns)" builder/brains/claude_code.py && grep -q "timeout=review_timeout" builder/runner.py && grep -q -- "--review-max-turns" build_local.py && grep -q "review_limit_options(plan_review)" vesper.py'
check "gate env is a fixed base (home and tool caches in the gate temp dir) plus the contract's gate_env names (no secrets; P1-T4, P1-T5, P1-T6)" "P1-T9" \
    sh -c 'grep -q "\"PYTHONDONTWRITEBYTECODE\": \"1\"" builder/runner.py && grep -q "for name in gate_env if name in os.environ" builder/runner.py && grep -q "\"GOCACHE\": str(cache" builder/runner.py && grep -q "def validate_gate_env" builder/contracts.py && grep -q "^CREDENTIALS = frozenset" builder/brains/__init__.py'
check "gates are Python scripts or bare-program commands run in a throwaway copy with an overlay (P1-T5)" "P1-T9" \
    sh -c 'grep -q "script.endswith(\".py\")" builder/contracts.py && grep -q "PROGRAM_NAME.fullmatch(command\[0\])" builder/contracts.py && grep -q "def execute_command_check" builder/runner.py && grep -q "\"check-command\"" builder/runner.py'
check "config: personal config.toml + project vesper.toml, section levels in LEVELS, secret-like keys refused, vesper config show (P1-T7)" "P1-T8, P1-T9, P1-T11, P2-T3" \
    sh -c 'grep -q "^LEVELS = {" builder/config.py && grep -q "def secret_like" builder/config.py && grep -q "def load_config" builder/config.py && grep -q "add_parser(\"config\")" vesper.py'
check "safe_path rejects node_modules (build dirs pass only as ignored top-level entries; P1-T6)" "P4-T8" \
    grep -q '"node_modules"' builder/contracts.py
check "inventory rejects linked or special paths" "P1-T9" \
    grep -q "Linked or special path is unsupported" builder/contracts.py
check "contract build: ignored top-level dirs and a setup step before the first command gate (launcher op setup; P1-T6)" "P1-T9, P4-T8" \
    sh -c 'grep -q "def validate_build" builder/contracts.py && grep -q "def inventory(root, ignore=())" builder/contracts.py && grep -q "def run_setup" builder/runner.py && grep -q "launch_command(\"setup\"" builder/runner.py && grep -q "Build setup changed tracked files" builder/runner.py'
check "role tools in PROFILES; shell (Claude Code Bash, Codex danger-full-access, Gemini run_shell_command) only inside a real sandbox backend (P1-T10)" "P3-T5" \
    sh -c 'grep -q "^def tools(brain, operation, role=None, sandboxed=False):" builder/brains/__init__.py && grep -q "(\"shell\", (\"Bash\",))" builder/brains/claude_code.py && grep -q "^REVIEWER_TOOLS = (\"read\", \"search\", \"shell\")" builder/team.py'
check "--brain NAME (config brain or adapter) on run/review-candidate; --provider claude|codex a deprecated alias (P1-T8)" "P1-T11, P5-T1" \
    sh -c 'grep -q "def brain_options" build_local.py && grep -q "brain_options(run, reviewer=True)" build_local.py && grep -q "^LEGACY = {\"claude\": \"claude-code\", \"codex\": \"codex\"}" builder/brains/__init__.py'
check "sandbox backends docker (default)/podman/none in builder/sandbox/; runner hands jobs to the backend (P1-T9)" "P1-T10, P1-T11, P5-T2" \
    sh -c 'grep -q "^BACKENDS = (\"docker\", \"podman\", \"none\")" builder/sandbox/__init__.py && grep -q "isinstance(launcher, Sandbox)" builder/runner.py && grep -q "\"sandbox.backend\": \"docker\"" builder/config.py && test -f sandbox/Dockerfile && test -x sandbox/selftest.sh'
check "sandbox jobs: your uid, read-only root, cap-drop ALL, no-new-privileges; brains reach only sandbox_hosts via tinyproxy (P1-T9)" "P1-T10" \
    sh -c 'grep -q "\"--read-only\", \"--cap-drop\", \"ALL\"" builder/sandbox/__init__.py && grep -q "FilterDefaultDeny Yes" builder/sandbox/__init__.py && grep -q "sandbox_hosts = " builder/brains/base.py'
check "vesper setup (builder/wizard.py) and vesper doctor (builder/doctor.py: each adapter's flags against its --help); bin/vesper finds Python 3.11+ (P1-T11)" "P1-G, P5-T2, P5-T3" \
    "$PYTHON" -B -c "
import sys; sys.path.insert(0, '.')
from pathlib import Path
from builder.brains import ADAPTERS
from builder.doctor import doctor, used_flags
from builder.wizard import setup
assert all(used_flags(adapter) and adapter.install_help for adapter in ADAPTERS.values())
assert 'bin\" / \"vesper' in Path('vesper.py').read_text() and Path('bin/vesper').stat().st_mode & 0o111"
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
check "planning manifest v2: sections by depth in SECTIONS; new runs write planning_version 2 (P2-T5)" "P2-G, P4-T6, P4-T7" \
    sh -c 'grep -q "^SECTIONS = {" builder/planning.py && grep -q "\"planning_version\": 2}" vesper.py'
check "add-check: amendments in builder/amendments.py chained to the approval digest; a protected action (P2-T6)" "P2-T7, P3-T3, P5-T1" \
    sh -c 'grep -q "^def add(runner, check_id" builder/amendments.py && grep -q "\"add-check\": \"Adding this check\"" builder/approvals.py'
check "findings have a category; backlog.json and decide (--fix/--accept-risk) in builder/decisions.py (P2-T7)" "P2-G, P3-T4, P5-T1, P5-T3" \
    sh -c 'grep -q "^CATEGORIES = " builder/review_gate.py && grep -q "^def decide(runner, finding_id" builder/decisions.py && grep -q "\"accept-risk\": \"Accepting this risk\"" builder/approvals.py'
check "candidate reviews sweep touched code: touched_code and TOUCHED_SWEEP in builder/review_gate.py (P2-T8)" "P2-G, P3-T4" \
    sh -c 'grep -q "^def touched_code(before, after, paths)" builder/review_gate.py && grep -q "^TOUCHED_SWEEP = (" builder/review_gate.py'
check "estimates you can check: only marked reading pairs calibrate, approve keeps the estimate, usage check (P2-T9)" "P2-G, P4-T6" \
    sh -c 'grep -q "^def marked_pairs(rows, account)" builder/usage.py && grep -q "^def check_run(run, state, rows)" builder/usage.py && grep -q "\"estimate\": estimate}" builder/runner.py'
check "Codex reports tokens: --json event log, usage_report=True, no reply decoded from its event log (P2-T10)" "P2-G" \
    sh -c 'grep -q "usage_report=True" builder/brains/codex.py && grep -q "\"--json\"" builder/brains/codex.py && grep -q "reply_in_log = False" builder/brains/codex.py && grep -q "^def reply_path(brain, response, log, launcher=None)" builder/brains/__init__.py'
check "every role loads critical-thinking (SHARED_SKILLS); a launched worker's reasoning note goes to reasoning.md, required at full depth; the reviewer gets only the hand-off's labelled claims (P3-T1)" "P3-G, P3-T3, P3-T4" \
    sh -c 'grep -q "^SHARED_SKILLS = (\"critical-thinking\",)" builder/team.py && grep -q "^def reasoning_note(text)" builder/providers.py && grep -q "def keep_reasoning(self, state, job, brain, log)" builder/runner.py && grep -q "packet\[\"claims\"\]" builder/review_gate.py && ! grep -q "packet\[\"reasoning_note\"\]" builder/runner.py'
check "knowledge packs in team/knowledge/<role>/ with front matter, BM25 search (builder/knowledge.py, vesper kb search), part of the role revision; the approved tree is mounted read-only at /knowledge for workers and reviewers (P3-T2)" "P3-T4, P4-T1, P4-T5, P4-T7, P5-T3" \
    sh -c 'grep -q "^def search(files, query, limit=PROMPT_PASSAGES)" builder/knowledge.py && grep -q "^STALE_DAYS = 180" builder/knowledge.py && grep -q "result\[\"knowledge\"\] = files" builder/team.py && grep -q "\"/knowledge\", True" builder/sandbox/__init__.py && grep -q "add_parser(\"kb\"" vesper.py && grep -q "frozen\[\"knowledge\"\] = packs" builder/team.py && grep -q "knowledge=packs)" builder/runner.py && test -d team/knowledge/qa && test -d team/knowledge/reviewer'
check "QA owns checks: broken variants in checks/_broken/<CHECK_ID>/, prove-checks (builder/qa.py) required before approve at focused/full depth, draft-checks, record-only checks (blocking false; P3-T3)" "P3-G, P3-T5, P5-T3" \
    sh -c 'grep -q "^BROKEN = \"_broken\"" builder/qa.py && grep -q "^def prove(runner, against=None, launcher=None)" builder/qa.py && grep -q "check_proof = approval_proof(self, bundle)" builder/runner.py && grep -q "add_parser(\"draft-checks\"" vesper.py && grep -q "\"prove-checks\"" build_local.py && test -d docs/plan/fixtures/pocket-todo/checks/_broken/G_BROWSER'
check "reviewer findings carry repro and confidence; a blocker without repro is a suspected advisory; four lens reviews at full depth merged deterministically; 400-line size note; calibration.jsonl and decide --dismiss (P3-T4)" "P3-G, P3-T3b, P5-T4" \
    sh -c 'grep -q "^LENSES = (\"correctness\", \"security\", \"performance\", \"readability\")" builder/review_gate.py && grep -q "^def downgrade(report)" builder/review_gate.py && grep -q "^def merge(reports, packet)" builder/review_gate.py && grep -q "^SIZE_LIMIT = 400" builder/review_gate.py && grep -q "^FILE = \"calibration.jsonl\"" builder/calibration.py && grep -q "\"--dismiss\"" build_local.py'
check "Pocket Todo gates fold P2-G's 169 accepted findings, each decided once in findings-triage.md; G_API also checks the bind, parser replies, framing, races and the deployed layout; G_BROWSER the layouts and stale actions (P3-T3b)" "P3-G, P3-T5, P5-T4" \
    sh -c 'test -f docs/plan/fixtures/pocket-todo/findings-triage.md && test -f tests/test_pocket_todo_triage.py && grep -q "^def deployed(root)" docs/plan/fixtures/pocket-todo/checks/api.py && grep -q "^def second_loopback()" docs/plan/fixtures/pocket-todo/checks/api.py && grep -q "^def layouts(browser, base)" docs/plan/fixtures/pocket-todo/checks/browser.py'
check "approve requires an approving plan critique at full/focused depth, or the owner's decision on each blocker (P2-T7)" "P2-T2, P2-T5" \
    grep -q "Independent plan critique must approve" builder/runner.py
check "review_plan decodes through the brain adapter (tolerant decoder; P1-T1, P1-T8)" "P3-T4" \
    sh -c 'grep -q "parse_result(brain, reply)" builder/planning.py && grep -q "return decode_provider_report(text)" builder/brains/base.py'
check "plan critique uses the review limits (P1-T3)" "P1-T7, P1-T8" \
    grep -q "timeout=review_timeout, response=response, schema=schema, max_turns=review_max_turns" builder/planning.py
check "review-plan, consult and repair-run take --brain (P1-T8)" "P5-T1, P5-T3" \
    sh -c 'grep -q "brain_options(plan_review, group=choice)" vesper.py && grep -q "brain_options(advice)" vesper.py && grep -q "brain_options(repair_run, reviewer=True)" vesper.py'
check "specialist evals call a brain adapter (--brain, default codex; P1-T8)" "P5-T4" \
    grep -q "command(args.brain, 'consult'" examples/specialist_evals/run_evals.py
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
