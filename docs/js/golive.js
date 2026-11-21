/* Go-live add-ons (workstream C): affiliate link wrapping and footer links.
   Settings come from site_config.json via js/site-config.js, which the build writes.
   Loaded after core.js; replaces outLink() so core.js itself never needs editing. */
(function () {
  const C = window.SAUBAG_CFG || {};
  const aff = C.affiliate || {};
  const perBrand = aff.per_brand || {};

  function wrap(url, product) {
    if (!/^https?:\/\//i.test(url || "")) return url;
    const tpl = (product && perBrand[product.source]) || aff.url_template || "";
    if (!tpl) return url;
    return tpl.split("{url_enc}").join(encodeURIComponent(url)).split("{url}").join(url);
  }
  window.outLink = wrap;

  // Footer: links to the info pages that are published, plus a disclosure line once affiliate links are on.
  function footer() {
    const box = document.querySelector("footer .wrap");
    if (!box || box.querySelector(".golive-links")) return;
    const pages = (C.pages || []).map(p => `<a href="${p.href}">${p.label}</a>`).join("");
    const div = document.createElement("div");
    div.className = "golive-links";
    div.innerHTML = (C.affiliate_on ? `<p class="golive-disc">Some links are affiliate links: saubag may earn a commission at no extra cost to you. <a href="disclosure.html">How this works</a></p>` : "")
      + (pages ? `<nav aria-label="About saubag">${pages}</nav>` : "");
    box.appendChild(div);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", footer); else footer();
})();
