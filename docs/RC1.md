# Vesper Relay RC1

Use [the installation guide](USAGE.md) to set up Codex or Claude Code. Both
clients use the same bundled playbooks and local runner. Existing managed
runs keep their approved contracts. New runs started with `vesper start`
require the team contract.

## Who owns the work

| Role | Owns | Included skills |
|---|---|---|
| Lead planner | User interview, decision log, approval packet, and routing | Discovery and scoping |
| UI/UX designer | User journeys, wireframes, comparative visual directions, design handoff | Interaction design, optional WebGL and motion |
| Frontend engineer | Component and state plan, API consumption, accessible and performant UI | Frontend delivery, optional React or WebGL and motion |
| Backend engineer | Interface and storage contracts, data invariants, migrations and compatibility | Backend delivery, optional SQLite or PostgreSQL |
| QA | Reproduction, independent acceptance scenarios, fixtures and evidence | Acceptance evidence and relevant stack skills |
| Independent reviewer | Requirements, regressions, scope and blast radius, maintainability, security, and applicable design evidence | Candidate review and scoped security review |
| Technical lead, when needed | Cross-layer contract conflicts, integration order, and architecture tradeoffs | Interface coordination and relevant data or security skills |

The planner interviews the owner and records the proposed boundary. The designer
provides a wireframe. The backend drafts contracts before approval when they affect
the flow. The frontend reviews the contracts and proposes the component, state,
and integration approach. QA drafts checks before implementation. Engineers can
reuse an existing form, component, or API convention when it fits the approved
behavior. Changes to direction, user-visible behavior, permissions, or material
complexity go back to the owner.

`vesper roles` lists the catalogue. Use `vesper roles --role designer --skill
webgl-motion` to inspect a profile. With a provider configured, `consult`
runs the chosen specialist in a separate read-only baseline copy and returns a
handoff. For example, ask backend to propose the API, then include that draft in
frontend's consultation task so it can review the interface as a consumer. The
editor assistant can also coordinate consultations directly. Only frontend and
backend own writing jobs in the contract, and the runner admits one writer at a
time. Candidate review uses `review-candidate`.

## Design and review

The designer compares two to four distinct compositions using the same
representative task and content. For example, a Stockroom page could compare a
dense ledger grouped by room with a purchase queue ordered by urgency. The
handoff explains why the chosen layout fits, how it adapts to a narrow screen,
and what happens after errors, retries, and keyboard actions. A visual treatment
such as glass, tactile surfaces, or 3D needs a clear purpose and a usable
fallback. Agree on representative browser checks before implementing.

Use `"design_required": true` in the contract for a feature or frontend change
that changes visual direction. Frontend jobs in `build` and `design` modes
already trigger the design gate. Put the wireframe in `plan/design.md` and the
comparison in `plan/design.json`. The JSON has `audience`, `primary_task`,
`representative_content`, `chosen`, `reason`, `avoid`, `narrow`, `wide`, `focus`,
`motion`, `browser_evidence`, a `states` object, and `directions` entries with
`name`, `composition`, `benefit`, and `tradeoff`.

`submit` runs the approved checks and returns `awaiting_review` for a passing
candidate. Use `review-candidate --provider codex --launcher /path/to/launcher`
or choose `claude`. In supervised mode, open the returned review copy in an
independent editor session, have it follow `review.md`, save its JSON outside
that copy, and submit `review-candidate --report FILE --attest-independent`.
The verdict binds to the attempt, baseline and candidate digests. A blocking
finding returns the job for correction. The accepted snapshot advances only
after the review passes. See [launcher interfaces](../START-HERE.md) for
automatic execution with `run` or a different `--reviewer-provider`.

## Repair Vesper's own source

Use `vesper --project RUN incidents` to investigate failures and `vesper learn`
to inspect local history. A failed app check can lead to a product fix. A provider
or launcher failure can lead to an environment fix. A confirmed Vesper-owned
bug can go through source repair. The assistant can author the reproducer as
part of diagnosis. Review it and the allowed files before authorizing the run.
The reproducer receives the source snapshot path, exits `1` for the defect, and
exits `0` once fixed. Use a distinct exit code for setup errors.

```sh
vesper repair --idea 'Describe the confirmed Vesper defect' \
  --repro /path/to/repro.py --path builder/runner.py
vesper --project REPAIR_RUN review
vesper --project REPAIR_RUN repair-run --digest APPROVED_PLAN_DIGEST \
  --provider codex --reviewer-provider claude --launcher /path/to/launcher --commit
```

Use the project path returned by `repair`. Optionally pass `--from-project RUN`
to attach its latest recorded incident. Use the provider you have configured.
The runner reproduces the failure on pinned Vesper source, runs the bounded
repair, checks the reproducer and frozen baseline suite, and launches a separate
reviewer. With `--commit` it writes the verified tree to a local `vesper/repair/…`
branch in the Vesper repository and records the commit in `vesper learn`. The
active source checkout and index stay intact. Publishing or merging a repair
branch is a separate action. For a supervised repair, run `repair-reproduce`
before approval, then use the confined launcher for `submit` and
`review-candidate`. Use `review-change` and `repair-commit --digest PATCH_DIGEST`
to commit the reviewed patch. Validate launcher isolation on your machine before
using the repair path with private source or credentials.
