# Phase 5 — Doors, self-repair, measurement and the v1.0 release

**Goal:** Vesper is usable from any AI app that supports connectors, installs in one step,
repairs itself up to a pull request, is measured on a fixed bench, and reaches v1.0 when
the owner promotes a release candidate.

**One engine, many doors.** All doors share the same engine and run data, so a run started
in one door can be followed in another.

| Door | v1.0 | Later |
| --- | --- | --- |
| Command line (`vesper …`) | Yes | |
| Skill (`/vesper-relay`) in AI coding assistants | Yes | |
| Claude Code plugin / marketplace | Yes (P5-T2) | |
| Local connector (MCP, stdio) | Yes (P5-T1) | |
| Python tool install (uv / pipx) | Yes (P5-T2) | |
| Sandbox image on GitHub's container registry | Yes (P5-T2) | |
| `vesper open` (plans and wireframes in the browser) | Yes (P5-T2) | |
| Full local dashboard | | After v1.0 |
| Remote connector + service mode (`vesper serve`) | | After v1.0 (needs a server that can run containers; free PaaS tiers can't) |
| GitHub integration (issue label → plan → PR) | | After v1.0 |
| Homebrew | | After v1.0 |
| Raw-API and local-model brains (kind 3) | | After v1.0 |

**v1.0 definition:** the first release candidate the owner promotes after P5-T5, against
criteria agreed before it runs.

---

## P5-T1 — Local connector (MCP server)

- **Why:** makes Vesper usable from any AI app that supports MCP connectors, not only
  coding assistants (kind 1 brains).
- **Change:** `vesper mcp` runs a standard-library MCP server over stdio (implement the
  JSON-RPC framing directly; no SDK, to keep the runner dependency-free). Tools:
  `start_run`, `list_runs`, `show_plan` (returns plan files and wireframe paths),
  `review_plan` (digest + estimate), `request_approval`, `run_next`, `status`,
  `show_backlog`, `export`. Approval tools only *request* approval; confirmation happens
  through the human confirmer (P2-T2, `mcp-elicitation` or `macos-dialog`), and the
  elicitation shows the action's plain-language approval sheet (P2-T2 item 4). Long runs return
  immediately with a run ID; `status` polls.
- **Do not:** expose any tool that confirms an approval, applies a patch or accepts a risk
  without the human confirmer; expose raw file writes.
- **Acceptance:** a JSON-RPC test client lists tools and completes a stand-in run; approval
  tools refuse without a confirmer result; an elicitation carries the action's approval
  sheet; setup instructions for Claude Code and the Claude
  desktop app in `docs/SETUP.md`.

## P5-T2 — Packaging and distribution

- **Change:**
  1. **Claude Code plugin:** `.claude-plugin/marketplace.json` at the repo root (the repo is
     its own marketplace) and a plugin folder containing the skill, the runner and a
     launcher script. Put executables in `scripts/` and reference them as
     `${CLAUDE_PLUGIN_ROOT}/scripts/vesper` (Claude Code also supports `bin/` on PATH, but
     Cowork and claude.ai don't install a top-level `bin/`). Keep run state outside the
     plugin folder (`${CLAUDE_PLUGIN_DATA}` or the normal state dir), because the plugin
     folder changes on update. Set `version` in `plugin.json` and bump it every release.
     Install: `/plugin marketplace add Mehul-Sharma-Git/vesper-relay`, then
     `/plugin install vesper-relay@<marketplace name>`.
  2. **Python tool install:** a `pyproject.toml` with no runtime dependencies and a
     `vesper` console script, so `uv tool install git+https://github.com/Mehul-Sharma-Git/vesper-relay`
     (or `pipx install …`) gives the terminal command. `vesper install-skill --for <assistant>`
     copies the skill for assistants without plugins (today's `install` behaviour).
  3. **Sandbox image:** a GitHub Actions workflow builds `sandbox/Dockerfile` for arm64 and
     amd64 and pushes it to GitHub's container registry with the release version tag;
     `vesper setup` pulls it instead of building locally.
  4. **`vesper open`:** writes a small static HTML index of the current run (plan files,
     wireframes, design directions, check results) and opens it in the default browser.
- **Acceptance:** a fresh macOS user account can install via the plugin and via `uv tool`,
  run `vesper setup` and `vesper doctor` green; the image runs on Apple Silicon and Intel.

## P5-T3 — Automatic repair loop (up to a pull request)

- **Owner decisions:** automate everything up to a ready-to-merge change; the owner always
  merges (never auto-merge); repair plans need a one-tap owner OK by default; protected
  safety files are off-limits to automatic repair; v1.0 runs the loop locally after failed
  runs, nightly CI comes after v1.0.
- **Read first:** `builder/repair.py`, `builder/maintenance.py`, `builder/learning.py`,
  `vesper.py` (`incidents`, `repair`, `repair-run`, `maintain`), `docs/RC1.md`.
- **Change:**
  1. **Detect:** every failed run, `vesper doctor` result and bench failure becomes an
     incident with a signature (failure kind + normalised message + location).
  2. **Sort:** buckets `product` (the user's app; not Vesper's job), `environment` (Docker
     down, login expired; notify with fix steps from `doctor`), `vesper-defect` (repair
     candidate). Identical signatures group into one case with a count.
  3. **Reproduce:** a triage agent writes a reproducer against a pinned copy of Vesper's
     source using the typed evidence format from b7da4d1: a `--failure-id` derived from the
     case signature, and one `VESPER_REPRO {"failure_id", "outcome", "evidence"}` line
     (`reproduced` + exit 1 on the baseline, `fixed` + exit 0 after repair; other exits for
     setup, product or provider failures). No valid reproducer → the case stays a note for
     the owner.
  4. **Plan:** draft the repair plan with allowed paths and a plan-limit estimate; ask the
     owner through the human confirmer (P2-T2).
  5. **Repair:** existing `repair-run` path in the sandbox: reproducer passes, frozen
     baseline tests and both replays pass, independent review approves.
  6. **Deliver:** a local branch `vesper/repair/<case>` with an evidence report; with
     GitHub configured, a pull request. Never merge.
  7. **Learn:** lessons become proposed rules (existing `learn` flow); the owner promotes.
  8. **Guardrails:** a `PROTECTED` list (plan digests and `review_bundle` in
     `builder/contracts.py`, scope checks and `verify` in `builder/runner.py`,
     `builder/review_gate.py`, `builder/planning.py` (plan routing and critique),
     `builder/sandbox/`, the approval and confirmer code, and `builder/repair.py` itself) that automatic repair may never touch (changes there only
     through owner-started `maintain` with an extra security-lens review); repairs may add
     tests but never edit or delete existing ones; at most 3 repair attempts per week
     (configurable), always inside the plan-usage reserve.
  9. **Knowledge refresh:** knowledge-pack files with `last_checked` older than 180 days
     produce a "re-check these facts" proposal with sources through the same flow.
- **Acceptance:** tests for signature grouping, bucket rules, refusal to edit protected
  files or existing tests, the weekly cap, and that no code path merges; an end-to-end
  stand-in where a seeded defect becomes a branch with evidence after one owner confirmation.

## P5-T4 — Evaluation bench and scorecard

- **Change:** add `bench/` with fixed projects, each a brief plus (where useful) a scripted
  owner-answer file so planning runs unattended:

  | Bench item | Exercises |
  | --- | --- |
  | `landing-bakery` | Astro site lane, designer flow, design gates |
  | `todo-app` | Pocket Todo fixture, Vite lane + Go API, full gates |
  | `crud-dashboard` | Bklit charts, RTK Query, auth, external database |
  | `repo-bugfix` | Existing Git repo, reproduce-first, patch delivery |
  | `refactor` | Behaviour-preserving change with frozen tests |
  | `npm-heavy` | Dependency setup, lockfiles, cache |
  | `hostile` | Bad worker, scope escape attempt, prompt injection in repo files, broken gate, an AI trying to self-approve |

  `vesper bench run --rc NAME` runs them in the sandbox and writes
  `bench/results/<rc>/scorecard.md` and `.json`:

  | Metric | Meaning |
  | --- | --- |
  | Unattended completion | Runs that finished with no manual step |
  | First-attempt pass rate | Jobs accepted on attempt 1 |
  | Reviewer parse failures | Must be 0 |
  | Scope violations caught | From the hostile item |
  | Sandbox escapes and self-approvals | Must be 0 |
  | Escaped defects | Bugs found after acceptance (exploratory session, owner) |
  | Security findings | Count and how they were decided |
  | Design score | From P5-T5 |
  | Time and plan usage | Wall time; plan % per account per run |

  Run the bench once per configured brain set (at minimum: one AI for every role).
- **Per-role quality:** build on `examples/specialist_evals/` (b7da4d1): matched
  specialist-vs-control trials with a separate blind grader and a target of 8/10 with no
  critical failure. Move it from `examples/` into `bench/specialists/`, and run it through
  the brain adapters (P1-T8) instead of calling Codex CLI directly. Add its per-role scores
  to the scorecard.
- **Acceptance:** a dry-run mode with stand-in brains produces a full scorecard in CI,
  including the specialist-eval section.

## P5-T5 — Design bench with blind owner rating

- **Change:** 5 fixed design briefs (bakery landing page, SaaS dashboard, portfolio, booking
  flow, pricing page). For each RC, render the result, the same brief done by the same AI
  without Vesper, and the previous RC. `vesper bench rate` shows the owner the screenshots in
  random order without labels and records a 1–5 rating. The scorecard adds the average
  rating, anti-pattern count, accessibility violations, fidelity diff and design revisions.
- **Acceptance:** the rating flow stores blind results and reveals labels only afterwards.

## P5-T6 — Release candidates, permission ladder and v1.0

- **Change:**
  1. RCs are Git tags `rc-YYYYMMDD-N` with their scorecard committed; the plugin `version`
     and image tag follow.
  2. Promotion criteria in `bench/criteria.json`, agreed with the owner before the RC runs
     (suggested start: unattended completion ≥ 90% over the bench, 0 sandbox escapes,
     0 self-approvals, 0 parser failures, design rating above the same AI without Vesper).
     `vesper bench verdict` prints pass/fail per criterion; only the owner's
     `vesper bench promote` (through the human confirmer, which first shows the release
     approval sheet from P2-T2 item 4: the candidate, its scorecard summary, each criterion
     with pass or fail) promotes. Vesper never promotes itself.
  3. Permission ladder in the personal config, one step per promoted RC:
     `sandbox-only` → `read-only real repos` → `patches with approval` →
     `limited autonomy for skip-depth jobs`.
  4. Finalise `docs/SETUP.md` from `SETUP-draft.md` with the real commands, and test it on a
     fresh macOS account.
  5. The first promoted RC after this task is tagged `v1.0.0`.
- **Acceptance:** tests that promotion is refused without the human confirmer and that the
  confirmer receives the release sheet, that the
  ladder cannot skip a step, and that `docs/SETUP.md` commands match the CLI's `--help`.
