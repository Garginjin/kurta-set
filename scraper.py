#!/usr/bin/env python3
"""
Fashion listing scraper -> one normalized CSV/JSON.

Pulls EVERY product from each brand and sorts it into a category
automatically (see CATEGORY RULES below), so the website can filter by category.

Sites supported:
  - Shopify stores (Jaipur Handblock, Label Kanupriya): the public
    /products.json feed (all sizes, prices, stock, images).
  - Zlaata (custom site): parses its server-rendered "all products" pages.

Usage:
  pip install requests beautifulsoup4
  python scraper.py                 # scrape everything -> docs/products.json (site) + data/ (record)
  python scraper.py --renormalise   # re-apply category + colour rules, no scraping

Polite by default: checks robots.txt, 1.5s delay between requests,
identifies itself with a plain User-Agent.
"""
import argparse
import gzip
import os
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
# BRANDS: one entry per brand. Add any Shopify brand with one line:
#   {"source": "Brand Name", "type": "shopify", "base": "https://brand.com"},
# ---------------------------------------------------------------------------
SOURCES = [
    {"source": "Jaipur Handblock", "type": "shopify", "base": "https://jaipurhandblock.in"},
    {"source": "Label Kanupriya", "type": "shopify", "base": "https://www.labelkanupriya.com"},
    {"source": "Ridhi Mehra", "type": "shopify", "base": "https://ridhimehra.com"},
    {"source": "Libas", "type": "shopify", "base": "https://www.libas.in"},
    {"source": "Aachho", "type": "shopify", "base": "https://www.aachho.com"},
    {"source": "House of Niav", "type": "shopify", "base": "https://houseofniav.com"},
    {"source": "Alaya by Stage3", "type": "shopify", "base": "https://alayabystage3.com"},
    {"source": "Lehenga Bazaar", "type": "shopify", "base": "https://lehengabazaar.co.in"},
    {"source": "Janasya", "type": "shopify", "base": "https://janasya.com"},
    {"source": "Phaelora", "type": "shopify", "base": "https://phaelora.in"},
    {"source": "Label S4U", "type": "shopify", "base": "https://label-s4u.com"},
    {"source": "Gulabo Jaipur", "type": "shopify", "base": "https://www.gulabojaipur.com"},
    {"source": "Pratapsons", "type": "shopify", "base": "https://pratapsons.com"},
    {"source": "AnarkaliSuit.in", "type": "shopify", "base": "https://anarkalisuit.in"},
    {"source": "Koskii", "type": "shopify", "base": "https://www.koskii.com"},       # custom front end: feed may be off
    {"source": "Nishorama", "type": "shopify", "base": "https://www.nishorama.com"}, # likely Shopify, unconfirmed
    {"source": "Subhvastra", "type": "shopify", "base": "https://subhvastra.in"},    # likely Shopify, unconfirmed
    {"source": "Aykaa", "type": "shopify", "base": "https://aykaa.in"},
    {"source": "Ethenika", "type": "shopify", "base": "https://ethenika.com"},
    {"source": "Mokosh", "type": "shopify", "base": "https://mokosh.in"},
    {"source": "Resha", "type": "shopify", "base": "https://www.reshaindia.in"},
    # Below: blocked AI readers, not checked yet. If one isn't Shopify, or its
    # robots.txt blocks all bots, the log says so and the run carries on.
    {"source": "Narayani Vastra", "type": "shopify", "base": "https://narayanivastra.in"},
    {"source": "House of Shrusha", "type": "shopify", "base": "https://houseofshrusha.com"},
    {"source": "Anayna", "type": "shopify", "base": "https://anayna.com"},
    {"source": "Idaho-o", "type": "shopify", "base": "https://idaho-o.com"},
    {"source": "Chhabra 555", "type": "shopify", "base": "https://www.chhabra555.com"},
    {"source": "Cotton Culture", "type": "shopify", "base": "https://www.cottonculture.co.in"},
    # Below: Shopify-style page addresses seen, platform not directly confirmed
    {"source": "Suta", "type": "shopify", "base": "https://suta.in"},
    {"source": "Okhai", "type": "shopify", "base": "https://okhai.org"},
    {"source": "Shobitam", "type": "shopify", "base": "https://shobitam.com"},
    {"source": "Kalki Fashion", "type": "shopify", "base": "https://www.kalkifashion.com"},  # shows $ abroad; rupee check guards
    {"source": "Posh Affair", "type": "shopify", "base": "https://poshaffair.co"},
    {"source": "Seher Jaipur", "type": "shopify", "base": "https://seherjaipur.com"},
    {"source": "The Gaima Label", "type": "shopify", "base": "https://thegaimalabel.com"},
    {"source": "Sheetal Batra", "type": "shopify", "base": "https://sheetalbatra.com"},
    {"source": "Idalia", "type": "shopify", "base": "https://www.idalia.in"},
    {"source": "Mansi Nagdev", "type": "shopify", "base": "https://mansinagdev.com"},
    {"source": "Misri", "type": "shopify", "base": "https://www.misri.in"},
    {"source": "Kalaloom", "type": "shopify", "base": "https://www.kalaloom.com"},
    {"source": "The Indian Ethnic Co", "type": "shopify", "base": "https://www.theindianethnicco.com"},
    {"source": "The Taram", "type": "shopify", "base": "https://www.thetaram.com"},
    {"source": "Gaia Coutures", "type": "shopify", "base": "https://gaiacoutures.com"},
    {"source": "Begum Pret", "type": "shopify", "base": "https://begumpret.com"},
    {"source": "Ranna Gill", "type": "shopify", "base": "https://rannagill.co.in"},
    {"source": "VNH Naidu Hall", "type": "shopify", "base": "https://vnhnaiduhall.com"},
    {"source": "Aarke by Ritu Kumar", "type": "shopify", "base": "https://aarke.ritukumar.com"},  # platform unconfirmed
    {"source": "Farida Gupta", "type": "shopify", "base": "https://faridagupta.com"},
    {"source": "Tjori", "type": "shopify", "base": "https://www.tjori.com"},
    {"source": "Utsav Bazar", "type": "shopify", "base": "https://utsavbazar.com"},
    {"source": "Xavielle", "type": "shopify", "base": "https://xavielle.com"},
    {"source": "Silai Studio", "type": "shopify", "base": "https://www.silaistudio.com"},
    {"source": "Aurelia", "type": "shopify", "base": "https://shopforaurelia.com"},
    {"source": "Lakshita", "type": "shopify", "base": "https://www.lakshita.com"},
    {"source": "Autumn Lane", "type": "shopify", "base": "https://autumnlane.in"},
    {"source": "Weavekala", "type": "shopify", "base": "https://weavekala.com"},
    {"source": "Bunai", "type": "shopify", "base": "https://www.bunai.com"},
    # Below: platform not confirmed - the run log shows if any fail
    {"source": "Kalmkari", "type": "shopify", "base": "https://kalmkari.in"},
    {"source": "House of Kari", "type": "shopify", "base": "https://houseofkari.in"},
    {"source": "Trendia", "type": "shopify", "base": "https://trendia.co"},
    {"source": "Kalpraag", "type": "shopify", "base": "https://kalpraag.com"},
    {"source": "Kisah", "type": "shopify", "base": "https://kisah.in"},
    {"source": "Pink Fort", "type": "shopify", "base": "https://pinkfort.co"},
    {"source": "Ensemble", "type": "shopify", "base": "https://www.ensembleindia.com"},
    {"source": "The Fashion Station", "type": "woocommerce", "base": "https://www.thefashionstation.in"},  # WordPress shop
    {"source": "Zlaata", "type": "zlaata",
     "urls": ["https://www.zlaata.com/zlaata-india/all",
              "https://www.zlaata.com/zlaata-india/all-accessories"]},
]

