/* Product cards, brand cards, home page and brands page. Owned by the design workstream (A). */
const ICON_PLUS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>';
const ICON_TICK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" aria-hidden="true"><path d="m5 12 5 5L20 7"/></svg>';

// colour dots: the card's own colour first, then the other versions
const SW_MAX = 6;
function swatches(p) {
  const all = [{ colour: p.colour, url: p.url, image: p.image, inStock: p.inStock }, ...p.vers];
  const dots = all.slice(0, SW_MAX).map((v, k) => `<button type="button" class="sw" data-p="${p.i}" data-v="${k}" aria-pressed="${k === 0}"
      aria-label="${esc(v.colour)}${v.inStock ? "" : " (out of stock)"}" title="${esc(v.colour)}${v.inStock ? "" : " – out of stock"}"
      style="background:${COLOUR_HEX[v.colour] || COLOUR_HEX.Other}"${v.inStock ? "" : ' data-oos="1"'}></button>`).join("");
  return `<div class="sws">${dots}<span>${all.length} colours</span></div>`;
}
function swatchPick(btn) {
  const p = BY_I[+btn.dataset.p]; if (!p) return;
  const k = +btn.dataset.v, v = k === 0 ? { url: p.url, image: p.image } : p.vers[k - 1];
  const cardEl = btn.closest(".card"), url = safeUrl(outLink(v.url, p));
  cardEl.querySelectorAll("a.img, h3 a, a.go").forEach(a => a.href = url);
  const img = cardEl.querySelector(".img img");
  if (img && v.image) img.src = safeUrl(v.image);
  cardEl.querySelectorAll(".sw").forEach(b => b.setAttribute("aria-pressed", b === btn));
}

function card(p, extra = "") {
  const url = safeUrl(outLink(p.url, p));
  const on = CMP.has(p.url);
  return `<article class="card${p.inStock ? "" : " sold"}">
    <div class="media">
      <a class="img" href="${esc(url)}" target="_blank" rel="noopener sponsored" tabindex="-1" aria-hidden="true">
        <span class="ph">${esc(p.source)}</span>
        ${p.image ? `<img src="${esc(safeUrl(p.image))}" alt="" loading="lazy" decoding="async" onerror="this.remove()">` : ""}
        ${p.inStock ? "" : '<span class="oos">Out of stock</span>'}
      </a>
      <button type="button" class="cmpbtn" data-cmp="${esc(p.url)}" aria-pressed="${on}" aria-label="${on ? "Remove from compare" : "Add to compare"}: ${esc(p.title)}">${on ? ICON_TICK : ICON_PLUS}<span>${on ? "Added" : "Compare"}</span></button>
    </div>
    <span class="src">${esc(p.source)}</span>
    <h3><a href="${esc(url)}" target="_blank" rel="noopener sponsored">${esc(p.title)}</a></h3>
    ${p.vers && p.vers.length ? swatches(p) : ""}
    <div class="price"><strong>${rs(p.price)}</strong>${p.disc > 0 ? `<s>${rs(p.mrp)}</s><span class="off">${p.disc}% off</span>` : ""}</div>
    ${extra}
    <a class="go" href="${esc(url)}" target="_blank" rel="noopener sponsored">View on ${esc(p.source)}</a>
    <button type="button" class="simbtn" data-sim="${p.i}">Similar styles</button>
  </article>`;
}

/* ---------------- home, brands, routing ---------------- */
let BRANDS = [], BRAND_BY = {};
const FEATURED_CRAFTS = [["work", "Chikankari"], ["print", "Hand block print"], ["print", "Bandhani & leheriya"], ["work", "Gota patti"],
  ["work", "Mirror work"], ["print", "Ajrakh"], ["print", "Ikat"], ["work", "Zari & zardozi"], ["print", "Woven & jacquard"], ["print", "Hand painted"]];
const NOT_CLOTHES = new Set(["Accessories", "Other"]);
const HOME_CATS = ["Kurta sets", "Kurtas", "Co-ord sets", "Sarees", "Lehengas", "Dresses", "Tops & shirts", "Bottoms", "Jackets & overlays", "Accessories"];
const BUDGETS = [["u1000", "Under", "₹1,000"], ["1000", "₹1,000 –", "₹1,999"], ["2000", "₹2,000 –", "₹2,999"], ["3000", "From", "₹3,000"]];
const imgTag = (src, alt = "") => src ? `<img src="${esc(safeUrl(imgUrl(src)))}" alt="${esc(alt)}" loading="lazy" decoding="async" onerror="this.style.visibility='hidden'">` : "";
const shopLink = q => "#/shop" + (q ? "?" + new URLSearchParams(q).toString() : "");
const nf = n => n.toLocaleString("en-IN");

