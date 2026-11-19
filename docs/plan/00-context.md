# 00 — Context

Read this file before every task. It replaces the conversations that produced the plan.

## 1. What Vesper Relay is

Vesper Relay is a local workshop for AI software work. It has two parts.

| Part | What it is | Files |
| --- | --- | --- |
| Instructions | Markdown that AI agents read: the entry skill, roles, skills | `integrations/vesper-relay/SKILL.md`, `team/roles/*.md`, `team/skills/*/SKILL.md` |
| The program (runner) | Python that enforces what instructions cannot: locked plans, work on copies, scope checks, running gates, launching an independent reviewer, records, recovery, Git patches | `vesper.py`, `build_local.py`, `builder/*.py` |

The instructions say how agents should work. The program makes sure they actually did.
That split is Vesper's core value and must be preserved.

`vesper.py install` copies the entry skill into `~/.claude/skills/vesper-relay/` and
`~/.agents/skills/vesper-relay/` and creates `~/.local/bin/vesper`. Nothing runs in the
background: the assistant calls `vesper …` commands, each starts, works and exits.
Run state lives under `~/.local/state/vesper-relay/runs/`.

### Where things live in the code

| File | Responsibility |
| --- | --- |
| `vesper.py` | CLI entry: install, start, roles, consult, learn, Git delivery, repair; forwards core commands to `build_local.py` |
| `build_local.py` | Core CLI: init, brief, review, approve, prepare, submit, review-candidate, run, status, export, retry, abandon |
| `builder/contracts.py` | Contract validation, file inventories, `safe_path`, `review_bundle` (what `review` checks) |
| `builder/runner.py` | Attempts, workspaces, `execute_check` (gates), `verify`, `stage_review`, `review_candidate`, `run`, `export` |
| `builder/providers.py` | Builds Claude/Codex commands (`provider_command`), provider env, worker prompt. Replaced by brain adapters in P1-T8 |
| `builder/review_gate.py` | Review packet, reviewer prompt, `decode_provider_report`, `validate_report` |
| `builder/team.py` | Role catalogue (`PROFILES`), freezing roles into a run, `validate_design` |
| `builder/process.py` | Bounded subprocess with process-group cleanup |
| `builder/git_bridge.py` | Git baseline intake, reviewed patch, apply |
| `builder/learning.py`, `builder/playbook.py` | Local signals and promotable rules |
| `builder/planning.py` | Impact-based planning depth, architecture handoff checks, independent plan critique (`review-plan`) — added in b7da4d1 |
| `builder/repair.py`, `builder/maintenance.py` | Self-repair of Vesper's own source; typed `VESPER_REPRO` evidence with a `--failure-id` |
| `tests/` | 41 tests (all passing at `b7da4d1`, 2026-11-17) |
| `examples/` | Stockroom, repo-fix and repair replays used as end-to-end checks; `specialist_evals/` (specialist-vs-control trials with a blind grader) |

The plan was first written against commit `9d3b223` (2026-11-09) and updated for `b7da4d1`
(2026-11-17), which added impact-based planning depth, the architecture handoff, independent
plan critique, typed repair evidence and specialist evaluations. See `appendix-b`, section 4.

## 2. What the live test showed (2026-11-09)

A todo app ("Pocket Todo") was planned and built with real Claude workers. Full detail is
in `appendix-b-test-run-evidence.md`. In short:

- **Worked:** plan digests, scope checks, gates, final full-gate rerun, export. The
  Claude adapter flags work on Claude Code 2.1.321. Both jobs passed first attempt.
- **Broke:** the reviewer returned a valid approving verdict with one sentence of prose
  before a fenced JSON block, and `decode_provider_report` rejected it. This happened 2 of 3
  times and stopped automatic runs.
- **Weak:** workers can't run code ("none of it has been run"); the reviewer can't see
  gate logs; gate env is stripped and the timeout is fixed at 45 s; advisories are dropped
  (a real CSRF hole shipped as "advisory"); the UI matched the wireframe's layout but had
  a generic default look; nothing asked the owner about the tech stack.

## 3. Owner decisions (all binding)

Dates are 2026. "Owner" is the repository owner.

### Direction

