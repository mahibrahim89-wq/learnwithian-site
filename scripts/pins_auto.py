"""Pinterest pictures for the free activity pages, made on GitHub with no person and no key.

For every activity page that is live (data/pages.json) and for each language:
  1. makes one picture (1000x1500) in img/pins/play-<english slug>-<lang>.jpg from the
     episode's own picture (cut out of the episode's existing "video" Pin), the page title
     and its English words, in the channel's colours and fonts;
  2. gives it a day in data/pins_auto.json: one new English Pin, one Spanish and one
     Portuguese a day at most, starting tomorrow, so Pinterest gets a little every day.
scripts/pins.py then puts each Pin into its board's feed when its day comes
(English: the episode's own board; Spanish: es-ingles; Portuguese: pt-ingles).
Every Pin leads only to our own free page. Safe to run many times.
Pause file: data/PAUSE_PINS_AUTO. Never stops the site update.
"""
import csv
import datetime
import html
import io
import json
import re
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://learnwithian.com"
PLAN = ROOT / "data" / "pins_auto.json"
IMG = ROOT / "img" / "pins"
FONTS = Path(__file__).resolve().parent / "fonts"
SHEET_PINS = "https://docs.google.com/spreadsheets/d/1oxDQWj9UmokHvhHp05L9GPgZxyOlyMZ3ctli8nORgsc/gviz/tq?tqx=out:csv&sheet=pins"
PREFIX = {"en": "", "es": "es/", "pt": "pt/"}
LANG_BOARD = {"es": "es-ingles", "pt": "pt-ingles"}
ENGLISH_BOARDS = ("christmas", "winter", "basics", "zoo-garden")
W, H = 1000, 1500
RGB = {k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) for k, v in dict(
    navy="#1d2b45", blue="#2f8fe6", green="#3fae5a", pink="#ec4f7b", sand="#ecdcbc", yel="#ffb321", cream="#fff9ef", white="#ffffff").items()}
T = {
    "en": dict(sub="Free 15-minute activity  ·  ages 2 to 6", words="Words to practice", btn="FREE ACTIVITY", foot="Steps + free video  ·  learnwithian.com"),
    "es": dict(sub="Actividad gratis de 15 minutos  ·  2 a 6 años", words="Palabras en inglés", btn="ACTIVIDAD GRATIS", foot="Pasos + video gratis  ·  learnwithian.com"),
    "pt": dict(sub="Atividade grátis de 15 minutos  ·  2 a 6 anos", words="Palavras em inglês", btn="ATIVIDADE GRÁTIS", foot="Passo a passo + vídeo grátis  ·  learnwithian.com"),
}


def B(s):
    return ImageFont.truetype(str(FONTS / "Baloo2-ExtraBold.ttf"), s)


def A(s):
    return ImageFont.truetype(str(FONTS / "AtkinsonHyperlegible-Bold.ttf"), s)


def today():
    return (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=4)).date()


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


# ---------- the picture ----------

def hero_box(im):
    """Where the clean episode picture sits inside an existing video Pin (between two white border lines)."""
    px = im.load()
    white = [all(min(px[x, y]) > 240 for x in range(100, 900, 8)) for y in range(im.height)]
    runs, y = [], 0
    while y < im.height:
        if white[y]:
            s = y
            while y < im.height and white[y]:
                y += 1
            if 6 <= y - s <= 16:
                runs.append((s, y - 1))
        else:
            y += 1
    for (a, b), (c, d) in zip(runs, runs[1:]):
        if 420 <= c - b <= 560:
            return (58, b + 9, 942, c - 9)
    return None


def episode_picture(ep):
    for key in ("video-a", "video-b"):
        p = IMG / f"{ep}-{key}.jpg"
        if p.exists():
            im = Image.open(p).convert("RGB")
            box = hero_box(im) if im.size == (W, H) else None
            if box:
                return im.crop(box)
    return None


