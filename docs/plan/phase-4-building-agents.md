# Phase 4 — Agents that build (designer first)

**Goal:** the designer produces distinctive, owner-directed design that the frontend
builds faithfully; the Go backend, planner and tech lead work at a senior level with the
default stack.

**Owner's priority:** the designer is the most important agent. AI code works after
testing; design stays generic. Tasks P4-T1 to P4-T4 come first in this phase.

**Phase gate (P4-G):** two briefs (Pocket Todo again, and a bakery landing page) run
through the new flow. All design gates pass, the components-first step happens, and the
owner rates both designs above the same brief done by the same AI without Vesper.

Background for every task here: `appendix-a-research.md` sections 1 and 2.

---

## P4-T1 — Designer knowledge pack (content)

- **Why it stays generic today:** no direction from the owner; taste, exploration and
  build fused into one step; no concrete design knowledge; the designer never sees a
  render; the frontend rounds designs off; no component supply chain; no design gate.
- **Change:** write `team/knowledge/designer/` (format from P3-T2). Research at
  implementation time from the sources named; write in our own words; record
  `last_checked` and `licence`.

  | File | Contents |
  | --- | --- |
  | `typography.md` | Pairings by mood (display + body + utility), type scales, measure, which faces to avoid as defaults (Inter, Roboto, Arial as display) and when they are fine |
  | `color.md` | Palette construction (hue-biased neutrals, one accent, semantic colours), contrast rules, dark-mode pairs, palettes by product type and mood |
  | `layout-patterns.md` | Landing, pricing, feature sections, dashboards, forms, settings, onboarding, empty states; narrow and wide variants of each |
  | `motion.md` | Durations and easings by purpose, enter/exit/layout/scroll patterns, when not to animate, reduced motion, performance (transform/opacity only) |
  | `motion-library-notes.md` | Motion for React patterns (from Motion docs and its AI Kit free guidance) and Anime.js v4 API notes (models mostly know v3; use the v4 docs and migration guide) |
  | `data-viz.md` | Chart by question; dashboard density; Bklit's 14 chart types and when each fits |
  | `component-map.md` | "What fits where": UI job → source (shadcn component, Kokonut item, Bklit chart, React Aria widget, or custom), install command, licence, accessibility notes. Built from shadcn, Kokonut and Bklit `llms.txt` |
  | `anti-patterns.md` | The generic AI look, each with a detection rule for P4-T3: indigo/purple gradients, centred hero + three identical cards, stock shadcn theme, emoji icons, nested cards, grey text on colour, default fonts, `rounded-lg` everywhere |
  | `directions/` | Short playbooks by product type (local business, SaaS, portfolio, dashboard, content site): audiences, typical jobs, directions that work, traps |
  | `references.md` | How to turn owner references into a brief; Mobbin MCP use when configured; never copy a real brand |

- **Licences:** check UI/UX Pro Max and Impeccable licences before reusing their text;
  until confirmed, use them only as inspiration. Kokonut (MIT), Bklit charts (MIT),
  shadcn, Motion core (MIT), Anime.js (MIT) are fine with attribution. Bklit Studio,
  Kokonut Pro and Motion+ material is excluded.
- **Acceptance:** front matter valid; `vesper kb search --role designer "pricing page"`
  returns layout guidance; every `anti-patterns.md` entry has a machine-checkable rule or
  is marked "review only".

## P4-T2 — Designer tools and design artifacts

- **Read first:** `team/roles/designer.md`, `team/skills/interaction-design/SKILL.md`,
  `builder/team.py` (`validate_design`), `builder/contracts.py` (`review_bundle`),
  `builder/providers.py` (MCP flags), `assets/wireframes/`.
