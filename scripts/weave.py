"""The Weaver: ties the free activity pages into the rest of the site with plain text links.

Google gives little weight to a page that no other page links to. This script runs after
pages.py and adds only small text links, never a new box or section:
  1. One "all activities" page per language: play/, es/play/ and pt/play/ (index.html).
  2. Activity page: the small line above the title becomes Home > Activities > Topic,
     where "Activities" opens the list page and the topic opens the episode page.
  3. Episode page: the "Play at home" list gets one extra bullet per activity (3 at most).
  4. Footer of every page: one word, "Activities", next to "YouTube".
  5. The list pages go into sitemap.xml.
  6. Check: every page in the sitemap must be reachable from the home page by following
     links, and no internal link may be broken. The result goes to data/weave_report.json (the Guardian reads it).
Safe to run many times. Pause file: data/PAUSE_WEAVER. Never stops the site update.
"""
import datetime
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://learnwithian.com"
PREFIX = {"en": "", "es": "es/", "pt": "pt/"}
LABEL = {"en": "English", "es": "Español", "pt": "Português"}
MAX_PER_EPISODE = 3
T = {
    "en": dict(home="Home", hub="Activities", free="FREE", tips="Play at home",
               title="Free Activities for Toddlers and Preschoolers: Easy Games to Play at Home | Learn with Ian",
               h1="Free activities for toddlers and preschoolers",
               desc="Free step-by-step activities and games for children ages 2 to 6, each with a short cartoon and free printable games: colors, shapes, numbers, seasons and more.",
               lead="Easy games to play at home or in class, for ages 2 to 6. Each one takes about 15 minutes, uses things you already have, and comes with a short cartoon and free printable games."),
    "es": dict(home="Inicio", hub="Actividades", free="GRATIS", tips="Juegos para casa",
               title="Actividades gratis en inglés para niños de 2 a 6 años: juegos para casa | Learn with Ian",
               h1="Actividades gratis en inglés para niños",
               desc="Actividades y juegos gratis, paso a paso, para que los niños de 2 a 6 años aprendan inglés: colores, formas, números y más, con un dibujo animado corto y juegos imprimibles.",
               lead="Juegos fáciles para hacer en casa o en clase, para niños de 2 a 6 años. Cada uno dura unos 15 minutos, usa cosas que ya tienes y viene con un dibujo animado corto en inglés y juegos imprimibles gratis."),
    "pt": dict(home="Início", hub="Atividades", free="GRÁTIS", tips="Brincadeiras para casa",
               title="Atividades grátis em inglês para crianças de 2 a 6 anos: brincadeiras para casa | Learn with Ian",
               h1="Atividades grátis em inglês para crianças",
               desc="Atividades e brincadeiras grátis, passo a passo, para crianças de 2 a 6 anos aprenderem inglês: cores, formas, números e mais, com um desenho animado curto e jogos para imprimir.",
               lead="Brincadeiras fáceis para fazer em casa ou na sala de aula, para crianças de 2 a 6 anos. Cada uma leva uns 15 minutos, usa coisas que você já tem e vem com um desenho animado curto em inglês e jogos para imprimir grátis."),
}
YT = '<a href="https://www.youtube.com/@LearnWithIanKids">YouTube</a>'


def esc(s):
    return html.escape(s, quote=True)


def today():
    return (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=4)).date().isoformat()


def hub_path(lang):
    return f"/{PREFIX[lang]}play/"


def play_path(lang, topic):
    return f"/{PREFIX[lang]}play/{topic[lang]['slug']}.html"


def write(path, text):
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def live_topics():
    data = ROOT / "data" / "pages.json"
    if not data.exists():
        return []
    now, out = today(), []
    for tp in json.loads(data.read_text(encoding="utf-8")):
        if tp.get("live_from", "9999") > now:
            continue
        if all((ROOT / PREFIX[l] / "play" / (tp[l]["slug"] + ".html")).exists() for l in PREFIX):
            out.append(tp)
    return out


