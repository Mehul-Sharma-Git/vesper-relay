/* Optional JS behavior check. Start the app on loopback, then pass its URL. */
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import vm from 'node:vm';

const base = process.argv[2];
if (!base) throw new Error('Pass the URL of a fresh Stockroom instance.');

class Element {
  constructor() {
    this.value = '';
    this.textContent = '';
    this.disabled = false;
    this.dataset = {};
    this.children = [];
    this.listeners = new Map();
  }
  addEventListener(name, handler) { this.listeners.set(name, handler); }
  setAttribute() {}
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  focus() { this.focused = true; }
  querySelector(selector) {
    const id = selector.match(/data-item-id="([^"]+)"/)?.[1];
    return this.children.find(child => child.dataset.itemId === id)?.children[1];
  }
  fire(name) { return this.listeners.get(name)({ preventDefault() {} }); }
}

const elements = new Map();
const element = name => {
  if (!elements.has(name)) elements.set(name, new Element());
  return elements.get(name);
};
element('add').reset = () => {
  element('name').value = '';
  element('room').value = 'Kitchen';
  element('quantity').value = '1';
};
element('add').reset();

let dropFirstPost = true;
const requestIds = [];
const fetchLocal = async (path, options) => {
  const result = await fetch(new URL(path, base), options);
  if (options.method === 'POST') {
    requestIds.push(JSON.parse(options.body).requestId);
    if (dropFirstPost) {
      dropFirstPost = false;
      await result.arrayBuffer();
      throw new TypeError('Simulated network loss after commit');
    }
  }
  return result;
};
const source = await (await fetch(new URL('/app.js', base))).text();
await vm.runInNewContext(source, {
  document: { getElementById: element, createElement: () => new Element() },
  fetch: fetchLocal,
  crypto: webcrypto,
  URLSearchParams
});
assert.match(element('feedback').textContent, /No supplies/);
element('name').value = 'Laundry basket';
element('room').value = 'Bedroom';
element('quantity').value = '2';
await element('add').fire('submit');
assert.match(element('feedback').textContent, /draft is still here/);
assert.equal(element('name').value, 'Laundry basket');
await element('add').fire('submit');
assert.equal(requestIds[0], requestIds[1]);
assert.match(element('feedback').textContent, /Item added/);
assert.equal(element('items').children.length, 1);
element('room-filter').value = 'Kitchen';
await element('room-filter').fire('change');
assert.equal(element('items').children.length, 0);
element('room-filter').value = 'Bedroom';
await element('room-filter').fire('change');
const purchase = element('items').children[0].children[1];
await purchase.fire('click');
assert.equal(element('items').children[0].children[1].textContent, 'Mark needed');
const items = await (await fetch(new URL('/api/items?status=bought', base))).json();
assert.equal(items.length, 1);
assert.equal(items[0].name, 'Laundry basket');
console.log('Frontend JS passed against real HTTP: draft survives failure, retry dedupes, filters and purchase persist.');
