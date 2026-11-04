/* Shared core: settings, data loading, compare, routing. Change with care; both workstreams depend on it. */
/* ------------------------------------------------------------------
   SETTINGS - edit these
------------------------------------------------------------------- */
const SITE_NAME = "saubag";
// Order the categories appear in the filter (must match the scraper's names)
const CATEGORY_ORDER = ["Kurta sets", "Co-ord sets", "Kurtas", "Dresses", "Tops & shirts", "Bottoms",
  "Lehengas", "Sarees", "Jackets & overlays", "Nightwear & loungewear", "Accessories", "Other"];
const PAGE_SIZE = 48;
// When you get affiliate links, wrap product URLs here, e.g.
// return "https://your-network.example/track?url=" + encodeURIComponent(url);
function outLink(url, product) { return url; }

const COLOUR_HEX = {
  Black: "#1B1B1F", White: "#FFFFFF", Beige: "#E8D9BC", Brown: "#7B4A2D", Red: "#C62828",
  Maroon: "#7A1F2B", Pink: "#E58FAE", Orange: "#F08A3C", Yellow: "#E8B931", Green: "#2E7D4F",
  Blue: "#2F4A9E", Purple: "#6B3FA0", Grey: "#9096A3", Gold: "#C9A23F",
  Multicolour: "conic-gradient(#E58FAE, #E8B931, #2E7D4F, #2F4A9E, #6B3FA0, #E58FAE)", Other: "#EEF0F6"
};
/* ------------------------------------------------------------------ */
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = u => /^https?:\/\//i.test(u || "") ? u : "#";
const rs = n => "₹" + Math.round(n).toLocaleString("en-IN");
const split = s => (s || "").split("|").map(x => x.trim()).filter(Boolean);

let ALL = [];
const st = { cats: new Set(), brands: new Set(), price: "all", disc: 0, sizes: new Set(), colours: new Set(), stock: true, q: "", sort: "rel", shown: PAGE_SIZE, bq: "", allBrands: false, attr: {} };
let META = { labels: {}, order: {}, groupsFor: {} };  // Indian-wear detail groups, from products.json
// Shopify images can be resized by the CDN: ask for ~500px instead of full size
function imgUrl(u) {
  if (!u) return "";
  if (u.startsWith("//")) u = "https:" + u;
  if (/\/cdn\/shop\/|cdn\.shopify\.com/.test(u) && !/[?&]width=/.test(u)) u += (u.includes("?") ? "&" : "?") + "width=500";
  return u;
}

// [3, 7] -> { work: ["Chikankari"], fabric: ["Cotton"] }
function attrGroups(ai, AT) {
  const A = {};
  for (const k of ai || []) { const [g, v] = AT[k] || []; if (g) (A[g] || (A[g] = [])).push(v); }
  return A;
}

function finish(p, i) {
  p.i = i;
  p.colours = [...new Set([p.colour, ...(p.vers || []).map(v => v.colour)])];
  p.disc = p.mrp > p.price ? Math.round((p.mrp - p.price) / p.mrp * 100) : 0;
  p.q = (p.title + " " + p.source + " " + p.colour + " " + p.category + " " + Object.values(p.A || {}).flat().join(" ")).toLowerCase();
  return p;
}

function parseCompact(d) {
  if (d.attr_labels) META = { labels: d.attr_labels, order: d.attr_order || {}, groupsFor: d.groups_for || {} };
  const AT = (d.attrs || []).map(a => { const k = a.indexOf(":"); return [a.slice(0, k), a.slice(k + 1)]; });
  return d.p.map(([si, ci, title, url, price, mrp, co, mask, stock, image, ai, vs], i) => {
    const src = d.sources[si];
    const sizes = [];
    for (let k = 0; k < d.sizes.length; k++) if (mask & (1 << k)) sizes.push(d.sizes[k]);
    return finish({ source: src.n, category: d.cats[ci], title, url: url.startsWith("http") ? url : src.b + url,
      price, mrp: mrp || price, colour: d.colours[co] || "Other", sizes, inStock: stock === 1, image: imgUrl(image),
      A: attrGroups(ai, AT),
      vers: (vs || []).map(([vc, vu, vi, vst]) => ({ colour: d.colours[vc] || "Other", url: vu.startsWith("http") ? vu : src.b + vu, image: imgUrl(vi), inStock: vst === 1 })) }, i);
  });
}

function showUpdated(u) {
  if (u) $("updated").textContent = "Last updated " + new Date(u).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) + ". ";
}

