/* Filters, search results and Similar styles. Owned by the filters/search workstream (B). */
// The filter column's markup (index.html has an empty <aside id="filters">)
const FILTERS_HTML = `
      <div class="ftop"><h2>Filters</h2><button type="button" class="linkbtn" id="clear" hidden>Clear all</button></div>
      <details class="fs" open data-g="category"><summary>Category<span class="sel" hidden></span><svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></summary>
        <fieldset class="fbody"><legend class="visually-hidden">Category</legend><div id="f-cat"></div></fieldset></details>
      <div id="f-attrs"></div>
      <details class="fs" open data-g="brand"><summary>Brand<span class="sel" hidden></span><svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></summary>
        <fieldset class="fbody"><legend class="visually-hidden">Brand</legend>
          <input type="search" id="bq" class="bq" aria-label="Search brands" placeholder="Search brands">
          <div id="f-brand"></div>
          <button type="button" class="linkbtn" id="bmore" hidden>Show all brands</button>
        </fieldset></details>
      <details class="fs" open data-g="price"><summary>Price<span class="sel" hidden></span><svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></summary>
        <fieldset class="fbody"><legend class="visually-hidden">Price</legend><div id="f-price"></div></fieldset></details>
      <details class="fs" data-g="disc"><summary>Discount<span class="sel" hidden></span><svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></summary>
        <fieldset class="fbody"><legend class="visually-hidden">Discount</legend><div id="f-disc"></div></fieldset></details>
      <details class="fs" data-g="size"><summary>Size<span class="sel" hidden></span><svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></summary>
        <fieldset class="fbody"><legend class="visually-hidden">Size</legend><div class="pills" id="f-size"></div><p class="note" id="size-note"></p></fieldset></details>
      <details class="fs" data-g="colour"><summary>Colour<span class="sel" hidden></span><svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></summary>
        <fieldset class="fbody"><legend class="visually-hidden">Colour</legend><div class="pills" id="f-colour"></div></fieldset></details>
      <label class="opt stock"><input type="checkbox" id="stock" checked> In stock only</label>
`;

const SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL", "5XL", "6XL", "7XL", "8XL", "Free size"];
const BUST = { 30: "XXS", 32: "XXS", 34: "XS", 36: "S", 38: "M", 40: "L", 42: "XL", 44: "XXL", 46: "3XL", 48: "4XL", 50: "5XL", 52: "6XL", 54: "7XL", 56: "8XL" };
// "S (36)", "S - 36", "SMALL", "36" -> "S"; "Set of 3", "Unstitched" -> not a size
function normSize(raw) {
  const t = String(raw).toUpperCase().replace(/[^A-Z0-9]+/g, " ").trim();
  if (!t) return null;
  if (/\bFREE\b|\bONE SIZE\b|\bFS\b|\bFREESIZE\b/.test(t)) return "Free size";
  if (/\bSET\b|STITCH|\bYRS?\b|\bYEARS?\b|\bMONTHS?\b|\bKIDS?\b/.test(t)) return null;
  let m = t.match(/\b([2-8])\s?XL\b/); if (m) return m[1] === "2" ? "XXL" : m[1] + "XL";
  m = t.match(/\b(X{3,8})L\b/); if (m) return m[1].length + "XL";
  const words = [[/\bXXL\b|\bXX L\b|\bDOUBLE XL\b/, "XXL"], [/\bXL\b|\bEXTRA LARGE\b|\bX LARGE\b/, "XL"], [/\bXXS\b/, "XXS"],
    [/\bXS\b|\bEXTRA SMALL\b|\bX SMALL\b/, "XS"], [/\bS\b|\bSMALL\b/, "S"], [/\bM\b|\bMEDIUM\b/, "M"], [/\bL\b|\bLARGE\b/, "L"]];
  for (const [rx, z] of words) if (rx.test(t)) return z;
  m = t.match(/\b(\d{2})\b/); if (m && BUST[+m[1]]) return BUST[+m[1]];
  return null;
}
const normSizes = list => [...new Set(list.map(normSize).filter(Boolean))].sort((a, b) => SIZE_ORDER.indexOf(a) - SIZE_ORDER.indexOf(b));
const PRICE_BUCKETS = [
  { k: "all", label: "Any price", test: () => true },
  { k: "u1000", label: "Under ₹1,000", test: p => p.price < 1000 },
  { k: "1000", label: "₹1,000 – ₹1,999", test: p => p.price >= 1000 && p.price < 2000 },
  { k: "2000", label: "₹2,000 – ₹2,999", test: p => p.price >= 2000 && p.price < 3000 },
  { k: "3000", label: "₹3,000 and above", test: p => p.price >= 3000 }
];
const DISCOUNTS = [[0, "Any discount"], [20, "20% off or more"], [40, "40% off or more"], [60, "60% off or more"]];

