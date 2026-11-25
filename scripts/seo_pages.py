"""Search pages for learnwithian.com.

Builds, on every robot run:
  * ep/<slug>.html: one page per episode, so Google can show each episode on its
    own (video, what the child learns, the free lesson plan, the printables),
  * sitemap.xml and robots.txt, so search engines find every page.
Uses only the Python standard library. Old pages are left alone.
"""
import html
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://learnwithian.com"
FREE_PACK = "https://drive.google.com/file/d/1v_QMRmjt9kUwq4TWjq3l_vBXLdii6hn5/view"
CHANNEL = "https://www.youtube.com/@LearnWithIanKids"


def esc(s):
    return html.escape(str(s), quote=True)


def keyword_part(yt_title, short):
    """'Colors for Toddlers | Ian's Color Day | Learn with Ian' -> 'Colors for Toddlers'."""
    parts = [p.strip() for p in (yt_title or "").split("|") if p.strip()]
    for p in parts:
        if p != short and "Learn with Ian" not in p and "Ian's" not in p and "Ian’s" not in p:
            return p
    return ""


def items(s):
    return "".join(f"<li>{esc(x.strip())}</li>" for x in (s or "").split("|") if x.strip())


def clip(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def plan_html(l):
    if not l:
        return ""
    return f'''
  <section class="sbox" id="lesson-plan">
    <span class="kicker">Free lesson plan</span>
    <h2>Use this episode in class</h2>
    <p><b>Goal:</b> {esc(l["goal"])}</p>
    <h3>Before you press play</h3>
    <ul>{items(l["before"])}</ul>
    <h3>Pause and ask</h3>
    <ul>{items(l["pause"])}</ul>
    <h3>After the episode</h3>
    <ul>{items(l["after"])}</ul>
    <h3>Activity</h3>
    <p>{esc(l["activity"])}</p>
    <p><a href="/lessons.html#plan-{esc(l["episode"])}">Print this lesson plan</a></p>
  </section>'''


def products_html(e):
    rows = []
    for p in e.get("products") or []:
        links = p.get("links") or []
        if not links:
            continue
        best = next((x for x in links if x.get("store") == "Payhip"), links[0])
        about = f' <span>{esc(p["about"])}</span>' if p.get("about") else ""
        rows.append(f'<li><a href="{esc(best["url"])}">{esc(p["name"])}</a>{about}</li>')
    shop = f'<p><a href="/shop.html#{esc(e["slug"])}">See every store for this episode</a></p>' if rows else ""
    return f'''
  <section class="sbox" id="printables">
    <span class="kicker">Printables</span>
    <h2>Worksheets for this episode</h2>
    <ul>{"".join(rows)}<li><a href="{FREE_PACK}">Free printable teacher pack</a> <span>Counting, tracing and shapes. Free for every class.</span></li></ul>
    {shop}
  </section>'''


def page(e, v, l, others, style):
    vid = e["id"]
    short = e["title"].split(": ")[-1] if "Ian" in e["title"].split(": ")[-1] else e["title"]
    kw = keyword_part(v.get("title", ""), short)
    h1 = f"{kw}: {short}" if kw else short
    title = f"{h1} – Free Video & Lesson Plan"
    learn = (l or {}).get("goal") or e.get("learn") or ""
    mins = (l or {}).get("minutes") or ""
    desc = clip(f"Watch {short}, a free {mins + '-minute ' if mins else ''}cartoon for toddlers and preschoolers. "
                f"{learn} Free lesson plan and printable worksheets.", 158)
    url = f"{SITE}/ep/{e['slug']}.html"
    thumb = f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg"
    published = v.get("published") or ""
    video_ld = {
        "@context": "https://schema.org", "@type": "VideoObject",
        "name": h1, "description": desc, "thumbnailUrl": [thumb],
        "embedUrl": f"https://www.youtube.com/embed/{vid}",
        "contentUrl": f"https://www.youtube.com/watch?v={vid}",
        "isFamilyFriendly": True, "inLanguage": "en",
        "publisher": {"@type": "Organization", "name": "Learn with Ian", "url": SITE + "/"},
    }
    if published and published != "0":
        video_ld["uploadDate"] = published
    if mins.isdigit():
        video_ld["duration"] = f"PT{int(mins)}M"
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Learn with Ian", "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": "Episodes", "item": SITE + "/episodes.html"},
        {"@type": "ListItem", "position": 3, "name": short, "item": url}]}
    more = "".join(f'<li><a href="/ep/{esc(o["slug"])}.html">{esc(o["title"])}</a></li>' for o in others)
    learn_p = f'<p class="lead"><b>Your child learns:</b> {esc(learn)}</p>' if learn else ""
    css = """
.swrap { padding: 24px 0 48px; max-width: 860px; }
.swrap h1 { font-size: clamp(30px, 5vw, 48px); font-weight: 800; line-height: 1.15; }
.swrap .lead { font-size: 20px; margin: 10px 0 18px; }
.swrap .player { margin: 8px 0 6px; }
.sbox { background: #fff; border: 3px solid var(--line); border-radius: 20px; padding: 20px 22px; margin-top: 22px; }
.sbox h2 { font-size: clamp(24px, 4vw, 32px); font-weight: 800; margin: 4px 0 10px; }
.sbox h3 { font-size: 20px; margin: 14px 0 4px; }
.sbox ul { margin: 6px 0; padding-left: 22px; }
.sbox li { margin: 4px 0; }
.sbox li span { color: var(--ink-soft); }
.sbox a { color: var(--sky); font-weight: 700; }
.nav a[aria-current] { color: var(--berry); }
.crumbs { font-size: 15px; color: var(--ink-soft); margin-bottom: 6px; }
.crumbs a { color: var(--ink-soft); }
"""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="video.other">
<meta property="og:title" content="{esc(h1)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{thumb}">
<meta property="og:url" content="{url}">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%23ffb321'/%3E%3Cpath d='M26 46V18M20 18h12M20 46h12' stroke='%231d2b45' stroke-width='6' stroke-linecap='round'/%3E%3Ccircle cx='44' cy='22' r='5' fill='%23ec4f7b'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@700;800&family=Atkinson+Hyperlegible:wght@400;700&display=swap" rel="stylesheet">
<script type="application/ld+json">{json.dumps(video_ld, ensure_ascii=False)}</script>
<script type="application/ld+json">{json.dumps(crumbs, ensure_ascii=False)}</script>
<style>
{style}
{css}
</style>
</head>
<body>
<header class="topbar scrolled" id="topbar">
  <div class="wrap bar">
    <a class="logo rainbow" translate="no" href="/" aria-label="Learn with Ian, home"><span class="w"><span>L</span><span>E</span><span>A</span><span>R</span><span>N</span></span> <span class="w"><span>W</span><span>I</span><span>T</span><span>H</span></span> <span class="w"><span>I</span><span>A</span><span>N</span></span></a>
    <nav class="nav" aria-label="Main">
      <a href="/episodes.html" aria-current="page">Episodes</a>
      <a href="/lessons.html">Lesson plans</a>
      <a href="/shop.html">Shop</a>
      <a href="/#contact">Contact</a>
    </nav>
    <a class="subnow" href="{CHANNEL}?sub_confirmation=1">Subscribe</a>
  </div>