- **Change:**
  1. **Designer becomes a planning-stage writer:** `vesper --project RUN draft-design
     --brain strong` runs the designer over a copy of `plan/design/`; the owner reviews
     the result before approval (same pattern as P3-T3 `draft-checks`).
  2. **MCP per role:** today every provider call uses `--strict-mcp-config` with an
     empty server list. Allow a per-role server list from the personal config (P1-T7). The
     designer gets the shadcn MCP (`npx shadcn@latest mcp`, which also reaches Kokonut and
     Bklit registries) and Motion's AI Kit MCP (`npx motion-ai`); Mobbin MCP only if the owner
     configures it. Servers run inside the sandbox.
  3. **See the work:** `vesper render PATH_OR_URL --widths 375,1280 --themes light,dark
     --out DIR` (Playwright inside the sandbox) writes PNGs. The designer uses it on its
     mocks and on candidates.
  4. **Sketch style:** turn `assets/wireframes/build.py` into a template the designer can
     use for first-round directions. Bundle an OFL handwriting font (Caveat or Patrick
     Hand from the Google Fonts repository) with its licence file; the test-run sandbox
     could not download fonts.
  5. **Required artifacts** under `plan/design/` (validated by an extended
     `validate_design` whenever a build/design run has a frontend job):

     | File | Holds |
     | --- | --- |
     | `brief.json` | 3 adjectives, sites loved (2–3) and disliked (1), audience, must-avoid, brand assets |
     | `references/` | Owner screenshots and links |
     | `directions/<name>/` | `wireframe.html`, `mock.html`, rendered PNGs; 2–4 truly different directions |
     | `tokens.json` | W3C design-token format: colour, type scale, spacing, radius, shadow, motion |
     | `components.json` | Inventory: component → variants, sizes, states, source (`shadcn`, `kokonut`, `bklit`, `react-aria`, `custom`) |
     | `motion.json` | Interaction → duration, easing, reduced-motion fallback |
     | `screens/<screen>.html` | Hi-fi mocks with `data-region` ids for the chosen direction |

     The chosen direction must exist; directions must differ in composition, not just colour
     (keep today's rule).
  6. **Process** in `team/roles/designer.md`: direction brief with the owner → 3 directions
     (sketch, then hi-fi) rendered and self-critiqued → owner picks or mixes → design
     system (tokens, components, motion, screens) locked by the approval digest.
- **Acceptance:** tests that `review` refuses a frontend build without the artifacts, a
  `tokens.json` that breaks the token format, and a component with an unknown source;
  `vesper render` writes four PNGs for a sample page (skip if Playwright is missing).

## P4-T3 — Design gates

- **Change:** ship a reusable gate package `gates/design/` (Playwright + TypeScript,
  run as command gates from P1-T5). `draft-checks` copies it in for frontend jobs.
  1. **Token compliance:** no raw colour values (hex, rgb, hsl, oklch) or raw px sizes in
     source outside the generated token/theme files.
  2. **Anti-pattern lint:** the machine-checkable rules from `anti-patterns.md`, including
     the stock shadcn theme values (the default look counts as a failure).
  3. **Accessibility:** axe-core at 375 and 1280 px, light and dark.
  4. **Reduced motion:** with `prefers-reduced-motion: reduce`, no running animations
     beyond the allowed fallbacks in `motion.json`.
  5. **Visual fidelity:** screenshot each screen at the approved widths and compare with
     the approved mock (perceptual diff with a per-screen threshold).
  6. **Designer as blocking reviewer:** for frontend jobs, after gates pass, the runner
     launches the designer with the mock and candidate screenshots side by side, using the
     same schema verdict (P1-T2) with lens `design`. A design blocker returns the job.
     Order: gates → designer → code reviewer.
- **Acceptance:** fixtures that fail each gate on purpose (raw hex colour, stock shadcn
  theme, missing label, animation ignoring reduced motion, mock mismatch) and pass when fixed.

## P4-T4 — Frontend role, skills and the designer contract

- **Read first:** `team/roles/frontend.md`, `team/skills/frontend-delivery/SKILL.md`,
  `team/skills/react/SKILL.md`.
- **Change:**
  1. `frontend.md`: build strictly from tokens, the component map and the motion spec;
     replace "Do not add a new dependency" with "only dependencies listed in the approved
     spec"; components first; run the app and render it (P4-T2) before finishing; write
     component tests (Vitest + Testing Library) and Playwright journeys; Core Web Vitals
     "good" (LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1) plus an initial bundle budget; title,
     description, social cards, favicon, sitemap; no raw HTML injection, safe token storage,
     CSP; typecheck, lint, format.
  2. Rewrite `team/skills/react/SKILL.md` for the default stack: Redux Toolkit + RTK Query
     (endpoints generated with `@rtk-query/codegen-openapi` from the Go spec), React Router
     data router (loaders, error elements), React Hook Form + Zod, error boundaries; local
     state in `useState`, URL state in the router, everything shared in the store.
  3. New skills: `vite-app`, `astro-site` (React islands; islands needing shared state each
     wrap the same store module in a Provider), `storybook-components`, `web-performance`.
  4. **Components first:** for frontend builds the planner creates a `J_COMPONENTS` job
     before page jobs. Its gate builds Storybook statically; the designer reviews every
     component and state from screenshots (P4-T3 step 6) before any page job starts.
  5. **Deviation requests:** a worker's final message may include `## Design deviations`;
     each becomes a backlog item (P2-T7) with category `design` for the designer to decide.
- **Acceptance:** role and skill text reviewed against `00-context.md`; a planner fixture
  for a frontend build contains `J_COMPONENTS` first; a deviation section lands in the backlog.

## P4-T5 — Backend (Go) role and skills

- **Change:**
  1. `team/roles/backend.md`: Go by default; writes and runs table-driven unit tests with
     `-race`; security baseline on every job (lighter at `skip` depth); spec-first API in
     `api/openapi.yaml` shared with frontend and QA; built for the host (stateless, fast
     start, timeouts, graceful shutdown, health and readiness); `log/slog` with request IDs.
  2. New skill `team/skills/go-delivery/SKILL.md` and pack `team/knowledge/backend/`:
     `security-baseline.md` (`http.Server` timeouts, `http.MaxBytesReader`, Origin and
     `Sec-Fetch-Site` CSRF checks, cookie flags, bcrypt or argon2, rate limiting, security
     headers, CORS allow-list, secrets from env only, no detailed errors), `go-readability.md`
     (own words, linking the Google Go Style Guide), `api-standards.md` (error shape,
     pagination, naming, versioning), `observability.md`, `migrations.md` (versioned,
     reversible or forward-repairable; backup and restore tested), `dependencies.md`
     (standard library first, pinned `go.sum`, `govulncheck`, licence check, only approved modules).
  3. Quality gates offered to QA as command gates: `gofmt -l .` must print nothing,
     `go vet ./...`, `staticcheck ./...`, `golangci-lint run`, `govulncheck ./...`, `go test -race ./...`.
- **Acceptance:** a Go fixture service passes all quality gates; a seeded fixture with a
  missing request-size limit is caught by the security checklist review.

## P4-T6 — Planner role, templates and estimates

- **Change** `team/roles/planner.md`, `team/skills/discovery/SKILL.md`, `docs/PLANNER.md`:
  1. Problem framing: why, success measure, non-goals; challenge the request once (build,
     buy, don't build) with a reason; the owner decides.
  2. Discovery depth follows the planning depth: `skip` 2–3 questions; `full` new app 10–15
     over rounds. Always ask about language and stack (default from `00-context.md`) and, at
     `full` depth, system
     design (users and auth, data, cache, queue, CDN, realtime, search, storage), speed,
     security, privacy, accessibility, hosting and running cost.
  3. Pick the framework from the needs table in `00-context.md`; exceptions need owner OK
     and a decision record.
  4. Options memo with the tech lead; pre-mortem → risks; assumption log; phases for big
     work; jobs sized to about 400 changed lines.
  5. Plan critique already exists (`vesper review-plan`, commit b7da4d1): keep using it, and
     add to its prompt the discovery checklist items above so the critic checks them.
     The tech lead's architecture handoff and the engineers' and QA's acknowledgement of
     the canonical contract are already enforced in `builder/planning.py`.
  6. Show the plan-limit estimate (P2-T3) with every `review`.
- **Acceptance:** a `full`-depth fixture plan passes P2-T5 validation and `review-plan`;
  `review` output contains the estimate block.

## P4-T7 — Tech lead (System Design Engineer): templates and hosting pack

- **Already done in b7da4d1:** the role is renamed "Technical lead · System Design
  Engineer"; it owns the architecture handoff at `full` and `focused` depth, recorded in
  `plan/planning.json` (`architecture`: owner, author, role revision, artifact, inputs,
  consumers; `handoff`: canonical contract acknowledged by engineers and QA), and an
  independent `review-plan` critique gates approval. Don't rebuild any of that.
- **Change** `team/roles/technical-lead.md`, `team/skills/interface-coordination/SKILL.md`:
  1. Templates in `team/knowledge/technical-lead/`: options memo with back-of-envelope
     numbers (users, requests, storage, hosting fit); component decision table (cache,
     queue, CDN, realtime, search, storage → now / later + trigger / no); decision record
     (ADR) template; library rubric (maturity, maintenance, licence, size, security
     history, lock-in); light threat model; operations plan (logs, alerts, backups,
     migrations, recovery). The architecture artifact named in `planning.json` must follow
     the options-memo and component-table templates at `full` depth.
  2. Decision records persist: in Git runs under `docs/adr/` of the target repo; in new
     builds inside the exported app. Later runs must follow or explicitly supersede them.
  3. Default stance "simple now, scale later when a named trigger is hit"; boring tech.
  4. `vesper --project RUN spike --question "..."`: a time-boxed throwaway prototype in the
     sandbox, started only after the owner approves its plan-limit estimate; never promoted.
  5. `hosting.md` with `last_checked`: Render free and Vercel Hobby limits from
     `appendix-a-research.md` section 3, plus the external database once chosen (open item).
  6. Changing the role file changes its revision: update the fixture's
     `planning.json` `architecture.revision` in the same PR (`verify-facts.sh` checks it).
- **Acceptance:** a `full`-depth fixture includes an options memo, component table and ADR;
  `spike` refuses to run without owner confirmation; the hosting pack warns when a design
  stores data on local disk.

## P4-T8 — Starter seeds

- **Change:** add `seeds/` used by `vesper start --mode build --seed NAME`:
  - `vite-app`: Vite + React + TypeScript strict + Tailwind v4 + shadcn (re-theme hook to
    `tokens.json`) + Redux Toolkit/RTK Query + React Router + React Hook Form/Zod + Vitest +
    Testing Library + Playwright + Storybook + ESLint/Prettier, pnpm.
  - `astro-site`: Astro + React islands + Tailwind v4 + shadcn + Motion.
  - `go-api`: `net/http`, `slog`, health and readiness, `api/openapi.yaml`, `migrations/`,
    Makefile targets for every P4-T5 quality gate.
  Pin exact versions checked at implementation time; commit lockfiles; each seed's own
  command gates pass out of the box inside the sandbox.
- **Acceptance:** `vesper start --mode build --seed vite-app` produces a seed that passes its
  gates; the same for the other two seeds.

## P4-T9 — Typed worker hand-off over MCP (`submit_handoff`)

- **Why:** a worker's hand-off is free text in its final message, and the runner finds the
  labelled claims with regular expressions (`handoff_claims`, `builder/providers.py`).
  Each brain also has its own output mode (Claude `--output-format json`, Codex `--json`,
  Gemini `-o json`). All three CLIs can call MCP tools, so one local tool gives every brain
  the same typed hand-off. The owner's decision (23 Nov 2026, after P3-G); `00-context.md`,
  "Reuse before building", names MCP.
- **Read first:** `builder/providers.py` (`handoff_claims`, `worker_prompt`),
  `builder/brains/*.py` (today's MCP flags: Claude `--strict-mcp-config`, Gemini
  `NO_MCP`), `builder/runner.py` (where `claims` are collected for `review.json`),
  `builder/review_gate.py`, P3-T1b, P4-T2 step 2 (MCP per role), P5-T1 (the connector,
  which may reuse this JSON-RPC code; its scope does not change here).
- **Change:**
  1. `builder/handoff_mcp.py`: a standard-library MCP server over stdio (JSON-RPC 2.0:
     `initialize`, `tools/list`, `tools/call`) with one tool, `submit_handoff`. Input
     schema: `summary` (string, bounded), `claims` (array of `{text, label, evidence}`,
     `label` one of `verified`, `inferred`, `assumed`; bounded count and length), optional
     `changed` (paths) and `blocked` (a reason). It validates the input and writes
     `handoff.json` to the one output path it was started with. It has no other tool, reads
     no files, and opens no network connection.
  2. Each adapter whose CLI supports MCP declares a `typed_handoff` capability and starts
     this server for workers only, inside the sandbox; reviewer, QA and plan-critique calls
     keep today's empty MCP config. Check every flag against each CLI's `--help` at
     implementation time, and add them to `vesper doctor`'s flag check.
  3. The brief asks the worker to call `submit_handoff` once, at the end. The runner reads
     `handoff.json`; its claims fill `claims` in `review.json` in the same shape as today.
     A missing or invalid hand-off falls back to `handoff_claims` on the final message,
     with a warning on the attempt.
  4. Adapters without the capability keep the text path unchanged.
- **Do not:** give the tool any power beyond writing that one file; add a reasoning,
  thinking or notes field to the schema (P3-T1b, finding 65); let the reviewer see anything
  but the claims; add a third-party MCP library to the runner (standard library only);
  widen the MCP servers a worker gets beyond this one (P4-T2 owns per-role servers).
- **Acceptance:** unit tests for the server (`initialize`, `tools/list`, a valid call
  writing `handoff.json`, each invalid input refused with a JSON-RPC error, nothing written
  outside the output path); per-adapter command tests for the worker's MCP config, and
  that reviewer calls stay MCP-free; a stand-in worker that calls the tool end to end, its
  claims in `review.json`; the fallback with its warning. Live: one launched Claude Code
  worker in the Docker sandbox hands off through the tool, and Codex too when its sandbox
  login is set up.
