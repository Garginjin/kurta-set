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
- Site (vanilla JS, hash routes `#/`, `#/shop?...`, `#/brands`, `#/brand/<slug>`), split by owner:

| File | Owner | What's in it |
|---|---|---|
| `docs/index.html` | A design | Page markup: header, banner/home sections, dialogs |
| `docs/css/site.css` | A design | All styles except the filter column |
| `docs/js/layout.js` | A design | Product card, brand card, home page, brands page, brand banner |
| `docs/css/filters.css` | B filters | Filter column styles |
| `docs/js/filters.js` | B filters | Filter column markup (FILTERS_HTML), filter logic and counts, search, sort, results list, Similar styles |
| `docs/js/core.js` | shared, avoid editing | Settings, data loading, compare, routing. Change only if both chats agree |
| `scraper.py` | B (attributes) and C (brands) | Scraping and data building |

  A and B never edit each other's files. If one needs something from the other's file, say so in that chat instead.
- `data/brand_stories.json` – brand stories (written only from each brand's own About page).
- Generated files (`docs/products*.json`, `docs/brands.json`) are NOT committed.

## Rules for every chat
- `git pull` before editing, small commits, push to main. Edit only your own files (table above).
- Test locally: `python3 scraper.py --renormalise` then serve `docs/` and check in a headless browser.

## Workstreams
A. Design/layout – LIVE 4 Nov: Garima's palette (bg #FFFBFA, card #FFF, banner #FFF3F1, main #AA1D5F, gold #E69B0F,
   arch #3C05A3, text #24121A, soft #66505A, lines #E3D8F8; Cormorant Garamond + Manrope). Colours are the 9 vars at the top of
   `css/site.css`; the rest derive from them. Festive banner = canvas option A (string lights, garlands, diyas, products in gold arches);
   brand cards = logo on off-white with lights. Banner copy "Light up the festive season" is seasonal: swap after the festive period.
   Design previews go in `docs/preview/` (own site.css + layout.js, loads shared files from ../, noindex) before changing live files.
B. Filters/search UX – filters in `compute()`/`renderAttrs()`; Similar styles in `similar()`; search is plain substring.
   4 Nov: Kidswear, Menswear, Style Union, Kisah, Kalpraag removed (EXCLUDED_CATEGORIES / REMOVED_SOURCES); styles whose
   own tags say exactly "Men"/"Menswear" (no women tag) are dropped too (tagged_menswear).
   Crafts: fixed ids in CRAFT_RULES (scraper.py); every clothing style gets 1+ crafts or exactly one bucket
   (Embroidered/Printed/Solid/Not specified). Title + type first, description only if the title names none.
   No brand tags, no brand-wide defaults (Garima: check every style). "Bandhani print" etc. -> Printed (other).
   Hand fixes: data/craft_overrides.json. Write-ups: data/crafts.json (casual, <=100 words, sourced) -> docs/crafts.json.
   Craft pages = #/shop?a=craft:<Name>; craft pages need 20+ in-stock styles.
   LIVE 4 Nov (Garima approved): craft pages, grouped Craft filter (replaces Work/Print groups), 36 home craft tiles.
   Home tiles are set by a DOMContentLoaded wrapper of renderHome() at the end of js/filters.js; workstream A may
   move it into renderHome() in layout.js and delete that block. docs/preview-b/ = B's preview folder for next changes.
C. Going live – custom domain saubag.in (Hostinger suggested; needs 4 A records 185.199.108-111.153 + CNAME www,
   `docs/CNAME`, Enforce HTTPS), affiliate links via `outLink()` in index.html (Cuelinks/vCommission/Shopify Collabs),
   About/privacy/disclosure/takedown pages, SEO pages + sitemap, analytics.
   Failing brands: Koskii, Nishorama, Aarke, Ensemble, Aramya, Soch, Garden Vareli, Global Desi (blocked/not Shopify);
   Shobitam, Kalki (non-INR prices); Cilory (unsupported).
