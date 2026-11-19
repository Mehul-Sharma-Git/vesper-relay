"""G_BROWSER: real Chromium at phone (320px) and laptop widths. Usage: browser.py CANDIDATE_DIR
Requires Python Playwright with Chromium on the gate host.

Rows of plan/acceptance.md checked here: R5, R7 and items A6, C1, C2, C4, C7, C9. "Another device" is
this script calling the API directly while the page is open."""
import os
from pathlib import Path
import re
import sys
import tempfile

for candidate in ("/opt/pw-browsers", str(Path.home() / ".cache/ms-playwright")):
    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ and Path(candidate).is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = candidate

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api import call, server
from playwright.sync_api import expect, sync_playwright

expect.set_options(timeout=4000)
ANOTHER_DEVICE = re.compile("another device", re.I)


def no_horizontal_scroll(page):
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), \
        "Page scrolls horizontally"


def list_named(base, name):
    return next(item for item in call(base, "/api/lists")[1] if item["name"] == name)


def all_titles(base):
    return [todo["title"] for item in call(base, "/api/lists")[1]
            for todo in call(base, f"/api/todos?list={item['id']}&status=all")[1]]


def wait_for(page, condition, message):
    for _ in range(40):
        if condition():
            return
        page.wait_for_timeout(100)
    raise AssertionError(message)


def track(page):
    """Count the page's open requests, so a step can wait until the UI has finished its work."""
    open_requests = [0]
    page.on("request", lambda _: open_requests.__setitem__(0, open_requests[0] + 1))
    for event in ("requestfinished", "requestfailed"):
        page.on(event, lambda _: open_requests.__setitem__(0, open_requests[0] - 1))

    def settle():
        quiet = 0
        for _ in range(100):
            quiet = quiet + 1 if open_requests[0] <= 0 else 0
            if quiet >= 3:
                return
            page.wait_for_timeout(50)
        raise AssertionError("The page kept requests open for 5 s")
    return settle


def open_menu(toggle):
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()


