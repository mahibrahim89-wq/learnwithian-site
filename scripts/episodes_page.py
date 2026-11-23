"""Episode cards for learnwithian.com.

The homepage shows only the 4 newest episodes (between the AUTO:EPS markers)
and episodes.html shows every episode, newest first. 1-hour compilations are
left out here: they live in their own YouTube playlist.
"""
import html
import re

COMPILATION = re.compile(r"\b1\s*hour\b|\bcompilation\b", re.I)
HOME_COUNT = 4


def esc(s):
    return html.escape(str(s), quote=True)


def is_compilation(title):
    return bool(COMPILATION.search(title or ""))


def card(e):
    vid = esc(e["id"])
    learn = f'\n            <p class="learn">{esc(e["learn"])}</p>' if e.get("learn") else ""
    return f'''        <article class="ep">
          <div class="pic"><img src="https://i.ytimg.com/vi/{vid}/maxresdefault.jpg" onerror="this.onerror=null;this.src='https://i.ytimg.com/vi/{vid}/mqdefault.jpg'" alt="" loading="lazy" width="1280" height="720"><span class="tag">Episode {e["num"]}</span><span class="play" aria-hidden="true"><svg viewBox="0 0 24 24"><path fill="#fff" d="M7 4l14 8-14 8z"/></svg></span></div>
          <div class="txt">
            <h3>{esc(e["title"])}</h3>{learn}
            <a class="cover" href="https://www.youtube.com/watch?v={vid}"><span>Watch {esc(e["title"])}</span></a>
            <p class="shop"><a href="shop.html#{esc(e["slug"])}">Shop this episode</a></p>
          </div>
        </article>
'''


def newest_first(eps):
    return sorted(eps, key=lambda e: e["num"], reverse=True)


def home_block(eps):
    return "".join(card(e) for e in newest_first(eps)[:HOME_COUNT])


def render_page(eps, style):
    cards = "".join(card(e) for e in newest_first(eps))
    css = """
.lwrap { padding: 24px 0 48px; }
.lhead { margin-bottom: 24px; }
.lhead h1 { font-size: clamp(34px, 6vw, 56px); font-weight: 800; }
.lhead p { margin-top: 8px; color: var(--ink-soft); font-size: 19px; }
.nav a[aria-current] { color: var(--berry); }
.lwrap .eps { grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
"""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>All Learn with Ian episodes</title>
<meta name="description" content="Every Learn with Ian episode for toddlers and preschoolers, newest first: animals, plants, shapes, numbers, colors and more.">
<meta property="og:title" content="All Learn with Ian episodes">
<meta property="og:url" content="https://learnwithian.com/episodes.html">
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
      <a href="episodes.html" aria-current="page">Episodes</a>
      <a href="lessons.html">Lesson plans</a>
      <a href="shop.html">Shop</a>
      <a href="./#contact">Contact</a>
    </nav>
    <a class="subnow" href="https://www.youtube.com/@LearnWithIanKids?sub_confirmation=1">Subscribe</a>
  </div>
</header>
<main class="wrap lwrap">
  <div class="lhead">
    <span class="kicker">All episodes</span>
    <h1>Every Learn with Ian episode</h1>
    <p>Newest first. Each adventure teaches one thing a preschooler can name, count or point to by the end.</p>
  </div>
  <div class="eps">
{cards}  </div>
  <div class="all"><a class="btn btn-white" href="https://www.youtube.com/@LearnWithIanKids/videos">Watch all episodes and shorts on YouTube</a></div>
</main>
<footer>
  <div class="wrap">
    <span>&copy; 2026 Learn with Ian &middot; <a href="https://www.youtube.com/@LearnWithIanKids">YouTube</a></span>
    <span>hello@learnwithian.com</span>
  </div>
</footer>
<script>
document.querySelectorAll('a[href^="http"]').forEach((a) => {{ if (a.host !== location.host) {{ a.target = '_blank'; a.rel = 'noopener'; }} }});
</script>
</body>
</html>
'''
