# Architecture

Python 3.11 standard library HTTP server (`server.py`) + SQLite + static
`index.html`, `styles.css`, `app.js`. No third-party packages, no build step.
The API is in api-contract.md (canonical).

## Launch
`python3 server.py --db PATH [--host 127.0.0.1] [--port 8080]`. `--port 0` picks a
free port. After binding, print exactly one line `READY http://HOST:PORT` and flush.
Creates tables and the Inbox list on first start.

## Data
- lists(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, fold TEXT UNIQUE (the case-folded
  name), inbox INTEGER 0/1, rev INTEGER)
- todos(id INTEGER PRIMARY KEY AUTOINCREMENT, list_id FK ON DELETE CASCADE, title TEXT,
  done INTEGER, created INTEGER)
- One SQLite connection per request with `PRAGMA foreign_keys = ON`; each write runs in one
  `BEGIN IMMEDIATE` transaction, so a todo change and its list's `rev` change commit together.

## Reachability (who and what can reach the app)
| # | Actor or channel | Could read or change | Handling | Gate |
|---|---|---|---|---|
| A1 | The owner's browser, laptop or phone, at `localhost` or the laptop's IP | everything | intended use | G_API, G_BROWSER |
| A2 | Another website in the owner's browser sending a form or `fetch` | write todos and lists | Origin must match, writes need a JSON body (403, 415) | G_API |
| A3 | Another website that rebinds its own host name to the laptop | read and write | `Host` must be `localhost` or an IP (403) | G_API |
| A4 | Another website reading the JSON | read todos | no CORS header, so the browser blocks the read | G_API |
| A5 | Another website framing the page to trick a click | delete or change | `frame-ancestors 'none'`, `X-Frame-Options: DENY` | G_API |
| A6 | A todo title or list name containing markup or script | run script in the app | the UI renders text only (`textContent`), CSP `default-src 'self'` | G_BROWSER |
| A7 | A request for any other path (`/server.py`, `../`, the database) | read server files | only `/`, `/app.js`, `/styles.css` are served (404) | G_API |
| A8 | An oversized or malformed body | crash or exhaust the server | 64 KB limit (413), JSON validation (400) | G_API |
| A9 | Other devices on the home Wi-Fi when started with `--host 0.0.0.0` | everything | proposed risk (D3): no login in v1; loopback is the default | none: proposed risk |
| A10 | Other programs running as the owner on the laptop | the database file | proposed risk: same user, outside the app's control | none: proposed risk |

## Concurrent changes (two actors on the same record)
| # | What happens at once | Handling | Gate |
|---|---|---|---|
| C1 | Device A confirms "Delete list" while device B adds, completes or deletes one of its todos, or renames it (even keeping the same count) | the delete carries the list's `rev`; any change raises `rev`; a stale delete gets 409 and deletes nothing; the UI announces it and reloads | G_API, G_BROWSER |
| C2 | Device A adds a todo to a list that device B deleted | 404; the UI reloads the lists, makes Inbox current, keeps the draft in the field and does not post it anywhere | G_API, G_BROWSER |
| C3 | Device A acts on a todo or list id that was deleted and might be reused | ids are never reused (AUTOINCREMENT), so a stale id gets 404 and never reaches a new record | G_API |
| C4 | Device A completes or deletes a todo that device B deleted | 404; the UI reloads the current list and announces it | G_API, G_BROWSER |
| C5 | Two devices rename the same list | last write wins; each device shows the final name on its next reload | none: proposed risk (one owner, no data lost) |
| C6 | An Add whose response is lost after the server saved it, then retried by the owner | the UI never retries a write by itself; a duplicate the owner creates by retrying is visible and deletable | none: proposed risk (one owner, visible, reversible) |
| C7 | An older read finishing after a newer one in the UI | the UI ignores a reply that is older than the latest request for the same view | none: proposed risk (corrected by the next reload; timing cannot be gated reliably) |
| C8 | Two server processes on one database file | not supported: run one server | none: proposed risk (documented in product.md) |

## First slice
J_API (backend, server.py) then J_UI (frontend, static files) against this API.
