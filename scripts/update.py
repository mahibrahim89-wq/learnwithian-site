"""Daily update for learnwithian.com.

Reads the YouTube channel feed (no API key needed), remembers every full
episode it has seen, then:
  * rebuilds shop.html from data/shop.json plus the links Grok puts in
    each video description,
  * points the homepage player at the newest full episode,
  * adds a card on the homepage for any new episode.
Runs from .github/workflows/update.yml. Uses only the Python standard library.
"""
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import episodes_page
import lessons

ROOT = Path(__file__).resolve().parent.parent
SHOP = json.loads((ROOT / "data" / "shop.json").read_text())
SEEN_PATH = ROOT / "data" / "episodes.json"
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id=" + SHOP["channel_id"]
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
      "m": "http://search.yahoo.com/mrss/"}
STORE_BY_DOMAIN = [
    ("amazon.", "Amazon"), ("gumroad.com", "Gumroad"), ("payhip.com", "Payhip"), ("lulu.com", "Lulu"),
    ("ko-fi.com", "Ko-fi"), ("itch.io", "itch.io"), ("teemill.com", "Teemill"), ("zazzle.com", "Zazzle"),
    ("teepublic.com", "TeePublic"), ("spreadshop.com", "Spreadshop"), ("tes.com", "Tes"),
    ("teacherspayteachers.com", "TPT"), ("redbubble.com", "Redbubble"), ("displate.com", "Displate"),
]
SKIP_DOMAINS = ("youtube.com", "youtu.be", "learnwithian.com")
# Links that are never a store. Any other link in a video description is treated
# as a store automatically, so a new store needs no code change.
NOT_STORES = ("instagram.com", "facebook.com", "fb.com", "fb.me", "tiktok.com", "twitter.com", "x.com",
              "threads.net", "pinterest.com", "linkedin.com", "wa.me", "whatsapp.com", "t.me", "telegram.me",
              "linktr.ee", "google.com", "goo.gl", "forms.gle", "spotify.com", "discord.com", "discord.gg",
              "reddit.com", "patreon.com", "snapchat.com", "x.ai", "grok.com", "grok.bot")


def esc(s):
    return html.escape(str(s), quote=True)


def store_of(url):
    for dom, name in STORE_BY_DOMAIN:
        if dom in url:
            return name
    host = re.sub(r"^https?://", "", url).split("/")[0].split(":")[0].lower()
    if not host or any(host == d or host.endswith("." + d) for d in NOT_STORES):
        return None
    parts = [p for p in host.split(".") if p and p != "www"]
    if len(parts) < 2:
        return None
    name = parts[-2]
    if name in ("co", "com", "org", "net") and len(parts) >= 3:
        name = parts[-3]
    return name.replace("-", " ").title()


def fetch_feed(path=None):
    if path:
        return Path(path).read_text()
    req = urllib.request.Request(FEED, headers={"User-Agent": "learnwithian-site-updater"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def description_links(desc):
    """Return [{label, url, store}] for shop links in a video description."""
    out, last = [], 0
    for m in re.finditer(r"https?://[^\s,]+", desc):
        url = m.group(0).rstrip(".)")
        chunk = desc[last:m.start()]
        last = m.end()
        if any(d in url for d in SKIP_DOMAINS) or not store_of(url):
            continue
        label = chunk.split("For parents:")[-1]
        label = re.sub(r",?\s*\$\d+(\.\d+)?,?\s*$", "", label).strip(" :,-")
        label = re.sub(r"^.*?!\s+", "", label) if "!" in label[:60] else label
        out.append({"label": label[:90], "url": url, "store": store_of(url)})
    return out


def parse_feed(xml_text):
    root = ET.fromstring(xml_text)
    vids = []
    for e in root.findall("a:entry", NS):
        link = e.find("a:link", NS).get("href", "")
        if "/shorts/" in link:
            continue
        vid = e.find("yt:videoId", NS).text
        desc = e.find("m:group/m:description", NS)
        vids.append({
            "id": vid,
            "title": e.find("a:title", NS).text,
            "published": e.find("a:published", NS).text,
            "links": description_links(desc.text if desc is not None and desc.text else ""),
        })
    return vids


def short_title(t):
    parts = [p.strip() for p in t.split("|")]
    for p in parts:
        if "Ian's" in p or "Ian’s" in p:
            return p
    return parts[0]


def clean_name(label):
    name = label.split("): ")[-1] if "): " in label else label
    name = re.sub(r"\s*\(Ep\s*\d+\)", "", name)
    name = re.sub(r"\s+on (Gumroad|Payhip|Amazon|Lulu|Ko-fi|itch\.io)$", "", name, flags=re.I)
    return name.strip(" :") or "Printable activity pack"


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "episode"


def still_online(vid):
    """False only when YouTube says the video is gone or private (deleted or replaced)."""
    url = f"https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v={vid}"
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "learnwithian-site-updater"}), timeout=20)
        return True
    except urllib.request.HTTPError as e:
        return e.code not in (400, 401, 403, 404)
    except Exception:
        return True  # network trouble: keep the video


