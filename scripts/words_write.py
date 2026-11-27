"""Writes the word pages (Spanish and Portuguese) for episodes that do not have one yet.

One call to Claude per episode gives both languages; the code checks the answer and adds it to
data/words.json. scripts/words.py builds the pages. Runs inside the daily writer workflow.
Limits: MAX_PER_RUN episodes per run, the writer's shared budget (data/writer_log.json).
Off switch: an empty file data/PAUSE_WORDS. Never stops the site.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pages_write as W  # noqa: E402

FILE = ROOT / "data" / "words.json"
PAUSE = ROOT / "data" / "PAUSE_WORDS"
MAX_PER_RUN = 3
LANGS = ("es", "pt")
BANNED = ("$", "€", "precio", "preço", "comprar", "tienda", "loja", "amazon", "etsy", "2-5", "2 a 5", "imprimir", "descargar", "baixar", "pdf")

SYSTEM = """You write short vocabulary pages for "Learn with Ian", a calm cartoon that teaches English to children aged 2 to 6.
The readers are parents and teachers who speak Spanish (Latin America) or Portuguese (Brazil) and often speak little English.
Each page lists the English words of one episode, what they mean and how to say them.
Rules:
- Only words the episode really teaches (see the episode text). 5 to 8 words, the simplest first, lowercase.
- "say" is the pronunciation written the way a Spanish (or Brazilian Portuguese) reader would read it aloud, simple letters only, no phonetic symbols; in words with two or more syllables write the stressed syllable in CAPITALS and split with a hyphen (yellow -> YE-lou).
- Ages are always "2 a 6 años" / "2 a 6 anos". Everything is free: never prices, shops, products, printing or downloads.
- Warm, simple, short sentences. Natural Latin-American Spanish and natural Brazilian Portuguese.
- Allowed HTML: only <b>...</b> around an English word inside the tips. No double-quote characters inside text values.
- Answer with ONE JSON object only, no other text."""


def prompt(ep, example, used):
    return f"""Write the word page for this episode in Spanish (es) and Portuguese (pt).

EPISODE ({ep}) - text of its English page:
{W.episode_text(ep)}

FORMAT - the same keys, style and length as this example (another episode):
{json.dumps({l: example[l] for l in LANGS}, ensure_ascii=False, indent=1)}

Field rules:
- slug: "<tema>-en-ingles" (es) and "<tema>-em-ingles" (pt), lowercase a-z and hyphens, not one of: {sorted(used)}
- topic: 1-2 words. title: "<Tema> en inglés para niños: N palabras con pronunciación | Learn with Ian" style, at most 95 characters.
- h1: the title without the part after the colon. desc: 140-170 characters, says the ages and that there is a free cartoon.
- lead: 1-2 sentences. words: list of {{"en", "tr", "say"}}; add "color" (a hex colour like #e5484d) ONLY when the words are colours.
- phrases: exactly 3 very short English sentences that use the words, each with its translation: [["It is red.", "Es rojo."], ...]
- tips: exactly 3 short tips for practising at home with no materials.
Return: {{"es": {{...}}, "pt": {{...}}}}"""


def check(entry, used):
    problems = []
    for l in LANGS:
        d = entry.get(l) or {}
        tail = "-en-ingles" if l == "es" else "-em-ingles"
        if not (W.slug_ok(d.get("slug", "")) and d["slug"].endswith(tail)) or d.get("slug") in used:
            problems.append(f"{l}: bad or used slug {d.get('slug')!r}")
        for k in ("topic", "title", "h1", "desc", "lead"):
            if not isinstance(d.get(k), str) or not d[k].strip():
                problems.append(f"{l}: missing {k}")
        if len(d.get("title", "")) > 100:
            problems.append(f"{l}: title too long")
        if not 110 <= len(d.get("desc", "")) <= 200:
            problems.append(f"{l}: description length {len(d.get('desc', ''))}")
        if ("2 a 6 años" if l == "es" else "2 a 6 anos") not in d.get("desc", ""):
            problems.append(f"{l}: the description must say the ages")
        if ("inglés" if l == "es" else "inglês") not in d.get("title", ""):
            problems.append(f"{l}: the title must say inglés/inglês")
        ws = d.get("words") or []
        if not 5 <= len(ws) <= 8:
            problems.append(f"{l}: needs 5 to 8 words")
        for w in ws:
            if not (isinstance(w, dict) and re.fullmatch(r"[a-z][a-z '-]{0,24}", str(w.get("en", ""))) and w.get("tr") and w.get("say")):
                problems.append(f"{l}: bad word {w!r}")
            elif "color" in w and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(w["color"])):
                problems.append(f"{l}: bad colour {w['color']!r}")
        if len(d.get("phrases") or []) != 3 or not all(isinstance(x, list) and len(x) == 2 for x in d.get("phrases") or []):
            problems.append(f"{l}: needs exactly 3 phrases")
        if len(d.get("tips") or []) != 3:
            problems.append(f"{l}: needs exactly 3 tips")
        blob = json.dumps(d, ensure_ascii=False).lower()
        problems += [f"{l}: banned word {b!r}" for b in BANNED if b in blob]
    if not problems and [w["en"] for w in entry["es"]["words"]] != [w["en"] for w in entry["pt"]["words"]]:
        problems.append("es and pt must list the same English words in the same order")
    return problems


def clean(v):
    if isinstance(v, list):
        return [clean(x) for x in v]
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    return re.sub(r"<(?!/?b>)[^>]*>", "", v).strip() if isinstance(v, str) else v


def main():
    if PAUSE.exists():
        print("words writer: paused (data/PAUSE_WORDS)")
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("words writer: no key, nothing to do")
        return
    entries = W.load(FILE, [])
    if not entries:
        print("words writer: no example entry in data/words.json")
        return
    have = {e["episode"] for e in entries}
    todo = [ep for ep in W.site_episodes() if ep not in have][:MAX_PER_RUN]
    budget = W.Budget()
    wrote = 0
    for ep in todo:
        used = {e[l]["slug"] for e in entries for l in LANGS}
        problems = ["not tried"]
        for attempt in (1, 2):
            if not budget.can_call():
                print("words writer: call limit or monthly budget reached")
                break
            try:
                extra = "" if attempt == 1 else "\n\nYour last answer had these problems, fix them: " + "; ".join(problems)
                ans = clean(W.parse_json(W.ask_claude(budget, SYSTEM, prompt(ep, entries[0], used) + extra)))
                entry = {"episode": ep, "live_from": W.today().isoformat(), "written_by": "robot", "es": ans.get("es"), "pt": ans.get("pt")}
                problems = check(entry, used)
            except Exception as e:
                problems = [str(e)[:200]]
            if not problems:
                entries.append(entry)
                W.save(FILE, entries)
                wrote += 1
                print(f"words writer: wrote {ep}: {entry['es']['slug']} / {entry['pt']['slug']} ({', '.join(w['en'] for w in entry['es']['words'])})")
                break
            print(f"words writer: try {attempt} for {ep}: {problems[:6]}")
    print(f"words writer: {wrote} new, {len(entries)} in all. this month about ${budget.spent():.2f}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the site
        print(f"words writer: stopped with a problem: {e}")