</header>
<main class="wrap swrap">
  <p class="crumbs"><a href="/">Home</a> › <a href="/episodes.html">Episodes</a> › Episode {e["num"]}</p>
  <h1>{esc(h1)}</h1>
  {learn_p}
  <div class="player">
    <iframe src="https://www.youtube-nocookie.com/embed/{esc(vid)}?rel=0" title="{esc(short)}, a Learn with Ian episode" loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
  </div>
  <p>Free to watch on <a href="https://www.youtube.com/watch?v={esc(vid)}">YouTube</a>. Calm, simple and made for ages 2 to 6, at home or in class.</p>
{plan_html(l)}
{products_html(e)}
  <section class="sbox" id="more">
    <span class="kicker">More episodes</span>
    <h2>Watch next</h2>
    <ul>{more}</ul>
    <p><a href="{CHANNEL}?sub_confirmation=1">Subscribe on YouTube for a new episode every week</a></p>
  </section>
</main>
<footer>
  <div class="wrap">
    <span>&copy; 2026 Learn with Ian &middot; <a href="{CHANNEL}">YouTube</a></span>
    <span>hello@learnwithian.com</span>
  </div>
</footer>
<script>
document.querySelectorAll('a[href^="http"]').forEach((a) => {{ if (a.host !== location.host) {{ a.target = '_blank'; a.rel = 'noopener'; }} }});
</script>
</body>
</html>
'''


def build(eps, allv, plans, style):
    """Write ep/*.html, sitemap.xml and robots.txt. Returns the number of episode pages."""
    by_id = {v["id"]: v for v in allv}
    plan_by_id = {p["youtube_id"]: p for p in plans}
    plan_by_num = {int(p["episode"]): p for p in plans}
    out = ROOT / "ep"
    out.mkdir(exist_ok=True)
    ordered = sorted(eps, key=lambda e: e["num"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [(SITE + "/", today, "1.0"), (SITE + "/episodes.html", today, "0.9"),
            (SITE + "/lessons.html", today, "0.9"), (SITE + "/shop.html", today, "0.7")]
    for e in ordered:
        v = by_id.get(e["id"], {})
        l = plan_by_id.get(e["id"]) or plan_by_num.get(e["num"])
        others = [o for o in sorted(ordered, key=lambda o: o["num"], reverse=True) if o["id"] != e["id"]][:4]
        (out / f'{e["slug"]}.html').write_text(page(e, v, l, others, style))
        when = (v.get("published") or "")[:10]
        urls.append((f'{SITE}/ep/{e["slug"]}.html', when if len(when) == 10 else today, "0.8"))
    sm = "".join(f"  <url><loc>{u}</loc><lastmod>{d}</lastmod><priority>{p}</priority></url>\n" for u, d, p in urls)
    (ROOT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + sm + "</urlset>\n")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")
    return len(ordered)


def main():
    """Run after update.py (same workflow): reads what update.py saved and builds the search pages."""
    import re
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import lessons
    import update
    allv = json.loads((ROOT / "data" / "episodes.json").read_text())
    eps = update.episode_entries(allv)
    style = re.search(r"<style>(.*?)</style>", (ROOT / "index.html").read_text(), re.S).group(1)
    cache = ROOT / "data" / "lessons.csv"
    plans = lessons.parse(cache.read_text()) if cache.exists() else []
    print("episode pages:", build(eps, allv, plans, style))


if __name__ == "__main__":
    main()
