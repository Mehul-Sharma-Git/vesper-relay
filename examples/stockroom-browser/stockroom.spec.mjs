import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { expect, test as base } from 'playwright/test';

const serverPath = fileURLToPath(new URL('../stockroom-app/server.py', import.meta.url));

const test = base.extend({
  baseURL: async ({}, use) => {
    const directory = await mkdtemp(join(tmpdir(), 'stockroom-browser-'));
    const server = spawn(process.env.PYTHON || 'python3', [
      '-B', serverPath, '--db', join(directory, 'stockroom.sqlite3'), '--port', '0',
    ], { stdio: ['ignore', 'pipe', 'inherit'] });
    const closed = new Promise(resolve => server.once('close', resolve));
    const lines = createInterface({ input: server.stdout });
    try {
      const [ready] = await Promise.race([
        once(lines, 'line', { signal: AbortSignal.timeout(10_000) }),
        once(server, 'error').then(([error]) => { throw error; }),
        closed.then(code => { throw new Error(`Stockroom exited before readiness (${code})`); }),
      ]);
      const url = /^READY (http:\/\/127\.0\.0\.1:\d+)$/.exec(ready)?.[1];
      if (!url) throw new Error(`Unexpected Stockroom startup output: ${ready}`);
      await use(url);
    } finally {
      lines.close();
      server.kill();
      await closed;
      await rm(directory, { recursive: true, force: true });
    }
  },
});

const nameInput = page => page.getByRole('textbox', { name: 'Item name' });
const roomInput = page => page.getByRole('combobox', { name: 'Room', exact: true });
const quantityInput = page => page.getByRole('spinbutton', { name: 'Quantity' });
const addButton = page => page.getByRole('button', { name: 'Add item' });
const roomFilter = page => page.getByRole('combobox', { name: 'Filter by room' });
const statusFilter = page => page.getByRole('combobox', { name: 'Filter by status' });
const feedback = page => page.getByRole('status');

async function openStockroom(page) {
  await page.goto('/');
  await expect(feedback(page)).toHaveText(/No supplies match/);
}

async function addSupply(page, name) {
  await nameInput(page).fill(name);
  await addButton(page).click();
  await expect(feedback(page)).toHaveText(/Item added/);
}

test.describe('phone viewport', () => {
  test.use({ viewport: { width: 320, height: 720 }, isMobile: true, hasTouch: true });

  test('stacks controls and fits a long item without horizontal scrolling', async ({ page }) => {
    await openStockroom(page);
    const name = 'W'.repeat(80);
    await addSupply(page, name);
    const row = page.getByRole('listitem').filter({ hasText: name });
    await expect(row).toBeVisible();
    const [viewport, documentWidth] = await page.evaluate(() => [
      document.documentElement.clientWidth, document.documentElement.scrollWidth,
    ]);
    expect(viewport).toBe(320);
    expect(documentWidth).toBe(viewport);

    const form = [nameInput(page), roomInput(page), quantityInput(page), addButton(page)];
    const controls = [...form, roomFilter(page), statusFilter(page), row.getByRole('button')];
    const boxes = await Promise.all(controls.map(async control => {
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      expect(box.height).toBeGreaterThanOrEqual(44);
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(viewport);
      return box;
    }));
    for (let i = 1; i < form.length; i++) {
      expect(boxes[i].y).toBeGreaterThanOrEqual(boxes[i - 1].y + boxes[i - 1].height);
    }
  });
});

test('keyboard users can add and update supplies without losing focus', async ({ page }) => {
  await openStockroom(page);
  const name = nameInput(page);
  const room = roomInput(page);
  const quantity = quantityInput(page);
  const add = addButton(page);
  const filter = statusFilter(page);
  const buy = page.getByRole('button', { name: 'Mark bought: Folding chair' });
  const unbuy = page.getByRole('button', { name: 'Mark needed: Folding chair' });
  const tabTo = async control => {
    await page.keyboard.press('Tab');
    await expect(control).toBeFocused();
  };

  await tabTo(name);
  await expect(name).toHaveCSS('outline-style', 'solid');
  expect(await name.evaluate(input => parseFloat(getComputedStyle(input).outlineWidth)))
    .toBeGreaterThan(0);
  await page.keyboard.type('Folding chair');
  for (const control of [room, quantity, add]) await tabTo(control);
  await page.keyboard.press('Enter');
  await expect(feedback(page)).toHaveText(/Item added/);
  await expect(name).toBeFocused();
  await expect(name).toHaveValue('');

  for (const control of [room, quantity, add, roomFilter(page), filter, buy]) await tabTo(control);
  await page.keyboard.press('Space');
  await expect(feedback(page)).toHaveText(/Item marked bought/);
  await expect(unbuy).toBeFocused();

  await page.keyboard.press('Shift+Tab');
  await expect(filter).toBeFocused();
  await filter.selectOption('bought');
  await expect(feedback(page)).toHaveText('');
  await tabTo(unbuy);
  await page.keyboard.press('Space');
  await expect(feedback(page)).toHaveText(/Item marked needed.*No supplies match/);
  await expect(unbuy).toHaveCount(0);
  await expect(filter).toBeFocused();
});

test('retrying a lost create response preserves the draft and avoids duplicates', async ({ page }) => {
  await openStockroom(page);
  let dropped = false;
  await page.route('**/api/items', async route => {
    if (route.request().method() !== 'POST' || dropped) return route.continue();
    dropped = true;
    const response = await route.fetch();
    // The real server commits the write; the browser never receives the reply.
    if (response.status() === 201) return route.abort('connectionreset');
    return route.fulfill({ response });
  });

  const name = nameInput(page);
  const room = roomInput(page);
  const quantity = quantityInput(page);
  await name.fill('Laundry basket');
  await room.selectOption('Bedroom');
  await quantity.fill('2');
  await addButton(page).click();
  await expect(feedback(page)).toHaveText(/draft is still here/);
  await expect(name).toHaveValue('Laundry basket');
  await expect(room).toHaveValue('Bedroom');
  await expect(quantity).toHaveValue('2');

  await addButton(page).click();
  await expect(feedback(page)).toHaveText(/Item added/);
  const rows = page.getByRole('listitem');
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText(/Laundry basket.*Bedroom · Qty 2 · needed/);
  await page.reload();
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText('Laundry basket');
});

test('a second tab sees a stale purchase conflict and can retry with the fresh state', async ({ page, context }) => {
  await openStockroom(page);
  await addSupply(page, 'Desk lamp');
  const second = await context.newPage();
  await second.goto('/');
  const buy = tab => tab.getByRole('button', { name: 'Mark bought: Desk lamp' });
  const unbuy = tab => tab.getByRole('button', { name: 'Mark needed: Desk lamp' });
  await expect(buy(second)).toBeVisible();

  await buy(page).click();
  await expect(feedback(page)).toHaveText(/Item marked bought/);
  await buy(second).click();
  await expect(feedback(second)).toHaveText(/Item changed.*try again/);
  await expect(unbuy(second)).toBeFocused();

  await unbuy(second).click();
  await expect(feedback(second)).toHaveText(/Item marked needed/);
  await page.reload();
  await expect(buy(page)).toBeVisible();
});