function pickImg(test, used) {
  for (const p of ALL) if (p.inStock && p.image && !used.has(p.image) && test(p)) { used.add(p.image); return p; }
  return null;
}
function brandFacts(b) {
  const bits = [];
  if (b.founded) bits.push("Since " + b.founded);
  if (b.based) bits.push(b.based);
  return bits.join(" · ");
}
function autoLine(b) {
  const cats = b.cats.filter(c => c !== "Other").slice(0, 3).map(c => c.toLowerCase());
  const list = cats.length > 1 ? cats.slice(0, -1).join(", ") + " and " + cats[cats.length - 1] : (cats[0] || "ethnic wear");
  let t = `Sells ${list}`;
  if (b.crafts.length) t += `, with a lot of ${b.crafts.slice(0, 2).map(c => c.toLowerCase()).join(" and ")}`;
  if (b.price_min) t += `. Most styles around ${rs(b.price_med)}`;
  return t + ".";
}
// Logo from the brand's own site; the brand name in type if there is none or it fails to load
function logoTag(b) {
  const mono = `<span class="mono" aria-hidden="true"${b.logo ? " hidden" : ""}>${esc(b.n.replace(/^the\s+/i, "")[0].toUpperCase())}</span>`;
  if (!b.logo) return mono;
  const src = safeUrl(b.logo.startsWith("//") ? "https:" + b.logo : b.logo);
  return `<img src="${esc(src)}" alt="${esc(b.n)} logo" loading="lazy" decoding="async"
    onerror="this.nextElementSibling.hidden=false;this.remove()">${mono}`;
}
function brandCard(b) {
  const facts = brandFacts(b);
  return `<article class="bcard">
    <a class="blogo" href="#/brand/${esc(b.slug)}" aria-hidden="true" tabindex="-1">${LIGHTS_CARD}${logoTag(b)}</a>
    <div class="bbody">
      ${facts ? `<span class="bmeta">${esc(facts)}</span>` : ""}
      <h3><a href="#/brand/${esc(b.slug)}">${esc(b.n)}</a></h3>
      <p class="bstory">${esc(b.story || autoLine(b))}</p>
      <div class="chips">${b.cats.filter(c => c !== "Other").slice(0, 3).concat(b.crafts.slice(0, 2)).map(c => `<span>${esc(c)}</span>`).join("")}</div>
      <div class="bfoot"><a class="btnp" href="#/brand/${esc(b.slug)}">Shop ${nf(b.in_stock)} styles</a>
        ${b.site ? `<a class="ext" href="${esc(safeUrl(b.site))}" target="_blank" rel="noopener">Visit site ↗</a>` : ""}</div>
    </div></article>`;
}

