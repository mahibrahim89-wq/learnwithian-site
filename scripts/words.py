"""Word pages in Spanish and Portuguese: the English words of one episode, what they mean
and how to say them ("Los colores en inglés para niños"). Parents in Latin America and Brazil
search for exactly these lists; the channel teaches English, so this is our own ground.

The content is in data/words.json (one entry = one episode = two pages), written by hand or
by scripts/words_write.py. Pages go to es/palabras/ and pt/palavras/, built from the episode
page of the same language so they look like the rest of the site, and into sitemap.xml.
No printable, no prices, no shops. Safe to run many times. Never stops the site update.
"""
import datetime
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://learnwithian.com"
DIR = {"es": "es/palabras", "pt": "pt/palavras"}
LABEL = {"en": "English", "es": "Español", "pt": "Português"}
T = {
    "es": dict(home="Inicio", free="GRATIS", age="De 2 a 6 años", h_words="Las {n} palabras", cols=("Inglés", "Español", "Se dice"),
               h_phr="Frases fáciles", h_tip="Cómo practicar en casa", h_watch="Escucha las palabras en el episodio",
               watch="Mira el episodio completo gratis en YouTube", more="Para jugar con estas palabras:"),
    "pt": dict(home="Início", free="GRÁTIS", age="De 2 a 6 anos", h_words="As {n} palavras", cols=("Inglês", "Português", "Como se fala"),
               h_phr="Frases fáceis", h_tip="Como praticar em casa", h_watch="Ouça as palavras no episódio",
               watch="Assista ao episódio completo grátis no YouTube", more="Para brincar com estas palavras:"),
}
CSS = """<!--X:WORDCSS--><style>
.wlist{list-style:none;margin:0;padding:0}
.wlist li{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:10px;align-items:center;padding:10px 0;border-top:2px solid var(--line)}
.wlist li.dots{grid-template-columns:22px 1.1fr 1fr 1fr}
.wlist li:first-child{border-top:0}
.wlist .dot{width:20px;height:20px;border-radius:50%;border:2px solid var(--ink)}
.wlist .en{font-family:var(--display);font-weight:800;font-size:clamp(22px,5vw,30px);color:#ec4f7b}
.wlist .say{color:var(--ink-soft);font-size:15px}
.wlist .hd{font-size:13px;color:var(--ink-soft);font-weight:700}
.phr{list-style:none;margin:0;padding:0}.phr li{padding:6px 0}.phr b{display:block}
</style><!--/X:WORDCSS-->"""


def esc(s):
    return html.escape(str(s), quote=True)


def today():
    return (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=4)).date().isoformat()


def url(lang, entry):
    return f"{SITE}/{DIR[lang]}/{entry[lang]['slug']}.html"


def live_entries():
    p = ROOT / "data" / "words.json"
    if not p.exists():
        return []
    return [e for e in json.loads(p.read_text(encoding="utf-8")) if e.get("live_from", "9999") <= today()
            and all((ROOT / l / "ep" / f"{e['episode']}.html").exists() for l in DIR)]


def play_link(lang, episode):
    """The newest activity page of this episode in this language, if there is one."""
    p = ROOT / "data" / "pages.json"
    if not p.exists():
        return ""
    for tp in reversed(json.loads(p.read_text(encoding="utf-8"))):
        f = ROOT / lang / "play" / f"{tp.get(lang, {}).get('slug', '')}.html"
        if tp.get("episode") == episode and tp.get("live_from", "9999") <= today() and f.exists():
            return f'<a href="/{lang}/play/{tp[lang]["slug"]}.html">{esc(re.sub(r"<[^>]+>", "", tp[lang]["h1"]))}</a>'
    return ""


