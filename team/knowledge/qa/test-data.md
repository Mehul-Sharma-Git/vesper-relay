---
title: Test data guide
tags: [testing, data, fixtures]
last_checked: 2026-11-21
sources: [https://martinfowler.com/bliki/ObjectMother.html, https://owasp.org/www-project-web-security-testing-guide/]
licence: Our own words; no third-party text quoted
---
# Test data guide

Bad test data hides bugs: if every name is "test" and every list has two items, the check never
meets a long name, an empty list or a second page.

## Principles

Make data look real: names with accents and apostrophes, long titles, prices with cents, dates in
other time zones. Take examples from `plan/product.md` and the design's representative content.
Never copy real personal data from production into a check; invent it.

Make each check create what it needs and nothing else. A check that relies on data left by
another check fails when run alone or in a different order. Build data with small helper
functions that fill sensible defaults and let the check override the one field it cares about.

Keep data small and visible. A reader should see in the check itself which values matter. A
large shared fixture file that every check depends on becomes impossible to change.

## Values worth including

Empty and whitespace-only strings; the maximum length and one past it; emoji and characters
outside the Basic Multilingual Plane; right-to-left text; HTML and script fragments
(`<script>alert(1)</script>`) to catch missing escaping; SQL fragments (`' OR '1'='1`) to catch
string-built queries; zero, negative and very large numbers; dates on February 29th, at daylight
saving changes and at the end of a month.

## Users and ownership

Most serious bugs are about who may see or change what. Always create at least two users with
their own data, and check that user A cannot read, list, change or delete user B's objects by
guessing an ID. Add an anonymous visitor and, when roles exist, the least privileged role.

## Databases in checks

Use a fresh database per check: a temporary SQLite file, or a disposable Postgres schema created
and dropped by the check. Apply the real migrations rather than a hand-written schema, so a broken
migration fails the check. Seed through the app's own API when you can, so the data is valid by
the app's own rules.