# ---------------------------------------------------------------------------
# CATEGORY RULES: checked top to bottom, first match wins.
# Matched against the product title first, then the brand's product type,
# then its tags. Edit the word lists to fix any product in the wrong place.
# ---------------------------------------------------------------------------
CATEGORIES = ["Kurta sets", "Co-ord sets", "Kurtas", "Dresses", "Tops & shirts",
              "Bottoms", "Lehengas", "Sarees", "Jackets & overlays",
              "Nightwear & loungewear", "Menswear", "Kidswear", "Accessories", "Other"]

_KURTA_WORDS = r"kurta|kurti|anarkali|sharara|salwar|suit|kaftan|churidar|afghani|dupatta"
_SET = (r"\bsets?\b|\bcombos?\b|\bskirt\s+tops?\b|\bsuits?\b|\b3\s?-?\s?(pc|pcs|piece)\b|\btwo[- ]piece\b|"
        r"\bwith\s+(\w+\s+){0,3}(palazzo|plazzo|pants?|sharara|salwar|dupatta|churidar|farshi|farsi|skirt|trousers?)\b|"
        r"\b(kurta|kurti|kaftan|tunic|top)\s*(&|and|\+)\s*(\w+\s+){0,2}(pants?|palazzo|sharara|salwar|skirt|dupatta|trousers?)\b")
