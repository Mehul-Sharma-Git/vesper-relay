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
- One SQLite connection per request, opened with a 5 s busy timeout and `PRAGMA foreign_keys = ON`;
  each write runs in one `BEGIN IMMEDIATE` transaction, so a todo change and its list's `rev`
  change commit together, and simultaneous writes from two devices wait instead of failing.
- The server sets its file-creation mask to owner-only (`os.umask(0o077)`) before opening the
  database, so the database and its journal files are readable and writable by the owner only.

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
| A10 | Other accounts on the laptop | the database file | the database and journal files are owner-only (mode 600) | G_API |
| A11 | Any program or account on the laptop using the loopback port | everything, like the owner's browser | proposed risk: no login in v1; a local program can do what the owner can | none: proposed risk |
| A12 | Someone on the home network watching or flooding traffic (with `--host 0.0.0.0`) | read todos in transit (plain HTTP); slow the app | proposed risk: outside the threat model (decisions.md); no TLS in v1 | none: proposed risk |
| A13 | Another web app the owner ran earlier on the same address and port (its service worker or cached files) | run its code on the app's origin | proposed risk: outside the threat model; give Pocket Todo its own port | none: proposed risk |

## Concurrent changes (two actors on the same record)
| # | What happens at once | Handling | Gate |
|---|---|---|---|
| C1 | Device A confirms "Delete list" while device B adds, completes or deletes one of its todos, or renames it (even keeping the same count) | the delete carries the list's `rev`; any change raises `rev`; a stale delete gets 409 and deletes nothing; the UI announces it and reloads | G_API, G_BROWSER |
| C2 | Device A adds a todo to a list that device B deleted | 404; the UI reloads the lists, makes Inbox current, keeps the draft in the field and does not post it anywhere | G_API, G_BROWSER |
| C3 | Device A acts on a todo or list id that was deleted and might be reused | ids are never reused (AUTOINCREMENT), so a stale id gets 404 and never reaches a new record | G_API |
| C4 | Device A completes or deletes a todo that device B deleted | 404; the UI reloads the current list and announces it | G_API, G_BROWSER |
| C5 | Two devices rename the same list, or set the same todo done and not done | last write wins: the earlier rename or done state is overwritten without a message; each device shows the result on its next reload | none: proposed risk (one owner; only a name or a tick is overwritten, never a todo or a list) |
| C6 | An Add whose response is lost after the server saved it, then retried by the owner | the UI never retries a write by itself; a duplicate the owner creates by retrying is visible and deletable | none: proposed risk (one owner, visible, reversible) |
| C7 | An older read finishing after a newer one (switch from Inbox to Work while Inbox's todos are still loading) | the UI keeps only the reply to its latest request for the todo view, so Inbox's todos never show under Work | G_BROWSER (holds the older reply) |
| C9 | Device A renames, deletes or selects a list, or completes or deletes a todo, that device B already deleted; or adds or renames a list to a name B just took | 404 or 409; the UI reloads, makes Inbox current if its list is gone, keeps the typed text and says why in the status region | G_API, G_BROWSER |
| C10 | Both devices write at the same moment | the busy timeout makes one wait; both writes succeed | G_API (20 parallel adds) |
| C8 | Two server processes on one database file | not supported: run one server | none: proposed risk (documented in product.md) |

## First slice
J_API (backend, server.py) then J_UI (frontend, static files) against this API.