def merge_seen(new):
    seen = json.loads(SEEN_PATH.read_text()) if SEEN_PATH.exists() else []
    feed_ids = {v["id"] for v in new}
    if feed_ids:  # only prune when the feed itself loaded
        seen = [v for v in seen if v["id"] in feed_ids or still_online(v["id"])]
    by_id = {v["id"]: v for v in seen}
    for v in new:
        by_id[v["id"]] = v
    allv = sorted(by_id.values(), key=lambda v: v["published"])
    SEEN_PATH.write_text(json.dumps(allv, indent=2, ensure_ascii=False) + "\n")
    return allv


def episode_entries(allv):
    """Ordered list of episodes with products, manual data first."""
    manual = SHOP["episodes"]
    eps = []
    general_urls = ({l["url"] for g in SHOP["general"] + [SHOP.get("bundle") or {"links": []}] for l in g["links"]}
                    | {s["url"] for s in SHOP["stores"]})
    known = [v for v in allv if v["id"] in manual or not episodes_page.is_compilation(v["title"])]
    for vid, m in manual.items():
        if not any(v["id"] == vid for v in known):
            known.append({"id": vid, "title": m["title"], "published": "0", "links": []})
    known.sort(key=lambda v: (manual.get(v["id"], {}).get("num", 999), v["published"]))
    for i, v in enumerate(known, 1):
        m = manual.get(v["id"])
        if m:
            eps.append({"id": v["id"], "num": m["num"], "slug": m["slug"], "title": m["title"],
                        "learn": m["learn"], "products": m["products"], "manual": True})
            continue
        prods = group_products([l for l in v["links"] if l["url"] not in general_urls],
                               f"https://i.ytimg.com/vi/{v['id']}/mqdefault.jpg")
        title = short_title(v["title"])
        eps.append({"id": v["id"], "num": i, "slug": slugify(title), "title": title,
                    "learn": "", "products": prods, "manual": False})
    return eps


FORMATS = {
    # format: (button title, how it reaches you, filter group)
    "printable": ("Printable PDF", "Instant download, print at home", "printable"),
    "ebook": ("eBook", "Instant download, read on a tablet", "book"),
    "paperback": ("Paperback book", "Printed and shipped to your door", "book"),
    "tshirt": ("Kids T-shirts", "Printed and shipped to your door", "tshirt"),
    "bundle": ("Get the bundle", "Instant download", "printable"),
}
TEE_SVG = ('<svg viewBox="0 0 120 150" role="img" aria-label="Ian T-shirt"><rect width="120" height="150" fill="#fff1d6"/>'
           '<path d="M38 30l-26 14 10 22 12-6v62h52V60l12 6 10-22-26-14c-3 8-11 13-22 13s-19-5-22-13z" fill="#ec4f7b" '
           'stroke="#1d2b45" stroke-width="4" stroke-linejoin="round"/>'
           '<text x="60" y="96" text-anchor="middle" font-family="Baloo 2, Arial Rounded MT Bold, sans-serif" '
           'font-weight="800" font-size="24" fill="#ffb321" stroke="#1d2b45" stroke-width="1.5">IAN</text></svg>')


def format_of(store, label=""):
    if store not in [n for _, n in STORE_BY_DOMAIN]:
        if re.search(r"\b(t-?shirts?|tees?|hoodies?)\b", label, re.I):
            return "tshirt"
        if re.search(r"\b(paperback|hardcover)\b", label, re.I):
            return "paperback"
    if store in ("Amazon", "Lulu"):
        return "paperback"
    if store in ("Teemill", "Zazzle", "TeePublic", "Spreadshop", "Redbubble"):
        return "tshirt"
    return "printable"


