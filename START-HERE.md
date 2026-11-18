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
Managed team jobs pause at `awaiting_review`. Follow the separate review step
in [the RC1 guide](docs/RC1.md) before preparing the next job.

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
| `launcher check-command /path/to/work -- PROGRAM ARGS...` | CWD is `/path/to/work`, a throwaway copy of the candidate with the check's overlay already copied in. `PROGRAM` is a bare name, never a path. | Mount the work copy writable and nothing from `checks/` or the verified candidate. Resolve `PROGRAM` on the sandbox's own `PATH`, run it with the given arguments in the work copy, and give it separate temporary space. Permit loopback as for `check`. When the contract has build setup, `GOMODCACHE` and `PNPM_STORE_DIR` name the run's dependency cache: mount it read-only. |
| `launcher setup /path/to/work -- PROGRAM ARGS...` | CWD is `/path/to/work`, a throwaway copy of the candidate. Runs once per verification, before the first command gate, for each command in the contract's `build.setup`. `PNPM_STORE_DIR` and `GOMODCACHE` name the run's dependency cache. | The only gate-side step that may have network access. Mount the work copy and the two cache directories writable, nothing else. Resolve `PROGRAM` as for `check-command`. |
| `launcher reviewer codex` or `launcher reviewer claude` | CWD contains the baseline, candidate, frozen plan, diff, and check evidence (for a plan critique: `plan/`, `checks/` and `seed/`), plus `review.schema.json`, the JSON Schema the verdict must match. The review prompt arrives on stdin. | Mount the review copy read-only. Pass `review.schema.json` to the provider's structured-output option where it has one (Claude Code: `--json-schema "$(cat review.schema.json)"`). Return the JSON verdict on stdout. Exclude the writer workspace and accepted snapshots. |
| `launcher consult codex` or `launcher consult claude` | CWD is a copy of the baseline. The specialist brief and requested handoff arrive on stdin. | Mount the baseline read-only and return the handoff on stdout. |

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

A check can also be a command in any language, such as `go test`, Vitest or
Playwright, in place of a script:

```json
{"id": "G1", "command": ["go", "test", "./..."],
 "overlay": {"from": "gotests", "to": "."}, "timeout": 300}
```

The first item must be a bare program name (`go`, `pnpm`, `node`), not a
path. Without a launcher, the runner finds it on its own `PATH`, and the gate's
`PATH` is that program's directory plus `/bin:/usr/bin`. The command runs in a
throwaway copy of the candidate, so tools may write caches and reports there.
The optional `overlay` copies a directory from `checks/` into that copy first
(`"to": "."` is the candidate root), so QA's own tests sit next to the code
without being part of the candidate. Overlay files replace candidate files of
the same name. The verified candidate and `checks/` must stay unchanged, or the
check fails.

Gates get a minimal environment: `PATH`, a temporary `HOME` and `TMPDIR`,
`LANG`, `PYTHONDONTWRITEBYTECODE`, and tool caches inside that temporary
directory (`XDG_CACHE_HOME`, `GOCACHE`, `GOPATH`). When a gate needs more, for example a
Playwright gate that must find its browsers, list the variable names in the
contract's top-level `gate_env`:

```json
"gate_env": ["PLAYWRIGHT_BROWSERS_PATH"]
```

Only names go in the contract, so they are part of the reviewed digest. The
runner copies each value from its own environment when the gate runs and
leaves out names that are unset. With a launcher, the variables reach the
launcher process, which decides what enters its sandbox. `review` rejects
names that look like secrets (any containing `key`, `token`, `secret`,
`password`, `credential` or `auth`, in any case), provider login variables such
as `ANTHROPIC_API_KEY`, `CLAUDE_CONFIG_DIR` or `CODEX_HOME`, and the names the
runner sets itself (the eight above plus `GOMODCACHE`, `PNPM_STORE_DIR`,
`pnpm_config_store_dir` and `npm_config_store_dir`).

### Toolchains: build setup and ignored directories

Projects that need `pnpm install` or Go modules declare a top-level `build`:

```json
"build": {"ignore": ["node_modules", "dist", ".pnpm-store", "test-results", ".turbo"],
          "setup": [["pnpm", "install", "--frozen-lockfile"], ["go", "mod", "download"]],
          "timeout": 600}
```

`ignore` names top-level directories that hold build output. Worker work
copies may contain them, links included, but they are never checked for
scope, promoted to a snapshot, exported or put in a Git patch. Everything else
keeps the strict rules: links and special files are rejected, and lockfiles
such as `pnpm-lock.yaml` and `go.sum` are ordinary tracked files. A job may
not write inside an ignored directory, and the seed may not contain one.

`setup` commands run once per verification, before the first command gate,
in a throwaway copy of the candidate (launcher operation `setup`). They must
leave tracked files unchanged, so commit the lockfile: `pnpm install
--frozen-lockfile` writes one when none exists, which fails the check. Each
command gate then gets the setup's ignored directories in its own copy.
`GOMODCACHE` and the pnpm store (`PNPM_STORE_DIR`, plus `pnpm_config_store_dir`,
the name pnpm 10 and later reads) point into `.builder/cache/` in the run, so
repeat verifications reuse downloads. Script gates never trigger setup, and
Vesper repairs cannot use it. `timeout` is per setup command (1 to 1800
seconds, default 600).

See [PILOT.md](docs/PILOT.md) for the results, limitations, and next gaps.
