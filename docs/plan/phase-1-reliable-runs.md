# Phase 1 — Reliable and safe runs

**Goal:** an automatic run finishes without manual help, inside a real sandbox, with
whichever AI the user has, for projects that use Go and React toolchains. Everything
later depends on this.

**Phase gate (P1-G):** the Pocket Todo fixture builds unattended inside the Docker
sandbox using ONE AI for every role, and exports a working app. A second run with a
different AI as reviewer also passes.

---

## P0-T1 — Add the plan and confirm the baseline

- **Change:** copy this folder to `docs/plan/`; copy `CLAUDE.md` to the repo root (if one
  exists, merge: keep both sets of rules); copy `docs/plan/superpowers/*.md` to
  `docs/superpowers/plans/` (the repo's existing Superpowers plan location). Add one line to `README.md` under "How the
  parts fit" pointing to `docs/plan/README.md`.
- **Do not:** change any Python file.
- **Acceptance:** the three commands in `docs/plan/README.md` step 6 all pass;
  `sh docs/plan/verify-facts.sh` prints no DRIFT (or each DRIFT is handled as README
  describes). Record the test count (41 at baseline commit `b7da4d1`) and the current commit in
  the PR description.

---

## P1-T1 — Robust reviewer report decoding

- **Why:** 2 of 3 real Claude reviewer replies were valid approvals wrapped as
  `"<one sentence>\n\n```json\n{...}\n```"`. `decode_provider_report` rejected them and
  the run stopped (`appendix-b`, finding 1).
- **Read first:** `builder/review_gate.py` (`decode_provider_report`, `validate_report`),
  `builder/runner.py` (`review_candidate`), `builder/planning.py` (`review_plan`, which uses
  the same decoder for plan critiques), `fixtures/pocket-todo/reviewer-replies/`.
- **Change** `decode_provider_report(text)`:
  1. Try `json.loads` on the stripped text.
  2. If the result is a Claude wrapper (`{"type":"result", ...}`), keep today's checks
     (`is_error`, `subtype`) and decode its `result` string with this same function.
  3. Otherwise look for fenced blocks (```` ```json ```` or bare ```` ``` ````). Try them
     from last to first; return the first that parses to a JSON object.
  4. Otherwise scan for the last balanced top-level `{…}` using
     `json.JSONDecoder().raw_decode` from each `{` position, last first.
  5. Otherwise raise the existing `BuilderError("Reviewer did not return a valid JSON report")`.
  Keep the 256 KB limit enforced by the caller. `validate_report` stays unchanged: it
  still binds attempt and digests and checks every evidence area.
- **Do not:** relax `validate_report`, accept arrays, or accept a report whose binding
  fields don't match.
- **Acceptance:** new `tests/test_review_decode.py` covering:
  bare object; fence only; prose + fence (use the real sample in
  `fixtures/pocket-todo/reviewer-replies/preamble-fence.json`); Claude wrapper whose
  `result` has prose + fence; two fences (the last valid wins); a fence holding invalid
  JSON followed by a valid one; prose with no JSON (raises); a wrapper with
  `is_error: true` (raises); and one test that `review_plan` accepts a plan critique wrapped
  as prose + fence (it shares the decoder).

## P1-T2 — Structured reviewer output

- **Why:** stop the problem at the source, not only in the parser.
- **Read first:** `builder/providers.py` (`provider_command`), `builder/review_gate.py`
  (`prompt`, `evidence_areas`), `START-HERE.md` (launcher interface table).
- **Change:**
  1. Add `report_schema(packet)` in `review_gate.py`. It returns a JSON Schema: object;
     `attempt_id`, `base_digest`, `candidate_digest` as `const` values from the packet;
     `verdict` enum `approve | request_changes`; `summary` string; `evidence` object
     requiring every key from `evidence_areas(packet)`; `findings` array of objects with
     `severity` enum `blocking | advisory`, `path`, `evidence`, `recommendation`.
  2. Write it to `review.schema.json` in the review workspace (`stage_review` and the
     fresh copy in `review_candidate`).
  3. Claude reviewer command (no launcher): add `--json-schema <schema text>`. The flag
     exists in Claude Code 2.1.321 (`claude --help`).
  4. Other agent CLIs (Codex, Gemini CLI): check their `--help` for an output-schema
     option. Where one exists, the adapter (P1-T8) declares the `strict_output`
     capability and passes the schema file; where not, it relies on P1-T1.
  5. Prompt: end with "Return only the JSON object. No text before or after it."
  6. Launcher interface: document that `review.schema.json` sits in the reviewer's CWD
     and a launcher should pass it to the provider.
  7. Plan critiques (`review_plan` in `builder/planning.py`) get the same treatment:
     `plan_report_schema(digest, identity)` with `phase` = `"plan"`, `packet_digest` and
     `reviewer` as `const`, `verdict`, `summary`, `evidence` requiring `requirements`,
     `architecture`, `checks`, and findings with `severity`, `path`, `scenario`,
     `consequence`, `evidence`, `recommendation` (mirror `validate_critique`).
- **Acceptance:** unit tests that the built reviewer command contains the schema flag;
  that `report_schema` accepts the real approved report from the fixture and rejects one
  missing an evidence area; `plan_report_schema` accepts a valid critique and rejects one
  missing `checks` evidence; the existing provider stand-in tests still pass.

## P1-T3 — Configurable gate and reviewer limits

- **Why:** gate timeout is hardcoded to 45 s (`run_check` passes 45, or 300 for
  `VESPER_REGRESSION` since b7da4d1); candidate-review and plan-critique timeouts are fixed
  at 180 s (`review_candidate`, `review_plan`) and `--max-turns 20`. Browser
  gates, Go builds and large reviews will exceed them.
- **Read first:** `builder/contracts.py` (`validate`), `builder/runner.py`
  (`execute_check`, `run_check`, `review_candidate`), `builder/providers.py`, `build_local.py`.
- **Change:**
  1. A check entry may carry `"timeout"`: integer seconds, 1 to 1800, default 45
     (`VESPER_REGRESSION` keeps 300; raised to 900 at P1-G, appendix B finding 40). Validate in `contracts.validate`; it is part of the
     digest because it sits in the contract.
  2. Add `--review-timeout SECONDS` (default 180; 600 for `review-plan` since P1-G, appendix B
     finding 46; max 1800) and `--review-max-turns N`
     (default 20, max 100) to `run` and `review-candidate` in `build_local.py` and to
     `review-plan` in `vesper.py`; thread them to `review_candidate`, `review_plan` and
     `provider_command`.
- **Acceptance:** tests for: an invalid check timeout is rejected at `review`; a gate that
  sleeps 50 s passes with `"timeout": 60` and fails without it (use a 1–2 s variant to
  keep tests fast); the reviewer command carries the chosen `--max-turns`.

## P1-T4 — Gate environment pass-through

- **Why:** `execute_check` gives gates only `PATH`, `HOME`, `TMPDIR`, `LANG`,
  `PYTHONDONTWRITEBYTECODE`. A Playwright gate could not find Chromium without a
  hardcoded path (`appendix-b`, finding 4).
- **Change:** contract top-level `"gate_env": ["PLAYWRIGHT_BROWSERS_PATH", ...]`: names
  only, values copied from the host at check time. Reject names that match
  `(?i)(key|token|secret|password|credential|auth)` and anything in `provider_environment`'s
  credential list. Document in `START-HERE.md`.
- **Acceptance:** a gate that prints a declared variable sees it; an undeclared one is
  absent; a contract declaring `ANTHROPIC_API_KEY` fails `review`.

## P1-T5 — Command gates (any language)

- **Why:** gates can only be Python scripts. QA must run `go test`, Vitest and Playwright
  (TypeScript) as independent checks.
- **Read first:** `builder/contracts.py` (`validate`), `builder/runner.py`
  (`execute_check`, `run_check`), `START-HERE.md` (launcher `check` operation).
- **Change:**
  1. A check entry has either `"script": "x.py"` (today) or
     `"command": ["go", "test", "./..."]` plus optional `"overlay"`:
     `{"from": "<dir in checks/>", "to": "<relative dir in the candidate>"}`.
     `command[0]` must be a bare program name (no path separators).
  2. Command gates run in a **throwaway copy** of the candidate (tools may write caches
     or reports there). The overlay is copied in first, so QA's independent tests sit
     next to the code without being part of the candidate. The verified candidate
     itself must stay byte-identical (existing inventory check).
  3. `HOME`, `TMPDIR`, `GOCACHE`, `GOPATH` and `XDG_CACHE_HOME` point inside the gate's temp dir.
  4. Launcher interface: add `launcher check-command <cwd> -- <argv...>`; keep
     `launcher check <script> <candidate>` unchanged.
- **Do not:** let a command gate write into `checks/` or the verified candidate.
- **Acceptance:** tests with a tiny Go module (skip if `go` is missing) where an overlay
  test file fails against a broken candidate and passes against a fixed one; a test that
  `command: ["/bin/sh", ...]` is rejected; all existing gate tests unchanged.

## P1-T6 — Toolchain support: setup step and ignored build dirs

- **Why:** React, shadcn, Kokonut, Bklit and Motion need `pnpm install`; Go needs modules.
  Today `safe_path` rejects `node_modules` and `inventory` rejects symlinks (pnpm uses
  them), so no such project can run.
- **Read first:** `builder/contracts.py` (`safe_path`, `inventory`), `builder/runner.py`
  (`copy_tree`, `verify`, `accept_candidate`, `export`), `builder/git_bridge.py`.
- **Change:**
  1. Contract top-level `"build"`:
     `{"ignore": ["node_modules", "dist", ".pnpm-store", "test-results", ".turbo"],
       "setup": [["pnpm", "install", "--frozen-lockfile"], ["go", "mod", "download"]]}`.
  2. Ignored top-level directories (and their symlinks) are skipped by `inventory`,
     `copy_tree` for snapshots and export, scope checks and Git patches. Everything else
     keeps today's strict rules: lockfiles (`pnpm-lock.yaml`, `go.sum`) are tracked files.
  3. Before the first command gate of a verification, run each `setup` command once in
     the throwaway copy (launcher operation `setup`, which is the ONLY gate-side step
     allowed network access). Cache dirs (`PNPM_STORE_DIR`, `GOMODCACHE`) live under
     `<run>/.builder/cache/` so repeat runs are fast.
  4. Worker workspaces may contain ignored dirs; they are never promoted.
- **Do not:** allow symlinks or special files outside ignored dirs; allow `setup` for
  script gates in repair mode.
- **Acceptance:** unit tests for ignore handling (a symlink inside `node_modules` is
  allowed, one in `src/` is rejected; ignored dirs never reach a snapshot or patch); an
  integration test (skipped if `pnpm` is missing) with a zero-dependency
  `package.json` whose Vitest-free command gate (`node --test`) runs after setup.

## P1-T7 — Config files (personal + project)

- **Why:** brains, sandbox, limits and defaults need one place; the owner decided on two
  levels and no secrets in config.
- **Change:** read TOML with `tomllib` (standard library):
  - Personal: `~/.config/vesper/config.toml` (override with `--config PATH` or
    `VESPER_CONFIG`). Sections: `brains`, `roles`, `sandbox`, `limits`, `defaults`,
    `tools`, `paths`.
  - Project: `vesper.toml` in the target repo or new project (committed). Sections:
    `stack`, `hosting`, `checks`. (Planning depth is not a config key: it comes from
    `plan/planning.json`, see b7da4d1.)
  - Precedence: command flag > project file for project matters (stack, hosting,
    checks) > personal file for personal matters (brains, sandbox, limits, paths) > built-in
    defaults. Implement this as an explicit table of which key belongs to which level.
  - Refuse any key whose name looks like a secret (`key`, `token`, `secret`,
    `password`, `credential`), with a message pointing to the secrets store.
  - `vesper config show` prints every effective value and where it came from.

  Example personal file:
  ```toml
  [brains.strong]
  use = "claude-code"
  model = "opus"
  effort = "high"

  [brains.fast]
  use = "claude-code"
  model = "sonnet"
  effort = "medium"

  [brains.reviewer]
  use = "claude-code"     # the owner sets "codex" here; one AI is enough by default
  model = "opus"

  [roles]
  planner = "strong"
  designer = "strong"
  technical-lead = "strong"
  frontend = "fast"
  backend = "fast"
  qa = "strong"
  reviewer = "reviewer"

  [sandbox]
  backend = "docker"      # docker | podman | none

  [limits]
  reserve_percent = 25
  review_timeout = 300
  review_max_turns = 30
  ```
  Model names are examples; adapters validate them against what the installed CLI accepts.
- **Acceptance:** tests for parsing, precedence per key, refusing secret-like keys,
  defaults when files are absent, and `config show` sources.

## P1-T8 — Brain adapter interface (any AI)

- **Why:** the owner decided Vesper must use ANY AI as its brain and must not depend on
  Claude or Codex. One AI must be enough. Today `builder/providers.py` hard-codes two CLIs.
- **Read first:** `builder/providers.py`, `builder/runner.py` (`run`, `review_candidate`),
  `builder/planning.py` (`review_plan`), `vesper.py` (`consult`, `review-plan`),
  `build_local.py` (`--provider` choices), `examples/specialist_evals/run_evals.py` (calls
  Codex CLI directly).
- **Change:**
  1. New package `builder/brains/` with a base adapter and one module per brain. Each
     adapter declares capabilities:

     | Capability | Meaning |
     | --- | --- |
     | `edit_files` | Can edit files in its workspace |
     | `run_shell` | Can run commands (used only with a sandbox, P1-T10) |
     | `strict_output` | Can be held to a JSON schema |
     | `model_select`, `effort_select` | Accepts model and effort choices |
     | `usage_report` | Reports tokens or usage per call |
     | `sandbox_login` | How it authenticates inside the sandbox (env var name or read-only file mount) |

     and implements `worker_command`, `reviewer_command`, `consult_command`,
     `parse_result` and `environment`.
  2. v1.0 adapters: `claude-code` (move today's Claude logic), `codex` (move today's Codex
     logic), `gemini-cli` (new; take flags from `gemini --help` at implementation time and
     record them in the adapter's docstring). Brains of "kind 1" (the host assistant in
     supervised mode) need no adapter: they drive Vesper through its commands.
  3. Roles map to brains through the config (P1-T7). Replace `--provider claude|codex`
     with `--brain NAME` everywhere it appears (`run`, `review-candidate`, `consult`,
     `review-plan`, `repair-run`); keep `--provider` as a deprecated alias for one release.
     The specialist evals call adapters too (finished in P5-T4).
  4. The core adapts to capabilities: no `strict_output` → tolerant parser only;
     no `usage_report` → time-only estimates; no `run_shell` → today's behaviour.
  5. The reviewer's independence comes from a fresh process, a read-only copy, no access
     to the worker's reasoning and its own checklist. A different brain for the reviewer
     is optional.
- **Do not:** leave vendor names in `builder/runner.py` or `builder/contracts.py`.
- **Acceptance:** stand-in adapters for all three pass the existing provider tests; a full
  stand-in run with one brain for every role reaches `complete`; a run with a different
  reviewer brain also completes; `grep -n "claude\|codex" builder/runner.py builder/planning.py`
  finds nothing.

## P1-T9 — Pluggable sandbox: Docker and Podman backends

- **Why:** the launcher is an interface with no implementation, so every real run so far
  used `--trust-host`. The owner decided Vesper runs sandboxed until proven, with the
  sandbox pluggable and Mac first.
- **Read first:** `START-HERE.md` (launcher table), `builder/providers.py`,
  `builder/runner.py` (`execute_check`), `docs/RC1.md` (repair launcher rules).
- **Change:**
  1. `builder/sandbox/` with backends `docker` (default), `podman`, and `none` (today's
     trust-host; explicit opt-in, warns on every run). The runner calls the backend, never
     Docker directly. Keep the external-launcher option for custom setups.
  2. One image definition `sandbox/Dockerfile`, built for **arm64 and amd64** (Apple
     Silicon and Intel Macs, Linux): Debian slim + Python 3.11+, Go, Node LTS + pnpm,
     Playwright browsers with OS deps, and the v1.0 agent CLIs (Claude Code, Codex, Gemini
     CLI). Pin versions in build args. Publish to GitHub's container registry later (P5).
  3. Operations and their boundaries:

     | Operation | Mounts | Network |
     | --- | --- | --- |
     | `worker <brain>` | Workspace read-write at `/work` | AI provider only |
     | `setup` | Workspace read-write, cache dir read-write | Allowed |
     | `check`, `check-command` | Gate dir and candidate read-only (throwaway copy writable for command gates), tmpfs `/tmp` | None (loopback works) |
     | `reviewer <brain>` | Review copy read-only | AI provider only |
     | `consult <brain>` | Baseline copy read-only | AI provider only |

  4. Logins come from each adapter's `sandbox_login` and the secrets store: macOS Keychain
     (via the `security` command) or `~/.config/vesper/secrets.env` (mode 600). Claude Code
     uses a token made once with `claude setup-token` (needed only for automatic mode,
     because the Mac keeps the normal login in Keychain). Codex and Gemini CLI: verify their
     login files or keys at implementation time.
  5. Hardening: non-root user, read-only root filesystem, `--cap-drop ALL`,
     `no-new-privileges`, memory and PID limits; never mount the host home, SSH keys or
     the Docker socket; never pass the full host environment.
  6. `sandbox/selftest.sh`: from inside each operation, try to write outside `/work`, read
     the host home, reach the internet from `check`, and write to a read-only mount. Every
     attempt must fail.
- **Acceptance:** unit tests for argument building per backend (no Docker needed);
  `selftest.sh` passes on the owner's Mac with Docker Desktop or Colima, and with Podman
  if installed; the `none` backend prints its warning.

## P1-T10 — Worker tool layer (shell only inside the sandbox)

- **Why:** workers cannot run the code they write (both Pocket Todo workers said so).
- **Read first:** `builder/brains/` (P1-T8), `builder/team.py` (`PROFILES`),
  `team/roles/frontend.md`, `team/roles/backend.md`.
- **Change:**
  1. Add a per-role tool list to `PROFILES` (writers: read, edit, write, search, shell;
     reviewer: read, search, shell; consult roles: read, search). Adapters translate these
     into their own flags.
  2. Shell is granted **only with a real sandbox backend**; with `none`, tools stay as today.
  3. Worker prompt: "You can run commands inside your workspace. Run the project's own unit
     tests and start the app before finishing. Report the exact commands and results."
     Independent gates stay hidden from the writer.
- **Acceptance:** tests that worker commands include shell with `docker`/`podman` and exclude
  it with `none`, for every adapter; the reviewer never gets edit or write.

## P1-T11 — `vesper setup` and `vesper doctor`

- **Why:** setup must work for other people too, not just the owner, and the CLI tools
  Vesper drives change their flags over time.
- **Change:**
  1. `vesper setup` (interactive): detects the OS and installed AI CLIs; asks which brain(s)
     to use; checks Docker/Colima/Podman and offers the install command; builds or pulls
     the sandbox image; walks through each brain's sandbox login (only for brains in use)
     and stores secrets in Keychain or the secrets file; asks for the plan-usage reserve;
     writes the personal config; runs `vesper doctor`.
  2. `vesper doctor`: checks Python version, config validity, sandbox backend reachable,
     image present and the right architecture, each configured brain's CLI present, its
     flags still match the adapter (run `--help` and compare), and login working (a tiny
     dry call). Prints a fix for each failure.
  3. The vesper command (shim and plugin launcher) finds a Python 3.11+ automatically, and
     vesper setup offers to install one, so users never need a venv.
- **Acceptance:** tests with fake environments for each branch; `doctor` reports a missing
  flag when a stand-in CLI's `--help` changes.

## P1-G — Phase 1 gate

Run on the owner's Mac:

```sh
vesper setup                                         # one brain for every role
vesper doctor
vesper start --mode build --idea "Pocket Todo"      # note the run path
cp -R docs/plan/fixtures/pocket-todo/plan/.   RUN/plan/   # managed planning format
cp -R docs/plan/fixtures/pocket-todo/checks/. RUN/checks/
vesper --project RUN review-plan --brain reviewer    # independent plan critique (b7da4d1)
vesper --project RUN review                          # the owner approves the digest
vesper --project RUN approve --digest DIGEST
vesper --project RUN run
vesper --project RUN export /tmp/pocket-todo-app
```

Pass when: status is `complete` with no manual step; every review parsed the first time;
the exported app starts and its three gates pass; `selftest.sh` passes. Then repeat with
`[brains.reviewer] use = "codex"` in the owner's config. Record elapsed time and plan
usage % before and after in `appendix-b-test-run-evidence.md` (seeds P2-T3).
