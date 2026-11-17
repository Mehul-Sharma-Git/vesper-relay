"""Generate pen-and-paper wireframes for Pocket Todo directions A, B, C."""
from pathlib import Path
import sys

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

CSS = """
:root { --ink:#2a2a2a; --pencil:#6b6b6b; --red:#d0342c; --paper:#fbfaf5; --grid:#dfe6ee; }
* { box-sizing:border-box; }
body { margin:0; background:var(--paper);
  background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);
  background-size:22px 22px; color:var(--ink);
  font-family:'Patrick Hand','Caveat','Bradley Hand','Marker Felt','Segoe Print','TeX Gyre Adventor',sans-serif; }
.sheet { padding:28px 34px 36px 74px; width:1220px; }
h1 { font-family:'TeX Gyre Chorus','Bradley Hand',cursive; font-size:44px; margin:0 0 2px; font-weight:400; }
.sub { color:var(--pencil); font-size:17px; margin:0 0 22px; }
.row { display:flex; gap:64px; align-items:flex-start; }
.cap { font-size:15px; color:var(--pencil); margin:8px 0 0 4px; letter-spacing:.5px; text-transform:uppercase; }
.rough { filter:url(#rough); }
.phone { width:290px; height:540px; border:2.5px solid var(--ink); border-radius:30px; padding:30px 14px 14px; position:relative; background:#fff; }
.phone:before { content:''; position:absolute; top:11px; left:50%; width:60px; height:6px; margin-left:-30px; border:2px solid var(--ink); border-radius:4px; }
.laptop { width:640px; height:400px; border:2.5px solid var(--ink); border-radius:10px 10px 0 0; padding:12px; position:relative; background:#fff; }
.base { width:720px; height:16px; border:2.5px solid var(--ink); border-radius:0 0 14px 14px; margin-left:-40px; }
.ui { font-size:15px; }
.r { position:relative; }
.box { border:2px solid var(--ink); border-radius:5px; padding:6px 8px; background:#fff; }
.hint { color:#9a9a9a; }
.btn { border:2px solid var(--ink); border-radius:6px; padding:5px 10px; display:inline-block; background:#fff; white-space:nowrap; }
.primary { background:repeating-linear-gradient(45deg,#bdbdbd 0 1.5px,#fff 1.5px 7px); }
.flex { display:flex; gap:8px; align-items:center; }
.grow { flex:1; }
.mb { margin-bottom:10px; }
.chips span { border:2px solid var(--ink); border-radius:16px; padding:3px 10px; margin-right:4px; white-space:nowrap; }
.chips span.on, .seg span.on { background:#2a2a2a; color:#fff; }
.seg { display:inline-flex; border:2px solid var(--ink); border-radius:6px; overflow:hidden; }
.seg span { padding:3px 11px; border-right:2px solid var(--ink); }
.seg span:last-child { border-right:0; }
.todo { display:flex; align-items:center; gap:9px; padding:8px 2px; border-top:1.5px dashed #b9b9b9; }
.cb { width:18px; height:18px; border:2px solid var(--ink); border-radius:3px; display:inline-flex; align-items:center; justify-content:center; font-size:15px; line-height:1; flex:none; }
.done { text-decoration:line-through; color:#888; }
.x { color:#777; margin-left:auto; font-size:17px; }
.side { border-right:2px solid var(--ink); padding-right:10px; width:170px; }
.li { padding:6px 6px; border-radius:5px; display:flex; justify-content:space-between; }
.li.on { background:repeating-linear-gradient(-45deg,#d6d6d6 0 1.5px,#fff 1.5px 6px); outline:2px solid var(--ink); }
.count { color:var(--pencil); }
.group { border-top:2px solid var(--ink); padding-top:6px; margin-top:8px; }
.gh { display:flex; justify-content:space-between; font-size:16px; }
.pin { position:absolute; width:26px; height:26px; border-radius:50%; border:2px solid var(--red); color:var(--red); background:var(--paper);
  font-size:15px; display:flex; align-items:center; justify-content:center; font-family:'TeX Gyre Adventor',sans-serif; font-weight:700; }
.pl { left:-60px; top:50%; margin-top:-13px; }
.top { top:18px; margin-top:0; }
.pr { right:-60px; top:50%; margin-top:-13px; }
.pin:after { content:''; position:absolute; top:11px; width:26px; border-top:2px dashed var(--red); }
.pl:after { left:24px; } .pr:after { right:24px; }
.notes { margin-top:24px; display:grid; grid-template-columns:1fr; gap:6px; font-size:18px; }
.notes div { display:flex; gap:10px; }
.notes b { color:var(--red); font-family:'TeX Gyre Adventor',sans-serif; min-width:22px; }
.verdict { margin-top:20px; display:flex; gap:22px; font-size:18px; }
.sticky { background:#fff3a6; padding:10px 14px; box-shadow:2px 3px 0 rgba(0,0,0,.15); transform:rotate(-1deg); flex:1; }
.sticky.minus { background:#ffd9cf; transform:rotate(.8deg); }
.overlay { position:absolute; inset:0; background:rgba(40,40,40,.18); border-radius:28px; }
.drawer { position:absolute; left:0; top:0; bottom:0; width:76%; background:#fff; border-right:2.5px solid var(--ink); border-radius:28px 0 0 28px; padding:32px 12px 12px; }
.dialog { position:absolute; left:22px; right:22px; top:170px; background:#fff; border:2.5px solid var(--ink); border-radius:10px; padding:14px; box-shadow:4px 5px 0 rgba(0,0,0,.18); }
.status { border:2px dashed var(--red); color:var(--red); border-radius:6px; padding:5px 8px; font-size:14px; }
.small .phone { width:230px; height:430px; overflow:hidden; }
.states { display:flex; gap:40px; margin-top:6px; }
"""

