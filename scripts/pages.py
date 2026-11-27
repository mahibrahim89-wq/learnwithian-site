"""Free activity pages: one page per search phrase, in English, Spanish and Portuguese.

The content is in data/pages.json (one entry = one topic = three pages). Every page is built
from the real episode page of the same language, so it looks exactly like the rest of the site.
Pages go to play/, es/play/ and pt/play/ and are added to sitemap.xml. A topic goes live
on its "live_from" date (Dubai time). Safe to run many times. If anything is wrong with a
topic (see pages_check.py), that topic is skipped and the rest of the site is not touched.
Run with --all to build every topic regardless of date (preview only).
"""
import datetime
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://learnwithian.com"
PREFIX = {"en": "", "es": "es/", "pt": "pt/"}
LABEL = {"en": "English", "es": "Español", "pt": "Português"}
T = {
    "en": dict(home="Home", free="FREE", age="Ages 2 to 6", mins="15 minutes", learns="Your child learns:", kicker="Free lesson plan",
               words="Words to practice", need="What you need", play="How to play", ease="Easier or harder", watch="Watch the episode",
               watchlink="Watch the full episode free on YouTube", acts_h="Free printable {g} activities",
               acts_p="For preschool and toddlers, made from the episode pictures. Watch the episode, then print and play."),
    "es": dict(home="Inicio", free="GRATIS", age="De 2 a 6 años", mins="15 minutos", learns="Tu hijo aprende:", kicker="Plan de clase gratis",
               words="Palabras para practicar", need="Qué necesitas", play="Cómo jugar", ease="Más fácil o más difícil", watch="Mira el episodio",
               watchlink="Mira el episodio completo gratis en YouTube", acts_h="Juegos imprimibles gratis de {g}",
               acts_p="Para preescolar y niños pequeños, hechos con las imágenes del episodio. Mira el episodio, luego imprime y juega."),
    "pt": dict(home="Início", free="GRÁTIS", age="De 2 a 6 anos", mins="15 minutos", learns="Seu filho aprende:", kicker="Plano de aula grátis",
               words="Palavras para praticar", need="O que você precisa", play="Como brincar", ease="Mais fácil ou mais difícil", watch="Assista ao episódio",
               watchlink="Assista ao episódio completo grátis no YouTube", acts_h="Jogos para imprimir grátis do {g}",
               acts_p="Para a educação infantil e crianças pequenas, feitos com as imagens do episódio. Assista ao episódio, depois imprima e brinque."),
}
GAME = {
    "es": [("Story sequencing cards", "Tarjetas para ordenar la historia"), ("4 pictures to put in order", "4 imágenes para ordenar"),
           ("Picture puzzle", "Rompecabezas"), ("6 pieces to cut and build", "6 piezas para recortar y armar"),
           ("Memory match game", "Juego de memoria"), ("12 cards, find the pairs", "12 cartas, encuentra las parejas"), ("Free PDF:", "PDF gratis:")],
    "pt": [("Story sequencing cards", "Cartões para ordenar a história"), ("4 pictures to put in order", "4 imagens para ordenar"),
           ("Picture puzzle", "Quebra-cabeça"), ("6 pieces to cut and build", "6 peças para recortar e montar"),
           ("Memory match game", "Jogo da memória"), ("12 cards, find the pairs", "12 cartas, encontre os pares"), ("Free PDF:", "PDF grátis:")],
}


def rd(p):
    return (ROOT / p).read_text(encoding="utf-8")


def today():
    return (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=4)).date().isoformat()


def url(lang, slug):
    return f"{SITE}/{PREFIX[lang]}play/{slug}.html"


