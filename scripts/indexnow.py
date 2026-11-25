"""Tell Bing (and the other IndexNow search engines) about new pages right away.

Runs after the pages are built. Sends every page that was never sent before,
and the whole sitemap once a week. Never stops the site update if it fails.
"""
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = "learnwithian.com"
KEY = "da6f404a5828b19c82e9974c597847ee"
STATE = ROOT / "data" / "indexnow.json"
WEEK = 7 * 24 * 3600


def main():
    sm = ROOT / "sitemap.xml"
    if not sm.exists():
        print("IndexNow: no sitemap")
        return
    urls = re.findall(r"<loc>([^<]+)</loc>", sm.read_text())
    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError):
        state = {"sent": [], "full": 0}
    now = int(time.time())
    weekly = now - int(state.get("full", 0)) > WEEK
    sent = set(state.get("sent", []))
    todo = urls if weekly else [u for u in urls if u not in sent]
    if not todo:
        print("IndexNow: nothing new")
        return
    body = {"host": HOST, "key": KEY, "keyLocation": f"https://{HOST}/{KEY}.txt", "urlList": todo[:10000]}
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
        print("IndexNow answer:", e.read()[:300])
    except Exception as e:  # network problem: try again next run
        print("IndexNow not reached:", e)
        return
    print(f"IndexNow: sent {len(todo)} pages, status {status}")
    if status in (200, 202):
        state = {"sent": sorted(sent | set(todo)), "full": now if weekly else state.get("full", 0)}
        STATE.write_text(json.dumps(state, indent=1) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("IndexNow skipped:", e)
