"""Free printables, topic pages, teachers page, Spanish and Portuguese pages.

Runs after seo_pages.py (same workflow). Reads the lesson plans and the
"Lesson extras" Google Sheet (tips, free PDF, translations) that Claude fills
for every episode, and builds or updates:
  free.html, teachers.html, topic/<topic>.html, es/ and pt/ episode pages,
  a green FREE band and sign-up box on the homepage, a free download box,
  parent tips and sign-up box on every episode page, the "Free printables"
  link in the menu, and the new pages in sitemap.xml. Safe to run many times.
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
import lessons  # noqa: E402
import update  # noqa: E402

SITE = "https://learnwithian.com"
CHANNEL = "https://www.youtube.com/@LearnWithIanKids"
EXTRAS_ID = "1oxDQWj9UmokHvhHp05L9GPgZxyOlyMZ3ctli8nORgsc"
EXTRAS_CSV = f"https://docs.google.com/spreadsheets/d/{EXTRAS_ID}/export?format=csv"
CACHE = ROOT / "data" / "extras.csv"
FORM = "https://script.google.com/macros/s/AKfycbwjGNFh65Ps70_1M2Zb3xj_B87JFUUIV2fqu1QFeRZDQcku1mBjtV3TP4QFbYIVLMg/exec"
PACK_ID = "1v_QMRmjt9kUwq4TWjq3l_vBXLdii6hn5"
TOPIC_WORDS = {
    "Animals": ("Animals for Toddlers", "Learn animal names with cartoons, sounds and printable pages."),
    "Plants": ("How Plants Grow for Kids", "Seed, soil, water and sun: watch a seed grow, then plant your own."),
    "Shapes": ("Shapes for Toddlers", "Circles, squares and triangles: find them, trace them and color them."),
    "Numbers": ("Counting for Toddlers", "Count from 1 to 10 with cartoons, counting walks and number tracing."),
    "Colors": ("Colors for Toddlers", "Red, blue, yellow and more: name colors, sort them and color them in."),
    "Weather": ("Weather for Toddlers", "Snow, rain and sun: what we wear and what we do in every weather."),
    "Holidays": ("Holidays for Toddlers", "Christmas and other holidays: words, counting and calm activities."),
}
L10N = {
    "es": {"lang": "es", "watch": "Ver gratis en YouTube", "learns": "Tu hijo aprende:", "plan": "Plan de clase gratis",
           "before": "Antes de ver", "pause": "Pausa y pregunta", "after": "Después del episodio", "activity": "Actividad",
           "tips": "Juegos para casa", "free": "Hoja gratis para imprimir", "dl": "Descargar PDF gratis",
           "all": "Todos los episodios", "home": "Inicio", "english": "English", "page": "Episodios de Learn with Ian en español",
           "intro": "Dibujos animados cortos y tranquilos para niños de 2 a 6 años, con planes de clase y hojas gratis.",
           "note": "El video está en inglés. YouTube puede mostrarlo con audio o subtítulos en español."},
    "pt": {"lang": "pt", "watch": "Assistir grátis no YouTube", "learns": "Seu filho aprende:", "plan": "Plano de aula grátis",
           "before": "Antes de assistir", "pause": "Pause e pergunte", "after": "Depois do episódio", "activity": "Atividade",
           "tips": "Brincadeiras para casa", "free": "Folha grátis para imprimir", "dl": "Baixar PDF grátis",
           "all": "Todos os episódios", "home": "Início", "english": "English", "page": "Episódios do Learn with Ian em português",
           "intro": "Desenhos curtos e calmos para crianças de 2 a 6 anos, com planos de aula e folhas grátis.",
           "note": "O vídeo é em inglês. O YouTube pode mostrar com áudio ou legendas em português."},
}
CSS = """
.badge-free { display: inline-block; background: var(--leaf); color: #fff; font-family: var(--display); font-weight: 800; font-size: 14px; letter-spacing: .04em; padding: 2px 10px; border-radius: 999px; border: 2px solid var(--ink); vertical-align: middle; }
.nav a.navfree { color: var(--leaf); }
.nav a.navfree::before { content: "FREE"; background: var(--leaf); color: #fff; font-size: 11px; font-weight: 800; padding: 1px 6px; border-radius: 999px; margin-right: 6px; vertical-align: 2px; }
.btn-green { background: var(--leaf); color: #fff; }
.freeband { background: #e6f6e9; border-block: 3px solid var(--ink); padding: 40px 0; }
.freeband h2, .xpage h1 { font-size: clamp(30px, 5vw, 46px); font-weight: 800; line-height: 1.1; margin: 6px 0 8px; }
.freegrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 18px; margin-top: 20px; }
.freecard { background: #fff; border: 3px solid var(--ink); border-radius: 20px; padding: 18px; display: flex; flex-direction: column; gap: 10px; box-shadow: 0 5px 0 var(--ink); }
.freecard h3 { margin: 0; font-size: 22px; }
.freecard p { margin: 0; color: var(--ink-soft); }
.freecard .btn { margin-top: auto; align-self: flex-start; }
.freecard img { border-radius: 12px; border: 2px solid var(--line); background: #fff; aspect-ratio: 794/1123; object-fit: contain; width: 100%; }
.freecard .badge-free, .signup .badge-free { align-self: flex-start; }
.freebox { background: #e6f6e9; border: 3px solid var(--leaf); border-radius: 20px; padding: 18px 20px; margin-top: 18px; display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }
.freebox img { width: 120px; border-radius: 10px; border: 2px solid var(--line); background: #fff; }
.freebox h2 { margin: 4px 0; font-size: 26px; font-weight: 800; }
.freebox div { flex: 1 1 240px; }
.signup { background: #fff; border: 3px solid var(--ink); border-radius: 20px; padding: 20px 22px; margin-top: 22px; }
.signup h2 { margin: 4px 0 6px; font-size: 26px; font-weight: 800; }
.signup form { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
.signup input[type=email] { flex: 1 1 220px; font: inherit; padding: 12px 16px; border: 3px solid var(--ink); border-radius: 999px; min-width: 0; }
.signup button { font: inherit; font-weight: 700; cursor: pointer; }
.signup .small { font-size: 14px; color: var(--ink-soft); margin-top: 8px; }
.signup .hp { position: absolute; left: -9999px; }
.xpage { padding: 24px 0 48px; }
.xpage .lead { font-size: 20px; margin: 8px 0 0; max-width: 760px; }
.xlist { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; margin-top: 18px; }
.xlist a.card { display: block; background: #fff; border: 3px solid var(--ink); border-radius: 18px; overflow: hidden; color: var(--ink); text-decoration: none; }
.xlist a.card img { width: 100%; aspect-ratio: 16/9; object-fit: cover; }
.xlist a.card span { display: block; padding: 12px 14px; font-weight: 700; }
.steps { counter-reset: s; padding-left: 0; list-style: none; }
.steps li { counter-increment: s; margin: 10px 0; padding-left: 44px; position: relative; }
.steps li::before { content: counter(s); position: absolute; left: 0; top: -2px; width: 32px; height: 32px; border-radius: 50%; background: var(--sun); border: 2px solid var(--ink); display: grid; place-items: center; font-weight: 800; }
.langs { font-size: 15px; margin-top: 8px; }
.xpage .sbox { background: #fff; border: 3px solid var(--line); border-radius: 20px; padding: 20px 22px; margin-top: 22px; }
.xpage .sbox h2 { font-size: clamp(22px, 4vw, 30px); font-weight: 800; margin: 4px 0 10px; }
.xpage .sbox h3 { font-size: 19px; margin: 14px 0 4px; }
.xpage .sbox a, .freebox a:not(.btn), .langs a, .signup a { color: var(--sky); font-weight: 700; }
.xpage .crumbs, .xpage .small { font-size: 15px; color: var(--ink-soft); }
.xpage .player { margin: 12px 0 6px; }
@media print { .noprint, header, footer, .signup { display: none !important; } }
"""
SIGNUP_JS = """<script>
document.querySelectorAll('form.signupform').forEach((f) => f.addEventListener('submit', (ev) => {
  ev.preventDefault();
  const box = f.closest('.signup'); const btn = f.querySelector('button'); btn.disabled = true;
  fetch(f.action, { method: 'POST', mode: 'no-cors', body: new URLSearchParams(new FormData(f)) })
    .finally(() => { box.querySelector('.ok').hidden = false; f.hidden = true; });
}));
</script>"""


def esc(s):
    return html.escape(str(s), quote=True)


def items(s):
    return "".join(f"<li>{esc(x.strip())}</li>" for x in (s or "").split("|") if x.strip())


def drive_id(url):
    m = re.search(r"/d/([A-Za-z0-9_-]{20,})", url or "")
    return m.group(1) if m else ""


def thumb(fid, w=600):
    return f"https://drive.google.com/thumbnail?id={fid}&sz=w{w}"


def load_extras():
    try:
        req = urllib.request.Request(EXTRAS_CSV, headers={"User-Agent": "learnwithian-site-updater"})
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
        if rows and "youtube_id" in rows[0]:
            CACHE.write_text(text)
    except Exception as e:  # sheet not reachable: use the saved copy
        print("extras sheet not used:", e)
        text = CACHE.read_text() if CACHE.exists() else ""
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        r = {k: (v or "").strip() for k, v in r.items() if k}
        if r.get("youtube_id"):
            for lang in ("es", "pt"):
                try:
                    r[lang] = json.loads(r.get(lang) or "{}")
                except ValueError:
                    r[lang] = {}
            out[r["youtube_id"]] = r
    return out


def signup(lang="en"):
    t = {"en": ("Get a free printable page every week", "Your email", "Send me free pages",
                "Free. One short email a week with a new episode and a printable page. Unsubscribe anytime.",
                "Thank you! You are on the list. Here is the free teacher pack to start:"),
         "es": ("Recibe una hoja gratis cada semana", "Tu email", "Quiero hojas gratis",
                "Gratis. Un email corto por semana. Puedes darte de baja cuando quieras.",
                "¡Gracias! Ya estás en la lista. Aquí tienes el pack gratis para empezar:"),
         "pt": ("Receba uma folha grátis toda semana", "Seu email", "Quero folhas grátis",
                "Grátis. Um email curto por semana. Cancele quando quiser.",
                "Obrigado! Você está na lista. Aqui está o pacote grátis para começar:")}[lang]
    return f'''<section class="signup noprint"><span class="badge-free">FREE</span>
    <h2>{t[0]}</h2>
    <form class="signupform" action="{FORM}" method="post">
      <input type="email" name="email" required placeholder="{t[1]}" aria-label="{t[1]}">
      <input type="hidden" name="lang" value="{lang}"><input class="hp" type="text" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">
      <input type="hidden" name="page" value="">
      <button class="btn btn-green" type="submit">{t[2]}</button>
    </form>
    <p class="ok" hidden>{t[4]} <a href="https://drive.google.com/file/d/{PACK_ID}/view">Teacher Pack (PDF)</a></p>
    <p class="small">{t[3]}</p>
  </section>'''


def shell(title, desc, canonical, body, style, lang="en", alternates=""):
    head_nav = {"en": ("Episodes", "Lesson plans", "Shop", "Free printables"),
                "es": ("Episodios", "Planes de clase", "Tienda", "Hojas gratis"),
                "pt": ("Episódios", "Planos de aula", "Loja", "Folhas grátis")}[lang]
    return f'''<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}">{alternates}
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%23ffb321'/%3E%3Cpath d='M26 46V18M20 18h12M20 46h12' stroke='%231d2b45' stroke-width='6' stroke-linecap='round'/%3E%3Ccircle cx='44' cy='22' r='5' fill='%23ec4f7b'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@700;800&family=Atkinson+Hyperlegible:wght@400;700&display=swap" rel="stylesheet">
<style>
{style}
.nav a[aria-current] {{ color: var(--berry); }}
</style>
</head>
<body>
<header class="topbar scrolled" id="topbar">
  <div class="wrap bar">
    <a class="logo rainbow" translate="no" href="/" aria-label="Learn with Ian, home"><span class="w"><span>L</span><span>E</span><span>A</span><span>R</span><span>N</span></span> <span class="w"><span>W</span><span>I</span><span>T</span><span>H</span></span> <span class="w"><span>I</span><span>A</span><span>N</span></span></a>
    <nav class="nav" aria-label="Main">
      <a href="/episodes.html">{head_nav[0]}</a>
      <a href="/lessons.html">{head_nav[1]}</a>
      <a href="/shop.html">{head_nav[2]}</a>
      <a href="/#contact">Contact</a>
    </nav>
    <a class="subnow" href="{CHANNEL}?sub_confirmation=1">Subscribe</a>
  </div>
</header>
<main class="wrap xpage">
{body}
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


def free_card(title, about, fid, extra=""):
    return (f'<article class="freecard"><span class="badge-free">FREE</span>'
            f'<a href="https://drive.google.com/file/d/{fid}/view" tabindex="-1" aria-hidden="true"><img src="{thumb(fid)}" alt="" loading="lazy" width="300" height="400"></a>'
            f'<h3>{esc(title)}</h3><p>{esc(about)}</p>{extra}'
            f'<a class="btn btn-green" href="https://drive.google.com/file/d/{fid}/view">Download free PDF</a></article>')


def ep_title(e):
    t = e["title"]
    return t.split(": ")[-1] if "Ian" in t.split(": ")[-1] else t


def build_pages(eps, plans, xt, style):
    pages = []  # (url, path) for the sitemap
    by_num = {int(p["episode"]): p for p in plans}
    plan = lambda e: next((p for p in plans if p["youtube_id"] == e["id"]), None) or by_num.get(e["num"])
    xtra = lambda e: xt.get(e["id"]) or next((x for x in xt.values() if x.get("episode") == str(e["num"])), {})
    ordered = sorted(eps, key=lambda e: e["num"], reverse=True)

    # Free printables page
    cards = [free_card("Free Teacher Pack (6 pages)", "Counting 1 to 10, number tracing, shapes and a Great job! certificate.", PACK_ID)]
    for e in ordered:
        fid = drive_id(xtra(e).get("free_pdf"))
        if fid:
            cards.append(free_card(f"{ep_title(e)}: free page", (plan(e) or {}).get("goal", ""), fid,
                                   f'<p><a href="/ep/{esc(e["slug"])}.html">Watch the episode and get the lesson plan</a></p>'))
    body = f'''<span class="badge-free">FREE</span>
  <h1>Free printables for toddlers and preschool</h1>
  <p class="lead">Free worksheets from every Learn with Ian episode: counting, tracing, shapes and colors. Print at home or for your whole class. No sign-up needed.</p>
  <div class="freegrid">{"".join(cards)}</div>
  {signup()}
  {SIGNUP_JS}'''
    (ROOT / "free.html").write_text(shell("Free Printables for Toddlers & Preschool – Learn with Ian",
                                          "Free printable worksheets for ages 2 to 6: counting, number tracing, shapes and colors, each with a free cartoon episode and lesson plan.",
                                          SITE + "/free.html", body, style))
    pages.append(SITE + "/free.html")

    # Teachers page
    plan_html = ""
    for e in sorted(eps, key=lambda e: e["num"]):
        p = plan(e)
        if not p:
            continue
        plan_html += (f'<section class="sbox"><span class="badge-free">FREE</span> <b>Episode {e["num"]}</b>'
                      f'<h2><a href="/ep/{esc(e["slug"])}.html">{esc(ep_title(e))}</a></h2><p><b>Goal:</b> {esc(p["goal"])}</p>'
                      f'<h3>Before you press play</h3><ul>{items(p["before"])}</ul><h3>Pause and ask</h3><ul>{items(p["pause"])}</ul>'
                      f'<h3>After the episode</h3><ul>{items(p["after"])}</ul><h3>Activity</h3><p>{esc(p["activity"])}</p></section>')
    body = f'''<span class="badge-free">FREE</span>
  <h1>Circle Time with Ian: free resources for teachers</h1>
  <p class="lead">Short, calm cartoon lessons for nurseries, preschools, church schools and children's homes. Every episode comes with a free lesson plan and a free printable page.</p>
  <section class="sbox noprint"><h2>How to use Ian in class</h2><ol class="steps">
    <li>Ask the "before you press play" question to wake up curiosity.</li>
    <li>Play the episode on a classroom screen (5 to 15 minutes). Pause at the questions.</li>
    <li>Do the hands-on activity, then hand out the free printable page.</li></ol>
    <p><a class="btn btn-green" href="https://drive.google.com/file/d/{PACK_ID}/view">Download the free Teacher Pack</a>
    <a class="btn btn-white" href="/free.html">All free printables</a>
    <button class="btn btn-white" type="button" onclick="window.print()">Print all lesson plans</button></p></section>
  {plan_html}
  {signup()}
  {SIGNUP_JS}'''
    (ROOT / "teachers.html").write_text(shell("Circle Time with Ian – Free Preschool Lesson Plans & Printables for Teachers",
                                              "Free preschool lesson plans, printable worksheets and calm cartoon episodes for circle time in nurseries and preschools.",
                                              SITE + "/teachers.html", body, style))
    pages.append(SITE + "/teachers.html")

    # Topic pages
    topics = {}
    for e in eps:
        p = plan(e)
        if p and p.get("topic"):
            topics.setdefault(p["topic"], []).append(e)
    (ROOT / "topic").mkdir(exist_ok=True)
    for topic, tes in topics.items():
        name, lead = TOPIC_WORDS.get(topic, (f"{topic} for Toddlers", f"Free cartoons, printables and lesson plans about {topic.lower()}."))
        slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
        blocks = ""
        for e in sorted(tes, key=lambda e: e["num"]):
            p, x = plan(e), xtra(e)
            fid = drive_id(x.get("free_pdf"))
            free = (f'<p><span class="badge-free">FREE</span> <a href="https://drive.google.com/file/d/{fid}/view">Download the free printable page</a></p>' if fid else "")
            tips = f'<h3>Play at home</h3><ul>{items(x.get("tips"))}</ul>' if x.get("tips") else ""
            blocks += (f'<section class="sbox"><h2><a href="/ep/{esc(e["slug"])}.html">{esc(ep_title(e))}</a></h2>'
                       f'<div class="player"><iframe src="https://www.youtube-nocookie.com/embed/{esc(e["id"])}?rel=0" title="{esc(ep_title(e))}" loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>'
                       f'<p><b>Your child learns:</b> {esc((p or {}).get("goal", ""))}</p>{free}{tips}'
                       f'<p><a href="/ep/{esc(e["slug"])}.html">Free lesson plan for this episode</a></p></section>')
        body = f'''<span class="badge-free">FREE</span>
  <h1>{esc(name)}</h1>
  <p class="lead">{esc(lead)} Free cartoon episodes, free printable pages and play ideas for ages 2 to 6.</p>
  {blocks}
  {signup()}
  {SIGNUP_JS}'''
        (ROOT / "topic" / f"{slug}.html").write_text(shell(f"{name} – Free Cartoons, Worksheets & Activities | Learn with Ian",
                                                           f"{lead} Free videos, printable worksheets and lesson plans for toddlers and preschool.",
                                                           f"{SITE}/topic/{slug}.html", body, style))
        pages.append(f"{SITE}/topic/{slug}.html")

    # Spanish and Portuguese pages
    for lang, t in L10N.items():
        (ROOT / lang / "ep").mkdir(parents=True, exist_ok=True)
        listing = ""
        for e in ordered:
            x = xtra(e).get(lang) or {}
            if not x.get("title"):
                continue
            fid = drive_id(xtra(e).get("free_pdf"))
            alt = (f'\n<link rel="alternate" hreflang="en" href="{SITE}/ep/{e["slug"]}.html">'
                   + "".join(f'\n<link rel="alternate" hreflang="{l}" href="{SITE}/{l}/ep/{e["slug"]}.html">' for l in L10N))
            free = (f'<section class="freebox"><img src="{thumb(fid, 300)}" alt="" loading="lazy" width="120" height="160"><div><span class="badge-free">FREE</span>'
                    f'<h2>{t["free"]}</h2><a class="btn btn-green" href="https://drive.google.com/file/d/{fid}/view">{t["dl"]}</a></div></section>' if fid else "")
            body = f'''<p class="crumbs"><a href="/{lang}/">{t["all"]}</a> · <a href="/ep/{esc(e["slug"])}.html">{t["english"]}</a></p>
  <h1>{esc(x["title"])}</h1>
  <p class="lead"><b>{t["learns"]}</b> {esc(x.get("goal", ""))}</p>
  <div class="player"><iframe src="https://www.youtube-nocookie.com/embed/{esc(e["id"])}?rel=0&hl={lang}&cc_lang_pref={lang}" title="{esc(x["title"])}" loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>
  <p class="small">{t["note"]} <a href="https://www.youtube.com/watch?v={esc(e["id"])}">{t["watch"]}</a></p>
  {free}
  <section class="sbox"><span class="badge-free">FREE</span><h2>{t["plan"]}</h2>
    <h3>{t["before"]}</h3><ul>{items(x.get("before"))}</ul><h3>{t["pause"]}</h3><ul>{items(x.get("pause"))}</ul>
    <h3>{t["after"]}</h3><ul>{items(x.get("after"))}</ul><h3>{t["activity"]}</h3><p>{esc(x.get("activity", ""))}</p></section>
  <section class="sbox"><h2>{t["tips"]}</h2><ul>{items(x.get("tips"))}</ul></section>
  {signup(lang)}
  {SIGNUP_JS}'''
            desc = f'{x["title"]}: {x.get("goal", "")} {t["intro"]}'[:158]
            (ROOT / lang / "ep" / f'{e["slug"]}.html').write_text(
                shell(f'{x["title"]} – Learn with Ian', desc, f'{SITE}/{lang}/ep/{e["slug"]}.html', body, style, lang, alt))
            pages.append(f'{SITE}/{lang}/ep/{e["slug"]}.html')
            listing += (f'<a class="card" href="/{lang}/ep/{esc(e["slug"])}.html"><img src="https://i.ytimg.com/vi/{esc(e["id"])}/mqdefault.jpg" alt="" loading="lazy" width="320" height="180">'
                        f'<span>{esc(x["title"])}</span></a>')
        body = f'''<h1>{t["page"]}</h1><p class="lead">{t["intro"]}</p><div class="xlist">{listing}</div>{signup(lang)}{SIGNUP_JS}'''
        (ROOT / lang / "index.html").write_text(shell(t["page"], t["intro"], f"{SITE}/{lang}/", body, style, lang))
        pages.append(f"{SITE}/{lang}/")
    return pages, plan, xtra, topics


def between(text, name, content, anchor_after=None, anchor_before=None):
    """Replace <!--X:name-->...<!--/X:name--> or insert it next to an anchor."""
    block = f"<!--X:{name}-->{content}<!--/X:{name}-->"
    pat = re.compile(r"<!--X:%s-->.*?<!--/X:%s-->" % (name, name), re.S)
    if pat.search(text):
        return pat.sub(lambda m: block, text)
    if anchor_after and anchor_after in text:
        i = text.index(anchor_after) + len(anchor_after)
        return text[:i] + block + text[i:]
    if anchor_before and anchor_before in text:
        i = text.index(anchor_before)
        return text[:i] + block + text[i:]
    return text


def decorate(path, extra_css=True):
    """Menu link, FREE styles. Works on any page that has the site header."""
    s = path.read_text()
    if extra_css:
        s = between(s, "CSS", f"<style>{CSS}</style>", anchor_before="</head>")
    if 'class="navfree"' not in s:
        s = re.sub(r'(<nav class="nav" aria-label="Main">)', r'\1\n      <a class="navfree" href="/free.html">Free printables</a>', s, count=1)
    path.write_text(s)
    return s


def main():
    allv = json.loads((ROOT / "data" / "episodes.json").read_text())
    eps = update.episode_entries(allv)
    style = re.search(r"<style>(.*?)</style>", (ROOT / "index.html").read_text(), re.S).group(1)
    plans = lessons.parse((ROOT / "data" / "lessons.csv").read_text()) if (ROOT / "data" / "lessons.csv").exists() else []
    xt = load_extras()
    pages, plan, xtra, topics = build_pages(eps, plans, xt, style)

    # Homepage: green FREE band right under the first screen
    idx = ROOT / "index.html"
    s = idx.read_text()
    topic_links = " ".join(f'<a href="/topic/{re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")}.html">{esc(TOPIC_WORDS.get(t, (t,))[0])}</a> ·'
                           for t in topics).rstrip(" ·")
    band = f'''
  <section class="freeband" id="free"><div class="wrap">
    <span class="badge-free">FREE</span>
    <h2>Everything here is free</h2>
    <p class="lead">Watch, print and play. No sign-up, no ads on this site.</p>
    <div class="freegrid">
      <div class="freecard"><span class="badge-free">FREE</span><h3>Cartoon episodes</h3><p>Short, calm lessons for ages 2 to 6. Watch at home or in class.</p><a class="btn btn-green" href="/episodes.html">Watch free</a></div>
      <div class="freecard"><span class="badge-free">FREE</span><h3>Printable pages</h3><p>A free worksheet for every episode, plus a 6-page Teacher Pack.</p><a class="btn btn-green" href="/free.html">Get free printables</a></div>
      <div class="freecard"><span class="badge-free">FREE</span><h3>Lesson plans</h3><p>Questions to ask and a hands-on activity for every episode.</p><a class="btn btn-green" href="/teachers.html">For teachers</a></div>
    </div>
    <p class="langs">Learn by topic: {topic_links}</p>
    <p class="langs">En español: <a href="/es/">episodios y hojas gratis</a> · Em português: <a href="/pt/">episódios e folhas grátis</a></p>
    {signup()}
  </div></section>
'''
    s = between(s, "FREE", band, anchor_before='<section class="section" id="episodes">')
    s = between(s, "JS", SIGNUP_JS, anchor_before="</body>")
    idx.write_text(s)

    # Episode pages: free download box, play-at-home tips, sign-up box, language links
    for e in eps:
        p = ROOT / "ep" / f'{e["slug"]}.html'
        if not p.exists():
            continue
        s = p.read_text()
        x = xtra(e)
        fid = drive_id(x.get("free_pdf"))
        box = (f'<section class="freebox"><img src="{thumb(fid, 300)}" alt="Free printable page preview" loading="lazy" width="120" height="160">'
               f'<div><span class="badge-free">FREE</span><h2>Free printable page</h2><p>Print it after the episode. Free for home and class.</p>'
               f'<a class="btn btn-green" href="https://drive.google.com/file/d/{fid}/view">Download free PDF</a></div></section>' if fid else "")
        langs = "".join(f' · <a href="/{l}/ep/{esc(e["slug"])}.html" hreflang="{l}">{n}</a>' for l, n in (("es", "Español"), ("pt", "Português")) if (x.get(l) or {}).get("title"))
        if langs:
            box += f'<p class="langs">Also in{langs}</p>'
        s = between(s, "FREEBOX", box, anchor_before='\n  <section class="sbox" id="lesson-plan">')
        tips = (f'<section class="sbox" id="play-at-home"><span class="kicker">For parents</span><h2>Play at home</h2><ul>{items(x.get("tips"))}</ul></section>'
                if x.get("tips") else "")
        s = between(s, "TIPS", tips + signup(), anchor_before='\n  <section class="sbox" id="more">')
        s = between(s, "JS", SIGNUP_JS, anchor_before="</body>")
        if langs:
            alt = (f'<link rel="alternate" hreflang="en" href="{SITE}/ep/{e["slug"]}.html">'
                   + "".join(f'<link rel="alternate" hreflang="{l}" href="{SITE}/{l}/ep/{e["slug"]}.html">' for l in L10N))
            s = between(s, "ALT", alt, anchor_before="</head>")
        p.write_text(s)

    # Menu link and styles everywhere
    for f in ["index.html", "episodes.html", "lessons.html", "shop.html", "free.html", "teachers.html"]:
        if (ROOT / f).exists():
            decorate(ROOT / f)
    for f in list((ROOT / "ep").glob("*.html")) + list((ROOT / "topic").glob("*.html")) + list((ROOT / "es").rglob("*.html")) + list((ROOT / "pt").rglob("*.html")):
        decorate(f)

    # Sitemap: add the new pages
    sm = ROOT / "sitemap.xml"
    text = sm.read_text() if sm.exists() else '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n</urlset>\n'
    add = "".join(f"  <url><loc>{u}</loc><priority>0.7</priority></url>\n" for u in pages if f"<loc>{u}</loc>" not in text)
    sm.write_text(text.replace("</urlset>", add + "</urlset>"))
    print("extra pages:", len(pages))


if __name__ == "__main__":
    main()
