"""Guardian: every morning checks that the whole Learn with Ian system still works.

It only LOOKS, it never changes the site. When something is wrong it opens one GitHub Issue
(assigned to the owner, so GitHub emails him), adds a comment when a NEW problem appears, and
closes the issue by itself when everything is fine again. When all is fine it stays silent.

Checks:
1. The website and its main pages open.
2. The three site robots (update, pages writer, Search Doctor) ran and succeeded recently.
3. The YouTube feed was read successfully in the last day (data/feed_status.json, written by update.py).
4. The pages writer: ran recently, no Claude API errors (empty key credit), monthly budget not near the cap.
5. Pinterest feeds get new pictures (English lane daily, Spanish/Portuguese lane every day or two).
6. Every episode page on the site has its Spanish and Portuguese pages and its free games (after 2 days).
"""
import datetime
import email.utils
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://learnwithian.com"
REPO = os.environ.get("GITHUB_REPOSITORY", "mahibrahim89-wq/learnwithian-site")
OWNER = REPO.split("/")[0]
TOKEN = os.environ.get("GITHUB_TOKEN", "")
TITLE = "🚨 الحارس: فيه مشكلة في السيستم"
UA = {"User-Agent": "learnwithian-guardian"}
NOW = datetime.datetime.now(datetime.timezone.utc)
TODAY_DUBAI = (NOW + datetime.timedelta(hours=4)).date()

ROBOTS = [  # workflow file, Arabic name, max hours since last successful run
    ("update.yml", "روبوت تحديث الموقع", 9),
    ("pages.yml", "روبوت كاتب الصفحات", 30),
    ("search.yml", "دكتور البحث", 8 * 24 + 6),
    ("translations.yml", "سفير اللغات", 30),
    ("scout.yml", "الكشّاف", 8 * 24 + 6),
    ("planner.yml", "مخطّط الحلقات", 30),
]
PAGES = ["/", "/free.html", "/episodes.html", "/sitemap.xml", "/es/", "/pt/", "/play/color-hunt-game.html"]
ENGLISH_BOARDS = ["christmas", "winter", "basics", "zoo-garden", "videos"]
LANG_BOARDS = ["es-ingles", "es-videos", "pt-ingles", "pt-videos"]

problems = []  # (key, Arabic text)


def add(key, text):
    problems.append((key, text))


def http(url, data=None, method=None, api=False):
    headers = dict(UA)
    if api:
        headers.update({"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"})
    if data is not None:
        data = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.status, r.read()


def gh(path, data=None, method=None):
    status, body = http("https://api.github.com/repos/" + REPO + path, data, method, api=True)
    return json.loads(body or b"null")


# ---------- checks ----------

def check_site():
    for p in PAGES:
        try:
            status, body = http(SITE + p)
            if status != 200 or len(body) < 1000:
                add("site" + p, f"صفحة الموقع {SITE}{p} بترجع رد غريب (كود {status}، حجم {len(body)}).")
        except Exception as e:
            add("site" + p, f"صفحة الموقع {SITE}{p} مش بتفتح ({str(e)[:80]}).")


def check_robots():
    for wf, name, hours in ROBOTS:
        try:
            runs = gh(f"/actions/workflows/{wf}/runs?per_page=10").get("workflow_runs", [])
        except Exception as e:
            add("robot-" + wf, f"مش قادر أشوف حالة {name} ({str(e)[:80]}).")
            continue
        done = [r for r in runs if r.get("status") == "completed"]
        if not done:
            continue  # new robot, never ran yet
        last = done[0]
        if last.get("conclusion") != "success":
            add("robot-" + wf, f"{name} آخر تشغيل ليه فشل ({last.get('conclusion')}). التفاصيل: {last.get('html_url')}")
        ok = [r for r in done if r.get("conclusion") == "success"]
        if ok:
            t = datetime.datetime.fromisoformat(ok[0]["updated_at"].replace("Z", "+00:00"))
            age = (NOW - t).total_seconds() / 3600
            if age > hours:
                add("late-" + wf, f"{name} مانجحش من {int(age)} ساعة (المفروض كل {hours} ساعة بالكتير).")


def check_youtube_feed():
    st = json.loads((ROOT / "data" / "feed_status.json").read_text()) if (ROOT / "data" / "feed_status.json").exists() else {}
    last = st.get("youtube_feed_ok")
    if not last:
        return  # not written yet (first days)
    days = (TODAY_DUBAI - datetime.date.fromisoformat(last)).days
    if days >= 2:
        add("youtube-feed", f"روبوت الموقع مش قادر يقرا قناة يوتيوب من {days} يوم (آخر مرة نجح: {last}). الموقع شغّال بآخر بيانات، بس الحلقات الجديدة مش هتظهر لحد ما يرجع.")


