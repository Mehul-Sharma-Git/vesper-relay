"use strict";
/* Pocket Todo browser UI — direction B, list picker. No dependencies. */
(function () {
  // ---------------------------------------------------------------- transport

  class ApiFailure extends Error {
    constructor(status, message) {
      super(message);
      this.status = status; // 0 = network failure
    }
  }

  const NETWORK_MESSAGE = "Can't reach the server. Check the connection and try again.";

  async function api(method, path, body, signal) {
    const init = { method, signal, headers: { Accept: "application/json" } };
    if (body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(path, init);
    } catch (err) {
      if (err && err.name === "AbortError") throw err;
      throw new ApiFailure(0, NETWORK_MESSAGE);
    }
    if (res.status === 204) return null;
    let data = null;
    try {
      data = await res.json();
    } catch (err) {
      if (err && err.name === "AbortError") throw err;
      data = null;
    }
    if (!res.ok) {
      const msg = data && typeof data.error === "string" ? data.error : "Request failed (" + res.status + ")";
      throw new ApiFailure(res.status, msg);
    }
    return data;
  }

  const isAbort = (err) => err && err.name === "AbortError";
  const capitalise = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

  // ---------------------------------------------------------------- elements

  const $ = (id) => document.getElementById(id);
  const el = {
    topbar: document.querySelector(".topbar"),
    toggle: $("list-toggle"),
    toggleName: $("toggle-list-name"),
    panel: $("list-panel"),
    lists: $("lists"),
    listsMessage: $("lists-message"),
    newListForm: $("new-list-form"),
    newList: $("new-list"),
    newListError: $("new-list-error"),
    addList: $("add-list"),
    listActions: $("list-actions"),
    renameButton: $("rename-list-button"),
    deleteButton: $("delete-list-button"),
    renameForm: $("rename-form"),
    renameInput: $("rename-list"),
    renameError: $("rename-list-error"),
    renameSave: $("rename-save"),
    renameCancel: $("rename-cancel"),
    heading: $("list-heading"),
    filters: Array.from(document.querySelectorAll(".filter")),
    newTodoForm: $("new-todo-form"),
    newTodo: $("new-todo"),
    newTodoError: $("new-todo-error"),
    addTodo: $("add-todo"),
    status: $("status"),
    todosMessage: $("todos-message"),
    todosMessageText: $("todos-message-text"),
    todosRetry: $("todos-retry"),
    todos: $("todos"),
  };

  const phoneQuery = window.matchMedia("(max-width: 719.98px)");
  const isPhone = () => phoneQuery.matches;

  // ---------------------------------------------------------------- state

  const STORAGE_KEY = "pocket-todo.list";
  const state = {
    lists: [],           // authoritative from GET /api/lists
    listsLoaded: false,
    currentId: null,
    filter: "all",
    todos: [],
    todosKey: null,      // "listId:filter" the todos array describes
    todosState: "idle",  // idle | loading | ready | error
    todosError: "",
    pendingTodos: new Set(),
    busy: { addTodo: false, addList: false, rename: false, deleteList: false },
    menuOpen: false,
  };

  let listsSeq = 0;
  let todosSeq = 0;
  let todosController = null;

  const currentList = () => state.lists.find((l) => l.id === state.currentId) || null;
  const inboxList = () => state.lists.find((l) => l.inbox) || state.lists[0] || null;
  const todoKey = () => state.currentId + ":" + state.filter;
  const matchesFilter = (todo) =>
    state.filter === "all" || (state.filter === "done" ? todo.done : !todo.done);

  // ---------------------------------------------------------------- status

  let statusTimer = 0;
  function announce(message, kind) {
    clearTimeout(statusTimer);
    el.status.className = "status" + (kind ? " is-" + kind : "");
    // Clear first so an identical repeated message is announced again.
    el.status.textContent = "";
    statusTimer = setTimeout(() => { el.status.textContent = message; }, 50);
  }

  function setFieldError(input, errorEl, message) {
    if (message) {
      input.setAttribute("aria-invalid", "true");
      errorEl.textContent = message;
      errorEl.hidden = false;
    } else {
      input.removeAttribute("aria-invalid");
      errorEl.textContent = "";
      errorEl.hidden = true;
    }
  }

  function setBusy(button, busy) {
    // aria-busy instead of disabled so a focused button keeps focus.
    if (busy) button.setAttribute("aria-busy", "true");
    else button.removeAttribute("aria-busy");
  }

  // ---------------------------------------------------------------- rendering

  function renderHeader() {
    const list = currentList();
    const name = list ? list.name : state.listsLoaded ? "Inbox" : "Loading…";
    el.toggleName.textContent = name;
    el.heading.textContent = name;
    document.title = list ? name + " · Pocket Todo" : "Pocket Todo";
    el.listActions.hidden = !list || list.inbox;
    if (!list || list.inbox) closeRename(false);
  }

  function renderLists() {
    const active = document.activeElement;
    const focusedId = active && active.dataset && el.lists.contains(active) ? active.dataset.listId : null;

    el.lists.textContent = "";
    for (const list of state.lists) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "list-item";
      btn.dataset.listId = String(list.id);
      if (list.id === state.currentId) btn.setAttribute("aria-current", "true");

      const name = document.createElement("span");
      name.className = "list-name";
      name.textContent = list.name;
      const count = document.createElement("span");
      count.className = "list-count";
      count.textContent = String(list.active);
      const countLabel = document.createElement("span");
      countLabel.className = "visually-hidden";
      countLabel.textContent = " active";
      count.appendChild(countLabel);

      btn.append(name, count);
      li.appendChild(btn);
      el.lists.appendChild(li);
    }
    if (focusedId) {
      const again = el.lists.querySelector('[data-list-id="' + focusedId + '"]');
      if (again) again.focus();
    }
    if (!state.listsLoaded) {
      el.listsMessage.hidden = false;
      el.listsMessage.textContent = "Loading lists…";
    } else {
      el.listsMessage.hidden = true;
    }
  }

  function renderFilters() {
    for (const btn of el.filters) {
      btn.setAttribute("aria-pressed", String(btn.dataset.filter === state.filter));
    }
  }

  function showTodosMessage(text, retry) {
    el.todosMessage.hidden = false;
    el.todosMessageText.textContent = text;
    el.todosRetry.hidden = !retry;
  }

  /** focusTarget: {id, part} to restore focus after rebuild, or "new-todo". */
  function renderTodos(focusTarget) {
    const active = document.activeElement;
    if (!focusTarget && active && el.todos.contains(active)) {
      const li = active.closest("li");
      if (li) focusTarget = { id: li.dataset.todoId, part: active.dataset.part };
    }

    el.todos.textContent = "";
    el.todos.removeAttribute("aria-busy");

    if (state.todosState === "error") {
      showTodosMessage(state.todosError, true);
      return;
    }
    if (state.todosState === "idle" ||
        (state.todosState === "loading" && state.todosKey !== todoKey())) {
      showTodosMessage("Loading todos…", false);
      el.todos.setAttribute("aria-busy", "true");
      return;
    }
    if (state.todosState === "loading") el.todos.setAttribute("aria-busy", "true");

    const visible = state.todos.filter(matchesFilter);
    if (visible.length === 0) {
      const list = currentList();
      const listEmpty = state.filter === "all" || (list && list.total === 0);
      if (listEmpty) showTodosMessage("Nothing here yet", false);
      else if (state.filter === "active") showTodosMessage("No active todos — everything here is done.", false);
      else showTodosMessage("No done todos yet.", false);
    } else {
      el.todosMessage.hidden = true;
    }

    for (const todo of visible) {
      const li = document.createElement("li");
      li.className = "todo" + (todo.done ? " is-done" : "");
      li.dataset.todoId = String(todo.id);
      if (state.pendingTodos.has(todo.id)) li.setAttribute("aria-busy", "true");

      const label = document.createElement("label");
      label.className = "todo-label";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = todo.done;
      box.dataset.part = "check";
      const title = document.createElement("span");
      title.className = "todo-title";
      title.textContent = todo.title;
      label.append(box, title);

      const del = document.createElement("button");
      del.type = "button";
      del.className = "todo-delete";
      del.dataset.part = "delete";
      del.textContent = "Delete";
      del.setAttribute("aria-label", "Delete " + todo.title);

      li.append(label, del);
      el.todos.appendChild(li);
    }

    if (focusTarget === "new-todo") {
      el.newTodo.focus();
    } else if (focusTarget && focusTarget.id) {
      const li = el.todos.querySelector('[data-todo-id="' + focusTarget.id + '"]');
      const target = li && li.querySelector('[data-part="' + (focusTarget.part || "check") + '"]');
      if (target) target.focus();
      else el.newTodo.focus();
    }
  }

  function renderAll() {
    renderHeader();
    renderLists();
    renderFilters();
    renderTodos();
  }

  // ---------------------------------------------------------------- loading

  async function loadLists() {
    const seq = ++listsSeq;
    try {
      const lists = await api("GET", "/api/lists");
      if (seq !== listsSeq) return false; // a newer read superseded this one
      state.lists = Array.isArray(lists) ? lists : [];
      state.listsLoaded = true;
      const stillThere = currentList();
      if (!stillThere) {
        const inbox = inboxList();
        const changed = state.currentId !== null;
        state.currentId = inbox ? inbox.id : null;
        saveCurrent();
        if (changed) {
          // Current list vanished (deleted elsewhere): fall back to Inbox.
          renderHeader();
          renderLists();
          loadTodos();
          return true;
        }
      }
      renderHeader();
      renderLists();
      renderTodos(); // counts feed the empty-state wording
      return true;
    } catch (err) {
      if (seq !== listsSeq) return false;
      if (!state.listsLoaded) {
        el.listsMessage.hidden = false;
        el.listsMessage.textContent = "Lists could not be loaded.";
        state.todosState = "error";
        state.todosError = "Couldn't load your lists. " + (err.status === 0 ? NETWORK_MESSAGE : err.message);
        renderTodos();
      }
      announce(err.status === 0 ? NETWORK_MESSAGE : "Couldn't refresh lists: " + err.message, "error");
      return false;
    }
  }

  async function loadTodos() {
    if (state.currentId === null) return;
    if (todosController) todosController.abort();
    const controller = new AbortController();
    todosController = controller;
    const seq = ++todosSeq;
    const key = todoKey();
    const listId = state.currentId;
    const filter = state.filter;

    state.todosState = "loading";
    renderTodos();
    try {
      const todos = await api("GET", "/api/todos?list=" + encodeURIComponent(listId) +
        "&status=" + encodeURIComponent(filter), undefined, controller.signal);
      if (seq !== todosSeq) return; // stale response: ignore
      state.todos = Array.isArray(todos) ? todos : [];
      state.todosKey = key;
      state.todosState = "ready";
      renderTodos();
    } catch (err) {
      if (isAbort(err) || seq !== todosSeq) return;
      if (err.status === 404) {
        announce("That list no longer exists. Showing Inbox.", "error");
        state.currentId = null;
        loadLists().then((ok) => { if (ok) loadTodos(); });
        return;
      }
      state.todosState = "error";
      state.todosError = "Couldn't load todos. " + (err.status === 0 ? NETWORK_MESSAGE : err.message);
      renderTodos();
      announce(state.todosError, "error");
    } finally {
      if (todosController === controller) todosController = null;
    }
  }

  function saveCurrent() {
    try {
      if (state.currentId !== null) localStorage.setItem(STORAGE_KEY, String(state.currentId));
    } catch (_) { /* storage unavailable: fine */ }
  }

  function restoreCurrent() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw && /^\d+$/.test(raw) ? Number(raw) : null;
    } catch (_) {
      return null;
    }
  }

  // ---------------------------------------------------------------- list menu

  function syncBarHeight() {
    document.documentElement.style.setProperty("--bar-height", el.topbar.offsetHeight + "px");
  }

  function openMenu() {
    syncBarHeight();
    state.menuOpen = true;
    el.panel.setAttribute("data-open", "");
    el.toggle.setAttribute("aria-expanded", "true");
    const current = el.lists.querySelector('[aria-current="true"]') || el.lists.querySelector("button") || el.newList;
    current.focus();
  }

  function closeMenu(returnFocus) {
    if (!state.menuOpen) return;
    state.menuOpen = false;
    el.panel.removeAttribute("data-open");
    el.toggle.setAttribute("aria-expanded", "false");
    if (returnFocus) el.toggle.focus();
  }

  el.toggle.addEventListener("click", () => {
    if (state.menuOpen) closeMenu(true);
    else openMenu();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || event.defaultPrevented) return;
    if (state.menuOpen && isPhone()) {
      event.preventDefault();
      closeMenu(true);
    }
  });

  // Tap outside the phone menu closes it.
  document.addEventListener("pointerdown", (event) => {
    if (!state.menuOpen || !isPhone()) return;
    if (el.panel.contains(event.target) || el.toggle.contains(event.target)) return;
    closeMenu(false);
  });

  // Moving to laptop width: the panel becomes the sidebar; reset menu state.
  phoneQuery.addEventListener("change", () => {
    syncBarHeight();
    if (!isPhone()) closeMenu(false);
  });
  window.addEventListener("resize", syncBarHeight);

  function switchList(id) {
    const changed = id !== state.currentId;
    state.currentId = id;
    saveCurrent();
    closeRename(false);
    renderHeader();
    renderLists();
    if (isPhone()) closeMenu(true);
    if (changed) loadTodos();
  }

  el.lists.addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-list-id]");
    if (!btn) return;
    switchList(Number(btn.dataset.listId));
  });

  // ---------------------------------------------------------------- filters

  for (const btn of el.filters) {
    btn.addEventListener("click", () => {
      if (state.filter === btn.dataset.filter) return;
      state.filter = btn.dataset.filter;
      renderFilters();
      loadTodos();
    });
  }

  el.todosRetry.addEventListener("click", async () => {
    if (!state.listsLoaded) {
      const ok = await loadLists();
      if (ok) loadTodos();
    } else {
      loadTodos();
    }
  });

  // ---------------------------------------------------------------- todos

  el.newTodo.addEventListener("input", () => {
    if (el.newTodo.getAttribute("aria-invalid")) setFieldError(el.newTodo, el.newTodoError, "");
  });

  el.newTodoForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.busy.addTodo) return; // guard duplicate submit
    const title = el.newTodo.value.trim();
    if (!title) {
      setFieldError(el.newTodo, el.newTodoError, "Enter a title for the todo.");
      announce("Enter a title for the todo.", "error");
      el.newTodo.focus();
      return;
    }
    const list = currentList();
    if (!list) {
      announce("Lists are still loading. Try again in a moment.", "error");
      return;
    }
    setFieldError(el.newTodo, el.newTodoError, "");
    state.busy.addTodo = true;
    setBusy(el.addTodo, true);
    announce("Saving…");
    try {
      const todo = await api("POST", "/api/todos", { listId: list.id, title });
      // Clear the draft only if the user hasn't typed something new meanwhile.
      if (el.newTodo.value.trim() === title) el.newTodo.value = "";
      if (state.currentId === todo.listId && state.todosKey === todoKey() && matchesFilter(todo) &&
          !state.todos.some((t) => t.id === todo.id)) {
        state.todos.push(todo);
      }
      list.active += 1;
      list.total += 1;
      renderLists();
      renderTodos();
      if (matchesFilter(todo)) {
        announce("Added “" + todo.title + "” to " + list.name + ".", "ok");
      } else {
        announce("Added “" + todo.title + "”. It is hidden by the Done filter.", "ok");
      }
      loadLists();
    } catch (err) {
      // Draft stays in the input so the user can retry.
      if (err.status === 400) setFieldError(el.newTodo, el.newTodoError, capitalise(err.message) + ".");
      if (err.status === 404) {
        announce("That list no longer exists. Your draft is kept.", "error");
        loadLists();
      } else if (err.status === 0) {
        announce("Not saved: " + NETWORK_MESSAGE + " Your draft is kept.", "error");
      } else {
        announce("Not saved: " + err.message + ". Your draft is kept.", "error");
      }
    } finally {
      state.busy.addTodo = false;
      setBusy(el.addTodo, false);
    }
  });

  el.todos.addEventListener("change", async (event) => {
    const box = event.target;
    if (!(box instanceof HTMLInputElement) || box.type !== "checkbox") return;
    const li = box.closest("li");
    const id = Number(li.dataset.todoId);
    const todo = state.todos.find((t) => t.id === id);
    const done = box.checked;
    if (!todo || state.pendingTodos.has(id)) {
      box.checked = !done; // ignore while a write is in flight
      return;
    }
    state.pendingTodos.add(id);
    li.setAttribute("aria-busy", "true");
    announce("Saving…");
    try {
      const updated = await api("PATCH", "/api/todos/" + id, { done });
      const stillThere = state.todos.find((t) => t.id === id);
      if (stillThere) stillThere.done = updated.done;
      state.pendingTodos.delete(id);
      // If the item leaves the filtered view, move focus to a neighbour.
      let focus;
      if (stillThere && !matchesFilter(stillThere) && li.contains(document.activeElement)) {
        focus = neighbourFocus(id);
        state.todos = state.todos.filter((t) => t.id !== id);
      }
      renderTodos(focus);
      announce((updated.done ? "Marked done: " : "Marked not done: ") + "“" + updated.title + "”.", "ok");
      loadLists();
    } catch (err) {
      state.pendingTodos.delete(id);
      if (err.status === 404) {
        state.todos = state.todos.filter((t) => t.id !== id);
        renderTodos(li.contains(document.activeElement) ? neighbourFocus(id) : undefined);
        announce("That todo no longer exists.", "error");
        loadLists();
      } else {
        renderTodos(); // re-renders with the unchanged state, reverting the box
        announce("Not saved: " + (err.status === 0 ? NETWORK_MESSAGE : err.message), "error");
      }
    }
  });

  function neighbourFocus(id) {
    const visible = state.todos.filter(matchesFilter);
    const idx = visible.findIndex((t) => t.id === id);
    const next = visible[idx + 1] || visible[idx - 1];
    return next ? { id: String(next.id), part: "check" } : "new-todo";
  }

  el.todos.addEventListener("click", async (event) => {
    const del = event.target.closest('button[data-part="delete"]');
    if (!del) return;
    const li = del.closest("li");
    const id = Number(li.dataset.todoId);
    const todo = state.todos.find((t) => t.id === id);
    if (!todo || state.pendingTodos.has(id)) return;
    state.pendingTodos.add(id);
    li.setAttribute("aria-busy", "true");
    setBusy(del, true);
    announce("Deleting…");
    try {
      await api("DELETE", "/api/todos/" + id);
      deleted();
      announce("Deleted “" + todo.title + "”.", "ok");
    } catch (err) {
      if (err.status === 404) {
        deleted(); // already gone: same end state
        announce("Deleted “" + todo.title + "”.", "ok");
      } else {
        state.pendingTodos.delete(id);
        renderTodos();
        announce("Not deleted: " + (err.status === 0 ? NETWORK_MESSAGE : err.message), "error");
      }
    }
    function deleted() {
      const focus = li.contains(document.activeElement) ? neighbourFocus(id) : undefined;
      state.pendingTodos.delete(id);
      state.todos = state.todos.filter((t) => t.id !== id);
      const list = state.lists.find((l) => l.id === todo.listId);
      if (list) {
        list.total = Math.max(0, list.total - 1);
        if (!todo.done) list.active = Math.max(0, list.active - 1);
      }
      renderLists();
      renderTodos(focus);
      loadLists();
    }
  });

  // ---------------------------------------------------------------- lists: create

  el.newList.addEventListener("input", () => {
    if (el.newList.getAttribute("aria-invalid")) setFieldError(el.newList, el.newListError, "");
  });

  el.newListForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.busy.addList) return;
    const name = el.newList.value.trim();
    if (!name) {
      setFieldError(el.newList, el.newListError, "Enter a name for the list.");
      announce("Enter a name for the list.", "error");
      el.newList.focus();
      return;
    }
    setFieldError(el.newList, el.newListError, "");
    state.busy.addList = true;
    setBusy(el.addList, true);
    announce("Saving…");
    try {
      const list = await api("POST", "/api/lists", { name });
      if (el.newList.value.trim() === name) el.newList.value = "";
      if (!state.lists.some((l) => l.id === list.id)) state.lists.push(list);
      announce("Created list “" + list.name + "”.", "ok");
      // Switch to the new list but keep focus in the field for adding more.
      state.currentId = list.id;
      saveCurrent();
      closeRename(false);
      renderHeader();
      renderLists();
      loadTodos();
      loadLists();
    } catch (err) {
      const msg = err.status === 409
        ? "A list named “" + name + "” already exists."
        : err.status === 0 ? NETWORK_MESSAGE : capitalise(err.message) + ".";
      if (err.status === 400 || err.status === 409) setFieldError(el.newList, el.newListError, msg);
      announce("List not created: " + msg + " Your draft is kept.", "error");
    } finally {
      state.busy.addList = false;
      setBusy(el.addList, false);
    }
  });

  // ---------------------------------------------------------------- lists: rename

  function openRename() {
    const list = currentList();
    if (!list || list.inbox) return;
    el.renameForm.hidden = false;
    el.renameButton.setAttribute("aria-expanded", "true");
    el.renameInput.value = list.name;
    setFieldError(el.renameInput, el.renameError, "");
    el.renameInput.focus();
    el.renameInput.select();
  }

  function closeRename(returnFocus) {
    if (el.renameForm.hidden) return;
    el.renameForm.hidden = true;
    el.renameButton.setAttribute("aria-expanded", "false");
    setFieldError(el.renameInput, el.renameError, "");
    if (returnFocus && !el.listActions.hidden) el.renameButton.focus();
  }

  el.renameButton.addEventListener("click", () => {
    if (el.renameForm.hidden) openRename();
    else closeRename(true);
  });
  el.renameCancel.addEventListener("click", () => closeRename(true));
  el.renameInput.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault(); // first Escape cancels rename, not the menu
      closeRename(true);
    }
  });
  el.renameInput.addEventListener("input", () => {
    if (el.renameInput.getAttribute("aria-invalid")) setFieldError(el.renameInput, el.renameError, "");
  });

  el.renameForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.busy.rename) return;
    const list = currentList();
    if (!list || list.inbox) return;
    const name = el.renameInput.value.trim();
    if (!name) {
      setFieldError(el.renameInput, el.renameError, "Enter a name for the list.");
      announce("Enter a name for the list.", "error");
      el.renameInput.focus();
      return;
    }
    if (name === list.name) {
      closeRename(true);
      return;
    }
    state.busy.rename = true;
    setBusy(el.renameSave, true);
    announce("Saving…");
    try {
      const updated = await api("PATCH", "/api/lists/" + list.id, { name });
      const target = state.lists.find((l) => l.id === updated.id);
      if (target) Object.assign(target, updated);
      closeRename(true);
      renderHeader();
      renderLists();
      announce("Renamed list to “" + updated.name + "”.", "ok");
      loadLists(); // re-sort by name
    } catch (err) {
      const msg = err.status === 409
        ? "A list named “" + name + "” already exists."
        : err.status === 0 ? NETWORK_MESSAGE : capitalise(err.message) + ".";
      if (err.status === 404) {
        closeRename(false);
        announce("That list no longer exists.", "error");
        loadLists();
      } else {
        if (err.status === 400 || err.status === 409) setFieldError(el.renameInput, el.renameError, msg);
        announce("Not renamed: " + msg, "error");
      }
    } finally {
      state.busy.rename = false;
      setBusy(el.renameSave, false);
    }
  });

  // ---------------------------------------------------------------- lists: delete

  el.deleteButton.addEventListener("click", async () => {
    if (state.busy.deleteList) return;
    const list = currentList();
    if (!list || list.inbox) return;
    const n = list.total;
    const ok = window.confirm(
      "Delete the list “" + list.name + "” and its " + n + (n === 1 ? " todo" : " todos") +
      "? This cannot be undone.");
    if (!ok) return;
    state.busy.deleteList = true;
    setBusy(el.deleteButton, true);
    announce("Deleting…");
    try {
      await api("DELETE", "/api/lists/" + list.id);
      afterDelete();
      announce("Deleted list “" + list.name + "”.", "ok");
    } catch (err) {
      if (err.status === 404) {
        afterDelete();
        announce("Deleted list “" + list.name + "”.", "ok");
      } else {
        announce("List not deleted: " + (err.status === 0 ? NETWORK_MESSAGE : err.message), "error");
      }
    } finally {
      state.busy.deleteList = false;
      setBusy(el.deleteButton, false);
    }

    function afterDelete() {
      state.lists = state.lists.filter((l) => l.id !== list.id);
      const inbox = inboxList();
      state.currentId = inbox ? inbox.id : null;
      saveCurrent();
      renderHeader();
      renderLists();
      // Focus left with the hidden Delete button: put it somewhere sensible.
      const currentBtn = el.lists.querySelector('[aria-current="true"]');
      if (isPhone() && !state.menuOpen) el.toggle.focus();
      else if (currentBtn) currentBtn.focus();
      loadTodos();
      loadLists();
    }
  });

  // ---------------------------------------------------------------- start

  async function start() {
    syncBarHeight();
    state.currentId = restoreCurrent();
    renderAll();
    const ok = await loadLists();
    if (ok) loadTodos();
  }

  start();
})();
