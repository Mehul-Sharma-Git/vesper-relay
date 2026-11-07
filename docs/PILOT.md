# Stockroom pilot and gaps

Stockroom is a real, local move-in supplies app. It captures items with room and
quantity, filters by room or status, and marks items bought. Python and SQLite
run on loopback. The pilot uses synthetic data.

## Evidence

- The supervised build ran backend and frontend as two separate jobs. The
  final job reran both approved gates before export.
- The API gate started a real server and checked create, validation, exact retry
  deduplication, filters, purchase updates, stale versions, and database restart.
- The UI gate fetched real HTML, JavaScript, and CSS. It checked the form labels,
  filter controls, status region, and local asset references.
- The optional Node check runs the served frontend JavaScript against the live
  HTTP server with a simulated DOM. It injects a dropped POST response after
  the server saves and checks that the draft survives and retry creates one row.
- The replay rejects a broken backend candidate and an out-of-scope frontend
  change. The runner suite also kills the coordinator mid-job, verifies fresh
  resume, checks process-group cleanup, and tests provider switching with CLI
  stand-ins.

## Gaps found

- Planning is a portable interactive brief and a review packet. We have yet to
  test the quality of discovery, wireframes, and second-round questions on an
  actual user-led idea.
- Live provider completion was not verified here. Automatic review blocked the
  live Codex action because it could send local pilot source and task context to
  an unverified external endpoint. Claude was verified with a CLI stand-in only.
- Browser layout and real keyboard behavior remain to be checked. The available
  browser binary could not be installed in this environment.
- A sandbox launcher is an interface, not a bundled sandbox. Before trusting
  unattended work on private code, validate a real launcher with worker and
  gate confinement on the target machine.
- The runner uses one writer and one approved plan per project. A changed
  product contract uses a new reviewed project seeded from the accepted output.
  Multi-writer integration, a Cezar comparison, and managed dependency
  provisioning are outside this version.
