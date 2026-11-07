# Local Builder

Local Builder takes a reviewed product contract, runs scoped implementation jobs, and
only advances the accepted app when independent checks pass. The planner can be
Codex, Claude, or another interactive assistant. The coordinator runs in Python.
No Git setup or external service is required for the packaged supervised pilot.

## Start with the packaged pilot

Use Python 3.11 or later on macOS or Linux. From this directory:

```sh
python3 -B -m unittest discover -s tests -v
python3 -B examples/replay_stockroom.py ./stockroom-run
cd stockroom-run/app
python3 -B server.py --port 8765 --db stockroom.sqlite3
```

Open http://127.0.0.1:8765. The demo builds through real gates and deliberately
injects two failures before exporting the verified app. The supervised replay
uses the packaged job outputs. The local app and database are real. Run the same
commands with a fresh destination name to replay again.

## Start your own idea

From the Local Builder directory:

```sh
python3 -B build_local.py --project ~/my-product init --idea "A checklist for two people"
python3 -B build_local.py --project ~/my-product brief
```

Ask your interactive assistant to follow the printed brief. Review the user
journeys, wireframes, technical interfaces, and acceptance scenarios it places
in the project. The starter example in `examples/stockroom` shows every required file.

```sh
python3 -B build_local.py --project ~/my-product review
python3 -B build_local.py --project ~/my-product approve --digest PASTE_REVIEWED_DIGEST
```

Review prints the contract, SHA-256 manifest, and digest. Read the Markdown
documents and gate scripts before approving. The digest binds the exact draft,
trusted checks, and optional product seed. Later edits to the draft do not
change that approval. To change scope, prepare a new project with the revised
plan and an export of the accepted work as the seed, then review it again.

### Supervised mode

```sh
python3 -B build_local.py --project ~/my-product prepare
# Implement the job in the returned workspace using the returned job brief.
python3 -B build_local.py --project ~/my-product submit ATTEMPT_ID
python3 -B build_local.py --project ~/my-product status
```

Repeat until complete. Only the runner publishes snapshots. Submit executes
the approved checks on the host by default, so use this mode with trusted
code and trusted checks, or supply the isolation launcher below.

### Automatic mode

With a supported, authenticated provider CLI installed:

```sh
python3 -B build_local.py --project ~/my-product run --provider codex --launcher /absolute/path/to/launcher
# Or select --provider claude. The native Claude adapter expects v2.1.248+.
```

For a trusted local experiment, explicitly replace `--launcher …` with
`--trust-host`. The direct Codex adapter requests workspace-write. The direct
Claude adapter requests restricted mode and file tools. These controls depend
on the local installation. In host mode, the worker can reach resources
permitted by its CLI, and the approved checks can execute app code as your
user. Keep unrelated secrets out of the execution account. A hosted provider
receives the task brief and any project context its worker reads for the task.

The launcher is a user-configured executable. Its interface is:

| Invocation | Working directory and inputs | Expected boundary |
|---|---|---|
| `launcher worker codex` or `launcher worker claude` | CWD is the disposable work copy. The job brief arrives on stdin. | Give the provider the candidate as its writable project. Limit other mounts and network access to those needed for the selected provider. |
| `launcher check /path/to/gate.py /path/to/candidate` | CWD is a temporary gate directory. Gate inputs are in the script's parent directory. | Run Python with the gate package and candidate mounted read-only. Give it separate temporary space. Permit loopback inside the isolated environment for checks that start a server. |

A launcher returns the provider or gate exit status. Launchers and their OS
isolation are supplied and validated by the operator. A launcher can also
be passed to `submit ATTEMPT_ID --launcher /absolute/path` for supervised jobs.
The runner passes a limited environment. A launcher should source any required
provider credentials from its own scoped configuration.

### Recovery and output

- `status` shows the next job, accepted jobs, active attempt, and gate evidence.
- Run `run` again to recover an interrupted automatic attempt from the last
  accepted snapshot. You can select a different provider for the new attempt.
- Use `abandon ATTEMPT_ID` to set aside an interrupted attempt before switching
  to supervised mode. It preserves the work copy for inspection.
- If all attempts failed, `retry --reason "What changed"` grants exactly one more
  attempt and preserves previous failures.
- `export /absolute/path/to/new-app` copies the accepted snapshot. Work and run
  the exported app from there. The hidden control folder is runner-owned.

An approved check receives the candidate path as its first argument. It should
assert behavior and exit nonzero on failure. Write databases, build caches, and
other check outputs in temporary locations. The runner tracks candidate file
contents and modes and rejects links, special files, and unrelated changes.
On the final job it reruns the full approved gate set.

See [PILOT.md](docs/PILOT.md) for the results, limitations, and next gaps.
