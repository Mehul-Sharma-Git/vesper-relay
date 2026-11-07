"use strict";
const find = id => document.getElementById(id);
const form = find("add");
const save = find("save");
const nameInput = find("name");
const list = find("items");
const feedback = find("feedback");
let generation = 0;
let pendingSubmission = null;

async function api(path, method = "GET", data) {
  const response = await fetch(path, {
    method,
    ...(data && {headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)})
  });
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || "Request failed.");
    error.status = response.status;
    throw error;
  }
  return result;
}

function row(item) {
  const element = document.createElement("li");
  const description = document.createElement("div");
  const name = document.createElement("strong");
  name.textContent = item.name;
  const detail = document.createElement("small");
  detail.textContent = item.room + " · Qty " + item.quantity + " · " + item.status;
  description.append(name, detail);
  const button = document.createElement("button");
  button.type = "button";
  const bought = item.status === "bought";
  button.textContent = bought ? "Mark needed" : "Mark bought";
  button.setAttribute("aria-label", button.textContent + ": " + item.name);
  button.addEventListener("click", async () => {
    button.disabled = true;
    const target = bought ? "needed" : "bought";
    try {
      await api("/api/items/" + item.id, "PATCH", {status: target, version: item.version});
      await refresh("Item marked " + target + ".", item.id);
    } catch (error) {
      if (error.status === 409) {
        await refresh("Item changed. Review it and try again.", item.id);
      } else {
        feedback.textContent = error.status ? error.message : "Could not update. Try again.";
      }
    } finally {
      button.disabled = false;
    }
  });
  element.dataset.itemId = String(item.id);
  element.append(description, button);
  return element;
}

async function refresh(message, focusItem) {
  const request = ++generation;
  const params = new URLSearchParams();
  for (const key of ["room", "status"]) {
    const value = find(key + "-filter").value;
    if (value) params.set(key, value);
  }
  try {
    const items = await api("/api/items?" + params);
    if (request !== generation) return;
    list.replaceChildren(...items.map(row));
    const empty = items.length ? "" : "No supplies match these filters.";
    feedback.textContent = [message, empty].filter(Boolean).join(" ");
    if (focusItem !== undefined) {
      (list.querySelector('[data-item-id="' + focusItem + '"] button') || find("status-filter")).focus();
    }
  } catch {
    if (request === generation) {
      feedback.textContent = [message, "Could not load supplies. Change a filter or reload to retry."]
        .filter(Boolean).join(" ");
    }
  }
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (save.disabled) return;
  const name = nameInput.value.trim();
  if (!name) {
    feedback.textContent = "Enter an item name.";
    nameInput.focus();
    return;
  }
  const body = {name, room: find("room").value, quantity: Number(find("quantity").value)};
  const identity = JSON.stringify(body);
  if (pendingSubmission?.identity !== identity) {
    pendingSubmission = {identity, requestId: crypto.randomUUID()};
  }
  save.disabled = true;
  feedback.textContent = "Saving…";
  try {
    await api("/api/items", "POST", {...body, requestId: pendingSubmission.requestId});
    pendingSubmission = null;
    form.reset();
    nameInput.focus();
    await refresh("Item added.");
  } catch (error) {
    if (error.status === 409) pendingSubmission = null;
    feedback.textContent = error.status ? error.message : "Could not save. Your draft is still here.";
  } finally {
    save.disabled = false;
  }
});

find("room-filter").addEventListener("change", () => refresh());
find("status-filter").addEventListener("change", () => refresh());
refresh();
