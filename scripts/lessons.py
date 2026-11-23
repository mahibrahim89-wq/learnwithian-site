"""Lesson plans for learnwithian.com.

Claude writes one row per episode in a Google Sheet (shared as view-only).
This file reads that sheet, keeps a copy in data/lessons.csv (used if the
sheet can't be reached), and builds:
  * the 3 newest plans on the homepage (between the AUTO:LESSONS markers),
  * lessons.html with every plan, filters by topic, and closed cards.
"""
import csv
import html
import io
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEET_ID = "1V-YSnoaUe914XP_q7KkBomrd-eHaqAfbPvl5x3cBeRU"
SHEET_CSV = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
CACHE = ROOT / "data" / "lessons.csv"
NEED = ["episode", "youtube_id", "title", "topic", "goal", "before", "pause", "after", "activity"]
TOPIC_BG = ["#dff3e3", "#e8f6d9", "#e4f1fd", "#fff1d6", "#fde4ec", "#efe6fd"]


def esc(s):
    return html.escape(str(s), quote=True)


def parse(text):
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or any(k not in rows[0] for k in NEED):
        raise ValueError("lesson sheet has the wrong columns")
    out = []
    for r in rows:
        r = {k: (v or "").strip() for k, v in r.items() if k}
        if not (r.get("episode", "").isdigit() and r.get("youtube_id") and r.get("title") and r.get("goal")):
            continue
        out.append(r)
    if not out:
        raise ValueError("lesson sheet is empty")
    return sorted(out, key=lambda r: int(r["episode"]))


def load():
    try:
        req = urllib.request.Request(SHEET_CSV, headers={"User-Agent": "learnwithian-site-updater"})
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8-sig")
        lessons = parse(text)
        CACHE.write_text(text)
        return lessons
    except Exception as e:  # sheet not reachable: use the saved copy
        print("lesson sheet not used:", e)
        return parse(CACHE.read_text()) if CACHE.exists() else []


def items(s):
    return "".join(f"<li>{esc(x.strip())}</li>" for x in s.split("|") if x.strip())


def body(l, pid):
    vid = esc(l["youtube_id"])
    return f'''
          <p><b>Goal:</b> {esc(l["goal"])}</p>
          <h4>Before you press play</h4>
          <ul>{items(l["before"])}</ul>
          <h4>Pause and ask</h4>
          <ul>{items(l["pause"])}</ul>
          <h4>After the episode</h4>
          <ul>{items(l["after"])}</ul>
          <h4>Activity</h4>
          <p>{esc(l["activity"])}</p>
          <p><a href="https://www.youtube.com/watch?v={vid}">Open the episode on YouTube</a></p>
          <button class="printbtn" type="button" data-plan="{pid}">Print this plan</button>'''


def top(l):
    vid = esc(l["youtube_id"])
    mins = f' · {esc(l["minutes"])} min' if l.get("minutes") else ""
    return (f'<div class="plan-top"><img src="https://i.ytimg.com/vi/{vid}/mqdefault.jpg" alt="" loading="lazy" width="320" height="180">'
            f'<div><h3>{esc(l["title"])}</h3><p class="plan-meta">Episode {esc(l["episode"])}{mins} · ages 3 to 6 · {esc(l["topic"])}</p></div></div>')


def card(l):
    return f'''
      <details class="plan lplan" id="plan-{esc(l["episode"])}" data-topic="{esc(l["topic"])}">
        <summary>{top(l)}<span class="open"><span class="o1">Open plan</span><span class="o2">Close plan</span></span></summary>{body(l, "plan-" + esc(l["episode"]))}
      </details>'''


def home_block(lessons):
    """Homepage: the 3 newest plans (closed), then a button to the full list."""
    newest = list(reversed(lessons))[:3]
    cards = "".join(card(l) for l in newest)
    more = (f'      <div class="all"><a class="btn btn-white" href="lessons.html">See all {len(lessons)} lesson plans</a></div>\n'
            if len(lessons) > 3 else "")
    return f'      <div class="llist">{cards}\n      </div>\n{more}'