// Shown when no category is picked; the rest appear once a category is chosen
// Craft replaces the old "Work & embroidery" and "Print & craft" groups
const ATTR_DEFAULT_GROUPS = ["craft", "fabric", "occasion"];
const ATTR_OPEN = new Set(["craft"]);
const ATTR_HIDDEN = new Set(["work", "print"]);

/* ---------------- crafts: names, families, write-ups (crafts.json) ---------------- */
let CRAFTS = [], CRAFT_BY_NAME = {}, CRAFT_BY_ID = {};
const CRAFT_MIN = 20;
const CRAFT_FAMILIES = ["Embroidery", "Print & dye", "Weave", "Other"];
fetch("crafts.json", { cache: "no-cache" }).then(r => r.ok ? r.json() : null).then(d => {
  if (!d) return;
  CRAFTS = d.crafts.map(c => ({ ...c, family: c.bucket ? "Other" : c.family }));
  CRAFTS.push(OTHERS_INFO);
  CRAFT_BY_NAME = Object.fromEntries(CRAFTS.map(c => [c.name, c]));
  CRAFT_BY_ID = Object.fromEntries(CRAFTS.map(c => [c.id, c]));
  if (typeof VIEW !== "undefined" && VIEW === "shop" && ALL.length) render();
  if (typeof VIEW !== "undefined" && VIEW === "home" && typeof renderHome === "function" && ALL.length) renderHome();
}).catch(() => {});
const craftLink = c => "#/shop?" + new URLSearchParams({ a: "craft:" + c.name }).toString();
// "Others": clothing styles that aren't in any home craft tile. Bottoms, accessories, nightwear, Other stay out.
const OTHERS = "Others";
const OTHERS_SKIP = new Set(["Bottoms", "Jackets & overlays", "Accessories", "Nightwear & loungewear", "Other"]);
const OTHERS_INFO = { id: "others", name: OTHERS, family: "Other", bucket: false, virtual: true, region: "",
  blurb: "Everything else in clothing: styles whose listing doesn't name one of the crafts on our craft tiles. That covers other embroidery, prints, plain styles and pieces the brand doesn't describe. Only kurtas, kurta sets, sarees, co-ords, dresses, tops and lehengas are included.", sources: [] };