def card(im, w, r=30, border=10):
    im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS).convert("RGBA")
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, im.width - 1, im.height - 1), r, fill=255)
    im.putalpha(m)
    bw, bh = im.width + 2 * border, im.height + 2 * border
    box = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    ImageDraw.Draw(box).rounded_rectangle((0, 0, bw - 1, bh - 1), r + border, fill=(255, 255, 255, 255))
    box.alpha_composite(im, (border, border))
    pad = 30
    out = Image.new("RGBA", (bw + 2 * pad, bh + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 8, pad + bw, pad + bh + 8), r + border, fill=(29, 43, 69, 70))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
    out.alpha_composite(box, (pad, pad))
    return out


def wrap(d, s, font, maxw):
    lines, cur = [], ""
    for word in s.split():
        t = (cur + " " + word).strip()
        if d.textlength(t, font=font) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    return lines + [cur]


def fit_lines(d, s, size, maxw, max_lines, floor=44):
    while True:
        lines = wrap(d, s, B(size), maxw)
        if (len(lines) <= max_lines and all(d.textlength(l, font=B(size)) <= maxw for l in lines)) or size <= floor:
            return lines, size
        size -= 4


def centre(d, y, s, font, col, maxw=W - 80):
    while d.textlength(s, font=font) > maxw and font.size > 22:
        font = font.font_variant(size=font.size - 2)
    d.text(((W - d.textlength(s, font=font)) / 2, y), s, font=font, fill=col)
    return font.size


def make_picture(topic, lang, hero, dest):
    """Draw once to measure, then again with the spare room shared out between the parts."""
    _, end = draw_picture(topic, lang, hero, 0)
    spare = max(0, (H - 118) - end)
    im, end = draw_picture(topic, lang, hero, spare)
    if end > H - 100:
        raise ValueError("picture too tall")
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=88, optimize=True)


def draw_picture(topic, lang, hero, spare):
    d0, t = topic[lang], T[lang]
    im = Image.new("RGB", (W, H), RGB["cream"])
    d = ImageDraw.Draw(im)
    centre(d, 22, "Learn with Ian", B(40), RGB["pink"])
    title = text(d0["h1"]).split(":")[0].strip()
    lines, size = fit_lines(d, title, 104, W - 90, 2)
    y = 78 + round(spare * 0.2)
    for i, line in enumerate(lines):
        centre(d, y, line, B(size), RGB["navy"] if i == 0 else RGB["blue"])
        y += size
    y += 44 + round(spare * 0.1)
    centre(d, y, t["sub"], A(36), RGB["navy"])
    y += 50 + round(spare * 0.1)
    c = card(hero, 900)
    im.paste(c, (int(W / 2 - c.width / 2), y), c)
    y += c.height - 12 + round(spare * 0.15)
    words = [text(w) for w in d0.get("words", [])][:3]
    if words:
        centre(d, y, t["words"], B(46), RGB["blue"])
        y += 70
        n, gap = len(words), 24
        cw = (W - 80 - gap * (n - 1)) // n
        ch = 190 if lang != "en" else 130
        for i, w in enumerate(words):
            x = 40 + i * (cw + gap)
            d.rounded_rectangle((x, y, x + cw, y + ch), 30, fill=RGB["white"], outline=RGB["sand"], width=4)
            parts = [p.strip() for p in re.split(r"\s*[·=]\s*", w, maxsplit=1)]
            f = B(64)
            while d.textlength(parts[0], font=f) > cw - 30 and f.size > 30:
                f = f.font_variant(size=f.size - 2)
            d.text((x + cw / 2 - d.textlength(parts[0], font=f) / 2, y + (18 if lang != "en" else 26)), parts[0], font=f, fill=RGB["pink"])
            if len(parts) > 1 and lang != "en":
                f2 = A(34)
                while d.textlength(parts[1], font=f2) > cw - 24 and f2.size > 20:
                    f2 = f2.font_variant(size=f2.size - 2)
                d.text((x + cw / 2 - d.textlength(parts[1], font=f2) / 2, y + 118), parts[1], font=f2, fill=RGB["navy"])
        y += ch + 34 + round(spare * 0.2)
    f = A(40)
    tw = d.textlength(t["btn"], font=f)
    d.rounded_rectangle((W / 2 - tw / 2 - 40, y, W / 2 + tw / 2 + 40, y + 76), 38, fill=RGB["yel"])
    d.text((W / 2 - tw / 2, y + 16), t["btn"], font=f, fill=RGB["navy"])
    centre(d, H - 86, t["foot"], B(44), RGB["pink"])
    return im, y + 76


