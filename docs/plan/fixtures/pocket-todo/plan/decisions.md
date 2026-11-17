# Decisions

## Confirmed by owner
- D1 Audience: one person (the owner), using a phone browser and a laptop browser.
- D2 Data per todo: title and done state, plus user-defined lists/categories (e.g. Work, Home). Add, complete, delete, filter active/done.

- D3 Data lives on the owner's laptop (local server + SQLite); phone uses it over home Wi-Fi while the laptop is on. No hosting, no login.
- D4 Lists: each todo in exactly one list; an Inbox list always exists; lists can be renamed; deleting a list deletes its todos after confirmation.

- D5 Layout: direction B, a list picker menu (drawer on phone, sidebar on laptop).

## Delegated defaults (planner)
- Inbox cannot be deleted or renamed (it is the always-present list).
- Server listens on 127.0.0.1 by default; `--host 0.0.0.0` exposes it to the home network for the phone. No login: anyone on that Wi-Fi can use it.
- Todo title 1-200 chars, list name 1-40 chars, list names unique ignoring case. Todos ordered oldest first.
- Deleting a todo needs no confirmation; deleting a list does.
- Stack, file layout, names: engineers decide within plan.

## Open / risks
- No authentication on the home network (accepted for v1 by D3; revisit before any hosting).
- Phone access depends on the laptop being on and the OS firewall allowing the port.

## Escalate if
- Any need for accounts, hosting, sync conflict handling, or tags arises.