SVG = """<svg width="0" height="0" style="position:absolute"><filter id="rough"><feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="7"/><feDisplacementMap in="SourceGraphic" scale="2.2"/></filter></svg>"""


def pin(n, side="l"):
    return f'<span class="pin p{side}">{n}</span>'


def todos(items):
    out = []
    for title, done in items:
        mark = "✓" if done else ""
        cls = ' class="done"' if done else ""
        out.append(f'<div class="todo"><span class="cb">{mark}</span><span{cls}>{title}</span><span class="x">✕</span></div>')
    return "".join(out)


INBOX = [("Buy milk", False), ("Call bank", True)]
ADD = '<div class="flex mb"><span class="box grow hint">New todo…</span><span class="btn primary">Add</span></div>'
SEG = '<span class="seg"><span class="on">All</span><span>Active</span><span>Done</span></span>'


def page(title, sub, body, notes, plus, minus):
    note_html = "".join(f"<div><b>{i}</b><span>{t}</span></div>" for i, t in enumerate(notes, 1))
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{title}</title><style>{CSS}</style></head><body>{SVG}<div class="sheet">
<h1>{title}</h1><p class="sub">{sub}</p>{body}
<div class="notes">{note_html}</div>
<div class="verdict"><div class="sticky">＋ {plus}</div><div class="sticky minus">－ {minus}</div></div>
</div></body></html>"""


def frames(phone, laptop):
    return f"""<div class="row"><div><div class="phone rough ui">{phone}</div><div class="cap">Phone · 375 px</div></div>