| Decision | Detail |
| --- | --- |
| Keep instructions + enforcing program | Carry the split into every future feature |
| Sandbox-first releases | Vesper runs in a sandbox until it passes repeated test runs; release candidates are scored; the owner promotes, Vesper never certifies itself |
| Process proportional to risk | Planning depth from `plan/planning.json` (b7da4d1): `full` for builds and material data, security, integration or deployment impact; `focused` for cross-layer-only changes; `skip` for a justified narrow fix. These names are used everywhere in this plan |
| Plan critique | At `full` and `focused` depth an independent reviewer critiques the exact plan packet (`review-plan`) before the owner can approve; the author can't review their own plan; at most 3 critiques per packet |
| Reuse before building | Prefer existing pieces (MCP, containers, schedulers) over hand-written equivalents, except the core: plan locking, independent checks and review, approvals, audit |
| Long-term assistant direction | Recorded in `appendix-c-future-assistant.md`; not part of this plan |
| v1.0 | The first release candidate the owner promotes after phase 5. Until then, Vesper's own code is changed by an AI coding assistant following this plan; after v1.0, Vesper repairs and maintains itself through its own process (P5-T3), and the owner merges |

### Any AI as the brain

| Decision | Detail |
| --- | --- |
| Vendor-neutral core | The runner talks to brain adapters, never to a vendor. Adapters declare capabilities (edit files, run shell, strict output, model/effort choice, usage report, sandbox login) and the core adapts |
| One AI is enough | Every role can use the same AI. Reviewer independence comes from a fresh process, a read-only copy, no access to the worker's reasoning and its own checklist. A different AI for the reviewer is optional |
| v1.0 brains | Kind 1: the host assistant the user is talking to (supervised, through commands or the connector; no extra login). Kind 2: agent CLIs started in the sandbox: Claude Code, Codex CLI, Gemini CLI. Kind 3 (raw APIs and local models through a built-in agent loop) comes after v1.0 |
| Brains named by purpose | The config defines `[brains.strong]`, `[brains.fast]`, `[brains.reviewer]` etc. with `use = "<adapter>"`; roles point at those names |
| Sandbox logins | Only for automatic mode. Claude Code: token from `claude setup-token` (the Mac keeps the normal login in Keychain, which the sandbox can't reach). Others per adapter |
| The owner's own setup | Claude Pro + a ChatGPT plan; the owner will set the reviewer brain to Codex. This is the owner's config, not a requirement |

### Cost and limits

| Decision | Detail |
| --- | --- |
| No dollar estimates | Users on subscription plans (the owner: Claude Pro, ChatGPT) pay a fixed fee and have session and weekly limits. Estimates are in % of session and week per account, plus wall time |
| Reserve | Vesper must leave a user-set reserve of plan usage (suggested 25%) |

### Sandbox, config, doors, approvals, self-repair

| Decision | Detail |
| --- | --- |
| Pluggable sandbox | Backends `docker` (default), `podman`, later cloud sandboxes; `none` only as explicit opt-in for disposable machines. The sandbox runs wherever the runner runs: the user's machine for local doors; a server that can run containers for service mode (free PaaS tiers can't) |
| Platforms | Mac first (Docker Desktop or Colima), then Linux, then Windows (WSL2). Images for arm64 and amd64 |
| Supervised-mode nuance | The host assistant works under its own app's permissions; Vesper's gates and reviewers still run sandboxed |
| Config | Personal `~/.config/vesper/config.toml` + project `vesper.toml`; no secrets in either (Keychain or a mode-600 secrets file); `vesper setup` writes it; `vesper config show` explains it |
| Doors (one engine, shared runs) | v1.0: command line, skill, Claude Code plugin/marketplace, local MCP connector, uv/pipx install, sandbox image on GHCR, `vesper open`. Later: dashboard, remote connector + service, GitHub integration, Homebrew |
| Human-only approvals | The AI can never approve on the user's behalf. Plan approval, applying patches, accepting risks, adding checks after approval, merging repairs and promoting releases need a human confirmation the AI can't produce, enforced by the program in every door. Before confirming, the human sees a plain-language approval sheet (what is delivered, each promise and its proof, what each job may change, the critique verdict, what changed), never raw JSON (2026-11-19) |
| Workers see the gates | Each worker workspace holds a read-only copy of the job's approved gate scripts (`.vesper-gates/`, files without write permission), and the brief says how to run each, so a worker can run them before finishing. Vesper ignores the copy, never ships it, and always decides with its own approved gates; the independent reviewer catches a build aimed narrowly at them. A retry starts from the job's last checked candidate and its brief carries every earlier failure of the job (2026-11-19, after P1-G finding 48) |
| The owner decides on findings | Reviewers find and explain; the owner decides. Every plan-critique blocker, and every job-review blocker still open when a job's attempts run out, ends in the owner's decision: fix it (the plan goes back, or the job gets another attempt) or accept it as a risk with a reason, on a plain-language sheet. Acceptance is human-only (P2-T2) and recorded; the independent review still runs and its findings are kept. Built in P2-T7 (2026-11-19) |
| Phase 1 gate scope | P1-G passes with one brain (Claude) for every role. The repeat with Codex as reviewer moved to P2-G, after P2-T5 and P2-T7 (2026-11-19) |
| Automatic repair | Detect → sort → reproduce → plan (one-tap owner OK) → repair in the sandbox → branch or PR with evidence → owner merges. Never auto-merge. Protected safety files are off-limits. Tests may be added, never edited or removed. Weekly cap. Local after failed runs in v1.0; nightly CI after v1.0 |