let TILE_SET = null;
function tagOthers() {
  if (!CRAFTS.length) return;
  if (!TILE_SET) TILE_SET = new Set(CRAFTS.filter(c => !c.bucket && !c.virtual && c.in_stock >= CRAFT_MIN).map(c => c.name));
  for (const p of ALL) {
    if (p._oth) continue;
    p._oth = 1;
    const cr = p.A.craft;
    if (!cr || OTHERS_SKIP.has(p.category) || cr.some(v => TILE_SET.has(v))) continue;
    cr.push(OTHERS);
    p.q += " others";
  }
}
// One craft picked -> show its write-up above the results
function renderCraftHead(list = []) {
  let box = $("crafthead");
  if (!box) { box = document.createElement("section"); box.id = "crafthead"; box.className = "crafthead"; $("bhead").after(box); }
  const sel = st.attr.craft;
  const c = sel && sel.size === 1 ? CRAFT_BY_NAME[[...sel][0]] : null;
  if (!c || c.bucket || !c.blurb) { box.hidden = true; box.innerHTML = ""; return null; }
  const others = CRAFTS.filter(o => !o.bucket && o.family === c.family && o.id !== c.id && o.in_stock >= CRAFT_MIN);
  const src = (c.sources || []).map((u, i) => `<a href="${esc(safeUrl(u))}" target="_blank" rel="noopener">${i + 1}</a>`).join(" ");
  // Right side: up to 3 in-stock photos from different brands + live facts
  const pics = [], seen = new Set();
  for (const p of list) { if (pics.length >= 3) break; if (!p.image || seen.has(p.source)) continue; seen.add(p.source); pics.push(p); }
  const nb = new Set(list.map(p => p.source)).size;
  const prices = list.map(p => p.price).sort((a, b) => a - b);
  const facts = list.length ? `<p class="cfacts"><b>${list.length.toLocaleString("en-IN")}</b> styles · <b>${nb}</b> ${nb === 1 ? "brand" : "brands"} · <b>${rs(prices[0])} – ${rs(prices[prices.length - 1])}</b></p>` : "";
  box.innerHTML = `<div class="ctext"><p class="eyebrow">${esc(c.family)}${c.region ? " · " + esc(c.region) : ""}</p>
    <h2>${esc(c.name)}</h2><p class="cblurb">${esc(c.blurb)}</p>
    ${src ? `<p class="csrc">Sources: ${src}</p>` : ""}</div>
    <div class="cside">${pics.length ? `<div class="cpics">${pics.map(p => `<a href="${esc(safeUrl(outLink(p.url, p)))}" target="_blank" rel="noopener sponsored" aria-label="${esc(p.title)}">${imgTag(p.image, p.title)}</a>`).join("")}</div>` : ""}${facts}</div>
    ${others.length ? `<div class="cmore"><span>More ${esc(c.family.toLowerCase())}</span>${others.map(o => `<a href="${craftLink(o)}">${esc(o.name)}</a>`).join("")}</div>` : ""}`;
  box.hidden = false;
  return c;
}

function sizeKey(z) { const i = SIZE_ORDER.indexOf(z); return i < 0 ? 999 : i; }

function resetFilters() {
  st.cats.clear(); st.brands.clear(); st.sizes.clear(); st.colours.clear(); st.attr = {};
  st.price = "all"; st.disc = 0; st.q = ""; $("q").value = ""; st.bq = ""; st.shown = PAGE_SIZE;
  render();
}

function bind() {
  let t;
  $("q").addEventListener("input", e => { clearTimeout(t); t = setTimeout(() => {
    st.q = e.target.value; st.shown = PAGE_SIZE;
    if (VIEW !== "shop") { history.replaceState(null, "", "#/shop"); route.last = "#/shop"; VIEW = "shop"; ["home", "brands"].forEach(v => $("view-" + v).hidden = true); $("view-shop").hidden = false; renderBrandHead(null); }
    render(); }, 150); });
  $("sort").addEventListener("change", e => { st.sort = e.target.value; render(); });
  $("stock").addEventListener("change", e => { st.stock = e.target.checked; st.shown = PAGE_SIZE; render(); });
  $("clear").addEventListener("click", () => { st.stock = true; $("stock").checked = true; st.sort = "rel"; $("sort").value = "rel"; resetFilters(); });
  $("more").querySelector("button").addEventListener("click", () => { st.shown += PAGE_SIZE; render(false); });
  $("ftoggle").addEventListener("click", () => {
    const open = $("filters").classList.toggle("open");
    $("ftoggle").setAttribute("aria-expanded", open);
  });
  $("bq").addEventListener("input", e => { st.bq = e.target.value; renderBrands(); });
  $("bmore").addEventListener("click", () => { st.allBrands = !st.allBrands; renderBrands(); });
  $("filters").addEventListener("change", e => {
    const tg = e.target, v = tg.value;
    const sets = { category: st.cats, brand: st.brands, size: st.sizes, colour: st.colours };
    if (sets[tg.name]) { tg.checked ? sets[tg.name].add(v) : sets[tg.name].delete(v); }
    else if (tg.name === "price") st.price = v;
    else if (tg.name === "disc") st.disc = +v;
    else if (tg.name.startsWith("a-")) { const g = tg.name.slice(2), set = st.attr[g] || (st.attr[g] = new Set()); tg.checked ? set.add(v) : set.delete(v); if (!set.size) delete st.attr[g]; }
    else return;
    st.shown = PAGE_SIZE; render();
  });
}

