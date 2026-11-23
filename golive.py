"""Build the published site (workstream C: going live).

Copies docs/ to _site/ and adds, using only real data from docs/products.json and docs/brands.json:
  - js/site-config.js + golive.js/golive.css hooked into index.html (affiliate links, footer links)
  - canonical / Open Graph / JSON-LD tags and optional analytics in index.html
  - info pages: about, disclosure (always); privacy, takedown (only once contact_email is set)
  - crawlable landing pages: /c/<category>/, /c/<category>/<craft>/, /brand/<brand>/
  - sitemap.xml, robots.txt, CNAME (only once a domain is set), 404.html

Settings: site_config.json. Nothing under docs/ is changed.
Run after scraper.py:  python golive.py   (then serve _site/ to preview)
"""
import html
import json
import os
import re
import shutil
import sys
from datetime import datetime
from urllib.parse import quote

from scraper import slugify

SRC, OUT = "docs", "_site"
PER_PAGE = 60            # products shown on each landing page
MIN_CRAFT = 30           # a category + craft page needs at least this many in-stock styles
MIN_CAT = 20             # a category page needs at least this many in-stock styles
e = html.escape


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


CFG = load_json("site_config.json", {})
DOMAIN = (CFG.get("domain") or "").strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
BASE = f"https://{DOMAIN}" if DOMAIN else (CFG.get("github_pages_url") or "").rstrip("/")
EMAIL = (CFG.get("contact_email") or "").strip()
AFF = CFG.get("affiliate") or {}
AFF_ON = bool(AFF.get("url_template") or AFF.get("per_brand"))
ANALYTICS = CFG.get("analytics") or {}
SITE_NAME = "saubag"


def out_link(url, source):
    """Same rule as golive.js, so static pages and the app send people to identical links."""
    if not re.match(r"^https?://", url or "", re.I):
        return url
    tpl = (AFF.get("per_brand") or {}).get(source) or AFF.get("url_template") or ""
    if not tpl:
        return url
    return tpl.replace("{url_enc}", quote(url, safe="")).replace("{url}", url)


def img_url(u):
    if not u:
        return ""
    if u.startswith("//"):
        u = "https:" + u
    if re.search(r"/cdn/shop/|cdn\.shopify\.com", u) and "width=" not in u:
        u += ("&" if "?" in u else "?") + "width=500"
    return u


def rs(n):
    """Indian digit grouping: 125000 -> ₹1,25,000"""
    s = str(int(round(n)))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = head + "," + tail
    return "₹" + s


def analytics_tag():
    p, i = (ANALYTICS.get("provider") or "").lower(), (ANALYTICS.get("id") or "").strip()
    if not (p and i):
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", i):
        sys.exit(f"analytics id {i!r} has unexpected characters")
    if p == "cloudflare":
        return f"""<script defer src="https://static.cloudflareinsights.com/beacon.min.js" data-cf-beacon='{{"token": "{i}"}}'></script>"""
    if p == "ga4":
        return (f'<script async src="https://www.googletagmanager.com/gtag/js?id={i}"></script>'
                f"<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}"
                f"gtag('js',new Date());gtag('config','{i}');</script>")
    if p == "goatcounter":
        return f'<script data-goatcounter="https://{i}.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>'
    sys.exit(f"unknown analytics provider {p!r} (use cloudflare, ga4 or goatcounter)")


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def products():
    d = load_json(os.path.join(SRC, "products.json"))
    if not d:
        sys.exit("docs/products.json missing: run python scraper.py --renormalise first")
    attrs = d.get("attrs", [])
    rows = []
    for si, ci, title, url, price, mrp, co, mask, stock, image, ai, vs in d["p"]:
        src = d["sources"][si]
        rows.append({
            "source": src["n"], "cat": d["cats"][ci], "title": title,
            "url": url if url.startswith("http") else src["b"] + url,
            "price": price, "mrp": mrp or price, "stock": stock == 1 or any(v[3] for v in vs),
            "image": img_url(image), "attrs": [attrs[k] for k in ai if k < len(attrs)],
        })
    return d, rows