def phone(browser, base):
    page = browser.new_page(viewport={"width": 320, "height": 740})
    settle = track(page)
    dialogs, answer, deletes = [], {"accept": False, "before": None}, []

    def on_dialog(dialog):
        dialogs.append(dialog.message)
        before, answer["before"] = answer["before"], None
        if before:
            before()  # what another device does while this dialog is open
        dialog.accept() if answer["accept"] else dialog.dismiss()

    page.on("dialog", on_dialog)
    page.on("response", lambda response: deletes.append(response.status)
            if response.request.method == "DELETE" and "/api/lists/" in response.url else None)
    page.goto(base + "/")
    toggle, panel = page.locator("#list-toggle"), page.locator("#list-panel")
    status = page.locator('[role="status"]').first
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
    settle()
    new_todo.fill("Call bank " + "very-long-word" * 6)
    page.get_by_role("button", name="Add", exact=True).click()
    bank = page.get_by_role("checkbox", name=re.compile("^Call bank"))
    settle()
    bank.check()
    expect(bank).to_be_checked()
    settle()
    no_horizontal_scroll(page)

    # A6: markup in a title shows as text and never runs.
    markup = '<img src=x onerror="window.__xss=1">'
    new_todo.fill(markup)
    new_todo.press("Enter")
    expect(page.get_by_role("checkbox", name=markup)).to_be_visible()
    expect(page.get_by_text(markup)).to_be_visible()
    assert page.evaluate("window.__xss") is None, "A todo title ran as markup"
    page.get_by_role("button", name=f"Delete {markup}").click()
    expect(page.get_by_role("checkbox", name=markup)).to_have_count(0)
    settle()

    page.get_by_role("button", name="Active", exact=True).click()
    expect(page.get_by_role("checkbox", name="Buy milk")).to_be_visible()
    expect(bank).to_have_count(0)
    page.get_by_role("button", name="Done", exact=True).click()
    expect(page.get_by_role("checkbox", name="Buy milk")).to_have_count(0)
    expect(bank).to_be_visible()
    page.get_by_role("button", name="All", exact=True).click()
    settle()

    # C4: a todo another device deleted disappears when touched, and the app says why.
    new_todo.fill("Water plants")
    new_todo.press("Enter")
    plants = page.get_by_role("checkbox", name="Water plants")
    expect(plants).to_be_visible()
    settle()
    inbox = list_named(base, "Inbox")
    doomed = next(t for t in call(base, f"/api/todos?list={inbox['id']}&status=all")[1] if t["title"] == "Water plants")
    assert call(base, f"/api/todos/{doomed['id']}", "DELETE")[0] == 204
    plants.click()
    expect(plants).to_have_count(0)
    expect(status).to_contain_text(ANOTHER_DEVICE)
    settle()

    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(panel).to_be_visible()
    expect(panel.get_by_role("button", name=re.compile("^Inbox"))).to_have_attribute("aria-current", "true")
    no_horizontal_scroll(page)
    page.keyboard.press("Escape")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(toggle).to_be_focused()

    toggle.click()
    page.locator("#new-list").fill("<b>Bold</b>")
    page.get_by_role("button", name="Add list").click()
    expect(panel.get_by_role("button", name="<b>Bold</b>")).to_be_visible()
    settle()
    page.locator("#new-list").fill("Work")
    page.get_by_role("button", name="Add list").click()
    settle()
    panel.get_by_role("button", name=re.compile("^Work")).click()
    expect(toggle).to_contain_text("Work")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(page.get_by_role("checkbox", name="Buy milk")).to_have_count(0)
    new_todo.fill("Send report")
    new_todo.press("Enter")
    expect(page.get_by_role("checkbox", name="Send report")).to_be_visible()
    settle()

    toggle.click()
    page.get_by_role("button", name="Rename list").click()
    rename = page.locator("#rename-list")
    rename.fill("Office")
    rename.press("Enter")
    expect(toggle).to_contain_text("Office")
    settle()

    # D4: deleting a list asks first, naming the list and its todo count; Cancel keeps it.
    open_menu(toggle)
    page.get_by_role("button", name="Delete list").click()
    wait_for(page, lambda: len(dialogs) == 1, "Delete list did not ask for confirmation")
    assert "Office" in dialogs[0] and re.search(r"\b1\b", dialogs[0]), \
        f"Confirmation must name the list and its todo count: {dialogs[0]!r}"
    expect(toggle).to_contain_text("Office")
    assert deletes == [], f"Cancel must not send a delete: {deletes}"

    # C1: while the dialog is open another device adds a todo to Office. The delete is sent
    # with the old revision and refused (409), the app says so, and Office and its todos stay.
    def another_device():
        office = list_named(base, "Office")
        assert call(base, "/api/todos", "POST", {"listId": office["id"], "title": "Book room"})[0] == 201

    open_menu(toggle)
    answer.update(accept=True, before=another_device)
    page.get_by_role("button", name="Delete list").click()
    wait_for(page, lambda: len(dialogs) == 2, "Delete list did not ask again")
    wait_for(page, lambda: deletes, "The confirmed delete was never sent")
    assert deletes == [409], f"A stale delete must be refused with 409: {deletes}"
    expect(status).to_contain_text(ANOTHER_DEVICE)
    expect(page.get_by_role("checkbox", name="Book room")).to_be_visible()
    expect(toggle).to_contain_text("Office")
    settle()
    open_menu(toggle)
    page.get_by_role("button", name="Delete list").click()
    expect(toggle).to_contain_text("Inbox")
    assert len(dialogs) == 3, dialogs
    assert "Office" in dialogs[2] and re.search(r"\b2\b", dialogs[2]), \
        f"After a refused delete the confirmation must show the new count: {dialogs[2]!r}"
    assert deletes == [409, 204], deletes
    open_menu(toggle)
    expect(panel.get_by_role("button", name=re.compile("^Office"))).to_have_count(0)
    expect(panel.get_by_role("button", name="Delete list")).to_have_count(0)

    # C2: another device deletes the current list; Add keeps the draft, moves to Inbox, posts nothing.
    page.locator("#new-list").fill("Errands")
    page.get_by_role("button", name="Add list").click()
    panel.get_by_role("button", name=re.compile("^Errands")).click()
    expect(toggle).to_contain_text("Errands")
    settle()
    errands = list_named(base, "Errands")
    assert call(base, f"/api/lists/{errands['id']}?rev={errands['rev']}", "DELETE")[0] == 204
    new_todo.fill("Buy stamps")
    new_todo.press("Enter")
    expect(toggle).to_contain_text("Inbox")
    expect(new_todo).to_have_value("Buy stamps")
    expect(status).to_contain_text(ANOTHER_DEVICE)
    settle()
    page.wait_for_timeout(300)
    assert "Buy stamps" not in all_titles(base), "The draft was posted to another list"
    new_todo.fill("")

    # C9: renaming or deleting a list another device deleted falls back to Inbox and says why.
    for name, action in (("Shed", "rename"), ("Loft", "delete")):
        open_menu(toggle)
        page.locator("#new-list").fill(name)
        page.get_by_role("button", name="Add list").click()
        panel.get_by_role("button", name=re.compile(f"^{name}")).click()
        expect(toggle).to_contain_text(name)
        settle()
        gone = list_named(base, name)
        assert call(base, f"/api/lists/{gone['id']}?rev={gone['rev']}", "DELETE")[0] == 204
        open_menu(toggle)
        if action == "rename":
            page.get_by_role("button", name="Rename list").click()
            page.locator("#rename-list").fill("Barn")
            page.locator("#rename-list").press("Enter")
        else:
            page.get_by_role("button", name="Delete list").click()
        expect(toggle).to_contain_text("Inbox")
        expect(status).to_contain_text(ANOTHER_DEVICE)
        settle()
    assert "Barn" not in [item["name"] for item in call(base, "/api/lists")[1]]

    # C9: a list name another device just took is refused, the app says so, and the text stays.
    assert call(base, "/api/lists", "POST", {"name": "Garage"})[0] == 201
    open_menu(toggle)
    page.locator("#new-list").fill("garage")
    page.get_by_role("button", name="Add list").click()
    expect(status).to_contain_text(re.compile("already", re.I))
    expect(page.locator("#new-list")).to_have_value("garage")
    settle()
    page.locator("#new-list").fill("")
    page.keyboard.press("Escape")

    page.get_by_role("button", name="Delete Buy milk").click()
    expect(page.get_by_role("checkbox", name="Buy milk")).to_have_count(0)
    no_horizontal_scroll(page)
    page.close()