// One pass over all products: builds the result list AND the counts shown next to
// every filter option (each count respects all the *other* active filters).
let LIST = [], COUNTS = {}, NOSIZE = new Set();
function compute() {
  tagOthers();
  const priceOk = PRICE_BUCKETS.find(b => b.k === st.price).test;
  const words = st.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const C = { category: {}, brand: {}, size: {}, colour: {}, attr: {} };
  const ag = Object.keys(st.attr);
  const addA = (g, p) => { const c = C.attr[g] || (C.attr[g] = {}); for (const v of (p.A[g] || [])) c[v] = (c[v] || 0) + 1; };
  const shownGroups = visibleGroups();
  const list = [], nosize = new Set();
  const add = (g, v) => { C[g][v] = (C[g][v] || 0) + 1; };
  for (const p of ALL) {
    if (st.stock && !p.inStock) continue;
    if (words.length && !words.every(w => p.q.includes(w))) continue;
    let fails = 0, failed = "";
    if (st.cats.size && !st.cats.has(p.category)) { fails++; failed = "category"; }
    if (st.brands.size && !st.brands.has(p.source)) { fails++; failed = "brand"; }
    if (!priceOk(p)) { fails++; failed = "price"; }
    if (p.disc < st.disc) { fails++; failed = "disc"; }
    if (st.sizes.size && !p.sizes.some(z => st.sizes.has(z))) { fails++; failed = "size"; }
    if (st.colours.size && !p.colours.some(c => st.colours.has(c))) { fails++; failed = "colour"; }
    for (const g of ag) {
      if (fails > 1) break;
      const vals = p.A[g];
      if (!vals || !vals.some(v => st.attr[g].has(v))) { fails++; failed = "a-" + g; }
    }
    if (fails > 1) continue;
    if (fails === 0) {
      list.push(p);
      add("category", p.category); add("brand", p.source); for (const c of p.colours) add("colour", c);
      for (const z of p.sizes) add("size", z);
      if (!p.sizes.length) nosize.add(p.source);
      for (const g of shownGroups) addA(g, p);
    } else if (failed.startsWith("a-")) addA(failed.slice(2), p);
    else if (failed === "category") add("category", p.category);
    else if (failed === "brand") add("brand", p.source);
    else if (failed === "colour") for (const c of p.colours) add("colour", c);
    else if (failed === "size") { for (const z of p.sizes) add("size", z); if (!p.sizes.length) nosize.add(p.source); }
  }
  LIST = list; COUNTS = C; NOSIZE = nosize;
}

function opt(type, name, value, label, n, checked, extra = "") {
  return `<label class="opt" title="${esc(label)}"><input type="${type}" name="${name}" value="${esc(value)}"${checked ? " checked" : ""}>${extra}<span>${esc(label)}</span>${n !== null ? `<span class="n">${n.toLocaleString("en-IN")}</span>` : ""}</label>`;
}

// options with results, plus anything already ticked (so it can be unticked)
const shownKeys = (counts, selected, order) => {
  const keys = new Set([...Object.keys(counts), ...selected]);
  return order ? [...order.filter(k => keys.has(k)), ...[...keys].filter(k => !order.includes(k))] : [...keys];
};

const BRAND_PREVIEW = 8;
function renderBrands() {
  const bc = COUNTS.brand || {};
  const q = st.bq.trim().toLowerCase();
  let brands = shownKeys(bc, st.brands).sort((a, b) => (st.brands.has(b) - st.brands.has(a)) || (bc[b] || 0) - (bc[a] || 0) || a.localeCompare(b));
  if (q) brands = brands.filter(b => b.toLowerCase().includes(q));
  const total = brands.length;
  const show = q || st.allBrands ? brands : brands.slice(0, BRAND_PREVIEW);
  $("f-brand").innerHTML = show.map(b => opt("checkbox", "brand", b, b, bc[b] || 0, st.brands.has(b))).join("") || '<span class="note">No brand matches</span>';
  $("bmore").hidden = !!q || total <= BRAND_PREVIEW;
  $("bmore").textContent = st.allBrands ? "Show fewer" : `Show all ${total} brands`;
}

