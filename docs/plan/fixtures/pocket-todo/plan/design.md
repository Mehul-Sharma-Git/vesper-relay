# Design handoff — direction B, list picker

## Layout
- Phone (<720px): top bar with a "☰ <current list> ▾" button. It opens a menu
  panel listing all lists with counts, a "New list" field, and Rename/Delete for
  the current list. Below the bar: filter (All · Active · Done), the add form, then todos.
- Laptop (>=720px): the same list panel is a persistent left sidebar; the toggle
  button is hidden. Main column holds filter, add form, todos.

## Controls
- List picker button: `id="list-toggle"`, `aria-expanded`, `aria-controls="list-panel"`.
- Panel `id="list-panel"`: each list is a button showing name and active count;
  current list has `aria-current="true"`.
- New list: labelled input `id="new-list"` + button "Add list"; Enter also submits.
- Rename current list: button "Rename list" reveals a labelled input `id="rename-list"`; Enter saves.
- Delete current list: button "Delete list" opens confirm() naming the list and its todo count.
- Inbox shows no Rename list / Delete list buttons.
- Choosing a list in the panel closes the phone menu; the toggle shows the current list name.
- "Add list" adds the list to the panel and keeps the phone menu open; the current list does not change.
- Saving a rename updates the toggle to the new name; the phone menu may stay open or close.
- Confirming "Delete list" removes the list and makes Inbox the current list; cancelling changes nothing.
- The delete request sends the list's `rev` from when the dialog opened. If the server answers
  409, the list stays current, the status region says "… changed on another device …", and
  the lists and the current list's todos reload, so the next "Delete list" names the new count.
- Adding a todo to a list another device deleted (404): the lists reload, Inbox becomes
  current, the typed title stays in `#new-todo` (it is not posted anywhere), and the status
  region says the list was deleted on another device.
- Completing or deleting a todo another device deleted (404): the current list reloads, the
  todo disappears, and the status region says it was deleted on another device.
- Any other 404 or 409 from a list or todo action (rename, delete, select, complete, add list):
  reload the lists and the current list's todos, make Inbox current if the current list is
  gone, keep any typed text (`#new-todo`, `#new-list`, `#rename-list`), and announce it in the
  status region: "… another device …" when something changed or was deleted elsewhere, and
  "… already …" when a list name is taken.
- Switching lists while todos are loading shows only the latest list's todos.
- Todo titles and list names always show as plain text, never as markup.
- Filter: three buttons with `aria-pressed`, labels All, Active, Done.
- Add todo: labelled input `id="new-todo"` ("New todo") + Add button; Enter submits.
- Each todo: a checkbox labelled by its title, and a Delete button ("Delete <title>").
- Status region `role="status"` announces saves and errors.

## Constraints
- No inline script or style (the server's Content-Security-Policy blocks them): all script
  in app.js, all CSS in styles.css. Set styles from script through classes or `element.style`.
- The phone layout works from 320px wide with no horizontal scroll (design.json).

## States
Empty list ("Nothing here yet"), empty filter result, saving, validation error
(empty title), network failure (draft kept, message in status), long titles wrap.

## Accessibility
Visible labels and focus rings, 44px touch targets, keyboard reachable menu,
Escape closes the phone menu and returns focus to the toggle.
