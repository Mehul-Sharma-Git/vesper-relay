(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var state = { lists: [], current: null, status: 'all', todos: [], busy: false };
  var readSeq = 0;
  var wide = window.matchMedia('(min-width:720px)');

  function say(msg, isErr) {
    var s = $('status');
    s.textContent = msg || '';
    s.className = isErr ? 'error' : '';
  }

  async function api(method, path, body) {
    var res;
    try {
      res = await fetch(path, {
        method: method,
        headers: body ? { 'Content-Type': 'application/json' } : {},
        body: body ? JSON.stringify(body) : undefined
      });
    } catch (e) { throw new Error('Network error: could not reach the server.'); }
    if (res.status === 204) return null;
    var data = null;
    try { data = await res.json(); } catch (e) {}
    if (!res.ok) { var err = new Error((data && data.error) || 'Request failed (' + res.status + ')'); err.status = res.status; throw err; }
    return data;
  }

  function currentList() {
    return state.lists.find(function (l) { return l.id === state.current; });
  }

  function menuOpen() { return $('list-toggle').getAttribute('aria-expanded') === 'true'; }
  function setMenu(open) {
    $('list-toggle').setAttribute('aria-expanded', open ? 'true' : 'false');
    syncPanel();
  }
  function syncPanel() {
    $('list-panel').hidden = wide.matches ? false : !menuOpen();
  }
  wide.addEventListener('change', syncPanel);

  function renderLists() {
    var ul = $('list-items');
    ul.textContent = '';
    state.lists.forEach(function (l) {
      var li = document.createElement('li');
      var b = document.createElement('button');
      b.type = 'button';
      var n = document.createElement('span'); n.textContent = l.name;
      var c = document.createElement('span'); c.textContent = String(l.active);
      c.setAttribute('aria-label', l.active + ' active');
      b.append(n, c);
      if (l.id === state.current) b.setAttribute('aria-current', 'true');
      b.addEventListener('click', function () { selectList(l.id); setMenu(false); });
      li.appendChild(b);
      ul.appendChild(li);
    });
    var cur = currentList();
    var name = cur ? cur.name : '';
    $('list-toggle-name').textContent = name;
    $('current-title').textContent = name;
    $('rename-btn').hidden = $('delete-list-btn').hidden = !cur || !!cur.inbox;
    if (!cur || cur.inbox) $('rename-form').hidden = true;
  }

  function renderTodos(loaded) {
    var ul = $('todos');
    ul.textContent = '';
    state.todos.forEach(function (t) {
      var li = document.createElement('li');
      if (t.done) li.className = 'done';
      var cb = document.createElement('input');
      cb.type = 'checkbox'; cb.id = 'todo-' + t.id; cb.checked = t.done;
      cb.addEventListener('change', function () { toggle(t, cb); });
      var lab = document.createElement('label');
      lab.htmlFor = cb.id; lab.textContent = t.title;
      var del = document.createElement('button');
      del.type = 'button'; del.textContent = 'Delete';
      del.setAttribute('aria-label', 'Delete ' + t.title);
      del.addEventListener('click', function () { removeTodo(t); });
      li.append(cb, lab, del);
      ul.appendChild(li);
    });
    var e = $('empty');
    if (loaded && !state.todos.length) {
      e.hidden = false;
      e.textContent = state.status === 'all' ? 'Nothing here yet' : 'Nothing here yet — no ' + state.status + ' todos in this list';
    } else e.hidden = true;
  }

  async function refreshLists() {
    state.lists = await api('GET', '/api/lists');
    if (!currentList()) state.current = state.lists.length ? state.lists[0].id : null;
    renderLists();
  }

  async function loadTodos() {
    var seq = ++readSeq;
    var listId = state.current, status = state.status;
    if (listId == null) return;
    try {
      var data = await api('GET', '/api/todos?list=' + encodeURIComponent(listId) + '&status=' + status);
      if (seq !== readSeq) return;
      state.todos = data;
      renderTodos(true);
    } catch (e) {
      if (seq !== readSeq) return;
      say(e.message, true);
    }
  }

  function selectList(id) {
    state.current = id;
    state.todos = [];
    renderLists();
    renderTodos(false);
    say('');
    loadTodos();
  }

  async function guarded(fn) {
    if (state.busy) return;
    state.busy = true;
    try { await fn(); } catch (e) {
      if (e.status === 404 || e.status === 409) {
        try { await refreshLists(); await loadTodos(); } catch (_) {}
        say(e.status === 409 && /already/i.test(e.message) ? e.message
          : e.status === 409 ? 'This list changed on another device. Check it and try again.'
          : 'That was deleted on another device.', true);
      } else { say(e.message, true); }
    }
    finally { state.busy = false; }
  }

  async function toggle(t, cb) {
    var want = cb.checked;
    await guarded(async function () {
      try {
        await api('PATCH', '/api/todos/' + t.id, { done: want });
      } catch (e) { cb.checked = !want; throw e; }
      say('Saved');
      await Promise.all([refreshLists(), loadTodos()]);
    });
  }

  async function removeTodo(t) {
    await guarded(async function () {
      await api('DELETE', '/api/todos/' + t.id);
      say('Deleted “' + t.title + '”');
      await Promise.all([refreshLists(), loadTodos()]);
      $('new-todo').focus();
    });
  }

  $('add-form').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var input = $('new-todo');
    var title = input.value.trim();
    if (!title) { say('Please enter a title.', true); input.focus(); return; }
    guarded(async function () {
      say('Saving…');
      await api('POST', '/api/todos', { listId: state.current, title: title });
      input.value = '';
      say('Saved');
      await Promise.all([refreshLists(), loadTodos()]);
    }).then(function () { input.focus(); });
  });

  $('new-list-form').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var input = $('new-list');
    var name = input.value.trim();
    if (!name) { say('Please enter a list name.', true); input.focus(); return; }
    guarded(async function () {
      await api('POST', '/api/lists', { name: name });
      input.value = '';
      await refreshLists();
      say('List “' + name + '” added');
    });
  });

  $('rename-btn').addEventListener('click', function () {
    var f = $('rename-form');
    f.hidden = !f.hidden;
    if (!f.hidden) { $('rename-list').value = currentList().name; $('rename-list').focus(); $('rename-list').select(); }
  });

  $('rename-form').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var name = $('rename-list').value.trim();
    if (!name) { say('Please enter a list name.', true); return; }
    guarded(async function () {
      await api('PATCH', '/api/lists/' + state.current, { name: name });
      $('rename-form').hidden = true;
      await refreshLists();
      say('Renamed to “' + name + '”');
      $('rename-btn').focus();
    });
  });

  $('delete-list-btn').addEventListener('click', function () {
    var cur = currentList();
    if (!cur || cur.inbox) return;
    if (!window.confirm('Delete list "' + cur.name + '" and its ' + cur.total + ' todo(s)?')) return;
    guarded(async function () {
      try {
        await api('DELETE', '/api/lists/' + cur.id + '?rev=' + cur.rev);
      } catch (e) { throw e; }
      state.current = null;
      await refreshLists();
      var inbox = state.lists.find(function (l) { return l.inbox; });
      if (inbox) state.current = inbox.id;
      renderLists();
      say('Deleted list “' + cur.name + '”');
      await loadTodos();
    });
  });

  document.querySelectorAll('.filters button').forEach(function (b) {
    b.addEventListener('click', function () {
      state.status = b.dataset.status;
      document.querySelectorAll('.filters button').forEach(function (o) {
        o.setAttribute('aria-pressed', o === b ? 'true' : 'false');
      });
      loadTodos();
    });
  });

  $('list-toggle').addEventListener('click', function () { setMenu(!menuOpen()); });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && menuOpen() && !wide.matches) {
      setMenu(false);
      $('list-toggle').focus();
    }
  });

  (async function init() {
    syncPanel();
    say('Loading…');
    try {
      await refreshLists();
      say('');
      await loadTodos();
    } catch (e) { say(e.message, true); }
  })();
})();
