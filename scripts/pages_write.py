"""Writer robot for the free activity pages (runs by itself every day, see .github/workflows/pages.yml).

1. Reads the plan (data/page_plan.json) and the written topics (data/pages.json).
2. If a new episode appeared on the site and has no topic in the plan, asks Claude for one
   new topic idea for it (with a new search phrase) and adds it to the plan.
3. Writes the next topics in the plan with Claude (English, Spanish, Portuguese), checks them
   (pages_check.py) and adds the good ones to data/pages.json. scripts/pages.py builds the pages.

Safety:
- Stops at once if the file data/PAUSE_WRITER exists (the off switch).
- At most MAX_TOPICS_PER_RUN topics per run and MAX_TOPICS_PER_WEEK topics in 7 days.
  Topics for new episodes go first and may pass the weekly limit.
- At most MAX_CALLS_PER_RUN calls to Claude per run, and stops for the month when the
  estimated cost in data/writer_log.json reaches MONTH_BUDGET_USD.
- Never touches anything except data/page_plan.json, data/pages.json and data/writer_log.json.
- Never stops the rest of the site: every problem is printed and the robot ends normally.
"""
import datetime
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pages_check  # noqa: E402

PLAN = ROOT / "data" / "page_plan.json"
PAGES = ROOT / "data" / "pages.json"
LOG = ROOT / "data" / "writer_log.json"
PAUSE = ROOT / "data" / "PAUSE_WRITER"

MODEL = os.environ.get("WRITER_MODEL", "claude-sonnet-5-5")
FALLBACK_MODEL = "claude-haiku-5-5"
MAX_TOPICS_PER_RUN = int(os.environ.get("WRITER_MAX_TOPICS", "2"))
MAX_TOPICS_PER_WEEK = 7          # 7 topics = 21 pages a week at most (Mahmoud, 27 Nov)
MAX_CALLS_PER_RUN = 6
MONTH_BUDGET_USD = 8.0
PRICE_PER_MTOK = {"in": 3.0, "out": 15.0}  # used only to estimate the cost (on the high side)
MAX_OUT_TOKENS = 8000


def today():
    return (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=4)).date()