def laptop(browser, base):
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    settle = track(page)
    page.goto(base + "/")
    panel = page.locator("#list-panel")
    expect(panel).to_be_visible()
    expect(page.locator("#list-toggle")).to_be_hidden()
    expect(page.get_by_role("checkbox", name=re.compile("^Call bank"))).to_be_checked()
    # The sidebar switches lists, and todos can be added and completed there.
    page.locator("#new-list").fill("Desk")
    page.get_by_role("button", name="Add list").click()
    panel.get_by_role("button", name=re.compile("^Desk")).click()
    expect(panel.get_by_role("button", name=re.compile("^Desk"))).to_have_attribute("aria-current", "true")
    new_todo = page.locator("#new-todo")
    new_todo.fill("Print slides")
    new_todo.press("Enter")
    slides = page.get_by_role("checkbox", name="Print slides")
    slides.check()
    expect(slides).to_be_checked()
    settle()
    expect(page.get_by_role("checkbox", name=re.compile("^Call bank"))).to_have_count(0)
    # C7: an older reply never shows under a newer choice. Inbox's todos are held while the
    # owner switches to Desk, then released.
    inbox = list_named(base, "Inbox")
    held, pattern = [], re.compile(rf"/api/todos\?(.*&)?list={inbox['id']}(&|$)")

    def hold(route):
        held.append(route)

    page.route(pattern, hold)
    panel.get_by_role("button", name=re.compile("^Inbox")).click()
    wait_for(page, lambda: held, "Choosing Inbox did not load its todos")
    panel.get_by_role("button", name=re.compile("^Desk")).click()
    expect(page.get_by_role("checkbox", name="Print slides")).to_be_visible()
    for route in held:
        route.continue_()
    page.unroute(pattern, hold)
    settle()
    page.wait_for_timeout(300)
    expect(panel.get_by_role("button", name=re.compile("^Desk"))).to_have_attribute("aria-current", "true")
    expect(page.get_by_role("checkbox", name="Print slides")).to_be_visible()
    expect(page.get_by_role("checkbox", name=re.compile("^Call bank"))).to_have_count(0)

    panel.get_by_role("button", name=re.compile("^Inbox")).click()
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
print("Phone (320px) and laptop browser journeys, text-only rendering and two-device behaviour passed.")