def render_page(lessons, style):
    topics = []
    for l in lessons:
        if l["topic"] and l["topic"] not in topics:
            topics.append(l["topic"])
    btns = '<button type="button" data-f="all" aria-pressed="true">All</button>' + "".join(
        f'<button type="button" data-f="{esc(t)}" aria-pressed="false">{esc(t)}</button>' for t in topics)
    cards = "".join(card(l) for l in reversed(lessons))
    css = """
.lwrap { padding: 24px 0 48px; }
.lhead h1 { font-size: clamp(34px, 6vw, 56px); font-weight: 800; }
.lhead p { margin-top: 8px; color: var(--ink-soft); font-size: 19px; }
.filters { display: flex; flex-wrap: wrap; gap: 10px; margin: 20px 0 24px; }
.filters button { font: inherit; font-weight: 700; font-size: 17px; padding: 8px 18px; border-radius: 999px; border: 3px solid var(--ink); background: #fff; color: var(--ink); cursor: pointer; }
.filters button[aria-pressed="true"] { background: var(--ink); color: #fff; }
.nav a[aria-current] { color: var(--berry); }
@media print {
  body.print-one > header, body.print-one > footer, body.print-one .lhead, body.print-one .filters, body.print-one .plan:not(.printing), body.print-one .printbtn, body.print-one .open { display: none !important; }
  body.print-one .plan { border: 0; padding: 0; }
}
"""
    script = """
<script>
(() => {
  const btns = document.querySelectorAll('.filters button');
  btns.forEach((b) => b.addEventListener('click', () => {
    btns.forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    document.querySelectorAll('.lplan').forEach((p) => { p.hidden = b.dataset.f !== 'all' && p.dataset.topic !== b.dataset.f; });
  }));
  if (location.hash) { const p = document.querySelector(location.hash); if (p && p.tagName === 'DETAILS') p.open = true; }
  document.querySelectorAll('.printbtn').forEach((b) => b.addEventListener('click', () => {
    const plan = document.getElementById(b.dataset.plan);
    plan.open = true;
    document.body.classList.add('print-one'); plan.classList.add('printing');
    const done = () => { document.body.classList.remove('print-one'); plan.classList.remove('printing'); window.removeEventListener('afterprint', done); };
    window.addEventListener('afterprint', done);
    window.print();
  }));
  document.querySelectorAll('a[href^="http"]').forEach((a) => { if (a.host !== location.host) { a.target = '_blank'; a.rel = 'noopener'; } });
})();
</script>"""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Free lesson plans for every Learn with Ian episode</title>
<meta name="description" content="Free preschool lesson plans for every Learn with Ian episode: a goal, questions to ask, and one hands-on activity. Print the one you need.">
<meta property="og:title" content="Free lesson plans for every Learn with Ian episode">
<meta property="og:url" content="https://learnwithian.com/lessons.html">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%23ffb321'/%3E%3Cpath d='M26 46V18M20 18h12M20 46h12' stroke='%231d2b45' stroke-width='6' stroke-linecap='round'/%3E%3Ccircle cx='44' cy='22' r='5' fill='%23ec4f7b'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@700;800&family=Atkinson+Hyperlegible:wght@400;700&display=swap" rel="stylesheet">
<style>
{style}
{css}
</style>
</head>
<body>
<header class="topbar scrolled" id="topbar">
  <div class="wrap bar">
    <a class="logo rainbow" translate="no" href="./" aria-label="Learn with Ian, home"><span class="w"><span>L</span><span>E</span><span>A</span><span>R</span><span>N</span></span> <span class="w"><span>W</span><span>I</span><span>T</span><span>H</span></span> <span class="w"><span>I</span><span>A</span><span>N</span></span></a>
    <nav class="nav" aria-label="Main">
      <a href="./#episodes">Episodes</a>
      <a href="lessons.html" aria-current="page">Lesson plans</a>
      <a href="shop.html">Shop</a>
      <a href="./#contact">Contact</a>
    </nav>
    <a class="subnow" href="https://www.youtube.com/@LearnWithIanKids?sub_confirmation=1">Subscribe</a>
  </div>
</header>
<main class="wrap lwrap">
  <div class="lhead">
    <span class="kicker">Free lesson plans</span>
    <h1>A lesson plan for every episode</h1>
    <p>Ready for circle time: a goal, questions to ask, and one hands-on activity with things you already have in class. Tap a plan to open it, then print the one you need.</p>
  </div>
  <div class="filters" role="group" aria-label="Show topic">{btns}</div>
  <div class="llist">{cards}
  </div>
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