function renderHome() {
  const used = new Set();
  const inStock = ALL.filter(p => p.inStock);
  const nb = new Set(inStock.map(p => p.source)).size;
  $("hstats").innerHTML = `<div><b>${nf(inStock.length)}</b><span>styles in stock</span></div><div><b>${nb}</b><span>brands</span></div><div><b>6 hrs</b><span>prices refreshed</span></div>`;

  const cc = {}; for (const p of inStock) cc[p.category] = (cc[p.category] || 0) + 1;
  $("hcats").innerHTML = HOME_CATS.filter(c => cc[c] > 20).map(c => { const p = pickImg(q => q.category === c, used);
    return `<a class="tile" href="${shopLink({ cat: c })}"><div class="ti">${p ? imgTag(p.image, "") : ""}</div><b>${esc(c)}</b><span>${nf(cc[c])} styles</span></a>`; }).join("");
  $("hcrafts").innerHTML = FEATURED_CRAFTS.map(([g, v]) => {
    const n = inStock.reduce((k, p) => k + (p.A[g] && p.A[g].includes(v) ? 1 : 0), 0);
    if (n < 20) return "";
    const p = pickImg(q => q.A[g] && q.A[g].includes(v) && (q.category === "Kurta sets" || q.category === "Kurtas" || q.category === "Sarees"), used);
    return `<a class="tile" href="${shopLink({ a: g + ":" + v })}"><div class="ti">${p ? imgTag(p.image, "") : ""}</div><b>${esc(v.replace(" & ", " / "))}</b><span>${nf(n)} styles</span></a>`;
  }).join("");
  $("hprices").innerHTML = BUDGETS.map(([k, a, b]) => `<a href="${shopLink({ price: k })}"><small>${a}</small><b>${b}</b></a>`).join("");
  const feat = BRANDS.filter(b => b.in_stock > 0).sort((a, b) => (!!b.story - !!a.story) || b.in_stock - a.in_stock).slice(0, 8);
  $("hbrands").innerHTML = feat.map(brandCard).join("");
  $("hbrandsub").textContent = BRANDS.length ? `${BRANDS.length} independent labels, from Jaipur block printers to Lucknow chikankari houses.` : "";
  const fresh = [], per = {};
  for (const p of ALL) { if (!p.inStock || !p.image || (per[p.source] || 0) >= 1 || NOT_CLOTHES.has(p.category)) continue; per[p.source] = 1; fresh.push(p); if (fresh.length >= 12) break; }
  $("hnew").innerHTML = fresh.map(p => card(p)).join("");
}

let AZ = "";
function renderBrandsPage() {
  const q = ($("bsearch")?.value || "").trim().toLowerCase();
  const letters = [...new Set(BRANDS.map(b => b.n[0].toUpperCase()))].sort();
  if (!$("bsearch")) {
    $("az").innerHTML = `<input type="search" id="bsearch" aria-label="Search brands" placeholder="Search brands">` +
      `<button type="button" data-l="" aria-pressed="true">All</button>` + letters.map(l => `<button type="button" data-l="${l}" aria-pressed="false">${l}</button>`).join("");
    $("bsearch").addEventListener("input", renderBrandsPage);
    $("az").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; AZ = b.dataset.l; renderBrandsPage(); });
  }
  $("az").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", b.dataset.l === AZ));
  const list = BRANDS.filter(b => (!AZ || b.n[0].toUpperCase() === AZ) && (!q || b.n.toLowerCase().includes(q)));
  $("bsub").textContent = `${BRANDS.length} brands. Every product links straight to the brand's own website.`;
  $("ball").innerHTML = list.map(brandCard).join("") || '<p class="note">No brand matches.</p>';
}

function renderBrandHead(b) {
  const h = $("bhead");
  if (!b) { h.hidden = true; h.innerHTML = ""; return; }
  const facts = [["Founded", b.founded], ["Based in", b.based], ["Founders", b.founders],
    ["Styles", `${nf(b.in_stock)} in stock (${nf(b.styles)} listed)`],
    ["Price range", b.price_min ? `${rs(b.price_min)} – ${rs(b.price_max)}` : ""],
    ["Sells", b.cats.filter(c => c !== "Other").join(", ")], ["Known for", b.crafts.join(", ")]].filter(([, v]) => v);
  let src = "";
  try { src = b.story_source ? new URL(b.story_source).hostname.replace(/^www\./, "") : ""; } catch (e) {}
  h.hidden = false;
  h.innerHTML = LIGHTS.hero + `<div><a class="crumb" href="#/brands">← All brands</a><h1>${esc(b.n)}</h1>
      <p class="bstory">${esc(b.story || autoLine(b))}</p>
      ${src ? `<p class="src2">Story written from <a href="${esc(safeUrl(b.story_source))}" target="_blank" rel="noopener">${esc(src)}</a>.</p>` : ""}
      <div class="ctas">${b.site ? `<a class="btns" href="${esc(safeUrl(b.site))}" target="_blank" rel="noopener">Visit ${esc(b.n)} ↗</a>` : ""}
        ${b.instagram ? `<a class="btns" href="${esc(safeUrl(b.instagram))}" target="_blank" rel="noopener">Instagram ↗</a>` : ""}</div></div>
    <div class="facts">${facts.map(([k, v]) => `<div><small>${k}</small>${esc(v)}</div>`).join("")}</div>`;
}



