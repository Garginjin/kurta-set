#!/usr/bin/env python3
"""
Fashion listing scraper -> one normalized CSV/JSON.

Sites supported:
  - Shopify stores (Jaipur Handblock, Label Kanupriya): uses the public
    /collections/<handle>/products.json feed (all sizes, prices, stock, images).
  - Zlaata (custom site): parses server-rendered category pages (?page=N).

Usage:
  pip install requests beautifulsoup4
  python scraper.py                       # scrape everything -> docs/listings.json
  python scraper.py --category kurta_set  # only one category (others kept)
  python scraper.py --renormalise         # re-apply colour mapping, no scraping

Polite by default: checks robots.txt, 1.5s delay between requests,
identifies itself with a plain User-Agent.
"""
import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; FashionAggregatorBot/0.1)"
DELAY_SEC = 1.5
TIMEOUT = 30

# ---------------------------------------------------------------------------
# CONFIG: which listings to pull for which normalized category.
#   type "shopify": base + collection handle ("all" = whole store).
#                   Optional keyword filter on title/product_type/tags.
#   type "zlaata":  category listing URL.
# Add categories/collections here as you find them on each site.
# ---------------------------------------------------------------------------
SITES = {
    "kurta_set": [
        {"source": "Jaipur Handblock", "type": "shopify",
         "base": "https://jaipurhandblock.in", "collection": "3pc-suit"},
        {"source": "Label Kanupriya", "type": "shopify",
         "base": "https://www.labelkanupriya.com", "collection": "all",
         "keywords": ["kurta set", "kurta-set", "suit set", "kurta with"]},
        {"source": "Zlaata", "type": "zlaata",
         "url": "https://www.zlaata.com/zlaata-india/kurta-set"},
    ],
    "co_ord_set": [
        {"source": "Jaipur Handblock", "type": "shopify",
         "base": "https://jaipurhandblock.in", "collection": "co-ord-sets"},
        {"source": "Zlaata", "type": "zlaata",
         "url": "https://www.zlaata.com/zlaata-india/co-ords"},
    ],
    "kurta": [
        {"source": "Jaipur Handblock", "type": "shopify",
         "base": "https://jaipurhandblock.in", "collection": "kurtas"},
        {"source": "Zlaata", "type": "zlaata",
         "url": "https://www.zlaata.com/zlaata-india/kurtas-kurtis"},
    ],
}

FIELDS = ["source", "category", "product_id", "title", "brand", "url",
          "price", "mrp", "discount_pct", "sizes_available", "sizes_all",
          "colour", "colour_raw", "in_stock", "image", "tags", "scraped_at"]


def is_size_option(name):
    return "size" in name


def is_colour_option(name):
    return "colo" in name  # color / colour / Select Colour ...


# ---------------------------------------------------------------------------
# Colour normalisation: every brand's colour words -> one short list.
# Edit COLOUR_WORDS to add new words you see in the data.
# ---------------------------------------------------------------------------
COLOUR_WORDS = {
    "Black": ["black", "charcoal", "jet"],
    "White": ["white", "off-white", "off white", "ivory", "pearl"],
    "Beige": ["beige", "cream", "ecru", "nude", "sand", "khaki", "tan", "camel", "fawn"],
    "Brown": ["brown", "walnut", "coffee", "chocolate", "mocha", "rust", "copper"],
    "Red": ["red", "scarlet", "cherry", "crimson", "tomato"],
    "Maroon": ["maroon", "wine", "burgundy", "oxblood"],
    "Pink": ["pink", "rani", "rose", "blush", "coral", "fuchsia", "magenta", "salmon"],
    "Orange": ["orange", "peach", "tangerine", "apricot"],
    "Yellow": ["yellow", "mustard", "lemon", "haldi", "ochre"],
    "Green": ["green", "sage", "mint", "olive", "jade", "emerald", "pista",
              "pistachio", "mehendi", "lime", "bottle green"],
    "Blue": ["blue", "navy", "indigo", "aqua", "turquoise", "teal", "sky",
             "cobalt", "denim", "firozi", "jade blue"],
    "Purple": ["purple", "lavender", "lilac", "jamuni", "violet", "mauve",
               "plum", "grape", "grapewine", "orchid", "onion"],
    "Grey": ["grey", "gray", "silver", "ash", "steel"],
    "Gold": ["gold", "golden"],
    "Multicolour": ["multicolor", "multicolour", "multi-color", "multi colour",
                    "multi-colour", "multi color", "multi"],
}
# "onion pink" should be Pink, not Purple: longer phrases win at the same spot
COLOUR_WORDS["Pink"] += ["onion pink", "dusty pink", "hot pink", "baby pink"]
_COLOUR_PATTERNS = sorted(
    ((w, c) for c, ws in COLOUR_WORDS.items() for w in ws),
    key=lambda x: -len(x[0]))