// Which detail groups to show: those that fit the picked categories
function visibleGroups() {
  const all = Object.keys(META.labels);
  if (!all.length) return [];
  let gs;
  if (!st.cats.size) gs = ATTR_DEFAULT_GROUPS;
  else { const u = new Set(); for (const c of st.cats) for (const g of (META.groupsFor[c] || [])) u.add(g); gs = all.filter(g => u.has(g)); }
  const groups = [...new Set([...gs.filter(g => all.includes(g)), ...Object.keys(st.attr)])].filter(g => !ATTR_HIDDEN.has(g) || st.attr[g]);
  // Craft is shown for every clothing category, first in the list
  if (all.includes("craft")) return ["craft", ...groups.filter(g => g !== "craft")];
  return groups;
}
// Craft pills grouped by family (Embroidery / Print & dye / Weave / Other)
function craftPills(counts, sel) {
  const keys = shownKeys(counts, sel, META.order.craft);
  if (!CRAFTS.length) return keys.map(v => opt("checkbox", "a-craft", v, v, counts[v] || 0, sel.has(v))).join("");
  return CRAFT_FAMILIES.map(f => {
    const ks = keys.filter(v => (CRAFT_BY_NAME[v] ? CRAFT_BY_NAME[v].family : "Other") === f);
    return ks.length ? `<p class="cfam">${esc(f)}</p><div class="pills">${ks.map(v => opt("checkbox", "a-craft", v, v, counts[v] || 0, sel.has(v))).join("")}</div>` : "";
  }).join("");
}

const CHEV = '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
const ATTR_NOTE = "Based on what each brand writes in its listing. Styles that don't mention this are hidden while it's picked.";
function renderAttrs() {
  const box = $("f-attrs");
  const openNow = new Set([...box.querySelectorAll("details[open]")].map(d => d.dataset.g));
  const known = new Set([...box.querySelectorAll("details")].map(d => d.dataset.g));
  box.innerHTML = visibleGroups().map(g => {
    const counts = (COUNTS.attr || {})[g] || {}, sel = st.attr[g] || new Set();
    const keys = shownKeys(counts, sel, META.order[g]);
    if (!keys.length) return "";
    const open = known.has("a-" + g) ? openNow.has("a-" + g) : (ATTR_OPEN.has(g) || sel.size > 0);
    return `<details class="fs" data-g="a-${g}"${open ? " open" : ""}><summary>${esc(META.labels[g])}<span class="sel"${sel.size ? "" : " hidden"}>${sel.size}</span>${CHEV}</summary>
      <fieldset class="fbody"><legend class="visually-hidden">${esc(META.labels[g])}</legend>${g === "craft" ? craftPills(counts, sel) : `<div class="pills">${
        keys.map(v => opt("checkbox", "a-" + g, v, v, counts[v] || 0, sel.has(v))).join("")}</div>`}
      ${g === "craft" || g === "work" || g === "neck" || g === "sleeve" ? `<p class="note">${ATTR_NOTE}</p>` : ""}</fieldset></details>`;
  }).join("");
}

function renderFilters() {
  const C = COUNTS;
  renderAttrs();
  $("f-cat").innerHTML = shownKeys(C.category, st.cats, CATEGORY_ORDER).map(c => opt("checkbox", "category", c, c, C.category[c] || 0, st.cats.has(c))).join("");
  renderBrands();
  $("f-price").innerHTML = PRICE_BUCKETS.map(b => opt("radio", "price", b.k, b.label, null, st.price === b.k)).join("");
  $("f-disc").innerHTML = DISCOUNTS.map(([v, l]) => opt("radio", "disc", v, l, null, st.disc === v)).join("");
  $("f-size").innerHTML = shownKeys(C.size, st.sizes, SIZE_ORDER).map(z => opt("checkbox", "size", z, z, null, st.sizes.has(z))).join("") || '<span class="note">No size data</span>';
  $("size-note").textContent = NOSIZE.size ? "Some styles show sizes only on the brand's site, so they're hidden when you pick a size." : "";
  $("f-colour").innerHTML = shownKeys(C.colour, st.colours, Object.keys(COLOUR_HEX)).map(c => opt("checkbox", "colour", c, c, null, st.colours.has(c),
    `<span class="dot" aria-hidden="true" style="background:${COLOUR_HEX[c] || COLOUR_HEX.Other}"></span>`)).join("");
  const picked = { category: st.cats.size, brand: st.brands.size, price: +(st.price !== "all"), disc: +(st.disc > 0), size: st.sizes.size, colour: st.colours.size };
  document.querySelectorAll("aside > details.fs").forEach(d => { const n = picked[d.dataset.g] || 0, el = d.querySelector(".sel"); el.hidden = !n; el.textContent = n; });
  const attrN = Object.values(st.attr).reduce((n, s) => n + s.size, 0);
  const active = st.cats.size + st.brands.size + st.sizes.size + st.colours.size + attrN + (st.price !== "all") + (st.disc > 0) + (st.q.trim() ? 1 : 0);
  $("clear").hidden = !active;
  $("clear").textContent = `Clear all (${active})`;
  $("ftoggle").textContent = active ? `Filters (${active})` : "Filters";
}

