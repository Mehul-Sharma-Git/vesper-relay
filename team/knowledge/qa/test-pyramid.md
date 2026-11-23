---
title: Test pyramid and who owns each level
tags: [testing, strategy, ownership]
last_checked: 2026-11-21
sources: [https://martinfowler.com/articles/practical-test-pyramid.html, https://testing.googleblog.com/2015/04/just-say-no-to-more-end-to-end-tests.html]
licence: Our own words; no third-party text quoted
---
# Test pyramid and who owns each level

Many fast, narrow tests at the bottom; fewer, slower, broader tests at the top. Each level
catches a different kind of mistake, and a failure at a low level points at the cause, while a
failure at the top only says that something, somewhere, broke.

## Unit tests (builders own them)

A unit test exercises one function, component or handler with its collaborators replaced or
kept in memory. The frontend and backend engineers write and run these with their code; QA does
not write them, but QA reads them to decide what still needs a broader check. Aim: runs in
milliseconds, no network, no shared state, one reason to fail.

## Contract tests (QA owns them)

A contract test checks that a service keeps the promises written in its interface: every route
in the OpenAPI spec, each status code, required fields, types, and the errors it returns for bad
input. Generate the happy paths from the spec, then add malicious requests by hand: missing auth,
another user's ID, oversized bodies, wrong content type, unknown fields. Contract tests are
where a frontend and a Go backend agree, so they catch most integration breaks cheaply.

## Integration tests (QA owns them)

An integration test runs real pieces together: the handler with its real database (SQLite file
or a disposable Postgres), the migration files, the queue. Use it for things a mock would hide:
SQL that does not compile, a missing index that makes a query time out, a transaction that does
not roll back, a unique constraint the code forgot about.

## End-to-end journeys (QA owns a few)

A journey drives the real app in a browser (Playwright) the way a user would: sign in, create a
thing, see it listed, edit it, delete it. Keep them few, one per critical promise in the
contract, because they are slow and the most likely to be flaky. A journey proves the pieces are
wired together; it is a poor place to test edge cases, which belong lower down.

## Choosing the level for a risk

Write `checks/test-strategy.md` as a table: risk, the lowest level that can catch it, check ID.
Push every check as low as it can go and still observe the failure. A rule inside one function
is a unit test; a rule about what the API accepts is a contract test; a rule about data surviving
a restart is an integration test; a rule about what the user sees after a click is a journey.
An inverted pyramid (mostly browser tests) is slow, flaky and hard to diagnose: treat it as a
finding.