CATEGORY_RULES = [
    ("Kidswear", r"\bkids?\b|\bgirls?\b|\bboys?\b|\binfants?\b|\btoddlers?\b"),
    ("Menswear", r"\bmen'?s?\b|\bmale\b|\bgents\b"),
    ("Co-ord sets", r"\bco[- ]?c?ords?\b|\bcoords?\b"),
    ("Lehengas", r"\blehenga|\blehnga"),
    ("Nightwear & loungewear", r"\bnight\s?wear\b|\bnight\s?suits?\b|\bnighty\b|\bnightdress\b|\bpyjamas?\b|\bpajamas?\b|\blounge\s?wear\b|\bsleep\s?wear\b"),
    ("Sarees", r"\bsarees?\b|\bsaris?\b"),
    ("SET", _SET),  # -> Kurta sets if kurta-type words, else Co-ord sets
    ("Dresses", r"\bdress(es)?\b|\bgowns?\b|\bjumpsuits?\b|\bmaxi\b|\bmidi\b"),
    ("Kurtas", r"\b(kurta|kurti|kurtas|kurtis|anarkali|kaftan)\b"),
    ("Tops & shirts", r"\btops?\b|\bshirts?\b|\bblouses?\b|\btunics?\b|\bcrop\b|\btees?\b|\bt-shirts?\b"),
    ("Bottoms", r"\bpants?\b|\bpalazzos?\b|\bplazzos?\b|\btrousers?\b|\bskirts?\b|\bshorts\b|\bsharara\b|\bsalwar\b|\bleggings?\b|\bculottes?\b|\bdhoti\b|\bbottoms?\b|\bjeans\b"),
    ("Jackets & overlays", r"\bjackets?\b|\bshrugs?\b|\boverlays?\b|\bcapes?\b|\bcoats?\b|\bwaistcoats?\b|\bbandi\b|\bkimonos?\b|\bcardigans?\b|\bblazers?\b"),
    ("Accessories", r"\bbags?\b|\btotes?\b|\bpouch(es)?\b|\bpotli\b|\bclutch\b|\bjewell?e?ry\b|\bearrings?\b|\bnecklaces?\b|\bbracelets?\b|\bbangles?\b|\brings?\b|\bscrunchies?\b|\bhair\b|\bkeychains?\b|\bmasks?\b|\bstoles?\b|\bscarf\b|\bdupattas?\b|\bbelts?\b|\bwallets?\b|\bgameboard\b|\bsocks\b"),
]
_RULES = [(c, re.compile(p, re.I)) for c, p in CATEGORY_RULES]
_KURTA_RE = re.compile(r"\b(" + _KURTA_WORDS + r")s?\b", re.I)

# Zlaata's own category (from its product URLs) -> our category
ZLAATA_CATEGORY = {
    "kurta-set": "Kurta sets", "co-ords": "Co-ord sets", "kurtas-kurtis": "Kurtas",
    "dresses": "Dresses", "tops-tunics": "Tops & shirts", "bottoms": "Bottoms",
    "lehengas": "Lehengas", "overlays": "Jackets & overlays",
    "hair": "Accessories", "bags-pouches": "Accessories", "gameboard": "Accessories",
    "keychain": "Accessories", "all-accessories": "Accessories",
}