def group_products(links, image=""):
    """Links tagged (EpN) are one product sold on several stores; others stand alone."""
    tagged = [l for l in links if re.search(r"\(Ep\s*\d+\)", l["label"])]
    other = [l for l in links if l not in tagged]
    prods = []
    if tagged:
        names = sorted((clean_name(l["label"]) for l in tagged), key=len, reverse=True)
        prods.append({"id": slugify(names[0]), "name": names[0], "about": "", "image": image,
                      "links": [{"format": format_of(l["store"], l["label"]), "store": l["store"], "url": l["url"]} for l in tagged]})
    for l in other:
        name = clean_name(l["label"]) or l["store"]
        prods.append({"id": slugify(name), "name": name, "about": "", "image": image,
                      "links": [{"format": format_of(l["store"], l["label"]), "store": l["store"], "url": l["url"]}]})
    return prods


def split_links(links):
    """First link of each format becomes a big button; the rest go under 'other stores'."""
    main, seen = [], set()
    for l in links:
        f = l.get("format") or format_of(l["store"])
        if f not in seen:
            seen.add(f)
            main.append(dict(l, format=f))
    rest = [dict(l, format=l.get("format") or format_of(l["store"])) for l in links if l["url"] not in {m["url"] for m in main}]
    return main, rest


def buy_button(l, i):
    title, how, _ = FORMATS.get(l["format"], FORMATS["printable"])
    cls = "pbtn pbtn-main" if i == 0 else "pbtn pbtn-alt"
    return (f'<a class="{cls}" href="{esc(l["url"])}"><b>{title}</b>'
            f'<span>{how} &middot; {esc(l["store"])}</span></a>')


def other_stores(rest):
    if not rest:
        return ""
    items = "".join(
        f'<li><a href="{esc(l["url"])}">{esc(l["store"])}</a> <span>{FORMATS.get(l["format"], FORMATS["printable"])[0]}'
        f'{(", " + esc(l["label"])) if l.get("label") else ""}</span></li>' for l in rest)
    n = len(rest)
    return (f'<details class="pother"><summary>Also on {n} other store{"s" if n > 1 else ""}</summary>'
            f'<ul>{items}</ul></details>')


def product_html(p, fallback_img=""):
    main, rest = split_links(p["links"])
    groups = " ".join(sorted({FORMATS.get(l["format"], FORMATS["printable"])[2] for l in p["links"]}))
    img = p.get("image") or fallback_img
    pic = (f'<img src="{esc(img)}" alt="{esc(p["name"])} cover" loading="lazy">' if img else TEE_SVG)
    about = f'<p class="pabout">{esc(p["about"])}</p>' if p.get("about") else ""
    pid = p.get("id") or slugify(p["name"])
    return (f'<article class="pcard" id="{esc(pid)}" data-f="{groups}">'
            f'<a class="pimg" href="{esc(main[0]["url"])}" tabindex="-1" aria-hidden="true">{pic}</a>'
            f'<div class="pbody"><h3>{esc(p["name"])}</h3>{about}'
            f'<div class="pbtns">{"".join(buy_button(l, i) for i, l in enumerate(main))}</div>'
            f'{other_stores(rest)}</div></article>')


def bundle_html(b):
    if not b:
        return ""
    covers = "".join(f'<img src="{esc(u)}" alt="" loading="lazy">' for u in b.get("images", [])[:3])
    l = b["links"][0]
    return (f'<section class="bundle" id="{esc(b["id"])}" aria-labelledby="bundle-h">'
            f'<div class="bcovers" aria-hidden="true">{covers}</div>'
            f'<div class="bbody"><span class="kicker">Want everything?</span><h2 id="bundle-h">{esc(b["name"])}</h2>'
            f'<p>{esc(b["about"])}</p>'
            f'<a class="pbtn pbtn-main bbtn" href="{esc(l["url"])}"><b>Get the bundle</b>'
            f'<span>Instant download &middot; {esc(l["store"])}</span></a></div></section>')