def check_writer():
    log_p = ROOT / "data" / "writer_log.json"
    if (ROOT / "data" / "PAUSE_WRITER").exists() or not log_p.exists():
        return
    log = json.loads(log_p.read_text())
    runs = log.get("runs", [])
    if runs:
        last = datetime.date.fromisoformat(runs[-1]["date"])
        if (TODAY_DUBAI - last).days >= 3:
            add("writer-late", f"كاتب الصفحات ماكتبش في الدفتر من {(TODAY_DUBAI - last).days} أيام.")
        errs = [s for r in runs[-3:] for s in r.get("skipped", []) for w in s.get("why", []) if "API error" in w or "credit" in w.lower()]
        if errs:
            add("writer-key", "كاتب الصفحات مش قادر يكلّم Claude (غالبًا رصيد مفتاح Anthropic خلص أو المفتاح اتلغى). افتح Anthropic Console وشوف الرصيد.")
    month = TODAY_DUBAI.strftime("%Y-%m")
    usd = log.get("months", {}).get(month, {}).get("usd", 0)
    if usd >= 25:  # no cap in the code since 27 Nov; this is only a heads-up, nothing stops
        add("writer-budget", f"للعلم بس: صرف الروبوتات على مفتاح Anthropic الشهر ده وصل حوالي ${usd:.2f}. مفيش حاجة وقفت.")


def newest(board):
    p = ROOT / ("activities.xml" if board == "general" else f"pins-{board}.xml")
    if not p.exists():
        return None
    ds = [email.utils.parsedate_to_datetime(d).date() for d in re.findall(r"<pubDate>([^<]+)", p.read_text())]
    return max(ds) if ds else None


def check_pinterest():
    en = [d for d in (newest(b) for b in ENGLISH_BOARDS) if d]
    if en and (TODAY_DUBAI - max(en)).days >= 3:
        add("pins-en", f"مفيش صور Pinterest إنجليزي جديدة من {max(en)}. مهمة الألعاب و Pinterest ممكن تكون وقفت، أو الجدول خلص.")
    la = [d for d in (newest(b) for b in LANG_BOARDS) if d]
    if la and (TODAY_DUBAI - max(la)).days >= 4:
        add("pins-lang", f"مفيش صور Pinterest إسباني أو برتغالي جديدة من {max(la)}. الجدول ممكن يكون خلص.")


def added_days_ago(path):
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%ct", "--", path], cwd=ROOT,
                             capture_output=True, text=True, timeout=30).stdout.split()
        if out:
            t = datetime.datetime.fromtimestamp(int(out[-1]), datetime.timezone.utc)
            return (NOW - t).days
    except Exception:
        pass
    return 0


def check_episodes():
    for p in sorted((ROOT / "ep").glob("*.html")):
        slug = p.stem
        if added_days_ago(f"ep/{slug}.html") < 2:
            continue  # a new episode gets 2 days to get everything
        missing = []
        if not (ROOT / "es" / "ep" / f"{slug}.html").exists():
            missing.append("الصفحة الإسباني")
        if not (ROOT / "pt" / "ep" / f"{slug}.html").exists():
            missing.append("الصفحة البرتغالي")
        if not (ROOT / "img" / "activities" / f"{slug}-story.png").exists():
            missing.append("الألعاب المجانية")
        if missing:
            add("ep-" + slug, f"حلقة {slug} على الموقع من أكتر من يومين وناقصها: {'، '.join(missing)}. (المهام المجدولة في Claude ممكن تكون وقفت.)")


def check_translations():
    p = ROOT / "data" / "youtube_es_pt.json"
    if not p.exists() or (ROOT / "data" / "PAUSE_TRANSLATIONS").exists():
        return
    eps = json.loads(p.read_text()).get("episodes", {})
    have = {e.get("slug") for e in eps.values()}
    for f in sorted((ROOT / "ep").glob("*.html")):
        if f.stem not in have and added_days_ago(f"ep/{f.stem}.html") >= 3 and (ROOT / "es" / "ep" / f.name).exists():
            add("tr-" + f.stem, f"حلقة {f.stem} لسه مالهاش عنوان ووصف بالإسباني والبرتغالي (روبوت سفير اللغات ماكتبهمش).")
    for yid, e in eps.items():
        if e.get("status") == "ready" and e.get("added") and (TODAY_DUBAI - datetime.date.fromisoformat(e["added"])).days >= 9:
            add("tr-paste-" + yid, f"ترجمة حلقة {e.get('slug')} جاهزة من {e['added']} ولسه ماتلصقتش في يوتيوب ستوديو (جلسة السبت ماعملتهاش).")