SKIP_TYPES = re.compile(r"gift ?card|e-?gift|insurance|shipping|donation", re.I)


def _match(text):
    if not text:
        return None
    for cat, rx in _RULES:
        if rx.search(text):
            if cat == "SET":
                return "Kurta sets" if _KURTA_RE.search(text) else "Co-ord sets"
            return cat
    return None


def classify(title, product_type="", tags="", hint=None):
    """Return one of CATEGORIES for a product."""
    head = f"{title} {product_type}"
    # kids / men first, but only from title + type (tags are often noisy)
    for cat in ("Kidswear", "Menswear"):
        rx = dict(_RULES)[cat]
        if rx.search(head):
            return cat
    if hint:
        return hint
    for text in (title, product_type, tags):
        cat = _match(text)
        if cat and cat not in ("Kidswear", "Menswear"):
            return cat
    return "Other"


FIELDS = ["source", "category", "product_type", "product_id", "title", "brand", "url",
          "price", "mrp", "discount_pct", "sizes_available", "sizes_all",
          "colour", "colour_raw", "in_stock", "image", "tags", "published_at", "scraped_at"]


# ---------------------------------------------------------------------------
# Size normalisation: "S (36)", "S - 36", "SMALL", "36" -> "S".
# "Set of 3", "Unstitched", kids' ages etc. are not sizes and are dropped.
# ---------------------------------------------------------------------------
SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL", "5XL", "6XL", "7XL", "8XL", "Free size"]
_BUST = {30: "XXS", 32: "XXS", 34: "XS", 36: "S", 38: "M", 40: "L", 42: "XL", 44: "XXL",
         46: "3XL", 48: "4XL", 50: "5XL", 52: "6XL", 54: "7XL", 56: "8XL"}


def normalise_size(raw):
    t = re.sub(r"[^A-Z0-9]+", " ", str(raw).upper()).strip()
    if not t:
        return None
    if re.search(r"\bFREE\b|\bONE SIZE\b|\bFS\b|\bFREESIZE\b", t):
        return "Free size"
    if re.search(r"\bSET\b|STITCH|\bYRS?\b|\bYEARS?\b|\bMONTHS?\b|\bKIDS?\b", t):
        return None
    m = re.search(r"\b([2-8])\s?XL\b", t)
    if m:
        return "XXL" if m.group(1) == "2" else m.group(1) + "XL"
    m = re.search(r"\b(X{3,8})L\b", t)
    if m:
        return f"{len(m.group(1))}XL"
    for pat, size in [(r"\bXXL\b|\bXX L\b|\bDOUBLE XL\b", "XXL"), (r"\bXL\b|\bEXTRA LARGE\b|\bX LARGE\b", "XL"),
                      (r"\bXXS\b", "XXS"), (r"\bXS\b|\bEXTRA SMALL\b|\bX SMALL\b", "XS"),
                      (r"\bS\b|\bSMALL\b", "S"), (r"\bM\b|\bMEDIUM\b", "M"), (r"\bL\b|\bLARGE\b", "L")]:
        if re.search(pat, t):
            return size
    m = re.search(r"\b(\d{2})\b", t)
    if m and int(m.group(1)) in _BUST:
        return _BUST[int(m.group(1))]
    return None


def normalise_sizes(values):
    out = []
    for v in values:
        z = normalise_size(v)
        if z and z not in out:
            out.append(z)
    return sorted(out, key=SIZE_ORDER.index)


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
def parse_shopify_product(p, base, source):
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
        "category": classify(p.get("title", ""), p.get("product_type", ""), " ".join(tags)),
        "product_type": p.get("product_type", ""),
        "product_id": str(p.get("id")),
        "title": p.get("title", "").strip(),
        "brand": p.get("vendor") or source,
        "url": f"{base.rstrip('/')}/products/{p.get('handle')}",
        "price": price,
        "mrp": mrp,
        "discount_pct": disc(price, mrp),
        "sizes_available": "|".join(normalise_sizes(sizes_avail)),
        "sizes_all": "|".join(normalise_sizes(sizes_all)),
        "colour": colour_for(colours[0] if colours else "", p.get("title", "")),
        "colour_raw": "|".join(colours),
        "in_stock": any(v.get("available") for v in variants),
        "image": imgs[0]["src"] if imgs else "",
        "tags": "|".join(tags),
        "published_at": p.get("published_at") or p.get("created_at") or "",
        "scraped_at": now(),
    }


