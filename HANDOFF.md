# saubag – handoff notes (read this first)

Site: https://garginjin.github.io/kurta-set/  ·  Repo: Garginjin/kurta-set (main)
Owner: Garima. Wants direct, list-format answers, tool-verified facts, no invented data.
Show a preview/mockup BEFORE changing the live site's look.

## How it works
- `scraper.py` – scrapes ~93 brands (Shopify /products.json, WooCommerce Store API, Zlaata HTML).
  Brand list = `SOURCES`. Adds categories, colours, sizes, Indian-wear attributes
  (work, print, fabric, shape, bottom, dupatta, neck, sleeve, occasion, stitching), groups colour versions.
- `.github/workflows/refresh.yml` – every 6 h (and manual): scrape → save `data/listings.json.gz`,
  `data/brands.json` (logo + About text, weekly) → build `docs/products.json`, `docs/brands.json` → deploy Pages.
  A push runs `scraper.py --renormalise` only (no scraping, ~2 min).
- `docs/index.html` – the whole site (vanilla JS, hash routes `#/`, `#/shop?...`, `#/brands`, `#/brand/<slug>`).
- `data/brand_stories.json` – brand stories (written only from each brand's own About page).
- Generated files (`docs/products*.json`, `docs/brands.json`) are NOT committed.

## Rules for every chat
- `git pull` before editing, small commits, push to main. Two chats both edit `docs/index.html`:
  keep changes to your own section and rebase before pushing.
- Test locally: `python3 scraper.py --renormalise` then serve `docs/` and check in a headless browser.

## Workstreams
A. Design/layout – colours not chosen yet (colour picker: https://claude.ai/artifact/LCBcZcQ552bnryQDjG7mR7);
   festive banner options on canvas https://claude.ai/artifact/94y3KauxE4vFjN4sXVxrgk (Garima rejected purple-everything,
   wants off-white with lights, brand cards simple with logos).
B. Filters/search UX – filters in `compute()`/`renderAttrs()`; Similar styles in `similar()`; search is plain substring.
   Open: Style Union (mostly non-ethnic) keep-or-remove; neck/sleeve coverage low until descriptions are scraped.
C. Going live – custom domain saubag.in (Hostinger suggested; needs 4 A records 185.199.108-111.153 + CNAME www,
   `docs/CNAME`, Enforce HTTPS), affiliate links via `outLink()` in index.html (Cuelinks/vCommission/Shopify Collabs),
   About/privacy/disclosure/takedown pages, SEO pages + sitemap, analytics.
   Failing brands: Koskii, Nishorama, Aarke, Ensemble, Aramya, Soch, Garden Vareli, Global Desi (blocked/not Shopify);
   Shobitam, Kalki (non-INR prices); Cilory (unsupported).