### Default stack (per project the planner confirms or records an exception)

| Layer | Choice |
| --- | --- |
| Backend | Go (standard library first, OpenAPI contract, versioned migrations) |
| Frontend | React + TypeScript strict |
| Framework | Chosen by project needs (table below); Next.js only as an exception with owner OK |
| State and server data | Redux Toolkit + RTK Query everywhere; endpoints generated from the OpenAPI spec |
| Routing | React Router (data router) |
| Styling | Tailwind CSS v4, generated from designer tokens |
| Components | shadcn/ui always re-themed; Kokonut UI and Bklit UI via the shadcn registry; React Aria for complex widgets |
| Animation | Motion (React transitions), Anime.js (timelines, SVG, scroll) |
| Forms | React Hook Form + Zod |
| Tests | Go `go test`; Vitest + Testing Library + Playwright |
| Tooling | pnpm; ESLint and Prettier (or Biome) |
| Hosting | Free tiers: Go API on Render, React site on Vercel, external database |

| Kind of project | Framework |
| --- | --- |
| Landing page, portfolio | Astro + React islands |
| Content site, blog, docs | Astro (Starlight for docs) |
| Web app or dashboard behind login | Vite + React |
| SaaS: marketing + app | Astro site + Vite app on an app subdomain, or Next.js |
| Online shop | Next.js, or Astro + headless commerce |
| Real-time / collaborative | Vite app + Go WebSockets |
| Offline-first / installable | Vite PWA |
| Native mobile | Out of scope for now |

### Agents (detail in phases 3 and 4)

| Agent | Key decisions |
| --- | --- |
| All | Reasoning note, claim labels, self-critique, knowledge packs, tools inside the sandbox, top model only for judgement roles, postmortems feed checklists, per-role evaluation |
| Planner | Depth scales with job size; push back once; options memo; pre-mortem; assumption list; phases; independent plan critique (`review-plan`, done); plan-limit estimate before every approval; asks about stack and system design |
| Tech lead (System Design Engineer) | Owns the architecture handoff at `full`/`focused` depth (done in b7da4d1); simple now, scale later; component decision table (cache, queue, CDN, realtime, search, storage); decision records; library rubric; prototypes only after asking the owner; ops plan; free-hosting knowledge pack |
| Designer | Top priority. Direction brief, 3 real directions, locked design system, knowledge base, render-and-see tools, blocking design gate |
| Frontend | Builds strictly from the design system; components first in Storybook; sees its own work; writes component tests and runs browser journeys; Core Web Vitals "good" by default |
| Backend (Go) | Writes and runs its own unit tests; security baseline on every job; OpenAPI; Go quality gates; built for the host |
| QA | Owns and writes all checks; test pyramid; contract tests; prove every check can fail; mutation testing on full builds; non-functional checks; exploratory session; additive checks after approval |
| Reviewer | Schema verdicts; evidence-backed blockers; multi-lens on full builds; full inputs; security and data advisories must be decided; about 400 changed lines per job; a different AI optional; calibration |

## 4. Glossary

| Word | Meaning |
| --- | --- |
| Run / project | One Vesper job folder with plan, checks, seed, state |
| Contract | `plan/contract.json`: requirements, checks, jobs |
| Gate / check | An approved test the candidate must pass |
| Digest | Fingerprint of the exact approved plan, checks and seed |
| Candidate | A worker's proposed result, before review |
| Snapshot | An accepted version of the product |
| Launcher | The executable that runs workers, gates and reviewers inside a sandbox |
| Depth | `full`, `focused` or `skip`: how much planning process a job gets, derived from declared impacts in `plan/planning.json` |
| Plan limits | Subscription session and weekly usage caps (e.g. Claude Pro, ChatGPT) |
| Brain | An AI Vesper uses for a role, named by purpose in the config |
| Adapter | The plug that drives one kind of brain (Claude Code, Codex CLI, Gemini CLI) |
| Sandbox backend | The locked room implementation (Docker, Podman, none) |
| Door | A way of using Vesper: command line, skill, plugin, connector, dashboard, service |
| Confirmer | The mechanism that proves a human approved a protected action |
