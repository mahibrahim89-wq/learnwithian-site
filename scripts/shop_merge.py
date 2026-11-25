"""Keep the hand-written episodes (1 to 4) in data/shop.json up to date.

Runs before update.py (same workflow). update.py reads the store links from
each video description, but for the first episodes it uses the products
written by hand in data/shop.json. This adds to them, automatically:
  * any new store link found in that episode's YouTube description,
  * the Etsy listings below (until the shop bot puts them in the descriptions),
  * Etsy and TPT in the "All stores" list.
It only adds links; it never removes or changes a product. Safe to run many times.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import update  # noqa: E402

EXTRA = {  # product id -> (store, url)
    "zoo-coloring-book": ("Etsy", "https://www.etsy.com/listing/4624384671"),
    "zoo-counting": ("Etsy", "https://www.etsy.com/listing/4623911018"),
    "plant-life-cycle": ("Etsy", "https://www.etsy.com/listing/4624385213"),
    "shape-hunt-pages": ("Etsy", "https://www.etsy.com/listing/4623910028"),
    "number-walk-pages": ("Etsy", "https://www.etsy.com/listing/4623901905"),
}
STORES = [
    {"name": "Etsy", "what": "Printable activity packs", "url": "https://www.etsy.com/shop/LearnWithIanShop"},
    {"name": "TPT", "what": "For teachers: free and classroom packs", "url": "https://www.teacherspayteachers.com/store/learn-with-ian"},
]


def norm(s):
    return "".join(c for c in s.lower() if c.isalnum())


def main():
    path = ROOT / "data" / "shop.json"
    shop = json.loads(path.read_text())
    seen = {}
    p = ROOT / "data" / "episodes.json"
    for v in (json.loads(p.read_text()) if p.exists() else []):
        seen[v["id"]] = v
    known = {s["url"] for s in shop["stores"]}
    for g in shop["general"] + [shop.get("bundle") or {"links": []}]:
        known |= {l["url"] for l in g["links"]}
    for ep in shop["episodes"].values():
        for prod in ep["products"]:
            known |= {l["url"] for l in prod["links"]}
    added = 0
    for vid, ep in shop["episodes"].items():
        prods = ep["products"]
        for prod in prods:
            if prod["id"] in EXTRA:
                store, url = EXTRA[prod["id"]]
                if url not in known:
                    prod["links"].append({"format": "printable", "store": store, "url": url})
                    known.add(url)
                    added += 1
        new = [l for l in (seen.get(vid) or {}).get("links", []) if l["url"] not in known]
        for np in update.group_products(new, f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"):
            match = next((x for x in prods if norm(x["name"]) in norm(np["name"]) or norm(np["name"]) in norm(x["name"])), None)
            if match:
                match["links"].extend(np["links"])
            else:
                prods.append(np)
            known |= {l["url"] for l in np["links"]}
            added += len(np["links"])
    names = {s["name"] for s in shop["stores"]}
    for s in STORES:
        if s["name"] not in names:
            shop["stores"].append(s)
            added += 1
    if added:
        path.write_text(json.dumps(shop, indent=1, ensure_ascii=False) + "\n")
    print("shop links added:", added)


if __name__ == "__main__":
    main()