<div style="margin-left:40px"><div class="laptop rough ui">{laptop}</div><div class="base rough"></div><div class="cap">Laptop · 1280 px</div></div></div>"""


# ---------- A: tabs on top ----------
a_phone = f"""
<div class="r chips mb" style="white-space:nowrap">{pin(1)}<span class="on">Inbox</span><span>Work</span><span>Home</span><span>＋</span></div>
<div class="r mb">{pin(2)}{SEG}</div>
<div class="r">{pin(3)}{ADD}</div>
<div class="r">{pin(4)}{todos(INBOX)}</div>"""
a_laptop = f"""<span class="pin pl top">5</span><div style="width:440px;margin:6px auto">
<div class="r chips mb"><span class="on">Inbox</span><span>Work</span><span>Home</span><span>＋ New list</span></div>
<div class="r mb">{SEG}</div>{ADD}{todos(INBOX)}</div>"""
(OUT / "A-tabs.html").write_text(page(
    "A · Tabs on top", "Same content in every option: Inbox (Buy milk, Call bank ✓), Work (Send report), Home (empty)",
    frames(a_phone, a_laptop),
    ["List tabs scroll sideways; ＋ makes a new list", "Filter for the current list",
     "Add box stays at the top; Enter adds", "Tap the box to tick; ✕ deletes", "Laptop: same tabs, centred column"],
    "One tap to switch lists; everything on one screen", "Tabs overflow past ~6 lists; rename/delete hidden in a long-press"), encoding="utf-8")

# ---------- B: list picker ----------
b_phone = f"""
<div class="r flex mb">{pin(1)}<span class="btn">☰ Inbox ▾</span><span class="grow"></span><span class="hint">2</span></div>
<div class="r mb">{pin(2)}{SEG}</div>
<div class="r">{pin(3)}{ADD}</div>
<div class="r">{pin(4)}{todos(INBOX)}</div>"""
side = """<div class="side"><div style="font-size:13px;color:#777;margin-bottom:4px">LISTS</div>
<div class="li on"><span>Inbox</span><span class="count">1</span></div>
<div class="li"><span>Work</span><span class="count">1</span></div>
<div class="li"><span>Home</span><span class="count">0</span></div>
<div class="flex" style="margin-top:10px"><span class="box grow hint" style="padding:4px 6px">New list…</span><span class="btn" style="padding:3px 7px">＋</span></div></div>"""
b_laptop = f"""<div class="flex" style="align-items:stretch;height:100%">
<div class="r">{pin(5,'l').replace('pin pl','pin pl top')}{side}</div>
<div class="grow" style="padding:4px 10px 0 14px">
<div class="flex mb" style="font-size:20px"><span>Inbox</span><span class="grow"></span><span class="hint" style="font-size:14px">rename · delete (not for Inbox)</span></div>
<div class="r mb">{SEG}</div>{ADD}{todos(INBOX)}</div></div>"""

menu_open = f"""<div class="flex mb"><span class="btn">☰ Inbox ▴</span></div>
<div class="overlay"></div><div class="drawer">
<div style="font-size:13px;color:#777;margin-bottom:4px">LISTS</div>
<div class="li on"><span>Inbox</span><span class="count">1</span></div>
<div class="li"><span>Work</span><span class="count">1</span></div>
<div class="li"><span>Home</span><span class="count">0</span></div>
<div class="flex" style="margin-top:10px"><span class="box grow hint" style="padding:4px 6px">New list…</span><span class="btn" style="padding:3px 7px">＋</span></div>
<div style="margin-top:14px;border-top:1.5px dashed #bbb;padding-top:8px" class="hint">Rename list · Delete list<br>(shown for Work, Home)</div></div>"""
empty = f"""<div class="flex mb"><span class="btn">☰ Home ▾</span></div><div class="mb">{SEG}</div>{ADD}
<div style="text-align:center;margin-top:60px;color:#888;font-size:18px">Nothing here yet<br><span style="font-size:14px">Add your first todo above</span></div>"""
error = f"""<div class="flex mb"><span class="btn">☰ Work ▾</span></div><div class="mb">{SEG}</div>
<div class="flex mb"><span class="box grow">Send invoice</span><span class="btn primary">Add</span></div>
<div class="status mb">Couldn't save — is the laptop on? Your text is kept. Try again.</div>{todos([("Send report", False)])}"""
confirm = f"""<div class="flex mb"><span class="btn">☰ Work ▾</span></div><div class="mb">{SEG}</div>{todos([("Send report", False)])}
<div class="overlay"></div><div class="dialog"><div style="font-size:17px;margin-bottom:8px">Delete “Work” and its 1 todo?</div>
<div class="flex" style="justify-content:flex-end"><span class="btn">Cancel</span><span class="btn primary">Delete</span></div></div>"""
states = f"""<h2 style="font-weight:400;font-size:26px;margin:34px 0 4px">States (phone)</h2>
<div class="states small">
<div><div class="phone rough ui">{menu_open}</div><div class="cap">Menu open · Esc closes</div></div>
<div><div class="phone rough ui">{empty}</div><div class="cap">Empty list</div></div>
<div><div class="phone rough ui">{error}</div><div class="cap">Save failed</div></div>
<div><div class="phone rough ui">{confirm}</div><div class="cap">Delete list confirm</div></div></div>"""
(OUT / "B-picker.html").write_text(page(
    "B · List picker  (your pick)", "Same content in every option: Inbox (Buy milk, Call bank ✓), Work (Send report), Home (empty)",
    frames(b_phone, b_laptop) + states,
    ["Menu button shows the current list; opens the list drawer", "Filter for the current list",
     "Add box; focus stays here after adding", "Tap the box to tick; ✕ deletes (no confirm)",
     "Laptop: drawer becomes a fixed sidebar with counts"],
    "Scales to many lists; rename/delete have an obvious home", "Switching lists on phone takes 2 taps"), encoding="utf-8")

