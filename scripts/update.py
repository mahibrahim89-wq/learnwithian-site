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


def esc(s):
    return html.escape(str(s), quote=True)


def store_of(url):
    for dom, name in STORE_BY_DOMAIN:
        if dom in url:
            return name
    return None


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


def group_products(links):
    """Links tagged (EpN) are one product sold on several stores; others stand alone."""
    tagged = [l for l in links if re.search(r"\(Ep\s*\d+\)", l["label"])]
    other = [l for l in links if l not in tagged]
    prods = []
    if tagged:
        names = sorted((clean_name(l["label"]) for l in tagged), key=len, reverse=True)
        prods.append({"name": names[0], "kind": "Printable", "links": [{"store": l["store"], "url": l["url"]} for l in tagged]})
    for l in other:
        prods.append({"name": clean_name(l["label"]) or l["store"], "kind": "", "links": [{"store": l["store"], "url": l["url"]}]})
    return prods


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "episode"


def merge_seen(new):
    seen = json.loads(SEEN_PATH.read_text()) if SEEN_PATH.exists() else []
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
    general_urls = {l["url"] for g in SHOP["general"] for l in g["links"]} | {s["url"] for s in SHOP["stores"]}
    known = [v for v in allv]
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
        prods = group_products([l for l in v["links"] if l["url"] not in general_urls])
        title = short_title(v["title"])
        eps.append({"id": v["id"], "num": i, "slug": slugify(title), "title": title,
                    "learn": "", "products": prods, "manual": False})
    return eps


def product_html(p):
    links = p["links"]
    main, rest = links[0], links[1:]
    main_label = "See price on " + main["store"]
    more = "".join(
        f'<a href="{esc(l["url"])}">{esc(l["store"])}{(" · " + esc(l["label"])) if l.get("label") else ""}</a>'
        for l in rest)
    kind = f'<span class="pkind">{esc(p["kind"])}</span>' if p.get("kind") else ""
    first_label = f' <span class="plabel">({esc(main["label"])})</span>' if main.get("label") else ""
    return (f'<div class="product"><div class="ptext"><b>{esc(p["name"])}</b>{kind}</div>'
            f'<a class="btn btn-red pbuy" href="{esc(main["url"])}">{main_label}{first_label}</a>'
            + (f'<div class="pmore"><span>Also on:</span> {more}</div>' if more else "") + '</div>')


