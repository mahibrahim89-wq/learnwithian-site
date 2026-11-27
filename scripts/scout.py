"""The Scout: finds what parents and teachers really type into search, and feeds the writer.

Every week (see .github/workflows/scout.yml):
1. For each episode on the site it takes 1-2 topic words per language (data/scout_seeds.json;
   for a new episode Claude writes them once) and asks the public search-suggestion services
   of Google, YouTube, Bing and DuckDuckGo how people finish phrases such as "colors game for".
2. It drops what does not fit us (coloring, paid things, brands, older children ...).
3. Claude picks the best new activity ideas, each one tied to real suggestions from the list,
   and they are added to data/page_plan.json with added_by "scout". The writer robot
   (scripts/pages_write.py) writes them later, with all its usual checks.

Safety:
- Off switch: an empty file data/PAUSE_SCOUT.
- At most MAX_NEW_PER_RUN new topics per run, one per episode, and nothing at all while
  QUEUE_CAP topics are already waiting to be written.
- Uses the writer's budget (data/writer_log.json): same monthly cap, 1-2 calls per run.
- Only touches data/page_plan.json, data/scout_seeds.json, data/scout_report.json and the log.
- SCOUT_DRY=1: look and report only, add nothing to the plan.
- Never stops the site: every problem is printed and the robot ends normally.
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pages_write as W  # noqa: E402  (Claude, budget, episode facts)

SEEDS = ROOT / "data" / "scout_seeds.json"
REPORT = ROOT / "data" / "scout_report.json"
PAUSE = ROOT / "data" / "PAUSE_SCOUT"
LANGS = ("en", "es", "pt")
MAX_NEW_PER_RUN = 3
QUEUE_CAP = 8            # topics waiting for the writer; above this the scout adds nothing
MAX_EPISODES_PER_RUN = 12
MAX_TERMS = 2
PER_EPISODE_TO_CLAUDE = 24
DRY = os.environ.get("SCOUT_DRY", "").strip().lower() in ("1", "true", "yes")
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"

TEMPLATES = {
    "en": ["{t} game for", "{t} activities for", "{t} for toddlers", "teaching {t} to"],
    "es": ["juego de {t} en inglés", "actividades de {t} en", "{t} en inglés para", "enseñar {t} en inglés"],
    "pt": ["jogo de {t} em inglês", "atividades de {t} em", "{t} em inglês para", "ensinar {t} em inglês"],
}
MARKET = {"en": ("en", "us", "en-US", "us-en"), "es": ("es", "mx", "es-MX", "mx-es"), "pt": ("pt", "br", "pt-BR", "br-pt")}
# Things we never make pages for (paid or drawn products belong to the shop, songs and apps are not ours).
BANNED = ("coloring", "colouring", "colorear", "colorir", "pintar", "color by", "worksheet", "ficha", "fichas", "folha",
          "pdf", "song", "songs", "cancion", "canciones", "musica", "app", "apps", "online", "download", "descargar",
          "baixar", "price", "buy", "comprar", "amazon", "adult", "adultos", "teen", "grade", "primaria", "secundaria",
          "fundamental", "esl adults", "tattoo", "nails", "outfit", "makeup", "wallpaper", "meme", "quiz", "test",
          "examen", "prova", "halloween", "kahoot", "roblox", "minecraft", "wordwall", "liveworksheets",
          "thrones", "excel", "near me", "senior", "traductor", "traduccion", "traducao", "imprimir", "video",
          "youtube", "como se dice", "como se escribe", "como se diz", "como fala", "como escreve", "letra", "poema",
          "mensagem", "mensaje", "frases", "medico", "large group", "party", "office", "work")
# A suggestion must be about children or about doing something with them.
ABOUT_US = {
    "en": ("toddler", "preschool", "kid", "children", "child", "kindergarten", "year old", "activity", "activities",
           "game", "teach", "learn", "circle time", "at home"),
    "es": ("nino", "preescolar", "infantil", "juego", "actividad", "aprender", "ensenar", "vocabulario", "kinder"),
    "pt": ("crianca", "infantil", "jogo", "atividade", "brincadeira", "aprender", "ensinar", "vocabulario", "palavras"),
}


def plain(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


# ---------- suggestion services ----------

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en,es;q=0.8,pt;q=0.7"})
    with urllib.request.urlopen(req, timeout=12) as r:
        raw = r.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return json.loads(raw.decode("latin-1"))


def s_google(q, lang, yt=False):
    hl, gl, _, _ = MARKET[lang]
    url = ("https://suggestqueries.google.com/complete/search?client=firefox&ie=utf-8&oe=utf-8"
           f"&hl={hl}&gl={gl}&q={urllib.parse.quote(q)}" + ("&ds=yt" if yt else ""))
    return [x for x in _get(url)[1] if isinstance(x, str)]


def s_youtube(q, lang):
    return s_google(q, lang, yt=True)


def s_bing(q, lang):
    return [x for x in _get(f"https://api.bing.com/osjson.aspx?query={urllib.parse.quote(q)}&market={MARKET[lang][2]}")[1]
            if isinstance(x, str)]


def s_ddg(q, lang):
    return [x.get("phrase", "") for x in _get(f"https://duckduckgo.com/ac/?q={urllib.parse.quote(q)}&kl={MARKET[lang][3]}")
            if isinstance(x, dict)]


SOURCES = {"google": s_google, "youtube": s_youtube, "bing": s_bing, "duckduckgo": s_ddg}


def harvest(seeds, episodes):
    """-> {episode: {lang: {phrase: set(sources)}}}, and how each service answered."""
    stats = {name: {"ok": 0, "failed": 0} for name in SOURCES}
    dead, found = set(), {}
    for ep in episodes:
        for lang in LANGS:
            bucket = found.setdefault(ep, {}).setdefault(lang, {})
            for term in seeds[ep][lang][:MAX_TERMS]:
                for tpl in TEMPLATES[lang]:
                    q = tpl.format(t=term)
                    for name, fn in SOURCES.items():
                        if name in dead:
                            continue
                        try:
                            got = fn(q, lang)
                            stats[name]["ok"] += 1
                        except Exception:
                            stats[name]["failed"] += 1
                            if stats[name]["failed"] >= 8 and stats[name]["ok"] == 0:
                                dead.add(name)  # this service does not answer robots today
                            continue
                        for phrase in got:
                            phrase = re.sub(r"\s+", " ", phrase).strip().lower()
                            if fits(phrase, lang):
                                bucket.setdefault(phrase, set()).add(name)
                        time.sleep(0.12)
    return found, stats


def fits(phrase, lang):
    p = plain(phrase)
    words = p.split()
    if not 3 <= len(words) <= 10 or len(phrase) > 80:
        return False
    if any(re.search(r"\b" + re.escape(b) + r"(s|es)?\b", p) for b in BANNED):
        return False
    if re.search(r"\b(19|20)\d\d\b", p):
        return False
    if lang in ("es", "pt") and "ingles" not in p:
        return False
    return any(w in p for w in ABOUT_US[lang])


# ---------- Claude ----------

SYSTEM = """You plan free activity pages for "Learn with Ian", a calm cartoon that teaches English to children aged 2 to 6 (home and preschool).
One page = one 15-minute activity a parent or teacher does with things every home or class already has, tied to one episode.
Rules: everything is free; never prices, shops, products or brand names; no coloring pages, no worksheets, no songs, no apps or screens for the child; nothing scary; safe for small children.
Spanish is natural Latin-American Spanish, Portuguese is natural Brazilian Portuguese, and their phrases say "en inglés" / "em inglês" because the children learn English.
Answer with ONE JSON object only, no other text."""


def seeds_prompt(missing):
    blocks = "\n\n".join(f"EPISODE {ep}:\n{W.episode_text(ep)[:900]}" for ep in missing)
    return f"""For each episode give the 1-2 short topic words people would use in a search, in English, Spanish and Portuguese (lowercase, 1-3 words each, most general first). Example for an episode about colors: {{"en": ["colors"], "es": ["colores"], "pt": ["cores"]}}.