# ---------------------------------------------------------------------------
# page shell
# ---------------------------------------------------------------------------
def shell(path, title, desc, body, root, extra_head="", noindex=False):
    canon = f"{BASE}/{path}" if BASE else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{f'<link rel="canonical" href="{e(canon)}">' if canon else ''}
{'<meta name="robots" content="noindex">' if noindex else ''}
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
{f'<meta property="og:url" content="{e(canon)}">' if canon else ''}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Manrope:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="{root}css/site.css">
<link rel="stylesheet" href="{root}css/golive.css">
{extra_head}
{analytics_tag()}
</head>
<body class="golive-page">
<header>
  <div class="wrap bar">
    <a class="logo" href="{root}#/">{SITE_NAME}</a>
    <nav class="top" aria-label="Main">
      <a href="{root}#/">Home</a><a href="{root}#/shop">Shop</a><a href="{root}#/brands">Brands</a>
    </nav>
  </div>
</header>
<main class="wrap gl-main">
{body}
</main>
<footer>
  <div class="wrap">
    <span class="logo">{SITE_NAME}</span><br>
    Prices and stock are refreshed about twice a day. Always check the final price on the brand's site.
    <div class="golive-links">
      {f'<p class="golive-disc">Some links are affiliate links: {SITE_NAME} may earn a commission at no extra cost to you. <a href="{root}disclosure.html">How this works</a></p>' if AFF_ON else ''}
      <nav aria-label="About {SITE_NAME}">{"".join(f'<a href="{root}{p["href"]}">{e(p["label"])}</a>' for p in INFO_LINKS)}</nav>
    </div>
  </div>
</footer>
</body>
</html>
"""


def card(p):
    off = round((p["mrp"] - p["price"]) / p["mrp"] * 100) if p["mrp"] > p["price"] else 0
    price = f'<b>{rs(p["price"])}</b>' + (f' <s>{rs(p["mrp"])}</s> <span class="gl-off">{off}% off</span>' if off else "")
    return f"""<li class="gl-card">
  <a href="{e(out_link(p["url"], p["source"]))}" target="_blank" rel="nofollow sponsored noopener">
    <span class="gl-img">{f'<img src="{e(p["image"])}" alt="{e(p["title"])}" loading="lazy" decoding="async">' if p["image"] else ''}</span>
    <span class="gl-src">{e(p["source"])}</span>
    <span class="gl-t">{e(p["title"])}</span>
    <span class="gl-p">{price}</span>
  </a>
</li>"""


def item_list_ld(items, name):
    return ('<script type="application/ld+json">' + json.dumps({
        "@context": "https://schema.org", "@type": "ItemList", "name": name,
        "numberOfItems": len(items),
        "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": p["title"], "url": p["url"]}
                            for i, p in enumerate(items)]}, ensure_ascii=False).replace("</", "<\\/") + "</script>")


def landing(path, h1, intro, items, total, app_href, app_label, root, chips_html="", top_html=""):
    show = items[:PER_PAGE]
    body = f"""<nav class="gl-crumbs" aria-label="Breadcrumb"><a href="{root}#/">Home</a> / <span>{e(h1)}</span></nav>
{top_html}
<h1 class="gl-h1">{e(h1)}</h1>
<p class="gl-intro">{intro}</p>
<p><a class="gl-cta" href="{e(app_href)}">{e(app_label)}</a></p>
{chips_html}
<ul class="gl-grid">{"".join(card(p) for p in show)}</ul>
{f'<p class="gl-more"><a class="gl-cta" href="{e(app_href)}">See all {total:,} with filters</a></p>' if total > len(show) else ''}"""
    og = f'<meta property="og:image" content="{e(show[0]["image"])}">' if show and show[0]["image"] else ""
    return body, og


def price_line(items):
    ps = sorted(p["price"] for p in items)
    return f"{rs(ps[0])} to {rs(ps[-1])}" if ps else ""


def chips(pairs, root):
    if not pairs:
        return ""
    return '<ul class="gl-chips">' + "".join(f'<li><a href="{root}{e(h)}">{e(t)}</a></li>' for t, h in pairs) + "</ul>"


# ---------------------------------------------------------------------------
# info pages (facts only: what the site actually does)
# ---------------------------------------------------------------------------
def info_pages(n_brands, n_styles, updated):
    pages = {}
    analytics = (ANALYTICS.get("provider") or "").lower() if ANALYTICS.get("id") else ""
    an_name = {"cloudflare": "Cloudflare Web Analytics", "ga4": "Google Analytics", "goatcounter": "GoatCounter"}.get(analytics, "")
    mail = f'<a href="mailto:{e(EMAIL)}">{e(EMAIL)}</a>' if EMAIL else ""

    pages["about.html"] = ("About", f"About {SITE_NAME}", f"What {SITE_NAME} is and how it works.", f"""
