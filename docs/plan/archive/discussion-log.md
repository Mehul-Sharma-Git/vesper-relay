> Historical record of the 9-11 Nov 2026 discussions this plan was built from. The plan files in this folder win on any conflict.

# Vesper Relay — TODOs found during live run (todo app)

Setup notes: installed to throwaway HOME; `vesper start --mode build --idea "A simple todo app"` worked.

## Run observations (todo-app build, planning stage)
- [minor] `start` creates an empty contract.json/idea.md only; no product.md/design.md/architecture.md templates are scaffolded — planner must know the file list from PLANNER.md.
- [medium] Gate environment is stripped to PATH/HOME/TMPDIR/LANG (runner.py execute_check). Gates that need tools configured by env vars (e.g. PLAYWRIGHT_BROWSERS_PATH for a browser gate) can't find them; there's no way in the contract to declare gate env or dependencies. Worked around inside the gate script with a hardcoded fallback path.
- [medium] Gate timeout is hardcoded to 45s with no per-check setting in the contract (jobs have `timeout`, checks don't). Real browser gates or slow servers may exceed it.
- [medium] No first-class browser gate in the runner: the shipped Stockroom UI gate is static HTML parsing; the Playwright suite lives outside the runner (CI only). Build mode for UI-heavy apps needs a supported way to run browser acceptance as an approved gate.
- [minor] Planner must remember exact field names for design.json (validated strictly in team.py) — `start` could scaffold a template.
- [minor] D3-style "phone over Wi-Fi" needs a non-loopback bind; the stockroom gate pattern asserts READY http://127.0.0.1 — fine, but there's no guidance on LAN exposure/security in the planner or backend skills.

## Designer: wireframes need a real deliverable [HIGH]

### Problem
- `team/roles/designer.md` says "deliver annotated wireframes or a prototype" and
  `interaction-design` says "sketch both at narrow and wide widths", but neither says
  what a wireframe *is* (format, file, tooling) or how the owner sees it.
- `validate_design` in `builder/team.py` only checks text fields in `plan/design.json`.
  A "direction" passes with one sentence of `composition` text, so a run can get
  approved without any visual, as this one nearly did (the options were text plus ASCII
  sketches in chat).
- Nothing renders or shows the options to the owner; on a phone or in VS Code they get prose.
- The designer is `consult` access only, so it has no defined place to write visual
  files. Its output has to go through the planner into `plan/`.

### Research (Nov 2026): existing wireframe / sketch skills
| Skill | Output | Look | Variants | Annotations | Self-check | License |
|---|---|---|---|---|---|---|
| nexu-io/open-design `wireframe-sketch` | One HTML file | Pen-and-paper: graph paper, marker fonts, hatching, slight rotation, sticky notes | Yes, 3-4 tabs | Sticky notes; `data-od-id` hooks on regions | Text checklist only | Not shown, check before reuse |
| paperclipai `wireframe` | One SVG per screen + `flow.svg` + `index.html` viewer | Strict mono lo-fi with locked tokens (8px grid, 12/14/20/28 type, 375/768/1280 canvases) | Per screen | Numbered callouts on a separate red dashed layer, plus a numbered region list in the reply | Walk the viewer at 3 widths | MIT (per listing) |
| yhassy/wireframe-skill | `*.wireframe.json` (source of truth) → self-contained editable HTML | Clean grey-box lo-fi | No | No | No | MIT |
| coleam00 `excalidraw-diagram` | Excalidraw JSON → PNG via Playwright | Hand-drawn | No | — | **Render → look at PNG → fix overlap → repeat** | Not shown |
| anthropics/skills `frontend-design` | Hi-fi code, not wireframes | Distinctive hi-fi | — | — | — | — |
Useful from frontend-design: a "design thinking" step before drawing and an explicit list of generic patterns to avoid.

### Recommendations (source changes, for later)
1. **Define the artifact.** For each direction, the designer writes
   `plan/wireframes/<direction>.html` (one self-contained file, no CDN). It shows the
   same representative content at 375px and 1280px side by side. Add a
   `plan/wireframes/index.html` that compares every option on one page, so the owner can
   open a single file in a browser or VS Code preview, including on a phone.
2. **Offer two looks.** "sketch" (pen-and-paper style like nexu-io: marker font,
   hatching, slight wobble) for early direction choices, so nobody mistakes it for final
   UI. "lofi" (mono, locked tokens and 8px grid like paperclipai) once a direction is
   chosen and frontend needs measurements. Ship both as small templates and tokens
   inside `team/skills/` so the runner stays dependency-free. Fonts must be inlined or
   use a system fallback (Vesper avoids network).
3. **Annotate on a separate layer.** Numbered callouts in one accent colour, never
   inside the UI, plus a numbered legend. Callouts cover the primary action, reading
   order, focus order, and what changes between narrow and wide.
4. **Show states.** Small frames for empty, error, saving, and confirm next to the main
   frame, linked to the `states` entries in design.json.
5. **Stable region IDs** (`data-region="list-toggle"`) that match the element IDs in
   design.md. QA's gates and the frontend brief can then point at the same names, and a
   later "change this region" is unambiguous.
6. **Make the validator require it.** `validate_design` should require each
   `directions[]` entry to reference an existing `plan/wireframes/*.html`, and
   `review_bundle` should check those files exist. The approval digest then binds the
   pictures the owner actually saw. Optionally reject files that load remote resources.
7. **Self-check before showing.** Where Playwright is available, render each wireframe
   at both widths to PNG and inspect for overlap, cut-off text, and horizontal scroll
   before presenting (the excalidraw-skill loop). Without Playwright, skip with a
   warning, so this stays optional.
8. **Present in chat with images, not prose.** The entry skill (`integrations/vesper-relay/SKILL.md`)
   should tell the assistant to show rendered PNGs or the index page link when asking
   the owner to choose, with one line per option: what it makes easier and what it costs.
9. **Real variation rule.** Keep the existing rule (recolor ≠ new direction) and add a
   short "avoid generic" list (card grids, gradients, default fonts), taken from frontend-design.
10. **Licensing.** Write Vesper's own templates. Borrow ideas freely, but copy code only
    from MIT sources (paperclipai, yhassy) with attribution. Check nexu-io's license first.
11. **Add a test** in `tests/test_rc1.py`: a build/design run whose design.json lacks
    wireframe files must fail `review`.

Sources: github.com/yhassy/wireframe-skill · skillsdirectory.com (nexu-io wireframe-sketch) ·
getclaudeskills.com/skills/wireframe-paperclipai · agskills.dev/coleam00/excalidraw-diagram-skill ·
mcpservers.org/agent-skills/anthropic/frontend-design

### Trial: hand-made pen-and-paper wireframes for this run (no source changes)
What I did: wrote a small generator outside the repo. It produced A/B/C wireframes as
self-contained HTML (graph paper, wobbly SVG-filtered lines, hatched buttons, red
numbered callouts outside the device, a numbered legend, and pro/con sticky notes),
with B's states (menu open, empty, save failed, delete confirm). I rendered them to PNG
with Playwright and put them in the run's `plan/wireframes/`.
Learnings for the source:
- **Bundle a handwriting font.** The sandbox could not reach Google Fonts, jsDelivr, npm
  or PyPI, and no handwriting font was installed. Ship an OFL font (Caveat or Patrick
  Hand, woff2, base64 in the template) with the designer skill, or the "sketch" look
  degrades to a plain sans.
- **The SVG `feTurbulence` + `feDisplacementMap` wobble filter works offline** and gives a
  convincing hand-drawn line without any library. Reuse it in the template.
- **The render-and-inspect loop caught 3 real defects** before the owner saw anything:
  callout pins clipped by an `overflow:hidden` row, a menu drawer that covered the whole
  phone, and a pin landing inside the laptop UI. An automated overflow check (comparing
  scrollWidth and clientWidth on frames) plus a screenshot review is worth making a
  standard step.
- **Vesper already accepts extra plan files.** `plan/wireframes/*` went into the review
  digest without any code change, so the approval binds the pictures. Nothing *requires*
  them yet (see rec. 6).
- **Plan approvals get invalidated as expected.** Adding wireframes changed the digest
  (4c0bc2f2… → 4ce5341e…), which is correct behaviour.
- **Each frame should state its width and content.** Using the same representative
  content in every option made the comparison fair, and labelling each frame with its
  width removed any ambiguity. Make both rules part of the template.

## Live build run: Claude provider, automatic mode, `--trust-host` (Nov 9)
Result: **complete**. J_API and J_UI were each accepted on the first worker attempt, and all
3 gates passed, including the real-browser gate and the final full-gate rerun. The app
exported and works at 320, 375 and 1280px. The native Claude adapter flags work on
Claude Code 2.1.321. Elapsed time was about 8 minutes. The reviewer calls cost about $1.26
(3 calls); worker cost isn't reported because worker logs are plain text.

### HIGH
- **The reviewer report parser rejects Claude's normal output.** 2 of 3 reviewer calls
  returned a valid, approving JSON verdict, but with one sentence of prose before the
  ```json fence. `decode_provider_report` (builder/review_gate.py) only accepts a bare
  object, a fence that is the entire text, or a single-line `{...}`. As a result, `run`
  stops with "Reviewer did not return a valid JSON report" and retrying hits the same
  problem. Fix: extract the last fenced json block or the last balanced `{...}`, and/or ask
  Claude for structured output (`--json-schema` or output-format options) and say "no prose"
  in the prompt. Add a regression test with a preamble before the fence.
  *Workaround used:* I took the independent reviewer's own JSON and submitted it with
  `review-candidate --report FILE --attest-independent`.
- **Workers can't run anything.** Worker tools are Read/Edit/Write/Glob/Grep only, and
  both workers said "None of it has been run". Passing first time was luck plus a very
  explicit plan. For real projects, give the worker a way to run the approved gates on its
  copy, or allow a shell inside the launcher sandbox. Otherwise retries are spent on
  blind fixes.
- **The reviewer can't see gate logs or scripts.** The review copy has only one-line
  summaries in review.json, and the reviewer flagged this itself. Copy the gate logs (and
  the read-only check scripts) into the review workspace.

### MEDIUM
- When `run` fails at review, the error doesn't name the recovery path (re-run `run`, or
  use the supervised `review-candidate --report`). Print the next step.
- The reviewer timeout is hardcoded at 180s (runner.py). Reviews took about 78s here, so
  a large diff will hit the limit. Make it configurable.
- The provider environment drops HTTPS_PROXY, NO_PROXY and custom CA variables
  (providers.py). This worked here, but users behind a corporate proxy will likely fail.
  The provider also inherits HOME, so running vesper under a different HOME loses the
  provider login. Document this, or pass the proxy variables through.
- **Security pattern for local apps.** The reviewer noted that the generated server
  accepts cross-site "simple" requests and doesn't check the Host header, so any website
  the owner visits could change their todos, which gets worse with `--host 0.0.0.0`. Add
  to the backend and security-diff skills: require `Content-Type: application/json` and
  check Host/Origin for local servers. Add this to the planner's LAN-exposure guidance
  noted above.
- **Design drift is caught only as advisory.** The design said "Add disabled while
  saving" and the build used aria-busy. That's fine here, but it shows design.json details
  aren't checked by any gate.

### Worked well (keep)
- Scope enforcement, digest-bound approval, the final rerun of every gate, and export.
- The independent reviewers were substantive. They traced every fetch against server.py,
  found a real stale-state bug path and the CSRF issue, and noticed that 320px wasn't covered.
- Wireframe B → built UI matched closely (picker button, panel, sidebar on laptop).

## Expected gaps for a complex app (analysis, not yet observed)
Blockers
1. **No dependency or toolchain support.** There is no npm/pip install step, gates run with
   a stripped environment and no network, `safe_path` rejects `node_modules`, and
   `inventory` rejects symlinks (npm uses them). A React/Vite or Postgres app can't be
   built or checked without a provisioning step ("managed dependency provisioning" is
   listed as out of scope).
2. **The plan is frozen per project.** Any scope change means a new project seeded from
   the export, plus a fresh approval. Complex apps change weekly, so this needs amendable
   plans (versioned contract and delta approvals).
3. **One writer at a time with file-level ownership.** Many jobs touch the same shared
   files (routes, schema, migrations, package.json), which leads to "Changes outside job
   scope" rejections or one giant job. This needs shared-file and directory ownership rules,
   plus a merge or integration job, and parallel writers on disjoint areas.
4. **Workers can't run code.** Fine for 4 files, but on a large codebase blind edits will
   burn through max_attempts (at most 5).
5. **Gates are hand-written, frozen and limited to 45s.** A big app needs its own test
   suite (pytest/jest/Playwright) as a gate, with a per-check timeout, and new tests
   added as features land without re-approving everything.
Scale and robustness
6. Every attempt copies and SHA-256 hashes the whole tree several times (workspace,
   candidate, review base and candidate). This will be slow and disk-heavy with thousands
   of files or assets.
7. The reviewer is limited to a 512 KB diff budget, a 180s timeout and 20 turns. Large
   jobs get shallow reviews, and the JSON parse bug blocks runs.
8. There's no secrets or environment mechanism for apps that need API keys or services,
   and `--trust-host` with real credentials is risky without a tested sandbox launcher.
9. The Git bridge has no submodules, symlinks or LFS, and no branch/PR flow, only
   patch-apply to the working tree.
Product and process
10. There's one design.json per run, with a single primary task. Many screens need a
    shared design system and tokens, and design changes trigger a full re-plan.
11. The QA, tech-lead and designer roles are consult-only. Someone (the assistant) must
    write everything up front, with no checkpoint once API contracts change mid-build.
12. There's no cost or time budget, no progress view beyond JSON status, and no
    run-level summary.
13. Out of scope today: deploy, DB migrations on real data, auth or multi-user, and
    performance checks.
Suggested way to use it meanwhile: many small runs (one feature slice each) on an
existing Git repo with its own test suite, rather than one big "build" run.

## Planner gaps raised by the owner
- **The tech stack was never asked about.** The planner role tells it to treat frameworks
  as delegated ("do not confuse a preferred framework with a user requirement"), and the
  runner can only build and check stdlib-only code anyway, so the choice was made silently.
  Fix: make language and stack an explicit decision in discovery. Ask the owner's
  preference and skills, how the app will be hosted, and who maintains it, and record the
  answer in decisions.md. If Vesper can't support the stack, the planner must say so
  before approval.
- **System design questions rely on the assistant's judgement.** The planner role mentions
  cost, data, deployment and operations, but there's no checklist and no "complexity
  trigger". Fix: add a system-design discovery pass for non-trivial builds (users and
  auth, data model and ownership, consistency and concurrency, sync and offline,
  background jobs, integrations and secrets, scale and performance, privacy, backup and
  migrations, deploy and hosting, observability). Have the technical lead produce a
  short architecture options memo with a recommendation before approval.

## System design: infrastructure components (owner's clarification)
Today: the skills mention only local hygiene (pagination, indexes, query plans in the
sqlite and postgres skills; a WebGL performance budget). interface-coordination says
"escalate new services", but nothing explains *when or why* to use a component, and
nothing can run one.
- **Add an architecture discovery step owned by the technical lead**, triggered by
  complexity. Estimate expected load (users, requests/sec, data size, read:write ratio,
  peak events), latency targets, and growth. For each candidate component, decide
  needed / not yet / no, give a reason, and say exactly how it would be used:
  - Cache (Redis etc.): what is cached, key design, TTL and invalidation, what happens if
    the cache is down.
  - Message queue or background jobs (Redis streams, RabbitMQ, SQS, Kafka): which work is
    async, retries, idempotency, dead letters, ordering.
  - CDN: static assets and media, cache headers, invalidation on deploy.
  - Real-time (WebSockets/SSE), search index, object storage, rate limiting, read
    replicas, sharding.
  - Record the decision in `plan/architecture.md` as an options table with costs, and
    revisit it when the load numbers change. Default to the simplest thing ("add Redis
    when X is measured"), not cargo-cult infrastructure.
- **Ask the owner** about the decisions that change cost, hosting or operations (managed
  vs self-hosted, budget, region, who's on call).
- **Runner support is missing.** Gates can't start Redis, a queue or Postgres (no service
  provisioning or docker-compose, stripped env, no network). The approved architecture
  needs a matching way to run those services in checks, or it can't be verified.
- **Add a skill per component** (cache, queue, CDN and HTTP caching, realtime), like the
  existing sqlite and postgres skills, with pass conditions.

## Performance and optimisation (owner's question)
Today Vesper does **not** optimise automatically. No reviewer area covers performance
(the areas are requirements, correctness, scope, tests, maintainability, security and
design). There are no performance gates, benchmarks, load tests or profiling, and no
"optimise" workflow mode. Code is only as fast as the worker happens to write it.
- **Put performance budgets in the contract**, for example p95 API latency under N ms at
  X rps, page load under Y s on a mid-range phone, JS bundle under Z KB, and a query
  count per request.
- **Turn budgets into gates**: a micro-benchmark or load test (k6/locust style), query
  counting to catch N+1 queries, and Lighthouse/Web Vitals in Playwright. Gates then need
  configurable timeouts and quiet, repeatable conditions (pinned CPU, warm-up, median of N).
- **Add "performance" as a reviewer evidence area** and a performance/profiling skill:
  measure first, find the bottleneck, fix it, re-measure, and show the before/after numbers.
- **Add an `optimise` workflow mode**, like bug mode: reproduce the slowness with a
  benchmark, freeze it as the failing gate, then fix within scope while the existing
  tests stay green.
- **Use learning on regressions**: record benchmark numbers per accepted snapshot and
  flag a regression at the next job.

## Direction and release decisions (Nov 10 discussion)
- **Tool layer (missing even for the website builder).** Give each role an allow-list of
  tools that run inside the sandbox: run tests/gates, install packages, start the app,
  open a browser, plus web search and MCP connectors for future branches. Today workers
  have Read/Edit/Write only. (Related: "Workers can't run anything", "No dependency
  support".)
- **Front door options.** Short term: expose Vesper as an MCP connector so the Claude app
  (phone or desktop) can start runs, show status and approve plans. Long term: a
  self-hosted always-on service (own address, HTTPS, login) that uses Claude via API as
  the brain.
- **Architecture rule.** Keep ONE generic orchestrator and branch at the workflow level
  (website/code, research, bookings…). Each branch brings its own agents, tools and
  checks; the planner, approval, sandbox, check runner, reviewer, action gate and
  learning are shared. Refactor the runner to separate the generic core from the
  code-specific parts (file inventories, patches).
- **Agents.** Add them per kind of work, not per task. Reuse general roles (researcher,
  writer, analyst) across branches, and add a specialist only when a task needs special
  knowledge, tools or risk rules (e.g. a caller). Keep a generalist fallback for one-off
  requests.
- **Release plan: sandbox-first candidate releases.**
  1. Build and test the real sandbox launcher first. Today's runs used `--trust-host`.
  2. Build an evaluation bench of dummy projects: static site, CRUD app, existing-repo
     bug fix, refactor, multi-job app, a dependency-heavy app (React/npm), and
     deliberately broken cases (bad worker, scope escape, hostile file content).
  3. Run the bench for every RC and publish a scorecard: runs finished without manual
     help, first-attempt pass rate, reviewer parse failures, scope violations caught,
     escaped defects found later, security findings, time and cost per run.
  4. Set promotion criteria in advance (e.g. ≥90% unattended completion over N runs, 0
     sandbox escapes, 0 parser failures). The OWNER promotes, based on the scorecard;
     Vesper must not certify itself (same rule as "worker doesn't grade its own homework").
  5. Use a permission ladder: sandbox only → read-only on real repos → patches with
     approval → limited autonomy on low-risk tasks.
  6. Optionally schedule the bench nightly and track regressions between RCs.

## Direction notes
- **Keep the split.** The instructions guide the AI, and the program enforces the rules.
  This is Vesper's core value; carry it into the assistant.
- **Process proportional to risk** (needed before going general):
  - Light path: reminders, lookups, summaries. No planner or reviewer, just do it and log it.
  - Standard path: drafts and reports. A short plan, a check, then hand-over.
  - Full path: code changes, money, messages sent as you, bookings, calls. The full
    plan → approval → checks → reviewer → ask-before-acting flow.
  The router picks the tier; any irreversible action always passes the action gate.
- **For the assistant, the program's job shifts** from file referee (copies, scope,
  patches) to action referee: tool permissions per agent, approval before irreversible
  actions, a secrets vault, spending and rate limits, an audit log, and treating
  email/web content as data, never as instructions.
- **Reuse before building.** Prefer existing pieces (MCP connectors, container sandboxes,
  a job queue or scheduler, the agent SDK) over hand-written equivalents. Keep Vesper's
  own code for the parts nobody else gives you: plan locking, independent checks and
  review, approvals and the audit trail.

## TOP PRIORITY: make the designer the highest-expertise agent [HIGH]
Owner's view: code from AI works after testing, but design stays generic even after many
prompts, so design is the bottleneck for website building. Goal: a designer with the
knowledge of what's available and what fits where, the eyes to judge its own output,
and the authority to block generic or off-spec builds.

### Analysis: why design comes out generic (and where Vesper stands)
Evidence from our run: the todo app worked and matched wireframe B's layout, but the
visual result was the default look (system blue buttons, plain sans, white cards).
Nothing in the pipeline asked for or checked anything better.
Root causes (supported by the research below):
1. **No direction input.** Vague requests make the model return the "median" of its
   training data (Inter, indigo/purple gradients, centered hero with three cards). Vesper
   never asks the owner for references, brand feel, or likes and dislikes.
2. **Taste, exploration and implementation are fused.** One pass tries to decide the
   look, explore it and specify it, and the ambiguity collapses to the average. Vesper's
   design.json is a text form filled in during planning.
3. **No knowledge base.** `designer.md` and `interaction-design` hold good principles,
   but no concrete vocabulary: no type pairings, palettes, layout patterns, motion
   timings, chart choices, or "which component fits which job".
4. **No eyes.** The designer is consult-only, renders nothing and never sees a
   screenshot. Neither the reviewer nor any gate looks at the built UI as an image.
5. **Implementation rounds the design off.** The frontend picks what's easiest.
   `frontend.md` even says "Do not add a new dependency", so component and motion
   libraries are effectively banned.
6. **No component or motion supply chain.** Everything is hand-written from scratch, and
   none of the good libraries can be installed (no npm support; see blocker #1).
7. **No design quality gate.** The reviewer's "design" area is free text. There's no
   rubric, no fidelity check against the approved mock, and no anti-pattern check.

### Research: the owner's 5 references + the wider landscape (Nov 2026)
| Resource | What it's best at | Stack | License / cost | Agent interface |
|---|---|---|---|---|
| **Anime.js v4** | Timelines, stagger, SVG morph/paths, scroll-linked, draggable; framework-free | Vanilla JS ES modules, ~24 KB | MIT, free | None. Needs our own v4 skill notes (models mostly know v3) |
| **Motion (motion.dev)** | React/JS/Vue transitions, layout animation, gestures, springs | `motion` npm | Core MIT; Motion+ paid (examples, 50 animated sections) | **AI Kit**: `npx motion-ai` installs a `/motion` skill and MCP (free docs and best practices; Performance Doctor and examples are paid) |
| **Kokonut UI** | ~116 free animated/marketing components, ready to copy | React, Next, Tailwind, shadcn, Motion | MIT; Pro paid | shadcn registry + shadcn MCP, `llms.txt`, `llms-full.txt`, per-page .md |
| **Bklit UI** | Dashboards: 14 chart types (area, bar, candlestick, choropleth, funnel, gauge, sankey…) | React, TS, shadcn registry (visx, Motion) | Charts MIT; **Bklit Studio proprietary, exclude** | shadcn CLI; repo has AGENTS.md, llms.txt, skills/ |
| **v0 (Vercel)** | Generates whole React/Next screens from a prompt | React/Next (framework-specific) | Paid; daily quotas; data "not used for training" | Platform API (`api.v0.dev`), `v0-sdk`, `@v0-sdk/ai-tools` |
| shadcn/ui + registry | Accessible base components; the "plug" most libraries use | React + Tailwind | Free | **Official MCP** (`npx shadcn@latest mcp`), CLI, registries in components.json |
| 21st.dev Magic MCP | Generates components "inspired by" the 21st.dev library | React | Key needed; free in beta, then limits | MCP + CLI |
| Mobbin MCP | 621k+ real app screens and 142k+ flows from shipped apps (onboarding, paywalls, checkout…) | n/a (references) | Paid Mobbin plans; beta | MCP (Claude, Cursor…) |
| UI/UX Pro Max skill | Searchable design knowledge: 67 styles, 96 palettes, 57 font pairings, 24 landing patterns, 25 chart types, 99 UX rules, 100 product types (self-reported) | Any | **License not stated, check** | Skill + BM25 search CLI |
| Impeccable (pbakaus) | Design skill with 17 commands (/audit, /critique, /polish, /normalize, /animate, /distill), 7 reference files, curated anti-patterns | Any | Not stated, check | Skill |
| Anthropic frontend-design | "Design thinking" before code and an anti-generic list | Any | (Anthropic skills repo) | Skill |

What the research agrees on: give a specific direction and real references; keep an
explicit avoid-list; separate taste → explore several directions → pin a design-system
spec → build; give feedback in concrete design terms, not adjectives; verify basics
(states, accessibility).

### Plan, as targeted TODOs
**1. Design knowledge base** (`team/skills/design-*/references/`, retrieved by search,
not pasted whole)
- Typography: pairings by mood, scales, measure, which fonts to avoid by default.
- Colour: palettes by product type and mood, contrast rules, dark-mode pairs, semantic colours.
- Layout patterns: landing pages, pricing, dashboards, forms, settings, onboarding;
  narrow and wide versions.
- Motion vocabulary: durations and easings by purpose, enter/exit/layout/scroll
  patterns, when NOT to animate, reduced motion, performance rules.
- Data viz: chart choice by question, dashboard density rules.
- Anti-pattern list, enforced as a gate (see 6).
- "What fits where" catalogue: for each UI job (hero, feature grid, pricing, chart,
  toast, page transition, number ticker…), the recommended source (shadcn / Kokonut /
  Bklit / Motion / Anime.js / hand-built), install command, licence, accessibility notes.
- Seed it by adapting MIT/clearly licensed material (frontend-design, Motion AI Kit
  guidance, shadcn/Kokonut/Bklit llms.txt). Check the UI/UX Pro Max and Impeccable licences
  before reusing any text. Add a small search script (BM25, stdlib) so the designer queries
  it like UI/UX Pro Max does.

**2. Designer tools** (needs the tool layer)
- shadcn MCP (covers shadcn, Kokonut and Bklit registries): search and preview
  components, return the install command.
- Motion AI Kit MCP/skill (free tier). Motion+ features only if purchased.
- Anime.js v4: our own skill notes plus a vendored ESM build, which also works in
  stdlib-only projects (copy as a file, no npm).
- Reference search: Mobbin MCP (optional, paid), plus `plan/references/` where the owner
  drops screenshots and links of sites they like and dislike.
- Optional generators for EXPLORATION ONLY: v0 Platform API or 21st Magic, behind a
  budget limit; output is treated as a draft direction, never shipped unreviewed.
- **Render and screenshot tool (Playwright)** so the designer can see its own mocks and
  the built candidate at phone and laptop widths, light and dark, and critique them.
- Use a vision-capable top model for the designer and the design reviewer.

**3. Design process** (new stages in build, feature and design modes)
1. Direction brief: ask the owner for 3 adjectives, 2-3 sites they love, 1 they dislike,
   audience, brand assets, and must-avoid items. Pull matching references.
2. Explore 3 truly different directions (sketch wireframes from the earlier TODO, then a
   hi-fi mock per direction with real content), rendered and self-critiqued before the
   owner sees them.
3. Owner picks or mixes.
4. **Design-system spec** written as plan files that the approval digest locks: tokens
   (colour, type scale, spacing, radius, shadow, motion), the component map (which
   library item for which UI part), motion spec, states, plus hi-fi mocks per key screen.
5. Frontend builds FROM the spec: required tokens, approved components, approved motion.
6. Design QA (step 6 below) before acceptance.

**4. Role changes**
- Designer becomes a writing role for design artifacts before approval, and a
  **blocking design reviewer** after the build (it can send a frontend job back).
- Update `frontend.md`: "use the approved design system and component map; approved
  libraries are allowed". Replace the blanket "no new dependency" rule with "only
  dependencies listed in the approved spec".
- Add a design rubric to `candidate-review`: hierarchy, typography, colour use, spacing
  rhythm, fidelity to the mock, motion quality, states, and anti-patterns found, with
  screenshots attached as evidence.

**5. Supply chain prerequisites** (link to existing blockers)
- npm/package install + build step (React, Tailwind, shadcn CLI). Without it none of
  Kokonut, Bklit, Motion or shadcn can be used. Blocker #1.
- `node_modules` and symlink handling in inventories; network access for registry
  installs during the build step only; lockfiles committed.
- Keep a no-build lane too: plain HTML/CSS plus vendored Anime.js for simple sites.

**6. Design gates** (automatic, before the reviewer)
- Visual fidelity: screenshot the candidate at the approved breakpoints and compare it
  to the approved mock (perceptual diff threshold, plus the design reviewer's judgement).
- Token compliance: CSS uses only spec colours, fonts and spacing (lint computed styles).
- Anti-pattern lint: default indigo/purple gradients, banned fonts, centered hero plus
  three identical cards, nested cards, grey text on colour, emoji icons…
- Accessibility: axe-core checks (contrast, labels), keyboard path, `prefers-reduced-motion`
  honoured by every animation.
- Motion performance: no layout-thrashing properties, frame budget, bundle size budget
  (Motion's Performance Doctor if available).

**7. Licensing guardrails**
- Allowed by default: MIT libraries (Anime.js, Motion core, Kokonut free, Bklit charts,
  shadcn) with attribution kept.
- Excluded unless purchased or licensed: Kokonut Pro, Motion+, Bklit Studio, Mobbin
  content, v0 or 21st output (check their terms).
- References are inspiration only. Never copy a real brand's design, logo or copy.

**8. Measuring it** (add to the RC evaluation bench)
- 5 fixed design briefs (bakery landing page, SaaS dashboard, portfolio, booking flow,
  pricing page) run every RC.
- Score: owner blind rating (1-5) against the previous RC and plain Claude, anti-pattern
  count, accessibility score, fidelity diff, and number of design revisions needed.
- Promote design changes only when the scores improve.

## Agent upgrades: shared foundation (all roles)
- **Reasoning note before the main output.** Understanding, assumptions, at least 2
  options considered and why one was picked, a pre-mortem, and "how I'd know I'm wrong".
  The runner checks the note exists.
- **Claim labels.** Mark each claim verified / inferred / assumed; "should work" is not allowed.
- **Self-critique pass** with fresh context before handing over.
- **Deep reference pack per role**: failure-mode catalogue, checklists, gold-standard examples.
- **Tools to verify** (see the tool layer TODO).
- **Model and effort routing**: the strongest model and high effort for the planner,
  designer, tech lead and reviewer; cheaper settings for routine work.
- **Postmortems feed role checklists**, with owner approval.
- **Per-role evaluation set** in the RC bench.

## Agent 1: Planner (agreed with owner, Nov 11)
1. **Problem framing**: why, success measure, non-goals. Challenge the request (build,
   buy, or don't build). Push back once with a reason; the owner decides.
2. **Discovery depth scales with job size**: light = 2-3 questions; full new app = 10-15
   questions over several rounds. The checklist covers stack and language, users and
   auth, data, system design (queue, cache, CDN…), performance, security, privacy,
   accessibility, hosting and running cost.
3. **Options memo** with the tech lead: 2-3 approaches, trade-offs, a recommendation.
4. **Pre-mortem**, turned into a risk list with a check or mitigation for each risk.
5. **Assumption list**, each with how and when it gets confirmed.
6. **Phases and milestones** for big work, each delivering something usable.
7. **Plan reviewed by the tech lead and QA** before the owner sees it.
8. **Required plan sections are validated** by `review` (like design.json).
9. **Estimate before every approval, in plan-limit units, NOT dollars.** The owner is on
   Claude Pro (a fixed fee) with 5-hour session and weekly limits.
   - Show: number of jobs, AI calls, expected % of a 5-hour session, % of the weekly
     limit, wall-clock time, and how many sessions it needs, e.g. "about 2 sessions,
     done tomorrow evening if started now".
   - Anthropic doesn't publish exact Pro numbers, so calibrate from the owner's own runs.
     Record tokens per call (the `claude -p` JSON includes usage) and plan-usage % before
     and after each run. Claude Code's statusline JSON exposes
     `rate_limits.five_hour/seven_day.used_percentage` and `resets_at` for Pro users.
     Show the estimate as a band and say how confident it is (low until ~5 runs).
   - **Limit-aware runner**: check remaining session and weekly %; keep an owner-set
     reserve (e.g. 25% for normal chatting); stop starting new jobs at the threshold;
     resume automatically after the window resets (resume exists); offer "start now"
     vs "start after the reset at HH:MM".
   - **Stretch the plan**: use the top model only for judgement roles and lighter models
     for routine workers; cap turns; avoid wasted calls (e.g. the reviewer parse bug
     cost a full extra review); cache prompts where possible.

## Agent 2: Tech lead (agreed with owner, Nov 11)
1. **Required for full builds**, optional for small jobs. Reviews the planner's plan.
2. **Architecture options memo** (2-3 options, always including the simplest) with
   back-of-envelope load, storage and hosting numbers, and a recommendation.
   **Default stance: simple now, scale later when a stated trigger is hit.**
3. **Component decision table**: cache, queue, CDN, realtime, search, file storage →
   now / later (trigger) / no.
4. **Architecture decision records** saved per project; later runs must follow or
   explicitly replace them.
5. **Library selection rubric**: maturity, maintenance, licence, size, security
   history, lock-in.
6. **Speed and reliability targets** turned into gates with QA; a light threat model
   with the security reviewer for login, personal data or payments.
7. **Prototypes allowed, but it ASKS the owner first** and shows the plan-limit
   estimate. Runs in the sandbox only.
8. **Operations plan**: logs, error alerts, backups, safe migrations, recovery steps.
9. **Simplicity guard**: every component justifies itself; boring tech by default.
10. **Hosting default: free tiers** (Vercel, Render, etc.) unless the owner says
    otherwise. The tech lead needs a **hosting knowledge pack** with a "last checked"
    date, because free tiers change. Facts as of 2026-11-11:
    - Render free: spins down after 15 min idle (~1 min cold start); 750 instance
      hours/month; **ephemeral disk (SQLite files are lost), no persistent disks**;
      free Postgres is 1 GB and **expires after 30 days**, no backups; free Key Value
      is in-memory only; no free background workers or cron.
    - Vercel Hobby: **personal, non-commercial use only**; functions max 300 s; 1M
      invocations, 100 GB transfer; no persistent local disk; Blob storage listed;
      going over a limit can disable a feature for 30 days.
    - Implications: free-hosted apps must be stateless with an external database
      (evaluate free managed Postgres/SQLite providers and record their limits);
      chunk long jobs or use an external scheduler; expect cold starts; a commercial
      product needs a different plan. Our todo app's local-SQLite design would lose
      data on either host, which is exactly the kind of mistake this pack must catch.

## Default stack (owner decision, Nov 11)
- **Backend: Go. Frontend: React.** The planner still confirms per project and records
  any exception in decisions.md.
- Vesper must support both toolchains (dependency layer): Go modules
  (`go build/test/vet`), npm/pnpm for React; gates able to run `go test` and browser
  tests.
- Hosting fit (tech lead to confirm per project): Go API as a web service (e.g. Render
  free: note the 15-min sleep and ~1-min cold start) with the React frontend on static
  hosting (e.g. Vercel Hobby, non-commercial). External database, because free hosts
  have no persistent disk. Set CORS/CSRF up deliberately when the frontend and API are on
  different domains.

## Agent 3: Backend engineer, Go (agreed with owner, Nov 11)
1. **Writes and runs its own unit tests** (`go test`, table-driven, `-race`) in addition
   to QA's independent gates.
2. **Security baseline on EVERY backend job** (lighter for small jobs): input size and
   validation, CSRF/Origin checks, authN/session safety (bcrypt/argon2 for passwords),
   rate limiting, security headers, a CORS allow-list, secrets only from env vars,
   no detailed errors in responses.
3. **API standards**: one error shape, pagination, naming and versioning; an
   **OpenAPI spec** as the shared contract with the React frontend and QA (generate
   TS types from it).
4. **Performance**: query budget per request, N+1 check, indexes for filters, measure
   before and after (pprof/benchmarks) for any optimisation.
5. **Built for the host**: stateless, fast startup, honours function/request
   timeouts, graceful shutdown, health and readiness endpoints.
6. **Observability**: structured logs (`log/slog`), error reporting, request IDs.
7. **Go code quality gates**: `gofmt`, `go vet`, `staticcheck`, `golangci-lint`, a
   readability self-review (small functions, clear names, errors wrapped with context,
   no panics in handlers, `context` passed through).
8. **Dependencies**: prefer stdlib (`net/http`, `database/sql`); every module pinned
   in go.sum; `govulncheck` must pass; licences checked; only plan-approved modules.
9. **Database safety**: versioned migrations (e.g. goose/migrate) that are reversible
   or forward-repairable; backup/restore tested on the chosen external DB.

## Agent 4: Frontend engineer, React (agreed with owner, Nov 11)
Exact frontend stack: PENDING a separate discussion (Vite vs Next.js vs others).
1. **Builds strictly from the approved design system**: tokens, the component map and
   the motion spec. Approved libraries are allowed.
2. **Standard React practices**: TypeScript strict, server-data caching, typed forms with
   schema validation, routing, error boundaries, API types generated from the backend
   OpenAPI spec. Exact libraries are decided in the stack discussion.
3. **Sees its own work**: runs the app in a real browser, screenshots phone and laptop
   in light and dark, self-critiques against the mock before submitting.
4. **Writes component tests and runs browser journeys itself** before submitting (in
   addition to QA's gates). Owner: yes.
5. **Speed targets default to Google Core Web Vitals "good"** (LCP ≤ 2.5 s, INP ≤ 200 ms,
   CLS ≤ 0.1) plus an initial JS bundle budget; tightened per project. Owner: yes.
6. **Animation discipline**: honour reduced motion, animate transform/opacity only,
   provide a fallback.
7. **Website basics**: title and description, social preview cards, favicon, sitemap;
   analytics only if approved.
8. **Security**: no raw HTML injection, safe token storage, CSP, dependency audit.
9. **Quality gates**: typecheck, lint, format, readability self-review.

## Frontend stack (owner decisions, Nov 11)
1. **The stack is chosen per project from its needs, not a fixed label.** The planner
   asks: search ranking? interactivity? logins? realtime? who edits content? offline?
   The answers map to:
   - landing/portfolio → Astro + React islands
   - content/blog/docs → Astro (Starlight for docs) + content source
   - web app/dashboard (behind login) → Vite + React SPA
   - SaaS (marketing + app) → Astro site + Vite app on an app subdomain, or Next.js
   - shop → Next.js or Astro + headless commerce
   - realtime/collaborative → Vite app + Go WebSockets (Render free sleeps; plan reconnects)
   - offline/installable → Vite PWA
   - native mobile → React Native/Expo (out of scope for now)
   Next.js only as an exception with owner OK. Exceptions are recorded in decisions.md.
2. **Shared layers**: TypeScript strict, Tailwind v4, Motion + Anime.js, React Hook Form
   + Zod, Vitest + Testing Library + Playwright, pnpm, ESLint/Prettier or Biome. API
   types and Zod schemas generated from the Go OpenAPI spec.
3. **State: Redux Toolkit everywhere, with RTK Query for server data** (instead of
   TanStack Query, so there's one cache). Generate RTK Query endpoints from the Go
   OpenAPI spec (`@rtk-query/codegen-openapi`). URL state in the router, form state in
   RHF, purely local UI state in `useState`; everything shared goes in the RTK store.
   Astro islands that need shared state each wrap the same store module in a Provider.
4. **Components: shadcn/ui as the base, ALWAYS re-themed** from the designer's tokens.
   An anti-pattern check flags the stock shadcn look (it's become the new "generic AI
   look"). Use **React Aria** for complex accessible widgets (date pickers, comboboxes,
   data grids). Kokonut and Bklit come via the shadcn registry.
5. **Designer ↔ frontend contract** (like the backend API contract):
   - W3C-format design-token file owned by the designer → generated Tailwind theme;
     no raw colours or sizes in code (lint).
   - Component inventory: variants × sizes × states, each mapped to its source
     (shadcn/Kokonut/Bklit/React Aria/custom).
   - **Components first**: the frontend builds the component library in Storybook; the
     designer screenshot-reviews every component and state and approves before pages
     are built.
   - Shared names across wireframes, mocks, code and tests (`data-region` / component names).
   - The frontend reviews the design for buildability and performance before approval.
   - Deviation requests instead of silent changes; the designer is a blocking
     visual-fidelity gate per page.
6. **Routing: React Router** (owner decision). Vite apps use its data router
   (`createBrowserRouter` with loaders and error elements).

## Agent 5: QA engineer (agreed with owner, Nov 11)
1. **QA owns and writes ALL acceptance checks** before approval, in the right language
   (Go tests, Playwright/Vitest in TS, Python where useful), with a short test strategy
   per project. It becomes a writing role for `checks/`.
2. **Test pyramid**: builders write unit tests; QA writes contract and integration
   tests plus a few end-to-end journeys.
3. **Contract tests** from the Go OpenAPI spec: generated and malicious requests
   against the API (Schemathesis-style), and checks that the frontend's calls match the spec.
4. **Prove the checks work (mandatory)**: every check must fail against a deliberately
   broken version before approval. **Mutation testing on full builds.**
5. **Non-functional checks**: always accessibility (axe), visual comparison, and
   phone + laptop sizes. Full builds also add Firefox + WebKit, load tests (k6-style),
   a baseline security scan, and Core Web Vitals.
6. **Exploratory session**: an agent drives the real app with edge cases (empty, huge,
   emoji, double click, back button, slow network, two tabs) and files bugs with repro steps.
7. **Seeded, realistic test data** at realistic volume.
8. **Additive checks after approval allowed** (add only, never remove or weaken), shown
   to the owner in the run summary, without full re-approval.
9. **Every escaped bug → a permanent regression test**, plus a release-readiness
   checklist before hand-over.
Runner support needed: gates in any language (with the toolchain layer), configurable
timeouts, multiple browsers.

## Agent 6: Independent reviewer (agreed with owner, Nov 11)
1. **Structured verdicts** enforced by a JSON schema (fixes the parse bug).
2. **Evidence-backed blockers**: may run tests in the sandbox; a blocker comes with a
   failing test or exact repro; unproven concerns are "suspected" with a confidence level.
3. **Multi-lens review on full builds** (correctness, security, performance,
   readability against the Google Go/TS style guides) merged by a lead reviewer;
   a single pass for small jobs. Design is the designer's gate.
4. **Full inputs**: gate logs and scripts, plan risk list, threat model, ADRs.
5. **Nothing lost**: advisories go to a backlog. **Security and data-safety advisories
   must be decided before acceptance** (fix now or the owner accepts the risk).
6. **Small jobs**: about 400 changed lines per job as a guideline; the planner splits work.
7. **Different eyes**: Codex as the reviewer (owner CONFIRMED a ChatGPT plan, Nov 11).
   This also spreads usage across two plans; track Codex limits alongside Claude's.
8. **Calibration**: track which findings were confirmed or dismissed.
9. **Configurable time and turn limits.**

## Platform decisions (Nov 11, topics 1-2 of the "one by one" round)
- **Delete this chat** only after topics 1-6 are folded into the plan pack and committed;
  this TODO file goes into the pack as an archive. Future planning happens in fresh chats
  that read docs/plan from the repo (long chats use up Pro limits faster).
- **Sandbox is pluggable** (backends: docker default, podman equal, cloud sandbox later,
  none = explicit opt-in for disposable machines only). The runner talks to a backend
  interface, never to Docker directly.
- **The owner is mostly on Mac**, but setup must work for other people: macOS first
  (Docker Desktop or Colima), then Linux (Docker Engine/Podman), then Windows (WSL2).
  Build the image for both Apple Silicon (arm64) and Intel (amd64).
- **The sandbox lives wherever the runner runs, not where the front door is**:
  local skill/plugin/CLI/local connector → the user's machine; remote connector or own
  service → a server that can run containers (a VPS) or a cloud sandbox provider; free
  PaaS tiers (Render/Vercel) can't run containers; CI bench → GitHub Actions Linux runners.
- **Supervised mode nuance**: the editor assistant itself is the worker and runs under its
  own app's permissions, not in Vesper's sandbox; Vesper's gates and reviewers still run sandboxed.
- **Write docs/SETUP.md** (per platform + per usage mode) after topics 3-6 settle.
- **Config file (topic 3, agreed)**: two levels. Personal `~/.config/vesper/config.toml`
  (brains, sandbox, limits, defaults, tools per role, paths) + project `vesper.toml` in
  the repo (stack, hosting, extra checks; committed). Project wins on project matters,
  personal on personal ones, command flags win for one run. NO secrets in either file
  (Keychain / secrets file readable only by the sandbox). `vesper setup` wizard writes it
  and walks through the sandbox and logins; `vesper config show` prints effective values
  and their source. Brains referenced by purpose names (e.g. strong/fast), never hard-wired
  to one company.
- **Any AI as the brain (topic 4, agreed)**:
  - The core talks to **brain adapters**, never to a vendor. Each adapter declares
    capabilities: edit files, run shell, strict output (schema), model/effort choice, usage
    reporting, sandbox login method. The core adapts (e.g. tolerant parser when no schema).
  - **One AI is enough by default.** Reviewer independence = fresh context + read-only
    copy + no access to worker reasoning + own checklist. A reviewer on a different AI is
    optional (the owner will use Codex via ChatGPT).
  - **v1.0 brains = kinds 1 and 2**: (1) the host assistant the user is talking to
    (supervised, via commands or the connector, no extra login); (2) agent CLIs started
    in the sandbox: Claude Code, Codex CLI, Gemini CLI. Kind 3 (raw APIs and local
    models via a built-in agent loop) comes after v1.0.
  - **Brains are named by purpose in the config** (`[brains.strong]`, `[brains.fast]`,
    `[brains.reviewer]` with `use = "<adapter>"` and `model`). Roles reference these names.
  - **Sandbox login per adapter**: Claude Code uses `claude setup-token` (only for automatic
    mode in the sandbox; the Mac keeps the normal login in Keychain); Codex uses its login
    file or an API key; Gemini CLI uses its key or login (verify at implementation). The
    setup wizard detects installed CLIs and only asks for what's used.
- **Doors (topic 5, agreed)**: one engine, many doors sharing the same runs.
  - v1.0 doors: command line, skill, Claude Code plugin/marketplace, LOCAL MCP connector
    (stdio), Python tool install (uv/pipx), sandbox image on GHCR, `vesper open` (shows plans
    and wireframes in the browser).
  - After v1.0: full local dashboard, remote MCP connector + service mode (`vesper serve`:
    job queue, timers, notifications), GitHub integration (issue label → plan → PR),
    Homebrew, kind-3 brains.
  - **The AI can never approve on the owner's behalf, enforced by the program in every
    door**: approving a plan, applying a patch, accepting a security risk, merging a repair
    need a human confirmation the AI can't produce (a command the human runs, a connector
    confirmation shown directly to the human, or a dashboard button). Today this is only text
    in the skill.

## Update 2026-11-17
Commit b7da4d1 analysed and folded into the plan (see appendix-b section 4). Depth names full/focused/skip replace light/standard/full tiers; plan-critique attestation is a protected human action; specialist evals become the per-role bench via brain adapters; Superpowers-format phase plans added.
