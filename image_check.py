"""Free image check (CLIP): what does each product PHOTO show?

Runs on GitHub (see .github/workflows/image-check.yml), never on the site.
Report only: it does not change categories. It writes
  data/image_checks.json.gz   image url -> [label, confidence, 2nd label, 2nd confidence, date]  (cache)
  data/image_review.csv       products where the photo disagrees with the title rules
  data/image_check_summary.md counts + how often photo and rules agree
Which products: all in-stock "Other", the cheapest per category, and a random sample per category
(to measure accuracy). Already-checked images are skipped, so later runs only do new ones.
"""
import csv, gzip, io, json, os, random, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import requests
from PIL import Image

MAX_NEW = int(os.environ.get("MAX_NEW", "120000"))
GENDER_CACHE = "data/image_gender.json.gz"   # image url -> [p_man, p_woman, p_no_person]
# every in-stock product in these categories gets the man/woman check
GENDER_CATS = {"Kurta sets", "Co-ord sets", "Kurtas", "Dresses", "Tops & shirts", "Pants", "Skirts", "Lehengas", "Sarees",
               "Jackets & overlays", "Dupattas", "Nightwear & loungewear", "Other"}
GENDER = {
    "man": ["a photo of a man wearing clothes", "a male model posing", "a man wearing a kurta", "a bearded man"],
    "woman": ["a photo of a woman wearing clothes", "a female model posing", "a woman wearing a kurta", "a woman wearing a saree"],
    "none": ["clothing laid flat with no person", "a garment on a hanger", "folded fabric", "a product photo with no model"],
}
CHEAPEST, SAMPLE = 200, 200
CACHE = "data/image_checks.json.gz"

# label -> prompts. Kept short and visual.
LABELS = {
    "Kurta set": ["a woman wearing a long kurta with matching pants and a dupatta", "a woman wearing an Indian salwar suit"],
    "Kurta": ["a woman wearing a long Indian kurta tunic"],
    "Saree": ["a woman wearing a saree draped over her shoulder", "a folded silk saree"],
    "Lehenga": ["a woman wearing a flared lehenga skirt and blouse"],
    "Dress": ["a woman wearing a western dress", "a woman wearing a long gown"],
    "Co-ord set": ["a woman wearing a matching top and trousers co-ord set"],
    "Top": ["a woman wearing a short top or shirt", "a blouse"],
    "Bottom": ["a pair of trousers, palazzo pants or a skirt"],
    "Jacket": ["a woman wearing a jacket or cape"],
    "Dupatta / stole": ["a dupatta, stole or shawl", "a folded scarf"],
    "Fabric": ["folded unstitched fabric", "a length of printed cloth"],
    "Jewellery": ["jewellery: earrings, a necklace or bangles"],
    "Bag": ["a handbag, potli or clutch"],
    "Footwear": ["a pair of shoes, sandals or juttis"],
    "Home": ["a cushion cover or bedsheet", "home decor or a kitchen item", "a table cloth or towel"],
    "Man": ["a man wearing clothes", "a man in a kurta or sherwani"],
    "Child": ["a child wearing clothes", "a little girl in a dress"],
    "Innerwear": ["a bra or lingerie"],
    "Turban": ["a turban"],
    "Text / chart": ["a size chart or text on a plain background"],
}
HIDE = {"Man", "Child", "Innerwear", "Home", "Turban"}
ACCESSORY = {"Jewellery", "Bag", "Footwear", "Dupatta / stole"}
# rule category -> photo labels that count as agreeing
AGREE = {
    "Kurta sets": {"Kurta set", "Kurta", "Co-ord set", "Fabric", "Dupatta / stole"},
    "Kurtas": {"Kurta", "Kurta set", "Dress", "Top"},
    "Co-ord sets": {"Co-ord set", "Kurta set", "Top", "Bottom"},
    "Dresses": {"Dress", "Kurta", "Kurta set", "Lehenga"},
    "Tops & shirts": {"Top", "Co-ord set", "Kurta"},
    "Bottoms": {"Bottom", "Co-ord set", "Kurta set"},
    "Lehengas": {"Lehenga", "Dress", "Saree"},
    "Sarees": {"Saree", "Lehenga", "Fabric", "Dupatta / stole"},
    "Jackets & overlays": {"Jacket", "Kurta", "Co-ord set", "Top"},
    "Nightwear & loungewear": {"Co-ord set", "Top", "Bottom", "Kurta set", "Dress", "Kurta"},
    "Accessories": ACCESSORY | {"Fabric"},
    "Other": set(),
}
FLOOR = {"Kurta sets": 400, "Co-ord sets": 400, "Kurtas": 250, "Dresses": 300, "Sarees": 300,
         "Lehengas": 800, "Tops & shirts": 200, "Jackets & overlays": 300, "Bottoms": 200}


