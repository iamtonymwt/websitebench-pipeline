/* The Home Depot offline clone — client interaction layer.
 * The frozen React snapshots are the visual/structural baseline (scripts were
 * stripped for offline safety). This script re-implements the dynamic behavior
 * that the 535 journey and its siblings need, against the clone JSON API:
 * search submit, add-to-cart, cart rendering, checkout accordion + place order,
 * and order confirmation. It styles injected panels with the captured `sui-*`
 * utility classes so they match the frozen surface. No remote request is made.
 */
(function () {
  "use strict";
  const $ = (s, r) => (r || document).querySelector(s);
  const api = async (path, opts) => {
    const r = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts));
    return r.json();
  };
  const apiRes = async (path, opts) => {
    const r = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts));
    let data = {}; try { data = await r.json(); } catch (e) {}
    return { ok: r.ok, status: r.status, data };
  };
  const firstErr = (d) => (d && (d.error || (d.errors && Object.values(d.errors)[0]))) || "";
  const money = (n) => "$" + Number(n).toFixed(2);

  async function updateCartBadge() {
    try {
      const c = await api("/api/cart");
      const n = c.count > 0 ? c.count : "";
      const hb = document.getElementById("hd-hdr-cart-badge");
      if (hb) hb.textContent = n;
      document.querySelectorAll('[data-testid="header-cart-icon"], [data-testid="CartIcon"]').forEach((el) => {
        let badge = el.parentElement && el.parentElement.querySelector(".hd-cart-badge");
        if (!badge) {
          badge = document.createElement("span");
          badge.className = "hd-cart-badge";
          badge.style.cssText = "background:#f96302;color:#fff;border-radius:9px;padding:0 6px;font-size:11px;font-weight:700;margin-left:2px;vertical-align:top;";
          (el.parentElement || el).appendChild(badge);
        }
        badge.textContent = n;
      });
    } catch (e) {}
  }

  // The frozen React header renders with its flex/absolute children collapsed
  // onto each other (logo, store, search and cart overlap) and an absolute
  // overlay eats clicks on the search box. Replace it with a clean, on-brand
  // HD header so the layout matches the source and search is usable.
  function mountHeader() {
    if (location.pathname.startsWith("/auth/")) return;      // keep minimal signin header
    if (document.getElementById("hd-clean-header")) return;
    const frozen = document.getElementById("header-root")
      || document.querySelector('[data-component="Header"]');
    const h = document.createElement("header");
    h.id = "hd-clean-header";
    h.style.cssText = "position:sticky;top:0;z-index:960;background:#fff;border-bottom:1px solid #e6e6e6;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif";
    h.innerHTML = `
      <div style="max-width:1440px;margin:0 auto;display:flex;align-items:center;gap:16px;padding:10px 16px">
        <a href="/" aria-label="The Home Depot" style="flex:0 0 auto;text-decoration:none">
          <span style="display:inline-flex;width:48px;height:48px;background:#f96302;border-radius:4px;align-items:center;justify-content:center;text-align:center">
            <span style="color:#fff;font-weight:800;font-size:9px;line-height:1.05;letter-spacing:.3px">THE<br>HOME<br>DEPOT</span></span>
        </a>
        <a href="/b/Tools/N-5yc1vZc1xy" style="flex:0 0 auto;display:flex;align-items:center;gap:6px;color:#333;text-decoration:none;font-size:12px;line-height:1.2">
          <span style="font-size:20px">📍</span><span><span style="color:#757575">Store</span><br><b>Niagara Falls</b></span></a>
        <form id="hd-hdr-form" role="search" style="flex:1;display:flex;min-width:180px">
          <input id="hd-hdr-q" type="text" autocomplete="off" placeholder="What can we help you find today?"
            style="flex:1;padding:11px 14px;border:1px solid #b3b3b3;border-right:none;border-radius:4px 0 0 4px;font:inherit;font-size:15px;outline:none">
          <button type="submit" aria-label="Search" style="background:#f96302;border:none;border-radius:0 4px 4px 0;padding:0 18px;cursor:pointer;color:#fff;font-size:18px">&#128269;</button>
        </form>
        <nav id="hd-hdr-nav" style="flex:0 0 auto;display:flex;align-items:stretch;gap:2px;font-size:11px;color:#333">
          <div id="hd-nav-shopall-wrap" style="position:relative">
            <button type="button" id="hd-nav-shopall" aria-haspopup="true" aria-expanded="false" style="display:flex;flex-direction:column;align-items:center;gap:2px;background:none;border:none;cursor:pointer;color:#333;font:inherit;font-size:11px;padding:4px 8px;white-space:nowrap">
              <span aria-hidden="true" style="font-size:17px;line-height:1">&#9638;</span><span>Shop All &#9662;</span></button>
            <div id="hd-nav-shopall-menu" role="menu" style="display:none;position:absolute;top:100%;left:0;background:#fff;border:1px solid #ccc;border-radius:6px;box-shadow:0 8px 24px rgba(0,0,0,.16);min-width:230px;z-index:970;padding:6px 0;text-align:left;max-height:70vh;overflow:auto"></div>
          </div>
          <a href="/c/customer-service" style="display:flex;flex-direction:column;align-items:center;gap:2px;color:#333;text-decoration:none;padding:4px 8px;white-space:nowrap">
            <span aria-hidden="true" style="font-size:17px;line-height:1">&#128736;</span><span>Services</span></a>
          <a href="/" style="display:flex;flex-direction:column;align-items:center;gap:2px;color:#333;text-decoration:none;padding:4px 8px;white-space:nowrap">
            <span aria-hidden="true" style="font-size:17px;line-height:1">&#128296;</span><span>DIY</span></a>
        </nav>
        <div id="hd-hdr-acct" style="flex:0 0 auto;font-size:13px;white-space:nowrap"></div>
        <a href="/cart" id="hd-hdr-cart" data-testid="header-cart" aria-label="Cart" style="flex:0 0 auto;position:relative;color:#333;text-decoration:none;font-size:26px;line-height:1">&#128722;
          <span id="hd-hdr-cart-badge" data-testid="header-cart-count" style="position:absolute;top:-4px;right:-9px;background:#f96302;color:#fff;border-radius:9px;padding:0 5px;font-size:11px;font-weight:700;min-width:15px;text-align:center"></span></a>
      </div>`;
    if (frozen && frozen.parentNode) {
      frozen.style.display = "none";
      frozen.parentNode.insertBefore(h, frozen);
    } else {
      document.body.insertBefore(h, document.body.firstChild);
    }
    const submitSearch = (e) => {
      if (e) { e.preventDefault(); e.stopPropagation(); }
      const el = document.getElementById("hd-hdr-q");
      const q = ((el && el.value) || "").trim();
      if (q) window.location.assign("/s/" + encodeURIComponent(q));
      return false;
    };
    const form = document.getElementById("hd-hdr-form");
    const input = document.getElementById("hd-hdr-q");
    const sbtn = form.querySelector('button[type="submit"]');
    form.addEventListener("submit", submitSearch);
    if (sbtn) sbtn.addEventListener("click", submitSearch);
    if (input) input.addEventListener("keydown", (e) => { if (e.key === "Enter") submitSearch(e); });

    // "Shop All" departments menu, mirroring the official header's department
    // flyout. Departments we actually clone link to their PLP; the rest resolve
    // through search so every entry lands on a real, working page.
    const DEPARTMENTS = [
      ["Tools", "/b/Tools/N-5yc1vZc1xy"], ["Drills", "/b/Drills/N-5yc1vZc27f"],
      ["Appliances", "/s/appliances"], ["Bath & Faucets", "/s/bath"],
      ["Building Materials", "/s/building materials"], ["Doors & Windows", "/s/doors"],
      ["Electrical", "/s/electrical"], ["Flooring", "/s/flooring"],
      ["Hardware", "/s/hardware"], ["Heating & Cooling", "/s/heating cooling"],
      ["Kitchen", "/s/kitchen"], ["Lawn & Garden", "/s/lawn garden"],
      ["Lighting & Ceiling Fans", "/s/lighting"], ["Outdoor Living", "/s/outdoor living"],
      ["Paint", "/s/paint"], ["Plumbing", "/s/plumbing"],
      ["Smart Home", "/s/smart home"], ["Storage & Organization", "/s/storage"],
    ];
    const menu = document.getElementById("hd-nav-shopall-menu");
    const shopAllBtn = document.getElementById("hd-nav-shopall");
    if (menu && shopAllBtn) {
      menu.innerHTML = DEPARTMENTS.map(([name, href]) =>
        `<a href="${href}" role="menuitem" style="display:block;padding:8px 18px;color:#333;text-decoration:none;font-size:14px;white-space:nowrap"
           onmouseover="this.style.background='#f5f5f5'" onmouseout="this.style.background='transparent'">${name}</a>`).join("");
      // Promote the menu to a body-level fixed popover with a top-of-stack
      // z-index. Left inside the sticky header it sits in the header's stacking
      // context, which some frozen pages trap below the fixed live panel — so the
      // panel would paint over the lower half of the menu. As a body child with
      // position:fixed it escapes every stacking context and always renders on top.
      document.body.appendChild(menu);
      menu.dataset.wbKeep = "1";                 // survive hideFrozenBodyExceptHeader
      menu.style.position = "fixed";
      menu.style.zIndex = "2147483000";
      menu.style.top = ""; menu.style.left = "";
      const place = () => {
        const r = shopAllBtn.getBoundingClientRect();
        const w = menu.offsetWidth || 232;
        menu.style.top = Math.round(r.bottom + 2) + "px";
        menu.style.left = Math.round(Math.max(8, Math.min(r.left, window.innerWidth - w - 8))) + "px";
        // Cap to the space below the button so the whole list fits (and only
        // scrolls on a genuinely short viewport) instead of a fixed 70vh clip.
        menu.style.maxHeight = Math.max(200, Math.round(window.innerHeight - r.bottom - 12)) + "px";
      };
      const setMenu = (open) => {
        if (open) { menu.style.display = "block"; place(); }
        else { menu.style.display = "none"; }
        shopAllBtn.setAttribute("aria-expanded", open ? "true" : "false");
      };
      setMenu(false);
      shopAllBtn.addEventListener("click", (e) => { e.stopPropagation(); setMenu(menu.style.display === "none"); });
      menu.addEventListener("click", (e) => e.stopPropagation());
      document.addEventListener("click", () => setMenu(false));
      document.addEventListener("keydown", (e) => { if (e.key === "Escape") setMenu(false); });
      window.addEventListener("resize", () => setMenu(false));
      window.addEventListener("scroll", () => setMenu(false), true);
    }
  }

  function headerStore(name) {
    // Reflect the active pickup store in the header (set from cart when known).
    const el = document.querySelector("#hd-clean-header a[href^='/b/Tools'] b");
    if (el && name) el.textContent = name;
  }

  function wireSearch() {
    const box = $("#typeahead-search-field-input");
    if (!box) return;
    const form = box.closest("form");
    const go = () => {
      const q = (box.value || "").trim();
      if (q) location.href = "/s/" + encodeURIComponent(q);
    };
    if (form) form.addEventListener("submit", (e) => { e.preventDefault(); go(); });
    box.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); go(); } });
    const btn = document.querySelector('[data-testid="search-bar-submit"], button[aria-label*="ubmit" i], form button[type="submit"]');
    if (btn) btn.addEventListener("click", (e) => { e.preventDefault(); go(); });
  }

  function wirePDP() {
    const m = location.pathname.match(/\/p\/[^/]+\/(\d{6,})/);
    if (!m) return;
    const itemId = m[1];
    const buttons = [...document.querySelectorAll("button")].filter(
      (b) => /add to cart/i.test((b.textContent || "").trim())
    );
    if (!buttons.length) return;
    // Inject a quantity selector (Limit 3) + Save-to-List control before the
    // primary add-to-cart button, once per page.
    let qtySel = document.getElementById("hd-pdp-qty");
    const primary = buttons[0];
    if (primary && !document.getElementById("hd-pdp-controls")) {
      const ctl = document.createElement("div");
      ctl.id = "hd-pdp-controls";
      ctl.style.cssText = "display:flex;gap:10px;align-items:center;margin:8px 0;flex-wrap:wrap";
      ctl.innerHTML =
        '<label style="font-size:14px;color:#333">Qty '
        + '<select id="hd-pdp-qty" style="padding:6px 8px;border:1px solid #999;border-radius:4px;margin-left:4px;font:inherit">'
        + '<option>1</option><option>2</option><option>3</option></select></label>'
        + '<button id="hd-pdp-save" type="button" style="background:#fff;border:1px solid #f96302;color:#f96302;border-radius:24px;padding:8px 16px;font-weight:700;cursor:pointer">Add to List</button>'
        + '<span id="hd-pdp-save-msg" style="font-size:13px;color:#367c2b"></span>';
      primary.parentNode.insertBefore(ctl, primary);
      qtySel = ctl.querySelector("#hd-pdp-qty");
      ctl.querySelector("#hd-pdp-save").addEventListener("click", async (e) => {
        e.preventDefault();
        const msg = document.getElementById("hd-pdp-save-msg");
        const r = await apiRes("/api/lists/add", { method: "POST", body: JSON.stringify({ itemId: itemId }) });
        if (r.ok) {
          msg.innerHTML = (r.data.added ? "✓ Saved to " : "Already in ") + esc(r.data.list)
            + ' · <a href="/myaccount/dashboard" style="color:#3e7697">view lists</a>';
        } else { msg.style.color = "#c00"; msg.textContent = "Could not save to list."; }
      });
    }
    buttons.forEach((b) => {
      const clone = b.cloneNode(true); // drop any stale listeners
      b.parentNode.replaceChild(clone, b);
      clone.addEventListener("click", async (e) => {
        e.preventDefault();
        clone.disabled = true;
        clone.textContent = "Adding…";
        const qty = qtySel ? (parseInt(qtySel.value, 10) || 1) : 1;
        await api("/api/cart/add", { method: "POST", body: JSON.stringify({ itemId: itemId, qty: qty }) });
        await updateCartBadge();
        clone.textContent = "✓ Added to Cart";
        setTimeout(() => { location.href = "/cart"; }, 600);
      });
    });
    injectPDPRelated(itemId);
  }

  async function injectPDPRelated(itemId) {
    if (document.getElementById("hd-pdp-related")) return;
    let rel;
    try { rel = await api("/api/products/" + encodeURIComponent(itemId) + "/related"); } catch (e) { return; }
    const items = (rel && rel.products) || [];
    if (items.length < 2) return;
    const host = document.getElementById("hd-pdp-controls") || document.querySelector("main") || document.body;
    const sec = document.createElement("section");
    sec.id = "hd-pdp-related";
    sec.style.cssText = "max-width:1232px;margin:20px auto;padding:16px;border-top:1px solid #e6e6e6;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif";
    sec.innerHTML =
      '<h2 style="font-size:20px;font-weight:400;margin:0 0 12px">Compare Similar Products</h2>'
      + '<div style="display:flex;gap:16px;overflow-x:auto;padding-bottom:8px">'
      + items.slice(0, 6).map((pr) =>
        `<a href="${esc(pr.canonicalUrl || ("/p/x/" + pr.itemId))}" style="flex:0 0 180px;border:1px solid #e6e6e6;border-radius:8px;padding:12px;text-decoration:none;color:#333">
           <img src="${esc(pr.thumb || "")}" alt="" style="width:100%;height:120px;object-fit:contain">
           <div style="font-weight:700;font-size:12px;margin-top:6px">${esc(pr.brand || "")}</div>
           <div style="font-size:13px;min-height:34px">${esc((pr.label || "").slice(0, 46))}</div>
           <div style="color:#f96302;font-size:12px">${pr.rating ? "★ " + pr.rating + " (" + (pr.reviews || 0) + ")" : ""}</div>
           <div style="font-weight:700;font-size:18px;margin-top:2px">${money(pr.price)}</div>
         </a>`).join("")
      + '</div>';
    if (host.id === "hd-pdp-controls") host.insertAdjacentElement("afterend", sec);
    else host.appendChild(sec);
  }

  function panel(html) {
    const wrap = document.createElement("div");
    wrap.className = "hd-clone-panel";
    wrap.style.cssText = "max-width:1232px;margin:16px auto;padding:0 16px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;";
    wrap.innerHTML = html;
    return wrap;
  }

  function mountMain(node) {
    // Show our functional panel in place of the frozen body content, keeping the
    // captured header/nav (visual identity). The frozen main content (a static
    // snapshot of a different state) is hidden so cart/checkout/confirmation
    // reflect live data only.
    document.querySelectorAll(".hd-clone-panel").forEach((n) => n.remove());
    // Do NOT mutate the frozen DOM (its header layout depends on ancestor CSS and
    // breaks if cloned or if siblings are hidden). Instead overlay the live panel
    // as a fixed region below the captured header; the frozen body content stays
    // in place, covered by the panel's opaque background.
    const header = document.querySelector("#hd-clean-header")
      || document.querySelector('[data-component="Header"], #header-root, header, #header, [role="banner"]');
    let top = 132;
    if (header) {
      const b = header.getBoundingClientRect().bottom;
      if (b > 20 && b < 400) top = Math.round(b);
    }
    node.style.position = "fixed";
    node.style.top = top + "px";
    node.style.left = "0";
    node.style.right = "0";
    node.style.bottom = "0";
    node.style.overflowY = "auto";
    node.style.background = "#fff";
    node.style.zIndex = "900";
    node.style.maxWidth = "none";
    node.style.margin = "0";
    node.style.padding = "0 max(16px, calc((100vw - 1232px) / 2))";
    document.body.appendChild(node);
    // Remove the frozen main content (a snapshot of a different state) from layout
    // so it can never scroll into the sliver between the sticky header and this
    // fixed panel — even under a programmatic scroll (an agent scrolling would
    // otherwise flash phantom frozen products). The clean header spine is kept;
    // the panel scrolls its own content via overflow-y:auto.
    hideFrozenBodyExceptHeader(node);
    window.scrollTo(0, 0);
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
  }

  // Hide everything that is not on the clean header's ancestor spine (and not the
  // live panel), walking from the header up to <body>. Keeps the sticky header
  // rendered while dropping the frozen main content + footer from layout.
  function hideFrozenBodyExceptHeader(panel) {
    const ch = document.getElementById("hd-clean-header");
    if (!ch) return;
    let node = ch;
    while (node && node !== document.body) {
      const parent = node.parentElement;
      if (!parent) break;
      for (const sib of [...parent.children]) {
        if (sib === node || sib === ch || sib === panel) continue;
        if (sib.contains(ch) || (panel && sib.contains(panel))) continue;
        if (sib.dataset && sib.dataset.wbKeep) continue;   // e.g. the Shop All popover
        if (/^(SCRIPT|STYLE|LINK|NOSCRIPT|TEMPLATE)$/.test(sib.tagName)) continue;
        sib.style.display = "none";
      }
      node = parent;
    }
  }

  // Holds the most recently removed cart line so it can be restored ("Undo").
  let _cartRestore = null;
  function cartRestoreBanner() {
    if (!_cartRestore) return "";
    return '<div id="hd-cart-restore" style="background:#fff8e1;border:1px solid #f0d98a;border-radius:6px;padding:10px 14px;margin:16px 0;max-width:640px;display:flex;align-items:center;gap:10px">'
      + "<span>Removed <b>" + esc((_cartRestore.label || "item").slice(0, 48)) + "</b> from your cart.</span>"
      + '<button id="hd-cart-undo" style="background:none;border:none;color:#f96302;font-weight:700;cursor:pointer;text-decoration:underline">Undo</button></div>';
  }
  function wireCartRestore() {
    const btn = document.getElementById("hd-cart-undo");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const r = _cartRestore; _cartRestore = null;
      if (r) await api("/api/cart/add", { method: "POST", body: JSON.stringify({ itemId: r.itemId, qty: r.qty || 1 }) });
      renderCart(); updateCartBadge();
    });
  }

  async function renderCart() {
    if (location.pathname.replace(/\/$/, "") !== "/cart") return;
    const c = await api("/api/cart");
    if (!c.items || !c.items.length) {
      const acct = await accountState();
      let recs = [];
      try { recs = ((await api("/api/search?q=&sort=top_rated&limit=6")) || {}).products || []; } catch (e) {}
      const authCta = (acct && acct.authenticated)
        ? ""
        : '<div style="border:1px solid #e6e6e6;border-radius:8px;padding:16px 20px;margin:16px 0;max-width:520px">'
          + '<div style="font-weight:700;margin-bottom:6px">Sign in for your saved cart & faster checkout</div>'
          + '<a href="/auth/view/signin" style="display:inline-block;background:#f96302;color:#fff;border-radius:24px;padding:9px 22px;font-weight:700;text-decoration:none">Sign In</a>'
          + ' <a href="/auth/view/signin" style="margin-left:10px;color:#3e7697">Create an Account</a></div>';
      const recRow = recs.length
        ? '<h2 style="font-size:20px;font-weight:400;margin:24px 0 12px">Top Sellers</h2>'
          + '<div style="display:flex;gap:16px;overflow-x:auto;padding-bottom:8px">'
          + recs.map((p) => `<a href="${esc(p.canonicalUrl || ("/p/x/" + p.itemId))}" style="flex:0 0 180px;border:1px solid #e6e6e6;border-radius:8px;padding:12px;text-decoration:none;color:#333">
               <img src="${esc(p.thumb || "")}" alt="" style="width:100%;height:130px;object-fit:contain">
               <div style="font-size:13px;min-height:34px;margin-top:6px">${esc((p.label || "").slice(0, 46))}</div>
               <div style="font-weight:700;font-size:18px">${money(p.price)}</div></a>`).join("")
          + "</div>"
        : "";
      mountMain(panel(
        cartRestoreBanner()
        + '<h1 style="font-size:28px;font-weight:400;margin:24px 0 8px">Your Cart is empty</h1>'
        + '<p style="margin-bottom:8px"><a href="/" style="color:#3e7697">Continue shopping</a></p>'
        + authCta + recRow));
      wireCartRestore();
      return;
    }
    const rows = c.items.map((it) => `
      <div class="sui-flex" style="display:flex;gap:16px;padding:16px 0;border-bottom:1px solid #e6e6e6">
        <img src="${it.thumb || ""}" alt="" style="width:96px;height:96px;object-fit:contain">
        <div style="flex:1">
          <div style="font-weight:700">${it.brand || ""}</div>
          <div>${it.label}</div>
          <div style="color:#757575;font-size:13px">Model# ${it.model || ""}</div>
          <div style="margin-top:8px">Qty:
            <select data-item="${it.itemId}" class="hd-qty" style="padding:4px 8px;border:1px solid #999;border-radius:4px">
              ${[1, 2, 3].map((n) => `<option value="${n}"${n === it.qty ? " selected" : ""}>${n}</option>`).join("")}
            </select>
            <button data-remove="${it.itemId}" class="hd-remove" style="margin-left:12px;color:#3e7697;background:none;border:none;cursor:pointer">Remove</button>
          </div>
        </div>
        <div style="font-weight:700;font-size:20px">${money(it.price)}</div>
      </div>`).join("");
    mountMain(panel(`
      ${cartRestoreBanner()}
      <h1 style="font-size:28px;font-weight:400;margin:24px 0">Cart <span style="color:#757575;font-size:18px">(${c.count} item${c.count > 1 ? "s" : ""})</span></h1>
      <div style="display:flex;gap:32px;flex-wrap:wrap">
        <div style="flex:2;min-width:320px">
          <div style="font-weight:700;margin-bottom:8px">Pickup <span style="font-weight:400;color:#757575">${c.store ? c.store.name : ""}</span></div>
          <div style="font-size:12px;color:#757575">Limit 3 per order</div>
          ${rows}
        </div>
        <div style="flex:1;min-width:260px;background:#f5f5f5;padding:20px;border-radius:4px;height:fit-content">
          <div style="display:flex;justify-content:space-between;margin-bottom:8px"><span>Subtotal</span><span>${money(c.subtotal)}</span></div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px"><span>Pickup</span><span style="color:#367c2b;font-weight:700">FREE</span></div>
          <div style="display:flex;justify-content:space-between;margin-bottom:8px"><span>Estimated Tax</span><span>${money(c.tax)}</span></div>
          <div style="display:flex;justify-content:space-between;font-weight:700;font-size:18px;border-top:1px solid #ccc;padding-top:12px;margin-top:12px"><span>Total</span><span>${money(c.total)}</span></div>
          <button id="hd-proceed" style="width:100%;margin-top:16px;background:#f96302;color:#fff;border:none;padding:14px;border-radius:24px;font-weight:700;font-size:16px;cursor:pointer">Proceed to Checkout</button>
        </div>
      </div>`));
    wireCartRestore();
    document.querySelectorAll(".hd-qty").forEach((s) =>
      s.addEventListener("change", async (e) => {
        _cartRestore = null;
        await api("/api/cart/update", { method: "POST", body: JSON.stringify({ itemId: e.target.dataset.item, qty: parseInt(e.target.value, 10) }) });
        renderCart(); updateCartBadge();
      }));
    document.querySelectorAll(".hd-remove").forEach((b) =>
      b.addEventListener("click", async (e) => {
        const id = e.target.dataset.remove;
        const it = (c.items || []).find((x) => String(x.itemId) === String(id));
        _cartRestore = it ? { itemId: id, qty: it.qty || 1, label: it.label || it.brand || "item" } : null;
        await api("/api/cart/remove", { method: "POST", body: JSON.stringify({ itemId: id }) });
        renderCart(); updateCartBadge();
      }));
    $("#hd-proceed").addEventListener("click", () => { location.href = "/checkout"; });
  }

  async function renderCheckout() {
    if (location.pathname.replace(/\/$/, "") !== "/checkout") return;
    let c = await api("/api/cart");
    if (!c.items || !c.items.length) { location.href = "/cart"; return; }
    const stores = ((await api("/api/stores")) || {}).stores || [];
    const state = { mode: "pickup" };
    const IN = "display:block;width:100%;max-width:360px;padding:10px;margin-bottom:2px;border:1px solid #999;border-radius:4px;font:inherit";
    const ERR = "color:#c00;font-size:12px;min-height:15px;margin-bottom:6px";
    const CARD = "border:1px solid #e6e6e6;border-radius:4px;padding:20px;margin-bottom:16px";
    const setErr = (id, m) => { const e = document.getElementById(id); if (e) e.textContent = m || ""; };

    function personFields(kind) {
      return `<input id="hd-first" placeholder="First Name" style="${IN}"><div id="hd-err-first" style="${ERR}"></div>
        <input id="hd-last" placeholder="Last Name" style="${IN}"><div id="hd-err-last" style="${ERR}"></div>
        <input id="hd-phone" placeholder="Phone (___) ___-____" style="${IN}"><div id="hd-err-phone" style="${ERR}"></div>`;
    }

    function paint() {
      const pickup = state.mode === "pickup";
      const storeOpts = stores.map((s) =>
        `<option value="${esc(s.id)}"${c.store && c.store.id === s.id ? " selected" : ""}>${esc(s.name)} — ${esc(s.city)}, ${esc(s.state)} ${esc(s.zip)}</option>`).join("");
      const fulfillmentCard = pickup ? `
        <div style="${CARD}">
          <div style="font-weight:700;font-size:18px;margin-bottom:4px">Pickup Person</div>
          <div style="color:#757575;font-size:13px;margin-bottom:12px">Who is picking up this order?</div>
          ${personFields("pickup")}
        </div>
        <div style="${CARD}">
          <div style="font-weight:700;font-size:18px;margin-bottom:8px">Store Pickup</div>
          <label style="font-size:13px;color:#555">Change store
            <select id="hd-store" style="display:block;margin-top:4px;padding:8px;border:1px solid #999;border-radius:4px;font:inherit;max-width:360px;width:100%">${storeOpts}</select></label>
          <div style="color:#757575;font-size:13px;margin-top:8px">${c.store ? esc(c.store.address + ", " + c.store.city + ", " + c.store.state + " " + c.store.zip) : ""}</div>
          <label style="display:block;margin-top:12px"><input type="radio" name="hd-pickup" value="instore" checked> In Store Pickup</label>
          <label style="display:block;margin-top:4px"><input type="radio" name="hd-pickup" value="curbside"> Curbside Pickup</label>
        </div>` : `
        <div style="${CARD}">
          <div style="font-weight:700;font-size:18px;margin-bottom:4px">Delivery Address</div>
          <div style="color:#757575;font-size:13px;margin-bottom:12px">Where should we ship this order?</div>
          ${personFields("delivery")}
          <input id="hd-addr" placeholder="Street Address" style="${IN}"><div id="hd-err-addr" style="${ERR}"></div>
          <input id="hd-zip" placeholder="ZIP Code" value="14304" style="${IN}"><div id="hd-err-zip" style="${ERR}"></div>
          <div style="font-weight:700;margin-top:8px">Shipping</div>
          <label style="display:block;margin-top:6px"><input type="radio" name="hd-ship" value="standard" checked> Standard — FREE (3–5 days)</label>
          <label style="display:block;margin-top:4px"><input type="radio" name="hd-ship" value="express"> Express (2 days)</label>
        </div>`;
      mountMain(panel(`
        <h1 style="font-size:24px;font-weight:400;margin:20px 0">Secure Checkout</h1>
        <div style="display:flex;gap:32px;flex-wrap:wrap">
          <div style="flex:2;min-width:320px">
            <div style="${CARD}">
              <div style="font-weight:700;font-size:18px;margin-bottom:8px">How would you like to get it?</div>
              <label style="margin-right:16px"><input type="radio" name="hd-ful" value="pickup"${pickup ? " checked" : ""}> Store Pickup (Free)</label>
              <label><input type="radio" name="hd-ful" value="delivery"${!pickup ? " checked" : ""}> Delivery</label>
            </div>
            ${fulfillmentCard}
            <div style="${CARD};margin-bottom:0">
              <div style="font-weight:700;font-size:18px;margin-bottom:8px">Payment Method</div>
              <div style="margin-bottom:14px">
                <div style="font-weight:700;font-size:14px;margin-bottom:6px">Apply Gift Card</div>
                ${state.gift
                  ? `<div style="font-size:14px;color:#367c2b">✓ Gift card <b>${esc(state.gift.code)}</b> applied (−${money(state.gift.amount)}) <button id="hd-gift-remove" style="background:none;border:none;color:#3e7697;cursor:pointer;text-decoration:underline">Remove</button></div>`
                  : `<div style="display:flex;gap:8px;max-width:360px">
                      <input id="hd-gift-code" type="text" placeholder="Gift card code" autocomplete="off" style="flex:1;padding:9px 10px;border:1px solid #999;border-radius:4px;font:inherit">
                      <button id="hd-gift-apply" style="background:#fff;border:1px solid #f96302;color:#f96302;border-radius:20px;padding:8px 18px;font-weight:700;cursor:pointer">Apply</button>
                    </div>
                    <div id="hd-gift-msg" style="font-size:12px;min-height:14px;margin-top:4px;color:#757575">Sandbox demo — try SANDBOX-GIFT-25</div>`}
              </div>
              <div style="color:#757575;font-size:12px;margin-bottom:12px">Local sandbox — no real card is accepted. Choose a simulated outcome:</div>
              <select id="hd-scenario" style="padding:10px;border:1px solid #999;border-radius:4px;width:100%;max-width:360px;font:inherit">
                <option value="sandbox-approved">Simulated approval</option>
                <option value="sandbox-declined">Simulated decline</option>
                <option value="sandbox-retry">Simulated retry</option>
              </select>
            </div>
          </div>
          <div style="flex:1;min-width:260px;background:#f5f5f5;padding:20px;border-radius:4px;height:fit-content">
            <div style="font-weight:700;margin-bottom:12px">Your Order</div>
            ${c.items.map((it) => `<div style="display:flex;justify-content:space-between;font-size:14px;margin-bottom:6px"><span>${it.qty}× ${esc(it.model || it.label.slice(0, 24))}</span><span>${money(it.line_total)}</span></div>`).join("")}
            <div style="display:flex;justify-content:space-between;margin:8px 0"><span>Subtotal</span><span>${money(c.subtotal)}</span></div>
            <div style="display:flex;justify-content:space-between;margin:8px 0"><span>${pickup ? "Pickup" : "Shipping"}</span><span style="color:#367c2b;font-weight:700">FREE</span></div>
            <div style="display:flex;justify-content:space-between;margin:8px 0"><span>Estimated Tax</span><span>${money(c.tax)}</span></div>
            <div style="display:flex;justify-content:space-between;font-weight:700;font-size:18px;border-top:1px solid #ccc;padding-top:12px;margin-top:12px"><span>Total</span><span>${money(c.total)}</span></div>
            ${state.gift ? `<div style="display:flex;justify-content:space-between;margin:8px 0;color:#367c2b"><span>Gift Card (${esc(state.gift.code)})</span><span>−${money(state.gift.amount)}</span></div>
            <div style="display:flex;justify-content:space-between;font-weight:700"><span>Charged to card</span><span>${money(Math.max(c.total - state.gift.amount, 0))}</span></div>` : ""}
            <button id="hd-place" style="width:100%;margin-top:16px;background:#f96302;color:#fff;border:none;padding:14px;border-radius:24px;font-weight:700;font-size:16px;cursor:pointer">Place Order</button>
            <div id="hd-pay-msg" style="margin-top:10px;font-size:13px"></div>
          </div>
        </div>`));
      const giftApply = document.getElementById("hd-gift-apply");
      if (giftApply) giftApply.addEventListener("click", async () => {
        const code = (document.getElementById("hd-gift-code").value || "").trim();
        const gm = document.getElementById("hd-gift-msg");
        if (!code) { gm.style.color = "#c00"; gm.textContent = "Enter a gift card code."; return; }
        const g = await api("/api/giftcard/check?code=" + encodeURIComponent(code));
        if (g && g.valid) { state.gift = { code: g.code, amount: g.amount }; paint(); }
        else { gm.style.color = "#c00"; gm.textContent = "That gift card code is not valid."; }
      });
      const giftRemove = document.getElementById("hd-gift-remove");
      if (giftRemove) giftRemove.addEventListener("click", () => { state.gift = null; paint(); });
      document.querySelectorAll('input[name="hd-ful"]').forEach((r) =>
        r.addEventListener("change", (e) => { state.mode = e.target.value; paint(); }));
      const storeSel = document.getElementById("hd-store");
      if (storeSel) storeSel.addEventListener("change", async (e) => {
        const r = await apiRes("/api/cart/store", { method: "POST", body: JSON.stringify({ store_id: e.target.value }) });
        if (r.ok) { c = r.data.cart; paint(); }
      });
      $("#hd-place").addEventListener("click", place);
    }

    async function place() {
      const btn = $("#hd-place"), msg = $("#hd-pay-msg");
      msg.textContent = "";
      const first = $("#hd-first").value.trim(), last = $("#hd-last").value.trim(), phone = $("#hd-phone").value.trim();
      let bad = false;
      setErr("hd-err-first", first ? "" : "Please enter a first name."); if (!first) bad = true;
      setErr("hd-err-last", last ? "" : "Please enter a last name."); if (!last) bad = true;
      setErr("hd-err-phone", phone ? "" : "Please enter a phone number."); if (!phone) bad = true;
      if (state.mode === "delivery") {
        const addr = ($("#hd-addr") || {}).value || "";
        setErr("hd-err-addr", addr.trim() ? "" : "Please enter a street address."); if (!addr.trim()) bad = true;
      }
      if (bad) { msg.style.color = "#c00"; msg.textContent = "Please complete the required fields."; return; }
      btn.disabled = true; btn.textContent = "Placing…";
      const r = await api("/api/checkout", { method: "POST", body: JSON.stringify({
        first_name: first, last_name: last, phone: phone,
        scenario_id: $("#hd-scenario").value, fulfillment: state.mode,
        gift_code: state.gift ? state.gift.code : "" }) });
      if (r.placed) { location.href = "/order-confirmation?order=" + encodeURIComponent(r.order_number); return; }
      btn.disabled = false; btn.textContent = "Place Order"; msg.style.color = "#c00";
      msg.textContent = r.error || ("Payment " + ((r.payment && r.payment.status) || "declined") + " — please try again.");
    }

    paint();
  }

  async function renderConfirmation() {
    if (location.pathname.replace(/\/$/, "") !== "/order-confirmation") return;
    const num = new URLSearchParams(location.search).get("order");
    const o = await api("/api/order/" + encodeURIComponent(num || ""));
    if (o.error) { mountMain(panel("<h1>Order not found</h1>")); return; }
    mountMain(panel(`
      <div style="text-align:center;padding:24px 0">
        <div style="color:#367c2b;font-size:40px">✓</div>
        <h1 style="font-size:28px;font-weight:400">Thank you for your order!</h1>
        <div style="color:#757575">Order # <strong>${o.order_number}</strong> · ${o.status}</div>
      </div>
      <div style="max-width:640px;margin:0 auto;border:1px solid #e6e6e6;border-radius:4px;padding:20px">
        <div style="font-weight:700;margin-bottom:8px">Pickup — ${o.store ? o.store.name : ""}</div>
        <div style="color:#757575;font-size:13px;margin-bottom:4px">${o.store ? o.store.address + ", " + o.store.city + ", " + o.store.state + " " + o.store.zip : ""}</div>
        <div style="color:#757575;font-size:13px;margin-bottom:16px">Pickup person: ${o.pickup_person.first_name} ${o.pickup_person.last_name} · ${o.pickup_person.phone}</div>
        ${o.items.map((it) => `<div style="display:flex;gap:12px;padding:12px 0;border-top:1px solid #eee"><img src="${it.thumb || ""}" style="width:64px;height:64px;object-fit:contain"><div style="flex:1">${it.label}<div style="color:#757575;font-size:12px">Model# ${it.model || ""} · Qty ${it.qty}</div></div><div style="font-weight:700">${money(it.unit_price)}</div></div>`).join("")}
        <div style="display:flex;justify-content:space-between;margin-top:12px"><span>Subtotal</span><span>${money(o.subtotal)}</span></div>
        <div style="display:flex;justify-content:space-between"><span>Estimated Tax</span><span>${money(o.tax)}</span></div>
        <div style="display:flex;justify-content:space-between;font-weight:700;font-size:18px;border-top:1px solid #ccc;padding-top:8px;margin-top:8px"><span>Total</span><span>${money(o.total)}</span></div>
        ${o.gift ? `<div style="display:flex;justify-content:space-between;color:#367c2b;margin-top:6px"><span>Gift Card applied</span><span>−${money(o.gift)}</span></div>
        <div style="display:flex;justify-content:space-between;font-weight:700"><span>Charged to card</span><span>${money(o.charged != null ? o.charged : o.total - o.gift)}</span></div>` : ""}
      </div>
      <div style="text-align:center;margin-top:20px"><a href="/" style="color:#3e7697">Continue shopping</a></div>`));
  }

  // --- accounts / sessions ----------------------------------------------
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function accountState() {
    try { return await api("/api/account"); } catch (e) { return { authenticated: false }; }
  }

  function wireSignin() {
    if (location.pathname.replace(/\/$/, "") !== "/auth/view/signin"
        && location.pathname.replace(/\/$/, "") !== "/auth/view/createaccount") return;
    const email = $("#username");
    const cont = $("#sign-in-button");
    if (!email || !cont) return;
    let step = "email";
    // The frozen button was captured inactive: `sui-btn-primary-inactive` sets
    // `pointer-events:none`, so even after clearing `disabled` the click never
    // reaches it. An inline value overrides the class and makes it live.
    const enable = () => {
      const on = !!(email.value || "").trim();
      cont.disabled = !on;
      cont.style.pointerEvents = "auto";
      cont.classList.toggle("sui-btn-primary-inactive", !on);
    };
    email.addEventListener("input", enable);
    enable();
    function revealPassword() {
      if ($("#hd-password")) return;
      const wrap = document.createElement("div");
      wrap.style.cssText = "margin-top:12px";
      wrap.innerHTML =
        '<label for="hd-password" style="display:block;font-size:13px;color:#333;margin-bottom:4px">Password</label>'
        + '<input id="hd-password" type="password" autocomplete="current-password" '
        + 'class="sui-input-base-input sui-peer sui-pl-3 sui-pr-3" '
        + 'style="width:100%;padding:10px;border:1px solid #999;border-radius:4px;font:inherit">'
        + '<div id="hd-signin-msg" role="alert" style="color:#c00;font-size:13px;margin-top:8px;min-height:16px"></div>'
        + '<div style="display:flex;justify-content:space-between;margin-top:4px;font-size:14px">'
        + '<a href="#" id="hd-forgot" style="color:#3e7697">Forgot Password?</a>'
        + '<a href="#" id="hd-create" style="color:#3e7697">Create Account</a></div>';
      // Insert into the form flow, right before the Continue button, so no
      // frozen sibling overlays the button after layout reflow.
      cont.insertAdjacentElement("beforebegin", wrap);
      $("#hd-forgot").addEventListener("click", (e) => { e.preventDefault(); renderReset((email.value || "").trim()); });
      $("#hd-create").addEventListener("click", (e) => { e.preventDefault(); renderRegister((email.value || "").trim()); });
      cont.textContent = "Sign In";
      cont.value = "Sign In";
      setTimeout(() => $("#hd-password").focus(), 30);
      $("#hd-password").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } });
    }
    async function submit() {
      const e = (email.value || "").trim();
      if (step === "email") {
        if (!e) return;
        step = "password";
        revealPassword();
        return;
      }
      const pw = ($("#hd-password") || {}).value || "";
      const msg = $("#hd-signin-msg");
      if (msg) msg.textContent = "";
      cont.disabled = true;
      const prev = cont.textContent; cont.textContent = "Signing in…";
      const r = await api("/api/account/login", { method: "POST", body: JSON.stringify({ email: e, password: pw }) });
      if (r && r.authenticated) { location.href = "/myaccount/dashboard"; return; }
      cont.disabled = false; cont.textContent = prev || "Sign In";
      const err = (r && (r.error || (r.errors && Object.values(r.errors)[0]))) || "We couldn't sign you in. Please try again.";
      if (msg) msg.textContent = err;
    }
    // The frozen page had its scripts stripped, so the button carries no stale
    // listeners; bind directly (cloning it would detach the element `enable`
    // toggles and leave the visible button stuck disabled).
    cont.addEventListener("click", (e) => { e.preventDefault(); submit(); });
    email.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } });
  }

  const AUTH_INPUT = "width:100%;max-width:420px;padding:11px;margin-bottom:10px;border:1px solid #999;border-radius:4px;font:inherit;display:block";
  const AUTH_BTN = "background:#f96302;color:#fff;border:none;padding:12px 20px;border-radius:24px;font-weight:700;font-size:15px;cursor:pointer";
  const sandboxHint = (code) => code
    ? `<div style="background:#fff7ec;border:1px solid #f96302;border-radius:6px;padding:10px 12px;margin:8px 0;font-size:13px">This offline demo sends no real email. Your verification code is <strong style="font-size:16px;letter-spacing:2px">${esc(code)}</strong>.</div>`
    : "";

  async function renderRegister(prefillEmail) {
    // Registering while a session is already signed in confuses the auth flow
    // (the store reports a conflict); guide the user instead.
    const acct = await accountState();
    if (acct && acct.authenticated) {
      mountMain(panel(`
        <h1 style="font-size:26px;font-weight:400;margin:24px 0 8px">You're already signed in</h1>
        <p style="color:#757575;margin-bottom:16px">Sign out first to create a different account.</p>
        <p><a href="/myaccount/dashboard" style="color:#3e7697">Go to My Account</a> ·
           <a href="#" id="hd-reg-signout" style="color:#3e7697">Sign Out</a></p>`));
      const so = document.getElementById("hd-reg-signout");
      if (so) so.addEventListener("click", async (e) => {
        e.preventDefault();
        await api("/api/account/logout", { method: "POST" });
        location.reload();
      });
      return;
    }
    mountMain(panel(`
      <h1 style="font-size:26px;font-weight:400;margin:24px 0 8px">Create Your Account</h1>
      <p style="color:#757575;margin-bottom:16px">Join The Home Depot to track orders, save lists and check out faster.</p>
      <div id="hd-reg-step1">
        <input id="hd-reg-email" type="email" placeholder="Email Address" value="${esc(prefillEmail || "")}" style="${AUTH_INPUT}">
        <input id="hd-reg-first" placeholder="First Name" style="${AUTH_INPUT}">
        <input id="hd-reg-last" placeholder="Last Name" style="${AUTH_INPUT}">
        <input id="hd-reg-pass" type="password" placeholder="Password (8+ characters)" autocomplete="new-password" style="${AUTH_INPUT}">
        <div id="hd-reg-msg" role="alert" style="color:#c00;font-size:13px;min-height:16px;margin-bottom:8px"></div>
        <button id="hd-reg-send" style="${AUTH_BTN}">Send Verification Code</button>
      </div>
      <div id="hd-reg-step2" style="display:none">
        <div id="hd-reg-hint"></div>
        <input id="hd-reg-code" inputmode="numeric" placeholder="6-digit code" style="${AUTH_INPUT}">
        <div id="hd-reg-msg2" role="alert" style="color:#c00;font-size:13px;min-height:16px;margin-bottom:8px"></div>
        <button id="hd-reg-finish" style="${AUTH_BTN}">Create Account</button>
      </div>
      <p style="margin-top:14px;font-size:12px;color:#757575;max-width:420px">By selecting "Create Account" you agree to The Home Depot's
        <a href="/c/customer-service" style="color:#3e7697">Terms of Use</a> and
        <a href="/c/customer-service" style="color:#3e7697">Privacy &amp; Security Statement</a>.</p>
      <p style="margin-top:10px;font-size:14px"><a href="/auth/view/signin" style="color:#3e7697">Already have an account? Sign in</a></p>`));
    $("#hd-reg-send").addEventListener("click", async () => {
      const btn = $("#hd-reg-send"), msg = $("#hd-reg-msg");
      msg.textContent = ""; btn.disabled = true; const t = btn.textContent; btn.textContent = "Sending…";
      const r = await apiRes("/api/account/register/start", { method: "POST", body: JSON.stringify({
        email: $("#hd-reg-email").value.trim(), first_name: $("#hd-reg-first").value.trim(),
        last_name: $("#hd-reg-last").value.trim(), password: $("#hd-reg-pass").value }) });
      btn.disabled = false; btn.textContent = t;
      if (r.ok) {
        $("#hd-reg-step1").style.display = "none";
        $("#hd-reg-step2").style.display = "block";
        $("#hd-reg-hint").innerHTML = sandboxHint(r.data.sandbox_code);
        $("#hd-reg-code").focus();
      } else { msg.textContent = firstErr(r.data) || "Could not start registration."; }
    });
    $("#hd-reg-finish").addEventListener("click", async () => {
      const btn = $("#hd-reg-finish"), msg = $("#hd-reg-msg2");
      msg.textContent = ""; btn.disabled = true; const t = btn.textContent; btn.textContent = "Creating…";
      const r = await apiRes("/api/account/register/complete", { method: "POST", body: JSON.stringify({ code: $("#hd-reg-code").value.trim() }) });
      if (r.ok && r.data.authenticated) { location.href = "/myaccount/dashboard"; return; }
      btn.disabled = false; btn.textContent = t; msg.textContent = firstErr(r.data) || "That code did not work.";
    });
  }

  function renderReset(prefillEmail) {
    mountMain(panel(`
      <h1 style="font-size:26px;font-weight:400;margin:24px 0 8px">Reset Your Password</h1>
      <p style="color:#757575;margin-bottom:16px">Enter your email and we'll send a verification code.</p>
      <div id="hd-rst-step1">
        <input id="hd-rst-email" type="email" placeholder="Email Address" value="${esc(prefillEmail || "")}" style="${AUTH_INPUT}">
        <div id="hd-rst-msg" role="alert" style="color:#c00;font-size:13px;min-height:16px;margin-bottom:8px"></div>
        <button id="hd-rst-send" style="${AUTH_BTN}">Send Verification Code</button>
      </div>
      <div id="hd-rst-step2" style="display:none">
        <div id="hd-rst-hint"></div>
        <input id="hd-rst-code" inputmode="numeric" placeholder="6-digit code" style="${AUTH_INPUT}">
        <input id="hd-rst-pass" type="password" placeholder="New password (8+ characters)" autocomplete="new-password" style="${AUTH_INPUT}">
        <div id="hd-rst-msg2" role="alert" style="color:#c00;font-size:13px;min-height:16px;margin-bottom:8px"></div>
        <button id="hd-rst-finish" style="${AUTH_BTN}">Reset &amp; Sign In</button>
      </div>
      <p style="margin-top:16px;font-size:14px"><a href="/auth/view/signin" style="color:#3e7697">Back to sign in</a></p>`));
    $("#hd-rst-send").addEventListener("click", async () => {
      const btn = $("#hd-rst-send"), msg = $("#hd-rst-msg");
      msg.textContent = ""; btn.disabled = true; const t = btn.textContent; btn.textContent = "Sending…";
      const r = await apiRes("/api/account/password-reset/start", { method: "POST", body: JSON.stringify({ email: $("#hd-rst-email").value.trim() }) });
      btn.disabled = false; btn.textContent = t;
      if (r.ok) {
        $("#hd-rst-step1").style.display = "none";
        $("#hd-rst-step2").style.display = "block";
        $("#hd-rst-hint").innerHTML = sandboxHint(r.data.sandbox_code);
        $("#hd-rst-code").focus();
      } else { msg.textContent = firstErr(r.data) || "Could not start reset."; }
    });
    $("#hd-rst-finish").addEventListener("click", async () => {
      const btn = $("#hd-rst-finish"), msg = $("#hd-rst-msg2");
      msg.textContent = ""; btn.disabled = true; const t = btn.textContent; btn.textContent = "Resetting…";
      const r = await apiRes("/api/account/password-reset/complete", { method: "POST", body: JSON.stringify({
        code: $("#hd-rst-code").value.trim(), new_password: $("#hd-rst-pass").value }) });
      if (r.ok && r.data.authenticated) { location.href = "/myaccount/dashboard"; return; }
      btn.disabled = false; btn.textContent = t; msg.textContent = firstErr(r.data) || "That code did not work.";
    });
  }

  async function wireAccountChip() {
    const st = await accountState();
    // Prefer the clean header's account slot; fall back to a floating chip on
    // pages without the injected header (e.g. the signin page).
    let slot = document.getElementById("hd-hdr-acct");
    const inHeader = !!slot;
    if (!slot) {
      slot = $("#hd-account-chip");
      if (!slot) {
        slot = document.createElement("div");
        slot.id = "hd-account-chip";
        slot.style.cssText = "position:fixed;top:8px;right:12px;z-index:1000;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:13px";
        document.body.appendChild(slot);
      }
    }
    if (st && st.authenticated && st.account) {
      const name = (st.account.display_name || "").split(" ")[0] || "Account";
      slot.innerHTML = inHeader
        ? '<a href="/myaccount/dashboard" style="color:#333;text-decoration:none;line-height:1.2"><span style="color:#757575;font-size:12px">Hi, ' + esc(name) + '</span><br><b style="color:#3e7697">My Account</b></a>'
          + ' <button id="hd-logout" style="background:none;border:none;color:#757575;cursor:pointer;font:inherit;text-decoration:underline;font-size:12px">Sign Out</button>'
        : '<div style="background:#fff;border:1px solid #d6d6d6;border-radius:20px;padding:6px 12px;box-shadow:0 1px 4px rgba(0,0,0,.12);display:flex;gap:10px;align-items:center">'
          + '<a href="/myaccount/dashboard" style="color:#3e7697;text-decoration:none;font-weight:700">Hi, ' + esc(name) + '</a>'
          + '<button id="hd-logout" style="background:none;border:none;color:#757575;cursor:pointer;font:inherit;text-decoration:underline">Sign Out</button></div>';
      const lo = $("#hd-logout");
      if (lo) lo.addEventListener("click", async () => {
        await api("/api/account/logout", { method: "POST", body: "{}" });
        location.href = "/";
      });
    } else {
      slot.innerHTML = inHeader
        ? '<a href="/auth/view/signin" style="color:#333;text-decoration:none;line-height:1.2"><span style="font-size:20px">&#128100;</span> <b style="color:#3e7697">Sign In</b></a>'
        : '<a href="/auth/view/signin" style="background:#fff;border:1px solid #d6d6d6;border-radius:20px;padding:6px 14px;box-shadow:0 1px 4px rgba(0,0,0,.12);color:#3e7697;text-decoration:none;font-weight:700">Sign In</a>';
    }
  }

  async function renderAccount() {
    const p = location.pathname.replace(/\/$/, "");
    if (!p.startsWith("/myaccount") && !p.startsWith("/list/")) return;
    const st = await accountState();
    if (!st || !st.authenticated) {
      mountMain(panel('<h1 style="font-size:28px;font-weight:400;margin:24px 0">Sign in to your account</h1>'
        + '<p>Please <a href="/auth/view/signin" style="color:#3e7697">sign in</a> to view your account dashboard, orders and lists.</p>'));
      return;
    }
    const a = st.account || {};
    const [od, ld] = [await api("/api/orders"), await api("/api/lists")];
    const orders = (od && od.orders) || [];
    const lists = (ld && ld.lists) || [];
    const ordBtn = "font:inherit;font-size:13px;border-radius:16px;padding:5px 12px;cursor:pointer;border:1px solid #999;background:#fff";
    const orderActions = (o) => {
      const cancellable = ["Ready for Pickup", "Processing", "Ordered"].includes(o.status);
      const returnable = ["Completed", "Picked Up"].includes(o.status);
      let b = `<button class="hd-reorder" data-order="${esc(o.order_number)}" style="${ordBtn};border-color:#f96302;color:#f96302">Buy It Again</button>`;
      if (cancellable) b = `<button class="hd-cancel" data-order="${esc(o.order_number)}" style="${ordBtn}">Cancel Order</button>` + b;
      if (returnable) b = `<button class="hd-return" data-order="${esc(o.order_number)}" style="${ordBtn}">Return Items</button>` + b;
      return `<div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">${b}</div>`;
    };
    const orderRows = orders.length ? orders.map((o) => `
      <div style="padding:12px 0;border-top:1px solid #eee">
        <div style="display:flex;justify-content:space-between">
          <div><a href="/order-confirmation?order=${encodeURIComponent(o.order_number)}" style="color:#3e7697;font-weight:700;text-decoration:none">Order #${esc(o.order_number)}</a>
            <div style="color:#757575;font-size:13px">${esc(o.status)} · ${esc((o.placed_at || "").slice(0, 10))}</div></div>
          <div style="font-weight:700">${money(o.total)}</div>
        </div>
        ${orderActions(o)}
      </div>`).join("") : '<div style="color:#757575;padding:12px 0">No orders yet.</div>';
    const listRows = lists.length ? lists.map((l) => `
      <div style="display:flex;justify-content:space-between;padding:10px 0;border-top:1px solid #eee">
        <span>${esc(l.name)}</span><span style="color:#757575">${(l.items ? l.items.length : (l.item_count || 0))} item(s)</span></div>`).join("")
      : '<div style="color:#757575;padding:12px 0">No lists yet.</div>';
    mountMain(panel(`
      <h1 style="font-size:28px;font-weight:400;margin:24px 0">Hi, ${esc((a.display_name || "").split(" ")[0] || "there")}</h1>
      <div style="display:flex;gap:24px;flex-wrap:wrap">
        <div style="flex:2;min-width:320px">
          <div style="border:1px solid #e6e6e6;border-radius:8px;padding:20px;margin-bottom:16px">
            <div style="font-weight:700;font-size:18px;margin-bottom:8px">Recent Orders</div>
            ${orderRows}
            <div style="margin-top:12px"><a href="/myaccount/purchase-history" style="color:#3e7697">View purchase history</a></div>
          </div>
          <div style="border:1px solid #e6e6e6;border-radius:8px;padding:20px">
            <div style="font-weight:700;font-size:18px;margin-bottom:8px">Your Lists</div>
            ${listRows}
          </div>
        </div>
        <div style="flex:1;min-width:260px">
          <div style="background:#f5f5f5;border-radius:8px;padding:20px">
            <div style="font-weight:700;margin-bottom:8px">Profile</div>
            <div style="margin-bottom:4px">${esc(a.display_name || "")}</div>
            <div style="color:#757575;font-size:14px;margin-bottom:16px">${esc(a.email_normalized || "")}</div>
            <button id="hd-acct-signout" style="width:100%;background:#fff;border:1px solid #999;border-radius:24px;padding:10px;font-weight:700;cursor:pointer">Sign Out</button>
          </div>
        </div>
      </div>`));
    const so = $("#hd-acct-signout");
    if (so) so.addEventListener("click", async () => {
      await api("/api/account/logout", { method: "POST", body: "{}" });
      location.href = "/";
    });
    const orderAction = (cls, suffix, after) =>
      document.querySelectorAll(cls).forEach((btn) => btn.addEventListener("click", async () => {
        btn.disabled = true;
        await apiRes("/api/order/" + encodeURIComponent(btn.dataset.order) + suffix, { method: "POST", body: "{}" });
        after();
      }));
    orderAction(".hd-cancel", "/cancel", () => renderAccount());
    orderAction(".hd-return", "/return", () => renderAccount());
    orderAction(".hd-reorder", "/reorder", async () => { await updateCartBadge(); location.href = "/cart"; });
  }

  // --- search: live results with sort / filter / compare (T04/T05/T15) -----
  const SORTS = [["default", "Top Sellers"], ["top_rated", "Top Rated"],
    ["price_low", "Price Low to High"], ["price_high", "Price High to Low"],
    ["reviews", "Most Reviews"]];

  async function renderSearch() {
    const path = location.pathname;
    if (!path.startsWith("/s/")) return;
    const query = decodeURIComponent(path.slice(3)).replace(/\+/g, " ");
    const st = { sort: "default", brands: new Set(), price_max: null, min_rating: null, compare: new Set() };

    async function load() {
      const params = new URLSearchParams({ q: query, sort: st.sort, limit: "48" });
      if (st.brands.size) params.set("brands", [...st.brands].join(","));
      if (st.price_max != null) params.set("price_max", String(st.price_max));
      if (st.min_rating != null) params.set("min_rating", String(st.min_rating));
      paint(await api("/api/search?" + params.toString()));
    }

    function stars(r) { return r ? "★".repeat(Math.round(r)) + "☆".repeat(5 - Math.round(r)) : ""; }

    function card(pr) {
      const checked = st.compare.has(pr.itemId) ? " checked" : "";
      return `<div style="border:1px solid #e6e6e6;border-radius:8px;padding:12px;display:flex;flex-direction:column">
        <a href="${esc(pr.canonicalUrl || ("/p/x/" + pr.itemId))}" style="text-align:center"><img src="${esc(pr.thumb || "")}" alt="" style="width:100%;height:150px;object-fit:contain"></a>
        <div style="font-weight:700;font-size:13px;margin-top:8px">${esc(pr.brand || "")}</div>
        <a href="${esc(pr.canonicalUrl || ("/p/x/" + pr.itemId))}" style="color:#333;text-decoration:none;font-size:14px;flex:1;margin:4px 0">${esc((pr.label || "").slice(0, 90))}</a>
        <div style="color:#f96302;font-size:13px">${stars(pr.rating)} <span style="color:#757575">(${pr.reviews || 0})</span></div>
        <div style="font-weight:700;font-size:20px;margin-top:4px">${money(pr.price)}</div>
        <label style="font-size:12px;color:#555;margin-top:6px"><input type="checkbox" class="hd-cmp" data-id="${esc(pr.itemId)}"${checked}> Compare</label>
      </div>`;
    }

    function paint(d) {
      const facets = d.facets || { brands: [], price_min: 0, price_max: 0 };
      const sortOpts = SORTS.map(([v, l]) => `<option value="${v}"${v === st.sort ? " selected" : ""}>${l}</option>`).join("");
      const brandRows = (facets.brands || []).slice(0, 10).map((b) =>
        `<label style="display:block;font-size:14px;margin:4px 0"><input type="checkbox" class="hd-fb" data-brand="${esc(b.name)}"${st.brands.has(b.name) ? " checked" : ""}> ${esc(b.name)} <span style="color:#757575">(${b.count})</span></label>`).join("");
      const grid = d.products.length
        ? `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px">${d.products.map(card).join("")}</div>`
        : `<div style="padding:32px 0"><h2 style="font-weight:400">We couldn't find results for "${esc(query)}"</h2><p style="color:#757575">Check your spelling or try a more general term. <a href="/" style="color:#3e7697">Back to home</a></p></div>`;
      mountMain(panel(`
        <div style="display:flex;justify-content:space-between;align-items:baseline;margin:20px 0 12px;flex-wrap:wrap;gap:8px">
          <h1 style="font-size:22px;font-weight:400">${d.total} result${d.total === 1 ? "" : "s"} for "${esc(query)}"</h1>
          <label style="font-size:14px">Sort by <select id="hd-sort" style="padding:6px 8px;border:1px solid #999;border-radius:4px;font:inherit">${sortOpts}</select></label>
        </div>
        <div style="display:flex;gap:24px;flex-wrap:wrap">
          <aside style="flex:0 0 220px;min-width:200px">
            <div style="font-weight:700;margin-bottom:8px">Filters</div>
            ${brandRows ? '<div style="font-weight:700;font-size:14px;margin-top:8px">Brand</div>' + brandRows : ""}
            <div style="font-weight:700;font-size:14px;margin-top:12px">Price</div>
            <label style="display:block;font-size:14px;margin:4px 0"><input type="radio" name="hd-price" class="hd-fp" data-max="" ${st.price_max == null ? "checked" : ""}> Any price</label>
            <label style="display:block;font-size:14px;margin:4px 0"><input type="radio" name="hd-price" class="hd-fp" data-max="200" ${st.price_max === 200 ? "checked" : ""}> Under $200</label>
            <label style="display:block;font-size:14px;margin:4px 0"><input type="radio" name="hd-price" class="hd-fp" data-max="400" ${st.price_max === 400 ? "checked" : ""}> Under $400</label>
            <div style="font-weight:700;font-size:14px;margin-top:12px">Rating</div>
            <label style="display:block;font-size:14px;margin:4px 0"><input type="radio" name="hd-rate" class="hd-fr" data-min="" ${st.min_rating == null ? "checked" : ""}> Any rating</label>
            <label style="display:block;font-size:14px;margin:4px 0"><input type="radio" name="hd-rate" class="hd-fr" data-min="4" ${st.min_rating === 4 ? "checked" : ""}> 4★ &amp; up</label>
            <label style="display:block;font-size:14px;margin:4px 0"><input type="radio" name="hd-rate" class="hd-fr" data-min="4.5" ${st.min_rating === 4.5 ? "checked" : ""}> 4.5★ &amp; up</label>
          </aside>
          <section style="flex:1;min-width:300px">${grid}</section>
        </div>
        <div id="hd-cmp-bar"></div>`));
      $("#hd-sort").addEventListener("change", (e) => { st.sort = e.target.value; load(); });
      document.querySelectorAll(".hd-fb").forEach((c) => c.addEventListener("change", (e) => {
        const bd = e.target.dataset.brand; if (e.target.checked) st.brands.add(bd); else st.brands.delete(bd); load();
      }));
      document.querySelectorAll(".hd-fp").forEach((c) => c.addEventListener("change", (e) => {
        st.price_max = e.target.dataset.max ? parseFloat(e.target.dataset.max) : null; load();
      }));
      document.querySelectorAll(".hd-fr").forEach((c) => c.addEventListener("change", (e) => {
        st.min_rating = e.target.dataset.min ? parseFloat(e.target.dataset.min) : null; load();
      }));
      document.querySelectorAll(".hd-cmp").forEach((c) => c.addEventListener("change", (e) => {
        const id = e.target.dataset.id; if (e.target.checked) st.compare.add(id); else st.compare.delete(id); compareBar();
      }));
      compareBar();
    }

    function compareBar() {
      const bar = $("#hd-cmp-bar"); if (!bar) return;
      if (st.compare.size < 2) { bar.innerHTML = st.compare.size === 1 ? '<div style="position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid #ccc;padding:12px;text-align:center;z-index:950">Select at least one more item to compare.</div>' : ""; return; }
      bar.innerHTML = `<div style="position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid #ccc;padding:12px;text-align:center;z-index:950">
        <button id="hd-cmp-go" style="background:#f96302;color:#fff;border:none;border-radius:24px;padding:10px 24px;font-weight:700;cursor:pointer">Compare (${st.compare.size})</button>
        <button id="hd-cmp-clear" style="margin-left:8px;background:none;border:none;color:#3e7697;cursor:pointer">Clear</button></div>`;
      $("#hd-cmp-go").addEventListener("click", showCompare);
      $("#hd-cmp-clear").addEventListener("click", () => { st.compare.clear(); load(); });
    }

    async function showCompare() {
      const items = [];
      for (const id of st.compare) { const pr = await api("/api/products/" + encodeURIComponent(id)); if (pr && !pr.error) items.push(pr); }
      const rows = (label, fn) => `<tr><th style="text-align:left;padding:8px;border-bottom:1px solid #eee;background:#f5f5f5">${label}</th>${items.map((p) => `<td style="padding:8px;border-bottom:1px solid #eee">${fn(p)}</td>`).join("")}</tr>`;
      mountMain(panel(`
        <h1 style="font-size:24px;font-weight:400;margin:20px 0">Compare ${items.length} items</h1>
        <div style="overflow-x:auto"><table style="border-collapse:collapse;width:100%;min-width:520px">
          ${rows("", (p) => `<img src="${esc(p.thumb || "")}" style="width:90px;height:90px;object-fit:contain">`)}
          ${rows("Brand", (p) => esc(p.brand || ""))}
          ${rows("Product", (p) => `<a href="${esc(p.canonicalUrl || ("/p/x/" + p.itemId))}" style="color:#3e7697;text-decoration:none">${esc((p.label || "").slice(0, 60))}</a>`)}
          ${rows("Model", (p) => esc(p.model || ""))}
          ${rows("Price", (p) => money(p.price))}
          ${rows("Rating", (p) => (p.rating || "—") + " (" + (p.reviews || 0) + ")")}
        </table></div>
        <div style="margin-top:16px"><a href="#" id="hd-cmp-back" style="color:#3e7697">← Back to results</a></div>`));
      $("#hd-cmp-back").addEventListener("click", (e) => { e.preventDefault(); load(); });
    }

    load();
  }

  // The home page's "Top Categories" / "Special Buy" modules are JS-driven
  // carousels captured in their skeleton (loading) state — the source snapshot
  // shows grey placeholder boxes because the population script was stripped.
  // Fill them with real catalog content so the page reads as a fully-loaded
  // home (HD's own carousels are personalised and vary per visit).
  async function fillHomeCarousels() {
    const path = location.pathname.replace(/\/$/, "");
    // Skip pages where mountMain overlays the frozen body with a live panel
    // (search/cart/checkout/account/confirmation/list/auth) — nothing to fill —
    // but still clean up the frozen body's never-loading skeleton / "Loading
    // Recommendations" blocks so no grey placeholder shows behind the live panel.
    if (/^\/(s\/|cart|checkout|order-confirmation|myaccount|list|auth)/.test(path + "/")) {
      collapseEmptyDynamic();
      setTimeout(collapseEmptyDynamic, 900);
      setTimeout(collapseEmptyDynamic, 2000);
      return;
    }
    let data; try { data = await api("/api/search?q=&sort=top_rated&limit=90"); } catch (e) { return; }
    const products = (data && data.products) || [];
    if (!products.length) return;
    const catMap = new Map();
    for (const p of products) { const c = p.category || "Tools"; if (!catMap.has(c)) catMap.set(c, p); }
    const cats = [...catMap.entries()];

    const SKEL = '[class*="skeleton" i],[class*="animate-pulse" i],[class*="placeholder" i]';
    const isProductImg = (im) => (im.currentSrc || im.src || "").includes("/assets/")
      && !/\.svg(\?|$)/i.test(im.currentSrc || im.src || "");  // ignore logo SVGs
    // The carousel "track" = the tight parent that directly holds the skeleton
    // boxes, so replacing it never wipes a section logo or an already-loaded
    // sibling (e.g. Top Deals).
    const skelContainer = (re) => {
      for (const h of document.querySelectorAll("h1,h2,h3")) {
        if (!re.test((h.textContent || "").trim())) continue;
        let scope = h.parentElement;
        for (let i = 0; i < 5 && scope; i++, scope = scope.parentElement) {
          const skels = scope.querySelectorAll(SKEL);
          if (!skels.length) continue;
          const track = skels[0].parentElement || scope;
          if ([...track.querySelectorAll("img")].some(isProductImg)) continue;
          return track;
        }
      }
      return null;
    };
    // The fills sit inside frozen flex ancestors whose items default to
    // min-width:auto, so a fixed-width flex strip inflates the whole track past
    // its module (tiles bleed out / get chopped mid-tile). A wrapping grid has a
    // small min-content, so the track can shrink to its module and every tile
    // stays fully inside — no clipping, no overflow.
    const row = (inner) => '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:14px;padding:8px 2px 4px;width:100%;min-width:0;box-sizing:border-box">' + inner + "</div>";
    const catTile = (name, p) => `<a href="/s/${encodeURIComponent(name)}" style="min-width:0;text-align:center;text-decoration:none;color:#333">
        <div style="border:1px solid #e6e6e6;border-radius:8px;overflow:hidden;background:#fff"><img src="${esc(p.thumb || "")}" alt="${esc(name)}" style="width:100%;height:140px;object-fit:contain"></div>
        <div style="font-weight:700;margin-top:8px;font-size:14px">${esc(name)}</div></a>`;
    const prodCard = (p) => `<a href="${esc(p.canonicalUrl || ("/p/x/" + p.itemId))}" style="min-width:0;border:1px solid #e6e6e6;border-radius:8px;padding:12px;text-decoration:none;color:#333;background:#fff">
        <img src="${esc(p.thumb || "")}" alt="" style="width:100%;height:120px;object-fit:contain">
        <div style="font-weight:700;font-size:12px;margin-top:6px">${esc(p.brand || "")}</div>
        <div style="font-size:13px;min-height:34px;overflow:hidden">${esc((p.label || "").slice(0, 46))}</div>
        <div style="color:#f96302;font-size:12px">${p.rating ? "★ " + p.rating + " (" + (p.reviews || 0) + ")" : ""}</div>
        <div style="font-weight:700;font-size:18px">${money(p.price)}</div></a>`;
    // Let the track (and any flex ancestors between it and its module) shrink:
    // flex items default to min-width:auto, which is what let the old strip
    // inflate them beyond the module's box.
    const allowShrink = (track) => {
      let el = track;
      for (let i = 0; i < 5 && el && el !== document.body; i++, el = el.parentElement) {
        const parent = el.parentElement;
        if (parent && getComputedStyle(parent).display.includes("flex")) {
          // shrinkable below content AND grow to fill the module's row
          el.style.minWidth = "0";
          el.style.flex = "1 1 auto";
          // The frozen carousel leaves empty slide husks beside the filled one
          // (imageless, textless flex shells) that eat module width — drop them.
          for (const sib of parent.children) {
            if (sib === el) continue;
            if (!sib.querySelector("img") && (sib.textContent || "").trim() === "") sib.style.display = "none";
          }
        }
      }
      track.style.maxWidth = "100%";
      track.style.overflow = "hidden";
    };

    // Classify each carousel by its section heading: fill category modules with
    // category tiles and product modules with real product cards; anything else
    // that is still a skeleton gets hidden so no grey placeholder ever shows.
    const CATEGORY_RE = /Top Categories|Shop by Category|Explore Categories/i;
    const PRODUCT_RE = /Special Buy|One Week Only|Top Deals|Can.t Miss|Recommended|Frequently Bought|Bought Together|Also (Viewed|Bought)|Customers Also|Related|Compare Similar|Sponsored|More to Explore|Popular|Savings|You (Might|May)/i;
    const trackFor = (h) => {
      let scope = h.parentElement;
      for (let i = 0; i < 5 && scope; i++, scope = scope.parentElement) {
        const s = scope.querySelector(SKEL);
        if (!s) continue;
        const track = s.parentElement || scope;
        if (![...track.querySelectorAll("img")].some(isProductImg)) return track;
      }
      return null;
    };
    let off = 0;
    document.querySelectorAll("h1,h2,h3").forEach((h) => {
      const txt = (h.textContent || "").trim();
      if (!CATEGORY_RE.test(txt) && !PRODUCT_RE.test(txt)) return;
      const track = trackFor(h);
      if (!track) return;
      if (CATEGORY_RE.test(txt)) track.innerHTML = row(cats.map(([n, p]) => catTile(n, p)).join(""));
      else { track.innerHTML = row(products.slice(off, off + 8).map(prodCard).join("")); off = (off + 6) % 70; }
      allowShrink(track);
    });
    // Hide leftover skeleton / never-loading dynamic blocks (handled centrally in
    // collapseEmptyDynamic so the same cleanup runs on the live-panel pages too).
    collapseEmptyDynamic();
    // Personalised hydrator cards can mount their spinner a beat late; re-sweep.
    setTimeout(collapseEmptyDynamic, 900);
    setTimeout(collapseEmptyDynamic, 2000);
  }

  // Personalised / dynamic home modules (THD "php-hydrator" and "personalized-*"
  // sections, plus any residual loading spinner) never populate offline — their
  // fetch/hydration script is stripped from the frozen snapshot, so they sit as
  // an empty white band or an endlessly-spinning loader. Collapse the empty ones
  // (their whole grid cell) so no gap or spinner ever shows. A hydrator that
  // fillHomeCarousels already populated has real content and is left untouched.
  function collapseEmptyDynamic() {
    const isEmpty = (el) => {
      if (!el) return false;
      const hasImg = [...el.querySelectorAll("img")].some((im) => im.naturalWidth > 20);
      return !hasImg && (el.textContent || "").replace(/\s+/g, " ").trim().length < 40;
    };
    const cellOf = (el) => {
      let c = el;
      for (let i = 0; i < 6 && c && c !== document.body; i++, c = c.parentElement) {
        if (/sui-col-span/.test((c.className || "").toString())) return c;
      }
      return el;
    };
    document.querySelectorAll('[id*="php-hydrator"],[id*="personalized"],[class*="spinner" i]').forEach((el) => {
      const sec = el.closest('[id*="php-hydrator"],[id*="personalized"]') || el;
      const cell = cellOf(sec);
      if (!cell || cell.dataset.wbCollapsed) return;
      if (isEmpty(cell)) { cell.style.display = "none"; cell.dataset.wbCollapsed = "1"; }
    });
    // "Loading Recommendations"-style carousels never resolve offline; hide the
    // heading so no perpetual "Loading …" label is left once its skeletons go.
    document.querySelectorAll("h1,h2,h3").forEach((h) => {
      if (/^\s*loading\b/i.test(h.textContent || "")) h.style.display = "none";
    });
    // Finally drop any leftover visible skeleton / pulse / placeholder box so the
    // page never shows a grey loading tile (runs on every page, live-panel ones
    // included, where fillHomeCarousels does not fill anything).
    document.querySelectorAll('[class*="skeleton" i],[class*="animate-pulse" i],[class*="placeholder" i]').forEach((sk) => {
      try { if (sk.getBoundingClientRect().height > 8) sk.style.display = "none"; } catch (e) {}
    });
  }

  // Frozen snapshots keep the source's lazy-loading (loading="lazy" / data-src),
  // but the script that swaps them in was stripped, so valid images can stay
  // unloaded (grey) below the fold. Force them to load eagerly and hide any that
  // genuinely 404 so no broken-image icon or grey box remains.
  function forceLoadImages() {
    const isGray = (el) => {
      const m = getComputedStyle(el).backgroundColor.match(/rgb\((\d+),\s*(\d+),\s*(\d+)/);
      if (!m) return false;
      const c = [+m[1], +m[2], +m[3]];
      return Math.abs(c[0] - c[1]) < 8 && Math.abs(c[1] - c[2]) < 8 && c[0] >= 224 && c[0] <= 249;
    };
    // Hide a broken image and collapse any grey placeholder box wrapping it, so
    // neither a broken-image icon nor an empty grey panel remains.
    const hideBroken = (im) => {
      im.style.visibility = "hidden";
      let el = im.parentElement;
      for (let i = 0; i < 3 && el; i++, el = el.parentElement) {
        const r = el.getBoundingClientRect();
        if (r.height > 90 && isGray(el) && (el.textContent || "").trim() === "") { el.style.display = "none"; break; }
      }
    };
    const collapseSlot = (im) => {  // hide a big media slot whose image is broken
      let el = im;
      for (let i = 0; i < 4 && el; i++, el = el.parentElement) {
        const r = el.getBoundingClientRect();
        if (r.width > 360 && r.height > 360) {
          if (![...el.querySelectorAll("img")].some((x) => x.naturalWidth > 0)) el.style.display = "none";
          return;
        }
      }
      hideBroken(im);
    };
    const kick = (im) => {
      if (im.dataset.wbKicked) return; im.dataset.wbKicked = "1";
      const ds = im.getAttribute("data-src") || im.getAttribute("data-lazy") || im.getAttribute("data-original");
      // Only adopt a data-* value that is an actual URL/path — many frozen imgs
      // carry data-lazy="true"/data-loaded markers that are NOT sources.
      if (ds && ds !== im.getAttribute("src") && /[/.]/.test(ds) && !/^(true|false)$/i.test(ds)) {
        try { im.setAttribute("src", ds); } catch (e) {}
      }
      if (im.getAttribute("loading") === "lazy") im.loading = "eager";
      im.addEventListener("error", () => collapseSlot(im), { once: true });
    };
    // Broken images (incl. lazy slots that mount only on scroll) are swept
    // repeatedly and on scroll: valid-but-unloaded get retriggered, genuinely
    // broken large slots collapse so no grey media panel / broken glyph shows.
    const sweep = () => {
      document.querySelectorAll("img").forEach((im) => {
        kick(im);
        if (im.naturalWidth !== 0) return;
        const s = im.getAttribute("src");
        if (!s || /^(true|false)$/i.test(s)) { collapseSlot(im); return; }
        if (im.dataset.wbProbed) return; im.dataset.wbProbed = "1";
        const probe = new Image();
        probe.onload = () => { im.setAttribute("src", s); };
        probe.onerror = () => collapseSlot(im);
        probe.src = s;
      });
    };
    sweep();
    let sweeps = 0;
    const timer = setInterval(() => { sweep(); if (++sweeps >= 8) clearInterval(timer); }, 700);
    let st; window.addEventListener("scroll", () => { clearTimeout(st); st = setTimeout(sweep, 200); }, { passive: true });
  }

  function stripAdFrames() {
    // The frozen PLP/search snapshots embed RevJet ad units as <iframe srcdoc>
    // creatives whose escaped scripts fire rmt.homedepot.com beacons. Their
    // srcdoc is neutralized at build time; remove the empty frames so no blank
    // ad gap remains (defense-in-depth against any residual beacon).
    document.querySelectorAll('iframe[name="revjet-single-iframe"], iframe[data-wb-neutralized], iframe[data-revjet-options]')
      .forEach((f) => f.remove());
  }

  // The PDP media gallery is a JS-driven "main image + thumbnail rail" widget.
  // With that script stripped, each ~80px thumbnail balloons to an 800px square
  // and they stack vertically — ~6000px of grey boxes each holding one tiny
  // 100px image (plus a couple of empty slots). Rebuild it as a clean, compact
  // gallery: keep the large main image and lay the real thumbnails out as a
  // horizontal strip (empty/placeholder slots hidden, duplicates removed,
  // click-to-swap wired) so the gallery matches the official main+thumbnails.
  function fixupPDPGallery() {
    const gal = document.querySelector('.mediagallery, [class*="mediagallery"]:not([class*="thumbnail"])');
    if (!gal || gal.dataset.wbGallery) return;
    const slots = [...gal.querySelectorAll('[class*="mediagallery__thumbnail"]')];
    if (!slots.length) return;
    gal.dataset.wbGallery = "1";
    const badSrc = (s) => !s || /^(true|false)$/i.test(s) || /^\s*$/.test(s);
    const mainImg = gal.querySelector("img");
    const strip = slots[0].parentElement;
    if (strip) {
      strip.style.cssText += ";display:flex;flex-direction:row;flex-wrap:wrap;gap:8px;height:auto;max-height:none;margin-top:12px;align-items:flex-start;";
    }
    const seen = new Set();
    slots.forEach((s) => {
      const im = s.querySelector("img");
      const src = im && im.getAttribute("src");
      if (!im || badSrc(src) || seen.has(src)) { s.style.display = "none"; return; }
      seen.add(src);
      s.style.cssText += ";width:76px;height:76px;aspect-ratio:auto;flex:0 0 76px;border:1px solid #d6d6d6;border-radius:6px;overflow:hidden;cursor:pointer;padding:2px;background:#fff;position:relative;";
      im.style.cssText += ";width:100%;height:100%;object-fit:contain;position:static;";
      s.addEventListener("click", () => {
        if (mainImg && src) { try { mainImg.setAttribute("src", src); } catch (e) {} }
        slots.forEach((x) => { x.style.borderColor = "#d6d6d6"; });
        s.style.borderColor = "#f96302";
      });
    });
  }

  // The Customer Service "Explore Help Topics" accordions ship their panels open
  // (the collapse script was stripped), so every topic's link list is dumped
  // inline. Collapse each panel by default — matching the official collapsed
  // look — and wire the header to toggle it, so the accordion is both faithful
  // and functional (a collapsed-but-dead accordion would hide the links for good).
  function wireAccordions() {
    document.querySelectorAll(".content-accordion").forEach((acc) => {
      if (acc.dataset.wbAccordion) return;
      const header = acc.querySelector('[role="button"], [id*="-header"]');
      const content = acc.querySelector('[role="region"], [id*="-content"]');
      if (!header || !content) return;
      acc.dataset.wbAccordion = "1";
      const chevron = header.querySelector("svg");
      const setOpen = (open) => {
        content.style.display = open ? "" : "none";
        header.setAttribute("aria-expanded", open ? "true" : "false");
        if (chevron) { chevron.style.transition = "transform .2s"; chevron.style.transform = open ? "rotate(180deg)" : ""; }
      };
      setOpen(false);
      header.style.cursor = "pointer";
      header.addEventListener("click", () => setOpen(content.style.display === "none"));
    });
  }

  function injectFixupCSS() {
    // The source sizes several JS-driven tile carousels at runtime; with those
    // scripts stripped the `card-tile__collection` grids fall back to 2 huge
    // columns (~684px tiles vs the source's ~203px). Restore a multi-column
    // tile grid so these modules match the official layout.
    if (document.getElementById("hd-fixup-css")) return;
    // The home hero grid uses responsive column spans (e.g. lg:sui-col-span-8 /
    // lg:sui-col-span-4 for the wide+narrow banner rows), but those responsive
    // utility rules are missing from the localized CSS bundle, so items fall
    // back to sui-col-span-12 (full width) and banners blow up to ~800px tall.
    // Re-supply the responsive col-span (and offset) rules at md/lg breakpoints.
    // Responsive grid-template-columns utilities (sui-grid-cols-N) are only
    // partially present in the localized CSS (no xl:, several md:/lg: absent), so
    // multi-column grids such as the PLP "Related Products" strip (xl:grid-cols-6
    // lg:grid-cols-4 …) collapse to the 2-col base and blow their tiles up to
    // ~578px squares. Re-supply the full grid-cols and col-span sets at every
    // breakpoint, emitted ascending so the widest matching variant wins —
    // reproducing the source's intended column counts.
    const cols = (prefix) => {
      let s = "";
      for (let n = 1; n <= 12; n++) {
        const sel = prefix ? `.${prefix}\\:sui-grid-cols-${n}` : `.sui-grid-cols-${n}`;
        s += `${sel}{grid-template-columns:repeat(${n},minmax(0,1fr))!important;}`;
      }
      return s;
    };
    const spanSet = (prefix) => {
      let s = "";
      for (let n = 1; n <= 12; n++) {
        s += `.${prefix}\\:sui-col-span-${n}{grid-column:span ${n}/span ${n}!important;}`;
      }
      return s;
    };
    // The Customer Service (/c/) page's captured CSS bundle is missing a large
    // set of sui-* sizing utilities (display:grid, w-full/h-full and the numeric
    // w-N/h-N icon sizes). Without them its topic-tile images fall back to their
    // 703px intrinsic size and the accordion chevron SVGs stretch to ~1400px,
    // blowing the page to ~30000px. Re-supply the utilities — scoped to /c/ only
    // so the fully-working home/PDP/PLP/search bundles are never touched.
    let helpFix = "";
    if (/^\/c\//.test(location.pathname)) {
      helpFix = ".sui-grid{display:grid;}.sui-w-full{width:100%;}.sui-h-full{height:100%;}"
        // sui-paper-outlined (the topic-tile cards) also lost its border rule.
        + ".sui-paper-outlined{border:1px solid #cccccc;border-radius:12px;}";
      const sizes = [];
      for (let n = 1; n <= 24; n++) sizes.push(n);
      [28, 32, 40, 48, 56, 64].forEach((n) => sizes.push(n));
      sizes.forEach((n) => {
        const rem = n * 0.25 + "rem";
        helpFix += `.sui-w-${n}{width:${rem};}.sui-h-${n}{height:${rem};}`;
      });
    }
    const st = document.createElement("style");
    st.id = "hd-fixup-css";
    st.textContent =
      // card-tile collections keep their auto-fill sizing (higher specificity
      // than the bare .sui-grid-cols-N rules below, so this wins for them).
      ".card-tile__collection.sui-grid{grid-template-columns:repeat(auto-fill,minmax(170px,1fr))!important;}"
      + cols("")
      + "@media(min-width:640px){" + cols("sm") + "}"
      + "@media(min-width:768px){" + spanSet("md") + cols("md") + "}"
      + "@media(min-width:1024px){" + spanSet("lg") + cols("lg") + "}"
      + "@media(min-width:1280px){" + spanSet("xl") + cols("xl") + "}"
      + helpFix
      + "#hd-clean-header + *{scroll-margin-top:96px;}";
    document.head.appendChild(st);
  }

  function boot() {
    injectFixupCSS();
    stripAdFrames();
    mountHeader();
    fillHomeCarousels();
    forceLoadImages();
    fixupPDPGallery();
    setTimeout(fixupPDPGallery, 800);
    wireAccordions();
    // Reflect the current query in the header search box on results pages.
    if (location.pathname.startsWith("/s/")) {
      const q = document.getElementById("hd-hdr-q");
      if (q) q.value = decodeURIComponent(location.pathname.slice(3)).replace(/\+/g, " ");
    }
    wireSearch();
    wirePDP();
    updateCartBadge();
    wireAccountChip();
    wireSignin();
    renderAccount();
    renderSearch();
    renderCart();
    renderCheckout();
    renderConfirmation();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