{blocks}

Return JSON: {{"<episode slug>": {{"en": ["..."], "es": ["..."], "pt": ["..."]}}, ...}}"""


def pick_prompt(room, episodes, found, plan, pages):
    used = sorted({v for t in plan if t.get("phrases") for v in t["phrases"].values()}
                  | {t[l]["title"] for t in pages for l in LANGS if t.get(l)})
    count = {ep: sum(1 for t in plan if t["episode"] == ep) for ep in episodes}
    blocks = []
    for ep in episodes:
        lines = [f"EPISODE {ep} (\"{W.episode_facts(ep)['ep_title']}\", already has {count[ep]} activity topics). It teaches: "
                 + W.episode_text(ep)[:350]]
        for lang in LANGS:
            top = sorted(found[ep][lang].items(), key=lambda kv: (-len(kv[1]), -len(kv[0].split()), kv[0]))[:PER_EPISODE_TO_CLAUDE]
            lines.append(f"  real searches ({lang}): " + " | ".join(f"{p} [{len(s)}]" for p, s in top) if top else f"  real searches ({lang}): none")
        blocks.append("\n".join(lines))
    return f"""Below are real search suggestions (what people type into Google, YouTube, Bing and DuckDuckGo), per episode. The number in [ ] is how many services showed the phrase.

