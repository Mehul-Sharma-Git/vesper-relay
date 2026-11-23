---
title: Proving a check can fail
tags: [testing, mutation, gates, prove-it-fails]
last_checked: 2026-11-21
sources: [https://stryker-mutator.io/docs/, https://github.com/go-gremlins/gremlins, https://en.wikipedia.org/wiki/Mutation_testing]
licence: Our own words; no third-party text quoted
---
# Proving a check can fail

A check that passes is only evidence if it would have failed on broken code. Checks that cannot
fail are common: an assertion on the wrong variable, a test that never reaches its assert, a
regular expression that matches anything, a journey that catches its own exception.

## The broken variant

For each check, write the smallest change to the product that breaks exactly the behaviour the
check guards, and keep it under `checks/_broken/<CHECK_ID>/` (a small patch or replacement files).
Apply it to a copy of the seed or the solution and run the check: it must fail, and its failure
message must name the broken promise. If it passes, the check is wrong; fix it before approval.

## Choosing what to break

Break the rule, not the build: a variant that makes the code not compile proves nothing about the
check. Good variants remove a guard (delete the ownership check), invert a condition, return the
old value, skip a write, drop a header, or accept input past the limit. For a security check,
the variant is the vulnerability itself: remove the Origin check and the CSRF check must fail.

## Signs a check can never fail

It has no assertion, or only asserts that a request returned without crashing. It catches broad
exceptions and passes in the handler. It compares a value with itself or with a copy computed the
same way. It skips when a dependency is missing instead of failing. It tests a mock rather than
the code. It checks that text exists anywhere on the page rather than in the right element.

## Mutation testing at full depth

Mutation tools make many small changes automatically and report how many the tests caught
(the mutation score). Gremlins does this for Go and StrykerJS for TypeScript. At full depth run
them as optional command gates, record the score and list surviving mutants in the report.
Do not block on the score yet; a surviving mutant in security or data code is a finding to
decide on.