<h1 class="gl-h1">About {SITE_NAME}</h1>
<div class="gl-prose">
<p>{SITE_NAME} puts Indian ethnic wear from {n_brands} brands in one place: {n_styles:,} styles you can filter by category, colour, size, price, fabric and craft, and compare side by side.</p>
<p>{SITE_NAME} does not sell anything. Every product links to the brand's own website, and you buy there, at the brand's price, under the brand's shipping, return and exchange policies.</p>
<h2>Where the information comes from</h2>
<ul>
<li>Product names, prices, sizes, stock and photos are read from each brand's public online store and refreshed about twice a day.</li>
<li>Categories, colours and details such as fabric or work are worked out automatically from the brand's own product name and description, so they can occasionally be wrong. The brand's page is always the final word.</li>
</ul>
<p>Last refreshed: {e(updated)}.</p>
<h2>For brands</h2>
<p>{'To correct a listing or have your brand removed, see <a href="takedown.html">Brand corrections and removal</a>.' if EMAIL else 'A page for brands to request corrections or removal is coming soon.'}</p>
</div>""")

    pages["disclosure.html"] = ("Affiliate disclosure", "Affiliate disclosure", f"How {SITE_NAME} earns money from links.", f"""
<h1 class="gl-h1">Affiliate disclosure</h1>
<div class="gl-prose">
{f'''<p>Some links on {SITE_NAME} are affiliate links. If you click one and buy something, {SITE_NAME} may earn a small commission from the brand or from an affiliate network.</p>
<ul><li>You pay the same price as you would going to the brand directly.</li>
<li>Commissions do not decide which products are shown or in what order.</li>
<li>Links that may earn a commission are marked as sponsored in the page code, as search engines require.</li></ul>'''
  if AFF_ON else
f'''<p>Right now, links on {SITE_NAME} go straight to each brand's website and {SITE_NAME} earns nothing from them.</p>
<p>{SITE_NAME} may add affiliate links in future. If it does, you will still pay the same price, commissions will not decide which products are shown, and this page will be updated to say so.</p>'''}
</div>""")

    if EMAIL:
        pages["privacy.html"] = ("Privacy", "Privacy policy", f"What {SITE_NAME} collects and why.", f"""