/* ---------------- similar styles ---------------- */
// Similar = same category, then shared craft details, colour, price band and title words.
const SIM_W = { work: 3, print: 3, silhouette: 2.5, fabric: 2, bottom: 1.5, neck: 1, sleeve: 1, occasion: 0.5, dupatta: 0.5 };
const SIM_N = 12, SIM_PER_BRAND = 3;
const STOP = new Set("a an and the with for of in on by set sets kurta kurtas kurti kurtis suit suits women womens woman pc pcs piece dupatta pant pants palazzo co ord coord style new".split(" "));
let BY_I = [];
function tokens(p) {
  if (p.tk) return p.tk;
  const drop = new Set((p.source + " " + p.colour).toLowerCase().split(/\W+/));
  p.tk = new Set(p.title.toLowerCase().split(/[^a-z]+/).filter(w => w.length > 2 && !STOP.has(w) && !drop.has(w) && !COLOUR_WORDS.has(w)));
  return p.tk;
}
const COLOUR_WORDS = new Set("black white off ivory cream beige brown red maroon pink orange yellow green blue navy purple grey gold silver multicolour multi peach mustard teal olive lilac lavender wine rust coral mint sage magenta fuchsia indigo turquoise".split(" "));
function simScore(a, b) {
  let s = 0; const why = [];
  for (const g in SIM_W) {
    const x = a.A[g], y = b.A[g];
    if (!x || !y) continue;
    const shared = x.filter(v => y.includes(v));
    if (shared.length) { s += SIM_W[g] * shared.length; if (SIM_W[g] >= 2) why.push(...shared); }
  }
  if (a.colour === b.colour && a.colour !== "Other") { s += 2; why.push(a.colour); }
  const r = Math.abs(Math.log(b.price / a.price));
  if (r < Math.LN2) s += 2 * (1 - r / Math.LN2);
  const ta = tokens(a), tb = tokens(b);
  if (ta.size && tb.size) { let n = 0; for (const w of ta) if (tb.has(w)) n++; s += 3 * n / (ta.size + tb.size - n); }
  return [s, why];
}
function similar(p) {
  const scored = [];
  for (const q of ALL) {
    if (q === p || q.category !== p.category || !q.inStock || q.title === p.title) continue;
    const [sc, why] = simScore(p, q);
    if (sc > 2) scored.push([sc, q, why]);
  }
  scored.sort((x, y) => y[0] - x[0]);
  const out = [], per = {};
  for (const row of scored) {
    const b = row[1].source;
    if ((per[b] || 0) >= SIM_PER_BRAND) continue;
    per[b] = (per[b] || 0) + 1; out.push(row);
    if (out.length >= SIM_N) break;
  }
  return out;
}
function simOpen(i) {
  const p = BY_I[i]; if (!p) return;
  const tags = Object.entries(p.A).filter(([g]) => SIM_W[g] >= 1).map(([, v]) => v).flat();
  $("simtop").innerHTML = `${p.image ? `<img src="${esc(p.image)}" alt="">` : ""}<div><span class="src">${esc(p.source)}</span><div class="cname">${esc(p.title)}</div>
    <div class="why">${rs(p.price)} · ${esc(p.category)}${tags.length ? " · <b>" + tags.map(esc).join(", ") + "</b>" : ""}<br>Matched on category, craft details, colour, price and style words. In-stock styles only, up to ${SIM_PER_BRAND} per brand.</div></div>`;
  const res = similar(p);
  $("simgrid").innerHTML = res.length
    ? res.map(([, q, why]) => card(q, why.length ? `<span class="match">Same: ${esc([...new Set(why)].slice(0, 3).join(", "))}</span>` : "")).join("")
    : '<p class="note">No close matches in stock right now.</p>';
  $("simgrid").scrollTop = 0;
  if (!$("sim").open) $("sim").showModal();
}
function simBind() {
  for (const id of ["cards", "hnew", "simgrid"]) $(id).addEventListener("click", e => { const w = e.target.closest(".sw"); if (w) swatchPick(w); });
  for (const id of ["cards", "hnew"]) $(id).addEventListener("click", e => { const b = e.target.closest(".simbtn"); if (b) simOpen(+b.dataset.sim); });
  $("simgrid").addEventListener("click", e => { const b = e.target.closest(".cmpbtn"); if (b) cmpToggle(b.dataset.cmp); });
  $("simclose").addEventListener("click", () => $("sim").close());
  $("sim").addEventListener("click", e => { if (e.target === $("sim")) $("sim").close(); });
}