Choose at most {room} NEW activity topics, the ones most likely to bring parents and teachers of 2 to 6 year olds to a free 15-minute activity page. At most one topic per episode; prefer episodes that have fewer topics.
Each topic must:
- answer a real search from the lists (copy that search exactly into "evidence"; English evidence is required, Spanish and Portuguese evidence when a listed search fits, otherwise ""),
- be a different activity and a different search phrase from everything already used: {used}
- be doable with household or classroom things, be true to what the episode teaches, and need no drawing, printing or screen.
Prefer the longer, more specific searches (4 words or more, e.g. with an age, a place or a kind of game) over the broadest ones: a young site cannot win the broadest phrases.
The "phrases" must be correctly spelled, with accents (inglés, inglês), even when the copied evidence has none.
Slugs are short: 3 to 5 words that name the activity or the search (e.g. winter-clothes-game, juego-de-colores-en-ingles).
If nothing good is left for an episode, skip it. Fewer good topics is better than weak ones.
Inside the JSON text values never use the double-quote character (write English words the adult says in single quotes).

{chr(10).join(blocks)}

Return JSON: {{"topics": [{{"episode": "<slug>", "idea": "<1-2 sentences, what the children do>", "phrases": {{"en": "<search phrase the page answers>", "es": "...", "pt": "..."}}, "slugs": {{"en": "<short slug, lowercase a-z 0-9 hyphens>", "es": "...-en-ingles", "pt": "...-em-ingles"}}, "evidence": {{"en": "...", "es": "...", "pt": "..."}}}}]}}"""


# ---------- main ----------

def waiting(plan, pages):
    written = {t["id"] for t in pages}
    return [t for t in plan if t["id"] not in written and not t.get("done_by_hand") and t.get("idea") and not t.get("failed")]


def main():
    if PAUSE.exists():
        print("scout: paused (data/PAUSE_SCOUT exists)")
        return
    plan_doc = W.load(W.PLAN, {"topics": []})
    plan, pages = plan_doc["topics"], W.load(W.PAGES, [])
    budget = W.Budget()
    today = W.today().isoformat()
    report = {"date": today, "dry_run": DRY, "added": [], "note": ""}

    queue = len(waiting(plan, pages))
    room = max(0, min(MAX_NEW_PER_RUN, QUEUE_CAP - queue))

    # 1) topic words for every episode (Claude writes them once for a new episode)
    seeds = W.load(SEEDS, {})
    episodes = W.site_episodes()
    missing = [ep for ep in episodes if not all(seeds.get(ep, {}).get(l) for l in LANGS)]
    if missing and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            ans = W.parse_json(W.ask_claude(budget, SYSTEM, seeds_prompt(missing[:6])))
            for ep in missing[:6]:
                got = ans.get(ep, {})
                clean = {l: [re.sub(r"\s+", " ", str(x)).strip().lower() for x in got.get(l, []) if 1 <= len(str(x).split()) <= 4][:3] for l in LANGS}
                if all(clean[l] for l in LANGS):
                    seeds[ep] = clean
                    print(f"scout: topic words for {ep}: {clean}")
            W.save(SEEDS, seeds)
        except Exception as e:
            print(f"scout: could not get topic words for new episodes: {e}")
    episodes = [ep for ep in episodes if all(seeds.get(ep, {}).get(l) for l in LANGS)]
    # episodes with the fewest topics first; the newest pages first among equals
    episodes.sort(key=lambda ep: (sum(1 for t in plan if t["episode"] == ep), -(ROOT / "ep" / f"{ep}.html").stat().st_mtime))
    episodes = episodes[:MAX_EPISODES_PER_RUN]

    # 2) what people type
    found, stats = harvest(seeds, episodes)
    total = sum(len(found[ep][l]) for ep in found for l in LANGS)
    report["sources"] = stats
    report["suggestions"] = total
    report["top"] = {ep: {l: [p for p, s in sorted(found[ep][l].items(), key=lambda kv: (-len(kv[1]), -len(kv[0].split()), kv[0]))[:8]] for l in LANGS}
                     for ep in episodes}
    print(f"scout: {total} fitting suggestions for {len(episodes)} episodes; services: "
          + ", ".join(f"{n} {v['ok']} ok/{v['failed']} failed" for n, v in stats.items()))
    if total == 0:
        report["note"] = "no suggestions (the services did not answer)"
        W.save(REPORT, report)
        return

    # 3) Claude picks, the code checks
    if room == 0:
        report["note"] = f"queue is full ({queue} topics waiting), nothing added"
        print("scout:", report["note"])
        W.save(REPORT, report)
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        report["note"] = "no key, suggestions only"
        W.save(REPORT, report)
        print("scout: no key, report only")
        return
    ans, err = None, ""
    for attempt in (1, 2):  # a broken JSON answer gets one more try
        try:
            extra = "" if attempt == 1 else f"\n\nYour last answer was not valid JSON ({err}). Send valid JSON only."
            ans = W.parse_json(W.ask_claude(budget, SYSTEM, pick_prompt(room, episodes, found, plan, pages) + extra))
            break
        except Exception as e:
            err = str(e)[:150]
            print(f"scout: try {attempt}: {err}")
    if ans is None:
        report["note"] = f"Claude did not answer: {err}"
        W.save(REPORT, report)
        return
    used_slugs = ({t.get("slugs", {}).get(l) for t in plan for l in LANGS} | {t["id"] for t in plan}
                  | {t[l]["slug"] for t in pages for l in LANGS if t.get(l)})
    known = plain(" ".join([v for t in plan if t.get("phrases") for v in t["phrases"].values()]
                           + [t[l]["title"] for t in pages for l in LANGS if t.get(l)]))
    seen_eps = set()
    for c in (ans.get("topics") or [])[:room]:
        try:
            ep = c["episode"]
            slugs = {l: c["slugs"][l].strip() for l in LANGS}
            phrases = {l: re.sub(r"\s+", " ", c["phrases"][l]).strip() for l in LANGS}
            ev = {l: re.sub(r"\s+", " ", (c.get("evidence") or {}).get(l, "")).strip().lower() for l in LANGS}
            why = None
            if ep not in found or ep in seen_eps:
                why = "unknown or repeated episode"
            elif not all(W.slug_ok(s) and s not in used_slugs for s in slugs.values()) or len(set(slugs.values())) < 3:
                why = f"bad or used slugs {slugs}"
            elif plain(ev["en"]) not in {plain(p) for p in found[ep]["en"]}:
                why = f"English evidence is not a real suggestion: {ev['en']!r}"
            elif any(fits(phrases[l], l) is False and l != "en" for l in ("es", "pt")):
                why = "Spanish or Portuguese phrase does not fit (must say inglés/inglês, nothing banned)"
            elif not fits(phrases["en"], "en"):
                why = "English phrase does not fit (length or a banned word)"
            elif all(w in known for w in re.findall(r"[a-z]+", plain(phrases["en"])) if len(w) > 3):
                why = "too close to a phrase we already have"
            if why:
                print(f"scout: dropped {slugs.get('en')}: {why}")
                continue
            for l in ("es", "pt"):  # keep evidence only when it really is in the list
                if plain(ev[l]) not in {plain(p) for p in found[ep][l]}:
                    ev[l] = ""
            new = {"id": slugs["en"], "episode": ep, "idea": c["idea"].strip(), "slugs": slugs, "phrases": phrases,
                   "added_by": "scout", "added": today, "from_suggestions": {l: v for l, v in ev.items() if v}}
            seen_eps.add(ep)
            used_slugs |= set(slugs.values())
            known += " " + plain(" ".join(phrases.values()))
            report["added"].append({"id": new["id"], "episode": ep, "phrases": phrases, "evidence": new["from_suggestions"], "idea": new["idea"]})
            if not DRY:
                plan.append(new)
            print(f"scout: {'would add' if DRY else 'added'} {new['id']} for {ep}: {phrases['en']} (people type: {ev['en']})")
        except Exception as e:
            print(f"scout: dropped a topic with a bad shape: {e}")
    if not DRY and report["added"]:
        W.save(W.PLAN, plan_doc)
    report["note"] = f"{len(report['added'])} topic(s) {'would be ' if DRY else ''}added; {queue} were waiting"
    W.save(REPORT, report)
    print(f"scout: done. {report['note']}. this month about ${budget.spent():.2f}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the site
        print(f"scout: stopped with a problem: {e!r}")
