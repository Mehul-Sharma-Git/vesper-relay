# Local Builder Implementation Plan

The builder turns a human-approved product brief into a sequence of verified local snapshots. It runs without Git, a hosted coordinator, or third-party Python dependencies. Python 3.11+ on macOS or Linux is the target. The provider boundary accepts Codex, Claude Code, or a supervised local worker.

## Build and evidence

- [x] Validate dependency order, path ownership, and acceptance coverage. Make approval bind exact plan, check, and seed bytes. Test cycles, missing coverage, and edits between review and approval.
- [x] Run jobs in disposable directories. Promote a new snapshot only after independent checks, with one atomic state update. Test failed checks, cross-scope edits, mutation, two simultaneous runners, and interruption.
- [x] Add bounded provider execution, fresh prompts and isolated gate environments. Test the process protocol using CLI stand-ins. Require explicit selection of a trusted host or a user-configured sandbox launcher.
- [x] Ship a planner prompt and a real pilot that exercises server persistence, browser UI, and reproducible fault injection. Document observations and package a clean download.

## Boundaries

Planning happens with the user's preferred interactive assistant using a portable prompt. Approval stays with the user. The framework owns routing, validation, and recovery. Approval and logs live outside the writable product tree. A workspace copy and file-scope checks protect ordinary workflow integrity. OS-level enforcement requires a separate launcher. The pilot uses synthetic tasks and separate local sessions, with no deployment.

## Review focus

Check edits between review and approval, corrupted accepted state, process death during an attempt, broad provider configuration inheritance, unauthorized changes to checks, and file path escape through links. Keep the previous accepted snapshot selectable until the complete candidate passes.

## Evidence ledger

- Contract approval, dependency validation, immutable check inputs, scoped snapshots,
  runner death, and adapter contracts are covered by the runner test suite.
- Independent review reproduced directory-scope escape, verifier mutation, and a
  worker cleanup race. Regression tests now cover those failures. The launcher
  interface covers both provider and gate execution.
- The supervised Stockroom replay executes the API and UI gates and rejects two
  injected failures. The Node check exercises served frontend code against the
  running HTTP server with a simulated DOM. See PILOT.md for remaining gaps.
