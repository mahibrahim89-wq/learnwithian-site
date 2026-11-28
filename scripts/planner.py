"""Episode planner: keeps the channel on its long-term program (data/program.json,
full text in program/EPISODE-PLAN.md: 12 worlds a year, 4 weeks a month, episodes A, B, C).

Every day (see .github/workflows/planner.yml) it:
1. finds which program slot each episode on the channel fills (the 7 first episodes are fixed in
   the program; a new one is matched by Claude from its title and page text);
2. reads how long each new episode is (the rule is 8 minutes or more);
3. writes data/program_status.json: this month's world, what is made, what comes next, problems
   (too short, outside this month's world, not in the program) - the Guardian reports the problems;
4. from the 20th, opens one GitHub issue with next month's 12 episodes (the owner gets an email).
It never changes the program or the site pages. Off switch: data/PAUSE_PLANNER.
"""
import datetime
import html
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pages_write as W  # noqa: E402

PROGRAM = ROOT / "data" / "program.json"
STATUS = ROOT / "data" / "program_status.json"
EPISODES = ROOT / "data" / "episodes.json"
RULES_FROM = "2026-11-28"   # episodes published before the program are not judged
MIN_SECONDS = 8 * 60
MAX_SECONDS = 10 * 60 + 30   # Mahmoud 28 Nov 2026: episodes 8 to 10 minutes (30 s grace)
AR = {1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"}


def slots_of(month):
    for w in month["weeks"]:
        for part in "ABC":
            yield f'{month["month"]:02d}-W{w["week"]}-{part}', w, part


def describe(w, part):
    e = w[part]
    if part == "C":
        return f'{w["topic"]} (play and review: {e["idea"]})'
    name = f' "{e["title"]}"' if e.get("title") else ""
    return f'{w["topic"]}{name}: {", ".join(e["words"])}'


def seconds_of(vid):
    try:
        req = urllib.request.Request(f"https://www.youtube.com/watch?v={vid}&hl=en", headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Accept-Language": "en", "Cookie": "CONSENT=YES+1"})
        with urllib.request.urlopen(req, timeout=30) as r:
            m = re.search(r'"lengthSeconds":"(\d+)"', r.read().decode("utf-8", "ignore"))
        return int(m.group(1)) if m else None
    except Exception:
        return None


def lesson_minutes():
    """Fallback when YouTube does not show the length to a robot: the minutes written in the lesson sheet."""
    out = {}
    try:
        import csv
        with open(ROOT / "data" / "lessons.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("minutes") or "").strip().isdigit():
                    out[r["youtube_id"].strip()] = int(r["minutes"]) * 60
    except Exception:
        pass
    return out


def page_text(vid):
    for p in (ROOT / "ep").glob("*.html"):
        s = p.read_text(encoding="utf-8")
        if f"embed/{vid}" in s:
            return W.episode_text(p.stem)[:900]
    return ""


def match(budget, ep, months):
    """Ask Claude which slot a new episode fills. Returns a slot id, "special" or "none"."""
    options = "\n".join(f"{sid}: {describe(w, part)}" for m in months for sid, w, part in slots_of(m))
    prompt = f"""A new episode is on the children's channel "Learn with Ian". Which slot of the program does it fill?

EPISODE TITLE: {ep["title"]}
EPISODE PAGE TEXT: {page_text(ep["id"]) or "(not on the site yet)"}

SLOTS (id: topic and words):
{options}

Answer with ONE JSON object: {{"slot": "<one slot id from the list>"}}. If it is a seasonal special that is not in the list (Valentine, Easter, Earth Day, Mother's Day, Father's Day, 100th day, Christmas, New Year), answer {{"slot": "special"}}. If it fits nothing, answer {{"slot": "none"}}."""
    ans = W.parse_json(W.ask_claude(budget, "You match a preschool episode to a slot of a yearly program. JSON only.", prompt))
    slot = str(ans.get("slot", "none"))
    valid = {sid for m in months for sid, _, _ in slots_of(m)} | {"special", "none"}
    return slot if slot in valid else "none"


def month_issue(g, month, made, status):
    lines = [f"**العالم:** {month['world']}", "", "كل أسبوع 3 حلقات: A اتعلّم (8 كلمات جديدة)، B عيش (8 كلمات جديدة)، C العب وراجع. كل حلقة 8 دقايق على الأقل.", ""]
    for w in month["weeks"]:
        lines.append(f"### الأسبوع {w['week']}: {w['topic']}")
        for part in "ABC":
            sid = f'{month["month"]:02d}-W{w["week"]}-{part}'
            tick = "✅ اتعملت" if sid in made else "⬜"
            lines.append(f"- {tick} **{part}** — {describe(w, part)}")
        lines.append("")
    now = status.get("month", {})
    lines += ["---", f"**الشهر الحالي ({now.get('name_ar', '')}):** اتعمل {now.get('made', 0)} من 12 حلقة.",
              "", "لو عايز تغيّر حاجة في الشهر الجاي، ابعت لـ Claude: \"عدّل خطة الشهر الجاي\". التفاصيل الكاملة في `program/EPISODE-PLAN.md`.",
              "", "التذكرة دي للعلم بس. اقفلها بعد ما تقراها."]
    title = f"📅 حلقات شهر {AR[month['month']]}: {month['world']}"
    new = g.gh("/issues", {"title": title, "body": "\n".join(lines), "assignees": [g.OWNER]}, "POST")
    print("planner: opened", new.get("html_url"))


def main():
    if (ROOT / "data" / "PAUSE_PLANNER").exists():
        print("planner: paused (data/PAUSE_PLANNER)")
        return
    program = W.load(PROGRAM, {})
    months = {m["month"]: m for m in program.get("months", [])}
    status = W.load(STATUS, {"slots": {}})
    slots = status.setdefault("slots", {})
    today = W.today()
    in_year1 = "2026-12" <= today.strftime("%Y-%m") <= "2027-11" or today.strftime("%Y-%m") == "2026-11"
    cur = months.get(12 if today.strftime("%Y-%m") == "2026-11" else today.month)  # late Nov 2026 already works on December
    nxt = months.get(cur["month"] % 12 + 1) if cur else None
    prev = months.get((cur["month"] - 2) % 12 + 1) if cur else None

    for m in months.values():   # the first episodes are fixed in the program
        for sid, w, part in slots_of(m):
            vid = w[part].get("done") if part != "C" else None
            if vid:
                slots.setdefault(vid, {})["slot"] = sid

    episodes = [e for e in W.load(EPISODES, []) if not re.search(r"1 Hour|Compilation|Bedtime Story", e.get("title", ""), re.I)]
    budget = W.Budget()
    for e in episodes:
        rec = slots.setdefault(e["id"], {})
        rec["title"], rec["published"] = e["title"], e.get("published", "")[:10]
        if "slot" not in rec and cur and os.environ.get("ANTHROPIC_API_KEY") and budget.can_call():
            try:
                rec["slot"] = match(budget, e, [x for x in (prev, cur, nxt) if x])
                print(f"planner: {e['title']} -> {rec['slot']}")
            except Exception as ex:
                print(f"planner: could not match {e['title']}: {ex}")
        if rec.get("seconds") is None:
            rec["seconds"] = seconds_of(e["id"]) or lesson_minutes().get(e["id"])

    problems = []
    for vid, rec in slots.items():
        if rec.get("published", "") < RULES_FROM:
            continue
        name = rec.get("title", vid)
        if rec.get("seconds") is not None and rec["seconds"] < MIN_SECONDS:
            problems.append({"key": f"short-{vid}", "text": f"حلقة \"{name}\" مدتها {rec['seconds'] // 60}:{rec['seconds'] % 60:02d}، والقاعدة من 8 لـ 10 دقايق."})
        slot = rec.get("slot")
        if slot not in (None, "none") and rec.get("seconds") is not None and rec["seconds"] > MAX_SECONDS:
            problems.append({"key": f"long-{vid}", "text": f"حلقة \"{name}\" مدتها {rec['seconds'] // 60}:{rec['seconds'] % 60:02d}، والقاعدة من 8 لـ 10 دقايق."})
        if slot == "none":
            problems.append({"key": f"none-{vid}", "text": f"حلقة \"{name}\" مش من المنهج (مالهاش مكان في البرنامج)."})
        elif slot and slot != "special" and cur:
            sm = int(slot[:2])
            pm = 12 if rec["published"][:7] == "2026-11" else int(rec["published"][5:7])
            planned_special = bool(months[sm]["weeks"][int(slot[4]) - 1][slot[-1]].get("title")) if slot[-1] != "C" else False
            if sm != pm and not planned_special:
                problems.append({"key": f"world-{vid}", "text": f"حلقة \"{name}\" من عالم شهر {AR[sm]}، واتنشرت في شهر {AR[pm]}. المنهج بيقول كل شهر عالمه."})

    made = {rec["slot"] for rec in slots.values() if rec.get("slot")}
    status["problems"] = problems
    status["updated"] = today.isoformat()
    if cur and in_year1:
        todo = [(sid, w, part) for sid, w, part in slots_of(cur) if sid not in made]
        status["month"] = {"month": cur["month"], "name_ar": AR[cur["month"]], "world": cur["world"],
                           "made": 12 - len(todo), "of": 12,
                           "next": ({"slot": todo[0][0], "what": describe(todo[0][1], todo[0][2])} if todo else None)}
        print(f"planner: {AR[cur['month']]} ({cur['world']}): {12 - len(todo)} of 12 made; next: {status['month']['next']}")
    else:
        status["month"] = {"note": "outside Year 1 of the program: the Year 2 week list is not written yet"}
        print("planner:", status["month"]["note"])
    print(f"planner: {len(problems)} problem(s)")
    for p in problems:
        print(" -", p["text"])

    # from the 20th: one issue with next month's episodes
    key = f"{today.year + (1 if today.month == 12 else 0)}-{(today.month % 12) + 1:02d}"
    if in_year1 and nxt and today.day >= 20 and today.strftime("%Y-%m") != "2026-11" and status.get("issue_month") != key and os.environ.get("GITHUB_TOKEN"):
        try:
            import guardian as g
            month_issue(g, nxt, made, status)
            status["issue_month"] = key
        except Exception as ex:
            print("planner: could not open the month issue:", ex)
    W.save(STATUS, status)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the site
        print(f"planner: stopped with a problem: {e!r}")
