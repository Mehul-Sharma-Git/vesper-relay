# Appendix C — Future direction: a personal assistant (do NOT implement yet)

The owner's long-term goal is to grow Vesper from a website builder into a general
assistant ("Jarvis"): marketing research, bookings, calls and more. This file records the
agreed direction so today's work doesn't block it. No task in phases 1–5 implements it.

## The path every request takes

| Stop | Job | Vesper today |
| --- | --- | --- |
| Front door | Where the owner talks to it (chat, voice, phone) | Borrowed: Claude Code + `/vesper-relay` |
| Router | Picks the workflow (website, research, booking…) | The skill text; owner picks the mode |
| Memory | What it knows about the owner and past work | Run-level learning only |
| Planner | Questions, then the plan | Built (software) |
| Owner's OK | Locks the exact plan | Built (digest) |
| Orchestrator (runner) | Runs the plan step by step, retries, recovers | Built, code only, one worker |
| Workflow | The recipe per kind of job | Software modes only |
| Specialist agents | Workers with one job each | Software roles only |
| Tools | Run code, web search, email, calendar, phone | Missing |
| Safe workspace | Copies and a locked room | Copies yes; sandbox from phase 1 |
| Checks | Proof the work is right | Code tests only |
| Independent reviewer | Second pair of eyes | Built |
| Ask before acting | Owner OK before anything irreversible | Patch apply only |
| Hand-over | Result plus what was verified | Built (export, patch) |
| Learning | Better rules over time | Partial |

Background services: always-on process, phone notifications, secrets vault, audit log.

## Agreed architecture rules

- **One generic orchestrator; branch at the workflow level.** Website/code, research,
  bookings… each bring their own agents, tools and checks. Planner, approval, sandbox,
  check runner, reviewer, ask-before-acting and learning are shared. Refactor the runner to
  separate this generic core from code-specific parts (file inventories, patches) when the
  second workflow starts.
- **Agents per kind of work, not per task.** Reuse general roles (researcher, writer,
  analyst); add a specialist only for special knowledge, tools or risk rules (e.g. a caller).
- **Process proportional to risk.** Light (reminders, lookups: just do it and log it),
  standard (drafts, reports: short plan, check, hand-over), full (code, money, messages as
  the owner, bookings, calls: the whole flow, always asking before acting).
- **The program's job shifts** from file referee to action referee: tool permissions per
  agent, approval before irreversible actions, secrets vault, spend and rate limits, audit
  log, and treating email and web content as data, never instructions.

## Front door options

| Option | How | Good for | Limits |
| --- | --- | --- | --- |
| A: Vesper as a connector | Expose Vesper's commands as an MCP server; the Claude app (phone, desktop, web) calls them | Start runs, approve plans, check status from anywhere | Acts only when messaged; needs a reachable host with login for phone use |
| B: Own assistant service | Always-on service on a home server or cloud machine with its own address, HTTPS and login; Claude via API as the brain; voice, Telegram or web front ends | Always on, timers, voice, push approvals | Hosting, security and API budget |

Suggested order after phase 5: fix remaining gaps → separate the generic core → add a
research workflow (low risk) → Option A connector → background service and phone approvals →
real-world actions (bookings, calls) last, with strict approval levels. Calls need a phone
service, a real-time voice agent, an AI disclosure, and attention to call-recording consent rules.
