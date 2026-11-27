"""Quality checks for data/pages.json. A topic with a problem is not published."""
import re

BANNED = ["$", "payhip", "etsy", "gumroad", "teacherspayteachers", "amazon", "buy ", "price", "2-5", "2 to 5", "comprar", "preço", "precio"]
MIN_STEPS, MIN_WORDS_TOTAL = 4, 120
LANGS = ("en", "es", "pt")


def text_of(d):
    parts = [d.get("h1", ""), d.get("learns", "")] + d.get("words", []) + d.get("need", []) + d.get("steps", []) + d.get("easy", [])
    return re.sub(r"<[^>]+>", " ", " ".join(parts)).lower()


def shingles(s, n=5):
    w = re.findall(r"\w+", s)
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def check_topic(tp, all_topics):
    p = []
    for l in LANGS:
        d = tp.get(l)
        if not d:
            p.append(f"missing {l}")
            continue
        for k in ("slug", "topic", "title", "h1", "desc", "learns", "words", "need", "steps", "easy"):
            if not d.get(k):
                p.append(f"{l}: empty {k}")
        if len(d.get("steps", [])) < MIN_STEPS:
            p.append(f"{l}: fewer than {MIN_STEPS} steps")
        txt = text_of(d)
        if len(re.findall(r"\w+", txt)) < MIN_WORDS_TOTAL:
            p.append(f"{l}: too short")
        low = (d.get("title", "") + " " + d.get("desc", "") + " " + txt).lower()
        for b in BANNED:
            if b in low:
                p.append(f"{l}: banned text '{b.strip()}'")
        if not re.search(r"\b2\b.{0,6}\b6\b", d.get("desc", "")):
            p.append(f"{l}: description must say ages 2 to 6")
        # nothing in the same language may repeat another topic's phrases or slug
        for o in all_topics:
            if o is tp or not o.get(l):
                continue
            if o[l].get("slug") == d.get("slug"):
                p.append(f"{l}: slug used twice")
            if o[l].get("title") == d.get("title"):
                p.append(f"{l}: title used twice")
            a, b = shingles(txt), shingles(text_of(o[l]))
            if a and b and len(a & b) / max(1, min(len(a), len(b))) > 0.35:
                p.append(f"{l}: too similar to topic {o.get('id')}")
    return p
