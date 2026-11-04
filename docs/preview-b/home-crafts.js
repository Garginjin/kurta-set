/* Preview B only: home "Shop by craft" tiles driven by crafts.json.
   Every craft with 20+ in-stock styles, biggest first, each linking to its craft page.
   layout.js belongs to workstream A; if approved, A moves this into renderHome(). */
(() => {
  const base = renderHome;
  renderHome = function () {
    base();
    if (!CRAFTS.length) return;
    const used = new Set();
    const list = CRAFTS.filter(c => !c.bucket && c.in_stock >= CRAFT_MIN).sort((a, b) => b.in_stock - a.in_stock);
    $("hcrafts").innerHTML = list.map(c => {
      const p = pickImg(q => q.A.craft && q.A.craft.includes(c.name), used);
      return `<a class="tile" href="${craftLink(c)}"><div class="ti">${p ? imgTag(p.image, "") : ""}</div><b>${esc(c.name)}</b><span>${nf(c.in_stock)} styles</span></a>`;
    }).join("");
  };
})();
