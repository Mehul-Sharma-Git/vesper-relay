---
title: Failure-mode catalogue by category
tags: [review, security, correctness, performance, accessibility]
last_checked: 2026-11-21
sources: [https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html, https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_Cheat_Sheet.html, https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html, https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS, https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html, https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html, https://www.w3.org/TR/WCAG22/]
licence: Our own words; no third-party text quoted
---
# Failure-mode catalogue by category

Each entry says what the defect looks like in a diff, how to prove it (the repro to put in the
finding) and what a fix looks like. A blocker needs a repro: the input, the request or the steps
that show the failure, not only a suspicion.

## Authorization and object ownership

Look for handlers that load an object by an ID from the URL or body and act on it without
checking that it belongs to the signed-in user or their team. Listing endpoints that filter by
user in the UI but not in the query. Admin actions guarded only by a hidden button. Repro: sign
in as user A, request user B's object ID (`GET /items/42`, `PATCH`, `DELETE`) and show it
succeeds. Fix: scope every query by owner (`WHERE id = ? AND owner_id = ?`) on the server, and
return 404 rather than 403 so IDs cannot be probed.

## Injection (SQL, shell, template, path)

Look for strings built from input and passed to a database, a shell, a template engine or a file
path: `fmt.Sprintf` or template literals inside SQL, `exec` with a joined command line, `innerHTML`
or `dangerouslySetInnerHTML` with user text, `filepath.Join(base, userInput)` without checking the
result stays under the base. Repro: send `' OR '1'='1`, `; id`, `<img src=x onerror=alert(1)>` or
`../../etc/passwd` and show the effect. Fix: parameterised queries, argument lists without a
shell, auto-escaping templates, and a resolved-path prefix check.

## CSRF, CORS and Origin checks

A site that keeps the session in a cookie is open to cross-site request forgery: another site
can make the browser send a state-changing request with the user's cookie. Look for POST, PUT,
PATCH and DELETE handlers with cookie sessions and no CSRF token and no Origin check. Look for
CORS that reflects any Origin with `Access-Control-Allow-Credentials: true`, or `*` on an API
that uses cookies. Repro: send the state-changing request with `Origin: https://evil.example`
and the user's cookie, and show it succeeds. Fix: check the Origin (or Referer) header against
an allow list on every state-changing request, add a CSRF token for forms, set `SameSite=Lax` or
`Strict` on the session cookie as defence in depth, and allow CORS only for named origins.

## Secrets in logs and responses

Look for logging whole requests, headers, environment variables or config structs; error
messages that include connection strings; tokens in URLs (they end up in access logs and the
Referer header); API keys in frontend bundles. Repro: trigger the log line and show the secret
in the output. Fix: log an allow list of fields, redact `Authorization`, cookies and anything
named like key, token, secret or password, and keep secrets server side.

## Race conditions

Look for check-then-act sequences without a transaction or lock: read a balance then write it,
check a username is free then insert it, read a version then update without comparing it. Shared
maps or slices written from several goroutines without a mutex. Repro: two concurrent requests
(or two tabs) that both pass the check; for Go, `go test -race` output. Fix: one atomic
statement (`UPDATE ... WHERE version = ?` and check rows affected), a unique constraint, or a
transaction at the right isolation level; guard shared memory with a mutex or a channel.

## Retries and idempotency

Look for payment, email, order or job-creation endpoints that a client or a proxy may retry,
with no idempotency key; frontends that send twice on a double click; background jobs that redo
side effects after a crash. Repro: send the same create request twice and show two records or
two emails. Fix: an idempotency key stored with a unique constraint, disabling the button while
a request is in flight, and jobs that record completion before or atomically with the side
effect.

## N+1 queries

Look for a loop over rows that runs a query per row: loading each item's owner, tags or counts
one at a time, often hidden behind an ORM relation or a helper called inside the loop. Repro:
count the queries for a list of 1 and of 100 items; the count grows with the list. Fix: one
query with a join or `WHERE id IN (...)`, or a batched loader, and an index on the join column.

## Unbounded input and output

Look for request bodies read without a size limit, lists without pagination, uploads without a
size or type limit, loops whose length comes from the request, regular expressions with nested
quantifiers run on user text. Repro: send a 50 MB body or `?limit=1000000` and show the memory
or time it takes. Fix: `http.MaxBytesReader` or a body-size limit in the framework, a maximum
page size enforced on the server, upload limits, and timeouts on every outbound call.

## Error leakage

Look for raw error strings, stack traces, SQL errors or file paths returned to the client;
different messages for "no such user" and "wrong password"; debug modes left on. Repro: send
malformed input and show the internal detail in the response. Fix: log the detail with a
request ID on the server, return a generic message with that ID, and give the same answer for
every failed sign-in.

## Stale UI state

Look for frontends that keep a copy of server data and never refresh it after a mutation, cache
keys that do not include the user or the filters, optimistic updates with no rollback on error,
forms that keep old values after a successful save, and two tabs overwriting each other's edits.
Repro: change data in one tab and show the other still offers the old value, or make the server
fail and show the UI claims success. Fix: invalidate or refetch after mutations (RTK Query tags),
roll back optimistic changes on error, and send a version with updates so stale writes fail.

## Accessibility regressions

Look for clickable `div` or `span` elements instead of buttons and links, removed focus outlines,
inputs without labels, icons without accessible names, colour as the only signal, modals that do
not trap and return focus, and content that appears on hover only. Repro: the axe-core rule ID
and element, or the keyboard steps that get stuck. Fix: native elements first, visible focus,
labels tied to inputs, and ARIA only where no native element fits.