def render_shop(eps, style):
    ep_blocks = []
    for e in eps:
        thumb = f'https://i.ytimg.com/vi/{e["id"]}/mqdefault.jpg'
        prods = "".join(product_html(p, thumb) for p in e["products"]) or \
            '<p class="pnone">Books and printables for this episode are coming soon.</p>'
        ep_blocks.append(f'''
    <section class="shopep" id="{esc(e["slug"])}">
      <div class="shophead">
        <a href="https://www.youtube.com/watch?v={esc(e["id"])}" tabindex="-1" aria-hidden="true"><img src="{esc(thumb)}" alt="" width="320" height="180" loading="lazy"></a>
        <div>
          <span class="kicker">Episode {e["num"]}</span>
          <h2>{esc(e["title"])}</h2>
          <a class="watchlink" href="https://www.youtube.com/watch?v={esc(e["id"])}">Watch it free on YouTube &rarr;</a>
        </div>
      </div>
      <div class="pgrid">{prods}</div>
    </section>''')
    jump = "".join(f'<a href="#{esc(e["slug"])}">{esc(e["title"].split(": ")[-1])}</a>' for e in eps)
    general = "".join(product_html(p) for p in SHOP["general"])
    stores = "".join(f'<a class="shopcard" href="{esc(s["url"])}"><b>{esc(s["name"])}</b><span>{esc(s["what"])}</span></a>'
                     for s in SHOP["stores"])
    shop_css = """
.shopwrap { padding: 24px 0 40px; }
.shopintro h1 { font-size: clamp(36px, 6vw, 60px); font-weight: 800; }
.shopintro p { margin-top: 8px; color: var(--ink-soft); font-size: 19px; }
.filters { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; align-items: center; }
.filters .flabel { font-weight: 700; margin-right: 2px; }
.filters button { font: inherit; font-weight: 700; font-size: 17px; padding: 9px 18px; border-radius: 999px; border: 3px solid var(--ink); background: #fff; color: var(--ink); cursor: pointer; }
.filters button[aria-pressed="true"] { background: var(--ink); color: #fff; }
.jumpline { margin-top: 14px; font-size: 15px; color: var(--ink-soft); display: flex; flex-wrap: wrap; gap: 6px 14px; }
.jumpline a { font-weight: 700; color: var(--ink); }
.bundle { margin-top: 26px; display: grid; grid-template-columns: 220px 1fr; gap: 26px; align-items: center; background: #fff; border: 3px solid var(--ink); border-radius: 26px; padding: 22px 26px; box-shadow: 8px 8px 0 var(--sun); }
.bcovers { position: relative; height: 190px; }
.bcovers img { position: absolute; top: 0; width: 120px; aspect-ratio: 4 / 5; object-fit: cover; border-radius: 10px; border: 3px solid var(--ink); background: #fff; }
.bcovers img:nth-child(1) { left: 0; transform: rotate(-7deg); }
.bcovers img:nth-child(2) { left: 50px; top: 8px; z-index: 1; }
.bcovers img:nth-child(3) { left: 100px; transform: rotate(7deg); }
.bbody h2 { font-size: clamp(26px, 3.4vw, 36px); }
.bbody p { margin-top: 6px; color: var(--ink-soft); }
.bbtn { margin-top: 14px; max-width: 340px; }
.shopep, .shopgen { padding: 34px 0; border-bottom: 2px dashed var(--line); }
.shophead { display: flex; gap: 18px; align-items: center; margin-bottom: 18px; flex-wrap: wrap; }
.shophead img { width: 180px; height: auto; aspect-ratio: 16 / 9; object-fit: cover; border-radius: 14px; border: 3px solid var(--ink); }
.shophead h2 { font-size: clamp(26px, 3.4vw, 36px); }
.watchlink { font-weight: 700; color: var(--ink); text-decoration-color: var(--sun); text-decoration-thickness: 3px; text-underline-offset: 4px; }
.pgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 440px), 1fr)); gap: 18px; }
.pcard { display: grid; grid-template-columns: 150px 1fr; gap: 18px; background: #fff; border: 3px solid var(--ink); border-radius: 22px; padding: 16px; scroll-margin-top: 90px; }
.pcard:target { box-shadow: 0 0 0 5px var(--sun); }
.pcard[hidden], .shopep[hidden], .shopgen[hidden] { display: none; }
.pimg { display: block; align-self: start; border-radius: 12px; overflow: hidden; border: 2px solid var(--line); background: #fff8ea; }
.pimg img, .pimg svg { width: 100%; aspect-ratio: 4 / 5; object-fit: cover; display: block; }
.pbody { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.pbody h3 { font-size: 21px; }
.pabout { font-size: 16px; color: var(--ink-soft); }
.pbtns { display: grid; gap: 10px; margin-top: 4px; }
.pbtn { display: flex; flex-direction: column; gap: 1px; padding: 10px 16px; border-radius: 16px; border: 3px solid var(--ink); text-decoration: none; box-shadow: 0 4px 0 var(--ink); transition: transform .15s ease, box-shadow .15s ease; }
.pbtn:hover { transform: translateY(-2px); box-shadow: 0 6px 0 var(--ink); }
.pbtn b { font-size: 18px; line-height: 1.2; }
.pbtn span { font-size: 14px; line-height: 1.3; }
.pbtn-main { background: #ff2f2f; color: #fff; }
.pbtn-alt { background: #fff; color: var(--ink); }
.pbtn-alt span { color: var(--ink-soft); }
.pother { font-size: 15px; color: var(--ink-soft); margin-top: 2px; }
.pother summary { cursor: pointer; font-weight: 700; color: var(--ink); width: fit-content; }
.pother ul { margin: 8px 0 0; padding-left: 20px; display: grid; gap: 4px; }
.pother ul a, .jumpline a, .watchlink { display: inline-block; padding: 8px 2px; }
.pother a { font-weight: 700; }
.pnone { color: var(--ink-soft); }
.note-buy { font-size: 15px; color: var(--ink-soft); margin-top: 14px; }
.nav a[aria-current] { color: var(--berry); }
@media (max-width: 640px) {
  .bundle { grid-template-columns: 1fr; padding: 18px; gap: 14px; }
  .bcovers { height: 150px; }
  .bcovers img { width: 95px; }
  .bcovers img:nth-child(2) { left: 70px; } .bcovers img:nth-child(3) { left: 140px; }
  .pcard { grid-template-columns: 96px 1fr; gap: 14px; padding: 14px; }
  .pbody h3 { font-size: 19px; }
  .shophead img { width: 130px; }
  .filters button { font-size: 16px; padding: 8px 14px; }
}
@media (prefers-reduced-motion: reduce) { .pbtn { transition: none; } }
"""
    script = """
<script>
(() => {
  const btns = document.querySelectorAll('.filters button');
  const show = (f) => {
    btns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.f === f)));
    document.querySelectorAll('.pcard').forEach((c) => { c.hidden = f !== 'all' && !c.dataset.f.split(' ').includes(f); });
    document.querySelectorAll('.shopep, .shopgen.prods').forEach((s) => {
      const cards = s.querySelectorAll('.pcard');
      s.hidden = cards.length > 0 && [...cards].every((c) => c.hidden);
    });
  };
  btns.forEach((b) => b.addEventListener('click', () => show(b.dataset.f)));
  document.querySelectorAll('a[href^="http"]').forEach((a) => { if (a.host !== location.host) { a.target = '_blank'; a.rel = 'noopener'; } });
})();
</script>"""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shop Learn with Ian: books and printables</title>
<meta name="description" content="Coloring books, storybooks, printable activity packs and kids T-shirts from every Learn with Ian episode, on Amazon, Gumroad, Payhip, Lulu and more.">
<meta property="og:title" content="Shop Learn with Ian: books and printables from every episode">
<meta property="og:image" content="https://i.ytimg.com/vi/baG8fJsSXFg/maxresdefault.jpg">
<meta property="og:url" content="https://learnwithian.com/shop.html">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%23ffb321'/%3E%3Cpath d='M26 46V18M20 18h12M20 46h12' stroke='%231d2b45' stroke-width='6' stroke-linecap='round'/%3E%3Ccircle cx='44' cy='22' r='5' fill='%23ec4f7b'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@700;800&family=Atkinson+Hyperlegible:wght@400;700&display=swap" rel="stylesheet">
<style>
{style}
{shop_css}
</style>
</head>
<body>
<header class="topbar scrolled" id="topbar">
  <div class="wrap bar">
    <a class="logo rainbow" translate="no" href="./" aria-label="Learn with Ian, home"><span class="w"><span>L</span><span>E</span><span>A</span><span>R</span><span>N</span></span> <span class="w"><span>W</span><span>I</span><span>T</span><span>H</span></span> <span class="w"><span>I</span><span>A</span><span>N</span></span></a>
    <nav class="nav" aria-label="Main">
      <a href="./#episodes">Episodes</a>
      <a href="./#lessons">Lesson plans</a>
      <a href="shop.html" aria-current="page">Shop</a>
      <a href="./#contact">Contact</a>
    </nav>
    <a class="subnow" href="https://www.youtube.com/@LearnWithIanKids?sub_confirmation=1">Subscribe</a>
  </div>
