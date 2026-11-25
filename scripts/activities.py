"""Free activities (story order cards, picture puzzle, memory game) made by
Claude from the channel's own episode pictures.

The files live in Google Drive (folder "Learn with Ian - Free activities").
The list is the tab "activities" of the extras sheet: one row per activity with
the Drive ids of the Letter PDF, the A4 PDF and the Pinterest picture.
Only rows with ok = yes are shown.

Adds:
- a "Free printable <topic> activities" box on each episode page, plus the page's search title,
  description (tab columns page_title / page_desc) and LearningResource data for search engines,
- the same activities at the top of free.html,
- activities.xml: an RSS feed that Pinterest reads to make Pins by itself.
Safe to run many times. If the sheet can't be read, nothing changes.
"""
import csv
import email.utils
import html
import io
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://learnwithian.com"
SHEET = "1oxDQWj9UmokHvhHp05L9GPgZxyOlyMZ3ctli8nORgsc"
LIST_CSV = f"https://docs.google.com/spreadsheets/d/{SHEET}/gviz/tq?tqx=out:csv&sheet=activities"
DL = "https://drive.google.com/uc?export=download&id={}"
IMG = ROOT / "img" / "activities"
SEEN = ROOT / "data" / "activities_seen.json"
NAMES = {"story": "Story sequencing cards", "puzzle": "Picture puzzle", "memory": "Memory match game"}
HOW = {"story": "4 pictures to put in order", "puzzle": "6 pieces to cut and build", "memory": "12 cards, find the pairs"}
FREE_TITLE = "Free Printable Activities for Preschoolers & Toddlers – Learn with Ian"
FREE_DESC = ("Free printable activities for preschoolers and toddlers (ages 2 to 6): story sequencing cards, picture puzzles, "
             "memory games and worksheets, each with a free cartoon episode and lesson plan.")
