"""Free activities (flashcards, bingo, memory game) made by the activity machine
in the repo mahibrahim89-wq/learnwithian-activities.

The workflow clones that repo to /tmp/acts first. Only episodes that Claude
approved (column "activities_ok" = yes in the extras sheet) are shown.

Adds:
- a "Free games & flashcards" box on each episode page (under the free page box),
- the same activities at the top of free.html,
- activities.xml: an RSS feed that Pinterest reads to make Pins by itself.
Safe to run many times. If the activities repo is missing, nothing changes.
"""
import csv
import email.utils
import html
import io
import json
import os
import re
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTS = Path(os.environ.get("ACTS_DIR", "/tmp/acts"))
SITE = "https://learnwithian.com"
RAW = "https://raw.githubusercontent.com/mahibrahim89-wq/learnwithian-activities/main"
IMG = ROOT / "img" / "activities"
SEEN = ROOT / "data" / "activities_seen.json"
NAMES = {"flashcards": "Word flashcards", "bingo": "Bingo game", "memory": "Memory game"}
ORDER = ["bingo", "memory", "flashcards"]

CSS = """<style>
.actbox { background: #fff; border: 3px solid var(--line); border-radius: 20px; padding: 18px 20px; margin-top: 18px; }
.actbox h2 { margin: 4px 0 4px; font-size: clamp(22px, 4vw, 28px); font-weight: 800; }
.actbox > p { margin: 0 0 10px; color: var(--ink-soft); }
.actgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 14px; }
.actcard { display: flex; flex-direction: column; gap: 6px; }
.actcard img { width: 100%; aspect-ratio: 2/3; object-fit: cover; border-radius: 12px; border: 2px solid var(--line); background: #fff; }
.actcard b { font-size: 16px; line-height: 1.25; }
.actcard .dl { font-size: 15px; }
.actcard .dl a { color: var(--sky); font-weight: 700; }
.actep { margin: 14px 0 4px; font-size: 18px; }
.actep a { color: var(--ink); }
</style>"""


def esc(s):
    return html.escape(str(s), quote=True)


def between(text, name, content, anchor_before=None):
    block = f"<!--X:{name}-->{content}<!--/X:{name}-->"
    pat = re.compile(r"<!--X:%s-->.*?<!--/X:%s-->" % (name, name), re.S)
    if pat.search(text):
        return pat.sub(lambda m: block, text)
    if anchor_before and anchor_before in text:
        i = text.index(anchor_before)
        return text[:i] + block + text[i:]
    return text


def approved():
    cache = ROOT / "data" / "extras.csv"
    if not cache.exists():
        return set()
    out = set()
    for r in csv.DictReader(io.StringIO(cache.read_text())):
        if (r.get("activities_ok") or "").strip().lower() in ("yes", "y", "ok", "approved"):
            out.add((r.get("youtube_id") or "").strip())
    return out


def load():
    ok = approved()
    acts = []
    for meta in sorted((ACTS / "output").glob("*/*/meta.json")):
        try:
            m = json.loads(meta.read_text())
        except ValueError:
            continue
        if not m.get("checks_passed") or m.get("youtube_id") not in ok:
            continue
        slug, kind = meta.parent.parent.name, meta.parent.name
        folder = meta.parent
        pdfs = {s: next(iter(sorted(folder.glob(f"*-{s}.pdf"))), None) for s in ("letter", "a4")}
        pin = folder / "pin.png"
        if not pin.exists() or not pdfs["letter"]:
            continue
        m.update(slug=slug, kind=kind, folder=folder, pin=pin, pdfs=pdfs)
        acts.append(m)
    return acts


def copy_pin(a):
    IMG.mkdir(parents=True, exist_ok=True)
    dest = IMG / f'{a["slug"]}-{a["kind"]}.png'
    if not dest.exists() or dest.read_bytes() != a["pin"].read_bytes():
        shutil.copyfile(a["pin"], dest)
    return f"/img/activities/{dest.name}"


