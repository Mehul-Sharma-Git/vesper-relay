# Appendix B — Test-run evidence and unscheduled gaps

## 1. The Pocket Todo run (9 Nov 2026)

Setup: Vesper installed into a throwaway home; `vesper start --mode build`; plan written
by the assistant acting as planner, designer, tech lead and QA; owner approved the digest;
`run --provider claude --trust-host` (no sandbox launcher existed). Claude Code 2.1.321.
The full plan, checks, wireframes, reviewer replies and the exported app are in
`fixtures/pocket-todo/`.

Result: `complete`. J_API and J_UI each accepted on the first worker attempt; the three
gates (API, page, real browser) passed, including the final full rerun; the export
worked at 320, 375 and 1280 px. About 8 minutes of runtime. The three reviewer calls
reported about $1.26 at list price (informational; the owner's plans are fixed-fee).

## 2. Numbered findings (referenced by task files)

| # | Finding | Fixed by |
| --- | --- | --- |
| 1 | Reviewer verdicts with a sentence before a fenced JSON block were rejected by `decode_provider_report`; 2 of 3 calls; run stopped and needed a supervised `review-candidate --report` | P1-T1, P1-T2 |
| 2 | Workers had Read/Edit/Write only and could not run code; both said nothing was run | P1-T10 |
| 3 | The review copy had only one-line gate summaries; the reviewer said logs were missing | P2-T1 |
| 4 | Gate env stripped to PATH/HOME/TMPDIR/LANG; a Playwright gate needed a hardcoded browser path; gate timeout fixed at 45 s | P1-T3, P1-T4 |
| 5 | The reviewer found that any website could change the owner's todos (no CSRF/Origin check) but filed it as advisory; it shipped | P2-T7, P4-T5 |
| 6 | The UI matched the wireframe's layout but had a generic default look; nothing asked for or checked design quality | P4-T1 to P4-T4 |
| 7 | The planner never asked about language/stack or system design; nothing enforces options, risks or assumptions | P2-T5, P4-T6 |
| 8 | Reviewer timeout fixed at 180 s and 20 turns | P1-T3 |
| 9 | Provider env passes HOME but drops HTTPS_PROXY/NO_PROXY/CA variables; works on a plain network, likely fails behind a corporate proxy | Unscheduled, see section 3 |
| 10 | No package installs: `node_modules` and symlinks rejected; the runner could only build stdlib Python + static files | P1-T6 |
| 11 | `start` scaffolds only `contract.json` and `idea.md`; the planner must know every other file and field from docs | P2-T5, P4-T6 |
| 12 | The plan's "use from phone on home Wi-Fi" needs `--host 0.0.0.0`; no guidance on the exposure risk | P4-T5, P4-T7 |
| 13 | Design artifacts were text only; `validate_design` accepts a direction with one sentence | P4-T2 |
| 14 | Adding wireframe files to `plan/` changed the digest as expected: approval binds the pictures the owner saw | Keep |
| 15 | Free hosting (Render, Vercel) would lose the app's SQLite data | P4-T7 hosting pack |
| 16 | While fixing #1: a hostile reviewer reply (deep nesting, or 256 KB of `{"`) made the decoder raise `RecursionError` or scan for 10+ s. The brace scan now tries only keyed-object starts, catches `RecursionError`, and gives up after 200 failed starts | P1-T1 |
| 17 | With `--json-schema`, Claude Code (checked on 2.1.81, 17 Nov 2026) returns the report in the wrapper's `structured_output` and leaves `result` empty. Without reading `structured_output`, adding the flag would have rejected every Claude review. Codex CLI and Gemini CLI were not installed, so their output-schema options are unchecked; the brain adapters (P1-T8) must check them | P1-T2, P1-T8 |
| 18 | While testing P1-T3 (18 Nov 2026): after a timeout kill, `run_process` calls `os.killpg` again in its `finally`. On macOS that call sometimes raises `PermissionError` (EPERM) when the group holds only an unreaped zombie, so the command crashes with "Operation not permitted" instead of returning exit 124. Seen locally in 1 of 12 reviewer-timeout runs and 0 of 12 gate-timeout runs, and on the GitHub macOS runner in 1 of 2 gate-timeout runs (PR #9). There `verify` turned the `OSError` into a rejection of kind "environment", with no check recorded. Affects gates, workers and reviewers that time out. The owner approved the fix inside P1-T3: `stop_group` now treats EPERM like ESRCH, since every group member was started in that session under the same user | P1-T3 |
| 19 | P1-T3: `--review-max-turns` reaches only a direct (`--trust-host`) provider command. The launcher protocol (`launcher reviewer <name>`) builds its own provider command, so a launcher never sees the turn limit; the review timeout does apply to launchers | P1-T8, P1-T9 |
| 20 | P1-T4: `gate_env` reaches every gate run through `verify`, including `VESPER_REPRO` after approval. The repair baseline reproduction before approval (`repair.reproduction_record`) still calls `execute_check` without it, so a reproducer that needs a declared variable would see it only after approval. Harmless for today's standard-library reproducers; left out because `builder/repair.py` is outside P1-T4's scope | unscheduled |
| 21 | P1-T5: `validate_repair` (`builder/repair.py`) reads `item["script"]` for every check, so a repair contract that contains a command gate stops with a `KeyError` instead of a clean "Repair requires…" error. The contract is still refused, so nothing unsafe runs; left out because `builder/repair.py` is outside P1-T5's scope (`validate_maintenance` in `builder/contracts.py` was fixed to use `.get`). Still open after P1-T6, which also leaves `builder/repair.py` alone; it only adds the earlier "Vesper repairs cannot run build setup" refusal. Fixed 18 Nov 2026 with the owner's OK, in a housekeeping PR after P1-T6: `validate_repair` uses `.get("script")`; `tests/test_repair_validation.py` | fixed |
| 22 | P1-T5: without a launcher, a command gate's program is found on the runner's own `PATH`, and the gate's `PATH` is only that program's directory plus `/bin:/usr/bin`. A tool that needs a sibling from another directory (for example `pnpm` from a version manager calling `node` elsewhere) won't find it. Each gate also starts with an empty `GOCACHE`, so a first `go test` compiles the standard library again (about 15 s per gate on an M-series Mac). Shared caches and sandbox `PATH` belong to the setup step and the sandbox | P1-T6, P1-T9 |
| 23 | P1-T6 (18 Nov 2026, pnpm 12.21 via corepack, macOS): `pnpm install --frozen-lockfile` *writes* `pnpm-lock.yaml` when none exists (zero-dependency project), so setup's "tracked files unchanged" rule fails until the lockfile is committed. Corepack also downloads pnpm itself into the setup's temporary `HOME` on every run, so even a zero-dependency setup needs network; a sandbox image with pnpm preinstalled (or a cached `COREPACK_HOME`) avoids it. pnpm 12 ignores both `PNPM_STORE_DIR` and `npm_config_store_dir` (only `pnpm_config_store_dir` moves the store) and, on macOS, falls back to the real `~/Library/pnpm/store`, outside the run; the runner sets all three (found by the independent review of PR #12) | P1-T9, P5-T2 |
| 24 | P1-T6: only the dependency caches (`GOMODCACHE`, pnpm store) are shared across verifications, in `<run>/.builder/cache/`; `GOCACHE` stays per gate (finding 22). Without a launcher, command gates can write to that shared cache like any host process; a launcher must mount it read-only for `check-command` (START-HERE launcher table). Each command gate gets its own copy of the setup's `node_modules`, which costs a copy per gate on large installs | P1-T9 |
| 25 | P1-T7: config refuses any key name that contains `key`, `token`, `secret`, `password`, `passwd` or `credential` anywhere, ignoring case (only `keyboard`, `keystroke` and `keystore` are exempt). Three independent review rounds on PR #14 found word-splitting heuristics that let `api_key1`, `awsAccessKeyId` or a quoted dotted key through, so the literal rule won. Later config keys must avoid those words: name a usage cap `usage_limit` or `max_usage`, not `max_tokens`, and an adapter's login `sandbox_login`, not `auth_token`. Nothing reads the config yet: `--set` exists only on `config show`, and no other command takes `--config` | P1-T8, P2-T3, P1-T11 |
| 26 | P1-T8 (18 Nov 2026): Gemini CLI was not installed, so the `gemini-cli` adapter's flags come from the upstream reference (`docs/cli/cli-reference.md`, `headless.md`, `reference/configuration.md`; package 0.70.0-nightly.20261110) and are recorded in the adapter's docstring. Unverified until it runs: `--allowed-mcp-server-names vesper-none` as an "allow nothing" list, and the stdin prompt plus `-p` closing line. Gemini has no effort, JSON Schema or turn-limit flag (the limit is the `model.maxSessionTurns` setting), so only the wall-time limit bounds it. Without a launcher it also reads the user's `~/.gemini` settings and extensions (`-e none` appears only in a doc summary, so it is not used). Codex has `--output-schema` but it is still not wired, so `codex` and `gemini-cli` are not `strict_output` and their reviewers use the tolerant parser (finding 17) | P1-T9, P1-T11 (`doctor` checks the installed CLIs) |
| 27 | P1-T8: the launcher protocol still passes only `<operation> <cli>` (`claude`, `codex`, `gemini`), unchanged so existing launchers keep working. A brain's `model`, `effort` and the review turn limit reach only a direct (`--trust-host`) brain (finding 19) | P1-T9 |
| 28 | P1-T8: commands now read the config. A brain name (`--brain`, `--reviewer-brain`, or `[roles]` when no flag is given) resolves through the personal config, then the current directory's `vesper.toml`, as `config show` does, so a malformed config file stops `run`, `review-candidate`, `consult`, `review-plan` and `repair-run` even when an adapter name is passed. With `--brain X` and no `--reviewer-brain`, a `[roles] reviewer` in the config takes the review; without it the worker's brain reviews. Attempts record `provider` (the brain name) and `adapter`; reviews also record `usage` (token counts only) for brains that report it. Repair commits now require a review whose `adapter` is a known adapter. `manual` and `operator` are reserved brain names: the core records them for a manual attempt and an attested report (found by the independent review of PR #15) | Keep |
| 29 | P1-T9 (18 Nov 2026, Docker Desktop 29.2.0 on Apple Silicon): the sandbox image builds to 4.0 GB (arm64). Building it surfaced three things that later images must keep: `debian:trixie-slim` has no `useradd` (the image only creates `/home/vesper`, since Vesper always passes `--user` with your uid); Node on arm64 needs `libatomic1`; and go.dev serves no `.sha256` file per download, so the Go checksum comes from `go.dev/dl/?mode=json&include=all`. Trixie gives Python 3.13. Playwright installs Chromium only (not Firefox or WebKit). The amd64 build is defined (`TARGETARCH`) but was not built here | P5-T2 (publish both architectures) |
| 30 | P1-T9: `sandbox/selftest.sh` passed on the first real run: in all six operations every escape attempt (write the image, `/etc` or `/`, read the host home, find the engine socket, run as root, keep capabilities, write a read-only mount or cache, reach the internet directly, tunnel through the proxy to a non-provider host) was blocked. Writes to `/work`, loopback and the tunnel to the provider worked. The provider check needs internet on the host. Podman isn't installed here, so the `podman` backend (`--userns=keep-id`, network `podman`) is checked only by argument tests. CI skips the Docker tests because it has no image | P1-G (run Pocket Todo in the sandbox), P5-T2 |
| 31 | P1-T9: no real brain ran in the sandbox yet, because this machine has no sandbox logins. Claude Code needs a `claude setup-token` token (Keychain service `vesper-relay` or `secrets.env`). Codex's `~/.codex/auth.json` is mounted read-only at `/run/vesper-login/` and copied into the private home before the CLI starts. A bind mount straight into the home made `~/.codex` root-owned and unwritable (found by the independent review of PR #16), and with the copy a refreshed token still can't reach the host file, so a long run may hit an expired token. Gemini CLI works only with an API key (a cached Google login in `~/.gemini` isn't mounted). The proxy allows only each adapter's `sandbox_hosts` over HTTPS (port 443); Claude Code runs with `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`. The host lists come from documentation, not from watching real traffic | P1-G, P1-T11 (`doctor` checks logins) |
| 32 | P1-T9: commands that already needed a boundary (`run`, `review-candidate`, `consult`, `review-plan`, `repair-reproduce`, `repair-run`) now default to `sandbox.backend` (docker). `submit` defaults to the sandbox too, as 00-context requires for supervised mode (round 1 of the independent review of PR #16 blocked an earlier host default). Tests and replays that use stand-in CLIs and trusted fixture gates choose `none` explicitly (a private config, or `--sandbox none`), so they need no engine and print the warning | Keep |
| 33 | P1-T9: a container engine on a Mac shares only some host folders. Docker Desktop shares `/Users`, `/private`, `/tmp` and `/var/folders` by default. Colima shares only the home directory, so runs must live under it: the default state directory does; a `--project` in `/tmp` won't mount. Consultations now use a temporary directory inside the run (`.builder/`) for the same reason. Killing the runner leaves no container behind: each job and proxy has a name and is removed with `rm -f`, and its network is removed in a `finally` | P1-T11 (`doctor` checks shared folders) |
| 34 | P1-T9: the built-in sandbox builds each brain's own command inside the container, so `model`, `effort` and the review turn limit now reach sandboxed brains (finding 27 remains for external launchers only). A reply file reaches the host through a per-call `/out` mount, never through the read-only review copy | Keep |
| 35 | P1-T10: Codex has no per-tool list: it reads, searches and edits through its own command tool, confined by its own `--sandbox` policy. So with no sandbox backend (`none`) a Codex worker still runs commands inside Codex's `workspace-write` sandbox, as before; turning its command tool off (`features.shell_tool`) would also stop it reading files. Inside a Vesper sandbox the worker gets `--sandbox danger-full-access` (the Codex docs: "use only if your environment already isolates processes"), and the container is that boundary. Reviewers and consultants stay `read-only`. Not yet seen with a real Codex: Codex's own `read-only` sandbox (Landlock/bubblewrap) may not start inside the hardened container (`--cap-drop ALL`, the engine's default seccomp profile), which would leave a sandboxed Codex reviewer unable to run even read commands | P1-G (run a Codex reviewer in the sandbox), P1-T11 |
| 36 | P1-T10: Gemini CLI's shell tool is `run_shell_command`; headless mode denies it unless allowed, so a sandboxed Gemini worker gets `--allowed-tools run_shell_command`. Upstream marks `--allowed-tools` deprecated in favour of policy files, and project-level policy files (`.gemini/policies/`) are disabled upstream (issue 18186), so a later CLI may need a user policy file written into the sandbox home instead. Reviewers keep `--approval-mode plan`; the docs don't say whether plan mode honours the shell allowance. Claude Code reviewers get `Bash` in the sandbox (the review copy is mounted read-only). Tool lists stay out of a role's frozen revision, so existing runs and the Pocket Todo fixture keep their revisions | P1-T11 (`doctor` re-checks the flags), P1-G |
| 37 | P1-T11 (18 Nov 2026): `vesper doctor` checked every adapter's flags against the pinned CLIs in the sandbox image (Claude Code 2.1.327, codex-cli 0.170.0, Gemini CLI 0.68.0): all listed, except Claude Code's `--max-turns`, which is accepted but hidden from `--help` and so declared `hidden_flags`. On this Mac the host `claude` is 2.1.81, which rejects `--restricted` ("unknown option"); so `sandbox.backend = "none"` with the host CLI would fail every Claude call until it is updated, and doctor says so. The doctor also checks finding 33 (can the engine see the state folder): it passes under the home folder with Docker Desktop and fails, with the fix, for an unshared `/opt/homebrew/var` path. Docker Desktop 29.2 (containerd image store) once answered `No such image` to `docker image inspect TAG` for several minutes while `docker image ls` listed the tag and inspect by ID worked; it recovered by itself. The runner's image check (`Container.check`) has the same exposure; doctor tells this case apart from a missing image. No real dry call ran: this machine has no sandbox token for Claude Code yet (finding 31) | P1-G (store the token with `vesper setup`, then `vesper doctor`) |
| 38 | P1-G first run (19 Nov 2026): the sandbox image had Node Playwright and its Chromium but not Python Playwright, while the Pocket Todo gate `browser.py` is a Python Playwright script, and gates run as `python3 -I` in the image. J_UI failed both attempts with `ModuleNotFoundError: playwright` before judging any UI; J_API passed. The image now pip-installs Python Playwright at `PLAYWRIGHT_VERSION` (pinned `greenlet`). Python Playwright 1.65.1 expects Chromium build 1254 while the Node package of the same version installs 1255, so the Python package installs its own build too (both live in `/opt/playwright`). A container test drives Chromium from a Python gate in the hardened, network-less `check` job | Fixed in the P1-G fix PR |
| 39 | P1-G (19 Nov 2026): the Docker Desktop 29.2 `No such image` answer (finding 37) hit the runner 4 times in one evening, once stopping `vesper run` before it started, and it lasted minutes at a time; using the image (a `docker run` by tag or an inspect by ID) brought the tag back. `Container.check` now resolves the tag to the image ID, falls back to the ID that `docker image ls -q --no-trunc TAG` lists when inspect misses the tag, and every job and proxy then runs that ID, so the tag is looked up once per command | Fixed in the P1-G fix PR |
| 40 | P1-G (19 Nov 2026): `examples/replay_repair.py` failed twice in a row with `VESPER_REGRESSION exited 124` (timed out, about 100 of 240 tests done): the gate runs Vesper's whole baseline suite, which now takes about 300-330 s on the owner's Mac (Docker container tests included), against a 300 s default. Repair plans set no check timeout, so the runner's default for `VESPER_REGRESSION` is now 900 s (`REGRESSION_TIMEOUT`); a contract can still set 1 to 1800 | Keep; revisit if the suite nears 900 s |
| 41 | P1-G (19 Nov 2026): a launched plan critique lost its whole reply when one finding cited a folder instead of a file: Claude cited `seed/` (run 1) and Codex cited `plan/` (run 3, `Invalid relative path: 'plan/'`), each spending one of the packet's 3 attempts. The prompt never said a finding must name one file, the reply schema left `path` free, and the rejected reply was deleted with the review folder. Asked for the folder under a `pattern` schema, Claude answered `plan/.`, which the path check also rejects. The prompt now lists the files a finding may cite and says never a folder; the schema's `path` pattern allows only a file under `plan/`, `checks/` or `seed/` (no `.` or `..` segment); a rejected reply is kept as `.builder/plan-critique-rejected-<attempt>.txt` (mode 600) | Fixed in the P1-G critique-citation PR |
| 42 | P1-G run 2 (19 Nov 2026): J_UI's first worker attempt (Claude, sandboxed) stopped after 7 minutes with `API Error: Couldn't connect through your proxy (ERR_PROXY_TUNNEL)`; the runner retried and the second attempt was accepted, so the run still completed unattended. The cause can't be found: the egress proxy's log was removed with its container. Each egress job now copies the proxy's log (last 64 KB) to `<job log>.proxy.log` before the container is removed; checked live, it names a refused host (`Proxying refused on filtered domain "example.com"`). Reading it never changes the job's result | Diagnostics fixed in the P1-G proxy-log PR; cause open until it recurs |
| 43 | P1-G run 3 (19 Nov 2026): the Codex plan critique (codex-cli 0.170.0, in the Docker sandbox) read nothing: Codex ran its commands under its own `--sandbox read-only`, whose Linux sandbox (bubblewrap) answered `bwrap: No permissions to create a new namespace` inside the hardened container, so it returned `request_changes` saying it could not open the packet. Codex 0.170 has no namespace-free mode left (`use_legacy_landlock` deprecated, the bwrap switch removed). A reviewer granted shell (only inside a Vesper sandbox) now runs `danger-full-access` like the worker, and the engine's read-only `/work` mount keeps the review copy unchanged; checked live, a sandboxed Codex reviewer read `/work` and `touch /work/x` failed. Host reviewers and every consultant stay `read-only`. A Codex consultant inside the sandbox still cannot run commands | Fixed in the P1-G Codex-reviewer PR; Codex consultants in the sandbox still open (follow-up) |
| 44 | P1-G run 3 (19 Nov 2026): both Codex plan critiques raised a blocker on `plan/planning.json`'s `architecture.revision`, reading it as an unverified digest of `architecture.md`. It is the technical-lead role revision, which the runner checks with the authors, and the approval binds every plan file by digest; the critique prompt never said so. The prompt now explains the manifest's revision field. (Codex's other blockers on the Pocket Todo plan were about the plan itself and are recorded with the gate run.) | Fixed in the P1-G planning-manifest PR |
| 45 | P1-G (19 Nov 2026): the Pocket Todo plan went through six critique rounds (Claude 3, Codex 3), and each round found new items of the same four kinds: who can reach the app (server files served, cross-site writes, DNS rebinding, clickjacking), two devices changing the same record (stale delete count twice, reused ids), gates a wrong build could pass (confirm dialog unchecked, laptop flow unexercised, stale delete unobserved, 320 px promised but 375 px tested), and unclear spec (phone panel, accented case). Claude marked as advisory what Codex blocked. Cause: nothing in plan creation required a complete sweep of any kind; the roles mentioned "who can act" and "stale versus invalid" in passing, and the critique prompt only said "distinguish blockers from advice", so each critique sampled a few items, each fix patched exactly those, and the brains drew the blocker line differently. Now: the technical lead delivers complete reachability and concurrent-change lists (each item mitigated with its gate, or proposed as a risk that only the owner accepts, by approving the plan; a decision-log entry never counts), QA a failure-path matrix naming the wrong implementation each assertion catches, the planner's packet carries both, and the critique sweeps each kind in one pass under a stated blocker rule. P2-T5 will make `review` refuse a plan without them | Fixed in the P1-G plan-sweep PR (roles and critique); runner enforcement in P2-T5 |
| 46 | P1-G (19 Nov 2026): with the sweep (finding 45), the Codex plan critique of the Pocket Todo plan ran about 182 s and was killed by the 180 s reviewer default; Vesper said only "Plan reviewer failed". Claude finished its sweep just inside the limit. `review-plan` now defaults to 600 s (`PLAN_REVIEW_TIMEOUT`; candidate reviewers keep 180 s) and the error says "timed out after N s; raise --review-timeout" or gives the exit code | Fixed in the P1-G plan-critique timeout PR |
| 47 | P1-G round 4 (19 Nov 2026): after the sweep (finding 45) Claude's critique converged (8 blockers, then 3, all plausible) but Codex's diverged (4, 3, then 23), most out of proportion for a one-person local app (cleartext on home Wi-Fi, a stale service worker, VPN interfaces, snapshot coherence). Cause: the blocker rule said "a requirement can be broken by an implementation that passes every gate", which no finite gate set can satisfy, since a reviewer can always invent a build made to slip past it; and nothing bounded security findings to the owner's threat model. Now a gate gap blocks only for a requirement with no assertion or a plausible mistake by a competent engineer following the plan (a build made to evade gates is the candidate reviewer's, who reads the code); security blocks only inside the owner's threat model, which the planner records; a threat placed outside it is still reported as "Accepted risk: owner must confirm", never dropped. P2-T5 adds `threat_model` to the required sections | Fixed in the P1-G critique-proportionality PR |
| 48 | P1-G run 4 (19 Nov 2026): with Codex reviewing every job, J_API was never accepted in five attempts (2 + 3 owner-approved `retry` grants). Each attempt rewrote `server.py` from the empty base snapshot, and each brief carried only the previous attempt's reason (`builder/runner.py:370`): attempt 2 fixed Codex's review blockers and broke a gate assertion (`inbox` as `1`), attempt 3 fixed the gate and repeated the review blockers, attempt 4 timed out, attempt 5 broke the gate again. Workers never see the gate scripts, so they test with their own requests | Fixed in the P1-G retries PR: a retry starts from the job's newest candidate that passed the scope check (if unchanged since), its brief lists every earlier failure oldest first (each cut to an equal share of 12,000 characters), and each workspace holds a read-only copy of the job's gates in `.vesper-gates/` with how to run them (owner decision: workers see the gates). Vesper ignores the copy and runs its approved gates |
| 49 | P1-G run 5 (19 Nov 2026, after the finding 48 fix): J_API's second attempt started from the first's `server.py`, fixed all three Codex review blockers and passed G_API in its own run, but was rejected unchecked with `Invalid relative path: '__pycache__'`: testing, it imported `server.py`, and Python left `__pycache__/server.cpython-313.pyc` in the workspace. Workers now run code (P1-T10), so caches are expected, and `safe_path` refuses the name. That spent the job's last attempt | Fixed in the P1-G Python-caches PR: `verify` removes `__pycache__` folders from the worker's workspace before checking it (a linked one is unlinked, never followed; ignored top-level folders untouched) |
| 50 | P1-G run 6 (19 Nov 2026, with the finding 48 and 49 fixes): J_API's second attempt started from the first, fixed all three Codex review blockers without a regression and passed G_API, yet Codex raised two new blockers on it: a `Host` such as `999.0.0.1` accepted as an IPv4 address (no browser or rebinding page sends one) and an invalid delete-confirmation name answered 409 instead of 400 (the UI never sends one). Two attempts ran out. Cause: the job reviewer's rule was "blockers for material correctness or security defects", with nothing tying a blocker to the plan or the owner's threat model (finding 47's rule covered only the plan critique), and each review started fresh, so the bar moved with every version | Fixed in the P1-G proportional-job-review PR: the candidate-review prompt (`builder/review_gate.py`; not the shared reviewer role, so the plan critique keeps finding 47's rule) defines blocking (a requirement, contract or decision broken for input a user, the app's own interface or a threat inside the owner's threat model can produce; a security defect such a threat reaches; scope; missing required evidence) and makes everything else advisory; a retry's `review.json` lists `earlier_blockers` (up to 20), which the reviewer checks first |
| 51 | P1-G run 7 (19 Nov 2026, with #31–#33): every Codex job review confirmed the earlier blockers fixed, yet raised one to three new ones per version, each narrower than the last, so J_API needed 4 attempts and J_UI was not done after 4. The reviewer was never asked to report everything in one pass, as the plan critique has been since #26 (finding 45) | Fixed in the P1-G candidate-sweep PR: the candidate-review prompt asks for one complete sweep by kind (each route, command or screen with every method, field, limit, encoding and error status; failure paths; concurrency and partial writes; every in-model input; and for an interface, controls while pending or failed, keyboard and focus, and typed text), reporting every blocker now. `team/roles/reviewer.md` now defers the blocking rule to the review prompt, so the plan critique and candidate review each state their own |
| 52 | P2-G (20 Nov 2026): all 212 calls in the owner's usage ledger (`~/.local/state/vesper-relay/usage.jsonl`) came from test runs in temp folders (stand-in brains, no tokens, near-zero durations), so `vesper estimate` said "1 min" and "tokens unknown". Most test modules never set `VESPER_STATE_DIR`, so runs, ledger calls and learning went into the owner's real state | Fixed in #44: `tests/stand_in.py` points `VESPER_STATE_DIR` at a temp folder for every test process; the owner's ledger was cleaned (backup `usage.jsonl.before-p2g-cleanup`) |
| 53 | P2-G run 2b (20 Nov 2026): the seed's `delete_list` built both its SQL statements from a raw path segment, a reachable injection (`DELETE /api/lists/(3)OR(inbox=0)?rev=1` deleted every list but Inbox). The worker added the missing revision check two lines below and left it; the Claude candidate reviewer approved with no findings, its security evidence covering only the diff ("the rev value is regex-validated"). In run 2 an unreachable f-string SQL was rightly not reported. A candidate review judges the change, not reachable defects in the code it touches | Fixed in P2-T8: the review packet lists the touched definitions (`touched`), the diff shows them in full, and the candidate prompt sweeps them (a reachable in-model security defect in them blocks; otherwise an advisory). P2-G's rerun checks it with a real reviewer |
| 54 | P2-G (20 Nov 2026): plan-limit estimates can't be checked tightly yet. The first run has no band (no earlier worker calls with tokens); `/usage` shows whole points, so a weekly rise under 1 point reads 0 (run 2: 0 against 0.5–3.8%); and the assistant driving the gate spends the same Claude account, so every reading pair includes its usage and inflates the calibrated rates (run 2b: session +2 against 3.2–34.8%). Codex had no readings at all (`chatgpt` uncalibrated) | Fixed in P2-T9: readings taken with `usage record --before RUN`/`--after RUN` around each `review-plan` or `run` part are the only ones that calibrate; `approve` keeps its estimate in the run's state; `vesper --project RUN usage check` compares the run's marked rise after approval with it (inside, below, above, with one point of tolerance, or unchecked) and `status` of a complete run shows it. P2-G's rerun checks it with real readings |
| 55 | P2-G run 3 (20 Nov 2026): deciding the Codex critique's 32 blockers took 32 separate `decide --accept-risk` calls and 32 macOS dialogs, one finding each | Open: a batch `decide F1 F2 … --accept-risk` with one sheet listing every finding in full (P5-T1 connector or a P2 follow-up) |
| 56 | P2-G run 3 (20 Nov 2026): on the plan Claude's critique blocked 6 times, Codex's raised 32 blockers (11 security, 9 correctness, 9 data, 3 other), several restating the owner's accepted risks (phone mode over a wildcard bind, the plan's wording of D3). With P2-T7 this is finite: the owner accepted all 32 and the run reached `complete`. Codex's job reviews converged (J_API 8, 4, 2; J_UI 8, 5) and raised no security or data advisory, only blockers | Open: P3-T4 calibration (proportion between brains) |
| 57 | P2-G rerun (21 Nov 2026), stopped before its first run: the Codex adapter declares `usage_report=False`, so every Codex call enters the usage ledger with `tokens: None` (all 6 Codex calls of 20 Nov). `calibrate` skips a marked window holding a call without tokens, so the `chatgpt` account can never get a band, and `usage check` reports it unchecked whatever readings are taken. The rerun's estimate criterion uses a Codex reviewer and needs every account inside. The tokens exist: `codex exec --json` (in the image's codex-cli 0.170.0) prints events with per-turn usage to stdout, which the runner already logs; Vesper reads only `--output-last-message`. No run was started and no plan usage was spent | Owner (21 Nov 2026): fix first, in P2-T10; then rerun P2-G. Fixed in P2-T10 (see 58) |
| 58 | P2-T10 (21 Nov 2026): every Codex command now adds `--json`, and `Codex.usage` sums `input_tokens` and `output_tokens` over each `turn.completed` event in the call's log. The field names come from the image's codex-cli 0.170.0 binary (the serde names of its exec `Usage`: `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`, `reasoning_output_tokens`), not from a live call, so no plan usage was spent; the cached and cache-write counts are part of the input count and the reasoning count part of the output count, so only input and output are kept. A log over the 4 MB read limit is now read from its end. A Codex reply comes only from `--output-last-message`: with no reply file, a host or sandbox Codex call has no reply (reviewer, plan critique, consult, doctor), but an external `--launcher` builds its own command, so its log stays its reply. A failed Codex worker's reason keeps its agent messages, errors and plain stderr lines, not raw events | Confirmed live in the P2-G rerun (21 Nov 2026): the first Codex call (run C's critique) entered the ledger with 158,375 tokens, and all 11 Codex calls of the rerun have tokens |
| 59 | P2-G rerun (21 Nov 2026): `usage check` judges plan percentages only, and whole-point readings are coarse for small runs. R2 (one bug-fix attempt) rose 0 points on all four limits and read inside only through the one-point tolerance (claude session band 0.6–6.5%, chatgpt 0.7–4.8%). Its token counts fell below the estimate's token ranges (claude 50,306 against 60,667–331,489; chatgpt 105,012 against 158,375–378,532), and R1's Claude tokens (862,485) were just above theirs (121,334–843,224), but no check compares tokens | Open: also check the token range per account against the ledger in `usage check` (P3 follow-up) |
| 60 | P2-G rerun (21 Nov 2026): with P2-T8's touched-code sweep, Codex job reviews still raised new blockers on each job's last attempt instead of converging: run C J_API 11 then 5, J_UI 6 then 7; run R1 J_API 10 then 6, J_UI 8 then 5. Every one was a hardening edge case outside the Pocket Todo fixture's gates (HTTP parser framing, Host forms, oversize integers; UI drafts, pending controls, focus), and the owner accepted all 23. The single-attempt bug fix (R2) gave no blockers | Open: fold into the fixture's gates with P3-T3; proportion between brains with P3-T4 (finding 56) |

What worked and must be kept: plan digests, scope enforcement, the final full-gate rerun,
export, the Claude adapter flags, and reviewers that traced every fetch against the
server and found real issues (a stale-state path, the CSRF hole, 320 px not covered).

## 3. Known gaps not yet scheduled (phase 6+)

| Gap | Note |
| --- | --- |
| Amendable plans | Beyond additive checks: versioned contracts with delta approvals for changing scope mid-project |
| Parallel writers | One writer at a time today; independent jobs on disjoint paths could run in parallel |
| Shared-file ownership | Routes, schema, migrations, `package.json` touched by many jobs; needs a shared-file protocol or integration job |
| Copy and hash cost | Every attempt copies and hashes the whole tree several times; slow for large repos |
| Services in gates | Postgres, Redis or queues started for checks (compose-style) so approved architecture can be verified |
| Secrets for built apps | A way to give apps API keys during checks without exposing them to workers |
| Git breadth | Submodules, symlinks, LFS, branch and PR flow (today: patch applied to the working tree) |
| Proxy-aware adapters | Pass HTTPS_PROXY/NO_PROXY/CA variables into the sandbox (finding 9) |
| Kind-3 brains | Raw model APIs and local models (Ollama, OpenRouter, vendor APIs) through a built-in agent loop |
| Optimise mode | Like bug mode: benchmark the slowness, freeze it as a failing gate, fix, show before/after |
| Performance budgets | Beyond Core Web Vitals: API latency at load, query counts per request, bundle budgets as gates |
| Infrastructure skills | Cache, queue, CDN/HTTP caching and realtime skills with pass conditions, plus runnable services |
| Remote connector and service | Local connector is in P5-T1; remote access, service mode and the dashboard come after v1.0 (see appendix C) |
| Confirmers that authenticate | P2-T2's `tty` and `macos-dialog` confirmers make a protected action a deliberate human act, but an AI controlling the machine could open a pseudo-terminal and type the shown code, or script the dialog. Real authentication (Touch ID through LocalAuthentication, a passkey, or a confirmation on another device) needs more than the standard library; revisit with the connector (P5-T1) and the dashboard |

## 4. Commit b7da4d1 (17 Nov 2026), made outside this plan

"Enforce managed handoffs and verify Vesper Relay workflows": 28 files, about 1,200 lines.
Verified here: 41 tests pass; repo-fix, stockroom and the new repair replay pass;
`verify-facts.sh` passes.

| Change | Effect on this plan |
| --- | --- |
| `builder/planning.py`: impact-based depth (`full`/`focused`/`skip`), tech-lead architecture handoff, canonical contract acknowledged by engineers and QA, independent `review-plan` critique required before `approve` | Adopted as the plan's depth vocabulary; P2-T5, P4-T6, P4-T7 shrink to what's left |
| `review_plan` reuses `decode_provider_report`, a 180 s timeout and claude/codex-only providers | Same weaknesses as candidate review: covered in P1-T1, P1-T2 (plan critique schema), P1-T3, P1-T8 |
| Session identities in plan critiques are self-declared ("not authentication against a malicious operator") | Attesting independence becomes a protected human action in P2-T2 |
| Repair: `--failure-id` and typed `VESPER_REPRO` evidence; `VESPER_REGRESSION` timeout 120 → 300 s; `examples/replay_repair.py` | The automatic repair loop (P5-T3) generates failure IDs and typed reproducers; README checks include the repair replay |
| `examples/specialist_evals/`: specialist-vs-control trials, blind grader, 8/10 target, Codex CLI only | Becomes the per-role section of the P5-T4 bench, run through brain adapters |
| Skill updates (discovery, frontend races and replays, focus after errors, idempotency for SQLite/Postgres) | Keep; phase-4 rewrites must preserve these points |
| Stockroom server skips reverse DNS on loopback (fixed a macOS readiness timeout) | Mac lesson: local servers in gates should bind a numeric address and avoid name lookups |
| The commit's own plan notes host Python 3.9.6 (macOS default) while 3.11+ is required | Covered by SETUP: install a newer Python |
| The fixture predated managed planning and failed `review` | Fixture updated (planning.json, api-contract.md, intake planning_version) |

Housekeeping outside the board (branch `plan/dev-setup`): `scripts/dev-setup.sh` creates a
project `.venv` on Python 3.11+ (Homebrew `python@3.12` on a Mac if none is found; never
sudo), ignores it in Git, and reports go/node/pnpm/docker for later tasks. Documented
commands and `verify-facts.sh` now call `.venv/bin/python3`, and a Claude Code
SessionStart hook runs `dev-setup.sh --check`. The runner is unchanged; users get a
Python 3.11+ without a venv through P1-T11 step 3.

## Gate P1-G — 2026-11-19 00:54

Result: **FAILED** on three criteria. (1) The Codex plan critique never approved the
Pocket Todo plan in five rounds. (2) With Codex reviewing every job (run 4), J_API was
never accepted in five attempts, three of them granted by hand, because a retry starts
from scratch and is told only the last failure (finding 48). (3) Two plan-critique replies
were rejected on their first reply for citing a folder (finding 41, fixed by #22); every
reply after #22 parsed the first time. Run 2 (Claude only) met every other criterion.

Setup: owner's Mac (macOS 15, Docker Desktop), sandbox image `vesper-sandbox:acbcacc59f3b`,
Claude Code and codex-cli 0.170.0, `vesper setup` (one brain for every role) and
`vesper doctor` clean. Fixture `fixtures/pocket-todo/` copied into each run as the
procedure says.

### Runs

| Run | Vesper commit | Plan | Plan critique | Job reviewer | Result |
| --- | --- | --- | --- | --- | --- |
| 2 | `bd81422` (gate branch) | as at gate start, plus `1170ae9` | Claude: approve, 0 blockers (before #22) | Claude | `complete`, 11 min 08 s (04:28:40Z to 04:39:48Z) |
| 3 | gate-branch head of each round: `bd81422` (round 1's rejected reply), `e850b81` (round 1 after #22, #23), `dc01eb5` (round 2), then `5ecaf55` to `bdfc6bc` (rounds 3–5) | rounds 1–5 | Codex: never approved | (not run) | stopped at the critique |
| 4 | `dc01eb5` | round 2 (`957144b`), digest `b9490de1…74a` | Claude: approve, 0 blockers, 4 advisories | Codex | `blocked` at J_API after 5 attempts (2 + 3 owner-approved `retry` grants), 27 min 19 s (12:51:23Z to 13:18:42Z) |

Run 4 uses `dc01eb5` because round 2's plan predates the role revisions in #26–#28;
`dc01eb5`'s build, review and export code is the same as `dev`'s.

### Criteria

| Criterion | Result | Evidence |
| --- | --- | --- |
| Status `complete` with no manual step | Pass (run 2); **fail** (run 4) | Run 2: J_API and J_UI accepted; J_UI's first worker attempt hit `ERR_PROXY_TUNNEL` and the runner's retry was accepted unattended (finding 42). Run 4: **fail**, table below |
| Every review parsed the first time | **Fail**, then fixed | Two plan-critique replies were rejected for citing a folder: Claude's `seed/` (run 1) and Codex's `plan/` (run 3, at `bd81422`), each spending one of the packet's 3 attempts (finding 41). After #22 every plan critique (rounds 1–5, both brains) and every job review (run 2 with Claude, run 4 with Codex) parsed on its first reply. Run 2's two job reviews (J_API, J_UI) parsed the first time before #22 too |
| The exported app starts and its three gates pass | Pass (run 2) | `export /tmp/pocket-todo-app`; `server.py --db … --port …` printed `READY`; `/health` 200; G_API, G_UI, G_BROWSER exit 0 in the sandbox image against the export. Run 4 never reached export |
| `selftest.sh` passes | Pass | `sh sandbox/selftest.sh` (docker) at `bd81422` and again at `bdfc6bc`: every escape attempt failed; loopback ok |
| Repeat with Codex as reviewer | **Fail** | Codex as the plan critic never approved (critique rounds below); with Codex as the job reviewer the build never completed (run 4 attempts below) |
| Elapsed time and plan usage recorded | Recorded | Below |

### Run 4 attempts (J_API, Claude worker, Codex reviewer)

| # | Brief told it | G_API | Codex review | Outcome |
| --- | --- | --- | --- | --- |
| 1 | the plan | pass | 3 blocking: ids can be reused (the round-2 plan never forbade it; the later fixture adds C3), the reply is read after the commit so another device's delete in between gives 404 or 500, and a 64-bit-overflow `listId` or an unpaired surrogate gives 500 not 400 | rejected |
| 2 | attempt 1's 3 blockers | fail: `inbox` returned as `1`, not `true` (`api.py:71`) | — | rejected |
| 3 (grant 1) | attempt 2's gate failure only | pass | 4 blocking: the same three again, plus the Host check it had called advisory in attempt 1 | rejected |
| 4 (grant 2) | attempt 3's 4 blockers | — | — | worker timed out at 600 s |
| 5 (grant 3) | attempt 4's timeout only | fail: `inbox` as `1` again | — | rejected |

Every attempt rewrote `server.py` from the empty base, and each brief carried only the
previous attempt's reason (`builder/runner.py:370`), so each fix undid the one before
(finding 48). Codex's job reviews parsed the first time and cited lines; its blockers are
real gaps, not noise.

### Plan critique rounds

Blocking findings per critique, from each `review-plan` reply (the round's plan fixes are
the commit named).

| Round | Plan | Claude | Codex |
| --- | --- | --- | --- |
| 1 | gate start (`185bc9c`), then `1170ae9` | 2 blocking, fixed in `1170ae9`; one reply rejected for citing `seed/` (finding 41); then approve | 4 blocking (3 on the plan, 1 the `planning.json` revision, finding 44) |
| 2 | `957144b` | approve, 0 blocking | 3 blocking |
| 3 | `1be6931`, `68fbafc` (sweep by kind, #26) | 8 blocking | timed out at 180 s (finding 46, #27) |
| 4 | `1f4da89` | 3 blocking | 23 blocking (finding 47, #28) |
| 5 | `d31c8a2` (proportionality, threat model) | 6 blocking | 30 blocking |

Claude's critique stays in single figures and approved twice; Codex's grows with each
round even after the blocker rule and the owner's threat model (#28). Round 5's 30 split
evenly between the gates (15) and the plan (15), and many are out of proportion for a
one-person local app: VPN and bridged interfaces, power loss mid-commit, a lock held over
five seconds, a label element with no text.
The plan cannot reach a Codex approval by patching findings one at a time, so this is
recorded as the failed criterion rather than a sixth round.

### Fixed during the gate (all merged into `dev`)

| PR | Fix | Finding |
| --- | --- | --- |
| #19 | Plain-language approval sheet added to P2-T2 | — |
| #20 | Python Playwright in the sandbox image; run the resolved image ID | — |
| #21 | `VESPER_REGRESSION` defaults to 900 s | — |
| #22 | A plan-critique finding cites one listed file, never a folder | 41 |
| #23 | A sandboxed Codex reviewer runs under `danger-full-access` | 43 |
| #24 | The egress proxy's log is kept beside the job's log | 42 |
| #25 | The critique prompt explains `planning.json`'s revision | 44 |
| #26 | Plan creation sweeps each risk kind; the critique blocks by a stated rule | 45 |
| #27 | `review-plan` defaults to 600 s and says when it timed out | 46 |
| #28 | Gaps block only for plausible mistakes; security inside the owner's threat model | 47 |

The Pocket Todo fixture was revised alongside (canonical contract, reachability and
concurrent-change lists, failure-path matrix, threat model, rewritten `checks/api.py` and
`checks/browser.py`). The rewritten gates were mutation-tested: a reference app passes,
and each broken variant fails at the assertion named for it in `acceptance.md`. The
reference app is now `fixtures/pocket-todo/reference/`, the known-good candidate for
P3-T3; `solution/` stays the 9 Nov app, which fails the revised checks.

### Time and usage

- Start 2026-11-19 00:54 IST, end 2026-11-19 18:53 IST: about 18 h of wall time, including
  ten PRs, five critique rounds and a pause at the session usage limit.
- Plan usage before: session 2%, weekly 37%. After: session 41% (the session window reset
  during the gate), weekly 60%: the gate used about 23 points of the weekly limit.

### Follow-ups

- **Codex plan critique convergence (blocks P1-G):** decide in Phase 2 how a critique
  converges: for example P2-T5's required sections checked by the runner first, the
  critique limited to gaps against those sections, and an owner-confirmed "accepted risk"
  outcome per finding (P2-T7's decision gate) instead of rounds of plan edits. Then
  rerun the Codex critique on the current fixture.
- **Retries that remember (blocks P1-G):** a retry should start from the last candidate
  that passed its gates, not the empty base, and its brief should carry every earlier
  reason for the job (review blockers and gate failures), not only the last. Give workers
  the job's gate scripts to run (P2-T1 gives them to reviewers). Then rerun run 4 on the
  current fixture. Finding 48.
- P2-T5: test that the approval sheet lists every proposed risk and the threat model.
- Codex as a consultant inside the sandbox still cannot run commands (finding 43).
- The cause of run 2's `ERR_PROXY_TUNNEL` is open until it recurs with the proxy log
  (finding 42).

### After the gate: Codex job-review runs 5–7 (19 Nov 2026)

The owner asked to fix what run 4 showed was Vesper's fault and rerun the Codex-reviewed
build. Each run used round 2's plan (the one Claude approved, file for file as run 4), a
fresh Claude plan critique (approve, 0 blocking, 6 advisories each time), the owner's
approval, and `run --reviewer-brain codex`. Vesper was `dc01eb5` (which accepts round 2's
planning roles) with `builder/runner.py`, `builder/providers.py` and `builder/review_gate.py`
from the fixes below, the same build and review code as `dev` at `08feedb`. The P1-G result
above is unchanged: these runs are not a gate rerun.

| Run | Fixes in | J_API | J_UI | Result |
| --- | --- | --- | --- | --- |
| 5 | #31 | 1: G_API pass, Codex 3 blocking. 2: started from 1, fixed all 3, passed G_API in its own run, rejected unchecked for `__pycache__` (finding 49) | — | `blocked`, 2 min 10 s |
| 6 | #31, #32 | 1: Codex 3 blocking. 2: started from 1, fixed all 3, G_API pass, Codex 2 new blocking (an invalid IPv4 Host such as `999.0.0.1` accepted, with unsupported methods answered 501 before the Host check; an invalid delete name answered 409; finding 50) | — | `blocked`, 3 min 15 s |
| 7 | #31, #32, #33 | blocking per attempt 3, 1, 1, 0: accepted on attempt 4 | blocking per attempt 3, 3, 2, 1; G_API, G_UI and G_BROWSER passed on all four | `blocked` at J_UI after 4 owner-approved `retry` grants (2 per job), about 11 min of runtime |

In run 7 every review listed `earlier_blockers` and confirmed each one fixed, and no
attempt regressed: retries now converge. Each new blocker was real under the stated rule
but narrower than the last: on J_API a stalled upload holding the write lock, then
`OPTIONS` with a foreign Host answered 501 instead of 403; on J_UI stale rows after a
failed filter change, dropped checkbox actions, length checks in UTF-16 units, an unsaved
checkbox left ticked, a new-list draft erased, and finally browser trimming of pasted
U+0085 and U+FEFF that differs from Python's `str.strip()`. The round-2 gates assert none
of these; the current fixture's gates assert the route-wide Host refusals, which workers
can now run themselves.

| PR | Fix | Finding |
| --- | --- | --- |
| #31 | A retry starts from the job's last checked candidate, its brief lists every earlier failure, and workers get a read-only copy of their gates (owner decision in `00-context.md`) | 48 |
| #32 | `verify` removes `__pycache__` folders a worker's own runs leave | 49 |
| #33 | Candidate review states a blocker rule (plan, contract or decision broken for input a user, the app or an in-model threat can produce; in-model security; scope; missing evidence) and a retry's reviewer checks `earlier_blockers` first | 50 |

Follow-ups from these runs:

- **Attempts needed under Codex review:** J_API was accepted on attempt 4 and J_UI still had
  one blocker after 4, against a plan whose gates leave contract clauses untested; the plan
  gave 2. Either the planner sets a larger budget when
  the reviewer is strict, or the candidate review sweeps each kind of defect in one pass
  (as the plan critique does since #26), so it reports what it would otherwise find one
  version at a time. Decide before rerunning P1-G.
- **Gates that cover the contract:** most of the new blockers were contract clauses no
  gate asserts. The current fixture closes several; P1-G should rerun on it once its plan
  critique converges (first follow-up above).
- `team/roles/reviewer.md` still says "use blockers for material correctness or security
  defects", which the plan critique shares; the candidate prompt's rule follows it and is
  more specific. Align the wording when the role next changes.

### Re-scoped by the owner (19 Nov 2026): PASSED

The owner chose to pass Phase 1 on one brain and move the Codex repeat to P2-G, after
P2-T5 (required plan sections, including the threat model) and P2-T7, widened so that every
plan-critique blocker and every job-review blocker left when attempts run out ends in the
owner's decision (fix it, or accept it as a risk with a reason). Both decisions are in
`00-context.md`. On the re-scoped criteria, run 2 (Claude for every role, `bd81422`) passes:

| Criterion | Result | Evidence (run 2) |
| --- | --- | --- |
| Status `complete` with no manual step | Pass | J_API accepted on its first attempt; J_UI's first worker attempt hit `ERR_PROXY_TUNNEL` and the runner's own retry, inside the job's budget, was accepted (finding 42). 11 min 08 s |
| Every review parsed the first time | Pass | Its plan critique and both job reviews (J_API, J_UI) parsed on their first reply. Outside run 2, run 1's Claude critique reply was rejected for citing `seed/` before #22 (finding 41); every reply after #22 parsed the first time |
| The exported app starts and its three gates pass | Pass | `READY`, `/health` 200; G_API, G_UI, G_BROWSER exit 0 in the sandbox image |
| `selftest.sh` passes | Pass | At `bd81422` and again at `bdfc6bc` |
| Repeat with Codex as reviewer | Moved to P2-G | Runs 3–7 above are its evidence so far |

Limits: run 2 tested `bd81422`. The runner changes since (#22–#35) are covered by the test
suite, the three replays and CI, and runs 5–7 exercised the build and review code end to
end with Codex; no Claude-only run has been repeated on today's `dev`, because round 2's
plan predates the current planning roles and the current fixture's plan has not yet
passed a critique. P2-G's runs exercise both. The follow-ups above marked "blocks P1-G"
now block P2-G.

## Gate P2-G — 2026-11-20 18:56

Result: **FAILED** on two criteria. (1) No real reviewer raised the seeded security advisory,
so "a seeded security advisory blocks acceptance until decided" was never exercised outside
the tests (finding 53). (2) Estimates did not land inside their band on two consecutive
runs: run 1 had no band and runs 2 and 2b each had one figure just below its band (finding
54). Every other criterion passed, including the Codex-reviewed Pocket Todo run, which
reached `complete` with every blocker and every security or data advisory decided by the
owner.

Setup: owner's Mac (macOS 15, Docker Desktop 29.2.0), sandbox image
`vesper-sandbox:acbcacc59f3b` (rebuilt at gate start: `doctor` found it listed but missing),
`vesper doctor` clean for Claude Code and, with a Codex-reviewer config, for codex. Runner
code: `dev` at `3b980ea` (the runs started at `4754bc5`; #44, merged during the gate, changed
only tests). Approvals through `[approvals] confirmer = "macos-dialog"` (set at the gate's
start by the owner's choice; kept). The owner's reserve was set to 0 during the gate after
the first `paused_for_limits` (owner's choice) and restored to 25 at the end. Run 3 used
`[brains.reviewer] use = "codex"` through a copy of the config (`VESPER_CONFIG`).

### Runs

| Run | What | Plan critique | Jobs | Result |
| --- | --- | --- | --- | --- |
| 1 | Pocket Todo fixture, Claude for every role | Claude: request_changes, 6 blockers (F1–F6, gate gaps; owner accepted each), 15 advisories (11 security or data, accepted by the plan approval) | J_API: attempt 1, 1 blocker returned automatically; attempt 2 accepted. Paused before J_UI (`paused_for_limits`, projected 97.1% of the week against the 75% reserve line). J_UI: accepted first attempt | `complete`; build 4 min 46 s (13:46:50–13:49:26Z, 13:50:45–13:52:55Z) |
| 2 | Bug fix on the reference app (stale list delete; f-string SQL seeded, unreachable) | none (`skip` depth) | J_FIX accepted first attempt, no findings | `complete`, 35 s |
| 2b | Same bug, seed with a reachable SQL injection in `delete_list` | none (`skip` depth) | J_FIX accepted first attempt, no findings (finding 53) | `complete`, 30 s |
| 3 | Pocket Todo fixture, Claude workers, Codex reviewer | Codex: request_changes, 32 blockers (owner accepted all), 12 advisories (11 security or data, accepted by the approval) | J_API: 8 blockers returned; 4 at out-of-attempts, owner `--fix` (one more attempt); 2 at out-of-attempts, owner accepted (F57, F58). Paused before J_UI (projected 102.4%; a fresh reading showed 94%). J_UI: 8 returned; 5 at out-of-attempts, owner accepted (F68–F72) | `complete`; critique 6 min 50 s, build 13 min 29 s of runtime |

### Criteria

| Criterion | Result | Evidence |
| --- | --- | --- |
| Estimates land inside their band (two consecutive runs) | **Fail** | Table below. Run 1: no band (no earlier worker calls with tokens). Run 2: session in, weekly below. Run 2b: session below, weekly in. Run 3: both in for Claude; Codex uncalibrated |
| A seeded security advisory blocks acceptance until decided | **Fail (not exercised)** | Run 2's seed was unreachable and rightly unreported; run 2b's reachable injection was missed (finding 53); Codex's job reviews raised blockers only. The decision path itself worked on blockers (below) and is covered by `tests/test_decisions.py` |
| A plan missing a required section is refused at `review` | Pass | Run 1 without `threat_model`, runs 2 and 2b without `estimate`, run 3 without `failure_paths`: each refused with exit 2, naming the section |
| An AI-issued `approve` without human confirmation is refused | Pass | In runs 1, 2, 2b and 3 the assistant ran `approve --digest` with the `tty` confirmer from its own tool call: "Approving this plan needs a human at a terminal…", exit 2, no `state.json`. The owner then approved each in the macOS dialog |
| Codex run reaches `complete` with every blocker and security or data advisory fixed or decided by the owner | Pass | Run 3 backlog: 32 plan blockers accepted (32 dialogs); 11 critique advisories accepted by the confirmed plan approval; job reviews: 16 blockers returned and fixed by retries, 4 sent back by the owner, 7 accepted; 0 awaiting |
| Every review parses the first time | Pass | Plan critiques: run 1 (Claude) and run 3 (Codex) each on attempt 1, no rejected reply kept. Job reviews: 3 Claude (run 1), 1 each (runs 2, 2b), 5 Codex (run 3), all decoded on their first reply |
| The exported app's three gates pass | Pass | Runs 1 and 3: `export`, then G_API, G_UI and G_BROWSER through `execute_check` in the docker sandbox image, each exit 0 with inputs intact |

### Estimates against observed usage (Claude account)

| Run | Estimate at approval | Readings (session / week) | Observed rise | In band? |
| --- | --- | --- | --- | --- |
| 1 | 5–9 calls, tokens unknown, uncalibrated | 2 / 91 → 19 / 93 | +17 / +2 | no band |
| 2 | session 4.3–18.4%, weekly 0.5–3.8% | 19 / 93 → 25 / 93 | +6 / +0 | session yes, weekly no |
| 2b | session 3.2–34.8%, weekly 0.0–3.8% | 25 / 93 → 27 / 94 | +2 / +1 | session no, weekly yes |
| 3 | session 2.4–33.2%, weekly 0.0–6.5% | 27 / 94 → 46 / 95 | +19 / +1 | yes / yes |

Every reading also includes the assistant session that drove the gate (same account).

### Fixed during the gate (merged into `dev`)

| PR | Fix | Finding |
| --- | --- | --- |
| #44 | Tests keep runs and the usage ledger in a temp folder | 52 |

### Time and usage

- Start 2026-11-20 18:56 IST, end 2026-11-20 20:14 IST: 1 h 18 min, including one test-isolation PR.
- Plan usage before: session 61%, weekly 90%. After: session 46% (the 5-hour window reset during
  the gate), weekly 95%: the gate used about 5 points of the weekly limit.

### Follow-ups

- **Reviewer coverage (blocks the seeded-advisory criterion):** candidate reviews should
  report a reachable defect in the code a change touches, not only in the diff (finding 53,
  now P2-T8). Then rerun the seeded bug-fix run.
- **Estimates (blocks the estimate criterion):** separate the host assistant's own usage from
  Vesper's calls, accept a band edge within one reading step, and add a way to log ChatGPT
  readings; then rerun two consecutive runs with readings around each (finding 54, now P2-T9).
- Pocket Todo fixture gaps the critiques identified and the owner accepted (run 1 F1–F6, run 3
  F1–F32; job blockers F57, F58, F68–F72): fold into the fixture's gates with P3-T3.
- Batch acceptance with one sheet (finding 55); critique proportion between brains (finding 56).


## Gate P2-G — 2026-11-21 01:43

Result: **PASSED.** This rerun covered only the two criteria the 20 Nov run failed (phase-2
file, "Rerun"); the other five passed on 20 Nov and stand. (1) Seeded advisory: with one
attempt, Codex reported the reachable SQL injection in `delete_list` as a security
advisory, and the run waited in `awaiting_decision` until the owner's `decide`. (2)
Estimates: after calibration run C, the next two runs (R1 Pocket Todo, then R2 bug fix) read
inside on every account and limit in `vesper usage check`.

Setup: owner's Mac, sandbox image `vesper-sandbox:acbcacc59f3b` (codex-cli 0.170.0, Claude
Code 2.1.327). Runner code: `dev` at `16f9eef` (P2-T10 merged). Every run used Claude
workers and a Codex reviewer through a copy of the owner's config
(`[brains.reviewer] use = "codex"`, `reserve_percent = 0`, the owner's choice for the gate;
the owner's own config kept 25), passed with `VESPER_CONFIG`. Approvals and decisions went
through the macOS-dialog confirmer. Readings came from the owner's `/usage`, recorded with
`vesper usage record --before|--after RUN` right before and after each `review-plan` or
`run` part. The assistant stayed idle while each part ran.

### Runs

| Run | What | Plan critique | Jobs | Result |
| --- | --- | --- | --- | --- |
| C (calibration) | Pocket Todo fixture (run 3's plan, checks and empty seed) | Codex: request_changes, 32 blockers (owner accepted all), 10 advisories; 158,375 tokens; 3 min 17 s | J_API: 11 blockers returned, then 5 blockers and 1 data advisory at out-of-attempts (F57–F62, owner accepted). J_UI: 6 returned, then 7 (F71–F77, owner accepted) | `complete`; build 5 min 28 s + 7 min 54 s |
| R1 (checked) | Pocket Todo fixture, same plan as C | Codex: request_changes, 28 blockers (owner accepted all), 10 advisories; 274,966 tokens; 3 min 10 s | J_API: 10 returned, then 6 (F49–F54, owner accepted). J_UI: 8 returned, then 5 (F66–F70, owner accepted) | `complete`; build 5 min 16 s + 7 min 28 s |
| R2 (checked) | Bug fix on the run-2b seed (stale list delete; reachable SQL injection in `delete_list`), J_FIX `max_attempts: 1` | none (`skip` depth) | J_FIX: no blocker; F1 security advisory (injection, awaiting decision; owner accepted), F2 correctness advisory (noted) | `complete`; 1 min 2 s |

### Criteria

| Criterion | Result | Evidence |
| --- | --- | --- |
| Seeded advisory: the review reports the injection as a security advisory and acceptance waits for the owner's `decide` | **Pass** | R2, attempt `e4d6bf0f`: F1 `severity: advisory`, `category: security`, `server.py`: "Lines 130 and 137 interpolate list_id into SQL. Lines 265–274 pass nonnumeric route IDs through to delete_list. A direct client that can reach the API can supply SQL syntax in the ID and alter row selection, risking deletion of stored lists and cascading todo loss … requests from other websites … are blocked on this route under D3." `run` exited 1 with status `awaiting_decision` ("waiting for the owner's decision on F1"). After `decide F1 --accept-risk` (macOS dialog) the run reached `complete` |
| Estimates: two consecutive runs whose estimates come from marked readings only, inside for every account and limit | **Pass** | Table below. R1 and R2 approved estimates with bands from marked pairs only (P2-T9); `usage check` gave `inside` for claude and chatgpt, session and week, on both runs |

### Estimates against observed usage

Readings are session / week in whole points, from the owner's `/usage`.

| Run | Part | claude | chatgpt |
| --- | --- | --- | --- |
| C | critique | 28 / 8 → 29 / 8 | 1 / 51 → 3 / 52 |
| C | J_API | 30 / 8 → 0 / 9 (session reset) | 3 / 52 → 0 / 52 (session reset) |
| C | J_UI | 0 / 9 → 7 / 10 | 0 / 52 → 3 / 53 |
| R1 | critique | 8 / 10 → 8 / 10 | 3 / 53 → 6 / 53 |
| R1 | J_API | 9 / 10 → 13 / 10 | 6 / 53 → 9 / 53 |
| R1 | J_UI | 14 / 10 → 19 / 11 | 9 / 53 → 12 / 54 |
| R2 | J_FIX | 20 / 11 → 20 / 11 | 12 / 54 → 12 / 54 |

C's J_API "after" pair was taken about 7¾ hours after that part ended (02:04 to 09:48 IST,
an overnight pause), so its weekly +1 for claude may include other use. Both sessions reset
inside the part, which gives no session sample (`usage check` on C: session `unchecked`,
"the window reset inside a bracketed part").

| Run | Limit | Approved band | Observed rise (marked parts after approval) | `usage check` |
| --- | --- | --- | --- | --- |
| R1 | claude session | 2.4–16.5% | +9 (2 parts) | inside |
| R1 | claude week | 0.3–2.9% | +1 | inside |
| R1 | chatgpt session | 1.4–19.1% | +6 | inside |
| R1 | chatgpt week | 0.0–9.6% | +1 | inside |
| R2 | claude session | 0.6–6.5% | 0 (1 part) | inside (one-point tolerance) |
| R2 | claude week | 0.0–1.1% | 0 | inside |
| R2 | chatgpt session | 0.7–4.8% | 0 | inside (one-point tolerance) |
| R2 | chatgpt week | 0.0–2.4% | 0 | inside |

R1's estimate was built from 2 calibrated Claude runs and 3 ChatGPT runs (confidence low).
R2's came from 4 and 6 (low and medium). Ledger tokens per run: C claude 649,910, chatgpt
1,343,315; R1 claude 862,485, chatgpt 1,310,578; R2 claude 50,306, chatgpt 105,012. R1's
Claude total fell just above, and both of R2's below, the estimate's token ranges, which no
check compares (finding 59).

### Fixed before the rerun (merged into `dev`)

| PR | Fix | Finding |
| --- | --- | --- |
| #50 | Marked readings and `usage check` (P2-T9) | 54 |
| #49 | Candidate reviews sweep the code a change touches (P2-T8) | 53 |
| #52 | Codex reports its token counts (P2-T10), confirmed live in this rerun | 57, 58 |

### Time and usage

- Start 2026-11-21 01:43 IST (gate branch), end 2026-11-21 10:48 IST: 9 h 5 min, of which
  about 7¾ h was the overnight pause after C's J_API part. Brain runtime was 33 min 35 s.
- Plan usage before: claude session 28%, weekly 8%; chatgpt session 1%, weekly 51%. After:
  claude session 22%, weekly 11%; chatgpt session 12%, weekly 54% (both 5-hour windows reset
  once). The gate used about 3 weekly points on each account.

### Follow-ups

- Decided findings to fold into the Pocket Todo fixture's gates with P3-T3: C critique
  F1–F32, C jobs F57–F62 and F71–F77; R1 critique F1–F28, R1 jobs F49–F54 and F66–F70.
- R2's F1 (accepted: reachable only by callers trusted under D3, out of J_FIX's scope):
  parameterize the `list_id` queries in a separate change to the reference app.
- Check token ranges too, and tell a 0-point rise on a small run from a sample (finding 59).
- Codex job reviews still don't converge in two attempts (finding 60); batch decisions are
  still one dialog per finding, 85 this rerun (finding 55).
