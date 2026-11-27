"""Daily Pinterest plan: one feed per Pinterest board, filled a little every day.

The plan is the tab "pins" of the extras sheet. One row = one Pin:
  date (YYYY-MM-DD, the day it may go out) | board | slug | key | title | pin_id (Drive id of the picture) | ok
  optional: description, link
A row is put in its board's feed only when its date has come (Dubai time), so Pinterest
makes a few new Pins every day instead of many at once. Pinterest reads the feeds by itself.

Feeds: pins-<board>.xml (for example pins-christmas.xml). Rows with board "general"
(or no board) are added to activities.xml, the feed of the main board.
Pictures are copied once into /img/pins. Safe to run many times.
Pins for the free activity pages come from data/pins_auto.json (made by scripts/pins_auto.py,
pictures already in /img/pins); they are added to the same feeds on their day.
If the sheet can't be read, nothing changes.
"""
import csv
import datetime
import email.utils
import html
import io
import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://learnwithian.com"
SHEET = "1oxDQWj9UmokHvhHp05L9GPgZxyOlyMZ3ctli8nORgsc"
CSV_URL = "https://docs.google.com/spreadsheets/d/" + SHEET + "/gviz/tq?tqx=out:csv&sheet={}"
PINS_CSV = os.environ.get("PINS_CSV") or CSV_URL.format("pins")
ACTS_CSV = os.environ.get("ACTS_CSV") or CSV_URL.format("activities")
DL = os.environ.get("PINS_DL") or "https://drive.google.com/uc?export=download&id={}"
IMG = ROOT / "img" / "pins"
KEEP = 80  # newest items kept in each feed
UA = {"User-Agent": "Mozilla/5.0 (learnwithian.com site builder)"}
BOARDS = {
    "christmas": "Christmas activities for preschool",
    "winter": "Winter activities for toddlers",
    "basics": "Shapes, colors and counting activities for toddlers",
    "zoo-garden": "Zoo and garden activities for preschool",
    "videos": "Learning videos for toddlers",
}
DESC = {
    "story": "Free printable {t} story sequencing cards for preschool and toddlers. Four pictures from the Learn with Ian cartoon {e}: "
             "cut them out and put the story in order. Ages 2 to 6. PDF in US Letter and A4, with a free video to watch first.",
    "puzzle": "Free printable {t} picture puzzle for toddlers and preschoolers, from the Learn with Ian cartoon {e}. "
              "Cut the 6 big pieces and build the picture again. Ages 2 to 6. PDF in US Letter and A4.",
    "video": "{e} is a free learning cartoon for toddlers and preschoolers, ages 2 to 6. Watch it together, then print the free "
             "story sequencing cards, picture puzzle and memory game that go with it.",
}
DESC_OTHER = "Free printable activity for toddlers and preschoolers, from the Learn with Ian cartoon {e}. Ages 2 to 6, with a free video to watch first."


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def esc(s):
    return html.escape(str(s), quote=True)


def table(url):
    rows = csv.DictReader(io.StringIO(fetch(url).decode("utf-8")))
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in rows]


def day(s):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def picture(row):
    """Copy the Pin picture once into /img/pins. Returns (site path, type) or None."""
    if row.get("local"):  # made on GitHub by pins_auto.py, already in the repo
        return (row["local"], "image/jpeg") if (ROOT / row["local"].lstrip("/")).exists() else None
    IMG.mkdir(parents=True, exist_ok=True)
    stem = f'{row["slug"]}-{row["key"]}'
    stamp = IMG / f".{stem}.id"
    for ext, typ in (("jpg", "image/jpeg"), ("png", "image/png")):
        dest = IMG / f"{stem}.{ext}"
        if dest.exists() and stamp.exists() and stamp.read_text() == row["pin_id"]:
            return f"/img/pins/{dest.name}", typ
    try:
        data = fetch(DL.format(row["pin_id"]))
    except Exception as e:
        print("pin picture download failed", stem, e)
        return None
    if data.startswith(b"\xff\xd8"):
        ext, typ = "jpg", "image/jpeg"
    elif data.startswith(b"\x89PNG"):
        ext, typ = "png", "image/png"
    else:
        print("pin picture is not a picture (Drive file not shared?)", stem)
        return None
    for old in IMG.glob(f"{stem}.*"):
        old.unlink()
    (IMG / f"{stem}.{ext}").write_bytes(data)
    stamp.write_text(row["pin_id"])
    return f"/img/pins/{stem}.{ext}", typ