def check_links():
    p = ROOT / "data" / "weave_report.json"
    if not p.exists() or (ROOT / "data" / "PAUSE_WEAVER").exists():
        return
    r = json.loads(p.read_text())
    if r.get("orphans"):
        add("weave-orphans", "صفحات مفيش لينك يوصّل ليها من الرئيسية (جوجل مش هيديها أهمية): " + "، ".join(r["orphans"][:5])
            + (f" و{len(r['orphans']) - 5} تانيين" if len(r["orphans"]) > 5 else "") + ". روبوت النسّاج ماربطهاش.")
    if r.get("broken"):
        add("weave-broken", "لينكات مكسورة جوه الموقع: " + "، ".join(r["broken"][:5])
            + (f" و{len(r['broken']) - 5} تانيين" if len(r["broken"]) > 5 else "") + ".")


def check_scout():
    p = ROOT / "data" / "scout_report.json"
    if not p.exists() or (ROOT / "data" / "PAUSE_SCOUT").exists():
        return
    r = json.loads(p.read_text())
    if not r.get("suggestions"):
        add("scout-blind", f"الكشّاف ماقدرش يقرا اقتراحات البحث في آخر تشغيل ({r.get('date')}): خدمات الاقتراحات ماردّتش.")

def page_price(html):
    """The price a product page tells machines about (JSON-LD or meta tags), as 'USD 3.99'. None if it tells nothing."""
    cur = None
    m = re.search(r'"priceCurrency"\s*:\s*"([A-Z]{3})"', html) or re.search(r'property="(?:product|og):price:currency"\s+content="([A-Z]{3})"', html) \
        or re.search(r'itemprop="priceCurrency"\s+content="([A-Z]{3})"', html)
    if m:
        cur = m.group(1)
    for pat in (r'"price"\s*:\s*"?(\d+(?:\.\d{1,2})?)"?', r'property="(?:product|og):price:amount"\s+content="(\d+(?:\.\d{1,2})?)"',
                r'itemprop="price"\s+content="(\d+(?:\.\d{1,2})?)"', r'"lowPrice"\s*:\s*"?(\d+(?:\.\d{1,2})?)"?'):
        m = re.search(pat, html)
        if m:
            return f"{cur or '?'} {float(m.group(1)):.2f}"
    return None


def check_stores():
    """Every product link on the shop page still opens (this used to be the shop bot's store review).
    Only a clear "gone" answer (404 or 410) counts. Stores that refuse robots (403, 429, 5xx) are skipped."""
    if (ROOT / "data" / "PAUSE_STORES").exists():
        return
    links = {}

    def walk(o, name=""):
        if isinstance(o, dict):
            name = o.get("name") or name
            if o.get("url") and o.get("store"):
                # same fix link_pages.py makes on the live pages (the Gumroad shop moved)
                u = o["url"].replace("https://mahibrahim.gumroad.com/", "https://learnwithian.gumroad.com/")
                links.setdefault(u, (o["store"], name))
            for v in o.values():
                walk(v, name)
        elif isinstance(o, list):
            for v in o:
                walk(v, name)

    walk(json.loads((ROOT / "data" / "shop.json").read_text()))
    dead, skipped, refused, prices = [], 0, {}, {}
    for url, (store, name) in sorted(links.items()):
        try:
            _, body = http(url)
            pr = page_price(body.decode("utf-8", "replace"))
            if pr:
                prices[url] = pr
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                dead.append((url, store, name))
            else:
                skipped += 1
                refused[store] = refused.get(store, []) + [e.code]
        except Exception as e:
            skipped += 1
            refused[store] = refused.get(store, []) + [type(e).__name__]
    print(f"guardian: stores: {len(links)} links, {len(dead)} dead, {skipped} could not be checked")
    for store, codes in sorted(refused.items()):
        print(f"guardian: stores: not checked: {store} x{len(codes)} ({sorted(set(map(str, codes)))})")
    # Prices: compare with the agreed list in data/store_prices.json (written by Claude, changed only on Mahmoud's word).
    # A page that shows no price today is not a problem (it may be a blocked or changed page): only a DIFFERENT price is.
    bp = ROOT / "data" / "store_prices.json"
    base = json.loads(bp.read_text()).get("prices", {}) if bp.exists() else {}
    for url, pr in sorted(prices.items()):
        store, name = links[url]
        print(f"guardian: stores: price {pr} | {store} | {name} | {url}")
        want = base.get(url)  # one price, or a list while a price change we asked for is on its way
        if isinstance(want, list):
            if pr in want:
                continue
            want = want[-1]
        if want and want != pr:
            add("store-price-" + re.sub(r"[^a-z0-9]+", "-", url.lower())[-50:],
                f"سعر اتغيّر على {store} ({name or 'منتج'}): كان {want} يوم ما اتسجّل، والمعروض دلوقتي {pr}. {url} . لو التغيير مقصود قول لـ Claude يحدّث القايمة.")
    print(f"guardian: stores: prices read {len(prices)}, in the agreed list {len(base)}")
    by_store, totals = {}, {}
    for url, store, name in dead:
        by_store.setdefault(store, []).append(url)
    for store, _ in links.values():
        totals[store] = totals.get(store, 0) + 1
    for store, urls in by_store.items():
        if len(urls) >= 3 and len(urls) == totals[store]:  # the whole store, not one product
            add("store-down-" + store.lower(), f"كل لينكات {store} ({len(urls)}) ردّت على الحارس بـ\"مش موجود\". يا المتجر واقف، يا المتجر بيرفض الروبوتات. افتح لينك واحد من موبايلك وقول لـ Claude النتيجة.")
            dead = [d for d in dead if d[1] != store]
    for url, store, name in dead:
        add("store-dead-" + re.sub(r"[^a-z0-9]+", "-", url.lower())[-50:],
            f"لينك منتج مش بيفتح على {store} ({name or 'منتج'}): {url} . المنتج اتشال أو اللينك اتغيّر، والزائر هيلاقي صفحة فاضية.")


