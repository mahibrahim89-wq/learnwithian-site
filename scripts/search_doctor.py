"""Search Doctor: once a week reads Google Search Console and makes the site better by itself.

1. Report: every page with its searches, impressions (people who saw it in Google), clicks and
   position for the last 28 days -> data/search_report.json (read in the Saturday check).
2. Fix titles: a free activity page (data/pages.json) that is seen a lot but almost never clicked
   gets a better title and description, written with Claude and checked by pages_check.py.
   At most MAX_FIXES pages a week, and each page at most once every 28 days.
3. New topics: real searches that bring people to the site but have no page of their own become
   new topics in data/page_plan.json; the writer robot writes them. At most MAX_NEW_TOPICS a week.

Google login is keyless (see gsc_session); Claude uses the ANTHROPIC_API_KEY secret.
Without data (a new site) it only writes the report. Off switch: data/PAUSE_DOCTOR.
Never stops the site: every problem is printed and the robot ends normally.
"""
import datetime
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pages_check  # noqa: E402
import pages_write as w  # noqa: E402  (shares the Claude call, the budget and the episode helpers)

SITE = "https://learnwithian.com"
PREFIX_OF = {"en": "", "es": "es/", "pt": "pt/"}
PROPERTIES = ["sc-domain:learnwithian.com", "https://learnwithian.com/", "https://www.learnwithian.com/"]
REPORT = ROOT / "data" / "search_report.json"
PAUSE = ROOT / "data" / "PAUSE_DOCTOR"
MAX_FIXES = 3
MAX_NEW_TOPICS = 2
FIX_MIN_IMPRESSIONS, FIX_MAX_CTR, FIX_MAX_POSITION = 80, 0.01, 20
TOPIC_MIN_IMPRESSIONS = 15


def plain(s):
    """lowercase without accents, so "inglés" and "ingles" match"""
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def has_google_login():
    return bool(os.environ.get("GSC_SERVICE_ACCOUNT") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))


def gsc_session():
    """Keyless login: GitHub proves to Google that this is the learnwithian-site robot (Workload
    Identity Federation, set up 27 Nov 2026), and Google lets it act as search-doctor@learnwithian-search
    (read only in Search Console). A JSON key in GSC_SERVICE_ACCOUNT also works but is not used."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    if os.environ.get("GSC_SERVICE_ACCOUNT"):
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_info(json.loads(os.environ["GSC_SERVICE_ACCOUNT"]), scopes=SCOPES)
    else:
        creds, _ = google.auth.default(scopes=SCOPES)
    return AuthorizedSession(creds)


def query(sess, prop, dims, days=28, limit=1000):
    end = datetime.date.today() - datetime.timedelta(days=2)
    start = end - datetime.timedelta(days=days - 1)
    url = "https://searchconsole.googleapis.com/webmasters/v3/sites/%s/searchAnalytics/query" % requests_quote(prop)
    r = sess.post(url, json={"startDate": start.isoformat(), "endDate": end.isoformat(), "dimensions": dims, "rowLimit": limit})
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code} {r.text[:200]}")
    return r.json().get("rows", [])


def requests_quote(s):
    from urllib.parse import quote
    return quote(s, safe="")


def find_property(sess):
    for p in PROPERTIES:
        try:
            query(sess, p, ["page"], days=7, limit=1)
            return p
        except Exception as e:
            print(f"doctor: property {p} not usable: {str(e)[:120]}")
    raise RuntimeError("no Search Console property is shared with the robot")


def page_of_url(pages, url):
    for t in pages:
        for l in ("en", "es", "pt"):
            if t.get(l) and url.rstrip("/").endswith(f"{PREFIX_OF[l]}play/{t[l]['slug']}.html"):
                return t, l
    return None, None


def better_title(budget, t, l, rows):
    d = t[l]
    qs = ", ".join(f"\"{r['keys'][1]}\" ({int(r['impressions'])} views)" for r in rows[:8])
    prompt = f"""This free activity page is seen in Google but almost nobody clicks it.
Language: {l}. Current title: {d['title']}
Current description: {d['desc']}
Real searches that show this page: {qs}
Write a better title and description that answer those searches honestly (same activity, nothing new promised).
Title at most 95 characters and ending with " | Learn with Ian". Description 140-170 characters, says it is free and says ages 2 to 6 (es "2 a 6 años", pt "2 a 6 anos").
Return JSON: {{"title": "...", "desc": "..."}}"""
    ans = w.parse_json(w.ask_claude(budget, w.RULES, prompt))
    return w.clean(ans.get("title", "")), w.clean(ans.get("desc", ""))


def new_topic(budget, q, plan, pages):
    eps = w.site_episodes()
    used = sorted({t["phrases"]["en"] for t in plan if t.get("phrases")})
    prompt = f"""Parents or teachers found our site in Google with this search: "{q}".