def item(row, titles):
    kind = row["key"].split("-")[0]
    ep = titles.get(row["slug"]) or row["slug"].replace("-", " ").title()
    theme = re.sub(r"^Ian[’']s\s+", "", ep)
    link = row.get("link") or (f'{SITE}/ep/{row["slug"]}.html?pin={row["key"]}' + ("" if kind == "video" else f"#free-{kind}"))
    desc = row.get("description") or DESC.get(kind, DESC_OTHER).format(t=theme, e=ep)
    img = SITE + row["img"]
    when = datetime.datetime.combine(row["day"], datetime.time(9, 0), datetime.timezone.utc).timestamp()
    size = (ROOT / row["img"].lstrip("/")).stat().st_size
    return f'''  <item>
    <title>{esc(row["title"])}</title>
    <link>{esc(link)}</link>
    <guid isPermaLink="false">learnwithian-pin-{esc(row["slug"])}/{esc(row["key"])}</guid>
    <pubDate>{email.utils.formatdate(when, usegmt=True)}</pubDate>
    <description>{esc(desc)}</description>
    <enclosure url="{esc(img)}" type="{row["type"]}" length="{size}"/>
    <media:content url="{esc(img)}" medium="image" type="{row["type"]}" width="1000" height="1500"/>
  </item>
'''


def main():
    rows = [r for r in table(PINS_CSV) if r.get("ok", "").lower() in ("yes", "y", "ok") and r.get("slug") and r.get("key") and r.get("pin_id") and r.get("title")]
    try:  # Pins for the activity pages (never stops the sheet Pins)
        auto = json.loads((ROOT / "data" / "pins_auto.json").read_text(encoding="utf-8")).get("pins", [])
        rows += [{"date": p["date"], "board": p["board"], "slug": p["id"].rsplit("-", 1)[0], "key": p["lang"], "title": p["title"],
                  "description": p["description"], "link": p["link"], "local": p["img"], "pin_id": "local", "ok": "yes"} for p in auto]
    except Exception as e:
        print("no activity-page pins:", e)
    try:
        titles = {a["slug"]: a.get("episode_title", "") for a in table(ACTS_CSV) if a.get("slug")}
    except Exception:
        titles = {}
    today = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=4)).date()
    seen, due = set(), {}
    waiting = 0
    for r in rows:
        r["day"] = day(r.get("date", ""))
        k = (r["slug"], r["key"])
        if not r["day"] or k in seen:
            continue
        seen.add(k)
        pic = picture(r)  # every picture is fetched early, so a broken one shows up before its day
        if r["day"] > today:
            waiting += 1
            continue
        if not pic:
            continue
        r["img"], r["type"] = pic
        board = re.sub(r"[^a-z0-9-]", "", (r.get("board") or "general").lower()) or "general"
        due.setdefault(board, []).append(r)

    for board, lst in due.items():
        lst.sort(key=lambda r: r["day"], reverse=True)
        items = "".join(item(r, titles) for r in lst[:KEEP])
        if board == "general":
            p = ROOT / "activities.xml"
            if p.exists():
                s = p.read_text()
                s = re.sub(r"<!--PINS-->.*?<!--/PINS-->\n?", "", s, flags=re.S)
                p.write_text(s.replace("</channel>", f"<!--PINS-->\n{items}<!--/PINS-->\n</channel>", 1))
            continue
        name = BOARDS.get(board, board.replace("-", " ").title())
        (ROOT / f"pins-{board}.xml").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel>
  <title>Learn with Ian – {esc(name)}</title>
  <link>{SITE}/free.html</link>
  <description>{esc(name)}: free printables and free cartoons from Learn with Ian. Ages 2 to 6.</description>
  <language>en-us</language>
{items}</channel>
</rss>
''')
    print("pins out:", {b: len(l) for b, l in due.items()}, "| waiting for their day:", waiting, "| today (Dubai):", today)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("pins skipped:", e)
