---
title: Flaky-test policy
tags: [testing, flaky, reliability]
last_checked: 2026-11-21
sources: [https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html, https://playwright.dev/docs/test-retries, https://playwright.dev/docs/actionability]
licence: Our own words; no third-party text quoted
---
# Flaky-test policy

A flaky check passes and fails on the same code. It is worse than no check: workers learn to
retry instead of fix, and real failures get dismissed as noise. Vesper decides on gates, so a
flaky gate can block a good candidate or wave a bad one through.

## The policy

A gate must give the same answer three runs in a row on the same candidate. A gate that fails
once and passes on rerun is flaky until proven otherwise: record it, find the cause, and fix the
check before the next job relies on it. Never add automatic retries to hide flakiness in an
approved gate; a retry is allowed only to collect evidence (a trace on the second run).

## Common causes and fixes

Timing: fixed sleeps, or asserting before the page or server is ready. Wait for a condition (the
element is visible, the port answers, the row exists), never for a number of seconds. Playwright
locators wait for actionability on their own; prefer them over manual waits.

Shared state: tests that depend on order, a database left dirty by an earlier test, a fixed port
already in use. Give each check its own temporary directory, database file and free port, and
clean up in a finally block.

Real clocks and randomness: dates near midnight or month end, time zones, random IDs, unseeded
shuffles. Freeze the clock or pass the time in; seed every random source; set `TZ` explicitly.

Network: anything that reaches the internet. Gates run with no network in the sandbox; a check
that needs a remote service is wrong by design. Replace the service with a local stand-in.

Resource limits: a check that passes on a fast laptop and times out in the sandbox. Measure the
slowest run, keep the gate's timeout well above it, and keep the work the check does small.

## Reporting flakiness

When a gate flips, write down the candidate digest, both outcomes, both logs and the suspected
cause, and add it to the run's findings. A flaky gate is a QA defect, not a worker defect: the
worker's attempt should not count against its retry budget for it.
