"""Render wireframes to PNG and report overflow issues."""
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

src, dpr = Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 1
CHECK = """() => {
  const issues = [];
  for (const el of document.querySelectorAll('.phone, .laptop, .box, .btn, .todo, .li, .sticky, .dialog, .status')) {
    if (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)
      issues.push(el.className + ' :: ' + el.textContent.trim().slice(0, 40));
  }
  return issues;
}"""
with sync_playwright() as p:
    b = p.chromium.launch()
    for name in ("A-tabs", "B-picker", "C-grouped"):
        page = b.new_page(viewport={"width": 1250, "height": 900}, device_scale_factor=dpr)
        page.goto((src / f"{name}.html").as_uri())
        page.wait_for_timeout(200)
        print(name, page.evaluate(CHECK))
        page.locator(".sheet").screenshot(path=str(src / f"{name}.png"))
        page.close()
    b.close()
