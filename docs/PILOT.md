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

## Browser acceptance

The separate `stockroom-browser` CI job runs the shipped app in headless
Chromium with a fresh loopback server and temporary SQLite database per test.
It checks the form and list at a 320 px phone viewport, keyboard navigation and
focus after updates, a lost create response followed by an exact retry, and
recovery from a stale purchase update in a second tab. Run it locally with
Python 3.11+ and Node.js 22:

```sh
cd examples/stockroom-browser
npm install --ignore-scripts --no-package-lock
npx playwright install --only-shell chromium
npm test
```

On Ubuntu, add `--with-deps` to install Chromium's system libraries if needed.
These dependencies are only for the browser check; the coordinator still uses
the Python standard library.

## Gaps found

- Planning is a portable interactive brief and a review packet. We have yet to
  test the quality of discovery, wireframes, and second-round questions on an
  actual user-led idea in a local VS Code assistant session.
- Live provider completion was not verified here. Automatic review blocked the
  live Codex action because it could send local pilot source and task context to
  an unverified external endpoint. Claude was verified with a CLI stand-in only.
- Browser acceptance is configured for CI. This workspace's Chromium download
  returned a truncated archive, so no browser run was verified here.
- A sandbox launcher is an interface, not a bundled sandbox. Before trusting
  unattended work on private code, validate a real launcher with worker and
  gate confinement on the target machine.
- The runner uses one writer and one approved plan per project. A changed
  product contract uses a new reviewed project seeded from the accepted output.
  Multi-writer integration, a Cezar comparison, and managed dependency
  provisioning are outside this version.
