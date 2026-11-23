---
title: Scenario template for acceptance checks
tags: [testing, scenarios, acceptance]
last_checked: 2026-11-21
sources: [https://cucumber.io/docs/gherkin/reference/, https://martinfowler.com/bliki/GivenWhenThen.html]
licence: Our own words; no third-party text quoted
---
# Scenario template for acceptance checks

Write each acceptance scenario before its check, in plain language the owner can read, then
turn it into a gate. One scenario guards one promise in the contract.

## The template

```
Scenario: <the promise, as the user would say it>
Requirement: <requirement ID from plan/contract.json>
Check: <check ID>
Level: unit | contract | integration | journey
Given: <the starting state: data, user, permissions, screen size>
When: <the one action under test>
Then: <the observable result, with exact values>
And not: <what must not happen: a leak, a duplicate, a crash, an error page>
Broken variant: <how the check is proven to fail; see proving-checks-fail.md>
```

## Writing good scenarios

Say what is observed, not how the code does it: "the list shows 3 items" rather than "the
reducer appends". Use real-looking data from the plan, not "foo" and "test1". State the user and
their rights, because many bugs are about the wrong user seeing or changing something. Keep one
action per scenario; a scenario with three "When" lines is three scenarios.

## The unhappy paths to cover

For every create or update promise, add scenarios for: empty input, input at the size limit and
one past it, a duplicate submit (double click, retried request), another user's object, a stale
version (two tabs), and the server being down or slow. For every list, add: zero items, one item,
and more than one page.

## From scenario to gate

The gate's name and its failure message should quote the scenario, so a failing gate tells the
worker which promise broke. A gate prints what it expected and what it saw, and exits non-zero on
any mismatch. A gate that cannot fail is not a check; prove it can fail before approval.
