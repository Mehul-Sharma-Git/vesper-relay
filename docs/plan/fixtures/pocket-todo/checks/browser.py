"""G_BROWSER: real Chromium at phone (320px) and laptop widths. Usage: browser.py CANDIDATE_DIR
Requires Python Playwright with Chromium on the gate host.

Rows of plan/acceptance.md checked here: R4 (in a real browser), R5, R7 and items A6, C1, C2, C4, C7, C9.
"Another device" is this script calling the API directly while the page is open. P3-T3b folded P2-G's
accepted findings in (findings-triage.md)."""
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
SOME_TEXT = re.compile(r"\S")


def no_horizontal_scroll(page, where=""):
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), \
        "Page scrolls horizontally" + (f" {where}" if where else "")


def list_named(base, name):
    return next(item for item in call(base, "/api/lists")[1] if item["name"] == name)


def all_titles(base):
    return [todo["title"] for item in call(base, "/api/lists")[1]
            for todo in call(base, f"/api/todos?list={item['id']}&status=all")[1]]


def todo_named(base, title):
    return next(todo for item in call(base, "/api/lists")[1]
                for todo in call(base, f"/api/todos?list={item['id']}&status=all")[1] if todo["title"] == title)


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


def local_only(page, base):
    """R4: the page loads only from its own server (no CDN, font, image or script elsewhere)."""
    foreign = []
    page.on("request", lambda request: foreign.append(request.url)
            if not (request.url.startswith(base + "/") or request.url == base) else None)
    return foreign


def writes(page):
    """Every write the page sends, as (method, path), to tell how many requests an action made."""
    sent = []
    page.on("request", lambda request: sent.append((request.method, request.url.split("/", 3)[-1]))
            if request.method in ("POST", "PATCH", "DELETE") else None)
    return sent


def fresh(page):
    """Clear the status region, so the next announcement is proved new, not left from an earlier action."""
    page.evaluate("document.querySelectorAll('[role=status]').forEach(n => { n.textContent = ''; })")


def open_menu(toggle):
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()


def touch_targets(page):
    """design.md: 44px touch targets on the phone, for buttons, text fields and each todo's checkbox row."""
    small = page.evaluate("""() => {
        const seen = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 ? r : null; };
        const out = [];
        for (const el of document.querySelectorAll('button, input[type=text], input:not([type])')) {
            const r = seen(el);
            if (r && (r.height < 44 || r.width < 44)) out.push(`${el.tagName} ${el.id || el.textContent.trim()} ${Math.round(r.width)}x${Math.round(r.height)}`);
        }
        for (const box of document.querySelectorAll('input[type=checkbox]')) {
            const label = box.labels && box.labels[0];
            const r = seen(label || box);
            if (r && r.height < 44) out.push(`checkbox row ${box.id} ${Math.round(r.height)}px high`);
        }
        return out;
    }""")
    assert not small, f"Touch targets must be at least 44px: {small}"