def check_program():
    p = ROOT / "data" / "program_status.json"
    if not p.exists() or (ROOT / "data" / "PAUSE_PLANNER").exists():
        return
    for x in json.loads(p.read_text()).get("problems", []):
        add("program-" + x["key"], "المنهج: " + x["text"])

# ---------- the issue ----------

def body_text():
    lines = [f"الحارس لقى المشاكل دي يوم {TODAY_DUBAI} (الصبح بتوقيت دبي):", ""]
    lines += [f"- {t}" for _, t in problems]
    lines += ["", "مش لازم تعمل حاجة بنفسك: ابعت لـ Claude \"شوف تذكرة الحارس\" وهو يتصرف.",
              "التذكرة دي بتتقفل لوحدها لما كل حاجة ترجع تشتغل.", "", "<!-- keys: " + ",".join(sorted(k for k, _ in problems)) + " -->"]
    return "\n".join(lines)


def main():
    for check in (check_site, check_robots, check_youtube_feed, check_writer, check_pinterest, check_episodes, check_translations, check_links, check_scout, check_program, check_stores):
        try:
            check()
        except Exception as e:
            add("guardian-" + check.__name__, f"الحارس نفسه ماقدرش يعمل فحص {check.__name__} ({str(e)[:80]}).")
    print(f"guardian: {len(problems)} problem(s)")
    for k, t in problems:
        print(" -", k, t)
    if not TOKEN:
        print("guardian: no GITHUB_TOKEN, not touching issues")
        return
    open_issues = [i for i in gh("/issues?state=open&per_page=50") if i.get("title") == TITLE and "pull_request" not in i]
    issue = open_issues[0] if open_issues else None
    if problems:
        keys = set(k for k, _ in problems)
        if not issue:
            new = gh("/issues", {"title": TITLE, "body": body_text(), "assignees": [OWNER]}, "POST")
            print("guardian: opened issue", new.get("html_url"))
        else:
            old_keys = set((re.search(r"<!-- keys: (.*?) -->", issue.get("body") or "") or [None, ""])[1].split(","))
            gh(f"/issues/{issue['number']}", {"body": body_text()}, "PATCH")
            fresh = keys - old_keys
            if fresh:  # a comment makes GitHub email the owner again
                gh(f"/issues/{issue['number']}/comments", {"body": "مشكلة جديدة:\n" + "\n".join(f"- {t}" for k, t in problems if k in fresh)}, "POST")
            print("guardian: updated issue", issue.get("html_url"))
    elif issue:
        gh(f"/issues/{issue['number']}/comments", {"body": f"✅ كل حاجة رجعت تشتغل ({TODAY_DUBAI}). الحارس قفل التذكرة."}, "POST")
        gh(f"/issues/{issue['number']}", {"state": "closed"}, "PATCH")
        print("guardian: all good, closed issue")
    else:
        print("guardian: all good")


if __name__ == "__main__":
    main()