# ---------- C: grouped page ----------
c_phone = f"""
<div class="r mb">{pin(1)}{SEG}</div>
<div class="r">{pin(2)}{ADD}</div>
<div class="group r">{pin(3)}<div class="gh"><span>▾ Inbox</span><span class="count">1 / 2</span></div>{todos(INBOX)}</div>
<div class="group"><div class="gh"><span>▾ Work</span><span class="count">1 / 1</span></div>{todos([("Send report", False)])}</div>
<div class="group r">{pin(4)}<div class="gh"><span>▸ Home</span><span class="count">0</span></div></div>
<div class="hint" style="margin-top:10px">＋ New list</div>"""
c_laptop = f"""<span class="pin pl top">5</span><div style="width:470px;margin:4px auto"><div class="flex mb">{SEG}<span class="grow"></span><span class="btn">＋ New list</span></div>
<div class="flex mb"><span class="box grow hint">New todo…</span><span class="box">Inbox ▾</span><span class="btn primary">Add</span></div>
<div class="group"><div class="gh"><span>▾ Inbox</span><span class="count">1 / 2</span></div>{todos(INBOX)}</div>
<div class="group"><div class="gh"><span>▾ Work</span><span class="count">1 / 1</span></div>{todos([("Send report", False)])}</div></div>"""
(OUT / "C-grouped.html").write_text(page(
    "C · One page, grouped", "Same content in every option: Inbox (Buy milk, Call bank ✓), Work (Send report), Home (empty)",
    frames(c_phone, c_laptop),
    ["One filter applies to every list", "Add box needs a list picker (defaults to Inbox)",
     "Each list is a collapsible section with counts", "Collapsed / empty list", "Laptop: same page, centred column"],
    "See everything at once", "Long scroll; adding needs an extra 'which list' choice"), encoding="utf-8")

index = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Pocket Todo wireframes</title>
<style>body{font-family:sans-serif;margin:0;background:#fbfaf5}nav{position:sticky;top:0;background:#fff;border-bottom:1px solid #ccc;padding:10px 16px}
nav a{margin-right:16px}iframe{width:100%;height:1250px;border:0;border-bottom:1px solid #ccc}</style></head><body>
<nav><a href="#a">A · Tabs</a><a href="#b">B · Picker</a><a href="#c">C · Grouped</a></nav>
<iframe id="a" src="A-tabs.html"></iframe><iframe id="b" src="B-picker.html"></iframe><iframe id="c" src="C-grouped.html"></iframe></body></html>"""
(OUT / "index.html").write_text(index, encoding="utf-8")
print("written", sorted(p.name for p in OUT.iterdir()))