def scrape_shopify(f, cfg):
    base = cfg["base"].rstrip("/")
    out, page = [], 1
    while True:
        r = f.get(f"{base}/products.json", params={"limit": 250, "page": page})
        products = r.json().get("products", [])
        if not products:
            break
        for p in products:
            if SKIP_TYPES.search(p.get("product_type", "") + " " + p.get("title", "")):
                continue
            out.append(parse_shopify_product(p, base, cfg["source"]))
        print(f"  page {page}: {len(products)} products")
        if len(products) < 250:
            break
        page += 1
    return out


# ---------------------------------------------------------------------------
# WooCommerce (WordPress shops): public Store API, /wp-json/wc/store/v1/products
# ---------------------------------------------------------------------------
def _woo_money(prices, key):
    v = (prices or {}).get(key)
    if v in (None, ""):
        return None
    try:
        return int(v) / (10 ** int((prices or {}).get("currency_minor_unit", 2)))
    except (TypeError, ValueError):
        return None


def parse_woo_product(p, source):
    prices = p.get("prices") or {}
    price = _woo_money(prices, "price")
    mrp = _woo_money(prices, "regular_price") or price
    sizes, colours = [], []
    for a in p.get("attributes") or []:
        name = (a.get("name") or "").lower()
        terms = [t.get("name", "") for t in a.get("terms") or []]
        if "size" in name:
            sizes += terms
        elif "colo" in name:
            colours += terms
    cats = " ".join(c.get("name", "") for c in p.get("categories") or [])
    title = BeautifulSoup(p.get("name") or "", "html.parser").get_text().strip()
    imgs = p.get("images") or []
    in_stock = bool(p.get("is_in_stock", True))
    sz = normalise_sizes(sizes)
    return {
        "source": source,
        "category": classify(title, cats),
        "product_type": cats,
        "product_id": str(p.get("id")),
        "title": title,
        "brand": source,
        "url": p.get("permalink") or "",
        "price": price,
        "mrp": mrp,
        "discount_pct": disc(price, mrp),
        # the listing API doesn't say which sizes are in stock, so show all
        "sizes_available": "|".join(sz) if in_stock else "",
        "sizes_all": "|".join(sz),
        "colour": colour_for(colours[0] if colours else "", title),
        "colour_raw": "|".join(colours),
        "in_stock": in_stock,
        "image": imgs[0].get("src", "") if imgs else "",
        "tags": "|".join(t.get("name", "") for t in p.get("tags") or []),
        "published_at": "",
        "scraped_at": now(),
    }


def scrape_woocommerce(f, cfg, max_pages=200):
    base = cfg["base"].rstrip("/")
    out, page = [], 1
    while page <= max_pages:
        r = f.get(f"{base}/wp-json/wc/store/v1/products", params={"per_page": 100, "page": page})
        items = r.json()
        if not isinstance(items, list) or not items:
            break
        out += [parse_woo_product(p, cfg["source"]) for p in items if p.get("prices")]
        print(f"  page {page}: {len(items)} products")
        if len(items) < 100:
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
ZLAATA_LINK = re.compile(r"/zlaata-india/([^/]+)/[^/]+/(\d+)/select/?$")
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


