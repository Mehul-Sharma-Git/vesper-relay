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
- Filter: three buttons with `aria-pressed`, labels All, Active, Done.
- Add todo: labelled input `id="new-todo"` ("New todo") + Add button; Enter submits.
- Each todo: a checkbox labelled by its title, and a Delete button ("Delete <title>").
- Status region `role="status"` announces saves and errors.

## States
Empty list ("Nothing here yet"), empty filter result, saving, validation error
(empty title), network failure (draft kept, message in status), long titles wrap.

## Accessibility
Visible labels and focus rings, 44px touch targets, keyboard reachable menu,
Escape closes the phone menu and returns focus to the toggle.
