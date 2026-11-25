"""Search extras that do not change how the site looks.

1. Free worksheet pictures are saved on the site itself (img/free/...) with clear
   names, so they can show up in Google Images, instead of Google Drive thumbnails.
2. Every picture gets a short description (alt text) for search engines.
3. llms.txt: a short plain-text guide to the site for AI assistants.

Runs after the pages are built. Safe to run many times. If a download fails,
the page simply keeps the Drive picture.
"""
import csv
import html
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import update  # noqa: E402

SITE = "https://learnwithian.com"
PACK_ID = "1v_QMRmjt9kUwq4TWjq3l_vBXLdii6hn5"
IMG_DIR = ROOT / "img" / "free"
DRIVE = re.compile(r"https://drive\.google\.com/thumbnail\?id=([A-Za-z0-9_-]{20,})&(?:amp;)?sz=w\d+")
YT = re.compile(r"https://i\.ytimg\.com/vi/([A-Za-z0-9_-]{11})/")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def pages():
    skip = {".git", "node_modules"}
    return [p for p in ROOT.rglob("*.html") if not skip & set(p.relative_to(ROOT).parts) and p.name[:6] != "google"]


def episode_names():
    """youtube id -> (keyword, readable name), from the episode pages."""
    out = {}
    try:
        allv = json.loads((ROOT / "data" / "episodes.json").read_text())
        yt = {v["id"]: v.get("title", "") for v in allv}
        for e in update.episode_entries(allv):
            kw = (yt.get(e["id"]) or e.get("title", "")).split("|")[0].strip()
            name = kw
            p = ROOT / "ep" / f'{e["slug"]}.html'
            if p.exists():
                m = re.search(r"<h1>(.*?)</h1>", p.read_text(), re.S)
                if m:
                    name = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
            out[e["id"]] = (kw, name)
        for v in allv:  # videos without an episode page (e.g. the 1-hour video)
            out.setdefault(v["id"], (v["title"].split("|")[0].strip(), v["title"].split("|")[0].strip()))
    except Exception as e:
        print("episode names not read:", e)
    return out


def free_files(names):
    """Drive file id -> (file name stem, alt text)."""
    out = {PACK_ID: ("free-preschool-teacher-pack-counting-tracing-worksheets",
                     "Free printable teacher pack for toddlers and preschool: counting, tracing and shapes worksheets – Learn with Ian")}
    cache = ROOT / "data" / "extras.csv"
    if not cache.exists():
        return out
    for r in csv.DictReader(io.StringIO(cache.read_text())):
        m = re.search(r"/d/([A-Za-z0-9_-]{20,})", r.get("free_pdf") or "")
        if not m:
            continue
        kw, name = names.get((r.get("youtube_id") or "").strip(), ("", ""))
        kw = kw or f'episode {r.get("episode", "")}'
        out[m.group(1)] = (f"{slugify(kw)}-free-printable-worksheet",
                           f"Free printable worksheet – {name or kw} (ages 2 to 6)")
    return out


def save_picture(fid, stem):
    """Download the Drive thumbnail once. Returns the site path or None."""
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("jpg", "png"):
        if (IMG_DIR / f"{stem}.{ext}").exists():
            return f"/img/free/{stem}.{ext}"
    try:
        req = urllib.request.Request(f"https://drive.google.com/thumbnail?id={fid}&sz=w800",
                                     headers={"User-Agent": "Mozilla/5.0 (learnwithian-site-updater)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data, ctype = r.read(), r.headers.get("Content-Type", "")
    except Exception as e:
        print("picture not saved:", stem, e)
        return None
    if data[:3] == b"\xff\xd8\xff":
        ext = "jpg"
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        ext = "png"
    else:
        print("picture not saved (not an image):", stem, ctype)
        return None
    (IMG_DIR / f"{stem}.{ext}").write_bytes(data)
    return f"/img/free/{stem}.{ext}"


def set_alt(tag, text):
    text = html.escape(text, quote=True)
    if re.search(r'\balt="[^"]*"', tag):
        return re.sub(r'\balt="[^"]*"', f'alt="{text}"', tag, count=1)
    return tag.replace("<img", f'<img alt="{text}"', 1)


def write_llms(names):
    eps = []
    for p in sorted((ROOT / "ep").glob("*.html")):
        s = p.read_text()
        h = re.search(r"<h1>(.*?)</h1>", s, re.S)
        d = re.search(r'<meta name="description" content="([^"]*)"', s)
        if h:
            eps.append((html.unescape(re.sub(r"<[^>]+>", "", h.group(1))).strip(),
                        f"{SITE}/ep/{p.name}", html.unescape(d.group(1)) if d else ""))
    topics = sorted(p.stem for p in (ROOT / "topic").glob("*.html")) if (ROOT / "topic").exists() else []
    lines = [
        "# Learn with Ian",
        "",
        "> Learn with Ian is a free cartoon series on YouTube for children ages 2 to 6. Each short, calm episode teaches one idea "
        "(animals, plants, shapes, numbers, colors, weather, holidays). Every episode has a free lesson plan for preschool "
        "teachers and a free printable worksheet. Made for Kids on YouTube; no ads or tracking on the website.",
        "",
        "## Main pages",
        f"- [Home]({SITE}/): newest episodes, free printables and lesson plans",
        f"- [All episodes]({SITE}/episodes.html): every episode with its topic",
        f"- [Free printables]({SITE}/free.html): a free worksheet for every episode and a free 6-page teacher pack (PDF)",
        f"- [Lesson plans]({SITE}/lessons.html): free circle-time lesson plans for preschool teachers",
        f"- [Teacher guide]({SITE}/teachers.html): how to use the episodes in class",
        f"- [Shop]({SITE}/shop.html): books, printables and T-shirts made from the episodes",
        f"- [Episodes in Spanish]({SITE}/es/) and [in Portuguese]({SITE}/pt/): lesson plans in Spanish and Portuguese (videos in simple English)",
        "",
        "## Episodes",
    ]
    lines += [f"- [{t}]({u}): {d}" for t, u, d in eps]
    if topics:
        lines += ["", "## Topics"] + [f"- [{t.title()}]({SITE}/topic/{t}.html)" for t in topics]
    lines += ["", "## Contact",
              "- YouTube: https://www.youtube.com/@LearnWithIanKids",
              "- Email: hello@learnwithian.com", ""]
    (ROOT / "llms.txt").write_text("\n".join(lines))


def main():
    names = episode_names()
    files = free_files(names)
    local = {}
    for fid, (stem, alt) in files.items():
        path = save_picture(fid, stem)
        if path:
            local[fid] = (path, alt)
    changed = 0
    for p in pages():
        s = p.read_text()
        before = s

        def fix(m):
            tag = m.group(0)
            d = DRIVE.search(tag)
            if d and d.group(1) in files:
                fid = d.group(1)
                if fid in local:
                    tag = tag.replace(d.group(0), local[fid][0])
                return set_alt(tag, files[fid][1])
            if re.search(r'\balt="[^"]+"', tag):
                return tag
            y = YT.search(tag)
            if y:
                kw, name = names.get(y.group(1), ("", ""))
                return set_alt(tag, f"{name or kw or 'Learn with Ian'} – free cartoon for ages 2 to 6")
            return set_alt(tag, "Learn with Ian")

        s = re.sub(r"<img\b[^>]*>", fix, s)
        if s != before:
            p.write_text(s)
            changed += 1
    write_llms(names)
    print(f"pictures on the site: {len(local)} of {len(files)}, pages updated: {changed}, llms.txt written")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("media_seo skipped:", e)
