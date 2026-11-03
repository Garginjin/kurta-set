# Kurta set aggregator

One website showing kurta sets from Jaipur Handblock, Label Kanupriya and Zlaata,
with filters for brand, price, discount, size, colour and stock.
Products refresh automatically every 6 hours.

## What's in this folder

| File | What it does |
|---|---|
| `docs/index.html` | The website |
| `docs/listings.json` | The product data the website reads (the scraper rewrites it) |
| `docs/listings.csv` | The same data, for Excel / Google Sheets |
| `scraper.py` | Pulls products from the brand sites |
| `.github/workflows/refresh.yml` | Runs the scraper every 6 hours and republishes the site |

## Put it online (one time, about 15 minutes)

1. **Make a GitHub account** at github.com (free) if you don't have one.
2. **Create a repository**: click **+** (top right) → **New repository**.
   Name it e.g. `kurta-sets`, choose **Public** (free hosting needs Public), click **Create repository**.
3. **Upload the files**: on the new repo page click **uploading an existing file**.
   Drag in `scraper.py`, `README.md` and the whole `docs` folder. Click **Commit changes**.
4. **Add the auto-refresh job** (it lives in a hidden folder, so add it by hand):
   **Add file → Create new file**. In the name box type exactly
   `.github/workflows/refresh.yml`, paste in the contents of `refresh.yml` (a copy sits next to this README), click **Commit changes**.
5. **Turn on hosting**: **Settings → Pages**. Under *Build and deployment → Source* pick **GitHub Actions**.
6. **Allow the job to save data**: **Settings → Actions → General → Workflow permissions** →
   **Read and write permissions** → **Save**.
7. **Run it the first time**: **Actions** tab → **Refresh products and publish site** → **Run workflow**.
   After 1–3 minutes the run turns green. Your site is live at
   `https://<your-github-username>.github.io/kurta-sets/`

From then on it refreshes itself every 6 hours. No laptop or Colab needed.

## Everyday changes

- **Site name**: open `docs/index.html` on GitHub → pencil icon → change `const SITE_NAME = "[SITE NAME]"`. Commit.
- **Add a brand or category**: edit the `SITES` block at the top of `scraper.py`.
  Any Shopify brand works by adding one line with its site address and collection name.
- **Refresh right now**: Actions → Refresh products and publish site → Run workflow.
- **Affiliate links**: when you have them, edit `outLink()` in `docs/index.html`.

## If something looks wrong

- **A brand's products stopped updating**: open the latest run in **Actions** and look for
  `WARNING - no fresh data for: ...`. The site keeps showing that brand's last good data,
  so nothing disappears, but the brand may have changed its site or blocked the refresh.
- **GitHub emails that the scheduled job was paused** (happens after long inactivity):
  Actions tab → the workflow → **Enable workflow**.
- **Preview on your laptop**: in this folder run `python -m http.server -d docs 8000`,
  then open http://localhost:8000 (opening index.html directly won't load the data).
