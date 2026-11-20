"""Inject and repair a real run-discovery defect in a disposable Vesper clone."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HEALTHY = 'return {"runs": output}'
BROKEN = 'return {"runs": []}'
FAILURE_ID = 'managed-run-discovery'

REPRODUCER = r'''
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1])


def run(*command, cwd, env):
    return subprocess.run(command, cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


def check(temp):
    target = Path(temp) / 'target'
    target.mkdir()
    env = dict(os.environ, VESPER_STATE_DIR=str(Path(temp) / 'state'),
               VESPER_TEST_CONFIRMER=str(Path(__file__).resolve().parent / "stand_in_confirmer.py"))
    run('git', 'init', '-q', cwd=target, env=env)
    (target / 'app.txt').write_text('Committed product fixture\n')
    run('git', 'add', 'app.txt', cwd=target, env=env)
    run('git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.com',
        'commit', '-qm', 'fixture', cwd=target, env=env)
    cli = (sys.executable, '-B', str(source / 'vesper.py'))
    start = json.loads(run(*cli, 'start', '--mode', 'bug', '--idea', 'Repair a local label', cwd=target, env=env))
    result = json.loads(run(*cli, 'runs', '--repo', str(target), cwd=target, env=env))
    if result == {'runs': []}:
        return 1, 'reproduced', 'start returned a managed run, but runs --repo returned an empty list.'
    if [item['project'] for item in result['runs']] == [start['project']]:
        return 0, 'fixed', 'runs --repo returned the exact project created by start.'
    raise ValueError('unexpected run discovery result')


try:
    with tempfile.TemporaryDirectory() as temp:
        code, outcome, evidence = check(temp)
except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
    print(f'Unexpected fixture failure: {exc}', file=sys.stderr)
    raise SystemExit(2)
print('VESPER_REPRO ' + json.dumps(dict(failure_id='managed-run-discovery', outcome=outcome, evidence=evidence)))
raise SystemExit(code)
'''

LAUNCHER = r'''
import json
from pathlib import Path
import subprocess
import sys

phase = sys.argv[1]
if phase == 'check':
    raise SystemExit(subprocess.call([sys.executable, '-I', '-B', *sys.argv[2:]]))
if phase == 'worker':
    path = Path('vesper.py')
    source = path.read_text()
    assert source.count('return {"runs": []}') == 1
    path.write_text(source.replace('return {"runs": []}', 'return {"runs": output}'))
elif phase == 'reviewer':
    packet = json.loads(Path('review.json').read_text())
    baseline = Path('base/vesper.py').read_text()
    proposed = Path('candidate/vesper.py').read_text()
    assert proposed == baseline.replace('return {"runs": []}', 'return {"runs": output}')
    assert packet['paths'] == ['vesper.py']
    checks = {item['id']: item for item in packet['checks']}
    assert all(checks[key]['exit_code'] == 0 for key in ('VESPER_REPRO', 'VESPER_REGRESSION'))
    assert 'exact project created by start' in checks['VESPER_REPRO']['evidence']
    verdict = {key: packet[key] for key in ('attempt_id', 'base_digest', 'candidate_digest')}
    verdict.update(verdict='approve', summary='Return the already filtered results from runs --repo.',
        findings=[], evidence={
        'requirements': 'Return the matching created managed run for the requested target.',
        'correctness': 'Restores the accumulated and filtered list without changing its construction.',
        'scope': 'Whole-file comparison shows precisely one corrected return expression.',
        'tests': 'The named start/runs workflow and frozen suite both passed.',
        'maintainability': 'Reuses the existing collected output.',
        'security': 'No change to target filtering, launch settings or trust boundaries.'})
    print(json.dumps(verdict))
else:
    raise SystemExit(2)
'''


def replay(destination):
    destination.mkdir(parents=True, exist_ok=False)
    source = destination / 'faulty-source'
    state = destination / 'state'
    env = dict(os.environ, VESPER_STATE_DIR=str(state), VESPER_TEST_CONFIRMER=str(Path(__file__).resolve().parent / "stand_in_confirmer.py"))

    def run(*args, cwd=destination, code=0):
        result = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True)
        if result.returncode != code:
            raise RuntimeError(f'{args}: expected exit {code}, got {result.returncode}\n{result.stdout}\n{result.stderr}')
        return result.stdout

    def git(*args):
        return run('git', *args, cwd=source).strip()

    run('git', 'clone', '-q', '--no-local', str(ROOT), str(source))
    source_file = source / 'vesper.py'
    original = source_file.read_text()
    assert original.count(HEALTHY) == 1
    source_file.write_text(original.replace(HEALTHY, BROKEN))
    git('add', 'vesper.py')
    git('-c', 'user.name=Vesper Fixture', '-c', 'user.email=fixture@example.com',
        '-c', 'commit.gpgsign=false', 'commit', '-qm', 'Inject managed run discovery defect')
    parent = git('rev-parse', 'HEAD')
    unrelated = source / 'unrelated-local.txt'
    unrelated.write_text('Keep this source checkout edit.\n')
    initial_status = git('status', '--porcelain')
    initial_index = (source / '.git/index').read_bytes()
    cli = (sys.executable, '-B', str(source_file))
    probe = destination / 'repro.py'
    probe.write_text(REPRODUCER)
    launcher = destination / 'fixture-launcher'
    launcher.write_text(f'#!{sys.executable}\n' + LAUNCHER)
    launcher.chmod(0o700)

    def plan(reproducer):
        run_path = json.loads(run(*cli, 'repair', '--idea', 'Restore managed run discovery', '--path', 'vesper.py',
                                   '--repro', str(reproducer), '--failure-id', FAILURE_ID))['project']
        def command(*args, code=0):
            return run(*cli, '--project', run_path, *args, code=code)
        return command

    for name, reason in [('product', 'App assertion failed'), ('provider', 'Provider credentials unavailable')]:
        control = destination / f'{name}-negative.py'
        control.write_text(f'raise RuntimeError({reason!r})\n')
        command = plan(control)
        command('repair-reproduce', '--launcher', str(launcher), code=2)
        command('approve', '--digest', json.loads(command('review'))['digest'], code=2)
        assert not git('for-each-ref', 'refs/heads/vesper/repair')
    print('Product and provider failure controls created zero repair refs.', flush=True)

    repair = plan(probe)
    approved = json.loads(repair('review'))['digest']
    proof = json.loads(repair('repair-reproduce', '--launcher', str(launcher)))
    assert proof['defect']['outcome'] == 'reproduced' and proof['digest'] == approved
    print('Named start/runs workflow reproduced on the frozen faulty baseline.', flush=True)
    repair('approve', '--digest', approved)
    status = json.loads(repair('run', '--brain', 'codex', '--reviewer-brain', 'claude-code',
                               '--launcher', str(launcher)))
    assert status['status'] == 'complete'
    reviewed = json.loads(repair('review-change'))
    assert reviewed['files'] == ['vesper.py']
    commit = json.loads(repair('repair-commit', '--digest', reviewed['digest']))
    assert commit['digest'] == reviewed['digest']
    assert git('rev-parse', commit['branch']) == commit['commit']
    assert git('rev-parse', commit['commit'] + '^') == parent
    assert run('git', 'show', commit['commit'] + ':vesper.py', cwd=source) == original
    assert git('diff-tree', '--no-commit-id', '--name-only', '-r', commit['commit']) == 'vesper.py'
    assert json.loads(repair('repair-commit', '--digest', reviewed['digest']))['commit'] == commit['commit']
    assert git('rev-parse', 'HEAD') == parent and git('status', '--porcelain') == initial_status
    assert (source / '.git/index').read_bytes() == initial_index
    assert unrelated.read_text() == 'Keep this source checkout edit.\n'
    assert any(receipt['commit'] == commit['commit'] for receipt in json.loads(run(*cli, 'learn'))['repairs'])
    checkout = destination / 'fresh-replay'
    run('git', 'clone', '-q', '--no-local', '--branch', commit['branch'], str(source), str(checkout))
    fixed = run(sys.executable, '-B', str(probe), str(checkout))
    assert '"outcome": "fixed"' in fixed
    result = {**commit, 'faulty_parent': parent, 'reviewer': 'deterministic fixture', 'replay': fixed.strip()}
    (destination / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    replay(parser.parse_args().destination.resolve())