def build_hub(lang, topics):
    """The list page, made from a real activity page so it looks like the rest of the site."""
    t = T[lang]
    base = (ROOT / PREFIX[lang] / "play" / (topics[0][lang]["slug"] + ".html")).read_text(encoding="utf-8")
    head, rest = base.split("<main", 1)
    after = rest.split("</main>", 1)[1]
    me = SITE + hub_path(lang)
    head = re.sub(r"<title>.*?</title>", f"<title>{esc(t['title'])}</title>", head, flags=re.S)
    head = re.sub(r'<meta name="description"[^>]*>', f'<meta name="description" content="{esc(t["desc"])}">', head)
    head = re.sub(r'<link rel="canonical"[^>]*>', f'<link rel="canonical" href="{me}">', head)
    head = re.sub(r'<meta property="og:url"[^>]*>', f'<meta property="og:url" content="{me}">', head)
    head = re.sub(r'<meta property="og:title"[^>]*>', f'<meta property="og:title" content="{esc(t["title"])}">', head)
    head = re.sub(r'<meta property="og:description"[^>]*>', f'<meta property="og:description" content="{esc(t["desc"])}">', head)
    head = re.sub(r'<link rel="alternate" hreflang[^>]*>\s*', "", head)
    alts = "".join(f'<link rel="alternate" hreflang="{l}" href="{SITE}{hub_path(l)}">' for l in PREFIX)
    alts += f'<link rel="alternate" hreflang="x-default" href="{SITE}{hub_path("en")}">'
    head = head.replace("</head>", alts + "</head>", 1)
    head = re.sub(r'<script type="application/ld\+json">.*?</script>\s*', "", head, flags=re.S)
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": t["h1"], "description": t["desc"],
          "inLanguage": lang, "url": me, "isAccessibleForFree": True,
          "mainEntity": {"@type": "ItemList", "itemListElement": [
              {"@type": "ListItem", "position": i + 1, "name": tp[lang]["h1"], "url": SITE + play_path(lang, tp)}
              for i, tp in enumerate(topics)]}}
    head += f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>\n'
    bar = '<!--X:LANG--><div class="langbar noprint"><span aria-hidden="true">🌎</span> ' + " · ".join(
        f"<b>{LABEL[l]}</b>" if l == lang else f'<a href="{hub_path(l)}" hreflang="{l}" lang="{l}">{LABEL[l]}</a>'
        for l in PREFIX) + "</div><!--/X:LANG-->"
    head = re.sub(r"<!--X:LANG-->.*?<!--/X:LANG-->", lambda m: bar, head, flags=re.S)
    head = head.replace(' aria-current="page"', "")  # this page is not in the top menu
    groups = {}
    for tp in topics:
        groups.setdefault(tp[lang]["topic"], []).append(tp)
    boxes = "".join(
        f'<section class="sbox"><h2>{esc(name)}</h2><ul>' + "".join(
            f'<li><a href="{play_path(lang, tp)}">{esc(tp[lang]["h1"])}</a></li>' for tp in tps) + "</ul></section>\n  "
        for name, tps in groups.items())
    sm = re.search(r'<section class="signup noprint">.*?</section>', base, re.S)
    main = f'''<main class="wrap xpage">
  <p class="crumbs"><a href="/{PREFIX[lang]}">{t["home"]}</a> › {t["hub"]}</p>
  <span class="badge-free">{t["free"]}</span>
  <h1>{esc(t["h1"])}</h1>
  <p class="lead">{esc(t["lead"])}</p>
  {boxes}{sm.group(0) if sm else ""}
</main>'''
    return head + main + after


def weave_play(lang, tp):
    """Home > Activities > Topic, on the small line the page already has."""
    t, path = T[lang], ROOT / PREFIX[lang] / "play" / (tp[lang]["slug"] + ".html")
    text = path.read_text(encoding="utf-8")
    topic = esc(tp[lang]["topic"])
    if (ROOT / PREFIX[lang] / "ep" / (tp["episode"] + ".html")).exists():
        topic = f'<a href="/{PREFIX[lang]}ep/{tp["episode"]}.html">{topic}</a>'
    crumbs = (f'<p class="crumbs"><a href="/{PREFIX[lang]}">{t["home"]}</a> › '
              f'<a href="{hub_path(lang)}">{t["hub"]}</a> › {topic}</p>')
    return write(path, re.sub(r'<p class="crumbs">.*?</p>', lambda m: crumbs, text, count=1, flags=re.S))


def weave_episode(lang, slug, topics):
    """One extra bullet per activity in the list of home games the episode page already has."""
    path = ROOT / PREFIX[lang] / "ep" / (slug + ".html")
    if not path.exists():
        return False
    text = re.sub(r'<li class="wv">.*?</li>', "", path.read_text(encoding="utf-8"), flags=re.S)
    items = "".join(f'<li class="wv"><a href="{play_path(lang, tp)}">{esc(tp[lang]["h1"])}</a></li>'
                    for tp in topics[-MAX_PER_EPISODE:])
    pat = r"(<h2>" + re.escape(T[lang]["tips"]) + r"</h2>\s*<ul>.*?)(</ul>)"
    return write(path, re.sub(pat, lambda m: m.group(1) + items + m.group(2), text, count=1, flags=re.S))