def small(url):
    if url.startswith("//"):
        url = "https:" + url
    if "cdn.shopify.com" in url or "/cdn/shop/" in url:
        return url + ("&" if "?" in url else "?") + "width=256"
    return url


def fetch(url):
    try:
        r = requests.get(small(url), timeout=15, headers={"User-Agent": "saubag-image-check"})
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail((336, 336))
        return url, im
    except Exception:
        return url, None


def main():
    d = json.load(open("docs/products.json"))
    cats, src = d["cats"], [s["n"] for s in d["sources"]]
    rows = [r for r in d["p"] if r[8] == 1 and r[9]]
    try:
        cache = json.load(gzip.open(CACHE, "rt"))
    except (OSError, ValueError):
        cache = {}

    random.seed(42)
    by = {}
    for r in rows:
        by.setdefault(cats[r[1]], []).append(r)
    pick, seen, sample_ids = [], set(), set()
    for c, rs in by.items():
        samp = [] if c == "Other" else random.sample(rs, min(SAMPLE, len(rs)))
        sample_ids |= {id(r) for r in samp}
        chosen = rs if c == "Other" else (samp + sorted(rs, key=lambda r: r[4])[:CHEAPEST]
                                          + [r for r in rs if c in FLOOR and r[4] < FLOOR[c]])
        for r in chosen:
            if id(r) not in seen:
                seen.add(id(r))
                pick.append(r)
    try:
        gcache = json.load(gzip.open(GENDER_CACHE, "rt"))
    except (OSError, ValueError):
        gcache = {}
    gpick = [r for r in rows if cats[r[1]] in GENDER_CATS]
    todo = list(dict.fromkeys([r[9] for r in pick if r[9] not in cache or r[9] not in gcache]
                              + [r[9] for r in gpick if r[9] not in gcache]))[:MAX_NEW]
    print(f"products picked {len(pick):,}; new images to check {len(todo):,} (cache {len(cache):,})", flush=True)

    if todo:
        import torch, open_clip
        torch.set_num_threads(os.cpu_count() or 4)
        model, _, prep = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
        tok = open_clip.get_tokenizer("ViT-B-32")
        model.eval()
        names = list(LABELS)
        with torch.no_grad():
            T = []
            for n in names:
                e = model.encode_text(tok([f"a product photo: {p}" for p in LABELS[n]]))
                e = e / e.norm(dim=-1, keepdim=True)
                T.append(e.mean(0))
            T = torch.stack(T)
            T = T / T.norm(dim=-1, keepdim=True)
            G = []
            for k in ("man", "woman", "none"):
                e = model.encode_text(tok(GENDER[k]))
                e = e / e.norm(dim=-1, keepdim=True)
                G.append(e.mean(0))
            G = torch.stack(G)
            G = G / G.norm(dim=-1, keepdim=True)
        t0, done = time.time(), 0
        with ThreadPoolExecutor(24) as ex:
            for i in range(0, len(todo), 64):
                batch = [(u, im) for u, im in ex.map(fetch, todo[i:i + 64]) if im is not None]
                for u in todo[i:i + 64]:
                    cache.setdefault(u, ["(no image)", 0, "", 0, str(date.today())])
                if not batch:
                    continue
                with torch.no_grad():
                    x = torch.stack([prep(im) for _, im in batch])
                    f = model.encode_image(x)
                    f = f / f.norm(dim=-1, keepdim=True)
                    p = (100 * f @ T.T).softmax(-1)
                    pg = (100 * f @ G.T).softmax(-1)
                for (u, _), gr in zip(batch, pg):
                    gcache[u] = [round(float(x), 3) for x in gr]
                for (u, _), pr in zip(batch, p):
                    v, ix = pr.topk(2)
                    cache[u] = [names[ix[0]], round(float(v[0]), 3), names[ix[1]], round(float(v[1]), 3), str(date.today())]
                done += len(batch)
                if (i // 64) % 20 == 0:
                    print(f"  {i + 64:,}/{len(todo):,} checked, {done / max(time.time() - t0, 1):.1f} img/s", flush=True)
        with gzip.open(CACHE, "wt") as fh:
            json.dump(cache, fh, separators=(",", ":"))
        with gzip.open(GENDER_CACHE, "wt") as fh:
            json.dump(gcache, fh, separators=(",", ":"))

    # ---- review list + summary ------------------------------------------------
    out, agree = [], {}
    for r in pick:
        res = cache.get(r[9])
        if not res or res[0] == "(no image)":
            continue
        c, lab, conf = cats[r[1]], res[0], res[1]
        ok = lab in AGREE.get(c, set())
        if id(r) in sample_ids:
            a = agree.setdefault(c, [0, 0]); a[1] += 1; a[0] += ok or conf < 0.5
        flag = None
        if lab in HIDE and conf >= 0.5:
            flag = "photo shows something we hide"
        elif c == "Other" and conf >= 0.5:
            flag = "Other: photo suggests a category"
        elif not ok and conf >= 0.6 and c not in ("Other",):
            flag = "photo disagrees with category"
        if flag:
            out.append([flag, src[r[0]], c, lab, conf, res[2], res[3], r[4], r[2], r[3], r[9]])
    out.sort(key=lambda x: (x[0], -x[4]))
    with open("data/image_review.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["flag", "brand", "rule category", "photo shows", "confidence", "2nd guess", "2nd conf", "price", "title", "url", "image"])
        w.writerows(out)
    men = [r for r in gpick if r[9] in gcache and gcache[r[9]][0] >= 0.85]
    with open("data/image_men.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["p_man", "brand", "category", "price", "title", "url", "image"])
        for r in sorted(men, key=lambda r: -gcache[r[9]][0]):
            w.writerow([gcache[r[9]][0], src[r[0]], cats[r[1]], r[4], r[2], r[3], r[9]])
    from collections import Counter as _C
    lines = [f"# Image check {date.today()}", "",
             f"- Man/woman check: {sum(1 for r in gpick if r[9] in gcache):,} of {len(gpick):,} clothing photos;"
             f" photo >= 85% a man: {len(men):,} (data/image_men.csv)",
             "- Men by brand: " + ", ".join(f"{b} {n}" for b, n in _C(src[r[0]] for r in men).most_common(15)), "",
             f"- Products looked at: {len(pick):,} (all in-stock Other, cheapest {CHEAPEST} + below-floor + random {SAMPLE} per category)",
             f"- Images checked so far (cache): {len(cache):,}", f"- Flagged for review: {len(out):,}", "",
             "## Flags", ""]
    from collections import Counter
    for (fl, c, lab), n in Counter((x[0], x[2], x[3]) for x in out).most_common(40):
        lines.append(f"- {fl} | rule: {c} | photo: {lab} | {n}")
    lines += ["", "## Random sample: photo agrees with category (or photo unsure, conf < 0.5)", ""]
    for c, (a, n) in sorted(agree.items()):
        lines.append(f"- {c}: {a}/{n} = {100 * a / max(n, 1):.0f}%")
    open("data/image_check_summary.md", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
