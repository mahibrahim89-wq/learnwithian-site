"""Point every episode click on learnwithian.com to the episode's own page.

Runs after update.py and seo_pages.py (same workflow). The episode page plays
the video inside the site (it still counts as a YouTube view) and shows the
lesson plan and printables. Safe to run many times.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import update  # noqa: E402

W = r"https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})"


def main():
    allv = json.loads((ROOT / "data" / "episodes.json").read_text())
    slugs = {e["id"]: e["slug"] for e in update.episode_entries(allv) if (ROOT / "ep" / f'{e["slug"]}.html').exists()}
    page = lambda m, tpl: tpl.format(slug=slugs[m.group(1)], vid=m.group(1)) if m.group(1) in slugs else m.group(0)
    total = 0
    for name in ("index.html", "episodes.html", "shop.html", "lessons.html"):
        path = ROOT / name
        if not path.exists():
            continue
        s = path.read_text()
        before = s
        # The Gumroad shop moved from mahibrahim.gumroad.com to learnwithian.gumroad.com (old links give 404)
        s = s.replace("https://mahibrahim.gumroad.com/", "https://learnwithian.gumroad.com/")
        # Episode cards (homepage and episodes page)
        s = re.sub(r'<a class="cover" href="' + W + '"', lambda m: page(m, '<a class="cover" href="ep/{slug}.html"'), s)
        # Shop: episode picture and "watch" link
        s = re.sub(r'<a href="' + W + '" tabindex="-1"', lambda m: page(m, '<a href="ep/{slug}.html" tabindex="-1"'), s)
        s = re.sub(r'<a class="watchlink" href="' + W + r'">Watch it free on YouTube',
                   lambda m: page(m, '<a class="watchlink" href="ep/{slug}.html">Watch the episode'), s)
        # Episode cards: small "Lesson plan & worksheets" link before "Shop this episode" (once)
        s = re.sub(r'<p class="shop"><a href="ep/[^"]+"[^>]*>Lesson plan &amp; worksheets</a> &middot; ', '<p class="shop">', s)
        s = re.sub(r'<p class="shop"><a href="shop\.html#([a-z0-9-]+)">Shop this episode</a></p>',
                   lambda m: (f'<p class="shop"><a href="ep/{m.group(1)}.html">Lesson plan &amp; worksheets</a> &middot; '
                              f'<a href="shop.html#{m.group(1)}">Shop this episode</a></p>')
                   if (ROOT / "ep" / f"{m.group(1)}.html").exists() else m.group(0), s)
        # Lesson plans: add the episode page next to the YouTube link (once)
        s = re.sub(r'<p><a href="ep/[^"]+"[^>]*>Episode page: video, lesson plan &amp; worksheets</a> &middot; ', "<p>", s)
        s = re.sub(r'<p><a href="' + W + r'">Open the episode on YouTube</a></p>',
                   lambda m: page(m, '<p><a href="ep/{slug}.html">Episode page: video, lesson plan &amp; worksheets</a> &middot; '
                                     '<a href="https://www.youtube.com/watch?v={vid}">Open the episode on YouTube</a></p>'), s)
        # Episode pages open in a new tab (once)
        s = re.sub(r'href="(ep/[^"]+\.html)"(?! target=)', r'href="\1" target="_blank" rel="noopener"', s)
        if s != before:
            path.write_text(s)
        total += len(re.findall(r'href="ep/[^"]+\.html"', s))
    print("links to episode pages:", total)


if __name__ == "__main__":
    main()