/* ---------------- festive decoration (workstream A) ---------------- */
const BULBS = ["#FFC247", "#FFE29A", "#FFB547", "#FFD36B"];
// strings of lights hanging across the top: [startY, endY, sag, bulbs] per strand, in a 1440-wide box
function lightsSVG(w, h, strands) {
  let out = "", k = 0;
  for (const [y0, y1, sag, n] of strands) {
    const pt = t => { const x = -10 + (w + 20) * t; const y = y0 + (y1 - y0) * t + sag * 4 * t * (1 - t); return [x, y]; };
    const [cx, cy] = [w / 2, (y0 + y1) / 2 + sag * 2];
    out += `<path class="wire" d="M-10 ${y0} Q ${cx} ${cy} ${w + 10} ${y1}"/>`;
    for (let i = 1; i < n; i++) {
      const [x, y] = pt(i / n), c = BULBS[(i + k) % 4], d = ((i * 37 + k * 11) % 30) / 10;
      out += `<g class="bulb" style="animation-delay:${d}s"><circle cx="${x.toFixed(1)}" cy="${(y + 9).toFixed(1)}" r="11" fill="url(#glow)" opacity=".55"/>` +
        `<line x1="${x.toFixed(1)}" y1="${y.toFixed(1)}" x2="${x.toFixed(1)}" y2="${(y + 5).toFixed(1)}" stroke="#7A5A35" stroke-opacity=".45"/>` +
        `<ellipse cx="${x.toFixed(1)}" cy="${(y + 9).toFixed(1)}" rx="2.8" ry="3.4" fill="${c}"/>` +
        `<ellipse cx="${(x - 0.9).toFixed(1)}" cy="${(y + 7.6).toFixed(1)}" rx="1.2" ry="1.6" fill="#FFFBEA" opacity=".9"/></g>`;
    }
    k++;
  }
  return `<svg class="lights" viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMin slice" aria-hidden="true" focusable="false">${out}</svg>`;
}
const LIGHT_DEFS = `<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>
  <radialGradient id="glow"><stop offset="0" stop-color="#FFD36B" stop-opacity=".9"/><stop offset="1" stop-color="#FFC247" stop-opacity="0"/></radialGradient>
  <radialGradient id="flame" cx=".5" cy=".7" r=".6"><stop offset="0" stop-color="#FFFBEA"/><stop offset=".45" stop-color="#FFD36B"/><stop offset="1" stop-color="#F08A24"/></radialGradient>
  <radialGradient id="dglow"><stop offset="0" stop-color="#FFC247" stop-opacity=".6"/><stop offset="1" stop-color="#FFC247" stop-opacity="0"/></radialGradient></defs></svg>`;
const LIGHTS_CARD = lightsSVG(420, 150, [[-6, -6, 34, 13]]);
const LIGHTS = { hero: lightsSVG(1440, 180, [[24, 6, 60, 34], [6, 40, 52, 30]]), card: LIGHTS_CARD };
const DIYA = `<svg class="diya" viewBox="0 0 44 44" aria-hidden="true" focusable="false"><circle cx="22" cy="22" r="21" fill="url(#dglow)"/>
  <path d="M22 9c4 6 5 10 0 15-5-5-4-9 0-15z" fill="url(#flame)"/><path d="M6 27h32c-2 8-9 12-16 12S8 35 6 27z" fill="#B4501E"/><path d="M6 27h32" stroke="#E8B54A" stroke-width="2"/></svg>`;
const GARLAND = n => `<svg viewBox="0 0 22 ${n * 18 + 20}" preserveAspectRatio="xMidYMin meet" aria-hidden="true" focusable="false">` +
  Array.from({ length: n }, (_, i) => `<circle cx="11" cy="${9 + i * 18}" r="8.5" fill="${i % 3 === 2 ? "#FFE08A" : "#F08A24"}"/><circle cx="11" cy="${9 + i * 18}" r="3" fill="${i % 3 === 2 ? "#E8B54A" : "#FFB347"}"/>`).join("") +
  `<path d="M7 ${n * 18 + 2}h8l-4 10z" fill="#C08A2B"/></svg>`;
function decorate(root = document) {
  root.querySelectorAll("[data-lights]").forEach(el => { if (!el.dataset.done) { el.innerHTML = LIGHTS[el.dataset.lights] || ""; el.dataset.done = 1; } });
}
document.body.insertAdjacentHTML("afterbegin", LIGHT_DEFS);
(() => {
  const hero = document.querySelector(".hero.festive");
  decorate();
})();