def build(entry, lang):
    d, t = entry[lang], T[lang]
    base = (ROOT / lang / "ep" / f"{entry['episode']}.html").read_text(encoding="utf-8")
    head, rest = base.split("<main", 1)
    after = rest.split("</main>", 1)[1]
    me = url(lang, entry)
    head = re.sub(r"<title>.*?</title>", f"<title>{esc(d['title'])}</title>", head, flags=re.S)
    head = re.sub(r'<meta name="description"[^>]*>', f'<meta name="description" content="{esc(d["desc"])}">', head)
    head = re.sub(r'<link rel="canonical"[^>]*>', f'<link rel="canonical" href="{me}">', head)
    head = re.sub(r'<meta property="og:url"[^>]*>', f'<meta property="og:url" content="{me}">', head)
    head = re.sub(r'<meta property="og:title"[^>]*>', f'<meta property="og:title" content="{esc(d["title"])}">', head)
    head = re.sub(r'<meta property="og:description"[^>]*>', f'<meta property="og:description" content="{esc(d["desc"])}">', head)
    head = re.sub(r'<link rel="alternate" hreflang[^>]*>\s*', "", head)
    alts = "".join(f'<link rel="alternate" hreflang="{l}" href="{url(l, entry)}">' for l in DIR)
    head = re.sub(r'<script type="application/ld\+json">.*?</script>\s*', "", head, flags=re.S)
    head = re.sub(r"<!--X:WORDCSS-->.*?<!--/X:WORDCSS-->", "", head, flags=re.S)
    head = head.replace("</head>", alts + CSS + "</head>", 1)
    ld = {"@context": "https://schema.org", "@type": "LearningResource", "name": d["h1"], "description": d["desc"], "inLanguage": lang,
          "educationalLevel": "Preschool", "typicalAgeRange": "2-6", "isAccessibleForFree": True, "url": me, "teaches": "English vocabulary",
          "provider": {"@type": "Organization", "name": "Learn with Ian", "url": SITE + "/"}}
    head += f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>\n'
    bar = '<!--X:LANG--><div class="langbar noprint"><span aria-hidden="true">🌎</span> ' + " · ".join(
        [f'<a href="/ep/{entry["episode"]}.html" hreflang="en" lang="en">English</a>'] +
        [f"<b>{LABEL[l]}</b>" if l == lang else f'<a href="/{DIR[l]}/{entry[l]["slug"]}.html" hreflang="{l}" lang="{l}">{LABEL[l]}</a>' for l in DIR]
    ) + "</div><!--/X:LANG-->"
    after = re.sub(r"<!--X:LANG-->.*?<!--/X:LANG-->", "", after, flags=re.S)
    head = re.sub(r"<!--X:LANG-->.*?<!--/X:LANG-->", lambda m: bar, head, flags=re.S)
    yt = re.search(r"embed/([A-Za-z0-9_-]{11})", base)
    dots = all(w.get("color") for w in d["words"])
    cls = ' class="dots"' if dots else ""
    hdr = f'<li{cls}>' + ("<span></span>" if dots else "") + "".join(f'<span class="hd">{c}</span>' for c in t["cols"]) + "</li>"
    rows = "".join(
        f'<li{cls}>' + (f'<span class="dot" style="background:{esc(w["color"])}"></span>' if dots else "")
        + f'<span class="en" lang="en">{esc(w["en"])}</span><span>{esc(w["tr"])}</span><span class="say">{esc(w["say"])}</span></li>'
        for w in d["words"])
    sm = re.search(r'<section class="signup noprint">.*?</section>', base, re.S)
    more = play_link(lang, entry["episode"])
    video = (f'''<section class="sbox"><h2>{t["h_watch"]}</h2>
    <div class="player"><iframe src="https://www.youtube-nocookie.com/embed/{yt.group(1)}?rel=0" title="Learn with Ian" loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>
    <p style="margin-top:10px"><a href="https://www.youtube.com/watch?v={yt.group(1)}">{t["watch"]}</a></p></section>''' if yt else "")
    clean = lambda s: re.sub(r"<(?!/?b>)[^>]*>", "", s)
    main = f'''<main class="wrap xpage">
  <p class="crumbs"><a href="/{lang}/">{t["home"]}</a> › <a href="/{lang}/ep/{entry["episode"]}.html">{esc(d["topic"])}</a></p>
  <span class="badge-free">{t["free"]}</span>
  <h1>{esc(d["h1"])}</h1>
  <p class="lead">{esc(d["lead"])}</p>
  <p style="margin-top:10px"><span class="badge-free">{t["age"]}</span></p>
  <section class="sbox"><h2>{t["h_words"].format(n=len(d["words"]))}</h2><ul class="wlist">{hdr}{rows}</ul></section>
  <section class="sbox"><h2>{t["h_phr"]}</h2><ul class="phr">{"".join(f'<li><b lang="en">{esc(a)}</b>{esc(b)}</li>' for a, b in d["phrases"])}</ul></section>
  <section class="sbox"><h2>{t["h_tip"]}</h2><ul>{"".join(f"<li>{clean(x)}</li>" for x in d["tips"])}</ul>{f"<p>{t['more']} {more}</p>" if more else ""}</section>
  {video}
  {sm.group(0) if sm else ""}
</main>'''
    return head + main + after


def main():
    entries, urls, built = live_entries(), [], 0
    for e in entries:
        try:
            outs = {l: build(e, l) for l in DIR}
        except Exception as ex:
            print("words: SKIPPED", e.get("episode"), "->", repr(ex))
            continue
        for l, page in outs.items():
            out = ROOT / DIR[l] / f"{e[l]['slug']}.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            if not out.exists() or out.read_text(encoding="utf-8") != page:
                out.write_text(page, encoding="utf-8")
            urls.append(url(l, e))
            built += 1
    sm = ROOT / "sitemap.xml"
    if sm.exists() and urls:
        text = sm.read_text()
        add = "".join(f"  <url><loc>{u}</loc><priority>0.7</priority></url>\n" for u in urls if f"<loc>{u}</loc>" not in text)
        if add:
            sm.write_text(text.replace("</urlset>", add + "</urlset>"))
    print("words: built", built, "pages for", len(entries), "episodes")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never stop the site update
        print("words: failed, site untouched:", repr(e))