def weave_footers(langs):
    n = 0
    for path in ROOT.rglob("*.html"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(".") or rel.startswith("google"):
            continue
        lang = "es" if rel.startswith("es/") else "pt" if rel.startswith("pt/") else "en"
        if lang not in langs:
            continue
        text = path.read_text(encoding="utf-8")
        link = f' &middot; <a class="wv" href="{hub_path(lang)}">{T[lang]["hub"]}</a>'
        if link in text or YT + "</span>" not in text:
            continue
        n += write(path, text.replace(YT + "</span>", YT + link + "</span>"))
    return n


def to_file(href, here):
    """Internal link -> file path inside the repo (None for outside links, anchors, mail)."""
    href = href.split("#", 1)[0].split("?", 1)[0]
    if href.startswith(SITE):
        href = href[len(SITE):] or "/"
    if not href or re.match(r"[a-z]+:", href) or href.startswith("//"):
        return None
    p = href.lstrip("/") if href.startswith("/") else (Path(here).parent / href).as_posix().lstrip("./")
    if p == "" or p.endswith("/"):
        p += "index.html"
    return p


def check():
    """Walk the site from the home page, link by link, like a search engine does."""
    pages, links, broken = {}, {}, []
    for path in ROOT.rglob("*.html"):
        rel = path.relative_to(ROOT).as_posix()
        if not rel.startswith("."):
            pages[rel] = path.read_text(encoding="utf-8", errors="ignore")
    for rel, text in pages.items():
        out = set()
        for href in set(re.findall(r'<a\b[^>]*?href="([^"]+)"', text)):
            target = to_file(html.unescape(href), rel)
            if not target or target == rel:
                continue
            if target.endswith(".html") and target not in pages:
                broken.append(f"{rel} -> /{target}")
            out.add(target)
        links[rel] = out
    clicks, queue = {"index.html": 0}, ["index.html"]
    while queue:
        cur = queue.pop(0)
        for nxt in links.get(cur, ()):
            if nxt in pages and nxt not in clicks:
                clicks[nxt] = clicks[cur] + 1
                queue.append(nxt)
    sm = ROOT / "sitemap.xml"
    locs = re.findall(r"<loc>([^<]+)</loc>", sm.read_text()) if sm.exists() else []
    files = [f for f in (to_file(loc, "") for loc in locs) if f in pages]
    orphans = sorted("/" + f for f in files if f not in clicks)
    return {"pages_checked": len(files), "orphans": orphans, "broken": sorted(broken),
            "max_clicks_from_home": max([clicks[f] for f in files if f in clicks] or [0])}


def main():
    if (ROOT / "data" / "PAUSE_WEAVER").exists():
        print("weave: paused (data/PAUSE_WEAVER)")
        return
    topics = live_topics()
    if not topics:
        print("weave: no activity pages yet")
        return
    changed = 0
    for lang in PREFIX:
        changed += write(ROOT / PREFIX[lang] / "play" / "index.html", build_hub(lang, topics))
        for tp in topics:
            changed += weave_play(lang, tp)
        by_ep = {}
        for tp in topics:
            by_ep.setdefault(tp["episode"], []).append(tp)
        for slug, tps in by_ep.items():
            changed += weave_episode(lang, slug, tps)
    changed += weave_footers(set(PREFIX))
    sm = ROOT / "sitemap.xml"
    if sm.exists():
        text = sm.read_text()
        add = "".join(f"  <url><loc>{SITE}{hub_path(l)}</loc><priority>0.8</priority></url>\n"
                      for l in PREFIX if f"<loc>{SITE}{hub_path(l)}</loc>" not in text)
        if add:
            sm.write_text(text.replace("</urlset>", add + "</urlset>"))
    report = check()
    write(ROOT / "data" / "weave_report.json", json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(f"weave: {len(topics)} activities linked, {changed} files changed, "
          f"{len(report['orphans'])} pages without a link, {len(report['broken'])} broken links")
    for x in report["orphans"] + report["broken"]:
        print("weave:   ", x)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never stop the site update
        print("weave: failed, site untouched:", repr(e))