def render_shop(eps, style):
    ep_blocks = []
    for e in eps:
        prods = "".join(product_html(p) for p in e["products"]) or \
            '<p class="pnone">Books and printables for this episode are coming soon.</p>'
        ep_blocks.append(f'''
    <section class="shopep" id="{esc(e["slug"])}">
      <div class="shophead">
        <img src="https://i.ytimg.com/vi/{esc(e["id"])}/mqdefault.jpg" alt="" width="320" height="180" loading="lazy">
        <div>
          <span class="kicker">Episode {e["num"]}</span>
          <h2>{esc(e["title"])}</h2>
          <a class="watchlink" href="https://www.youtube.com/watch?v={esc(e["id"])}">Watch the episode free on YouTube &rarr;</a>
        </div>
      </div>
      <div class="products">{prods}</div>
    </section>''')
    jump = "".join(f'<a href="#{esc(e["slug"])}">Ep {e["num"]}: {esc(e["title"].split(": ")[-1])}</a>' for e in eps)
    general = "".join(product_html(p) for p in SHOP["general"])
    stores = "".join(f'<a class="shopcard" href="{esc(s["url"])}"><b>{esc(s["name"])}</b><span>{esc(s["what"])}</span></a>'
                     for s in SHOP["stores"])
    shop_css = """
.shopwrap { padding: 28px 0 40px; }
.shopintro h1 { font-size: clamp(38px, 6vw, 64px); font-weight: 800; }
.shopintro p { margin-top: 10px; color: var(--ink-soft); font-size: 19px; }
.shopep, .shopgen { padding: 34px 0; border-bottom: 2px dashed var(--line); }
.shophead { display: flex; gap: 18px; align-items: center; margin-bottom: 18px; flex-wrap: wrap; }
.shophead img { width: 200px; height: auto; aspect-ratio: 16 / 9; object-fit: cover; border-radius: 14px; border: 3px solid var(--ink); }
.shophead h2 { font-size: clamp(26px, 3.4vw, 36px); }
.watchlink { font-weight: 700; color: var(--ink); text-decoration-color: var(--sun); text-decoration-thickness: 3px; text-underline-offset: 4px; }
.products { display: grid; gap: 14px; }
.product { display: grid; grid-template-columns: 1fr auto; gap: 8px 18px; align-items: center; background: #fff; border: 2px solid var(--ink); border-radius: 18px; padding: 16px 18px; }
.ptext b { display: block; font-size: 19px; }
.pkind { color: var(--ink-soft); font-size: 15px; }
.pbuy { font-size: 16px; padding: 10px 18px; white-space: nowrap; }
.plabel { font-weight: 400; opacity: .9; }
.pmore { grid-column: 1 / -1; font-size: 15px; color: var(--ink-soft); display: flex; flex-wrap: wrap; gap: 6px 14px; }
.pmore a { font-weight: 700; }
.pnone { color: var(--ink-soft); }
.note-buy { font-size: 15px; color: var(--ink-soft); margin-top: 14px; }
@media (max-width: 640px) { .product { grid-template-columns: 1fr; } .pbuy { white-space: normal; } .shophead img { width: 100%; } }
"""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shop Learn with Ian</title>
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
    <a class="logo rainbow" href="./" aria-label="Learn with Ian, home"><span class="w"><span>L</span><span>E</span><span>A</span><span>R</span><span>N</span></span> <span class="w"><span>W</span><span>I</span><span>T</span><span>H</span></span> <span class="w"><span>I</span><span>A</span><span>N</span></span></a>
    <nav class="nav" aria-label="Main">
      <a href="./#episodes">Episodes</a>
      <a href="./#lessons">Lesson plans</a>
      <a href="./#contact">Contact</a>
    </nav>
    <a class="subnow" href="https://www.youtube.com/@LearnWithIanKids?sub_confirmation=1">Subscribe</a>
  </div>
</header>
<main class="wrap shopwrap">
  <div class="shopintro">
    <h1>Shop Learn with Ian</h1>
    <p>Books, printables and T-shirts from every episode. You buy on the store you trust; prices are shown there.</p>
    <nav class="jump" aria-label="Jump to an episode" style="margin-top:18px">{jump}<a href="#for-every-child">For every child</a><a href="#stores">All stores</a></nav>
  </div>
{"".join(ep_blocks)}
  <section class="shopgen" id="for-every-child">
    <span class="kicker">For every child</span>
    <h2>Bundles, ABC and T-shirts</h2>
    <div class="products" style="margin-top:18px">{general}</div>
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
    latest = sorted(allv, key=lambda v: v["published"])[-1] if allv else None
    if latest:
        t = short_title(latest["title"])
        hero = (f'      <div class="player">\n        <iframe src="https://www.youtube-nocookie.com/embed/{esc(latest["id"])}?rel=0" '
                f'title="{esc(t)}, the newest episode of Learn with Ian" loading="lazy" allow="accelerometer; autoplay; clipboard-write; '
                f'encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>\n      </div>\n'
                f'      <p class="player-cap">Newest episode: <b>{esc(t)}</b>.</p>\n')
        index = replace_between(index, "HERO", hero)
    cards = "".join(new_card(e) for e in eps if not e["manual"])
    index = replace_between(index, "NEWEPS", cards)
    index_path.write_text(index)
    print(f"episodes: {len(eps)}, new cards: {sum(1 for e in eps if not e['manual'])}, latest: {latest and latest['id']}")


if __name__ == "__main__":
    main()