async function load() {
  $("filters").innerHTML = FILTERS_HTML;
  $("logo").textContent = SITE_NAME;
  const opts = { cache: "no-cache" };  // reuse the browser's copy unless the file changed
  const full = fetch("products.json", opts).then(r => r.ok ? r.json() : null).catch(() => null);
  try {
    const bd = await fetch("brands.json", opts).then(r => r.ok ? r.json() : null);
    if (bd) { BRANDS = bd.brands; BRAND_BY = Object.fromEntries(BRANDS.map(b => [b.slug, b])); }
  } catch (e) {}
  let started = false;
  const start = list => {
    ALL = list; BY_I = list;
    if (!started) {
      started = true;
      bind(); cmpBind(); simBind();
      window.addEventListener("hashchange", route);
      route();
    } else if (VIEW === "home") renderHome();
    else if (VIEW === "shop") render();
    cmpRestore();
  };
  try {
    // 1) small first part: shows products straight away
    const first = await fetch("products-first.json", opts).then(r => r.ok ? r.json() : null).catch(() => null);
    if (first && first.p.length) {
      start(parseCompact(first));
      showUpdated(first.updated);
      if (first.total > first.p.length) $("loading").hidden = false;
    }
    // 2) everything
    const d = await full;
    if (d) { start(parseCompact(d)); showUpdated(d.updated); }
    else if (!started) throw new Error("no product file");
  } catch (e) {
    if (!started) { $("title").textContent = "Couldn't load products"; $("sub").textContent = "The product file is missing or unreadable."; }
  }
  $("loading").hidden = true;
}

/* ---------------- compare (up to 4 styles) ---------------- */
const CMP_MAX = 4, CMP_KEY = "saubag-compare";
let CMP = new Map();  // url -> product
function cmpSave() { try { localStorage.setItem(CMP_KEY, JSON.stringify([...CMP.keys()])); } catch (e) {} }
function cmpRestore() {
  let urls = [];
  try { urls = JSON.parse(localStorage.getItem(CMP_KEY) || "[]"); } catch (e) {}
  const byUrl = new Map(ALL.map(p => [p.url, p]));
  CMP = new Map(urls.filter(u => byUrl.has(u)).slice(0, CMP_MAX).map(u => [u, byUrl.get(u)]));
  cmpBar();
}
function cmpToggle(url) {
  if (CMP.has(url)) CMP.delete(url);
  else {
    if (CMP.size >= CMP_MAX) { cmpBar(`Up to ${CMP_MAX} styles. Remove one first.`); clearTimeout(cmpBar.t); cmpBar.t = setTimeout(() => cmpBar(), 3000); return; }
    const p = ALL.find(x => x.url === url); if (p) CMP.set(url, p);
  }
  cmpSave(); cmpBar();
  document.querySelectorAll(`.cmpbtn[data-cmp="${CSS.escape(url)}"]`).forEach(b => {
    const on = CMP.has(url), t = CMP.get(url)?.title || "";
    b.setAttribute("aria-pressed", on); b.innerHTML = (on ? ICON_TICK : ICON_PLUS) + `<span>${on ? "Added" : "Compare"}</span>`;
  });
  if ($("cmp").open) cmpRender();
}
function cmpBar(msg) {
  const n = CMP.size;
  $("cmpbar").hidden = n === 0;
  const thumbs = [...CMP.values()].map(p => p.image ? `<img src="${esc(p.image)}" alt="" onerror="this.style.visibility='hidden'">` : '<span class="empty-slot"></span>');
  while (thumbs.length < CMP_MAX) thumbs.push('<span class="empty-slot" aria-hidden="true"></span>');
  $("cmpthumbs").innerHTML = thumbs.join("");
  $("cmpmsg").textContent = msg || (n < 2 ? "Add one more style to compare" : `${n} styles selected`);
  $("cmpgo").disabled = n < 2;
  $("cmpgo").textContent = n >= 2 ? `Compare ${n}` : "Compare";
}
function cmpRender() {
  const ps = [...CMP.values()];
  if (ps.length < 2) { $("cmp").close(); return; }
  const low = Math.min(...ps.map(p => p.price));
  const cell = (fn) => ps.map(p => `<td>${fn(p)}</td>`).join("");
  const rows = [
    ["", p => p.image ? `<img src="${esc(p.image)}" alt="${esc(p.title)}" onerror="this.style.visibility='hidden'">` : ""],
    ["Brand", p => `<span class="src">${esc(p.source)}</span>`],
    ["Style", p => `<div class="cname">${esc(p.title)}</div>`],
    ["Price", p => `<div class="cprice">${rs(p.price)}</div>${p.price === low ? '<span class="best">Lowest price</span>' : ""}`],
    ["MRP", p => p.disc > 0 ? `<s>${rs(p.mrp)}</s>` : rs(p.mrp)],
    ["Discount", p => p.disc > 0 ? `${p.disc}% off` : "—"],
    ["Category", p => esc(p.category)],
    ["Colour", p => p.colours.map(c => `<span style="display:inline-flex;align-items:center;gap:6px;margin-right:10px"><span class="dot" style="background:${COLOUR_HEX[c] || COLOUR_HEX.Other}"></span>${esc(c)}</span>`).join("")],
    ["Sizes", p => p.sizes.length ? esc(p.sizes.join(", ")) : "See brand's site"],
    ["Stock", p => p.inStock ? "In stock" : "Out of stock"],
    ["", p => `<a class="go" href="${esc(safeUrl(outLink(p.url, p)))}" target="_blank" rel="noopener sponsored">View on ${esc(p.source)}</a>
      <button type="button" class="linkbtn rm" data-cmp="${esc(p.url)}">Remove</button>`]
  ];
  $("cmptable").innerHTML = `<table class="ctable"><tbody>${rows.map(([h, fn]) => `<tr><th scope="row">${h}</th>${cell(fn)}</tr>`).join("")}</tbody></table>`;
}
function cmpBind() {
  for (const id of ["cards", "hnew"]) $(id).addEventListener("click", e => { const b = e.target.closest(".cmpbtn"); if (b) cmpToggle(b.dataset.cmp); });
  $("cmptable").addEventListener("click", e => { const b = e.target.closest(".rm"); if (b) cmpToggle(b.dataset.cmp); });
  $("cmpclear").addEventListener("click", () => { const urls = [...CMP.keys()]; urls.forEach(u => cmpToggle(u)); });
  $("cmpgo").addEventListener("click", () => { cmpRender(); $("cmp").showModal(); });
  $("cmpclose").addEventListener("click", () => $("cmp").close());
  $("cmp").addEventListener("click", e => { if (e.target === $("cmp")) $("cmp").close(); });
}