def card(a, img):
    rel = lambda p: f'{RAW}/{p.relative_to(ACTS).as_posix()}' if p else ""
    links = f'<a href="{esc(rel(a["pdfs"]["letter"]))}">Letter</a>'
    if a["pdfs"].get("a4"):
        links += f' · <a href="{esc(rel(a["pdfs"]["a4"]))}">A4</a>'
    return (f'<div class="actcard" id="free-{esc(a["kind"])}"><img src="{img}" alt="{esc(a.get("title", ""))}" loading="lazy" width="200" height="300">'
            f'<b>{esc(NAMES.get(a["kind"], a["kind"].title()))}</b><span class="dl">Free PDF: {links}</span></div>')


def main():
    if not (ACTS / "output").exists():
        print("activities repo not found, nothing to do")
        return
    acts = load()
    by_ep = {}
    for a in acts:
        a["img"] = copy_pin(a)
        by_ep.setdefault(a["slug"], []).append(a)
    for lst in by_ep.values():
        lst.sort(key=lambda a: ORDER.index(a["kind"]) if a["kind"] in ORDER else 9)

    # Episode pages
    for slug, lst in by_ep.items():
        p = ROOT / "ep" / f"{slug}.html"
        if not p.exists():
            continue
        s = p.read_text()
        box = (f'<section class="actbox noprint" id="free-activities"><span class="badge-free">FREE</span>'
               f'<h2>Free games and flashcards</h2><p>Print them and play after the episode. Free for home and class.</p>'
               f'<div class="actgrid">{"".join(card(a, a["img"]) for a in lst)}</div></section>')
        s = between(s, "ACTS", box, anchor_before='\n  <section class="sbox" id="lesson-plan">')
        s = between(s, "ACTCSS", CSS, anchor_before="</head>")
        p.write_text(s)

    # Free printables page
    fp = ROOT / "free.html"
    if fp.exists() and by_ep:
        s = fp.read_text()
        parts = []
        for slug, lst in by_ep.items():
            title = lst[0].get("episode_title") or slug
            parts.append(f'<h3 class="actep"><a href="/ep/{esc(slug)}.html">{esc(title)}</a></h3>'
                         f'<div class="actgrid">{"".join(card(a, a["img"]) for a in lst)}</div>')
        box = (f'<section class="actbox" id="free-activities"><h2>Free games and flashcards</h2>'
               f'<p>Bingo, memory games and word flashcards for every episode.</p>{"".join(parts)}</section>')
        s = between(s, "ACTS", box, anchor_before='<div class="freegrid">')
        s = between(s, "ACTCSS", CSS, anchor_before="</head>")
        fp.write_text(s)

    # RSS feed for Pinterest (newest first; each activity once)
    try:
        seen = json.loads(SEEN.read_text())
    except (OSError, ValueError):
        seen = {}
    now = int(time.time())
    items = []
    for a in acts:
        key = f'{a["slug"]}/{a["kind"]}'
        seen.setdefault(key, now)
        link = f'{SITE}/ep/{a["slug"]}.html#free-{a["kind"]}'
        img = f'{SITE}{a["img"]}'
        desc = a.get("description") or f'Free printable {NAMES.get(a["kind"], "")} for ages 2 to 6.'
        items.append((seen[key], f'''  <item>
    <title>{esc(a.get("title") or key)}</title>
    <link>{esc(link)}</link>
    <guid isPermaLink="false">learnwithian-{esc(key)}</guid>
    <pubDate>{email.utils.formatdate(seen[key], usegmt=True)}</pubDate>
    <description>{esc(desc)}</description>
    <enclosure url="{esc(img)}" type="image/png" length="{a["pin"].stat().st_size}"/>
    <media:content url="{esc(img)}" medium="image" type="image/png" width="1000" height="1500"/>
  </item>
'''))
    SEEN.parent.mkdir(exist_ok=True)
    SEEN.write_text(json.dumps(seen, indent=1, sort_keys=True) + "\n")
    items.sort(key=lambda x: -x[0])
    feed = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel>
  <title>Learn with Ian – Free activities for toddlers and preschool</title>
  <link>{SITE}/free.html</link>
  <description>Free printable bingo, memory games and flashcards that go with the Learn with Ian episodes. Ages 2 to 6.</description>
  <language>en-us</language>
{"".join(i[1] for i in items)}</channel>
</rss>
'''
    (ROOT / "activities.xml").write_text(feed)
    print(f"activities shown: {len(acts)} on {len(by_ep)} episode pages, feed items: {len(items)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("activities skipped:", e)