We have no page made for it. If a free 15-minute activity from one of our episodes would truly answer it,
propose ONE topic. Episodes on the site (slugs): {eps}
Phrases already used (do not repeat): {used}
If no episode fits honestly, return {{"skip": true}}.
Otherwise return JSON: {{"episode": "<slug from the list>", "idea": "<1-2 sentences>", "phrases": {{"en": "...", "es": "...", "pt": "..."}}, "slugs": {{"en": "...", "es": "...", "pt": "..."}}}}
The English phrase should be close to the search. Slugs lowercase a-z 0-9 and hyphens."""
    return w.parse_json(w.ask_claude(budget, w.RULES, prompt))


def main():
    if PAUSE.exists():
        print("doctor: paused (data/PAUSE_DOCTOR exists)")
        return
    if not has_google_login():
        print("doctor: no Google login yet, nothing to do")
        return
    sess = gsc_session()
    prop = find_property(sess)
    by_page = query(sess, prop, ["page"])
    by_pq = query(sess, prop, ["page", "query"], limit=5000)
    by_q = query(sess, prop, ["query"], limit=1000)
    today = w.today().isoformat()
    report = {"date": today, "property": prop, "totals": {
        "clicks": int(sum(r["clicks"] for r in by_page)), "impressions": int(sum(r["impressions"] for r in by_page))},
        "pages": [{"url": r["keys"][0], "clicks": int(r["clicks"]), "impressions": int(r["impressions"]),
                   "ctr": round(r["ctr"], 4), "position": round(r["position"], 1)} for r in sorted(by_page, key=lambda r: -r["impressions"])][:200],
        "top_searches": [{"query": r["keys"][0], "clicks": int(r["clicks"]), "impressions": int(r["impressions"]),
                          "position": round(r["position"], 1)} for r in sorted(by_q, key=lambda r: -r["impressions"])][:100],
        "fixed": [], "new_topics": [], "notes": []}
    print(f"doctor: {prop}: {report['totals']['impressions']} impressions, {report['totals']['clicks']} clicks in 28 days")

    key = os.environ.get("ANTHROPIC_API_KEY")
    budget = w.Budget()
    pages = w.load(w.PAGES, [])
    plan_doc = w.load(w.PLAN, {"topics": []})
    plan = plan_doc["topics"]

    # 2) fix titles of activity pages that are seen but not clicked
    if key:
        fixes = 0
        for r in sorted(by_page, key=lambda r: -r["impressions"]):
            if fixes >= MAX_FIXES or not budget.can_call():
                break
            if r["impressions"] < FIX_MIN_IMPRESSIONS or r["ctr"] > FIX_MAX_CTR or r["position"] > FIX_MAX_POSITION:
                continue
            t, l = page_of_url(pages, r["keys"][0])
            if not t or t[l].get("title_fixed", "") > (w.today() - datetime.timedelta(days=28)).isoformat():
                continue
            rows = sorted([x for x in by_pq if x["keys"][0] == r["keys"][0]], key=lambda x: -x["impressions"])
            try:
                title, desc = better_title(budget, t, l, rows)
                old = dict(t[l])
                t[l]["title"], t[l]["desc"] = title, desc
                problems = [p for p in pages_check.check_topic(t, pages) if p.startswith(l)]
                if len(title) > 100 or not 100 <= len(desc) <= 200:
                    problems.append("length")
                if problems:
                    t[l].update({k: old[k] for k in ("title", "desc")})
                    report["notes"].append(f"title fix for {r['keys'][0]} rejected: {problems[:3]}")
                    continue
                t[l]["title_fixed"] = today
                t[l].setdefault("title_history", []).append({"date": today, "old": old["title"], "impressions": int(r["impressions"]), "ctr": round(r["ctr"], 4)})
                fixes += 1
                report["fixed"].append({"url": r["keys"][0], "old": old["title"], "new": title})
                print(f"doctor: new title for {r['keys'][0]}: {title}")
            except Exception as e:
                report["notes"].append(f"title fix for {r['keys'][0]} failed: {str(e)[:150]}")
        w.save(w.PAGES, pages)

    # 3) real searches without their own page -> new topics for the writer
    if key:
        known = plain(" ".join([v for t in plan if t.get("phrases") for v in t["phrases"].values()] +
                               [t[l]["title"] for t in pages for l in ("en", "es", "pt") if t.get(l)]))
        # searches where one of our pages already shows on the first two Google pages
        ranked = {plain(x["keys"][1]) for x in by_pq if x["position"] <= 20 and ("/play/" in x["keys"][0] or "/ep/" in x["keys"][0])}
        added = 0
        for r in sorted(by_q, key=lambda r: -r["impressions"]):
            if added >= MAX_NEW_TOPICS or not budget.can_call():
                break
            q = r["keys"][0].lower().strip()
            if r["impressions"] < TOPIC_MIN_IMPRESSIONS or "learn with ian" in q or "ian" == q or len(q.split()) < 3:
                continue
            if plain(q) in ranked:
                continue  # we already have a page that shows for it
            if all(word in known for word in re.findall(r"[a-z]+", plain(q)) if len(word) > 3):
                continue  # already covered by an existing phrase
            try:
                ans = new_topic(budget, q, plan, pages)
                if ans.get("skip"):
                    continue
                slugs = {l: ans["slugs"][l] for l in ("en", "es", "pt")}
                used = {t.get("slugs", {}).get(l) for t in plan for l in ("en", "es", "pt")} | {t[l]["slug"] for t in pages for l in ("en", "es", "pt") if t.get(l)}
                if ans.get("episode") not in w.site_episodes() or not all(w.slug_ok(s) and s not in used for s in slugs.values()):
                    report["notes"].append(f"topic for '{q}' rejected")
                    continue
                plan.append({"id": slugs["en"], "episode": ans["episode"], "idea": ans["idea"].strip(), "slugs": slugs,
                             "phrases": {l: ans["phrases"][l].strip() for l in ("en", "es", "pt")},
                             "added_by": "doctor", "added": today, "from_search": q})
                known += " " + plain(" ".join(ans["phrases"].values()))
                added += 1
                report["new_topics"].append({"search": q, "topic": slugs["en"]})
                print(f"doctor: new topic from search '{q}': {slugs['en']}")
            except Exception as e:
                report["notes"].append(f"topic for '{q}' failed: {str(e)[:150]}")
        w.save(w.PLAN, plan_doc)

    report["spent_this_month_usd"] = budget.spent()
    w.save(REPORT, report)
    print(f"doctor: done. fixed {len(report['fixed'])} titles, added {len(report['new_topics'])} topics")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"doctor: stopped with a problem: {e}")
