---
title: Go readability checklist
tags: [review, readability, go]
last_checked: 2026-11-21
sources: [https://google.github.io/styleguide/go/, https://google.github.io/styleguide/go/decisions, https://go.dev/doc/effective_go, https://go.dev/wiki/CodeReviewComments]
licence: Our own words; no third-party text quoted. The Google Go Style Guide is linked, not copied (CC-BY 3.0).
---
# Go readability checklist

A summary in our own words of what to look for when reading Go. The Google Go Style Guide
(https://google.github.io/styleguide/go/) is the reference; read its "Decisions" page for the
reasons. Readability findings are advisories unless they hide a defect.

## Clarity first

Code is read far more than written: prefer the plain version over the clever one. A function
should do one thing that its name says. Deep nesting is a smell: return early on errors and
keep the happy path at the left margin. Comments explain why, not what; exported names have doc
comments that start with the name.

## Names

Short names for short scopes (`i`, `r`, `buf`), longer names as the scope grows. No stutter:
`user.Store`, not `user.UserStore`. Package names are short, lower case, singular, with no
underscores, and never `util`, `common` or `helpers`. Receivers are one or two letters and the
same across a type's methods. Initialisms keep their case: `userID`, `HTTPClient`.

## Errors

Every error is handled or returned, never dropped with `_` without a comment saying why. Wrap
with context using `%w` (`fmt.Errorf("load order %d: %w", id, err)`) so callers can use
`errors.Is` and `errors.As`. Error strings are lower case with no final punctuation. Do not log
and return the same error; one place reports it. Do not panic for ordinary failures.

## Interfaces and types

Define interfaces where they are used, not where they are implemented, and keep them small.
Accept interfaces, return concrete types. Avoid empty interfaces and `any` where a real type
fits. Zero values should be useful; constructors only when they are not.

## Concurrency

Every goroutine has a clear owner and a way to stop (a `context.Context` or a closed channel).
Pass `ctx` as the first parameter, and never store it in a struct. Shared state is guarded by a
mutex next to the fields it guards, or replaced by channels. Tests run with `-race`.

## Tests

Table-driven tests with named cases for many inputs; `t.Run` per case. Failure messages say what
was called, with what, what came back and what was wanted (`got %v, want %v`). Use the standard
`testing` package and `cmp` for comparisons before reaching for an assertion library. Helpers
call `t.Helper()`.

## Formatting and tools

`gofmt` (or `goimports`) output is not up for discussion. `go vet` and `staticcheck` should be
clean. Imports are grouped: standard library, then third party, then local.
