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
- Todo title 1-200 chars, list name 1-40 chars, list names unique ignoring case (Unicode case folding). Todos ordered oldest first.
- Open the app by `localhost` or the laptop's IP address (for example `http://192.168.1.20:8080`); other host names are refused. Other websites cannot read, change or frame the app (api-contract.md, Browser safety).
- A list delete only goes through if the list has not changed since the user confirmed it (its revision).
- Changes from two devices: the delete guard above; everything else is last write wins, and each device catches up on reload (architecture.md, Concurrent changes).
- Deleting a todo needs no confirmation; deleting a list does.
- Stack, file layout, names: engineers decide within plan.

## Open / risks
- No authentication on the home network (accepted for v1 by D3; revisit before any hosting). Other websites in the owner's browser are refused, but anyone on that Wi-Fi can still use the app.
- Phone access depends on the laptop being on and the OS firewall allowing the port.
- Risks proposed for v1, each with its reason in architecture.md: Wi-Fi devices (A9), local programs using the loopback port (A11), two devices renaming or ticking the same thing (C5), a duplicate after a lost response (C6), two servers on one database (C8). Only the owner accepts them, by approving this plan.

## Escalate if
- Any need for accounts, hosting, sync conflict handling, or tags arises.
