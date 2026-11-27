"""Language Ambassador: Spanish and Portuguese YouTube titles and descriptions for new episodes.

The video stays in English (the channel teaches English). Only the title and description get a
Spanish and a Portuguese version, so mothers who search YouTube in those languages find it.

For every episode on the site (with its Spanish and Portuguese pages) that is not yet in
data/youtube_es_pt.json, Claude writes two short things per language: the search phrase
("Los colores en inglés para niños") and one sentence of what children learn. The title and the
description are then built from the same fixed template used by hand for the first 7 episodes on
27 Nov 2026, and checked. Claude's Saturday task pastes "ready" entries into YouTube Studio.

Safety: off switch data/PAUSE_TRANSLATIONS; shares the pages writer's call limit and monthly budget;
never stops the site.
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pages_write as w  # noqa: E402

FILE = ROOT / "data" / "youtube_es_pt.json"
DONE_CSV = "https://docs.google.com/spreadsheets/d/1oxDQWj9UmokHvhHp05L9GPgZxyOlyMZ3ctli8nORgsc/gviz/tq?tqx=out:csv&sheet=yt_titles"
PAUSE = ROOT / "data" / "PAUSE_TRANSLATIONS"
MAX_PER_RUN = 3
BANNED = ["$", "precio", "preço", "comprar", "compra", "tienda", "loja", "etsy", "payhip", "gumroad", "amazon", "2-5", "2 a 5"]

T = {
    "es": dict(must="en inglés para niños", intro="Aprende inglés jugando con Ian. El video está en inglés: tu hijo escucha y repite las palabras en inglés.",
               age="Para niños de 2 a 6 años, en casa o en clase.", games="Juegos imprimibles gratis y plan de clase en español:",
               act="Actividad gratis de 15 minutos:", end="Learn with Ian: dibujos animados cortos y tranquilos para aprender inglés.",
               lang="Spanish (Latin America)", learner="Los niños"),
    "pt": dict(must="em inglês para crianças", intro="Aprenda inglês brincando com o Ian. O vídeo é em inglês: seu filho escuta e repete as palavras em inglês.",
               age="Para crianças de 2 a 6 anos, em casa ou na escola.", games="Jogos para imprimir grátis e plano de aula em português:",
               act="Atividade grátis de 15 minutos:", end="Learn with Ian: desenhos curtos e calmos para aprender inglês.",
               lang="Brazilian Portuguese", learner="As crianças"),
}


def page_bits(lang, slug):
    s = (ROOT / lang / "ep" / f"{slug}.html").read_text(encoding="utf-8")
    h1 = html.unescape(re.sub(r"<[^>]+>", "", re.search(r"<h1[^>]*>(.*?)</h1>", s, re.S).group(1))).strip()
    d = re.search(r'<meta name="description" content="([^"]*)"', s)
    return h1, html.unescape(d.group(1)) if d else ""


def play_slug(lang, slug):
    for t in w.load(w.PAGES, []):
        if t.get("episode") == slug and t.get(lang) and (ROOT / lang / "play" / f"{t[lang]['slug']}.html").exists():
            return t[lang]["slug"]
    return None


def build(lang, slug, phrase, learn, h1):
    t = T[lang]
    title = f"{phrase} | {h1} | Learn with Ian"
    desc = [t["intro"], "", learn, t["age"], "", f"🎲 {t['games']} https://learnwithian.com/{lang}/ep/{slug}.html"]
    ps = play_slug(lang, slug)
    if ps:
        desc.append(f"✏️ {t['act']} https://learnwithian.com/{lang}/play/{ps}.html")
    desc += ["", t["end"]]
    return {"title": title, "description": "\n".join(desc)}


def problems_of(entry):
    p = []
    for lang in ("es", "pt"):
        x = entry[lang]
        if len(x["title"]) > 100:
            p.append(f"{lang}: title too long ({len(x['title'])})")
        if T[lang]["must"] not in x["title"].lower():
            p.append(f"{lang}: title must say '{T[lang]['must']}'")
        low = (x["title"] + " " + x["description"]).lower()
        for b in BANNED:
            if b in low:
                p.append(f"{lang}: banned '{b}'")
        if len(x["description"]) > 1500:
            p.append(f"{lang}: description too long")
    return p


def prompt(slug, facts, bits, examples):
    ex = "\n".join(f"- es: {e['es']['title']}\n  pt: {e['pt']['title']}" for e in examples[:4])
    return f"""Episode "{facts['ep_title']}" of Learn with Ian, an English-learning cartoon for children aged 2 to 6.
