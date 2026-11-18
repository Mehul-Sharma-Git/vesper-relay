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
| 21 | P1-T5: `validate_repair` (`builder/repair.py`) reads `item["script"]` for every check, so a repair contract that contains a command gate stops with a `KeyError` instead of a clean "Repair requires…" error. The contract is still refused, so nothing unsafe runs; left out because `builder/repair.py` is outside P1-T5's scope (`validate_maintenance` in `builder/contracts.py` was fixed to use `.get`). Still open after P1-T6, which also leaves `builder/repair.py` alone; it only adds the earlier "Vesper repairs cannot run build setup" refusal. A one-line `.get` fix needs the owner's OK to touch `builder/repair.py` | unscheduled |
| 22 | P1-T5: without a launcher, a command gate's program is found on the runner's own `PATH`, and the gate's `PATH` is only that program's directory plus `/bin:/usr/bin`. A tool that needs a sibling from another directory (for example `pnpm` from a version manager calling `node` elsewhere) won't find it. Each gate also starts with an empty `GOCACHE`, so a first `go test` compiles the standard library again (about 15 s per gate on an M-series Mac). Shared caches and sandbox `PATH` belong to the setup step and the sandbox | P1-T6, P1-T9 |
| 23 | P1-T6 (18 Nov 2026, pnpm 12.21 via corepack, macOS): `pnpm install --frozen-lockfile` *writes* `pnpm-lock.yaml` when none exists (zero-dependency project), so setup's "tracked files unchanged" rule fails until the lockfile is committed. Corepack also downloads pnpm itself into the setup's temporary `HOME` on every run, so even a zero-dependency setup needs network; a sandbox image with pnpm preinstalled (or a cached `COREPACK_HOME`) avoids it. pnpm 12 ignores both `PNPM_STORE_DIR` and `npm_config_store_dir` (only `pnpm_config_store_dir` moves the store) and, on macOS, falls back to the real `~/Library/pnpm/store`, outside the run; the runner sets all three (found by the independent review of PR #12) | P1-T9, P5-T2 |
| 24 | P1-T6: only the dependency caches (`GOMODCACHE`, pnpm store) are shared across verifications, in `<run>/.builder/cache/`; `GOCACHE` stays per gate (finding 22). Without a launcher, command gates can write to that shared cache like any host process; a launcher must mount it read-only for `check-command` (START-HERE launcher table). Each command gate gets its own copy of the setup's `node_modules`, which costs a copy per gate on large installs | P1-T9 |

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
