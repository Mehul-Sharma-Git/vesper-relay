# Choose a Vesper Relay workflow

| Mode | First artifact | Typical worker and gate |
|---|---|---|
| build | Brief, wireframes, architecture, delivery target | Frontend and backend jobs with end-to-end acceptance |
| feature | Current user flow and a proposed new one | Specialist for the affected layer with a regression check |
| bug | Expected and actual behavior, reproducible failing case | Specialist for the implicated layer with that case frozen |
| design | Existing state, proposed wireframe, responsive and error states | Product designer then frontend engineer, visual and functional checks |
| frontend | Screen, components, states, and API expectations | Frontend engineer, interaction and narrow-screen checks |
| backend | Existing callers, storage and API behavior, migration impact | Backend engineer, API and persistence tests |
| maintenance | Vesper evidence and the proposed behavior change | Backend specialist with independent baseline regression |

The planner owns the conversation and acceptance agreement. The product designer
owns layout and states. The backend engineer proposes APIs and data invariants,
the frontend reviews the API as a consumer, and QA describes how success is proven.
Assign separate roles where the work needs them. A small bug can use one writing job.
New managed runs use the [RC1 team contract](RC1.md) and each tested candidate
must pass independent review before it advances the snapshot.

Use the packet shape in [PLANNER.md](PLANNER.md). For a targeted bug, one paragraph
per plan artifact is often sufficient. Record the command, inputs, and observed
failure before writing the fix. For an ambiguous redesign, show and review a
wireframe before approval. Apply lessons from `plan/intake.json` only where relevant.

For an existing Git repo, inspect the run's `seed/`. It contains the exact
committed tree copied from HEAD. Uncommitted and ignored files stay out.
Git delivery uses `review-change`, `patch`, and the reviewed patch digest.
For a new project, use `export` and choose a new destination.

For maintenance, include the supplied check in the plan and attach it to a job:

```json
{"id":"VESPER_REGRESSION","script":"vesper_regression.py"}
```

The gate runs the frozen baseline tests against the candidate copy. Add an
independent regression for the new behavior where the baseline does not cover it.