<h1 class="gl-h1">Privacy policy</h1>
<div class="gl-prose">
<p>{SITE_NAME} has no accounts, no sign-up and no forms. It does not ask for your name, phone number, email or address.</p>
<h2>What is stored on your device</h2>
<ul><li>Styles you add to Compare are saved in your browser's local storage, so they are still there when you come back. They never leave your device. Clearing your browser data removes them.</li>
<li>{SITE_NAME} itself sets no cookies.</li></ul>
<h2>Other services your browser talks to</h2>
<ul>
<li><b>GitHub Pages</b> hosts the site and, like any web host, receives your IP address and browser details when pages load.</li>
<li><b>Google Fonts</b> serves the typefaces.</li>
<li><b>Brand websites and their image servers</b> supply product photos, and you go to the brand's site when you click a product. Their privacy policies apply there.</li>
{f'<li><b>{an_name}</b> counts visits and pages viewed, to see what is useful. It does not identify you personally.</li>' if an_name else '<li>No analytics or tracking tools are used at the moment. This page will be updated before any are added.</li>'}
{f'<li><b>Affiliate networks</b>: some product links pass through an affiliate network, which may set its own cookie to record that the visit came from {SITE_NAME}.</li>' if AFF_ON else ''}
</ul>
<h2>Contact</h2>
<p>For any question about privacy, or to raise a grievance, write to {mail}.</p>
</div>""")

        pages["takedown.html"] = ("Brand corrections and removal", "Brand corrections and removal",
                                  f"How brands can correct or remove their listings on {SITE_NAME}.", f"""