function render(recompute = true) {
  if (recompute) {
    compute();
    renderFilters();
    const by = { lo: (a, b) => a.price - b.price, hi: (a, b) => b.price - a.price, disc: (a, b) => b.disc - a.disc, rel: (a, b) => a.i - b.i };
    LIST.sort((a, b) => (b.inStock - a.inStock) || by[st.sort](a, b));
  }
  const list = LIST;
  const sel = CATEGORY_ORDER.filter(c => st.cats.has(c)).concat([...st.cats].filter(c => !CATEGORY_ORDER.includes(c)));
  const one = st.brands.size === 1 && !$("bhead").hidden ? [...st.brands][0] : "";
  const craft = renderCraftHead(list);
  let label = !sel.length ? (one ? `All ${one} styles` : "All styles") : sel.length <= 2 ? sel.join(" & ") : `${sel.length} categories`;
  if (craft) label = sel.length ? `${craft.name} ${label.toLowerCase()}` : `${craft.name} styles`;
  $("title").textContent = label;
  document.title = `${label} | ${SITE_NAME}`;
  const nb = new Set(list.map(p => p.source)).size;
  $("sub").textContent = `${list.length.toLocaleString("en-IN")} ${list.length === 1 ? "style" : "styles"} from ${nb} ${nb === 1 ? "brand" : "brands"}`;
  $("cards").innerHTML = list.length
    ? list.slice(0, st.shown).map(p => card(p)).join("")
    : `<div class="empty"><p>Nothing matches these filters</p><button type="button" class="linkbtn" onclick="document.getElementById('clear').click()">Clear filters</button></div>`;
  $("cards").style.display = list.length ? "" : "block";
  $("more").hidden = list.length <= st.shown;
}

/* ---------------- home "Shop by craft" tiles (approved 4 Nov) ----------------
   Every craft with 20+ in-stock styles, biggest first, each linking to its craft page.
   renderHome() lives in layout.js (workstream A); this wraps it once all scripts have loaded.
   A can move this into renderHome() later and delete this block. */
document.addEventListener("DOMContentLoaded", () => {
  if (typeof renderHome !== "function") return;
  const base = renderHome;
  renderHome = function () {
    base();
    if (!CRAFTS.length) return;
    const used = new Set();
    tagOthers();
    const list = CRAFTS.filter(c => !c.bucket && !c.virtual && c.in_stock >= CRAFT_MIN).sort((a, b) => b.in_stock - a.in_stock);
    OTHERS_INFO.in_stock = ALL.reduce((n, p) => n + (p.inStock && p.A.craft && p.A.craft.includes(OTHERS) ? 1 : 0), 0);
    const tile = (c, p) => `<a class="tile" href="${craftLink(c)}"><div class="ti">${p ? imgTag(p.image, "") : ""}</div><b>${esc(c.name)}</b><span>${nf(c.in_stock)} styles</span></a>`;
    $("hcrafts").innerHTML = list.map(c => tile(c, pickImg(q => q.A.craft && q.A.craft.includes(c.name), used))).join("")
      + (OTHERS_INFO.in_stock ? tile(OTHERS_INFO, pickImg(q => q.A.craft && q.A.craft.includes(OTHERS) && q.category === "Kurta sets", used)) : "");
  };
});