ORDER = ["story", "puzzle", "memory"]
UA = {"User-Agent": "Mozilla/5.0 (learnwithian.com site builder)"}

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
.actcard .how { font-size: 14px; color: var(--ink-soft); line-height: 1.3; }
.actep { margin: 14px 0 4px; font-size: 18px; }
.actep a { color: var(--ink); }
</style>"""


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


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


def load():
    rows = csv.DictReader(io.StringIO(fetch(LIST_CSV).decode("utf-8")))
    acts = []
    for r in rows:
        r = {k: (v or "").strip() for k, v in r.items()}
        if r.get("ok", "").lower() not in ("yes", "y", "ok") or not r.get("slug") or not r.get("pin_id"):
            continue
        r["kind"] = r.get("kind") or "activity"
        acts.append(r)
    return acts


def copy_pin(a):
    """Download the Pinterest picture once into /img/activities. Returns its site path or None."""
    IMG.mkdir(parents=True, exist_ok=True)
    dest = IMG / f'{a["slug"]}-{a["kind"]}.png'
    stamp = IMG / f'.{dest.stem}.id'
    if dest.exists() and stamp.exists() and stamp.read_text() == a["pin_id"]:
        return f"/img/activities/{dest.name}"
    try:
        data = fetch(DL.format(a["pin_id"]))
    except Exception as e:
        print("pin download failed", a["slug"], a["kind"], e)
        return f"/img/activities/{dest.name}" if dest.exists() else None
    if not data.startswith(b"\x89PNG"):
        print("pin is not a picture (Drive file not shared?)", a["slug"], a["kind"])
        return f"/img/activities/{dest.name}" if dest.exists() else None
    dest.write_bytes(data)
    stamp.write_text(a["pin_id"])
    return f"/img/activities/{dest.name}"


def theme(a):
    return re.sub(r"^Ian[’']s\s+", "", a.get("episode_title") or a["slug"].replace("-", " ").title())


def set_head(s, title, desc):
    """Search title and description of the page (what Google shows). The look of the page does not change."""
    put = lambda v: (lambda m: m.group(1) + esc(v) + m.group(2))
    s = re.sub(r"(<title>).*?(</title>)", put(title), s, count=1, flags=re.S)
    s = re.sub(r'(<meta name="description" content=")[^"]*(")', put(desc), s, count=1)
    s = re.sub(r'(<meta property="og:title" content=")[^"]*(")', put(title), s, count=1)
    s = re.sub(r'(<meta property="og:description" content=")[^"]*(")', put(desc), s, count=1)
    return s


def page_seo(lst):
    t = theme(lst[0])
    title = next((a["page_title"] for a in lst if a.get("page_title")), "") or f"{t} Sequencing Cards for Preschool: Free Printable + Video"
    desc = next((a["page_desc"] for a in lst if a.get("page_desc")), "") or (
        f"Free printable {t} activities for preschoolers and toddlers: story sequencing cards, a picture puzzle "
        f"and a memory game (PDF), with a free cartoon and lesson plan.")
    return title, desc


def learning_ld(slug, lst):
    """Tells search engines what the printables are. Matches what the page shows."""
    items = [{"@type": "ListItem", "position": i + 1, "item": {
        "@type": "LearningResource", "name": a.get("title") or NAMES.get(a["kind"], a["kind"]),
        "description": a.get("description", ""), "url": f'{SITE}/ep/{slug}.html#free-{a["kind"]}',
        "image": f'{SITE}{a["img"]}', "learningResourceType": "Activity", "educationalLevel": "Preschool",
        "typicalAgeRange": "2-6", "isAccessibleForFree": True, "inLanguage": "en", "encodingFormat": "application/pdf",
        "publisher": {"@type": "Organization", "name": "Learn with Ian", "url": SITE}}} for i, a in enumerate(lst)]
    ld = {"@context": "https://schema.org", "@type": "ItemList",
          "name": f"Free printable {theme(lst[0])} activities for preschool", "itemListElement": items}
    return '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def card(a, img):
    links = f'<a href="{esc(DL.format(a["letter_id"]))}">Letter</a>'
    if a.get("a4_id"):
        links += f' · <a href="{esc(DL.format(a["a4_id"]))}">A4</a>'
    return (f'<div class="actcard" id="free-{esc(a["kind"])}"><img src="{img}" alt="{esc(a.get("title", ""))}" loading="lazy" width="200" height="300">'
            f'<b>{esc(NAMES.get(a["kind"], a["kind"].title()))}</b>'
            + (f'<span class="how">{esc(HOW[a["kind"]])}</span>' if a["kind"] in HOW else "")
            + f'<span class="dl">Free PDF: {links}</span></div>')


def main():
    acts = [a for a in load() if a.get("letter_id")]
    by_ep = {}
    for a in acts:
        a["img"] = copy_pin(a)
    acts = [a for a in acts if a["img"]]
    for a in acts:
        by_ep.setdefault(a["slug"], []).append(a)
    for lst in by_ep.values():
        lst.sort(key=lambda a: ORDER.index(a["kind"]) if a["kind"] in ORDER else 9)

    # Episode pages
    for slug, lst in by_ep.items():
        p = ROOT / "ep" / f"{slug}.html"
        if not p.exists():
            continue
        s = p.read_text()
        box = (f'<section class="actbox noprint" id="free-activities">'
               f'<h2>Free printable {esc(theme(lst[0]))} activities</h2><p>For preschool and toddlers, made from the episode pictures. Watch the episode, then print and play.</p>'
               f'<div class="actgrid">{"".join(card(a, a["img"]) for a in lst)}</div></section>')
        s = between(s, "ACTS", box, anchor_before='\n  <section class="sbox" id="lesson-plan">')
        s = between(s, "ACTCSS", CSS, anchor_before="</head>")
        s = between(s, "ACTLD", learning_ld(slug, lst), anchor_before="</head>")
        s = set_head(s, *page_seo(lst))
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
        box = (f'<section class="actbox" id="free-activities"><h2>Free printable games</h2>'
               f'<p>Story sequencing cards, picture puzzles and memory games for every episode.</p>{"".join(parts)}</section>')
        s = between(s, "ACTS", box, anchor_before='<div class="freegrid">')
        s = between(s, "ACTCSS", CSS, anchor_before="</head>")
        s = set_head(s, FREE_TITLE, FREE_DESC)
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
    <enclosure url="{esc(img)}" type="image/png" length="{(ROOT / a["img"].lstrip("/")).stat().st_size}"/>
    <media:content url="{esc(img)}" medium="image" type="image/png" width="1000" height="1500"/>
  </item>
'''))
    SEEN.parent.mkdir(exist_ok=True)
    SEEN.write_text(json.dumps(seen, indent=1, sort_keys=True) + "\n")
    items.sort(key=lambda x: -x[0])
    feed = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel>
  <title>Learn with Ian – Free printable games for toddlers and preschool</title>
  <link>{SITE}/free.html</link>
  <description>Free printable story cards, picture puzzles and memory games that go with the Learn with Ian episodes. Ages 2 to 6.</description>
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