def build_page(topic, lang):
    d, t = topic[lang], T[lang]
    ep = topic["episode"]
    base_file = f"{PREFIX[lang]}ep/{ep}.html"
    base = rd(base_file)
    head, rest = base.split("<main", 1)
    after = rest.split("</main>", 1)[1]
    head = re.sub(r"<title>.*?</title>", f"<title>{html.escape(d['title'])}</title>", head, flags=re.S)
    head = re.sub(r'<meta name="description"[^>]*>', f'<meta name="description" content="{html.escape(d["desc"])}">', head)
    me = url(lang, d["slug"])
    head = re.sub(r'<link rel="canonical"[^>]*>', f'<link rel="canonical" href="{me}">', head)
    head = re.sub(r'<meta property="og:url"[^>]*>', f'<meta property="og:url" content="{me}">', head)
    head = re.sub(r'<meta property="og:title"[^>]*>', f'<meta property="og:title" content="{html.escape(d["title"])}">', head)
    head = re.sub(r'<meta property="og:description"[^>]*>', f'<meta property="og:description" content="{html.escape(d["desc"])}">', head)
    head = re.sub(r'<meta property="og:type"[^>]*>', '<meta property="og:type" content="article">', head)
    head = re.sub(r'<link rel="alternate" hreflang[^>]*>\s*', "", head)
    alts = "".join(f'<link rel="alternate" hreflang="{l}" href="{url(l, topic[l]["slug"])}">' for l in ("en", "es", "pt"))
    alts += f'<link rel="alternate" hreflang="x-default" href="{url("en", topic["en"]["slug"])}">'
    head = head.replace("</head>", alts + "</head>", 1) if "</head>" in head else head + alts
    ld = {"@context": "https://schema.org", "@type": "LearningResource", "name": d["h1"], "description": d["desc"],
          "inLanguage": lang, "educationalLevel": "Preschool", "typicalAgeRange": "2-6", "isAccessibleForFree": True,
          "url": me, "provider": {"@type": "Organization", "name": "Learn with Ian", "url": SITE + "/"}}
    head = re.sub(r'<script type="application/ld\+json">.*?</script>', "", head, flags=re.S)
    head += f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>\n'
    if "<head>" not in head:
        pass
    # language bar -> the three versions of this page
    bar = '<!--X:LANG--><div class="langbar noprint"><span aria-hidden="true">🌎</span> ' + " · ".join(
        f"<b>{LABEL[l]}</b>" if l == lang else f'<a href="/{PREFIX[l]}play/{topic[l]["slug"]}.html" hreflang="{l}" lang="{l}">{LABEL[l]}</a>'
        for l in ("en", "es", "pt")) + "</div><!--/X:LANG-->"
    after = re.sub(r"<!--X:LANG-->.*?<!--/X:LANG-->", "", after, flags=re.S)
    head = re.sub(r"<!--X:LANG-->.*?<!--/X:LANG-->", bar, head, flags=re.S)
    # games block of this episode (English file), translated for es/pt
    en_ep = rd(f"ep/{ep}.html")
    acts_m = re.search(r"<!--X:ACTS-->.*?<!--/X:ACTS-->", en_ep, re.S)
    acts = acts_m.group(0) if acts_m else ""
    if acts:
        acts = re.sub(r"<h2>.*?</h2>", "<h2>" + t["acts_h"].format(g=topic["game_title"][lang]) + "</h2>", acts, count=1)
        acts = re.sub(r"(<h2>.*?</h2>)<p>.*?</p>", lambda m: m.group(1) + "<p>" + t["acts_p"] + "</p>", acts, count=1)
        for a, b in GAME.get(lang, []):
            acts = acts.replace(a, b)
        if "<!--X:ACTCSS-->" not in head:
            css = re.search(r"<!--X:ACTCSS-->.*?<!--/X:ACTCSS-->", en_ep, re.S)
            if css:
                head = head.replace("</head>", css.group(0) + "</head>", 1) if "</head>" in head else head + css.group(0)
    signup_src = rd("topic/colors.html") if lang == "en" else base
    sm = re.search(r'<section class="signup noprint">.*?</section>', signup_src, re.S)
    signup = sm.group(0) if sm else ""
    li = lambda xs: "<ul>" + "".join(f"<li>{x}</li>" for x in xs) + "</ul>"
    ol = lambda xs: "<ol>" + "".join(f"<li>{x}</li>" for x in xs) + "</ol>"
    home = f"/{PREFIX[lang]}"
    main = f'''<main class="wrap xpage">
  <p class="crumbs"><a href="{home}">{t["home"]}</a> › {html.escape(d["topic"])}</p>
  <span class="badge-free">{t["free"]}</span>
  <h1>{html.escape(d["h1"])}</h1>
  <p class="lead"><b>{t["learns"]}</b> {d["learns"]}</p>
  <p style="margin-top:10px"><span class="badge-free">{t["age"]}</span> <span class="badge-free" style="background:var(--sun);color:var(--ink)">{t["mins"]}</span></p>
  <section class="sbox"><span class="kicker">{t["kicker"]}</span><h2>{t["words"]}</h2>{li(d["words"])}</section>
  <section class="sbox"><h2>{t["need"]}</h2>{li(d["need"])}</section>
  <section class="sbox"><h2>{t["play"]}</h2>{ol(d["steps"])}</section>
  <section class="sbox"><h2>{t["ease"]}</h2>{li(d["easy"])}</section>
  <section class="sbox"><h2>{t["watch"]}</h2>
    <div class="player"><iframe src="https://www.youtube-nocookie.com/embed/{topic["ytid"]}?rel=0" title="{html.escape(topic["ep_title"])}" loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>
    <p style="margin-top:10px"><a href="https://www.youtube.com/watch?v={topic["ytid"]}">{t["watchlink"]}</a></p></section>
  {acts}
  {signup}
</main>'''
    return head + main + after


def main():
    preview = "--all" in sys.argv
    data = ROOT / "data" / "pages.json"
    if not data.exists():
        print("pages: no data/pages.json, nothing to do")
        return
    try:
        topics = json.loads(data.read_text(encoding="utf-8"))
    except Exception as e:
        print("pages: cannot read data/pages.json:", e)
        return
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import pages_check
    except Exception:
        pages_check = None
    now, built, urls = today(), 0, []
    for tp in topics:
        if not preview and tp.get("live_from", "9999") > now:
            continue
        if pages_check:
            problems = pages_check.check_topic(tp, topics)
            if problems:
                print("pages: SKIPPED", tp.get("id"), "->", "; ".join(problems))
                continue
        try:
            outs = {l: build_page(tp, l) for l in ("en", "es", "pt")}
        except Exception as e:
            print("pages: SKIPPED", tp.get("id"), "->", repr(e))
            continue
        for l, page in outs.items():
            out = ROOT / PREFIX[l] / "play" / (tp[l]["slug"] + ".html")
            out.parent.mkdir(parents=True, exist_ok=True)
            if not out.exists() or out.read_text(encoding="utf-8") != page:
                out.write_text(page, encoding="utf-8")
            urls.append(url(l, tp[l]["slug"]))
            built += 1
    sm = ROOT / "sitemap.xml"
    if sm.exists() and urls:
        text = sm.read_text()
        add = "".join(f"  <url><loc>{u}</loc><priority>0.7</priority></url>\n" for u in urls if f"<loc>{u}</loc>" not in text)
        if add:
            sm.write_text(text.replace("</urlset>", add + "</urlset>"))
    print("pages: built", built, "pages from", len(topics), "topics")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never stop the site update
        print("pages: failed, site untouched:", repr(e))
