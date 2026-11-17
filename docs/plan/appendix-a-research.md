# Appendix A — Research notes

Facts gathered 9–11 Nov 2026. Re-check anything marked with a date before relying on it;
record the new `last_checked` date in the knowledge pack that uses it.

## 1. Why AI design looks generic, and the remedies

- Vague requests make models return the statistical "median" of their training data:
  Inter or Roboto, indigo/purple gradients, a centred hero with three identical cards.
  Superdesign calls this "distributional convergence".
- Coding agents narrow further to what is easiest to implement.
- One prompt that mixes taste, exploration and implementation spec resolves ambiguity to
  the average.
- Remedies that sources agree on: give a specific direction and real references; keep an
  explicit avoid-list; separate taste → explore several directions → pin a design-system
  spec → build; give feedback in concrete design terms, not adjectives; verify basics
  (states, accessibility).
- In 2026 the stock shadcn/ui look is itself a recognisable "AI default", because v0 and
  many AI tools produce it. Use shadcn as a base only when re-themed.

Sources: [Superdesign: why AI design looks generic](https://superdesign.dev/blog/why-ai-design-looks-generic),
[Why your AI keeps building the same purple gradient website](https://prg.sh/ramblings/Why-Your-AI-Keeps-Building-the-Same-Purple-Gradient-Website).

## 2. Design resources

| Resource | Best at | Stack | Licence / cost | Agent interface |
| --- | --- | --- | --- | --- |
| [Anime.js v4](https://animejs.com/) | Timelines, stagger, SVG morph/paths, scroll, draggable | Vanilla JS ES modules, ~24 KB | MIT, free | None; write own v4 notes (models mostly know v3) |
| [Motion](https://motion.dev/) | React/JS/Vue transitions, layout animation, gestures, springs | `motion` npm | Core MIT; Motion+ paid (examples, 50 animated sections, Performance Doctor) | AI Kit: `npx motion-ai` installs a `/motion` skill and MCP; docs and best practices free |
| [Kokonut UI](https://github.com/kokonut-labs/kokonutui) | ~116 free animated / marketing components | React, Next, Tailwind, shadcn, Motion | MIT; Pro paid | shadcn registry + shadcn MCP; `llms.txt`, `llms-full.txt`, per-page Markdown ([MCP docs](https://kokonutui.com/docs/mcp)) |
| [Bklit UI](https://github.com/bklit/bklit-ui) | 14 chart types: area, bar, candlestick, choropleth, composed, funnel, gauge, line, live line, pie, radar, ring, scatter, sankey | React, TS, shadcn registry (visx, Motion) | Charts MIT; **Bklit Studio proprietary, exclude** | shadcn CLI; repo has AGENTS.md, llms.txt, skills/ |
| [v0](https://v0.app/docs/api/platform) | Whole React screens from a prompt | React/Next | Paid, daily quotas; data "not used for training" | Platform API `api.v0.dev`, `v0-sdk`, `@v0-sdk/ai-tools` |
| [shadcn/ui](https://ui.shadcn.com/docs/mcp) | Accessible base components; the registry most libraries use | React + Tailwind | Free | Official MCP `npx shadcn@latest mcp`, CLI, registries in `components.json` |
| [21st.dev Magic MCP](https://mcpservers.org/es/servers/21st-dev/magic-mcp) | Generates components "inspired by" the 21st.dev library | React | API key; free in beta, then limits | MCP + CLI |
| [Mobbin MCP](https://www.businesswire.com/news/home/20260511053592/en/Mobbin-Launches-MCP-Server-Giving-AI-Tools-621500-Real-App-Screens-to-Reference) | 621,500+ real app screens, 142,200+ flows | References | Paid Mobbin plans; beta | MCP |
| [UI/UX Pro Max](https://www.mintlify.com/nextlevelbuilder/ui-ux-pro-max-skill) | Searchable design knowledge (self-reported: 67 styles, 96 palettes, 57 font pairings, 24 landing patterns, 25 chart types, 99 UX rules) | Any | **Licence not stated; check before reuse** | Skill + BM25 search |
| [Impeccable](https://www.mintlify.com/pbakaus/impeccable) | Design skill with 17 commands (/audit, /critique, /polish, /normalize, /animate, /distill) and anti-patterns | Any | **Licence not stated; check before reuse** | Skill |
| Anthropic `frontend-design` skill | Design thinking before code; anti-generic list | Any | Anthropic skills repo | Skill |

Wireframe skill ideas worth reusing: JSON or HTML as the editable source of truth
(yhassy/wireframe-skill, MIT); locked low-fi tokens, 8 px grid and a separate red annotation
layer (paperclipai wireframe, MIT); render to an image and inspect before showing
(coleam00 excalidraw skill); stable region ids for targeted edits (nexu-io wireframe-sketch).

## 3. Free hosting limits (checked 11 Nov 2026)

| Host | Limits | Consequence |
| --- | --- | --- |
| [Render free](https://render.com/docs/free) | Web services sleep after 15 min without traffic, ~1 min to wake; 750 instance hours per workspace per month; **ephemeral disk, no persistent disks**; free Postgres 1 GB, **expires 30 days after creation**, no backups; free Key Value in-memory only; no free workers or cron; may restart at any time | Stateless Go API, external database, expect cold starts, no background jobs on the free tier |
| [Vercel Hobby](https://vercel.com/docs/plans/hobby) | **Personal, non-commercial use only**; functions max 300 s; 1M invocations; 100 GB fast data transfer; no persistent local disk; exceeding a limit can disable a feature for 30 days | Static React site; commercial products need another plan |

The external database provider is still an open owner decision.

## 4. Claude plan limits (checked 11 Nov 2026)

- Claude Pro has a **5-hour session limit and a weekly limit**, shared between Claude chat
  and Claude Code ([Anthropic support](https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan)).
- Model choice affects how fast limits are used ([usage limit best practices](https://support.claude.com/en/articles/9797557-usage-limit-best-practices)).
- Anthropic does not publish exact token or message numbers for Pro.
- `/usage` in Claude Code shows session and weekly % with reset times. Claude Code's
  statusline JSON exposes `rate_limits.five_hour.used_percentage`,
  `rate_limits.seven_day.used_percentage` and `resets_at` for Pro/Max users
  ([statusline docs](https://code.claude.com/docs/en/statusline)). Not documented for
  headless `claude -p` output.
- Claude Code 2.1.321 supports `--json-schema`, `--model`, `--effort`, `--output-format`,
  `--restricted`, `--tools`, `--allowedTools`, `--strict-mcp-config`, `--permission-mode`.

## 5. Frontend ecosystem facts (checked 11 Nov 2026)

- Vite 8 ships with the Rust-based Rolldown bundler ([Vite 8 announcement](https://vite.dev/blog/announcing-vite8)).
- Cloudflare acquired Astro in January 2026; Astro stays open source ([press release](https://www.cloudflare.com/press/press-releases/2026/cloudflare-acquires-astro-to-accelerate-the-future-of-high-performance-web-development/)).
- TanStack Start reached 1.0 ([comparison page](https://tanstack.com/start/latest/docs/framework/react/comparison)). Not chosen: the owner picked React Router and Redux Toolkit.