</header>
<main class="wrap shopwrap">
  <div class="shopintro">
    <h1>Shop Learn with Ian</h1>
    <p>Books and printables from the episodes your child loves. You pay on a store you trust, and the price is shown there.</p>
    <div class="filters" role="group" aria-label="Show">
      <span class="flabel">Show:</span>
      <button type="button" data-f="all" aria-pressed="true">Everything</button>
      <button type="button" data-f="printable" aria-pressed="false">Print at home</button>
      <button type="button" data-f="book" aria-pressed="false">Books</button>
      <button type="button" data-f="tshirt" aria-pressed="false">T-shirts</button>
    </div>
    <nav class="jumpline" aria-label="Jump to an episode"><span>Jump to:</span>{jump}<a href="#for-every-child">ABC &amp; T-shirts</a></nav>
  </div>
  {bundle_html(SHOP.get("bundle"))}
{"".join(ep_blocks)}
  <section class="shopgen prods" id="for-every-child">
    <span class="kicker">For every child</span>
    <h2>ABC and T-shirts</h2>
    <div class="pgrid" style="margin-top:18px">{general}</div>
  </section>
  <section class="shopgen" id="stores">
    <span class="kicker">All stores</span>
    <h2>Find Ian on your favourite store</h2>
    <div class="shops" style="margin-top:18px">{stores}</div>
    <p class="note-buy">Payments, delivery and downloads are handled by each store.</p>
  </section>