// #/  #/shop?cat=..&a=work:Chikankari&price=..&brand=..&q=..  #/brands  #/brand/<slug>
let VIEW = "";
function route() {
  const h = location.hash.replace(/^#\/?/, "");
  const [path, qs] = h.split("?");
  const params = new URLSearchParams(qs || "");
  let view = "home", brand = null;
  if (path === "shop") view = "shop";
  else if (path === "brands") view = "brands";
  else if (path.startsWith("brand/")) { view = "shop"; brand = BRAND_BY[decodeURIComponent(path.slice(6))] || null; }
  else if (new URLSearchParams(location.search).get("category")) { view = "shop"; params.set("cat", new URLSearchParams(location.search).get("category")); }
  VIEW = view;
  ["home", "brands", "shop"].forEach(v => $("view-" + v).hidden = v !== view);
  const cur = brand ? "brands" : view;
  document.querySelectorAll("nav.top a").forEach(a => a.dataset.nav === cur ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  if (view === "shop") {
    const fromLink = brand || [...params.keys()].length;
    if (fromLink) {
      st.cats.clear(); st.brands.clear(); st.sizes.clear(); st.colours.clear(); st.attr = {}; st.price = "all"; st.disc = 0; st.q = ""; $("q").value = "";
      for (const c of params.getAll("cat")) st.cats.add(c);
      for (const b of params.getAll("brand")) st.brands.add(b);
      if (brand) st.brands.add(brand.n);
      for (const a of params.getAll("a")) { const k = a.indexOf(":"); if (k > 0) (st.attr[a.slice(0, k)] || (st.attr[a.slice(0, k)] = new Set())).add(a.slice(k + 1)); }
      if (params.get("price")) st.price = params.get("price");
      if (params.get("q")) { st.q = params.get("q"); $("q").value = st.q; }
      st.shown = PAGE_SIZE;
    }
    renderBrandHead(brand);
    render();
  } else if (view === "home") { renderHome(); document.title = `${SITE_NAME} | India's ethnic-wear brands, in one place`; }
  else { renderBrandsPage(); document.title = `Brands | ${SITE_NAME}`; }
  if (route.last !== location.hash) window.scrollTo(0, 0);
  route.last = location.hash;
}


load();