"""G_BROWSER: real Chromium at phone and laptop widths. Usage: browser.py CANDIDATE_DIR
Requires Python Playwright with Chromium on the gate host."""
import os
from pathlib import Path
import re
import sys
import tempfile

for candidate in ("/opt/pw-browsers", str(Path.home() / ".cache/ms-playwright")):
    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ and Path(candidate).is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = candidate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import server
from playwright.sync_api import expect, sync_playwright

expect.set_options(timeout=4000)


def no_horizontal_scroll(page):
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), \
        "Page scrolls horizontally"


def phone(browser, base):
    page = browser.new_page(viewport={"width": 375, "height": 740})
    dialogs, answer = [], {"accept": False}

    def on_dialog(dialog):
        dialogs.append(dialog.message)
        dialog.accept() if answer["accept"] else dialog.dismiss()

    page.on("dialog", on_dialog)
    page.goto(base + "/")
    toggle, panel = page.locator("#list-toggle"), page.locator("#list-panel")
    expect(toggle).to_be_visible()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(toggle).to_contain_text("Inbox")
    expect(page.get_by_text("Nothing here yet")).to_be_visible()

    new_todo = page.locator("#new-todo")
    new_todo.fill("Buy milk")
    new_todo.press("Enter")
    expect(page.get_by_role("checkbox", name="Buy milk")).to_be_visible()
    expect(new_todo).to_be_focused()
    expect(new_todo).to_have_value("")
    new_todo.fill("Call bank " + "very-long-word" * 6)
    page.get_by_role("button", name="Add", exact=True).click()
    bank = page.get_by_role("checkbox", name=re.compile("^Call bank"))
    bank.check()
    expect(bank).to_be_checked()
    no_horizontal_scroll(page)

    page.get_by_role("button", name="Active", exact=True).click()
    expect(page.get_by_role("checkbox", name="Buy milk")).to_be_visible()
    expect(bank).to_have_count(0)
    page.get_by_role("button", name="Done", exact=True).click()
    expect(page.get_by_role("checkbox", name="Buy milk")).to_have_count(0)
    expect(bank).to_be_visible()
    page.get_by_role("button", name="All", exact=True).click()

    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(panel).to_be_visible()
    page.keyboard.press("Escape")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(toggle).to_be_focused()

    toggle.click()
    page.locator("#new-list").fill("Work")
    page.get_by_role("button", name="Add list").click()
    panel.get_by_role("button", name=re.compile("^Work")).click()
    expect(toggle).to_contain_text("Work")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(page.get_by_role("checkbox", name="Buy milk")).to_have_count(0)
    new_todo.fill("Send report")
    new_todo.press("Enter")
    expect(page.get_by_role("checkbox", name="Send report")).to_be_visible()

    toggle.click()
    page.get_by_role("button", name="Rename list").click()
    rename = page.locator("#rename-list")
    rename.fill("Office")
    rename.press("Enter")
    expect(toggle).to_contain_text("Office")

    # D4: deleting a list asks first, naming the list and its todo count; Cancel keeps it.
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()
    page.get_by_role("button", name="Delete list").click()
    for _ in range(40):
        if dialogs:
            break
        page.wait_for_timeout(100)
    assert len(dialogs) == 1, "Delete list did not ask for confirmation"
    assert "Office" in dialogs[0] and re.search(r"\b1\b", dialogs[0]), \
        f"Confirmation must name the list and its todo count: {dialogs[0]!r}"
    expect(toggle).to_contain_text("Office")
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()
    answer["accept"] = True
    page.get_by_role("button", name="Delete list").click()
    expect(toggle).to_contain_text("Inbox")
    assert len(dialogs) == 2, dialogs
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()
    expect(panel.get_by_role("button", name=re.compile("^Office"))).to_have_count(0)
    expect(panel.get_by_role("button", name="Delete list")).to_have_count(0)
    page.keyboard.press("Escape")

    page.get_by_role("button", name="Delete Buy milk").click()
    expect(page.get_by_role("checkbox", name="Buy milk")).to_have_count(0)
    page.close()


def laptop(browser, base):
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(base + "/")
    expect(page.locator("#list-panel")).to_be_visible()
    expect(page.locator("#list-toggle")).to_be_hidden()
    expect(page.get_by_role("checkbox", name=re.compile("^Call bank"))).to_be_checked()
    no_horizontal_scroll(page)
    page.close()


root = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as directory:
    with server(root, Path(directory) / "browser.sqlite3") as base, sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            phone(browser, base)
            laptop(browser, base)
        finally:
            browser.close()
print("Phone and laptop browser journeys passed.")