</main>
<footer>
  <div class="wrap">
    <span>&copy; 2026 Learn with Ian &middot; <a href="https://www.youtube.com/@LearnWithIanKids">YouTube</a></span>
    <span>hello@learnwithian.com</span>
  </div>
</footer>
{script}
</body>
</html>
'''


def new_card(e):
    return f'''        <article class="ep">
          <div class="pic"><img src="https://i.ytimg.com/vi/{esc(e["id"])}/maxresdefault.jpg" onerror="this.onerror=null;this.src='https://i.ytimg.com/vi/{esc(e["id"])}/mqdefault.jpg'" alt="" loading="lazy" width="1280" height="720"><span class="tag">Episode {e["num"]}</span><span class="play" aria-hidden="true"><svg viewBox="0 0 24 24"><path fill="#fff" d="M7 4l14 8-14 8z"/></svg></span></div>
          <div class="txt">
            <h3>{esc(e["title"])}</h3>
            <a class="cover" href="https://www.youtube.com/watch?v={esc(e["id"])}"><span>Watch {esc(e["title"])}</span></a>
            <p class="shop"><a href="shop.html#{esc(e["slug"])}">Shop this episode</a></p>
          </div>
        </article>
'''


def replace_between(text, name, content):
    pat = re.compile(r"(<!--AUTO:%s-->)(.*?)(<!--/AUTO:%s-->)" % (name, name), re.S)
    if not pat.search(text):
        sys.exit(f"marker AUTO:{name} missing in index.html")
    return pat.sub(lambda m: m.group(1) + "\n" + content + "      " + m.group(3), text)


def main():
    feed = fetch_feed(sys.argv[1] if len(sys.argv) > 1 else None)
    allv = merge_seen(parse_feed(feed))
    eps = episode_entries(allv)
    index_path = ROOT / "index.html"
    index = index_path.read_text()
    style = re.search(r"<style>(.*?)</style>", index, re.S).group(1)
    (ROOT / "shop.html").write_text(render_shop(eps, style))
    real = [v for v in allv if not episodes_page.is_compilation(v["title"])]
    latest = sorted(real, key=lambda v: v["published"])[-1] if real else None
    if latest:
        t = short_title(latest["title"])
        hero = (f'      <div class="player">\n        <iframe src="https://www.youtube-nocookie.com/embed/{esc(latest["id"])}?rel=0" '
                f'title="{esc(t)}, the newest episode of Learn with Ian" loading="lazy" allow="accelerometer; autoplay; clipboard-write; '
                f'encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>\n      </div>\n'
                f'      <p class="player-cap">Newest episode: <b>{esc(t)}</b>.</p>\n')
        index = replace_between(index, "HERO", hero)
    index = replace_between(index, "EPS", episodes_page.home_block(eps))
    (ROOT / "episodes.html").write_text(episodes_page.render_page(eps, style))
    plans = lessons.load()
    if plans:
        index = replace_between(index, "LESSONS", lessons.home_block(plans))
        (ROOT / "lessons.html").write_text(lessons.render_page(plans, style))
    index_path.write_text(index)
    print(f"episodes: {len(eps)}, new cards: {sum(1 for e in eps if not e['manual'])}, latest: {latest and latest['id']}")


if __name__ == "__main__":
    main()