# ---------- the plan ----------

def english_boards():
    """episode slug -> English board, learned from the Pins already in the feeds and planned in the sheet."""
    found = {}
    for board in ENGLISH_BOARDS:
        feed = ROOT / f"pins-{board}.xml"
        if feed.exists():
            for ep in re.findall(r"learnwithian-pin-([a-z0-9-]+)/", feed.read_text(encoding="utf-8")):
                if not ep.startswith("play-"):
                    found.setdefault(ep, board)
    found.update(sheet_boards())
    return found


def sheet_boards():
    try:
        req = urllib.request.Request(SHEET_PINS, headers={"User-Agent": "Mozilla/5.0 (learnwithian.com site builder)"})
        with urllib.request.urlopen(req, timeout=40) as r:
            rows = csv.DictReader(io.StringIO(r.read().decode("utf-8")))
            return {(x.get("slug") or "").strip(): (x.get("board") or "").strip() for x in rows
                    if (x.get("board") or "").strip() in ENGLISH_BOARDS}
    except Exception as e:
        print("pins_auto: could not read the boards from the sheet:", e)
        return {}


def main():
    if (ROOT / "data" / "PAUSE_PINS_AUTO").exists():
        print("pins_auto: paused (data/PAUSE_PINS_AUTO)")
        return
    pages = ROOT / "data" / "pages.json"
    if not pages.exists():
        return
    topics = [t for t in json.loads(pages.read_text(encoding="utf-8")) if t.get("live_from", "9999") <= today().isoformat()]
    doc = json.loads(PLAN.read_text(encoding="utf-8")) if PLAN.exists() else {"boards": {}, "pins": []}
    have = {p["id"] for p in doc["pins"]}
    doc["boards"].update(english_boards())
    # seasonal pages first: a Christmas or winter Pin is worth most before the season
    topics.sort(key=lambda t: 0 if doc["boards"].get(t["episode"]) in ("christmas", "winter") else 1)
    last = {}
    for p in doc["pins"]:
        last[p["lang"]] = max(last.get(p["lang"], ""), p["date"])
    start = (today() + datetime.timedelta(days=1)).isoformat()
    made = 0
    for tp in topics:
        hero = None
        for lang in PREFIX:
            pid = f'play-{tp["en"]["slug"]}-{lang}'
            if pid in have:
                continue
            if not (ROOT / PREFIX[lang] / "play" / (tp[lang]["slug"] + ".html")).exists():
                continue
            hero = hero or episode_picture(tp["episode"])
            if hero is None:
                print(f'pins_auto: no episode picture yet for {tp["episode"]}, later')
                break
            dest = IMG / f"{pid}.jpg"
            try:
                make_picture(tp, lang, hero, dest)
            except Exception as e:
                print(f"pins_auto: could not make {pid}: {e!r}")
                continue
            day = start if not last.get(lang) else max(start, (datetime.date.fromisoformat(last[lang]) + datetime.timedelta(days=1)).isoformat())
            last[lang] = day
            doc["pins"].append({
                "id": pid, "lang": lang, "date": day, "topic": tp["id"], "episode": tp["episode"],
                "board": LANG_BOARD.get(lang) or doc["boards"].get(tp["episode"], "general"),
                "title": text(tp[lang]["h1"])[:100], "description": text(tp[lang]["desc"])[:480],
                "link": f'{SITE}/{PREFIX[lang]}play/{tp[lang]["slug"]}.html?pin={lang}',
                "img": f"/img/pins/{pid}.jpg"})
            have.add(pid)
            made += 1
    if made or not PLAN.exists():
        PLAN.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    waiting = sum(1 for p in doc["pins"] if p["date"] > today().isoformat())
    print(f"pins_auto: {made} new pictures, {len(doc['pins'])} planned in all, {waiting} waiting for their day")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never stop the site update
        print("pins_auto: skipped:", repr(e))