def load(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------- Claude ----------

class Budget:
    def __init__(self):
        self.log = load(LOG, {"months": {}, "runs": []})
        self.month = today().strftime("%Y-%m")
        self.calls = 0

    def spent(self):
        return self.log["months"].get(self.month, {}).get("usd", 0.0)

    def can_call(self):
        return self.calls < MAX_CALLS_PER_RUN and self.spent() < MONTH_BUDGET_USD

    def add(self, tin, tout):
        m = self.log["months"].setdefault(self.month, {"usd": 0.0, "calls": 0, "in": 0, "out": 0})
        m["in"] += tin
        m["out"] += tout
        m["calls"] += 1
        m["usd"] = round(m["usd"] + tin / 1e6 * PRICE_PER_MTOK["in"] + tout / 1e6 * PRICE_PER_MTOK["out"], 4)
        self.calls += 1
        save(LOG, self.log)


def ask_claude(budget, system, prompt, model=None):
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("no ANTHROPIC_API_KEY")
    if not budget.can_call():
        raise RuntimeError("call limit or monthly budget reached")
    model = model or MODEL
    body = json.dumps({"model": model, "max_tokens": MAX_OUT_TOKENS, "system": system,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            res = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:300]
        if e.code in (400, 404) and "model" in msg.lower() and model != FALLBACK_MODEL:
            print(f"model {model} not available, using {FALLBACK_MODEL}")
            return ask_claude(budget, system, prompt, FALLBACK_MODEL)
        raise RuntimeError(f"Claude API error {e.code}: {msg}")
    u = res.get("usage", {})
    budget.add(u.get("input_tokens", 0), u.get("output_tokens", 0))
    return "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")


def parse_json(text):
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in the answer")
    return json.loads(m.group(0))


# ---------- episode facts from the site ----------

def episode_text(slug):
    p = ROOT / "ep" / f"{slug}.html"
    s = p.read_text(encoding="utf-8")
    main = re.search(r"<main.*?</main>", s, re.S)
    s = main.group(0) if main else s
    s = re.split(r"Worksheets for this episode|Printables", s)[0]
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()[:2500]


def episode_facts(slug):
    s = (ROOT / "ep" / f"{slug}.html").read_text(encoding="utf-8")
    yt = re.search(r"embed/([A-Za-z0-9_-]{11})", s)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", s, re.S)
    ep_title = html.unescape(re.sub(r"<[^>]+>", "", h1.group(1))).split(":")[-1].strip() if h1 else slug
    short = re.sub(r"^Ian'?s\s+", "", ep_title).strip()
    return {"ytid": yt.group(1) if yt else "", "ep_title": ep_title, "game_title": {"en": short, "es": short, "pt": short}}


def site_episodes():
    eps = []
    for p in sorted((ROOT / "ep").glob("*.html")):
        s = p.stem
        if (ROOT / "es" / "ep" / f"{s}.html").exists() and (ROOT / "pt" / "ep" / f"{s}.html").exists():
            eps.append(s)
    return eps


# ---------- prompts ----------

RULES = """You write free activity pages for "Learn with Ian", a calm English-learning cartoon for children aged 2 to 6 (home and preschool).
Each page is a 15-minute activity that a parent or teacher can do with things every home or class already has.
Rules:
- Ages are always "2 to 6" (Spanish "2 a 6 años", Portuguese "2 a 6 anos"). Never write 2-5.
- Never mention prices, shops, buying, products or brand names. Everything is free.
- Be true to the episode: only say the episode shows something if the episode text below says so. Otherwise write "for example".
- Safe for small children: no small parts for under-3s without an adult, no scissors without an adult, nothing scary.
- Simple, warm, practical. No keyword stuffing. Sentences short.
- Spanish is natural Latin-American Spanish, Portuguese is natural Brazilian Portuguese. In es and pt the English words the child learns stay in English (they are learning English), the rest is translated.
- Allowed HTML inside text: only <b>...</b> and HTML entities like &ldquo; &rdquo; &rsquo; &middot;. No other tags.
- Answer with ONE JSON object only, no other text."""


def example_block(pages):
    ex = next((t for t in pages if t.get("id") == "color-hunt-game"), pages[0] if pages else None)
    if not ex:
        return ""
    keep = {l: {k: ex[l][k] for k in ("topic", "title", "h1", "desc", "learns", "words", "need", "steps", "easy")} for l in ("en", "es", "pt")}
    return json.dumps(keep, ensure_ascii=False, indent=1)


def write_prompt(plan_tp, pages):
    ep = plan_tp["episode"]
    others = "; ".join(f"{t['en']['title']}" for t in pages if t.get("en"))
    return f"""Write the three pages (en, es, pt) for this topic.

TOPIC IDEA: {plan_tp['idea']}
SEARCH PHRASE the page must answer (use it naturally in title, h1 and desc):
- en: {plan_tp['phrases']['en']}
- es: {plan_tp['phrases']['es']}
- pt: {plan_tp['phrases']['pt']}

EPISODE ({ep}) - text of its page on the site:
{episode_text(ep)}

PAGES THAT ALREADY EXIST (do not repeat their game, title or wording): {others}

FORMAT - same keys and the same style and length as this example (a different topic):
{example_block(pages)}

Field rules:
- topic: 1-2 words (the subject, e.g. Colors / Colores / Cores).
- title: "<phrase-based title>: Free 15-Minute ... | Learn with Ian" style, at most 95 characters in total including " | Learn with Ian".
- h1: shorter than title, no "| Learn with Ian".
- desc: 140-170 characters, says ages 2 to 6 (es "2 a 6 años", pt "2 a 6 anos"), says it is free.
- learns: one sentence starting "Children ..." (es "Los niños ...", pt "As crianças ...").
- words: 4-6 English words; in es and pt write "english &middot; translation".
- need: exactly 3 items, the last one is the episode {html.escape(facts_title(ep))} (free on YouTube).
- steps: exactly 5 steps; quote what the adult says in English with &ldquo; &rdquo; and the key word in <b></b>.
- easy: exactly 3 items starting with <b>Younger children:</b>, <b>Older children:</b>, <b>Mixed group:</b> (translated in es/pt).
Return: {{"en": {{...}}, "es": {{...}}, "pt": {{...}}}}"""


def facts_title(ep):
    return episode_facts(ep)["ep_title"].replace("'", "&rsquo;")


def plan_prompt(ep, plan, pages):
    used = sorted({t["phrases"]["en"] for t in plan if t.get("phrases")} | {t["en"]["title"] for t in pages if t.get("en")})
    return f"""A new episode is on the site. Propose ONE new free 15-minute activity for it, with a real search phrase that parents or teachers type into Google, in English, Spanish and Portuguese.
The phrase must be different from the episode page's own title and from every phrase already used: {used}

EPISODE ({ep}) page text:
{episode_text(ep)}

Return JSON: {{"idea": "<1-2 sentences, what the children do>", "phrases": {{"en": "...", "es": "...", "pt": "..."}}, "slugs": {{"en": "<phrase as a short slug, lowercase, a-z 0-9 and hyphens>", "es": "...", "pt": "..."}}}}
Spanish and Portuguese phrases should say "en inglés" / "em inglês" when it fits, because the children learn English."""


# ---------- cleaning and checks ----------

def clean(v):
    if isinstance(v, list):
        return [clean(x) for x in v]
    if not isinstance(v, str):
        return v
    v = v.strip()
    v = re.sub(r"<(?!/?b>)[^>]*>", "", v)  # only <b> survives
    return v


def slug_ok(s):
    return bool(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s or "")) and len(s) <= 60