English page text (what it teaches): {w.episode_text(slug)[:1200]}
Spanish page: title "{bits['es'][0]}", description "{bits['es'][1]}"
Portuguese page: title "{bits['pt'][0]}", description "{bits['pt'][1]}"

Write, for YouTube search in each language:
1. phrase: what the episode teaches as parents search it, ending exactly with "en inglés para niños" (es) or "em inglês para crianças" (pt). 3 to 8 words. Natural Latin-American Spanish / Brazilian Portuguese.
2. learn: ONE short sentence starting "Los niños" (es) / "As crianças" (pt) saying what children learn, true to the episode text. If it lists the English words, keep those words in English.
Titles already used for other episodes (do not repeat their phrase):
{ex}
No prices, no shops, no "buy". Return JSON only: {{"es": {{"phrase": "...", "learn": "..."}}, "pt": {{"phrase": "...", "learn": "..."}}}}"""


def main():
    if PAUSE.exists():
        print("translations: paused")
        return
    data = w.load(FILE, {"episodes": {}})
    eps = data.setdefault("episodes", {})
    # Claude's Saturday task writes a row (youtube_id, date, done) in the sheet tab yt_titles after pasting
    try:
        import csv, io, urllib.request
        raw = urllib.request.urlopen(urllib.request.Request(DONE_CSV, headers={"User-Agent": "learnwithian-site"}), timeout=30).read().decode()
        for row in csv.reader(io.StringIO(raw)):
            if len(row) >= 3 and row[0] in eps and row[2].strip().lower() == "done" and eps[row[0]].get("status") != "done":
                eps[row[0]].update(status="done", done=row[1])
                print(f"translations: {eps[row[0]]['slug']} marked done (pasted {row[1]})")
        w.save(FILE, data)
    except Exception as e:
        print(f"translations: could not read the done list: {e}")
    have = {e["slug"] for e in eps.values()}
    todo = [s for s in w.site_episodes() if s not in have]
    print(f"translations: {len(todo)} episode(s) without Spanish/Portuguese titles")
    if not todo:
        return
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("translations: no key")
        return
    budget = w.Budget()
    for slug in todo[:MAX_PER_RUN]:
        facts = w.episode_facts(slug)
        if not facts["ytid"] or facts["ytid"] in eps:
            continue
        bits = {l: page_bits(l, slug) for l in ("es", "pt")}
        probs = ["not tried"]
        for attempt in (1, 2):
            if not budget.can_call():
                print("translations: call limit or budget reached")
                break
            try:
                extra = "" if attempt == 1 else "\nFix these problems: " + "; ".join(probs)
                ans = w.parse_json(w.ask_claude(budget, w.RULES, prompt(slug, facts, bits, list(eps.values())) + extra))
                entry = {"slug": slug, "added": w.today().isoformat(), "status": "ready"}
                for l in ("es", "pt"):
                    phrase = w.clean(ans[l]["phrase"]).strip().rstrip(".")
                    phrase = phrase[0].upper() + phrase[1:]
                    learn = w.clean(ans[l]["learn"]).strip()
                    learn = learn if learn.endswith(".") else learn + "."
                    entry[l] = build(l, slug, phrase, learn, bits[l][0])
                    if not learn.startswith(T[l]["learner"]):
                        raise ValueError(f"{l}: learn must start with {T[l]['learner']}")
                probs = problems_of(entry)
            except Exception as e:
                probs = [str(e)[:200]]
            if not probs:
                eps[facts["ytid"]] = entry
                w.save(FILE, data)
                print(f"translations: ready for {slug}: {entry['es']['title']} / {entry['pt']['title']}")
                break
            print(f"translations: try {attempt} for {slug}: {probs}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"translations: stopped with a problem: {e}")
