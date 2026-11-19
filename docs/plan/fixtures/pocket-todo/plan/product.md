# Product: Pocket Todo

## User and journey
One person (the owner) keeps personal todos. On the laptop or on the phone over
home Wi-Fi, they open the app, pick a list (Inbox, Work, Home…), type a todo and
press Add. Later they tick it done, filter to Active to see what is left, or
delete it. They create, rename and delete their own lists.

## Scope
- Lists: Inbox always exists. Create, rename, delete other lists. Deleting a list
  deletes its todos after the user confirms, and only if the list has not changed since.
- Two devices at once: a change made on one device never silently undoes or loses one made
  on the other; the app says when something changed on another device.
- Other websites open in the same browser cannot read, change or frame the todos.
- Todos: title + done state, in exactly one list. Add, mark done/not done, delete.
- Filter the current list by All / Active / Done.
- Data persists in SQLite on the laptop and survives a restart.

## Excluded
Accounts/login, hosting, offline mode, due dates, tags, reordering, sharing.

## Delivery target
A local Python (standard library) + SQLite server with a browser UI, exported
to a new folder. Run: `python3 server.py --db todos.sqlite3 [--host 0.0.0.0] [--port 8080]`,
then open `http://localhost:8080` on the laptop or `http://<laptop IP>:8080` on the phone.
Run one server per database file.