def build_topic(plan_tp, answer, pages):
    facts = episode_facts(plan_tp["episode"])
    tp = {"id": plan_tp["id"], "episode": plan_tp["episode"], **facts, "live_from": today().isoformat(), "written_by": "robot"}
    for l in ("en", "es", "pt"):
        d = answer.get(l) or {}
        tp[l] = {"slug": plan_tp["slugs"][l]}
        for k in ("topic", "title", "h1", "desc", "learns", "words", "need", "steps", "easy"):
            tp[l][k] = clean(d.get(k, "" if k not in ("words", "need", "steps", "easy") else []))
    problems = pages_check.check_topic(tp, pages + [tp])
    for l in ("en", "es", "pt"):
        if len(tp[l]["title"]) > 100:
            problems.append(f"{l}: title too long")
        if not 100 <= len(re.sub(r"&\w+;", "x", tp[l]["desc"])) <= 200:
            problems.append(f"{l}: description length {len(tp[l]['desc'])}")
        if len(tp[l]["steps"]) != 5:
            problems.append(f"{l}: needs 5 steps")
    return tp, problems


# ---------- main ----------

def main():
    if PAUSE.exists():
        print("writer: paused (data/PAUSE_WRITER exists)")
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("writer: no key, nothing to do")
        return
    plan_doc = load(PLAN, {"topics": []})
    plan = plan_doc["topics"]
    pages = load(PAGES, [])
    budget = Budget()
    written = {t["id"] for t in pages}
    run = {"date": today().isoformat(), "written": [], "skipped": [], "planned": []}

    # 1) new episodes get a topic idea
    for ep in site_episodes():
        if any(t["episode"] == ep for t in plan):
            continue
        try:
            ans = parse_json(ask_claude(budget, RULES, plan_prompt(ep, plan, pages)))
            slugs = {l: ans["slugs"][l] for l in ("en", "es", "pt")}
            used = {t.get("slugs", {}).get(l) for t in plan for l in ("en", "es", "pt")} | {t[l]["slug"] for t in pages for l in ("en", "es", "pt") if t.get(l)}
            if not all(slug_ok(s) and s not in used for s in slugs.values()):
                raise ValueError(f"bad slugs {slugs}")
            new = {"id": slugs["en"], "episode": ep, "idea": ans["idea"].strip(), "slugs": slugs,
                   "phrases": {l: ans["phrases"][l].strip() for l in ("en", "es", "pt")}, "added_by": "robot", "added": today().isoformat()}
            plan.append(new)
            run["planned"].append(new["id"])
            print(f"writer: new topic idea for {ep}: {new['phrases']['en']}")
        except Exception as e:
            print(f"writer: could not plan a topic for {ep}: {e}")
    save(PLAN, plan_doc)

    # 2) weekly limit
    week_ago = (today() - datetime.timedelta(days=6)).isoformat()
    this_week = sum(1 for t in pages if t.get("live_from", "") >= week_ago)
    room = max(0, min(MAX_TOPICS_PER_RUN, MAX_TOPICS_PER_WEEK - this_week))
    todo = [t for t in plan if t["id"] not in written and not t.get("done_by_hand") and t.get("idea") and not t.get("failed")]
    # New episodes go first (newest first): a page is most useful while the episode is new.
    # They may pass the weekly limit (never the per-run limit); older topics wait for room.
    fresh = sorted([t for t in todo if t.get("added_by") == "robot"], key=lambda t: t.get("added", ""), reverse=True)
    older = [t for t in todo if t.get("added_by") != "robot"]
    picks = (fresh + older[:max(0, room - len(fresh))])[:MAX_TOPICS_PER_RUN]
    print(f"writer: {len(todo)} topics waiting ({len(fresh)} for new episodes), {this_week} written in the last 7 days, room for {room} now")

    # 3) write
    for ptp in picks:
        if not budget.can_call():
            print("writer: call limit or monthly budget reached, stopping")
            break
        if not all((ROOT / p / "ep" / f"{ptp['episode']}.html").exists() for p in ("", "es", "pt")):
            print(f"writer: episode pages for {ptp['episode']} not ready, later")
            continue
        problems = ["not tried"]
        for attempt in (1, 2):
            if not budget.can_call():
                break
            try:
                extra = "" if attempt == 1 else "\n\nYour last answer had these problems, fix them: " + "; ".join(problems)
                ans = parse_json(ask_claude(budget, RULES, write_prompt(ptp, pages) + extra))
                tp, problems = build_topic(ptp, ans, pages)
            except Exception as e:
                problems = [str(e)[:200]]
            if not problems:
                pages.append(tp)
                save(PAGES, pages)
                run["written"].append(ptp["id"])
                print(f"writer: wrote {ptp['id']} (en {tp['en']['slug']}, es {tp['es']['slug']}, pt {tp['pt']['slug']})")
                break
            print(f"writer: try {attempt} for {ptp['id']} has problems: {problems}")
        if problems:
            run["skipped"].append({"id": ptp["id"], "why": problems[:5]})
            ptp["fails"] = ptp.get("fails", 0) + 1
            if ptp["fails"] >= 3:
                ptp["failed"] = True  # stop trying after 3 bad days; a human can remove this mark
            save(PLAN, plan_doc)

    log = load(LOG, {"months": {}, "runs": []})
    log["runs"] = (log.get("runs", []) + [run])[-60:]
    save(LOG, log)
    print(f"writer: done. this month about ${budget.spent():.2f} of ${MONTH_BUDGET_USD:.0f}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the site
        print(f"writer: stopped with a problem: {e}")