def parse_zlaata_page(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    seen, items = set(), {}
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"])
        m = ZLAATA_LINK.search(urlparse(href).path)
        if not m:
            continue
        zcat, pid = m.group(1), m.group(2)
        card = find_card(a)
        rec = items.get(pid)
        if rec is None:
            rec = {"source": "Zlaata", "category": "", "product_type": zcat, "product_id": pid,
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
        rec["category"] = classify(rec["title"], hint=ZLAATA_CATEGORY.get(rec["product_type"]))
    return list(items.values())


def scrape_zlaata(f, cfg, max_pages=150):
    out, ids = [], set()
    for url in cfg["urls"]:
        page = 1
        while page <= max_pages:
            r = f.get(url, params={"page": page})
            items = parse_zlaata_page(r.text, r.url)
            new = [i for i in items if i["product_id"] not in ids]
            print(f"  {urlparse(url).path.rsplit('/', 1)[-1]} page {page}: {len(new)} new products")
            if not new:
                break
            ids.update(i["product_id"] for i in new)
            out.extend(new)
            page += 1
    return out


# ---------------------------------------------------------------------------
def write_out(rows, out):
    seen, uniq = set(), []
    for r in rows:  # never write the same product twice
        key = (r["source"], str(r["product_id"]))
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    rows = uniq
    order = {c: i for i, c in enumerate(CATEGORIES)}
    rows = sorted(rows, key=lambda r: (r["source"], order.get(r["category"], 99)))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out + ".csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    # the scraper's own record, compressed (~12x smaller) so the repo stays small
    with gzip.open(out + ".json.gz", "wt", encoding="utf-8", compresslevel=9) as fh:
        json.dump(rows, fh, ensure_ascii=False, separators=(",", ":"))
    write_site_data(rows, SITE_DATA)
    print(f"\n{len(rows)} products -> {out}.json.gz / {out}.csv")
    for src in sorted({r["source"] for r in rows}):
        mine = [r for r in rows if r["source"] == src]
        cats = {}
        for r in mine:
            cats[r["category"]] = cats.get(r["category"], 0) + 1
        print(f"  {src}: {len(mine)}  (" + ", ".join(
            f"{c} {n}" for c, n in sorted(cats.items(), key=lambda x: order.get(x[0], 99))) + ")")


# ---------------------------------------------------------------------------
# Site data: a compact file the website loads (docs/products.json).
# Short format + lookup tables keeps it small; brands are interleaved so the
# default "Recommended" view mixes brands instead of showing one at a time.
# ---------------------------------------------------------------------------
def mixed_order(rows):
    by_src = {}
    for r in rows:
        by_src.setdefault(r["source"], []).append(r)
    for lst in by_src.values():  # in stock, newest, then biggest discount first
        lst.sort(key=lambda r: (not r.get("in_stock"), _neg_date(r.get("published_at")),
                                -(r.get("discount_pct") or 0)))
    queues = sorted(by_src.values(), key=len, reverse=True)
    out, i = [], 0
    while queues:
        nxt = []
        for q in queues:
            if i < len(q):
                out.append(q[i])
            if i + 1 < len(q):
                nxt.append(q)
        queues, i = nxt, i + 1
    return out


def _neg_date(d):
    # newest first: invert the ISO date string's characters for descending sort
    return "".join(chr(0x10FFFF - ord(c)) for c in (d or "")[:19]) if d else "\U0010ffff"


FIRST_PART = 1500
SITE_DATA = "docs/products.json"   # what the website loads


def write_site_data(rows, path):
    sources, src_ix = [], {}
    for r in rows:
        if r["source"] not in src_ix:
            src_ix[r["source"]] = len(sources)
            base = re.match(r"https?://[^/]+", r["url"] or "")
            sources.append({"n": r["source"], "b": base.group(0) if base else ""})
    cats = CATEGORIES + sorted({r["category"] for r in rows} - set(CATEGORIES))
    cat_ix = {c: i for i, c in enumerate(cats)}
    colours = list(COLOUR_WORDS) + ["Other"]
    col_ix = {c: i for i, c in enumerate(colours)}
    products = []
    for r in mixed_order([r for r in rows if r.get("price")]):
        si = src_ix[r["source"]]
        base = sources[si]["b"]
        url = r["url"] or ""
        if base and url.startswith(base):
            url = url[len(base):]  # store the path only
        img = re.sub(r"^https?:", "", r.get("image") or "")
        img = re.sub(r"[?&]v=\d+$", "", img)  # cache-buster not needed
        mask = 0
        for z in (r.get("sizes_available") or "").split("|"):
            if z in SIZE_ORDER:
                mask |= 1 << SIZE_ORDER.index(z)
        price = round(float(r["price"]))
        mrp = round(float(r.get("mrp") or price))
        products.append([si, cat_ix.get(r["category"], len(cats) - 1), r["title"], url, price,
                         mrp if mrp > price else 0, col_ix.get(r.get("colour") or "Other", len(colours) - 1),
                         mask, 1 if r.get("in_stock") else 0, img])
    data = {"v": 1, "updated": now(), "sources": sources, "cats": cats, "colours": colours,
            "sizes": SIZE_ORDER,
            "fields": ["source", "cat", "title", "url", "price", "mrp", "colour", "sizes", "stock", "image"],
            "p": products}
    data["total"] = len(products)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    # first part: the top of the brand-mixed list, so the page shows products instantly
    first = dict(data, p=products[:FIRST_PART], part="first")
    with open(path.replace(".json", "-first.json"), "w", encoding="utf-8") as fh:
        json.dump(first, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"site data: {len(products)} products -> {path} (+ first {min(FIRST_PART, len(products))} in a quick-load file)")


def load_previous(out):
    """Last run's record. Older versions kept it uncompressed in docs/."""
    for path in (out + ".json.gz", out + ".json", "docs/listings.json"):
        try:
            if path.endswith(".gz"):
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    return json.load(fh)
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            continue
    return []


def renormalise(rows):
    """Re-apply category + colour rules to already-scraped rows."""
    seen, outr = set(), []
    for r in rows:
        key = (r["source"], str(r["product_id"]))
        if key in seen:  # old files could hold one product under 2 categories
            continue
        seen.add(key)
        raw = r.get("colour_raw")
        if raw is None:
            raw = r.get("colour", "")
        r["colour_raw"] = raw
        r["colour"] = colour_for(raw.split("|")[0] if raw else "", r["title"])
        for k in ("sizes_available", "sizes_all"):
            r[k] = "|".join(normalise_sizes((r.get(k) or "").split("|")))
        ptype = r.get("product_type", "")
        if r["source"] == "Zlaata":
            if not ptype:
                m = ZLAATA_LINK.search(urlparse(r["url"]).path)
                ptype = m.group(1) if m else ""
            r["product_type"] = ptype
            r["category"] = classify(r["title"], hint=ZLAATA_CATEGORY.get(ptype))
        else:
            r["product_type"] = ptype
            r["category"] = classify(r["title"], ptype, r.get("tags", "").replace("|", " "))
        outr.append(r)
    return outr


def main():
    sys.stdout.reconfigure(line_buffering=True)  # show progress live in the GitHub log
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/listings",
                    help="record path without extension (default data/listings)")
    ap.add_argument("--renormalise", action="store_true",
                    help="don't scrape; re-apply category + colour rules to the existing file")
    args = ap.parse_args()
    previous = load_previous(args.out)

    if args.renormalise:
        write_out(renormalise(previous), args.out)
        return

    f = Fetcher()
    rows, failed = [], []
    for cfg in SOURCES:
        print(f"[{cfg['source']}]")
        got = []
        try:
            if cfg["type"] == "shopify":
                got = scrape_shopify(f, cfg)
            elif cfg["type"] == "zlaata":
                got = scrape_zlaata(f, cfg)
            elif cfg["type"] == "woocommerce":
                got = scrape_woocommerce(f, cfg)
        except Exception as e:  # keep going if one site fails
            print(f"  FAILED: {e}", file=sys.stderr)
        prices = sorted(r["price"] for r in got if r.get("price"))
        if prices and prices[len(prices) // 2] < 300:
            # e.g. a store priced in US dollars: ₹45 would be wrong, so drop it
            print(f"  SKIPPED: median price {prices[len(prices) // 2]} looks like a non-rupee store")
            got = []
        if not got:
            # Site failed or returned nothing: keep its last good data
            # so the website never suddenly loses a whole brand.
            got = renormalise([r for r in previous if r["source"] == cfg["source"]])
            if got:
                print(f"  keeping {len(got)} products from the last good run")
            failed.append(cfg["source"])
        rows += got

    if not rows:
        print("No products at all - not overwriting the output.", file=sys.stderr)
        sys.exit(1)
    write_out(rows, args.out)
    if failed:
        print("\nWARNING - no fresh data for: " + ", ".join(failed), file=sys.stderr)


if __name__ == "__main__":
    main()