<h1 class="gl-h1">Brand corrections and removal</h1>
<div class="gl-prose">
<p>{SITE_NAME} lists products from brands' public online stores and sends shoppers to the brand's own site to buy.</p>
<p>If you represent a brand and want to:</p>
<ul><li>correct a listing, logo or brand story,</li><li>change how your products are linked, or</li><li>have your brand removed from {SITE_NAME},</li></ul>
<p>email {mail} from an address at your brand's domain, with your brand name and what you would like changed.</p>
<p>A removed brand is taken out of the next refresh and stops being collected.</p>
<p>For anything else, such as a copyright concern about a photo or text, write to the same address with a link to the page.</p>
</div>""")
    return pages


INFO_LINKS = []
BUILT_CATS, BUILT_BRANDS = [], []
CRAFT_BY_NAME = {}


def main():
    if not os.path.isdir(SRC):
        sys.exit("run from the repo root")
    d, rows = products()
    bd = load_json(os.path.join(SRC, "brands.json"), {"brands": []})
    CRAFT_BY_NAME.clear()
    CRAFT_BY_NAME.update({c["name"]: c for c in (load_json(os.path.join(SRC, "crafts.json"), {}) or {}).get("crafts", [])
                          if not c.get("bucket")})   # skip catch-alls like "Printed (other)"
    brands = {b["n"]: b for b in bd.get("brands", [])}
    updated = d.get("updated", "")
    try:
        updated_h = datetime.fromisoformat(updated.replace("Z", "+00:00")).strftime("%d %b %Y")
    except ValueError:
        updated_h = updated[:10]
    lastmod = updated[:10]

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(SRC, OUT)

    live = [p for p in rows if p["stock"]]
    n_brands = len({p["source"] for p in rows})
    urls = [("", "daily")]

    info = info_pages(n_brands, len(rows), updated_h)
    INFO_LINKS[:] = [{"href": "brands/", "label": "All brands"}] + [{"href": k, "label": v[0]} for k, v in info.items()]

    # ---- site-config.js for the app + hook into index.html
    cfg_js = {"affiliate": {"url_template": AFF.get("url_template") or "", "per_brand": AFF.get("per_brand") or {}},
              "affiliate_on": AFF_ON, "pages": INFO_LINKS}
    with open(os.path.join(OUT, "js", "site-config.js"), "w", encoding="utf-8") as fh:
        fh.write("window.SAUBAG_CFG = " + json.dumps(cfg_js, ensure_ascii=False).replace("</", "<\\/") + ";\n")
    idx_path = os.path.join(OUT, "index.html")
    with open(idx_path, encoding="utf-8") as fh:
        idx = fh.read()
    desc = re.search(r'<meta name="description" content="([^"]*)"', idx)
    head = [f'<link rel="canonical" href="{e(BASE)}/">' if BASE else "",
            f'<meta property="og:site_name" content="{SITE_NAME}">',
            f'<meta property="og:title" content="{SITE_NAME} | India\'s ethnic-wear brands, in one place">',
            f'<meta property="og:description" content="{desc.group(1) if desc else ""}">',
            '<meta property="og:type" content="website">',
            f'<meta property="og:url" content="{e(BASE)}/">' if BASE else "",
            '<link rel="stylesheet" href="css/golive.css">',
            '<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@type": "WebSite",
                                                                "name": SITE_NAME, "url": BASE + "/"}) + "</script>",
            analytics_tag()]
    if "</head>" not in idx or '<script src="js/core.js"></script>' not in idx:
        sys.exit("index.html layout changed: can't find </head> or the core.js script tag")
    idx = idx.replace("</head>", "\n".join(h for h in head if h) + "\n</head>", 1)
    idx = idx.replace('<script src="js/core.js"></script>',
                      '<script src="js/core.js"></script>\n<script src="js/site-config.js"></script>\n<script src="js/golive.js"></script>', 1)
    with open(idx_path, "w", encoding="utf-8") as fh:
        fh.write(idx)

    # ---- info pages
    for fname, (label, title, desc_, body) in info.items():
        with open(os.path.join(OUT, fname), "w", encoding="utf-8") as fh:
            fh.write(shell(fname, f"{title} | {SITE_NAME}", desc_, body, ""))
        urls.append((fname, "monthly"))

    def write(rel, page_html):
        os.makedirs(os.path.join(OUT, rel), exist_ok=True)
        with open(os.path.join(OUT, rel, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(page_html)
        urls.append((rel + "/", "daily"))

    # ---- category pages + category x craft pages
    root2, root3 = "../../", "../../../"
    n_cat = n_craft = 0
    for cat in d["cats"]:
        items = [p for p in live if p["cat"] == cat]
        if cat == "Other" or len(items) < MIN_CAT:
            continue
        cslug = slugify(cat)
        by_brand = {}
        for p in items:
            by_brand[p["source"]] = by_brand.get(p["source"], 0) + 1
        crafts = {}
        for p in items:
            for a in p["attrs"]:
                g, v = a.split(":", 1)
                if g == "craft" and v in CRAFT_BY_NAME:   # the site's own craft list (crafts.json)
                    crafts.setdefault((a, v), []).append(p)
        craft_pages = [(a, v, ps) for (a, v), ps in sorted(crafts.items(), key=lambda x: -len(x[1])) if len(ps) >= MIN_CRAFT]
        top_brands = sorted(by_brand.items(), key=lambda x: -x[1])[:12]
        intro = (f"{len(items):,} {e(cat.lower())} in stock from {len(by_brand)} Indian brands, "
                 f"{price_line(items)}. Updated {e(updated_h)}. Buy straight from each brand.")
        chip_html = ""
        if craft_pages:
            chip_html += '<h2 class="gl-h2">By craft</h2>' + chips([(f"{v} ({len(ps)})", f"c/{cslug}/{CRAFT_BY_NAME[v]['id']}/") for a, v, ps in craft_pages], root2)
        chip_html += '<h2 class="gl-h2">Top brands</h2>' + chips([(f"{b} ({n})", f"brand/{slugify(b)}/") for b, n in top_brands if b in brands], root2)
        app = f"{root2}#/shop?cat={quote(cat)}"
        body, ld = landing(f"c/{cslug}/", cat, intro, items, len(items), app, f"Filter all {len(items):,} {cat.lower()}", root2, chip_html)
        write(f"c/{cslug}", shell(f"c/{cslug}/", f"{cat} from {len(by_brand)} Indian brands | {SITE_NAME}",
                                  f"Shop {len(items):,} {cat.lower()} from {len(by_brand)} Indian ethnic-wear brands in one place. Prices {price_line(items)}.",
                                  body, root2, ld))
        n_cat += 1
        BUILT_CATS.append((cat, f"c/{cslug}/", len(items)))
        for a, v, ps in craft_pages:
            nb = len({p["source"] for p in ps})
            h1 = f"{v} {cat.lower()}"
            cr = CRAFT_BY_NAME[v]
            intro = (f"{len(ps):,} {e(h1.lower())} in stock from {nb} brands, {price_line(ps)}. "
                     f"Craft is detected from each brand's product name and description. Updated {e(updated_h)}.")
            if cr.get("blurb"):
                intro += f'</p><p class="gl-story">{e(cr["blurb"])}' + (f' <span class="gl-region">{e(cr["region"])}</span>' if cr.get("region") else "")
            app = f"{root3}#/shop?cat={quote(cat)}&a={quote(a)}"
            crumbs = f'<nav class="gl-crumbs" aria-label="Breadcrumb"><a href="{root3}#/">Home</a> / <a href="{root3}c/{cslug}/">{e(cat)}</a> / <span>{e(v)}</span></nav>'
            body, ld = landing("", h1, intro, ps, len(ps), app, f"Filter all {len(ps):,}", root3)
            body = re.sub(r'^<nav class="gl-crumbs".*?</nav>', crumbs, body, count=1, flags=re.S)
            rel = f"c/{cslug}/{cr['id']}"
            write(rel, shell(rel + "/", f"{h1[0].upper() + h1[1:]} from {nb} brands | {SITE_NAME}",
                             f"{len(ps):,} {h1.lower()} from {nb} Indian brands in one place. Prices {price_line(ps)}.",
                             body, root3, ld))
            n_craft += 1

    # ---- brand pages
    n_brand = 0
    for name, b in brands.items():
        items = [p for p in rows if p["source"] == name]
        stock = [p for p in items if p["stock"]]
        if not items:
            continue
        cats = {}
        for p in stock:
            cats[p["cat"]] = cats.get(p["cat"], 0) + 1
        facts = []
        story_l = (b.get("story") or "").lower()
        if b.get("based") and str(b["based"]).lower() not in story_l:   # don't repeat what the story already says
            facts.append(f"Based in {e(b['based'])}")
        if b.get("founded") and str(b["founded"]) not in story_l:
            facts.append(f"Founded {e(str(b['founded']))}")
        top = ""
        if b.get("logo"):
            top += f'<img class="gl-logo" src="{e(img_url(b["logo"]))}" alt="{e(name)} logo">'
        intro = (f"{len(stock):,} {name} styles in stock, {price_line(stock or items)}. Updated {e(updated_h)}."
                 + (f" {' · '.join(facts)}." if facts else ""))
        if b.get("story"):
            intro += f'</p><p class="gl-story">{e(b["story"])}' + (
                f' <a href="{e(b["story_source"])}" rel="nofollow noopener" target="_blank">From the brand\'s site</a>' if b.get("story_source") else "")
        chip_html = '<h2 class="gl-h2">Categories</h2>' + chips(
            [(f"{c} ({n})", f"#/shop?cat={quote(c)}&brand={quote(name)}") for c, n in sorted(cats.items(), key=lambda x: -x[1]) if c != "Other"], root2) if cats else ""
        if b.get("site"):
            chip_html += f'<p class="gl-site">Shop the full range on <a href="{e(out_link(b["site"], name))}" rel="nofollow sponsored noopener" target="_blank">{e(re.sub(r"^https?://(www\.)?", "", b["site"]).rstrip("/"))}</a></p>'
        app = f"{root2}#/brand/{b['slug']}"
        body, ld = landing(f"brand/{b['slug']}/", name, intro, stock or items, len(items), app,
                           f"Filter all {len(items):,} {name} styles", root2, chip_html, top)
        write(f"brand/{b['slug']}", shell(f"brand/{b['slug']}/", f"{name}: {len(stock):,} styles in stock | {SITE_NAME}",
                                          f"Browse {len(stock):,} {name} styles ({', '.join(list(cats)[:3]).lower()}) and compare with other Indian brands on {SITE_NAME}.",
                                          body, root2, ld))
        n_brand += 1
        BUILT_BRANDS.append((name, f"brand/{b['slug']}/", len(stock)))

    # ---- crawlable entry points: /brands/ directory page + static links in the homepage footer
    cat_links = "".join(f'<li><a href="{root2[:0]}{h}">{e(c)} ({n:,})</a></li>' for c, h, n in BUILT_CATS)
    body = (f'<nav class="gl-crumbs" aria-label="Breadcrumb"><a href="../#/">Home</a> / <span>All brands</span></nav>'
            f'<h1 class="gl-h1">All brands</h1><p class="gl-intro">{len(BUILT_BRANDS)} Indian ethnic-wear brands on {SITE_NAME}, '
            f'with the number of styles in stock. Updated {e(updated_h)}.</p>'
            '<h2 class="gl-h2">Categories</h2>' + chips([(f"{c} ({n:,})", h) for c, h, n in BUILT_CATS], "../") +
            '<h2 class="gl-h2">Brands</h2>' + chips([(f"{b} ({n:,})", h) for b, h, n in sorted(BUILT_BRANDS, key=lambda x: x[0].lower())], "../"))
    os.makedirs(os.path.join(OUT, "brands"), exist_ok=True)
    with open(os.path.join(OUT, "brands", "index.html"), "w", encoding="utf-8") as fh:
        fh.write(shell("brands/", f"All {len(BUILT_BRANDS)} brands | {SITE_NAME}",
                       f"Every Indian ethnic-wear brand on {SITE_NAME}: {len(BUILT_BRANDS)} brands, browse by category or brand.", body, "../"))
    urls.append(("brands/", "daily"))
    with open(idx_path, encoding="utf-8") as fh:
        idx = fh.read()
    nav = ('<nav class="golive-browse" aria-label="Browse"><b>Browse:</b> '
           + " · ".join(f'<a href="{h}">{e(c)}</a>' for c, h, n in BUILT_CATS) + ' · <a href="brands/">All brands</a></nav>')
    marker = "  </div>\n</footer>"
    if marker not in idx:
        sys.exit("index.html footer layout changed: can't add browse links")
    idx = idx.replace(marker, "    " + nav + "\n" + marker, 1)
    with open(idx_path, "w", encoding="utf-8") as fh:
        fh.write(idx)

    # ---- 404, sitemap, robots, CNAME
    with open(os.path.join(OUT, "404.html"), "w", encoding="utf-8") as fh:
        # GitHub serves 404.html at any depth, so links must start from the site root
        sub = BASE.split("/", 3)[3].strip("/") if not DOMAIN and BASE.count("/") >= 3 else ""
        root = f"/{sub}/" if sub else "/"
        fh.write(shell("404.html", f"Page not found | {SITE_NAME}", "This page doesn't exist.",
                       f'<h1 class="gl-h1">Page not found</h1><p class="gl-intro">This page has moved or never existed.</p><p><a class="gl-cta" href="{root}#/shop">Browse all styles</a></p>',
                       root, noindex=True))
    if BASE:
        sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for u, freq in urls:
            sm.append(f"  <url><loc>{e(BASE)}/{e(u)}</loc><lastmod>{lastmod}</lastmod><changefreq>{freq}</changefreq></url>")
        sm.append("</urlset>")
        with open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(sm) + "\n")
        with open(os.path.join(OUT, "robots.txt"), "w", encoding="utf-8") as fh:
            fh.write(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
    if DOMAIN:
        with open(os.path.join(OUT, "CNAME"), "w") as fh:
            fh.write(DOMAIN + "\n")

    print(f"golive: {OUT}/ built for {BASE or '(no base URL)'}: {n_cat} category, {n_craft} category+craft, "
          f"{n_brand} brand pages, {len(info)} info pages ({', '.join(info)}), {len(urls)} URLs in sitemap")
    if not EMAIL:
        print("golive: NOTE privacy.html and takedown.html are not published until contact_email is set in site_config.json")
    if not AFF_ON:
        print("golive: NOTE no affiliate template set; product links go straight to brands")


if __name__ == "__main__":
    main()