def phone(browser, base):
    page = browser.new_page(viewport={"width": 320, "height": 740})
    settle = track(page)
    foreign = local_only(page, base)
    sent = writes(page)
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
    expect(panel, "the phone menu starts closed").to_be_hidden()
    # R4 in a real browser: the add field's label is visible and names it.
    expect(page.locator('label[for="new-todo"]'), "the New todo label is visible").to_be_visible()
    expect(page.get_by_label("New todo", exact=True)).to_be_visible()
    settle()
    # design.md: the menu works from the keyboard, and keyboard focus is visible.
    page.keyboard.press("Tab")
    expect(toggle).to_be_focused()
    ring = page.evaluate("""() => { const s = getComputedStyle(document.activeElement);
        return (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'; }""")
    assert ring, "Keyboard focus must be visible (a focus ring on the list toggle)"
    page.keyboard.press("Enter")
    expect(toggle, "the menu opens from the keyboard").to_have_attribute("aria-expanded", "true")
    expect(panel).to_be_visible()
    page.keyboard.press("Escape")
    expect(toggle).to_have_attribute("aria-expanded", "false")

    new_todo = page.locator("#new-todo")
    # design.md States: an empty title is a validation error, said in the status region, and sends nothing.
    fresh(page)
    new_todo.fill("   ")
    new_todo.press("Enter")
    expect(status, "an empty title says why in the status region").to_have_text(SOME_TEXT)
    settle()
    assert sent == [], f"An empty title must not be sent: {sent}"
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
    touch_targets(page)

    # design.md States, C6: a network failure keeps the draft and says so; the UI never retries by itself.
    def offline(route):
        route.abort() if route.request.method == "POST" else route.continue_()

    page.route("**/api/todos", offline)
    fresh(page)
    before = len(sent)
    new_todo.fill("Offline task")
    new_todo.press("Enter")
    expect(status, "a failed Add says so in the status region").to_have_text(SOME_TEXT)
    expect(new_todo, "a failed Add keeps the draft").to_have_value("Offline task")
    settle()
    page.wait_for_timeout(500)
    assert sent[before:] == [("POST", "api/todos")], f"A failed Add must be sent once, never retried: {sent[before:]}"
    page.unroute("**/api/todos", offline)
    assert "Offline task" not in all_titles(base)
    new_todo.fill("")

    # A6: markup in a title shows as text and never runs.
    markup = '<img src=x onerror="window.__xss=1">'
    new_todo.fill(markup)
    new_todo.press("Enter")
    expect(page.get_by_role("checkbox", name=markup)).to_be_visible()
    expect(page.get_by_text(markup)).to_be_visible()
    assert page.evaluate("window.__xss") is None, "A todo title ran as markup"
    settle()  # the add's refresh is done, so the click is not dropped while the UI is busy (T26)
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
    # C4: the same for its Delete button; the reload also shows what another device added meanwhile.
    new_todo.fill("Feed cat")
    new_todo.press("Enter")
    cat = page.get_by_role("checkbox", name="Feed cat")
    expect(cat).to_be_visible()
    settle()
    assert call(base, f"/api/todos/{todo_named(base, 'Feed cat')['id']}", "DELETE")[0] == 204
    assert call(base, "/api/todos", "POST", {"listId": inbox["id"], "title": "From the laptop"})[0] == 201
    fresh(page)
    page.get_by_role("button", name="Delete Feed cat").click()
    expect(cat, "a todo another device deleted disappears when its Delete is clicked").to_have_count(0)
    expect(status).to_contain_text(ANOTHER_DEVICE)
    expect(page.get_by_role("checkbox", name="From the laptop"),
           "the recovery reloads the list (another device's new todo shows)").to_be_visible()
    settle()
    page.get_by_role("button", name="Delete From the laptop").click()
    expect(page.get_by_role("checkbox", name="From the laptop")).to_have_count(0)
    settle()

    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(panel).to_be_visible()
    expect(panel.get_by_role("button", name=re.compile("^Inbox"))).to_have_attribute("aria-current", "true")
    no_horizontal_scroll(page)
    expect(page.locator('label[for="new-list"]'), "the New list label is visible").to_be_visible()
    expect(page.get_by_label("New list", exact=True)).to_be_visible()
    touch_targets(page)
    page.keyboard.press("Escape")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(toggle).to_be_focused()

    toggle.click()
    page.locator("#new-list").fill("<b>Bold</b>")
    page.get_by_role("button", name="Add list").click()
    expect(panel.get_by_role("button", name="<b>Bold</b>")).to_be_visible()
    settle()
    # design.md: Add list keeps the phone menu open and does not change the current list.
    expect(toggle, "Add list keeps the phone menu open").to_have_attribute("aria-expanded", "true")
    expect(toggle, "Add list keeps the current list").to_contain_text("Inbox")
    # A6: a list name stays text on every surface: the picker, the toggle, the heading, a rename and the status.
    panel.get_by_role("button", name="<b>Bold</b>").click()
    expect(toggle).to_contain_text("<b>Bold</b>")
    expect(page.get_by_text("<b>Bold</b>").first).to_be_visible()
    settle()
    open_menu(toggle)
    page.get_by_role("button", name="Rename list").click()
    named = "<img src=x onerror=window.__xss=2>"
    page.locator("#rename-list").fill(named)
    page.locator("#rename-list").press("Enter")
    expect(toggle).to_contain_text(named)
    expect(panel.get_by_role("button", name=re.compile("^" + re.escape(named)))).to_be_visible()
    settle()
    assert page.evaluate("window.__xss") is None, "A list name ran as markup"
    injected = page.evaluate("document.querySelectorAll('img[src=x], b').length")
    assert injected == 0, f"A list name was inserted as markup: {injected} element(s) parsed from it"
    open_menu(toggle)
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
    # The count is the list's total, even while a filter hides its done todos.
    page.get_by_role("checkbox", name="Send report").check()
    settle()
    page.get_by_role("button", name="Active", exact=True).click()
    expect(page.get_by_role("checkbox", name="Send report")).to_have_count(0)
    settle()
    open_menu(toggle)
    page.get_by_role("button", name="Delete list").click()
    wait_for(page, lambda: len(dialogs) == 1, "Delete list did not ask for confirmation")
    assert "Office" in dialogs[0] and re.search(r"\b1\b", dialogs[0]), \
        f"Confirmation must name the list and its todo count: {dialogs[0]!r}"
    expect(toggle).to_contain_text("Office")
    assert deletes == [], f"Cancel must not send a delete: {deletes}"
    page.get_by_role("button", name="All", exact=True).click()
    settle()

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
    expect(panel.get_by_role("button", name="Rename list"), "Inbox shows no Rename list").to_have_count(0)

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
        fresh(page)
        if action == "rename":
            page.get_by_role("button", name="Rename list").click()
            page.locator("#rename-list").fill("Barn")
            page.locator("#rename-list").press("Enter")
        else:
            page.get_by_role("button", name="Delete list").click()
        expect(toggle).to_contain_text("Inbox")
        expect(status).to_contain_text(ANOTHER_DEVICE)
        if action == "rename":
            expect(page.locator("#rename-list"), "the typed rename is kept after a 404").to_have_value("Barn")
        settle()
    assert "Barn" not in [item["name"] for item in call(base, "/api/lists")[1]]

    # C9: choosing a list another device deleted (still in this picker) falls back to Inbox, says why
    # and shows Inbox's todos. Enter submits New list.
    open_menu(toggle)
    page.locator("#new-list").fill("Attic")
    page.locator("#new-list").press("Enter")
    attic = panel.get_by_role("button", name=re.compile("^Attic"))
    expect(attic, "Enter in New list adds the list").to_be_visible()
    settle()
    expect(toggle).to_contain_text("Inbox")
    gone = list_named(base, "Attic")
    assert call(base, f"/api/lists/{gone['id']}?rev={gone['rev']}", "DELETE")[0] == 204
    fresh(page)
    attic.click()
    expect(toggle, "choosing a list another device deleted falls back to Inbox").to_contain_text("Inbox")
    expect(status).to_contain_text(ANOTHER_DEVICE)
    expect(page.get_by_role("checkbox", name="Buy milk")).to_be_visible()
    settle()

    # C4, C9: ticking a todo whose list another device deleted falls back to Inbox and says why.
    open_menu(toggle)
    page.locator("#new-list").fill("Porch")
    page.get_by_role("button", name="Add list").click()
    panel.get_by_role("button", name=re.compile("^Porch")).click()
    expect(toggle).to_contain_text("Porch")
    new_todo.fill("Paint porch")
    new_todo.press("Enter")
    paint = page.get_by_role("checkbox", name="Paint porch")
    expect(paint).to_be_visible()
    settle()
    porch = list_named(base, "Porch")
    assert call(base, f"/api/lists/{porch['id']}?rev={porch['rev']}", "DELETE")[0] == 204
    fresh(page)
    paint.click()
    expect(toggle, "ticking a todo whose list another device deleted falls back to Inbox").to_contain_text("Inbox")
    expect(status).to_contain_text(ANOTHER_DEVICE)
    expect(paint).to_have_count(0)
    settle()

    # C9: a list name another device just took is refused, the app says so, and the text stays.
    assert call(base, "/api/lists", "POST", {"name": "Garage"})[0] == 201
    open_menu(toggle)
    page.locator("#new-list").fill("garage")
    page.get_by_role("button", name="Add list").click()
    expect(status).to_contain_text(re.compile("already", re.I))
    expect(page.locator("#new-list")).to_have_value("garage")
    settle()
    page.locator("#new-list").fill("")
    # C9: the same for a rename: the typed name stays in #rename-list.
    page.locator("#new-list").fill("Cellar")
    page.get_by_role("button", name="Add list").click()
    panel.get_by_role("button", name=re.compile("^Cellar")).click()
    expect(toggle).to_contain_text("Cellar")
    settle()
    assert call(base, "/api/lists", "POST", {"name": "Pantry"})[0] == 201
    open_menu(toggle)
    fresh(page)
    page.get_by_role("button", name="Rename list").click()
    page.locator("#rename-list").fill("pantry")
    page.locator("#rename-list").press("Enter")
    expect(status).to_contain_text(re.compile("already", re.I))
    expect(page.locator("#rename-list"), "the typed rename is kept after a 409").to_have_value("pantry")
    settle()
    # design.json: 320px holds a 40-character name in the picker, the toggle and the status region.
    longest = "W" * 40
    open_menu(toggle)
    page.locator("#new-list").fill(longest)
    page.get_by_role("button", name="Add list").click()
    expect(panel.get_by_role("button", name=re.compile("^" + longest))).to_be_visible()
    settle()
    no_horizontal_scroll(page, "with a 40-character list name in the open picker and the status region")
    panel.get_by_role("button", name=re.compile("^" + longest)).click()
    expect(toggle).to_contain_text("W" * 10)
    settle()
    no_horizontal_scroll(page, "with a 40-character list name current")
    open_menu(toggle)
    panel.get_by_role("button", name=re.compile("^Inbox")).click()
    expect(toggle).to_contain_text("Inbox")
    settle()
    open_menu(toggle)
    page.keyboard.press("Escape")

    page.get_by_role("button", name="Delete Buy milk").click()
    expect(page.get_by_role("checkbox", name="Buy milk")).to_have_count(0)
    no_horizontal_scroll(page)
    assert not foreign, f"Only local assets: the page requested {foreign}"
    page.close()