def normalise_colour(text):
    """Return the canonical colour for the earliest colour word in text."""
    if not text:
        return ""
    t = text.lower()
    best = None  # (start, -len, colour)
    for word, colour in _COLOUR_PATTERNS:
        for m in re.finditer(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", t):
            cand = (m.start(), -len(word), colour)
            if best is None or cand < best:
                best = cand
    return best[2] if best else ""


def colour_for(raw_option, title):
    return normalise_colour(raw_option) or normalise_colour(title) or "Other"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
class Fetcher:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self.robots = {}
        self.last = 0.0

    def allowed(self, url):
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self.robots:
            rp = robotparser.RobotFileParser()
            try:
                r = self.s.get(root + "/robots.txt", timeout=TIMEOUT)
                rp.parse(r.text.splitlines() if r.ok else [])
            except requests.RequestException:
                rp.parse([])
            self.robots[root] = rp
        return self.robots[root].can_fetch(USER_AGENT, url)

    def get(self, url, **kw):
        if not self.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        wait = DELAY_SEC - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            try:
                r = self.s.get(url, timeout=TIMEOUT, **kw)
                self.last = time.time()
                if r.status_code == 429:
                    time.sleep(10 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                if attempt == 2:
                    raise
                print(f"  retry {attempt + 1} for {url}: {e}", file=sys.stderr)
                time.sleep(3 * (attempt + 1))
        raise RuntimeError(f"failed: {url}")


def to_num(x):
    if x in (None, ""):
        return None
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return None


def disc(price, mrp):
    if price and mrp and mrp > price:
        return round((mrp - price) / mrp * 100)
    return 0


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Shopify
# ---------------------------------------------------------------------------
def parse_shopify_product(p, base, source, category):
    opts = [o.get("name", "").strip().lower() for o in p.get("options", [])]
    size_idx = next((i for i, n in enumerate(opts) if is_size_option(n)), None)
    col_idx = next((i for i, n in enumerate(opts) if is_colour_option(n)), None)

    variants = p.get("variants", [])
    prices = [to_num(v.get("price")) for v in variants if to_num(v.get("price"))]
    mrps = [to_num(v.get("compare_at_price")) for v in variants
            if to_num(v.get("compare_at_price"))]
    price = min(prices) if prices else None
    mrp = max(mrps) if mrps else price

    def opt(v, i):
        return v.get(f"option{i + 1}") if i is not None else None

    sizes_all, sizes_avail, colours = [], [], []
    for v in variants:
        s = opt(v, size_idx)
        if s and s not in sizes_all:
            sizes_all.append(s)
        if s and v.get("available") and s not in sizes_avail:
            sizes_avail.append(s)
        c = opt(v, col_idx)
        if c and c not in colours:
            colours.append(c)

    tags = p.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    imgs = p.get("images") or []
    return {
        "source": source,
        "category": category,
        "product_id": str(p.get("id")),
        "title": p.get("title", "").strip(),
        "brand": p.get("vendor") or source,
        "url": f"{base.rstrip('/')}/products/{p.get('handle')}",
        "price": price,
        "mrp": mrp,
        "discount_pct": disc(price, mrp),
        "sizes_available": "|".join(sizes_avail),
        "sizes_all": "|".join(sizes_all),
        "colour": colour_for(colours[0] if colours else "", p.get("title", "")),
        "colour_raw": "|".join(colours),
        "in_stock": any(v.get("available") for v in variants),
        "image": imgs[0]["src"] if imgs else "",
        "tags": "|".join(tags),
        "scraped_at": now(),
    }


def matches_keywords(p, keywords):
    if not keywords:
        return True
    tags = p.get("tags", [])
    if isinstance(tags, list):
        tags = " ".join(tags)
    hay = " ".join([p.get("title", ""), p.get("product_type", ""), tags]).lower()
    return any(k.lower() in hay for k in keywords)


def scrape_shopify(f, cfg, category):
    base, coll = cfg["base"], cfg["collection"]
    out, page = [], 1
    while True:
        url = f"{base.rstrip('/')}/collections/{coll}/products.json"
        r = f.get(url, params={"limit": 250, "page": page})
        products = r.json().get("products", [])
        if not products:
            break
        for p in products:
            if matches_keywords(p, cfg.get("keywords")):
                out.append(parse_shopify_product(p, base, cfg["source"], category))
        print(f"  page {page}: {len(products)} products")
        if len(products) < 250:
            break
        page += 1
    return out


# ---------------------------------------------------------------------------
# Zlaata (server-rendered HTML)
# Product links look like: /zlaata-india/<cat>/<slug>/<id>/select
# Price text looks like:   "₹1649 ₹3188 (48% OFF)"  or  "₹2299"
# Parsing is anchored on the link pattern, not CSS class names, so it
# survives most theme changes.
# ---------------------------------------------------------------------------
ZLAATA_LINK = re.compile(r"/zlaata-india/[^/]+/[^/]+/(\d+)/select/?$")
RUPEE = re.compile(r"₹\s*([\d,]+(?:\.\d+)?)")


def find_card(a):
    """Walk up from a product link to the smallest ancestor holding a ₹ price."""
    node = a
    for _ in range(6):
        if node.parent is None:
            break
        node = node.parent
        if "₹" in node.get_text(" ", strip=True):
            return node
    return a


def parse_zlaata_page(html, page_url, category):
    soup = BeautifulSoup(html, "html.parser")
    seen, items = set(), {}
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"])
        m = ZLAATA_LINK.search(urlparse(href).path)
        if not m:
            continue
        pid = m.group(1)
        card = find_card(a)
        rec = items.get(pid)
        if rec is None:
            rec = {"source": "Zlaata", "category": category, "product_id": pid,
                   "title": "", "brand": "Zlaata", "url": href, "price": None,
                   "mrp": None, "discount_pct": 0, "sizes_available": "",
                   "sizes_all": "", "colour": "", "colour_raw": "", "in_stock": True,
                   "image": "", "tags": "", "scraped_at": now()}
            items[pid] = rec
        # title: link text, else img alt, else title attr
        text = a.get_text(" ", strip=True)
        if text and "₹" not in text and len(text) > len(rec["title"]):
            rec["title"] = text
        img = (a.find("img") or card.find("img"))
        if img and not rec["image"]:
            src = img.get("data-src") or img.get("src") or ""
            if src and not src.startswith("data:"):
                rec["image"] = urljoin(page_url, src)
            if not rec["title"] and img.get("alt"):
                rec["title"] = img["alt"].strip()
        if rec["price"] is None and pid not in seen:
            nums = [to_num(n) for n in RUPEE.findall(card.get_text(" ", strip=True))]
            nums = [n for n in nums if n]
            if nums:
                rec["price"] = nums[0]
                rec["mrp"] = nums[1] if len(nums) > 1 and nums[1] > nums[0] else nums[0]
                rec["discount_pct"] = disc(rec["price"], rec["mrp"])
                seen.add(pid)
        ct = card.get_text(" ", strip=True).lower()
        if "sold out" in ct or "out of stock" in ct:
            rec["in_stock"] = False
    for rec in items.values():
        if not rec["title"]:  # fall back to slug
            slug = urlparse(rec["url"]).path.rstrip("/").split("/")[-3]
            rec["title"] = slug.replace("-", " ").title()
        rec["colour"] = colour_for("", rec["title"])
    return list(items.values())


def scrape_zlaata(f, cfg, category, max_pages=50):
    out, ids, page = [], set(), 1
    while page <= max_pages:
        r = f.get(cfg["url"], params={"page": page})
        items = parse_zlaata_page(r.text, r.url, category)
        new = [i for i in items if i["product_id"] not in ids]
        print(f"  page {page}: {len(new)} new products")
        if not new:
            break
        ids.update(i["product_id"] for i in new)
        out.extend(new)
        page += 1
    return out


# ---------------------------------------------------------------------------
def write_out(rows, out):
    rows = sorted(rows, key=lambda r: (r["category"], r["source"]))
    with open(out + ".csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(out + ".json", "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    by = {}
    for r in rows:
        by[(r["category"], r["source"])] = by.get((r["category"], r["source"]), 0) + 1
    print(f"\n{len(rows)} products -> {out}.csv / {out}.json")
    for (c, s), n in sorted(by.items()):
        print(f"  {c:12} {s:18} {n}")


def load_previous(out):
    try:
        with open(out + ".json", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", help=f"one of {list(SITES)}; default = all")
    ap.add_argument("--out", default="docs/listings",
                    help="output path without extension (default docs/listings)")
    ap.add_argument("--renormalise", action="store_true",
                    help="don't scrape; re-apply colour mapping to the existing file")
    args = ap.parse_args()
    previous = load_previous(args.out)

    if args.renormalise:
        for r in previous:
            raw = r.get("colour_raw")
            if raw is None:  # file from the first scraper version
                raw = r.get("colour", "")
            r["colour_raw"] = raw
            r["colour"] = colour_for(raw.split("|")[0] if raw else "", r["title"])
        write_out(previous, args.out)
        return

    cats = [args.category] if args.category else list(SITES)
    f = Fetcher()
    rows, failed = [], []
    for cat in cats:
        for cfg in SITES[cat]:
            print(f"[{cat}] {cfg['source']}")
            got = []
            try:
                if cfg["type"] == "shopify":
                    got = scrape_shopify(f, cfg, cat)
                elif cfg["type"] == "zlaata":
                    got = scrape_zlaata(f, cfg, cat)
            except Exception as e:  # keep going if one site fails
                print(f"  FAILED: {e}", file=sys.stderr)
            if not got:
                # Site failed or returned nothing: keep its last good data
                # so the website never suddenly loses a whole brand.
                old = [r for r in previous
                       if r["category"] == cat and r["source"] == cfg["source"]]
                if old:
                    print(f"  keeping {len(old)} products from the last good run")
                got = old
                failed.append(f"{cat}/{cfg['source']}")
            rows += got

    # categories not scraped this run (when --category is used) are kept as-is
    rows += [r for r in previous if r["category"] not in cats]

    if not rows:
        print("No products at all - not overwriting the output.", file=sys.stderr)
        sys.exit(1)
    write_out(rows, args.out)
    if failed:
        print("\nWARNING - no fresh data for: " + ", ".join(failed), file=sys.stderr)


if __name__ == "__main__":
    main()