def layouts(browser, base):
    """design.md: below 720px the picker is a menu behind the toggle; from 720px a sidebar."""
    for width, phone_layout in ((719, True), (720, False)):
        page = browser.new_page(viewport={"width": width, "height": 800})
        page.goto(base + "/")
        toggle, panel = page.locator("#list-toggle"), page.locator("#list-panel")
        if phone_layout:
            expect(toggle, f"below 720px the list toggle shows ({width}px)").to_be_visible()
            expect(panel, f"below 720px the menu starts closed ({width}px)").to_be_hidden()
        else:
            expect(toggle, f"from 720px the sidebar shows, not the toggle ({width}px)").to_be_hidden()
            expect(panel, f"from 720px the sidebar shows, not the toggle ({width}px)").to_be_visible()
        no_horizontal_scroll(page, f"at {width}px")
        page.close()


def laptop(browser, base):
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    settle = track(page)
    foreign = local_only(page, base)
    sent = writes(page)
    dialogs, answer = [], {"accept": False}

    def on_dialog(dialog):
        dialogs.append(dialog.message)
        dialog.accept() if answer["accept"] else dialog.dismiss()

    page.on("dialog", on_dialog)
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
    # The laptop has the filters, and a todo can be reopened; both reach the server.
    new_todo.fill("Staple handouts")
    new_todo.press("Enter")
    handouts = page.get_by_role("checkbox", name="Staple handouts")
    expect(handouts).to_be_visible()
    settle()
    page.get_by_role("button", name="Active", exact=True).click()
    expect(slides, "laptop: the Active filter hides done todos").to_have_count(0)
    expect(handouts).to_be_visible()
    page.get_by_role("button", name="Done", exact=True).click()
    expect(slides).to_be_visible()
    expect(handouts).to_have_count(0)
    page.get_by_role("button", name="All", exact=True).click()
    settle()
    slides.uncheck()
    expect(slides).not_to_be_checked()
    settle()
    assert todo_named(base, "Print slides")["done"] is False, "laptop: reopening a todo must reach the server"
    slides.check()
    settle()
    assert todo_named(base, "Print slides")["done"] is True, "laptop: completing a todo must reach the server"
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
    # C7: the same for filters: the Active reply is held while the owner chooses Done, then released.
    held, pattern = [], re.compile(r"/api/todos\?(.*&)?status=active(&|$)")
    page.route(pattern, hold)
    page.get_by_role("button", name="Active", exact=True).click()
    wait_for(page, lambda: held, "Choosing Active did not load the todos")
    page.get_by_role("button", name="Done", exact=True).click()
    expect(slides).to_be_visible()
    for route in held:
        route.continue_()
    page.unroute(pattern, hold)
    settle()
    page.wait_for_timeout(300)
    expect(page.get_by_role("button", name="Done", exact=True)).to_have_attribute("aria-pressed", "true")
    expect(slides).to_be_visible()
    expect(handouts, "an older filter reply never shows under a newer filter").to_have_count(0)
    page.get_by_role("button", name="All", exact=True).click()
    settle()
    # Deleting a todo needs no confirmation (decisions.md); renaming and deleting the list work here too.
    before = len(dialogs)
    page.get_by_role("button", name="Delete Staple handouts").click()
    expect(handouts).to_have_count(0)
    settle()
    assert len(dialogs) == before, "laptop: deleting a todo must not ask for confirmation"
    page.get_by_role("button", name="Rename list").click()
    page.locator("#rename-list").fill("Studio")
    page.locator("#rename-list").press("Enter")
    expect(panel.get_by_role("button", name=re.compile("^Studio"))).to_be_visible()
    settle()
    assert "Studio" in [item["name"] for item in call(base, "/api/lists")[1]], "laptop: a rename must reach the server"
    page.get_by_role("button", name="Delete list").click()
    wait_for(page, lambda: len(dialogs) == before + 1, "laptop: Delete list did not ask for confirmation")
    settle()
    assert not [item for item in sent if item[0] == "DELETE" and item[1].startswith("api/lists/")], \
        "laptop: Cancel must not send a delete"
    answer["accept"] = True
    page.get_by_role("button", name="Delete list").click()
    expect(panel.get_by_role("button", name=re.compile("^Inbox"))).to_have_attribute("aria-current", "true")
    expect(panel.get_by_role("button", name=re.compile("^Studio"))).to_have_count(0)
    settle()
    assert "Studio" not in [item["name"] for item in call(base, "/api/lists")[1]], "laptop: a list delete must reach the server"

    panel.get_by_role("button", name=re.compile("^Inbox")).click()
    expect(page.get_by_role("checkbox", name=re.compile("^Call bank"))).to_be_checked()
    no_horizontal_scroll(page)
    assert not foreign, f"Only local assets: the page requested {foreign}"
    page.close()


root = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as directory:
    with server(root, Path(directory) / "browser.sqlite3") as base, sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            phone(browser, base)
            layouts(browser, base)
            laptop(browser, base)
        finally:
            browser.close()
print("Phone (320px) and laptop browser journeys, text-only rendering and two-device behaviour passed.")
