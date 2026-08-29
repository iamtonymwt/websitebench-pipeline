/*
 * websitebench humble-bundle interaction layer.
 * Injected with `defer` on every frozen page; binds by location.pathname.
 * Same-origin JSON API only (see clone/app.py). No dependencies.
 * Constraint: on frozen-oracle surfaces (the two captured bundle pages and
 * the portal search grid) nothing re-renders at load — listeners only.
 */
(function () {
  'use strict';

  /* ---------- helpers ---------- */

  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined) return;
        if (k === 'text') node.textContent = v;
        else if (k === 'html') node.innerHTML = v;
        else if (k === 'style' && typeof v === 'object') Object.keys(v).forEach(function (s) { node.style[s] = v[s]; });
        else if (k.indexOf('on') === 0 && typeof v === 'function') node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v);
      });
    }
    (children || []).forEach(function (c) {
      if (c === null || c === undefined) return;
      node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return node;
  }

  function commas(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }

  /* Oracle: "CA$" + thousands commas + always 2 decimals (CA$1,234.56). */
  function money(minor) {
    var n = Math.round(Number(minor) || 0);
    var sign = n < 0 ? '-' : '';
    n = Math.abs(n);
    var cents = String(n % 100);
    if (cents.length < 2) cents = '0' + cents;
    return sign + 'CA$' + commas(Math.floor(n / 100)) + '.' + cents;
  }
  /* Frozen split rows / preset labels drop ".00" on whole dollars (CA$9, CA$30). */
  function moneyTrim(minor) { return money(minor).replace(/\.00$/, ''); }
  function dollarsValue(minor) {
    return (Math.round(Number(minor) || 0) / 100).toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1');
  }

  /* Media fields may be plain URL strings or {local, source_url} objects. */
  function mediaUrl(v) {
    if (!v) return '';
    if (typeof v === 'string') return v;
    if (typeof v === 'object') return v.local || v.source_url || '';
    return '';
  }
  function firstMedia(media, keys) {
    if (!media || typeof media !== 'object') return '';
    for (var i = 0; i < keys.length; i++) {
      var u = mediaUrl(media[keys[i]]);
      if (u) return u;
    }
    return '';
  }

  function api(path, opts) {
    opts = opts || {};
    var init = {
      method: opts.method || (opts.body !== undefined ? 'POST' : 'GET'),
      headers: {},
      credentials: 'same-origin'
    };
    if (opts.body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.body);
    }
    return fetch(path, init).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        return { ok: r.ok, status: r.status, data: data };
      });
    }, function (err) {
      return { ok: false, status: 0, data: { error: 'network', message: String(err) } };
    });
  }

  function debounce(fn, ms) {
    var t = null;
    return function () {
      var args = arguments, self = this;
      if (t) clearTimeout(t);
      t = setTimeout(function () { t = null; fn.apply(self, args); }, ms);
    };
  }

  function safeDecode(s) {
    try { return decodeURIComponent(s); } catch (e) { return s; }
  }

  function params() {
    var out = {};
    var raw = location.search.replace(/^\?/, '');
    if (!raw) return out;
    raw.split('&').forEach(function (pair) {
      if (!pair) return;
      var i = pair.indexOf('=');
      var k = safeDecode(i < 0 ? pair : pair.slice(0, i)).replace(/\+/g, ' ');
      var v = i < 0 ? '' : safeDecode(pair.slice(i + 1).replace(/\+/g, ' '));
      if (!(k in out)) out[k] = v;
    });
    return out;
  }

  /* Only same-origin absolute paths may be redirect targets. */
  function safeGoto(fallback) {
    var g = params().goto || '';
    if (g && g.charAt(0) === '/' && g.charAt(1) !== '/') return g;
    return fallback || '/';
  }

  function run(name, fn) {
    try { fn(); } catch (err) {
      try { console.warn('[hb-app] module "' + name + '" failed:', err); } catch (e2) { /* noop */ }
    }
  }

  function fmtDate(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return months[d.getMonth()] + ' ' + d.getDate() + ', ' + d.getFullYear();
  }

  /* Icon classes and display labels are the source's own: the frozen store
     page carries `li.operating-system.hb.hb-<icon>[title="<label>"]` and
     `li.platform.hb.hb-<icon>`, and the store platform facets spell the same
     labels (Windows / Mac / Linux / Nintendo Switch / Oculus Rift / Steam). */
  var OS_ICON = {
    windows: 'hb-windows', mac: 'hb-osx', linux: 'hb-linux',
    'oculus-rift': 'hb-oculus', switch: 'hb-switch'
  };
  var OS_LABEL = {
    windows: 'Windows', mac: 'Mac', linux: 'Linux',
    'oculus-rift': 'Oculus Rift', switch: 'Nintendo Switch'
  };
  var DRM_ICON = {
    steam: 'hb-steam', epic: 'hb-epic', switch: 'hb-switch',
    download: 'hb-drmfree', 'other-key': 'hb-key'
  };
  var DRM_LABEL = {
    steam: 'Steam', epic: 'Epic Games Store', switch: 'Nintendo Switch',
    download: 'DRM-Free', 'other-key': 'Key'
  };
  /* Captured drawer order (and the product page's operating-systems list
     order): windows, mac, linux. */
  var OS_ORDER = ['windows', 'mac', 'linux', 'oculus-rift', 'switch'];
  function osIcon(os) { return OS_ICON[os] || ('hb-' + os); }
  function osLabel(os) { return OS_LABEL[os] || os; }
  function drmIcon(drm) { return DRM_ICON[drm] || ('hb-' + drm); }
  function drmLabel(drm) { return DRM_LABEL[drm] || drm; }
  function orderedPlatforms(list) {
    var rest = (list || []).slice();
    var out = [];
    OS_ORDER.forEach(function (os) {
      var at = rest.indexOf(os);
      if (at >= 0) { out.push(os); rest.splice(at, 1); }
    });
    return out.concat(rest);
  }

  var path = location.pathname.replace(/\/+$/, '') || '/';
  var FROZEN_BUNDLES = { 'yes-chef-cooking-bundle': 1, '2k-megahits-2026-bundle': 1 };

  /* ---------- shared account + cart state ---------- */

  var accountPromise = null;
  function getAccount() {
    if (!accountPromise) {
      accountPromise = api('/api/account').then(function (r) {
        return (r.ok && r.data && r.data.authenticated) ? r.data : { authenticated: false, account: null };
      });
    }
    return accountPromise;
  }

  var cartState = { count: 0, items: [], total_minor: 0 };
  var cartListeners = [];
  function onCart(fn) { cartListeners.push(fn); fn(cartState); }
  function setCart(view) {
    if (!view || typeof view !== 'object') return;
    cartState = view;
    cartListeners.forEach(function (fn) {
      try { fn(cartState); } catch (e) { /* keep other listeners alive */ }
    });
  }
  function refreshCart(splitMode) {
    var q = splitMode ? '?split_mode=' + encodeURIComponent(splitMode) : '';
    return api('/api/cart' + q).then(function (r) { if (r.ok) setCart(r.data); return cartState; });
  }
  function cartAdd(kind, slug, amountMinor) {
    var body = { kind: kind, slug: slug };
    if (amountMinor !== undefined && amountMinor !== null) body.amount_minor = amountMinor;
    return api('/api/cart/add', { body: body }).then(function (r) {
      if (r.ok) setCart(r.data);
      return r;
    });
  }
  function cartAddAndOpen(kind, slug, amountMinor) {
    return cartAdd(kind, slug, amountMinor).then(function (r) {
      openDrawer();
      if (!r.ok) drawerNotify([document.createTextNode(r.data.message || 'Could not add the item to your cart.')]);
      return r;
    });
  }

  /* ---------- cart drawer (client-side, all pages) ---------- */
  /* REFINE-AFTER-HANDOFF: drawer interior mirrors the captured store-page
     skeleton; the source's authenticated drawer states are refined after
     handoff tr-001. */

  var drawer = null;
  var lastRemoveSnapshot = null;

  function drawerStyles(isConstructed) {
    return isConstructed ? {
      grayout: { position: 'fixed', top: '0', left: '0', right: '0', bottom: '0', background: 'rgba(0,0,0,0.5)', overflowY: 'auto', zIndex: '10000' },
      contents: { margin: '40px auto', fontSize: '16px', width: '92%', maxWidth: '55em', background: '#eff2fb', color: '#494f5c', textAlign: 'left', boxShadow: '0 3px 8px rgba(0,0,0,0.2)', borderRadius: '3px', position: 'relative', padding: '0 0 12px' }
    } : { grayout: {}, contents: {} };
  }

  /* Pages that carry the frozen #js-cart-container also carry the source
     stylesheet, so the drawer's row/total markup needs no inline styling and
     stays byte-comparable with the capture. The drawer hb-app.js *constructs*
     elsewhere has no such stylesheet, so the handful of source rules the cart
     interior depends on are injected once, verbatim from the frozen sheet. */
  function ensureConstructedDrawerStyles() {
    if (qs('#js-hb-drawer-style')) return;
    document.head.appendChild(el('style', {
      id: 'js-hb-drawer-style',
      text: [
        '.js-hb-constructed .cart-group{padding:0 20px}',
        '.js-hb-constructed .shopping-cart-row{padding:19px 0 17px 0;position:relative}',
        '.js-hb-constructed .shopping-cart-row+.shopping-cart-row{border-top:1px solid #c7cbd4}',
        '.js-hb-constructed .row-contents{display:flex;white-space:nowrap}',
        '.js-hb-constructed .remove-from-cart{margin-right:16px;cursor:pointer;color:rgba(72,78,91,0.4);float:left}',
        '.js-hb-constructed .cart-item-information-wrapper{flex:1;text-overflow:ellipsis;overflow:hidden;white-space:nowrap}',
        '.js-hb-constructed .cart-item-name{font-weight:500;line-height:24px;margin:0;text-decoration:none;color:inherit}',
        '.js-hb-constructed .cart-platforms{display:inline-block;margin:0 0 0 10px;padding:0;list-style:none}',
        '.js-hb-constructed .cart-item-price{margin:0 0 0 4px}',
        '.js-hb-constructed .cart-item-price s{margin:0 8px}',
        '.js-hb-constructed .cart-item-price .discounted{color:#db1a00}',
        '.js-hb-constructed .shopping-cart-empty p{text-align:center;color:#7b818c;margin:19px 0 17px 0}',
        '.js-hb-constructed .total-holder{border-top:1px solid #c7cbd4;padding:17px 20px 17px 49px;font-weight:bold}',
        '.js-hb-constructed .total-holder .total-row:not(:first-child){margin-top:17px}',
        '.js-hb-constructed .total-holder .total-heading{display:inline-block;margin:0}',
        '.js-hb-constructed .total-holder .total{display:inline-block;float:right;margin:0}',
        '.js-hb-constructed .total-holder .total-amount.is-original{text-decoration:line-through}',
        '.js-hb-constructed .total-holder .total-amount.is-discounted{color:#db1a00;margin-left:10px}',
        '.js-hb-constructed .rewards-total-holder{border-top:1px solid #c7cbd4;padding:17px 20px}',
        '.js-hb-constructed .rewards-total-holder.inactive{display:none}',
        '.js-hb-constructed .rewards-line-item>*{display:inline-block}',
        '.js-hb-constructed .rewards-line-item .line-item-amount{float:right}',
        '.js-hb-constructed .monthly-promo-wrapper{color:#fff;background:#4c4a63;text-align:center;padding:1em}',
        '.js-hb-constructed .monthly-promo-wrapper h2{text-transform:uppercase;font-weight:bold}',
        '.js-hb-constructed .sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}'
      ].join('')
    }));
  }

  function ensureDrawer() {
    if (drawer) return drawer;
    var container = qs('#js-cart-container');
    var constructed = false;
    if (!container) {
      constructed = true;
      ensureConstructedDrawerStyles();
      container = el('div', { id: 'js-cart-container', 'class': 'cart-container js-cart-container' });
      var st = drawerStyles(true);
      container.appendChild(el('div', { 'class': 'js-shopping-cart shopping-cart' }, [
        el('div', { 'class': 'js-grayout shopping-cart-grayout', style: st.grayout }, [
          el('div', { 'class': 'js-cart-contents cart-contents js-hb-constructed', tabindex: '0', style: st.contents }, [
            el('div', { 'class': 'fixed-width-container' }, [
              el('a', { 'class': 'js-close-cart close-cart', href: '#', style: constructed ? { position: 'absolute', top: '10px', right: '12px', textDecoration: 'none', color: '#a1a7b2', fontSize: '18px' } : null, text: '✕' }),
              el('div', { 'class': 'cart-section-header', style: { padding: '16px 20px 0' } }, [
                el('h1', { text: 'Shopping Cart' })
              ]),
              el('div', { 'class': 'cart-notifications js-cart-notifications' }),
              el('div', { 'class': 'cart-contents-holder' }, [el('div', { 'class': 'js-shopping-cart-row-holder' })]),
              el('div', { 'class': 'js-shopping-cart-total-holder total-holder', style: { display: 'none' } }),
              el('div', { 'class': 'js-rewards-total-holder rewards-total-holder inactive' }),
              el('div', { 'class': 'js-shopping-cart-monthly-promo' })
            ])
          ])
        ])
      ]));
      document.body.appendChild(container);
      qs('.js-grayout', container).style.display = 'none';
    }
    drawer = { container: container, constructed: constructed };
    var close = qs('.js-close-cart', container);
    if (close) close.addEventListener('click', function (ev) { ev.preventDefault(); closeDrawer(); });
    var grayout = qs('.js-grayout', container);
    if (grayout) grayout.addEventListener('click', function (ev) { if (ev.target === grayout) closeDrawer(); });
    onCart(renderDrawer);
    return drawer;
  }

  function openDrawer() {
    ensureDrawer();
    renderDrawer(cartState);
    var grayout = qs('.js-grayout', drawer.container);
    if (grayout) grayout.style.display = 'block';
  }
  function closeDrawer() {
    if (!drawer) return;
    var grayout = qs('.js-grayout', drawer.container);
    if (!grayout) return;
    if (drawer.constructed) grayout.style.display = 'none';
    else grayout.style.removeProperty('display'); /* restore frozen CSS state */
  }

  function drawerNotify(children) {
    if (!drawer) return;
    var holder = qs('.js-cart-notifications', drawer.container);
    if (!holder) return;
    holder.innerHTML = '';
    if (children) {
      holder.style.display = 'block';
      holder.appendChild(el('div', { style: { padding: '10px 20px', background: '#fdf3d7', borderBottom: '1px solid #e8d9a0', color: '#494f5c' } }, children));
    } else {
      holder.style.removeProperty('display');
    }
  }

  function syncDrawerAuthState(container) {
    /* frozen checkout-section: email state mirrors the source (login hint
       anonymous / account email + Logout when signed in); purchase buttons
       route into the local checkout. */
    var section = qs('.checkout-section', container);
    if (!section || section.dataset.wbWired) {
      if (section) updateDrawerEmail(section);
      return;
    }
    section.dataset.wbWired = '1';
    var purchaseControls = qsa('button, a', section)
      .concat(qsa('.js-payment-button, .payment-buttons button, .payment-buttons a', container));
    purchaseControls.forEach(function (elx) {
      var label = (elx.textContent || '').trim();
      if (/pay with|checkout|purchase/i.test(label) && !/logout|log out/i.test(label)) {
        elx.addEventListener('click', function (ev) {
          ev.preventDefault();
          location.href = '/checkout';
        });
      }
    });
    updateDrawerEmail(section);
  }

  function updateDrawerEmail(section) {
    var holder = qs('.email-holder', section);
    if (!holder) return;
    api('/api/account').then(function (r) {
      if (!r.ok) return;
      var authed = r.data && r.data.authenticated;
      var account = (r.data && r.data.account) || {};
      /* /api/account exposes the normalized address as `email_normalized`;
         there is no `email` key, so reading one silently fell back to the
         display name. The captured drawer shows the address, never a name. */
      var who = account.email_normalized || '';
      if (!authed || !who) { holder.style.removeProperty('display'); return; }
      /* Captured signed-in shape (A/cart-drawer-populated):
           input.email-input.js-email[disabled][value=<address>]
             [placeholder="your@emailaddress.com"][aria-label="Email address"]
           div.email-logout > span.email "Not <address>?" + a.logout
             .js-shopping-cart-logout "Logout"
         replacing the anonymous "Must be logged in to purchase" text node and
         its Login link. */
      var stale = [];
      Array.prototype.forEach.call(holder.childNodes, function (n) {
        if (n.nodeType === 3 && /must be logged in/i.test(n.textContent)) stale.push(n);
      });
      stale.forEach(function (n) { holder.removeChild(n); });
      var input = qs('input.js-email', holder);
      if (!input) {
        input = el('input', {
          type: 'text', 'class': 'email-input js-email', name: 'email',
          placeholder: 'your@emailaddress.com', 'aria-label': 'Email address',
          disabled: 'disabled'
        });
        holder.insertBefore(input, holder.firstChild);
      }
      input.setAttribute('value', who);
      input.value = who;
      var logoutBox = qs('.email-logout', holder);
      if (logoutBox && logoutBox.dataset.wbIdentity !== who) {
        logoutBox.dataset.wbIdentity = who;
        logoutBox.innerHTML = '';
        logoutBox.appendChild(el('span', { 'class': 'email', 'heap-ignore': 'true', text: 'Not ' + who + '?' }));
        var logout = el('a', { href: '#', 'class': 'logout js-shopping-cart-logout', text: 'Logout' });
        logout.addEventListener('click', function (ev) {
          ev.preventDefault();
          api('/api/account/logout', { body: {} }).then(function () { location.reload(); });
        });
        logoutBox.appendChild(logout);
      }
      /* The source drops both newsletter blocks once signed in — the
         `Subscribe to hear about more deals!` checkbox and the Terms of
         Service paragraph. Both carry the source's own js-newsletter-section
         class and the captured signed-in drawer has zero of them. */
      qsa('.js-newsletter-section', section).forEach(function (n) {
        if (n.parentNode) n.parentNode.removeChild(n);
      });
    });
  }

  /* One total row in the captured shape: p.total-heading + p.total, with the
     original/discounted pair when there is a discount to strike through and a
     bare .total-amount otherwise (the Sales Tax row never carries a pair). */
  function drawerTotalRow(heading, currentMinor, originalMinor) {
    var total = el('p', { 'class': 'total' });
    if (originalMinor !== null && originalMinor !== undefined && originalMinor > currentMinor) {
      total.appendChild(el('span', { 'class': 'sr-only', text: 'Original amount' }));
      total.appendChild(el('span', { 'class': 'total-amount is-original', text: money(originalMinor) }));
      total.appendChild(el('span', { 'class': 'sr-only', text: 'Discounted amount' }));
      total.appendChild(el('span', { 'class': 'total-amount is-discounted', text: money(currentMinor) }));
    } else {
      total.appendChild(el('span', { 'class': 'total-amount', text: money(currentMinor) }));
    }
    return el('div', { 'class': 'total-row' }, [
      el('p', { 'class': 'total-heading', text: heading }),
      total
    ]);
  }

  function renderDrawerTotals(container, view) {
    var holder = qs('.js-shopping-cart-total-holder', container);
    if (!holder) return;
    holder.innerHTML = '';
    if (!view.items || !view.items.length) {
      holder.style.display = 'none';
      return;
    }
    holder.style.display = 'block';
    /* Captured totals block: Sub-Total (pair), <tax label> (single), Total
       (pair). The tax label travels with the numbers — `Sales Tax` on the
       store drawer, `HST` on the bundle checkout — so nothing here hardcodes
       one of the two. The Total's struck-through original is the undiscounted
       sub-total, not sub-total + tax (CA$5.48 / CA$1.54 in the capture). */
    var original = view.original_total_minor;
    holder.appendChild(drawerTotalRow('Sub-Total:', view.subtotal_minor || 0, original));
    holder.appendChild(drawerTotalRow((view.tax_label || '') + ':', view.tax_minor || 0, null));
    holder.appendChild(drawerTotalRow('Total:', view.grand_total_minor || 0, original));
    if (!qs('.checkout-section', container)) {
      /* Clone-only fallback: the drawer hb-app.js constructs on pages without
         the frozen #js-cart-container has no captured checkout-section. */
      holder.appendChild(el('div', { 'class': 'js-hb-drawer-checkout-holder', style: { padding: '12px 0 0', textAlign: 'right' } }, [
        el('a', { href: '/checkout', 'class': 'js-hb-drawer-checkout', style: { display: 'inline-block', background: '#c00', color: '#fff', padding: '10px 26px', borderRadius: '3px', textDecoration: 'none', fontWeight: 'bold' }, text: 'Checkout' })
      ]));
    }
  }

  function renderDrawerRewards(container, view) {
    var credit = view.rewards_credit_minor || 0;
    var holder = qs('.js-rewards-total-holder', container);
    if (holder) {
      holder.innerHTML = '';
      /* Captured: div.humble-rewards-breakdown > div.rewards-line-item with
         .line-item-title `Wallet Credit Earned` and .line-item-amount. The
         frozen empty holder carries `inactive` (display:none in the source
         stylesheet); the populated capture does not. */
      if (credit > 0) {
        holder.classList.remove('inactive');
        holder.appendChild(el('div', { 'class': 'humble-rewards-breakdown' }, [
          el('div', { 'class': 'rewards-line-item' }, [
            el('div', { 'class': 'line-item-title', text: view.rewards_label || 'Wallet Credit Earned' }),
            el('div', { 'class': 'line-item-amount', text: money(credit) })
          ])
        ]));
      } else {
        holder.classList.add('inactive');
      }
    }
    /* The `Manage Your Rewards` section loses is-hidden in the same capture. */
    var section = qs('.js-rewards-section', container);
    if (section) {
      if (credit > 0) section.classList.remove('is-hidden');
      else section.classList.add('is-hidden');
    }
  }

  function renderDrawerPromo(container, view) {
    var promo = qs('.js-shopping-cart-monthly-promo', container);
    if (!promo) return;
    promo.innerHTML = '';
    var coupon = view.choice_coupon_minor || 0;
    if (coupon <= 0) return;
    /* Captured membership offer, verbatim apart from the amount, which comes
       from the server so the copy and the number cannot drift apart. */
    promo.appendChild(el('div', { 'class': 'monthly-promo-wrapper humble-choice' }, [
      el('h2', { text: 'You can save on Humble Choice!' }),
      el('p', {
        text: "You'll get a coupon for " + money(coupon) + ' off your first month'
          + ' when you check out. Save even more by adding items! Humble Choice'
          + ' members get a new mix of PC games to own every month, access to the'
          + ' Humble Games Collection, Store discounts, and more.'
      }),
      el('p', {
        'class': 'small-link',
        text: 'New members only. Must log in to Humble Bundle account before'
          + ' checkout. After checkout, coupon will be automatically added to'
          + ' account. If you already have a coupon of higher value, this'
          + ' purchase will not grant another.'
      })
    ]));
  }

  function renderDrawer(view) {
    if (!drawer) return;
    var container = drawer.container;
    syncDrawerAuthState(container);
    var header = qs('h1.js-header', container);
    if (header) {
      header.innerHTML = '';
      header.appendChild(el('i', { 'class': 'hb hb-shopping-cart-light' }));
      header.appendChild(document.createTextNode(' Cart (' + (view.count || 0) + ' items)'));
    }
    var rows = qs('.js-shopping-cart-row-holder', container);
    if (rows) {
      rows.innerHTML = '';
      if (!view.items || !view.items.length) {
        rows.appendChild(el('div', { 'class': 'shopping-cart-empty' }, [el('p', { text: 'Your cart is empty' })]));
      } else {
        /* Captured nesting: row-holder > .cart-group > .js-shopping-cart-row+ */
        var group = el('div', { 'class': 'cart-group' });
        view.items.forEach(function (item) { group.appendChild(drawerRow(item)); });
        rows.appendChild(group);
      }
    }
    renderDrawerTotals(container, view);
    renderDrawerRewards(container, view);
    renderDrawerPromo(container, view);
  }

  /* The captured row's per-platform redemption block:
       ul.platforms.cart-platforms > li
         > i.hb.hb-<drm>[aria-label="<DRM>"][tabindex="0"]
         + aside.platform-info > p (i.hb.hb-<os> + em "Redeem for <OS>")*    */
  function drawerPlatforms(item) {
    var drms = item.drm || [];
    var oses = orderedPlatforms(item.platforms || []);
    if (!drms.length && !oses.length) return null;
    var list = el('ul', { 'class': 'platforms cart-platforms' });
    (drms.length ? drms : ['']).forEach(function (d) {
      var info = el('aside', { 'class': 'platform-info' });
      oses.forEach(function (os) {
        info.appendChild(el('p', {}, [
          el('i', { 'class': 'hb ' + osIcon(os) }),
          el('em', { text: 'Redeem for ' + osLabel(os) })
        ]));
      });
      var kids = [];
      if (d) kids.push(el('i', { 'class': 'hb ' + drmIcon(d), title: '', tabindex: '0', 'aria-label': drmLabel(d) }));
      kids.push(info);
      list.appendChild(el('li', {}, kids));
    });
    return list;
  }

  /* Captured price paragraph: an sr-only `Original amount` + <s>full</s> and an
     sr-only `Discounted amount` + span.current-price.discounted. An
     undiscounted store row was not captured, so it degrades to the bare
     .current-price span rather than striking a price through itself. */
  function drawerPrice(currentMinor, originalMinor) {
    var price = el('p', { 'class': 'js-cart-item-price cart-item-price' });
    if (originalMinor > currentMinor) {
      price.appendChild(el('span', { 'class': 'sr-only', text: 'Original amount' }));
      price.appendChild(el('s', { text: money(originalMinor) }));
      price.appendChild(el('span', { 'class': 'sr-only', text: 'Discounted amount' }));
      price.appendChild(el('span', { 'class': 'current-price discounted', text: money(currentMinor) }));
    } else {
      price.appendChild(el('span', { 'class': 'current-price', text: money(currentMinor) }));
    }
    return price;
  }

  function drawerAmountEditor(item) {
    /* Bundle lines are a clone-side extension of the cart (the source sends a
       bundle straight to /checkout); the pay-what-you-want amount is edited
       here, which is also where T11's "change quantity" clause lands, since
       the source cart has no quantity concept at all. */
    var amountInput = el('input', {
      type: 'number', step: '0.01', min: dollarsValue(item.floor_minor || 0),
      value: (item.amount_minor / 100).toFixed(2),
      'class': 'js-hb-cart-amount', 'aria-label': 'Bundle amount',
      style: { width: '90px', padding: '4px' }
    });
    amountInput.addEventListener('change', function () {
      var minor = Math.round(parseFloat(amountInput.value || '0') * 100);
      api('/api/cart/update', { body: { item_id: item.item_id, amount_minor: minor } }).then(function (r) {
        if (r.ok) { setCart(r.data); drawerNotify(null); }
        else drawerNotify([document.createTextNode(r.data.message || 'Could not update the amount.')]);
      });
    });
    return el('p', { 'class': 'js-cart-item-price cart-item-price' }, [
      document.createTextNode('CA$ '), amountInput
    ]);
  }

  function drawerRow(item) {
    /* Captured row (A/cart-drawer-populated/dom.html):
         div.js-shopping-cart-row.shopping-cart-row
           div.row-contents
             a.js-remove-from-cart.remove-from-cart[aria-label="Remove from cart"]
               > i.hb.hb-times-circle
             div.cart-item-information-wrapper
               > a.cart-item-name + ul.platforms.cart-platforms
             p.js-cart-item-price.cart-item-price
           div.row-contents > div.product-error-holder
             .js-product-error-holder-<machine_name>
       There is no quantity control and no quantity text: the source cart has
       neither (see scope/implement-notes.md). */
    var isBundle = item.kind === 'bundle';
    var href = (isBundle ? '/games/' : '/store/') + item.slug;
    var name = item.name || item.slug;

    var remove = el('a', {
      'class': 'js-remove-from-cart remove-from-cart', href: '#',
      'data-model-id': String(item.item_id), 'aria-label': 'Remove from cart'
    }, [el('i', { 'class': 'hb hb-times-circle' })]);
    remove.addEventListener('click', function (ev) {
      ev.preventDefault();
      api('/api/cart/remove', { body: { item_id: item.item_id } }).then(function (r) {
        if (!r.ok) { drawerNotify([document.createTextNode(r.data.message || 'Could not remove the item.')]); return; }
        lastRemoveSnapshot = r.data.snapshot || null;
        setCart(r.data.cart || {});
        /* Clone-invented restore affordance: the source's .js-cart-notifications
           is empty in every capture, but T11 asks for a restore and the ✕ is
           one-way. Disclosed in scope/implement-notes.md. */
        var undo = el('button', { type: 'button', 'class': 'js-hb-cart-undo', style: { marginLeft: '8px', background: 'none', border: 'none', color: '#06c', cursor: 'pointer', textDecoration: 'underline', fontWeight: 'bold', padding: '0' }, text: 'Undo' });
        undo.addEventListener('click', function () {
          if (!lastRemoveSnapshot) return;
          api('/api/cart/restore', { body: { snapshot: lastRemoveSnapshot } }).then(function (r2) {
            if (r2.ok) { lastRemoveSnapshot = null; setCart(r2.data); drawerNotify(null); }
            else drawerNotify([document.createTextNode(r2.data.message || 'Could not restore the item.')]);
          });
        });
        drawerNotify([document.createTextNode('Removed ' + name + ' — '), undo]);
      });
    });

    var info = el('div', { 'class': 'cart-item-information-wrapper' }, [
      el('a', { href: href, 'class': 'cart-item-name', title: name, text: name })
    ]);
    var platforms = drawerPlatforms(item);
    if (platforms) info.appendChild(platforms);
    else if (isBundle) {
      info.appendChild(el('ul', { 'class': 'platforms cart-platforms' }, [
        el('li', {}, [el('aside', { 'class': 'platform-info' }, [
          el('p', {}, [el('em', { text: 'Pay what you want · ' + item.unlocked_count + ' of ' + item.total_count + ' items' })])
        ])])
      ]));
    }

    var errorClass = 'product-error-holder';
    if (item.machine_name) errorClass += ' js-product-error-holder-' + item.machine_name;

    return el('div', { 'class': 'js-shopping-cart-row shopping-cart-row' }, [
      el('div', { 'class': 'row-contents' }, [
        remove,
        info,
        isBundle ? drawerAmountEditor(item) : drawerPrice(item.line_total_minor, item.line_full_total_minor)
      ]),
      el('div', { 'class': 'row-contents' }, [el('div', { 'class': errorClass })])
    ]);
  }

  /* ---------- header module (all pages) ---------- */

  function initHeader() {
    /* Anonymous auth links are frozen as href="javascript:void(0)"; the source
       resolves them to /login?goto=<path> and /signup?goto=<path>, carrying the
       URL-encoded pathname of the page the visitor left (observed anonymously
       on the source: "/" -> /signup?goto=%2F, and
       /games/yes-chef-cooking-bundle -> /login?goto=%2Fgames%2Fyes-chef-...). */
    function authHref(base) {
      return base + '?goto=' + encodeURIComponent(location.pathname);
    }
    qsa('a.js-account-login').forEach(function (a) {
      a.addEventListener('click', function (ev) { ev.preventDefault(); location.href = authHref('/login'); });
    });
    qsa('a.js-create-account').forEach(function (a) {
      a.addEventListener('click', function (ev) { ev.preventDefault(); location.href = authHref('/signup'); });
    });

    getAccount().then(function (state) {
      if (state.authenticated && state.account) renderAccountMenu(state.account);
    });

    initHeaderSearch();
    initHeaderCart();
  }

  /* Signed-in account menu, reproduced node-for-node from the authenticated
     capture (every state under source-auth-scratch/walk-671): the source
     replaces the Sign Up / Log In pair with a user-circle icon plus a caret —
     it never prints the display name in the navbar. Class list, attribute set,
     item order, labels and hrefs are the captured ones. The source hides the
     panel with a `hidden` class whose rule ships in stylesheet code we do not
     serve, so this layer keeps the class for markup fidelity and drives the
     actual visibility itself. */
  function renderAccountMenu(account) {
    var loginLink = qs('a.js-account-login');
    if (!loginLink) return; /* simple navbar (login/signup) has no account area */
    var signupLink = qs('a.js-create-account');

    var dropdown = el('div', {
      'class': 'navbar-item-dropdown-container user-dropdown user-item-dropdown-container' +
        ' nav-dropdown click-to-open-dropdown hidden js-user-dropdown-2021',
      style: { display: 'none', position: 'absolute', right: '0', top: '100%', background: '#272930', minWidth: '180px', zIndex: '1000', boxShadow: '0 2px 8px rgba(0,0,0,0.35)' }
    }, [
      el('div', { 'class': 'js-disable-body-scroll navbar-item-dropdown-items user-items nav-dropdown-items' }, [
        el('a', { 'class': 'navbar-item-dropdown-item', href: '/home/purchases', text: 'Purchases' }),
        el('a', { 'class': 'navbar-item-dropdown-item', href: '/home/library', text: 'Library' }),
        el('a', { 'class': 'navbar-item-dropdown-item', href: '/home/keys', text: 'Keys & Entitlements' }),
        el('a', { 'class': 'navbar-item-dropdown-item', href: '/home/coupons', text: 'Coupons' }),
        el('a', { 'class': 'navbar-item-dropdown-item', href: '/store/wishlist', text: 'Wish List' }),
        el('a', { 'class': 'navbar-item-dropdown-item', href: '/user/wallet', text: 'Wallet' }),
        el('a', { 'class': 'navbar-item-dropdown-item', href: '/user/settings', text: 'Settings' }),
        el('a', { 'class': 'navbar-item-dropdown-item js-navbar-logout', href: '', text: 'Logout' })
      ])
    ]);
    var button = el('div', {
      'class': 'navbar-item navbar-item-dropdown user-navbar-item logged-in button-title' +
        ' no-style-button non-link-item js-user-dropdown-container-2021',
      'aria-label': 'Account Access', 'aria-live': 'polite', role: 'button', tabindex: '0',
      'aria-haspopup': 'true', 'aria-expanded': 'false', style: { cursor: 'pointer' }
    }, [
      el('span', { 'class': 'navbar-icon-text-wrapper' }, [
        el('i', { 'class': 'navbar-item-icon hb hb-user-circle-o', 'aria-hidden': 'true' }),
        el('i', { 'class': 'hb hb-caret-down desktop secondary-caret user-item-dropdown-caret', 'aria-hidden': 'true' }),
        el('span', { 'class': 'navbar-item-text mobile', text: 'Account' })
      ])
    ]);
    var wrap = el('div', {
      'class': 'user-dropdown-container nav-dropdown-container js-hb-account-menu',
      style: { position: 'relative' }
    }, [button, dropdown]);
    loginLink.parentNode.insertBefore(wrap, loginLink);
    /* the source's logged-in navbar carries no Sign Up / Log In pair at all */
    if (signupLink && signupLink.parentNode) signupLink.parentNode.removeChild(signupLink);
    loginLink.parentNode.removeChild(loginLink);

    function toggle(open) {
      var isOpen = !dropdown.classList.contains('hidden');
      var next = open === undefined ? !isOpen : open;
      dropdown.classList[next ? 'remove' : 'add']('hidden');
      dropdown.style.display = next ? 'block' : 'none';
      button.setAttribute('aria-expanded', next ? 'true' : 'false');
    }
    button.addEventListener('click', function () { toggle(); });
    document.addEventListener('click', function (ev) { if (!wrap.contains(ev.target)) toggle(false); });
    qs('.js-navbar-logout', dropdown).addEventListener('click', function (ev) {
      ev.preventDefault();
      api('/api/account/logout', { method: 'POST', body: {} }).then(function () { location.reload(); });
    });

    /* the source serves the wishlist under /store/wishlist (handoff-confirmed) */
    qsa('a.js-wishlist').forEach(function (a) { a.setAttribute('href', '/store/wishlist'); });
  }

  function initHeaderSearch() {
    var box = qs('.js-site-search');
    var input = qs('input.js-search');
    if (!box || !input) return;
    var holder = qs('.js-search-holder', box);
    var results = qs('.js-results', box);
    var message = qs('.js-message', box);
    var link = qs('.js-search-link', box);

    function close() {
      if (holder) holder.style.removeProperty('display');
      if (results) results.innerHTML = '';
      if (message) message.textContent = '';
    }
    function open() { if (holder) holder.style.display = 'block'; }

    function renderRows(rows, q) {
      /* row markup mirrors the captured .product-search-result structure
         (frozen suggest oracle: interactive/home-search-suggest) */
      if (!results) return;
      results.innerHTML = '';
      rows.forEach(function (row) {
        var info = el('div', { 'class': 'product-information' }, [
          el('span', { 'class': 'product-title', text: row.name })
        ]);
        if (row.description) {
          info.appendChild(el('div', { 'class': 'product-description', text: row.description }));
        } else if (row.platform_icons && row.platform_icons.length) {
          var icons = el('div', { 'class': 'product-platform-delivery' });
          row.platform_icons.forEach(function (token, i) {
            icons.appendChild(el('i', { 'class': 'hb hb-' + token, 'aria-hidden': 'true' }));
            if (i === 0 && row.delivery_separator) {
              icons.appendChild(el('span', { 'class': 'separator', text: '|' }));
            }
          });
          info.appendChild(icons);
        }
        var action = el('div', { 'class': 'product-action-wrapper' }, []);
        if (row.discount_pct) {
          action.appendChild(el('span', { 'class': 'product-discount-amount', text: '-' + row.discount_pct + '%' }));
        }
        action.appendChild(el('span', {
          'class': 'product-action-text js-action-text ' + (row.discount_pct ? ' on-sale ' : ''),
          text: row.price_display || row.action_text || 'View'
        }));
        var kids = [];
        if (row.img && (row.img.local || typeof row.img === 'string')) {
          kids.push(el('img', {
            'class': 'product-image' + (row.kind === 'bundle' ? ' bundle-product' : ' '),
            src: row.img.local || row.img, alt: row.name
          }));
        }
        kids.push(info);
        kids.push(action);
        var wrap = el('div', { 'class': 'product-search-result' }, [
          el('a', { href: row.href, 'class': 'product-details js-product-details', 'aria-label': row.name + ', View' }, kids)
        ]);
        results.appendChild(wrap);
      });
      if (message) message.textContent = rows.length ? '' : 'No results found for “' + q + '”';
      if (link) {
        link.textContent = 'See All Results';
        link.setAttribute('href', '/store/search?search=' + encodeURIComponent(q));
      }
      open();
    }

    var suggest = debounce(function () {
      var q = input.value.trim();
      if (!q) { close(); return; }
      api('/api/suggest?q=' + encodeURIComponent(q)).then(function (r) {
        if (!r.ok) return;
        if (input.value.trim() !== q) return; /* stale response */
        renderRows(r.data.results || [], q);
      });
    }, 150);

    input.addEventListener('input', suggest);
    input.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        var q = input.value.trim();
        if (q) location.href = '/store/search?search=' + encodeURIComponent(q);
      } else if (ev.key === 'Escape') {
        close();
        input.blur();
      }
    });
    var clearBtn = qs('.js-clear-search-button', box);
    if (clearBtn) clearBtn.addEventListener('click', function (ev) { ev.preventDefault(); input.value = ''; close(); input.focus(); });
    document.addEventListener('click', function (ev) { if (!box.contains(ev.target)) close(); });
  }

  function initHeaderCart() {
    refreshCart();

    /* store sub-nav cart button (present on /store* pages) */
    qsa('button.js-cart').forEach(function (btn) {
      btn.addEventListener('click', function (ev) { ev.preventDefault(); openDrawer(); });
      onCart(function (view) {
        var count = qs('.js-item-count', btn);
        if (count) count.textContent = String(view.count || 0);
        btn.setAttribute('aria-label', 'You have ' + (view.count || 0) + ' items in your shopping cart. View your cart');
      });
    });

    /* REFINE-AFTER-HANDOFF: header cart icon is absent from the anonymous
       frozen header; injected only when the cart is non-empty. */
    var navContent = qs('.navbar-content');
    if (navContent && !qs('button.js-cart') && qs('a.js-account-login')) {
      var badge = el('span', { 'class': 'js-hb-cart-count', style: { marginLeft: '4px' }, text: '0' });
      var icon = el('a', { 'class': 'navbar-item button-title js-hb-cart-icon', href: '#', style: { display: 'none', cursor: 'pointer' } }, [
        el('i', { 'class': 'hb hb-shopping-cart-solid' }), badge
      ]);
      icon.addEventListener('click', function (ev) { ev.preventDefault(); openDrawer(); });
      var anchor = qs('a.js-create-account', navContent);
      if (anchor) navContent.insertBefore(icon, anchor); else navContent.appendChild(icon);
      onCart(function (view) {
        badge.textContent = String(view.count || 0);
        icon.style.display = (view.count || 0) > 0 ? '' : 'none';
      });
    }
  }

  /* ---------- countdown ---------- */

  function startCountdown(root, endAtIso, immediate) {
    var end = new Date(endAtIso);
    if (isNaN(end.getTime())) return;
    var days = qs('.js-days', root), hours = qs('.js-hours', root), minutes = qs('.js-minutes', root), seconds = qs('.js-seconds', root);
    if (!days && !hours && !minutes) return;
    function tick() {
      var rem = Math.max(0, end.getTime() - Date.now());
      if (days) days.textContent = String(Math.floor(rem / 86400000));
      if (hours) hours.textContent = String(Math.floor((rem % 86400000) / 3600000));
      if (minutes) minutes.textContent = String(Math.floor((rem % 3600000) / 60000));
      if (seconds) seconds.textContent = String(Math.floor((rem % 60000) / 1000));
    }
    if (immediate) tick(); /* frozen pages wait for tick 1 to keep load pixels */
    setInterval(tick, 1000);
  }

  /* ---------- bundle page (/games/{slug}) ---------- */

  function bundlePage() {
    var slug = path.split('/')[2];
    var pwyw = qs('.js-pwyw-view');
    if (!pwyw) return; /* branded 404 body */
    api('/api/bundle/' + encodeURIComponent(slug)).then(function (r) {
      if (!r.ok) return;
      var bundle = r.data;
      var frozen = !!FROZEN_BUNDLES[slug];
      if (!frozen) hydrateBundle(bundle);
      wireBundle(bundle, frozen);
    });
  }

  function partyLabel(entry) {
    if (entry['class'] === 'humblebundle') return 'Humble';
    return String(entry.name || '').trim();
  }
  function splitFraction(entry, mode) {
    return mode === 'extra-charity' ? (entry.extra_charity_split || 0) : (entry.sibling_split || 0);
  }
  function splitRowsList(bundle, amountMinor, mode) {
    var ul = el('ul', { 'class': 'preset-splits-view' });
    (bundle.splits || []).forEach(function (entry) {
      ul.appendChild(el('li', { 'class': 'preset-split-view', text: moneyTrim(Math.round(amountMinor * splitFraction(entry, mode))) + ' to ' + partyLabel(entry) }));
    });
    return ul;
  }

  /* .js-item-count-text nodes. The captured line wraps its middle clause in
     <strong>: `You will get 7 items. <strong>You're missing out</strong> on
     Tavern Manager Simulator and 8 more! Pay at least CA$22.19 to get all
     items.` — so the message is assembled as nodes, not a flat string.
     Below the floor the trailing clause switches to the source's own
     minimum-price sentence: the floor is the minimum purchase price, not the
     price that unlocks every item (that is next_threshold_minor). */
  function unlockMessageNodes(p) {
    if (p.missing_count > 0) {
      var tail = p.valid
        ? ' more! Pay at least ' + money(p.next_threshold_minor) + ' to get all items.'
        : ' more! The minimum price for this bundle is ' + money(p.floor_minor) + '.';
      return [
        document.createTextNode('You will get ' + p.unlocked_count + ' items. '),
        el('strong', { text: "You're missing out" }),
        document.createTextNode(' on ' + p.missing_first_name + ' and ' + (p.missing_count - 1) + tail)
      ];
    }
    return [document.createTextNode('You will get all ' + p.total_count +
      ' items. Thank you for giving extra and helping the Humble community!')];
  }

  function tierByThreshold(bundle) {
    return (bundle.tiers || []).slice().sort(function (a, b) { return a.threshold_minor - b.threshold_minor; });
  }
  function itemTierIndex(bundle) {
    var map = {};
    (bundle.tiers || []).forEach(function (tier) {
      (tier.items || []).forEach(function (item) {
        map[item.human_name] = { tier_id: tier.tier_id, threshold_minor: tier.threshold_minor };
      });
    });
    return map;
  }

  function wireBundle(bundle, frozen) {
    var form = qs('form.js-go-to-checkout');
    if (!form) return;
    var presets = qsa('input.js-preset-price', form);
    var custom = qs('input.js-custom-amount', form);
    var countText = qs('.js-item-count-text', form);
    var infotip = qs('.js-error-and-infotip', form);
    var checkoutBtn = qs('.js-checkout-button', form);
    var itemsByName = itemTierIndex(bundle);
    var lastPreview = null;

    startCountdown(qs('.countdown-container') || document, bundle.end_at, !frozen);

    function currentAmountMinor() {
      if (custom && custom.value !== '') {
        var v = parseFloat(custom.value);
        if (!isNaN(v)) return Math.round(v * 100);
      }
      for (var i = 0; i < presets.length; i++) {
        if (presets[i].checked) return Math.round(parseFloat(presets[i].value) * 100);
      }
      return bundle.suggested_price_minor || bundle.floor_minor || 0;
    }

    function applyLocks(preview) {
      var unlocked = {};
      (preview.unlocked_tier_ids || []).forEach(function (id) { unlocked[id] = 1; });
      qsa('.js-tier-collection .tier-item-view').forEach(function (tile) {
        var titleEl = qs('.item-title', tile);
        if (!titleEl) return;
        var meta = itemsByName[titleEl.textContent.trim()];
        if (!meta) return;
        var locked = !unlocked[meta.tier_id];
        var badge = qs('.js-hb-lock-badge', tile);
        if (locked) {
          tile.classList.add('hb-locked');
          tile.style.opacity = '0.45';
          if (!badge) {
            badge = el('span', { 'class': 'js-hb-lock-badge fine-print', style: { display: 'block', marginTop: '4px', fontWeight: 'bold' } }, [
              el('i', { 'class': 'hb hb-lock' }),
              document.createTextNode(' Pay at least ' + money(meta.threshold_minor) + ' to get this item')
            ]);
            tile.appendChild(badge);
          }
        } else {
          tile.classList.remove('hb-locked');
          tile.style.removeProperty('opacity');
          if (badge) badge.parentNode.removeChild(badge);
        }
      });
    }

    function applySplitAmounts(amountMinor) {
      var defaultHolder = qs('.js-default-preset-splits');
      if (defaultHolder) { defaultHolder.innerHTML = ''; defaultHolder.appendChild(splitRowsList(bundle, amountMinor, 'default')); }
      var extraHolder = qs('.js-extra-charity-preset-splits');
      if (extraHolder) { extraHolder.innerHTML = ''; extraHolder.appendChild(splitRowsList(bundle, amountMinor, 'extra-charity')); }
      /* custom sliders: recompute the displayed amounts by matching each
         .split-name against the bundle's split parties and subsplits */
      var byName = {};
      (bundle.splits || []).forEach(function (entry) {
        var amount = Math.round(amountMinor * splitFraction(entry, 'default'));
        byName[partyLabel(entry)] = amount;
        if (entry.name) byName[String(entry.name).trim()] = amount;
        (entry.subsplit || []).forEach(function (sub) {
          byName[String(sub.name || '').trim()] = Math.round(amount * (sub.sibling_split || 0));
        });
      });
      qsa('.js-split-sliders .split-view').forEach(function (row) {
        var nameEl = qs('.split-name', row);
        var amountEl = qs('.js-amount-container', row);
        if (!nameEl || !amountEl) return;
        var minor = byName[nameEl.textContent.trim()];
        if (minor !== undefined) amountEl.textContent = money(minor);
      });
    }

    var updateSeq = 0;
    var update = debounce(function () {
      var amountMinor = currentAmountMinor();
      var seq = ++updateSeq;
      api('/api/bundle/' + encodeURIComponent(bundle.slug) + '/preview?amount_minor=' + amountMinor).then(function (r) {
        if (!r.ok) return;
        if (seq !== updateSeq) return; /* a newer request superseded this one */
        var p = r.data;
        lastPreview = p;
        if (countText) {
          countText.innerHTML = '';
          unlockMessageNodes(p).forEach(function (node) { countText.appendChild(node); });
        }
        if (checkoutBtn) checkoutBtn.disabled = !p.valid;
        if (infotip) infotip.textContent = p.valid ? 'Suggested Price' : ('The minimum price for this bundle is ' + money(p.floor_minor) + '.');
        applyLocks(p);
        applySplitAmounts(amountMinor);
      });
    }, 250);

    presets.forEach(function (radio) {
      radio.addEventListener('change', function () {
        if (custom) custom.value = '';
        update();
      });
    });
    if (custom) custom.addEventListener('input', function () {
      presets.forEach(function (radio) { radio.checked = false; });
      update();
    });

    /* Adjust Donation toggle + split allocation radios */
    var splitsToggle = qs('.js-splits-toggle');
    var splitsInfo = qs('.js-splits-info');
    if (splitsToggle && splitsInfo) {
      splitsToggle.addEventListener('click', function (ev) {
        ev.preventDefault();
        var open = getComputedStyle(splitsInfo).display !== 'none';
        splitsInfo.style.display = open ? 'none' : 'block';
      });
    }
    function showSplitMode(mode) {
      var holders = {
        'default': qs('.js-default-preset-splits'),
        'extra-charity': qs('.js-extra-charity-preset-splits'),
        'custom': qs('.js-split-sliders'),
      };
      Object.keys(holders).forEach(function (key) {
        var holder = holders[key];
        if (!holder) return;
        var wrap = holder.closest('li, .split-option-view') || holder;
        wrap.style.display = (key === mode) ? 'block' : 'none';
      });
    }
    qsa('input.js-split-allocation').forEach(function (radio) {
      radio.addEventListener('change', function () {
        if (!radio.checked) return;
        var mode = radio.value === 'custom' ? 'custom'
          : (radio.value === 'extra-charity' ? 'extra-charity' : 'default');
        try { sessionStorage.setItem('hb-split-mode', mode); } catch (e) { /* storage unavailable */ }
        showSplitMode(mode);
      });
    });

    /* bundle Checkout mirrors the source's direct-to-checkout flow.
       REFINE-AFTER-HANDOFF: checkout interior pending handoff tr-001. */
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var amountMinor = currentAmountMinor();
      if (lastPreview && !lastPreview.valid) return;
      cartAdd('bundle', bundle.slug, amountMinor).then(function (r) {
        if (r.ok) location.href = '/checkout';
        else if (infotip) infotip.textContent = r.data.message || 'Could not start checkout.';
      });
    });

    /* tier filter chips re-target the grid header (selection only) */
    qsa('.js-tier-filter').forEach(function (chip) {
      chip.addEventListener('click', function (ev) {
        ev.preventDefault();
        qsa('.js-tier-filter').forEach(function (other) { other.classList.remove('selected'); });
        chip.classList.add('selected');
        var tier = null;
        (bundle.tiers || []).forEach(function (t) { if (t.tier_id === chip.getAttribute('data-tier')) tier = t; });
        var header = qs('.js-tier-header');
        if (tier && header) header.textContent = 'Pay at least ' + money(tier.threshold_minor) + ' for these ' + tier.item_count + ' items';
      });
    });
  }

  function hydrateBundle(bundle) {
    document.title = bundle.name + ' (pay what you want and help charity)';

    /* A bundle known only from a listing tile has a name, an end date,
     * highlight lines and a logo, and no tiers, prices or contents — its own
     * page was never captured. The frozen template ships a captured bundle's
     * purchase machinery for the hydrator to overwrite, so leaving it in place
     * would show this bundle's name above another bundle's games and asking
     * price. Removing those sections is the truthful reading: this is what we
     * hold about this bundle, and nothing else. */
    if (bundle.listing_only) {
      var heading = qs('.js-basic-info-view h2.heading-medium');
      if (heading) heading.textContent = bundle.name;
      qsa('.bundle-title img.bundle-logo').forEach(function (img) {
        if (bundle.tile_image) { img.src = mediaUrl(bundle.tile_image); img.alt = bundle.name; }
      });
      if (bundle.highlights && bundle.highlights.length) {
        qsa('.marketing-blurb').forEach(function (node) {
          node.textContent = bundle.highlights.join(' • ');
        });
      }
      ['.js-desktop-tiers-view', '.js-mobile-tiers-view', '.js-pwyw-view',
       '.js-splits-view', '.js-leaderboard-view', '.js-video-view',
       '.js-details-view', '.js-charity-info-view'].forEach(function (sel) {
        qsa(sel).forEach(function (node) { node.remove(); });
      });
      return;
    }

    api('/api/bundles').then(function (r) {
      if (!r.ok) return;
      var entry = null;
      Object.keys(r.data || {}).forEach(function (cat) {
        (r.data[cat] || []).forEach(function (b) { if (b.slug === bundle.slug) entry = b; });
      });
      qsa('.bundle-title img.bundle-logo').forEach(function (img) {
        var url = entry ? mediaUrl(entry.tile_image) : '';
        img.alt = bundle.name;
        if (url) img.src = url;
        else {
          var text = el('span', { 'class': 'bundle-logo', style: { fontSize: '28px', fontWeight: 'bold' }, text: bundle.name });
          img.parentNode.replaceChild(text, img);
        }
      });
      if (entry && entry.highlights) {
        qsa('.marketing-blurb').forEach(function (p) { p.textContent = entry.highlights.join(' • '); });
      }
    });

    var basicInfo = qs('.js-basic-info-view h2.heading-medium');
    if (basicInfo) basicInfo.textContent = bundle.name;

    var valueLine = qs('.js-pwyw-view h2.heading-medium');
    if (valueLine) valueLine.textContent = money(bundle.msrp_minor) + ' Value • Pay What You Want';

    /* preset price radios */
    var sorted = tierByThreshold(bundle);
    var presetHolder = qs('.js-pwyw-view .preset-prices');
    if (presetHolder) {
      presetHolder.innerHTML = '';
      var checkedMinor = bundle.suggested_price_minor || (bundle.preset_prices_minor || [])[0];
      (bundle.preset_prices_minor || []).forEach(function (minor) {
        var qualifying = 'initial';
        sorted.forEach(function (t) { if (minor >= t.threshold_minor) qualifying = t.tier_id; });
        var value = dollarsValue(minor);
        var id = 'preset-' + value;
        presetHolder.appendChild(el('input', {
          type: 'radio', name: 'amount', id: id, 'class': 'is-visually-hidden js-preset-price',
          value: value, 'data-qualifying-tier': qualifying, checked: minor === checkedMinor ? '' : null
        }));
        presetHolder.appendChild(el('label', { 'class': 'preset-price', 'for': id, text: moneyTrim(minor) }));
      });
    }
    var custom = qs('input.js-custom-amount');
    if (custom) custom.min = (bundle.floor_minor / 100).toFixed(2);

    /* quick facts: floor headline + sold count */
    qsa('.quick-facts .fact .fine-print').forEach(function (span) {
      var text = span.textContent.trim();
      if (/^Pay CA\$/.test(text)) span.textContent = 'Pay ' + money(bundle.floor_minor) + ' Or More';
      else if (/ Sold$/.test(text)) span.textContent = commas(bundle.sold_count || 0) + ' Sold';
    });

    var raised = qs('.charity-amount-raised');
    if (raised) {
      raised.innerHTML = '';
      raised.appendChild(el('i', { 'class': 'hb hb-heart' }));
      raised.appendChild(document.createTextNode(' This bundle has raised ' + moneyTrim(bundle.charity_raised_minor || 0) + ' for charity!'));
    }

    /* tier filter chips + header */
    var filters = qs('.tier-filters');
    if (filters) {
      qsa('.js-tier-filter', filters).forEach(function (chip) { chip.parentNode.removeChild(chip); });
      var byThresholdDesc = sorted.slice().reverse();
      byThresholdDesc.forEach(function (tier, i) {
        filters.appendChild(el('a', {
          href: '#', 'class': 'js-tier-filter chip' + (i === 0 ? ' selected' : ''), 'data-tier': tier.tier_id,
          text: (i === 0 ? 'Entire ' + tier.item_count + ' Item Bundle' : tier.item_count + ' Item Bundle')
        }));
      });
    }
    var top = sorted[sorted.length - 1];
    var tierHeader = qs('.js-tier-header');
    if (tierHeader && top) tierHeader.textContent = 'Pay at least ' + money(top.threshold_minor) + ' for these ' + top.item_count + ' items';

    /* item grid (replaces the frozen tiles AND the item-detail carousel) */
    var collection = qs('.js-tier-collection');
    if (collection) {
      collection.innerHTML = '';
      var grid = el('div', { 'class': 'desktop-tier-collection-view' });
      var order = 0;
      var seenItems = {};
      (bundle.tier_order || []).forEach(function (tierId) {
        (bundle.tiers || []).forEach(function (tier) {
          if (tier.tier_id !== tierId) return;
          (tier.items || []).forEach(function (item) {
            /* tiers nest cumulatively; render each unique item once */
            var itemKey = item.machine_name || item.human_name;
            if (seenItems[itemKey]) return;
            seenItems[itemKey] = 1;
            var img = firstMedia(item.media || {}, ['featured_image', 'standard_carousel_image', 'large_capsule']);
            var flavor = el('span', { 'class': 'item-flavor-text fine-print' });
            if (item.steam_positive_pct) {
              flavor.appendChild(el('span', { text: item.steam_positive_pct + '% Positive on Steam' }));
              flavor.appendChild(el('br'));
              flavor.appendChild(el('br'));
            }
            flavor.appendChild(document.createTextNode(item.one_liner || ''));
            grid.appendChild(el('div', { 'class': 'tier-item-view', style: { order: String(order++) } }, [
              el('a', { href: '#', 'class': 'js-item-details item-details' }, [
                el('div', { 'class': 'img-container' }, [
                  img ? el('img', { alt: item.human_name, 'class': 'item-image', width: '616', height: '353', src: img }) : null
                ]),
                el('span', { 'class': 'item-title', text: item.human_name })
              ]),
              flavor
            ]));
          });
        });
      });
      collection.appendChild(grid);
    }

    /* charity panel */
    var charityName = (bundle.charity && bundle.charity.name) || '';
    var charityNames = qs('.js-charity-names');
    if (charityNames && charityName) {
      charityNames.innerHTML = '';
      charityNames.appendChild(document.createTextNode('This bundle supports '));
      charityNames.appendChild(el('a', { href: '#', 'class': 'js-show-charity-modal text-button', text: charityName }));
      charityNames.appendChild(document.createTextNode('.'));
    }
    qsa('.charity-item-view').forEach(function (item) {
      var name = qs('strong.name', item);
      if (name && charityName) name.textContent = charityName;
      var logo = qs('.logo-container', item);
      if (logo) logo.style.backgroundImage = 'none'; /* frozen logo belongs to the captured charity */
    });
    var details = qs('.js-details-view .js-contents p');
    if (details) details.textContent = bundle.name + ' — pay what you want and support ' + (charityName || 'charity') + '.';

    /* split option preset rows for the suggested amount */
    var amount = bundle.suggested_price_minor || bundle.floor_minor || 0;
    var defaultHolder = qs('.js-default-preset-splits');
    if (defaultHolder) { defaultHolder.innerHTML = ''; defaultHolder.appendChild(splitRowsList(bundle, amount, 'default')); }
    var extraHolder = qs('.js-extra-charity-preset-splits');
    if (extraHolder) { extraHolder.innerHTML = ''; extraHolder.appendChild(splitRowsList(bundle, amount, 'extra-charity')); }
    var sliders = qs('.js-split-sliders');
    if (sliders) {
      sliders.innerHTML = '';
      var view = el('div', { 'class': 'splits-view' });
      (bundle.splits || []).forEach(function (entry) {
        view.appendChild(el('div', { 'class': 'split-view' }, [
          el('span', { 'class': 'split-name', text: partyLabel(entry) }),
          el('div', { 'class': 'split-slider-container' }, [
            el('span', { 'class': 'amount-container js-amount-container', text: money(Math.round(amount * splitFraction(entry, 'default'))) })
          ])
        ]));
      });
      sliders.appendChild(view);
    }
  }

  /* ---------- store search (/store/search, /store/c/{genre}) ---------- */

  function searchPage() {
    var view = qs('.js-search-view');
    if (!view) return;
    var q = params();
    var state = {
      search: q.search || '',
      genre: q.genre || '',
      platform: q.platform || '',
      drm: q.drm || '',
      sort: q.sort || 'bestselling',
      filter: q.filter || '',
      page: 0
    };
    /* /store/c/{token} is one category namespace spanning three facets. The
       nav's Top Genres column links genre tokens (including `vr`, whose
       captured Genre label is "Virtual Reality"), Top Platforms links
       platform tokens plus the `steam` DRM token, and /store/c/all appears in
       both columns as "All Genres" / "All platforms" — i.e. no facet at all.
       Resolve the token against the search page's own captured facet
       vocabularies in the order genre -> platform -> drm: `switch` is both a
       platform and a DRM value and the source files it under Top Platforms. */
    function inFacetVocab(name, token) {
      return qsa('input.js-filter-option[name="' + name + '"]', view).some(function (input) {
        return input.value === token;
      });
    }
    var m = path.match(/^\/store\/c\/([^/]+)$/);
    if (m) {
      var token = safeDecode(m[1]);
      if (token === 'all') { /* every product: no facet applied */ }
      else if (inFacetVocab('genre', token)) state.genre = token;
      else if (inFacetVocab('platform', token)) state.platform = token;
      else if (inFacetVocab('drm', token)) state.drm = token;
      else state.genre = token; /* outside every captured vocabulary: keep the
        genre reading so the page shows an honest 0 Results */
    }
    var urlPage = parseInt(q.page || '0', 10);
    if (!isNaN(urlPage) && urlPage >= 1) state.page = urlPage - 1; /* frozen pagination URLs are 1-based */

    /* pixel-fidelity case: the captured portal grid with no other params */
    var bareQuery = !('genre' in q) && !('platform' in q) && !('drm' in q) &&
      !('sort' in q) && !('filter' in q) && !('page' in q);
    var frozenPortal = path === '/store/search' && bareQuery &&
      (state.search === 'portal' || state.search === 'zzzz-no-match-websitebench');

    var titleText = qs('.js-title-text', view);
    var listHolder = qs('ul.js-entities-list', view);
    var pagination = qs('.js-pagination', view);
    var searchInput = qs('.js-search-input', view);
    if (searchInput) searchInput.value = state.search;

    var SORT_LABELS = { discount: 'Top Discounts', alphabetical: 'Alphabetical', newest: 'Release Date', bestselling: 'Bestselling' };
    var FILTER_LABELS = { onsale: 'On Sale', 'new': 'New Releases' };

    function syncControls() {
      qsa('.filter-option-view', view).forEach(function (group) {
        var heading = qs('h4.heading', group);
        var current = qs('.js-current-option', group);
        if (!heading || !current) return;
        var kind = heading.textContent.trim();
        if (kind === 'Sort') current.textContent = SORT_LABELS[state.sort] || 'Bestselling';
        else if (kind === 'Filter') current.textContent = FILTER_LABELS[state.filter] || 'None';
        else {
          var name = kind === 'Genre' ? 'genre' : (kind === 'Platform' ? 'platform' : (kind === 'DRM' ? 'drm' : null));
          if (!name) return;
          var label = 'Any';
          qsa('input.js-filter-option[name="' + name + '"]', group).forEach(function (input) {
            input.checked = input.value === state[name];
            if (input.checked && input.parentNode) label = input.parentNode.textContent.trim();
          });
          current.textContent = label;
        }
      });
    }

    function stateUrl() {
      var parts = [];
      if (state.sort) parts.push('sort=' + encodeURIComponent(state.sort));
      if (state.search) parts.push('search=' + encodeURIComponent(state.search));
      if (state.genre) parts.push('genre=' + encodeURIComponent(state.genre));
      if (state.platform) parts.push('platform=' + encodeURIComponent(state.platform));
      if (state.drm) parts.push('drm=' + encodeURIComponent(state.drm));
      if (state.filter) parts.push('filter=' + encodeURIComponent(state.filter));
      if (state.page > 0) parts.push('page=' + (state.page + 1));
      return '/store/search' + (parts.length ? '?' + parts.join('&') : '');
    }

    function apiUrl() {
      var parts = ['page=' + state.page, 'sort=' + encodeURIComponent(state.sort)];
      ['search', 'genre', 'platform', 'drm', 'filter'].forEach(function (k) {
        if (state[k]) parts.push(k + '=' + encodeURIComponent(state[k]));
      });
      return '/api/search?' + parts.join('&');
    }

    function tile(product, index) {
      var img = firstMedia(product.media || {}, ['standard_carousel_image', 'featured_image_recommendation', 'large_capsule']);
      var pricing = el('div', { 'class': 'price-container' });
      if (product.discount_pct > 0) {
        pricing.appendChild(el('div', { 'class': 'js-discount-gem discount-gem-container' }, [
          el('div', { 'class': 'discount-gem-view' }, [
            el('div', { 'class': 'discount-gem' }, [
              el('div', { 'class': 'js-discount-amount discount-amount' }, [
                document.createTextNode('-' + product.discount_pct + '%'),
                el('span', { 'class': 'off-text', text: ' OFF' })
              ])
            ])
          ])
        ]));
      }
      var priceBtn = el('div', { 'class': 'price-button js-price-button' }, [
        el('button', { 'class': 'price price-inner-button', text: money(product.current_price_minor) }),
        el('i', { 'class': 'hb hb-shopping-cart-solid' }),
        el('button', { 'class': 'add-text price-inner-button', text: 'Add' }),
        el('button', { 'class': 'buy-text price-inner-button', text: 'Buy' })
      ]);
      priceBtn.addEventListener('click', function (ev) {
        ev.preventDefault();
        /* REFINE-AFTER-HANDOFF: tile add-to-cart flow */
        cartAddAndOpen('product', product.slug);
      });
      pricing.appendChild(priceBtn);

      var drms = el('ul', { 'class': 'platforms no-style-list' }, (product.drm || []).map(function (d) {
        return el('li', { 'class': 'platform hb ' + drmIcon(d) });
      }));
      var oses = el('ul', { 'class': 'operating-systems no-style-list' }, (product.platforms || []).map(function (os) {
        return el('li', { 'class': 'operating-system hb ' + osIcon(os) });
      }));

      return el('li', { 'class': 'entity-block-container js-entity-container', 'data-entity-key': product.machine_name || product.slug, 'data-block-index': String(index + 1) }, [
        el('div', {}, [
          el('div', { 'class': 'entity js-entity' + (product.discount_pct > 0 ? ' on-sale' : '') }, [
            el('a', { 'class': 'entity-link js-entity-link', href: '/store/' + product.slug, 'aria-label': product.human_name }, [
              el('div', { 'class': 'entity-details' }, [
                img ? el('img', { 'class': 'entity-image', src: img, alt: product.human_name }) : null,
                el('div', { 'class': 'entity-meta' }, [
                  el('span', { 'class': 'entity-title', text: product.human_name })
                ])
              ])
            ]),
            el('div', { 'class': 'entity-purchase-details' }, [
              el('div', { 'class': 'entity-devices js-platform-delivery-container' }, [
                el('div', { 'class': 'platform-delivery-container' }, [drms, oses])
              ]),
              el('div', { 'class': 'entity-pricing js-price-container' }, [pricing])
            ])
          ])
        ])
      ]);
    }

    function renderPagination(numPages) {
      if (!pagination) return;
      pagination.innerHTML = '';
      if (numPages <= 1) return;
      var holder = el('div', { 'class': 'pagination no-style-list' });
      function nav(cls, page, disabled) {
        var a = el('a', { href: '#', 'class': cls + (disabled ? ' disabled' : '') });
        a.addEventListener('click', function (ev) { ev.preventDefault(); if (!disabled) go(page); });
        return a;
      }
      holder.appendChild(nav('js-grid-first grid-first grid-page-nav hb hb-angle-double-left', 0, state.page === 0));
      holder.appendChild(nav('js-grid-prev grid-prev grid-page-nav hb hb-angle-left', state.page - 1, state.page === 0));
      for (var p = 0; p < numPages; p++) {
        (function (p2) {
          var a = el('a', { href: '#', 'class': 'js-grid-page grid-page visible' + (p2 === state.page ? ' active' : ''), 'data-page': String(p2 + 1), text: String(p2 + 1) });
          a.addEventListener('click', function (ev) { ev.preventDefault(); go(p2); });
          holder.appendChild(a);
        })(p);
      }
      holder.appendChild(nav('js-grid-next grid-next grid-page-nav hb hb-angle-right', state.page + 1, state.page >= numPages - 1));
      holder.appendChild(nav('js-grid-last grid-last grid-page-nav hb hb-angle-double-right', numPages - 1, state.page >= numPages - 1));
      pagination.appendChild(holder);
    }

    function render() {
      api(apiUrl()).then(function (r) {
        if (!r.ok || !listHolder) return;
        var data = r.data;
        if (titleText) titleText.textContent = commas(data.num_results || 0) + ' Results';
        if (state.search) document.title = '"' + state.search + '" | The Humble Store';
        else if (state.genre) document.title = 'The Humble Store: great games at great prices';
        listHolder.innerHTML = '';
        (data.results || []).forEach(function (product, i) { listHolder.appendChild(tile(product, i)); });
        var oldClear = qs('.js-hb-clear-search', view);
        if (oldClear) oldClear.parentNode.removeChild(oldClear);
        if (!data.num_results) {
          /* frozen no-results structure: "0 Results" + empty grid; the
             clear-search link is the route back */
          listHolder.parentNode.appendChild(el('a', { 'class': 'js-hb-clear-search', href: '/store/search', style: { display: 'block', padding: '24px 0', textAlign: 'center' }, text: 'Clear your search and browse all games' }));
        }
        renderPagination(data.num_pages || 0);
      });
    }

    function go(page) {
      state.page = Math.max(0, page);
      history.replaceState(null, '', stateUrl());
      render();
      try { window.scrollTo(0, 0); } catch (e) { /* noop */ }
    }
    function apply() {
      state.page = 0;
      history.replaceState(null, '', stateUrl());
      syncControls();
      render();
    }

    /* dropdown open/close (frozen CSS hides .js-dropdown-options) */
    qsa('.js-filter-dropdown', view).forEach(function (dropdown) {
      var options = qs('.js-dropdown-options', dropdown);
      if (!options) return;
      dropdown.addEventListener('click', function (ev) {
        if (ev.target.closest && ev.target.closest('.js-dropdown-options') && ev.target.tagName === 'INPUT') return;
        var open = options.style.display === 'block';
        qsa('.js-dropdown-options', view).forEach(function (other) { other.style.removeProperty('display'); });
        if (!open) options.style.display = 'block';
      });
    });
    document.addEventListener('click', function (ev) {
      if (!ev.target.closest || !ev.target.closest('.js-filter-dropdown')) {
        qsa('.js-dropdown-options', view).forEach(function (o) { o.style.removeProperty('display'); });
      }
    });

    /* sort / filter single-choice options */
    qsa('a.js-option', view).forEach(function (option) {
      option.addEventListener('click', function (ev) {
        ev.preventDefault();
        var value = option.getAttribute('data-option-value');
        var group = option.closest ? option.closest('.filter-option-view') : null;
        var kind = group ? (qs('h4.heading', group) || {}).textContent : '';
        if (kind && kind.trim() === 'Sort') state.sort = value;
        else state.filter = (value === 'all') ? '' : value;
        apply();
      });
    });

    /* facet checkboxes: the API is single-valued per facet */
    qsa('input.js-filter-option', view).forEach(function (input) {
      input.addEventListener('change', function () {
        var name = input.getAttribute('name');
        if (!name) return;
        state[name] = input.checked ? input.value : '';
        apply();
      });
    });
    qsa('a.js-show-all-in-category', view).forEach(function (link) {
      link.addEventListener('click', function (ev) {
        ev.preventDefault();
        var group = link.closest ? link.closest('.filter-option-view') : null;
        if (!group) return;
        var input = qs('input.js-filter-option', group);
        if (input) { state[input.getAttribute('name')] = ''; apply(); }
      });
    });

    if (searchInput) {
      searchInput.addEventListener('input', debounce(function () {
        state.search = searchInput.value.trim();
        apply();
      }, 350));
      searchInput.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter') { ev.preventDefault(); state.search = searchInput.value.trim(); apply(); }
      });
    }

    syncControls();
    if (!frozenPortal) render(); /* frozen portal grid keeps its pixels until interaction */
  }

  /* ---------- store product (/store/{slug}) ---------- */

  function productPage() {
    var slug = decodeURIComponent(path.split('/')[2] || '');
    if (!qs('.product-details-page')) return; /* branded 404 body */
    api('/api/product/' + encodeURIComponent(slug)).then(function (r) {
      if (!r.ok) return;
      var product = r.data;
      if (slug !== 'satisfactory') hydrateProduct(product);
      else repairFrozenFeatured(product); /* frozen page: the stripped
        trailer iframe leaves a dead slick husk in the featured slot */
      wireProduct(product);
    });
  }

  /* Seed HTML (product description / system requirements) can embed absolute
     image URLs that were never localized. The clone's CSP blocks every
     remote origin, so injecting them verbatim yields broken images plus a
     console error each. Drop the unresolvable references on injection — the
     same policy the page builder applies to frozen head refs. */
  function setSeedHtml(node, html) {
    if (!node) return;
    /* parse into a <template>: its contents are an inert fragment, so the
       remote references are dropped before the browser ever fetches them */
    var tpl = document.createElement('template');
    tpl.innerHTML = html || '';
    qsa('img, source, iframe, script, link, video, audio', tpl.content).forEach(function (n) {
      var url = n.getAttribute('src') || n.getAttribute('href') || n.getAttribute('data-src') || '';
      if (/^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(url) && n.parentNode) n.parentNode.removeChild(n);
    });
    node.innerHTML = '';
    node.appendChild(tpl.content);
  }

  /* review_text tokens ("overwhelmingly_positive") render as the captured
     label ("Overwhelmingly Positive"). */
  function ratingLabel(token) {
    return String(token || '').split('_').filter(Boolean).map(function (word) {
      return word.charAt(0).toUpperCase() + word.slice(1);
    }).join(' ');
  }

  /* The Steam user-rating summary. Captured on /store/satisfactory as
     `.review-text` = steam icon + "96% |" + "Overwhelmingly Positive" and
     `.tooltip-text` = "96% of the 1,772 user reviews on Steam in the last 30
     days are positive." That tooltip's recency clause belongs to
     display_user_ratings "steam_recent"; for "steam_overall" the clause is
     dropped (that variant was not captured). Without per-product rating data
     the whole property is hidden — the frozen page's numbers must never
     stand in for another product's. */
  function bindUserRating(product) {
    var view = qs('.user-rating-view');
    if (!view) return;
    var holder = (view.closest && view.closest('.basic-property-view')) || view;
    var rating = product.user_rating || null;
    var pct = rating && typeof rating.steam_percent === 'number'
      ? Math.round(rating.steam_percent * 100) : null;
    if (pct === null) {
      view.innerHTML = '';
      holder.style.display = 'none';
      return;
    }
    holder.style.removeProperty('display');
    var label = ratingLabel(rating.review_text);
    var text = qs('.review-text', view);
    if (!text) { text = el('div', { 'class': 'review-text' }); view.appendChild(text); }
    text.innerHTML = '';
    text.appendChild(el('i', { 'class': 'hb hb-steam' }));
    text.appendChild(document.createTextNode(' ' + pct + '% |'));
    if (label) text.appendChild(document.createTextNode(' ' + label));
    var tip = qs('.tooltip-text', view);
    if (!tip) { tip = el('div', { 'class': 'tooltip-text' }); view.appendChild(tip); }
    var count = typeof rating.steam_count === 'number' ? rating.steam_count : null;
    tip.textContent = count === null ? (pct + '% of user reviews on Steam are positive.')
      : (pct + '% of the ' + commas(count) + ' user reviews on Steam' +
        (rating.display_user_ratings === 'steam_recent' ? ' in the last 30 days' : '') +
        ' are positive.');
  }

  /* Critical Reception. The frozen page ships Satisfactory's three OpenCritic
     entries; every other product must get its own or none. `product.reviews`
     (per entry: snippet / score / author / outlet / url) is the contract; the
     authorized catalog subset carries no critic reviews for any other title,
     so the section renders empty with a truthful note instead of another
     product's quotes. */
  function bindReviews(product) {
    var view = qs('.reviews-view');
    if (!view) return;
    var collection = qs('.reviews-collection', view);
    var value = qs('.js-property-value', view);
    if (!collection && value) {
      collection = el('div', { 'class': 'reviews-collection entity-block-collection' });
      value.innerHTML = '';
      value.appendChild(collection);
    }
    if (!collection) return;
    collection.innerHTML = '';
    var attribution = qs('.opencritic-attribution', view);
    var reviews = product.reviews || [];
    var oldNote = qs('.js-hb-no-reviews', view);
    if (oldNote && oldNote.parentNode) oldNote.parentNode.removeChild(oldNote);
    if (!reviews.length) {
      if (attribution) attribution.style.display = 'none';
      collection.appendChild(el('p', {
        'class': 'fine-print js-hb-no-reviews js-hb-offline-hint',
        style: { margin: '0', fontSize: '12px', lineHeight: '1.4', color: '#cdd2df' },
        text: 'No critic reviews for ' + product.human_name + ' in this offline catalog subset. ' +
          'Critical Reception was captured for one product only, so no review text is shown here.'
      }));
      return;
    }
    if (attribution) attribution.style.removeProperty('display');
    reviews.forEach(function (review) {
      var reviewer = el('div', { 'class': 'reviewer-information' }, [
        el('span', { 'class': 'review-score', text: review.score || '' })
      ]);
      var byline = [];
      if (review.author) byline.push(el('span', { 'class': 'review-author', text: review.author }));
      if (review.outlet) byline.push(el('span', { text: review.outlet }));
      if (review.url) {
        reviewer.appendChild(el('a', {
          'class': 'full-review-link', rel: 'nofollow', target: '_blank', href: review.url,
          'aria-label': 'Read the review by ' + (review.author || '') + ' at ' + (review.outlet || '')
        }, byline));
      } else byline.forEach(function (node) { reviewer.appendChild(node); });
      collection.appendChild(el('div', { 'class': 'reviews-entity entity' }, [
        el('div', { 'class': 'entity-details' }, [
          el('div', { 'class': 'review-information' }, [
            el('div', { 'class': 'review-snippet' }, [el('q', { text: review.snippet || '' })])
          ]),
          reviewer
        ])
      ]));
    });
  }

  function hydrateProduct(product) {
    document.title = 'Buy ' + product.human_name + ' from the Humble Store' + (product.discount_pct > 0 ? ' and save ' + product.discount_pct + '%' : '');

    var title = qs('.js-human-name h1');
    if (title) title.textContent = product.human_name;

    var capsule = qs('.js-grid-image img');
    var capsuleUrl = firstMedia(product.media || {}, ['large_capsule', 'standard_carousel_image']);
    if (capsule && capsuleUrl) { capsule.src = capsuleUrl; capsule.alt = product.human_name; }

    var current = qs('.price-info .current-price');
    if (current) current.textContent = money(product.current_price_minor);
    var full = qs('.price-info .full-price');
    if (full) {
      if (product.discount_pct > 0) full.textContent = money(product.full_price_minor);
      else full.style.display = 'none';
    }
    var gem = qs('.price-info .js-discount-gem');
    if (gem) {
      if (product.discount_pct > 0) {
        var amount = qs('.js-discount-amount', gem);
        if (amount) {
          amount.innerHTML = '';
          amount.appendChild(document.createTextNode('-' + product.discount_pct + '%'));
          amount.appendChild(el('span', { 'class': 'off-text', text: ' OFF' }));
        }
        var breakdownFull = qs('.breakdown-full-price', gem);
        if (breakdownFull) breakdownFull.textContent = money(product.full_price_minor);
        var breakdownPct = qs('.store-discount', gem);
        if (breakdownPct) breakdownPct.textContent = '-' + product.discount_pct + '%';
        var breakdownNow = qs('.store-discounted-price', gem);
        if (breakdownNow) breakdownNow.textContent = money(product.current_price_minor);
      } else gem.style.display = 'none';
    }
    if (product.discount_pct <= 0) {
      var timer = qs('.promo-timer-view');
      if (timer) timer.style.display = 'none'; /* frozen sale countdown belongs to the captured product */
      var rewards = qs('.rewards-monthly-section');
      if (rewards) rewards.style.display = 'none';
    }

    /* platform / DRM / OS badges */
    var pad = qs('.platform-and-delivery');
    if (pad) {
      pad.innerHTML = '';
      (product.drm || []).forEach(function (d) { pad.appendChild(el('i', { 'class': 'hb ' + drmIcon(d), title: d })); });
      (product.platforms || []).forEach(function (os) { pad.appendChild(el('i', { 'class': 'hb ' + osIcon(os), title: os })); });
    }
    var avail = qs('.icon_dict-view');
    if (avail) {
      avail.innerHTML = '';
      (product.delivery_methods || product.drm || []).forEach(function (d) {
        avail.appendChild(el('div', { 'class': 'availability-section' }, [
          el('div', { 'class': 'platform ' + d }, [el('i', { 'class': 'hb ' + drmIcon(d), title: d })]),
          el('ul', { 'class': 'availableOSes no-style-list' }, (product.platforms || []).map(function (os) {
            return el('li', { 'class': 'os ' + os }, [el('i', { 'class': 'hb ' + osIcon(os), title: os })]);
          }))
        ]));
      });
    }
    var osList = qs('ul.platforms-view.OSes');
    if (osList) {
      osList.innerHTML = '';
      (product.platforms || []).forEach(function (os) {
        osList.appendChild(el('li', { 'class': 'os ' + os }, [el('i', { 'class': 'hb ' + osIcon(os), title: os })]));
      });
    }

    /* developer / publisher / links */
    function fillParty(sel, list, key) {
      var holder = qs(sel);
      if (!holder) return;
      holder.innerHTML = '';
      (list || []).forEach(function (party, i) {
        if (i) holder.appendChild(document.createTextNode(', '));
        holder.appendChild(el('a', { href: '/store/search?' + key + '=' + encodeURIComponent(party.name), text: party.name }));
      });
    }
    fillParty('.developers-view', product.developers, 'developer');
    fillParty('.publishers-view', product.publishers, 'publisher');
    var links = qs('ul.links-view');
    if (links) {
      links.innerHTML = '';
      (product.developers || []).concat(product.publishers || []).forEach(function (party) {
        if (party.url) links.appendChild(el('li', {}, [el('a', { href: party.url, target: '_blank', rel: 'nofollow', text: party.name + ' Website' })]));
      });
    }

    /* description / disclaimer / system requirements (seed HTML) */
    setSeedHtml(qs('.description-view .js-property-content'), product.description);
    setSeedHtml(qs('#system-requirements .js-property-content'), product.system_requirements);
    var disclaimer = qs('.disclaimer-view');
    if (disclaimer) {
      disclaimer.innerHTML = '';
      disclaimer.appendChild(el('b', { text: product.human_name + ' is provided via ' + (product.delivery_methods || product.drm || []).join(', ') + '. A free account may be required.' }));
    }

    /* per-product Steam rating + Critical Reception: the frozen shell carries
       the captured product's values, so both must be rebound or cleared */
    bindUserRating(product);
    bindReviews(product);

    /* media gallery: simple main image + click-to-swap thumbnails replace
       the frozen slick carousel (vendored runtime is stripped) */
    ensureGallery(product);
  }

  function repairFrozenFeatured(product) {
    /* Replace only the featured slot; the frozen thumbnail strip stays and
       its clicks swap the main image. Trailer playback is a recorded known
       difference (external video not localized). */
    var media = product.media || {};
    var screenshots = (media.screenshots || []).map(mediaUrl).filter(Boolean);
    var featured = qs('.js-featured-media');
    if (!featured || !screenshots.length) return;
    /* the stripped slick lazy loader never promoted data-lazy to src, so all
       31 frozen thumbnails render at naturalWidth 0 even though every file is
       localized on disk. Promote them (they are already local paths). */
    qsa('.js-media-thumbnails img[data-lazy]').forEach(function (im) {
      var lazy = im.getAttribute('data-lazy');
      if (lazy && !im.getAttribute('src')) {
        im.setAttribute('src', lazy);
        im.classList.remove('slick-loading');
      }
    });
    var frozenThumbs = qsa('.js-media-thumbnails img').map(function (im) {
      return im.currentSrc || im.getAttribute('src') || im.getAttribute('data-lazy') || im.getAttribute('data-src') || '';
    }).filter(function (u) { return u && u.indexOf('data:') !== 0; });
    var firstFill = frozenThumbs[0] || screenshots[0];
    featured.innerHTML = '';
    featured.classList.remove('slick-initialized', 'slick-slider');
    var main = el('img', { 'class': 'single-media image js-hb-gallery-main', alt: product.human_name + ' media', src: firstFill, style: { width: '100%', display: 'block' } });
    featured.appendChild(el('div', { 'class': 'carousel-image-container' }, [main]));
    qsa('.js-media-thumbnails .thumbnail').forEach(function (holder) {
      /* a video thumbnail carries a poster plus a play-icon overlay: bind the
         holder once and always swap in its first (poster) image */
      var poster = qs('img', holder);
      if (!poster) return;
      holder.style.cursor = 'pointer';
      holder.addEventListener('click', function () {
        var url = poster.currentSrc || poster.getAttribute('src');
        if (url) main.src = url;
      });
    });
  }

  function ensureGallery(product) {
    var media = product.media || {};
    var screenshots = (media.screenshots || []).map(mediaUrl).filter(Boolean);
    var thumbs = (media.thumbnails || []).map(mediaUrl).filter(Boolean);
    var featured = qs('.js-featured-media');
    /* Every product detail page is served from the same frozen template, which
     * ships Satisfactory's gallery for the hydrator to replace. A product whose
     * detail page was never captured has no screenshots to replace it with, and
     * the guard below then leaves that gallery in place — so promoting the lazy
     * attributes would put Satisfactory's screenshots on another game's page.
     * Empty is the truthful answer: this product has no captured screenshots. */
    if (!screenshots.length) {
      if (featured) featured.remove();
      var strandedThumbs = qs('.js-media-thumbnails');
      if (strandedThumbs) strandedThumbs.remove();
      return;
    }
    if (featured && screenshots.length) {
      featured.innerHTML = '';
      featured.classList.remove('slick-initialized', 'slick-slider');
      var main = el('img', { 'class': 'single-media image js-hb-gallery-main', alt: product.human_name + ' screenshot', src: screenshots[0], style: { width: '100%', display: 'block' } });
      featured.appendChild(el('div', { 'class': 'carousel-image-container' }, [main]));
      var thumbHolder = qs('.js-media-thumbnails');
      if (thumbHolder) {
        thumbHolder.innerHTML = '';
        thumbHolder.classList.remove('slick-initialized', 'slick-slider');
        var row = el('div', { style: { display: 'flex', flexWrap: 'wrap', gap: '6px', padding: '8px 0' } });
        screenshots.forEach(function (shot, i) {
          var thumb = el('div', { 'class': 'thumbnail js-clickable-thumbnail screenshot', style: { cursor: 'pointer' } }, [
            el('img', { 'class': 'thumbnail-image', alt: 'Media thumbnail', src: thumbs[i] || shot, style: { width: '120px', display: 'block' } })
          ]);
          thumb.addEventListener('click', function () { main.src = shot; });
          row.appendChild(thumb);
        });
        thumbHolder.appendChild(row);
      }
    }
  }

  function wireProduct(product) {
    /* REFINE-AFTER-HANDOFF: cart + checkout flows pending handoff tr-001. */
    var buttons = qs('.js-shopping-cart-button');
    if (buttons) {
      var addBtn = qs('button.add', buttons);
      if (addBtn) addBtn.addEventListener('click', function (ev) {
        ev.preventDefault();
        cartAddAndOpen('product', product.slug);
      });
      var checkoutBtn = qs('button.checkout', buttons);
      if (checkoutBtn) checkoutBtn.addEventListener('click', function (ev) {
        ev.preventDefault();
        cartAdd('product', product.slug).then(function (r) { if (r.ok) location.href = '/checkout'; });
      });
    }

    var wishBtn = qs('.js-wishlist-container .js-wishlist-button');
    if (wishBtn) {
      getAccount().then(function (state) {
        if (!state.authenticated) {
          wishBtn.addEventListener('click', function () {
            location.href = '/login?goto=' + encodeURIComponent(path);
          });
          return;
        }
        api('/api/wishlist').then(function (r) {
          if (r.ok && (r.data.wishlist || []).some(function (w) { return w.slug === product.slug; })) wishBtn.classList.add('saved');
        });
        wishBtn.addEventListener('click', function () {
          var saved = wishBtn.classList.contains('saved');
          api('/api/wishlist/' + (saved ? 'remove' : 'add'), { body: { slug: product.slug } }).then(function (r) {
            if (r.ok) wishBtn.classList.toggle('saved', !saved);
          });
        });
      });
    }
  }

  /* ---------- checkout (/checkout) ---------- */
  /* REFINE-AFTER-HANDOFF: entire checkout interior is a local sandbox
     surface; the source walk stopped before payment submission. */

  function hideStoreSubNavs() {
    /* The served shell is the store page, whose sub-navs (storefront charity
       strip, shopping/wallet strip) do not exist on the source's checkout
       review — including a wallet amount in the wrong currency. */
    qsa('.js-storefront-nav, .shopping-nav').forEach(function (nav) {
      nav.style.display = 'none';
    });
  }

  function clearFrozenOverlays() {
    /* The frozen shells keep an absolutely positioned hero/background layer
       that paints over an injected panel and swallows its pointer events. */
    qsa('#js-background-container, .js-background-container').forEach(function (node) {
      node.style.display = 'none';
    });
  }

  /* ---------- checkout (/checkout) ---------- */
  /* Structure, class names, field names and copy come from the authenticated
     capture of the real review (walk tr-001; scope/handoff-findings.md):
     left column = upsell / delivery / payment method / gift / leaderboard /
     submit, right column = Order Summary. The source's checkout stylesheet
     was never localized (the review is behind auth and only its DOM was
     captured read-only), so the panels carry the captured classes for
     selector fidelity plus local inline layout styling. */

  /* Frozen upsell copy + prices from the captured offer card. */
  var CHOICE_UPSELL = {
    name: 'Humble Choice',
    discount_copy: '5% off your first month!',
    first_month_minor: 1709,
    renewal_minor: 1799
  };
  /* The captured radios carry the source's Stripe-backed value attributes.
     The clone is a local sandbox, so the values are clone-local ids and the
     opaque sandbox scenario stays the only payment input (deliberate,
     recorded difference — labels and field name are the captured ones). */
  /* hb-paypal / hb-credit-card are in the localized icon font. The source's
     Alipay mark is a remote CDN png that was never harvested (it only appears
     on the authenticated review) and cannot be fetched offline, so that one
     trailing slot renders empty; its accessible name duplicated the visible
     label, so nothing is lost semantically. Recorded difference. */
  /* Each visible processor maps to an opaque local sandbox scenario; the
     demo-only control below the panel can override it to reach the declined
     and retryable outcomes (catalog_db.PROCESSOR_SCENARIOS mirrors this). */
  var PROCESSOR_CHOICES = [
    { value: 'paypal', label: 'Paypal', icon: 'hb-paypal', scenario: 'sandbox-approved' },
    { value: 'card', label: 'Credit Card', icon: 'hb-credit-card', scenario: 'sandbox-approved' },
    { value: 'alipay', label: 'Alipay', icon: 'hb-alipay', scenario: 'sandbox-approved' }
  ];
  function processorScenario(value) {
    for (var i = 0; i < PROCESSOR_CHOICES.length; i++) {
      if (PROCESSOR_CHOICES[i].value === value) return PROCESSOR_CHOICES[i].scenario;
    }
    return 'sandbox-approved';
  }
  var SANDBOX_OUTCOMES = [
    ['sandbox-approved', 'Sandbox approved'],
    ['sandbox-declined', 'Sandbox declined'],
    ['sandbox-retry', 'Sandbox retry']
  ];
  var LICENSE_NOTICE_HEAD =
    'BUYERS ARE GRANTED ONLY A LICENSE FOR SOME DIGITAL PRODUCTS IN THIS PURCHASE. SEE ';
  var LICENSE_NOTICE_TAIL = ' FOR MORE DETAILS.';

  function setHidden(node, hidden) {
    if (!node) return;
    if (hidden) node.classList.add('is-hidden');
    else node.classList.remove('is-hidden');
    node.style.display = hidden ? 'none' : '';
  }

  function commonView(headerText, contents, extraClass) {
    var children = [];
    if (headerText) children.push(el('h4', { 'class': 'common-header', text: headerText }));
    children.push(el('div', { 'class': 'common-contents' }, contents));
    return el('div', {
      'class': 'common-view ' + (extraClass || ''),
      style: { background: '#fff', border: '1px solid #c7cbd4', borderRadius: '3px', padding: '16px 18px', marginBottom: '16px' }
    }, children);
  }

  function checkboxLabel(id, name, labelText, cls) {
    var input = el('input', { type: 'checkbox', id: id, name: name, 'class': cls + ' dark-checkbox' });
    var label = el('label', {
      'class': (cls === 'js-add-upsell-monthly' ? 'upsell-label' : '') + ' label-with-checkbox-radio',
      'for': id, style: { display: 'block', margin: '6px 0', cursor: 'pointer' }
    }, [input, el('span', { 'class': 'label-text', style: { marginLeft: '6px' }, text: labelText })]);
    return { input: input, label: label };
  }

  function radioLabel(id, name, value, labelText, cls) {
    var input = el('input', {
      type: 'radio', id: id, name: name, value: value, autocomplete: 'off',
      'class': cls + ' dark-radio-button'
    });
    var label = el('label', {
      'class': 'label-with-checkbox-radio', 'for': id,
      style: { display: 'block', margin: '6px 0', cursor: 'pointer' }
    }, [input, el('span', { 'class': 'label-text', style: { marginLeft: '6px' }, text: labelText })]);
    return { input: input, label: label };
  }

  function hintLine(text) {
    return el('p', {
      'class': 'fine-print js-hb-offline-hint',
      style: { margin: '8px 0 0', fontSize: '12px', lineHeight: '1.4', color: '#6b7280' },
      text: text
    });
  }

  function summaryRow(labelText, amountMinor, rowClass, subInfoText) {
    var info = [el('span', { text: labelText })];
    if (subInfoText) {
      /* The source renders the item count but keeps it hidden on this view. */
      info.push(el('span', { 'class': 'sub-info is-hidden', style: { display: 'none' }, text: subInfoText }));
    }
    return el('div', {
      'class': 'js-item-and-price item-and-price ' + (rowClass || ''),
      style: {
        display: 'flex', justifyContent: 'space-between', gap: '12px',
        padding: '6px 0', fontWeight: rowClass === 'total' ? 'bold' : 'normal'
      }
    }, [
      el('div', { 'class': 'item-info' }, info),
      el('span', {
        'class': rowClass === 'total' ? 'js-hb-checkout-total' : null,
        text: money(amountMinor)
      })
    ]);
  }

  function orderSummaryView(view, opts) {
    opts = opts || {};
    var items = el('div', { 'class': 'items-and-prices' });
    (view.items || []).forEach(function (item) {
      var count = item.kind === 'bundle' && item.unlocked_count
        ? String(item.unlocked_count) + ' Items' : null;
      items.appendChild(summaryRow(item.name || item.slug, item.line_total_minor, '', count));
    });
    if (opts.upsell) {
      /* Display-only preview: the offline demo never enrolls a membership. */
      var row = summaryRow(CHOICE_UPSELL.name, CHOICE_UPSELL.first_month_minor, 'js-hb-upsell-line');
      row.appendChild(el('span', {
        'class': 'sub-info',
        style: { flexBasis: '100%', fontSize: '12px', color: '#6b7280' },
        text: 'Preview only — not charged and not enrolled in this offline demo.'
      }));
      row.style.flexWrap = 'wrap';
      items.appendChild(row);
    }

    var subtotal = el('div', {
      'class': 'subtotal',
      style: { borderTop: '1px solid #c7cbd4', marginTop: '8px', paddingTop: '8px' }
    }, [
      summaryRow('Subtotal', view.subtotal_minor, ''),
      summaryRow(view.tax_label || 'HST', view.tax_minor, 'tax-info')
    ]);

    var children = [
      el('h2', { 'class': 'summary-header', style: { margin: '0 0 12px', fontSize: '18px' }, text: 'Order Summary' }),
      items,
      subtotal,
      summaryRow('Total', view.grand_total_minor, 'total')
    ];

    if (view.charity_minor && view.charity_name) {
      children.push(el('div', {
        'class': 'split-callout js-split-callout',
        style: { background: '#e8f4ea', border: '1px solid #b7d9bf', borderRadius: '3px', padding: '10px 12px', margin: '12px 0' }
      }, [
        el('strong', { text: "You're Supporting Charity" }),
        el('p', {
          style: { margin: '4px 0 0' },
          text: money(view.charity_minor) + ' of your order supports ' + view.charity_name + '. Thank you!'
        })
      ]));
    }

    children.push(el('div', { 'class': 'bundle-purchase-disclosure' }, [
      el('p', { 'class': 'purchase-disclosure', style: { margin: '0', fontSize: '11px', lineHeight: '1.5' } }, [
        el('strong', {}, [
          LICENSE_NOTICE_HEAD,
          el('a', { href: '/terms', target: '_blank', 'class': 'white-link', text: 'TERMS' }),
          LICENSE_NOTICE_TAIL
        ])
      ])
    ]));

    return el('div', {
      'class': 'common-view js-order-summary-view-desktop desktop',
      style: { background: '#fff', border: '1px solid #c7cbd4', borderRadius: '3px', padding: '16px 18px' }
    }, [el('div', { 'class': 'order-summary-view common-contents' }, children)]);
  }

  function checkoutPage() {
    var host = qs('.js-page-content') || qs('.inner-main-wrapper') || qs('.main-content');
    if (!host) return;
    clearFrozenOverlays();
    hideStoreSubNavs();
    document.title = 'Humble Checkout';
    /* Donation mode is chosen on the bundle page in the source, not here; it
       moves the charity share and with it the taxable base. */
    var splitMode = 'default';
    try { splitMode = sessionStorage.getItem('hb-split-mode') || 'default'; } catch (e) { /* storage unavailable */ }

    Promise.all([refreshCart(splitMode), getAccount()]).then(function (results) {
      var view = results[0];
      var accountState = results[1] || {};
      var account = accountState.account || {};
      host.innerHTML = '';

      var page = el('div', {
        'class': 'checkout-page js-checkout-page grid',
        style: { maxWidth: '1080px', margin: '30px auto', padding: '0 16px 48px', color: '#494f5c' }
      });
      page.appendChild(el('h1', { 'class': 'page-header js-checkout-page-header', text: 'Checkout' }));
      host.appendChild(page);

      if (!view.items || !view.items.length) {
        page.appendChild(el('p', { text: 'Your cart is empty.' }));
        page.appendChild(el('a', { href: '/bundles', text: 'Browse bundles' }));
        return;
      }

      var columns = el('div', { style: { display: 'flex', gap: '24px', alignItems: 'flex-start', flexWrap: 'wrap', marginTop: '18px' } });
      var mainArea = el('div', { 'class': 'main-area', style: { flex: '1 1 420px', minWidth: '300px' } });
      var sidebar = el('div', { 'class': 'sidebar', style: { flex: '0 0 320px', minWidth: '280px' } });
      columns.appendChild(mainArea);
      columns.appendChild(sidebar);
      page.appendChild(columns);

      var bundleItems = view.items.filter(function (item) { return item.kind === 'bundle'; });

      /* ---- summary (right column), re-rendered when the upsell toggles ---- */
      function renderSummary() {
        sidebar.innerHTML = '';
        sidebar.appendChild(orderSummaryView(view, { upsell: upsellBox.input.checked }));
      }

      /* ---- 1. You Might Also Like (Humble Choice upsell) ---- */
      var upsellBox = checkboxLabel('add-upsell-monthly', 'add-upsell', 'Add Choice to My Cart', 'js-add-upsell-monthly');
      var offer = el('p', { style: { margin: '6px 0' } }, [
        'You qualify for ',
        el('b', { text: CHOICE_UPSELL.discount_copy }),
        " Enjoy this month's mix of games to own, play the Humble Games Collection, and more for only ",
        el('b', { text: money(CHOICE_UPSELL.first_month_minor) }),
        '.'
      ]);
      var upsellView = el('div', { 'class': 'upsell-view common-view', style: { background: '#fff', border: '1px solid #c7cbd4', borderRadius: '3px', padding: '16px 18px', marginBottom: '16px' } }, [
        el('h4', { 'class': 'common-header', text: 'You Might Also Like' }),
        el('div', { 'class': 'common-contents js-upsells' }, [
          el('div', { 'class': 'upsell-item-view' }, [
            el('h2', { 'class': 'heading-medium', style: { margin: '0 0 4px', fontSize: '18px' }, text: CHOICE_UPSELL.name }),
            offer,
            upsellBox.label,
            hintLine('This offline demo never creates a subscription or charges the '
              + money(CHOICE_UPSELL.renewal_minor) + ' monthly renewal: ticking the box only previews the '
              + CHOICE_UPSELL.name + ' line on your Order Summary.')
          ])
        ])
      ]);
      upsellBox.input.addEventListener('change', function () { renderSummary(); });
      mainArea.appendChild(el('div', { 'class': 'js-upsell-view' }, [upsellView]));

      /* ---- 2. Delivery Information ---- */
      var signOut = el('button', {
        type: 'button', 'class': 'no-style-button text-button redirect js-sign-out-redirect',
        style: { background: 'none', border: 'none', padding: '0', color: '#c00', cursor: 'pointer', textDecoration: 'underline' },
        text: 'Sign out'
      });
      signOut.addEventListener('click', function () {
        signOut.disabled = true;
        api('/api/account/logout', { method: 'POST', body: {} }).then(function () { location.reload(); });
      });
      /* the settings page's Email Address control edits the delivery
         destination for a digital order, so it wins over the sign-in
         address here (see /api/account -> delivery_email) */
      var deliveryEmail = accountState.delivery_email || account.email_normalized || account.email || '';
      mainArea.appendChild(el('div', { 'class': 'js-delivery-view' }, [
        commonView('Delivery Information', [
          el('div', { 'class': 'delivery-info' }, [
            (bundleItems.length ? 'This bundle will be sent to' : 'This order will be sent to'),
            el('br'),
            el('strong', { text: deliveryEmail })
          ]),
          el('div', { style: { marginTop: '8px' } }, [
            el('span', { text: 'Not You?' }), ' ', signOut
          ])
        ], 'delivery-view')
      ]));

      /* ---- 3. Payment Method ---- */
      var processors = el('div', { 'class': 'payment-processors' });
      var processorInputs = [];
      PROCESSOR_CHOICES.forEach(function (choice) {
        var input = el('input', {
          type: 'radio', name: 'processor-type', value: choice.value, autocomplete: 'off',
          'data-processor': choice.value, 'class': 'js-processor-button dark-radio-button'
        });
        processorInputs.push(input);
        var label = el('label', {
          'class': 'payment-processor-selection label-with-checkbox-radio',
          style: { display: 'flex', alignItems: 'center', gap: '8px', margin: '6px 0', cursor: 'pointer' }
        }, [
          input,
          el('span', { 'class': 'label-text', style: { flex: '1' }, text: choice.label }),
          el('i', { 'class': 'hb ' + choice.icon, 'aria-hidden': 'true' })
        ]);
        input.addEventListener('change', function () { clearPaymentWarning(); });
        processors.appendChild(label);
      });
      var paymentWarning = el('span', { 'class': 'warning-text js-warning-text', text: 'Please Select a Payment Method' });
      setHidden(paymentWarning, true);
      paymentWarning.style.color = '#c0392b';
      var paymentMethodView = el('div', {
        'class': 'common-view payment-method-view',
        style: { background: '#fff', border: '1px solid #c7cbd4', borderRadius: '3px', padding: '16px 18px', marginBottom: '16px' }
      }, [
        el('h4', { 'class': 'common-header', text: 'Payment Method' }),
        el('div', { 'class': 'common-contents' }, [
          processors,
          el('span', {
            'class': 'payment-processor-warning js-payment-processor-warning',
            style: { display: 'block', marginTop: '8px', fontSize: '13px' },
            text: 'After clicking "Continue to Payment", you will be redirected to complete your purchase securely.'
          }),
          hintLine('Offline demo: no real payment is possible and nothing leaves this machine. '
            + 'The redirect is simulated locally, and Paypal, Credit Card and Alipay each map to '
            + 'the local "sandbox-approved" scenario. Use the demo-only control below the form to '
            + 'exercise the declined and retryable outcomes instead.')
        ]),
        paymentWarning
      ]);
      function clearPaymentWarning() {
        paymentMethodView.classList.remove('js-has-errors');
        paymentMethodView.classList.remove('has-errors');
        setHidden(paymentWarning, true);
      }
      function showPaymentWarning() {
        /* Mirrors the captured payment-step state: the review does not
           advance, it flags the panel and unhides the warning. */
        paymentMethodView.classList.add('js-has-errors');
        paymentMethodView.classList.add('has-errors');
        setHidden(paymentWarning, false);
      }
      function selectedProcessor() {
        for (var i = 0; i < processorInputs.length; i++) {
          if (processorInputs[i].checked) return processorInputs[i].value;
        }
        return null;
      }
      mainArea.appendChild(el('div', { 'class': 'js-payment-method-view' }, [paymentMethodView]));

      /* ---- 4. Gift opt-in ---- */
      var giftToggle = checkboxLabel('gifting-enabled', 'gifting-enabled', 'This purchase is a gift', 'js-gifting-enabled');
      var giftEmailInput = el('input', {
        type: 'text', id: 'gift-recipient-email-input', name: 'gift-recipient-email-input',
        'class': 'gift-recipient-email-input js-gift-recipient-email-input dark-text-input',
        placeholder: 'Gift Recipient Email Address',
        style: { display: 'block', width: '100%', maxWidth: '320px', padding: '6px', margin: '4px 0' }
      });
      var giftEmailError = el('span', {
        'class': 'gift-email-input-error js-gift-email-input-error',
        style: { color: '#c0392b', fontSize: '12px' },
        text: 'Please enter a correctly formatted email address'
      });
      setHidden(giftEmailError, true);
      var giftAnonymous = checkboxLabel('gift-recipient-anonymous', 'gift-anonymous', 'Make this gift anonymous', 'js-gift-recipient-anonymous');
      var giftByEmail = radioLabel('gift-recipient-email', 'gift-type', 'gift-recipient-email', 'Email Recipient', 'js-gift-recipient-email');
      var giftByLink = radioLabel('gift-recipient-link', 'gift-type', 'gift-recipient-link', 'Email Gift Link to Me', 'js-gift-recipient-link');
      var giftEmailContainer = el('div', { 'class': 'gift-recipient-email-container js-gift-recipient-email-container', style: { margin: '0 0 8px 20px' } }, [
        giftEmailInput, giftEmailError, giftAnonymous.label
      ]);
      var giftWrapper = el('div', { 'class': 'gift-recipient-wrapper js-gift-recipient-wrapper' }, [
        el('div', { 'class': 'gift-recipient-container js-gift-recipient-container' }, [
          giftByEmail.label, giftEmailContainer, giftByLink.label
        ])
      ]);
      setHidden(giftWrapper, true);
      function giftMode() {
        if (!giftToggle.input.checked) return 'none';
        return giftByLink.input.checked ? 'link' : 'email';
      }
      function syncGift() {
        setHidden(giftWrapper, !giftToggle.input.checked);
        if (giftToggle.input.checked && !giftByEmail.input.checked && !giftByLink.input.checked) {
          giftByEmail.input.checked = true;
        }
        setHidden(giftEmailContainer, giftToggle.input.checked && giftByLink.input.checked);
        setHidden(giftEmailError, true);
      }
      giftToggle.input.addEventListener('change', syncGift);
      giftByEmail.input.addEventListener('change', syncGift);
      giftByLink.input.addEventListener('change', syncGift);
      mainArea.appendChild(el('div', { 'class': 'common-view js-gift-view', style: { background: '#fff', border: '1px solid #c7cbd4', borderRadius: '3px', padding: '16px 18px', marginBottom: '16px' } }, [
        el('div', { 'class': 'gift-view common-contents' }, [giftToggle.label, giftWrapper])
      ]));

      /* ---- 5. Leaderboard opt-in ---- */
      var leaderToggle = checkboxLabel('leaderboard-inclusion', 'leaderboard', 'Include me in the Leaderboard', 'js-leaderboard-inclusion');
      var leaderName = el('input', {
        type: 'text', id: 'leaderboard-name', name: 'leaderboard-name', maxlength: '70',
        'class': 'js-leaderboard-name-input dark-text-input', placeholder: 'Leaderboard Name',
        disabled: 'disabled',
        style: { display: 'block', width: '100%', maxWidth: '320px', padding: '6px', margin: '4px 0' }
      });
      leaderToggle.input.addEventListener('change', function () {
        if (leaderToggle.input.checked) leaderName.removeAttribute('disabled');
        else { leaderName.setAttribute('disabled', 'disabled'); leaderName.value = ''; }
      });
      mainArea.appendChild(el('div', { 'class': 'common-view js-leaderboard-view', style: { background: '#fff', border: '1px solid #c7cbd4', borderRadius: '3px', padding: '16px 18px', marginBottom: '16px' } }, [
        el('div', { 'class': 'leaderboard-view common-contents' }, [
          leaderToggle.label,
          el('div', { 'class': 'leaderboard-input-wrapper js-leaderboard-input-wrapper' }, [
            el('div', { 'class': 'leaderboard-input-container' }, [
              leaderName,
              el('span', { 'class': 'leaderboard-warning', style: { fontSize: '12px' }, text: 'This name will be shared publicly' })
            ])
          ])
        ])
      ]));

      /* ---- 6. submit + demo-only sandbox outcome control ---- */
      var sandboxOverride = null;  /* null => use the processor's mapping */
      var sandboxBox = el('div', {
        'class': 'js-hb-sandbox-outcome',
        style: { background: '#fdf6e3', border: '1px dashed #c9b458', borderRadius: '3px', padding: '10px 12px', marginBottom: '12px' }
      }, [
        el('strong', { text: 'Offline sandbox control — demo only, not part of the source page' })
      ]);
      SANDBOX_OUTCOMES.forEach(function (pair, index) {
        var input = el('input', { type: 'radio', name: 'hb-scenario', value: pair[0] });
        if (index === 0) input.checked = true;  /* mirrors the processor mapping */
        input.addEventListener('change', function () { sandboxOverride = pair[0]; });
        sandboxBox.appendChild(el('label', { style: { display: 'block', margin: '4px 0', cursor: 'pointer' } }, [
          input, el('span', { style: { marginLeft: '6px' }, text: pair[1] })
        ]));
      });
      sandboxBox.appendChild(hintLine('Chooses the outcome of the locally simulated payment so the declined and '
        + 'retryable paths stay reachable. The real site has no such control.'));

      var errorBox = el('div', {
        'class': 'js-hb-checkout-error',
        style: { display: 'none', margin: '12px 0', padding: '10px', background: '#fbe3e4', color: '#8a1f11', borderRadius: '3px' }
      });
      var buttonText = el('span', { 'class': 'js-button-text', text: 'Continue to Payment' });
      var spinner = el('i', { 'class': 'hb hb-spinner hb-spin is-hidden js-submit-spinner', style: { display: 'none' } });
      /* js-hb-place-order is kept alongside the captured js-submit-button so
         the recorded clone-walk selector keeps resolving. */
      /* The source's submit stays enabled with no payment method chosen and
         answers a click with its own prompt; marking it aria-disabled made that
         captured state unreachable by a normal click. */
      var submit = el('button', {
        type: 'button', 'class': 'primary-button submit-button js-submit-button js-hb-place-order',
        style: { background: '#c00', color: '#fff', border: 'none', padding: '12px 34px', borderRadius: '3px', fontWeight: 'bold', cursor: 'pointer' }
      }, [buttonText, spinner]);
      var backLink = el('button', {
        type: 'button', 'class': 'back-to-link no-style-button text-button js-back-to-link cannot-disabled',
        style: { display: 'block', background: 'none', border: 'none', padding: '10px 0', color: '#494f5c', cursor: 'pointer' }
      }, [
        el('i', { 'class': 'hb hb-angle-left', 'aria-hidden': 'true' }),
        el('span', { 'class': 'back-to-link-message', style: { marginLeft: '6px' }, text: bundleItems.length ? 'Back to Bundle' : 'Back to Store' })
      ]);
      backLink.addEventListener('click', function () {
        location.href = bundleItems.length ? '/games/' + bundleItems[0].slug : '/store';
      });
      mainArea.appendChild(el('div', { 'class': 'js-payment-button-view' }, [
        el('div', { 'class': 'payment-button-view' }, [sandboxBox, errorBox, submit, backLink])
      ]));

      processorInputs.forEach(function (input) {
        input.addEventListener('change', clearPaymentWarning);
      });

      submit.addEventListener('click', function () {
        errorBox.style.display = 'none';
        setHidden(giftEmailError, true);
        var processor = selectedProcessor();
        if (!processor) { showPaymentWarning(); return; }  /* no-op until chosen */
        clearPaymentWarning();

        var mode = giftMode();
        var body = {
          scenario_id: sandboxOverride || processorScenario(processor),
          processor: processor,
          delivery_kind: mode === 'none' ? 'self' : 'gift',
          gift: { mode: mode, recipient: null, anonymous: !!giftAnonymous.input.checked }
        };
        if (mode === 'email') {
          var email = giftEmailInput.value.trim();
          if (!/^[^@\s]+@[^@\s]+$/.test(email)) { setHidden(giftEmailError, false); return; }
          body.gift.recipient = email;
        }
        if (leaderToggle.input.checked && leaderName.value.trim()) {
          body.leaderboard_name = leaderName.value.trim();
        }
        if (bundleItems.length) {
          body.splits = { mode: splitMode === 'extra-charity' ? 'extra-charity' : 'default' };
        }

        submit.disabled = true;
        setHidden(spinner, false);
        api('/api/checkout', { body: body }).then(function (r) {
          submit.disabled = false;
          setHidden(spinner, true);
          if (r.ok && r.data.placed) {
            refreshCart();
            renderConfirmation(host, r.data);
            return;
          }
          var msg = r.data.message || 'Checkout failed.';
          if (r.status === 402) msg += r.data.retryable ? ' You can try placing the order again.' : ' Choose a different payment option and try again.';
          errorBox.textContent = msg;
          errorBox.style.display = 'block';
        });
      });

      syncGift();
      renderSummary();
    });
  }

  function renderConfirmation(host, result) {
    var purchase = result.purchase || {};
    host.innerHTML = '';
    var panel = el('div', { 'class': 'js-hb-confirmation', style: { maxWidth: '760px', margin: '30px auto', padding: '24px', background: '#eff2fb', color: '#494f5c', borderRadius: '3px', boxShadow: '0 3px 8px rgba(0,0,0,0.2)' } });
    panel.appendChild(el('h1', { text: 'Thank you for your order!' }));
    panel.appendChild(el('p', {}, [
      document.createTextNode('Order number: '),
      el('strong', { 'class': 'js-hb-order-no', text: result.order_no || purchase.order_no || '' })
    ]));
    (purchase.items || []).forEach(function (item) {
      panel.appendChild(el('div', { style: { display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #c7cbd4' } }, [
        el('span', { text: item.human_name || item.name || item.slug }),
        el('span', { text: money(item.amount_minor) })
      ]));
    });
    /* Same quadruple the review's Order Summary showed, straight off the row. */
    panel.appendChild(summaryRow('Subtotal', purchase.subtotal_minor || purchase.total_minor || 0, ''));
    panel.appendChild(summaryRow(purchase.tax_label || 'HST', purchase.tax_minor || 0, 'tax-info'));
    panel.appendChild(summaryRow('Total', purchase.charged_minor || purchase.grand_total_minor || 0, 'total'));
    if (purchase.charity_minor && purchase.charity_name) {
      panel.appendChild(el('div', { 'class': 'split-callout js-split-callout', style: { background: '#e8f4ea', border: '1px solid #b7d9bf', borderRadius: '3px', padding: '10px 12px', margin: '12px 0' } }, [
        el('strong', { text: "You're Supporting Charity" }),
        el('p', { style: { margin: '4px 0 0' }, text: money(purchase.charity_minor) + ' of your order supports ' + purchase.charity_name + '. Thank you!' })
      ]));
    }
    if (purchase.gift_mode && purchase.gift_mode !== 'none') {
      panel.appendChild(el('p', {
        'class': 'fine-print',
        text: purchase.gift_mode === 'link'
          ? 'Gift: the gift link was emailed to you.'
          : 'Gift sent to ' + (purchase.gift_email || '') + (purchase.gift_anonymous ? ' (anonymous)' : '')
      }));
    }
    if (purchase.leaderboard_name) {
      panel.appendChild(el('p', { 'class': 'fine-print', text: 'Leaderboard name: ' + purchase.leaderboard_name }));
    }
    var keys = purchase.keys || [];
    if (keys.length) {
      var teaser = keys.slice(0, 3).map(function (k) { return k.human_name; }).join(', ');
      if (keys.length > 3) teaser += ' and ' + (keys.length - 3) + ' more';
      panel.appendChild(el('p', { 'class': 'fine-print', text: 'Keys ready to reveal: ' + teaser }));
    }
    panel.appendChild(el('a', { href: '/home/library', style: { display: 'inline-block', background: '#c00', color: '#fff', padding: '10px 26px', borderRadius: '3px', textDecoration: 'none', fontWeight: 'bold' }, text: 'View in Library' }));
    host.appendChild(panel);
  }

  /* ---------- login (/login) ---------- */

  function loginPage() {
    var wrapper = qs('.js-login-form');
    if (!wrapper) return;
    var viewBody = qs('.js-view-body', wrapper) || wrapper;
    var form = qs('form[action="/processlogin"]', wrapper);
    if (form) {
      var status = qs('.js-status-message', form);
      form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var email = (qs('input[name="username"]', form) || {}).value || '';
        var password = (qs('input[name="password"]', form) || {}).value || '';
        api('/api/account/login', { body: { email: email.trim(), password: password } }).then(function (r) {
          if (r.ok && r.data.authenticated) { location.href = safeGoto('/'); return; }
          if (status) status.textContent = r.data.message || 'credentials are invalid';
        });
      });
    }
    var resetBtn = qs('.js-password-reset', wrapper);
    if (resetBtn) resetBtn.addEventListener('click', function () { renderPasswordReset(viewBody); });
    wireSsoNotice(wrapper);
  }

  function ssoNoticeText() {
    return 'Third-party sign-in is not available in this offline demo — use email and password.';
  }
  function wireSsoNotice(wrapper) {
    qsa('.js-google-ssi, .js-facebook-ssi', wrapper).forEach(function (btn) {
      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        var options = btn.parentNode;
        if (!qs('.js-hb-sso-notice', options)) {
          options.appendChild(el('p', { 'class': 'js-hb-sso-notice fine-print', style: { marginTop: '8px' }, text: ssoNoticeText() }));
        }
      });
    });
  }

  function fieldWrapper(name, input) {
    return el('div', { 'class': 'js-field-wrapper field-wrapper', 'data-name': name }, [
      el('div', { 'class': 'input-field-container' }, [input]),
      el('div', { 'class': 'js-input-error input-status' })
    ]);
  }

  function sandboxHint(code) {
    /* sandbox_code stands in for the source's email delivery */
    return el('p', { 'class': 'fine-print js-hb-sandbox-hint', style: { marginTop: '8px' }, text: code ? ('Sandbox demo — your code is ' + code + '.') : 'Sandbox demo — check the local mail log for your code.' });
  }

  function renderPasswordReset(viewBody) {
    /* captured in-page Password Reset state (no standalone recovery URL) */
    var email = el('input', { type: 'email', name: 'email', 'class': 'text-input', placeholder: 'Email', 'aria-label': 'Email' });
    var status = el('div', { 'class': 'status-message js-status-message' });
    var submit = el('button', { type: 'submit', 'class': 'flat-cta-button blue no-style-button', text: 'RESET PASSWORD' });
    var form = el('form', {}, [fieldWrapper('email', email), status, submit]);
    var panel = el('div', { 'class': 'login-form-view' }, [
      el('section', { 'class': 'primary-section' }, [
        el('h1', { 'class': 'header', text: 'Password Reset' }),
        el('p', { text: "We'll send a password setup link to your account's email address." }),
        form
      ]),
      el('section', { 'class': 'footer-section' }, [
        el('a', { href: '/support', 'class': 'flat-cta-button white', text: 'Contact Support' })
      ])
    ]);
    viewBody.innerHTML = '';
    viewBody.appendChild(panel);

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      api('/api/account/password-reset/start', { body: { email: email.value.trim() } }).then(function (r) {
        if (!r.ok) { status.textContent = r.data.message || 'Could not start the reset.'; return; }
        renderPasswordResetComplete(viewBody, r.data.sandbox_code);
      });
    });
  }

  function renderPasswordResetComplete(viewBody, code) {
    var codeInput = el('input', { type: 'text', name: 'code', 'class': 'text-input', placeholder: 'Reset code', 'aria-label': 'Reset code' });
    var passInput = el('input', { type: 'password', name: 'new_password', 'class': 'text-input', placeholder: 'New password (at least 8 characters required)', 'aria-label': 'New password' });
    var status = el('div', { 'class': 'status-message js-status-message' });
    var form = el('form', {}, [
      fieldWrapper('code', codeInput), fieldWrapper('new_password', passInput), status,
      el('button', { type: 'submit', 'class': 'flat-cta-button blue no-style-button', text: 'SET NEW PASSWORD' })
    ]);
    viewBody.innerHTML = '';
    viewBody.appendChild(el('div', { 'class': 'login-form-view' }, [
      el('section', { 'class': 'primary-section' }, [
        el('h1', { 'class': 'header', text: 'Password Reset' }),
        el('p', { text: 'Enter the code from your email and choose a new password.' }),
        sandboxHint(code),
        form
      ])
    ]));
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      if ((passInput.value || '').length < 8) { status.textContent = 'Password must be at least 8 characters.'; return; }
      api('/api/account/password-reset/complete', { body: { code: codeInput.value.trim(), new_password: passInput.value } }).then(function (r) {
        if (r.ok && r.data.authenticated) { location.href = safeGoto('/'); return; }
        status.textContent = r.data.message || 'Could not complete the reset.';
      });
    });
  }

  /* ---------- signup (/signup) ---------- */

  function signupPage() {
    var wrapper = qs('.js-signup-form');
    if (!wrapper) return;
    var viewBody = qs('.js-view-body', wrapper) || wrapper;
    var form = qs('form[action="/signup"]', wrapper);
    if (form) {
      var status = qs('.js-status-message', form);
      form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var email = (qs('input[name="email"]', form) || {}).value || '';
        var password = (qs('input[name="password"]', form) || {}).value || '';
        var passError = qs('.js-field-wrapper[data-name="password"] .js-input-error', form);
        if (passError) { passError.textContent = ''; passError.style.removeProperty('display'); }
        if (status) status.textContent = '';
        if (password.length < 8) { /* mirrors the placeholder copy */
          var message = 'Password must be at least 8 characters.';
          if (passError) {
            passError.textContent = message;
            /* the frozen stylesheet hides this slot until the site's own
               error class is applied, so make the message observable */
            passError.style.display = 'block';
          }
          if (status) status.textContent = message;
          return;
        }
        api('/api/account/register/start', { body: { email: email.trim(), password: password, display_name: email.trim() } }).then(function (r) {
          if (!r.ok) { if (status) status.textContent = r.data.message || 'Could not create the account.'; return; }
          renderVerifyStep(viewBody, r.data.sandbox_code);
        });
      });
    }
    wireSsoNotice(wrapper);
  }

  function renderVerifyStep(viewBody, code) {
    var codeInput = el('input', { type: 'text', name: 'code', 'class': 'text-input', placeholder: 'Verification code', 'aria-label': 'Verification code' });
    var status = el('div', { 'class': 'status-message js-status-message' });
    var form = el('form', {}, [
      fieldWrapper('code', codeInput), status,
      el('button', { type: 'submit', 'class': 'flat-cta-button blue no-style-button', text: 'Verify' })
    ]);
    viewBody.innerHTML = '';
    viewBody.appendChild(el('div', { 'class': 'signup-form-view' }, [
      el('section', { 'class': 'primary-section' }, [
        el('h1', { 'class': 'header', text: 'Verify your email' }),
        el('p', { text: 'Enter the verification code sent to your email address.' }),
        sandboxHint(code),
        form
      ])
    ]));
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      api('/api/account/register/complete', { body: { code: codeInput.value.trim() } }).then(function (r) {
        if (r.ok && r.data.authenticated) { location.href = '/'; return; }
        status.textContent = r.data.message || 'That code did not match.';
      });
    });
  }

  /* ---------- account surfaces (/home/*, /store/wishlist, /user/*) ---------- */
  /*
   * Layout, headings, control sets, column headers and empty-state copy come
   * from the authenticated handoff capture (walk tr-001):
   * source-auth-scratch/walk-671/{library,purchases,keys,coupons,wishlist,
   * wishlist-populated,user-settings}. The account walked there was brand new,
   * so every /home interior was observed EMPTY — the *rows* the controls act
   * on are this clone's own seeded history, which SEEDED_NOTE says on every
   * populated view (claim.unavailable.{library,purchases,keys}-interior).
   * The source serves /home/* as one shell holding all five js-*-holder
   * panels with every inactive one is-hidden; that shape is reproduced below.
   */

  var ACCOUNT_TABS = [
    ['purchases', 'Purchases', '/home/purchases', 'hb-tier js-purchases-icon purchases-icon'],
    ['library', 'Library', '/home/library', 'hb-library'],
    ['keys', 'Keys & Entitlements', '/home/keys', 'hb-key'],
    ['coupons', 'Coupons', '/home/coupons', 'hb-scissors']
  ];
  /* Observed headings (h1) per surface. */
  var ACCOUNT_HEADINGS = {
    library: 'Humble Library',
    purchases: 'Purchased Products',
    keys: 'Keys & Entitlements',
    coupons: 'Humble Coupons'
  };
  var ACCOUNT_HOLDER = {
    purchases: 'js-purchase-holder',
    library: 'js-library-holder',
    keys: 'js-key-manager-holder',
    coupons: 'js-coupon-holder'
  };
  var ACCOUNT_EMPTY = 'Nothing found';  /* .no-results copy on all three */
  var WISHLIST_EMPTY = 'Your wish list is empty.';
  var SEEDED_NOTE =
    'Seeded demo data — these rows are this offline clone’s own construction, ' +
    'not reproduced content. The source account was empty when it was walked, so only ' +
    'the surrounding layout and controls come from the capture.';
  var UNCAPTURED_NOTE =
    'Offline sandbox surface — the source route exists but its page was not captured, ' +
    'so this panel is built from the settings page’s own sections.';

  function accountHeading(tab) {
    return el('h1', { text: ACCOUNT_HEADINGS[tab] || tab });
  }
  function accountEmpty(text) {
    return el('div', {
      'class': 'no-results js-no-results',
      style: { display: 'block', padding: '18px 0' },
      text: text || ACCOUNT_EMPTY
    });
  }
  function seededNote() { return hintLine(SEEDED_NOTE); }

  /* nav.tabbar > a.tabbar-tab: four tabs, captured order and icons. The
     source's wishlist is a store page and carries no tabbar at all. */
  function accountTabbar(active) {
    var nav = el('nav', { 'class': 'tabbar', style: { display: 'flex', gap: '18px', borderBottom: '2px solid #c7cbd4', paddingBottom: '10px', marginBottom: '20px', flexWrap: 'wrap' } });
    ACCOUNT_TABS.forEach(function (entry) {
      var on = entry[0] === active;
      nav.appendChild(el('a', {
        'class': 'tabbar-tab' + (on ? ' tabbar-tab-is-active' : ''),
        href: entry[2],
        style: { textDecoration: 'none', fontWeight: on ? 'bold' : 'normal', color: on ? '#c00' : '#494f5c' }
      }, [el('i', { 'class': 'hb ' + entry[3] }), document.createTextNode(' ' + entry[1])]));
    });
    return nav;
  }

  /* .bottom-tab-shortcuts: the captured footer strip, "|"-separated. */
  function bottomTabShortcuts() {
    var wrap = el('div', { 'class': 'bottom-tab-shortcuts', style: { padding: '18px 0', color: '#6b7280' } });
    ACCOUNT_TABS.forEach(function (entry, i) {
      if (i) wrap.appendChild(document.createTextNode(' | '));
      wrap.appendChild(el('a', { href: entry[2], text: entry[1] }));
    });
    return wrap;
  }

  function labelledSelect(id, name, cls, labelText, options, selected) {
    var select = el('select', { id: id, name: name, 'class': cls });
    options.forEach(function (opt) {
      var option = el('option', { value: opt[0], text: opt[1] });
      if (opt[0] === selected) option.selected = true;
      select.appendChild(option);
    });
    return {
      node: el('div', { style: { display: 'inline-block', marginRight: '18px' } }, [
        el('label', { 'for': id, style: { marginRight: '6px' }, text: labelText }),
        select
      ]),
      select: select
    };
  }

  /* .search: input plus the captured clear + magnifier icons. */
  function searchControl(id, name, cls, onChange) {
    var input = el('input', { type: 'text', id: id, name: name, 'class': cls || '' });
    var clear = el('i', { 'class': 'hb hb-times-circle clear-search js-clear-search', style: { cursor: 'pointer', marginLeft: '6px' } });
    clear.addEventListener('click', function () { input.value = ''; onChange(); });
    input.addEventListener('input', debounce(onChange, 200));
    input.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { ev.preventDefault(); onChange(); } });
    return {
      node: el('div', { 'class': 'search', style: { display: 'inline-block' } }, [
        input, clear, el('i', { 'class': 'hb hb-search' })
      ]),
      input: input
    };
  }

  function matchesQuery(text, query) {
    return !query || String(text || '').toLowerCase().indexOf(query.toLowerCase()) >= 0;
  }
  function byName(a, b) {
    return String(a || '').toLowerCase().localeCompare(String(b || '').toLowerCase());
  }

  function accountPanels() {
    /* the account panels ride the served home shell, except the wishlist which
       the source serves as a store page (handoff tr-001) */
    var onStoreWishlist = path === '/store/wishlist';
    if (!onStoreWishlist && !qs('.js-humble-home') && !qs('.humble-home-main')) return;
    var host = qs('.inner-main-wrapper') || qs('.base-main-wrapper');
    if (!host) return;
    clearFrozenOverlays();

    if (onStoreWishlist) {
      host.innerHTML = '';
      document.title = 'The Humble Store';
      var wishHost = el('div', { 'class': 'container js-hb-account', style: { maxWidth: '960px', margin: '30px auto', padding: '0 16px 40px', color: '#494f5c' } });
      host.appendChild(wishHost);
      renderWishlist(wishHost);
      return;
    }

    if (path === '/user/settings' || path === '/user/wallet') {
      host.innerHTML = '';
      var settingsHost = el('main', { 'class': 'js-user-settings-main js-hb-account', style: { maxWidth: '960px', margin: '30px auto', padding: '0 16px 40px', color: '#494f5c' } });
      host.appendChild(settingsHost);
      if (path === '/user/wallet') renderWalletPage(settingsHost);
      else renderUserSettings(settingsHost);
      return;
    }

    var tab = (path.split('/')[2] || 'library').toLowerCase();
    if (!ACCOUNT_HOLDER[tab]) tab = 'library';
    document.title = (ACCOUNT_HEADINGS[tab] || tab) + ' | Humble Bundle';

    host.innerHTML = '';
    var panel = el('div', { 'class': 'js-hb-account', style: { maxWidth: '960px', margin: '30px auto', padding: '0 16px 40px', color: '#494f5c' } });
    panel.appendChild(accountTabbar(tab));

    /* the captured shell keeps every holder in the DOM, inactive ones hidden */
    var holders = {};
    ['js-purchase-holder', 'js-library-holder', 'js-claimed-orders-holder', 'js-key-manager-holder', 'js-coupon-holder'].forEach(function (cls) {
      var active = cls === ACCOUNT_HOLDER[tab];
      var holder = el('div', { 'class': cls + ' js-holder' + (active ? '' : ' is-hidden'), style: active ? {} : { display: 'none' } });
      holders[cls] = holder;
      panel.appendChild(holder);
    });
    panel.appendChild(bottomTabShortcuts());
    host.appendChild(panel);

    /* the coupon holder carries its content on every tab in the capture */
    renderCoupons(holders['js-coupon-holder']);
    var content = holders[ACCOUNT_HOLDER[tab]];
    if (tab === 'library') renderLibrary(content);
    else if (tab === 'purchases') renderPurchases(content);
    else if (tab === 'keys') renderKeys(content);
  }

  function keyRevealControl(orderNo, machineName, existingCode, onRevealed) {
    var codeBox = el('code', { style: { display: existingCode ? 'inline-block' : 'none', background: '#2d2f36', color: '#8be28b', padding: '4px 10px', borderRadius: '3px' }, text: existingCode || '' });
    var btn = el('button', { type: 'button', style: { display: existingCode ? 'none' : 'inline-block', background: '#c00', color: '#fff', border: 'none', padding: '6px 14px', borderRadius: '3px', cursor: 'pointer' }, text: 'Reveal key' });
    btn.addEventListener('click', function () {
      api('/api/purchase/' + encodeURIComponent(orderNo) + '/reveal-key', { body: { machine_name: machineName } }).then(function (r) {
        if (r.ok && r.data.key) {
          codeBox.textContent = r.data.key;
          codeBox.style.display = 'inline-block';
          btn.style.display = 'none';
          if (onRevealed) onRevealed(r.data.key);
        } else btn.textContent = r.data.message || 'Unavailable';
      });
    });
    return el('span', {}, [btn, codeBox]);
  }

  /* ---- library (/home/library) ----
     Captured controls: Platform select (#switch-platform.js-platform),
     search (#search.js-search), Sort (#sort-order.js-sort-order:
     Alphabetical / Recently updated) and Download method
     (#download-method.js-download-method: BitTorrent / direct link), then
     .hb-download-list with .js-subproducts-holder and the
     .js-details-column / .js-details-holder detail pane. Selecting a row
     fills that pane — the "inspect downloads" surface. */
  function renderLibrary(content) {
    api('/api/library').then(function (r) {
      content.innerHTML = '';
      if (!r.ok) {
        content.appendChild(accountHeading('library'));
        content.appendChild(el('p', { text: r.data.message || 'Sign in to view your library.' }));
        return;
      }
      var items = r.data.library || [];
      var state = { search: '', platform: 'all', sort: 'human_name', method: 'direct' };

      var platforms = [];
      items.forEach(function (item) {
        (item.platforms || []).forEach(function (os) { if (platforms.indexOf(os) < 0) platforms.push(os); });
      });
      platforms.sort();

      var header = el('div', { 'class': 'header' });
      var titleRow = el('div', { 'class': 'container' }, [accountHeading('library')]);
      var filter = el('div', { 'class': 'filter' });
      var platformSel = labelledSelect('switch-platform', 'switch-platform', 'js-platform', 'Platform',
        [['all', 'all']].concat(platforms.map(function (os) { return [os, os]; })), 'all');
      var search = searchControl('search', 'search', 'js-search', function () { state.search = search.input.value.trim(); paint(); });
      filter.appendChild(el('div', { 'class': 'switch-platform js-platform-filter-holder', style: { display: 'inline-block' } }, [platformSel.node]));
      filter.appendChild(search.node);
      titleRow.appendChild(filter);
      header.appendChild(titleRow);
      header.appendChild(el('hr'));
      var sortSel = labelledSelect('sort-order', 'sort-order', 'js-sort-order', 'Sort',
        [['human_name', 'Alphabetical'], ['updated', 'Recently updated']], 'human_name');
      var methodSel = labelledSelect('download-method', 'download-method', 'js-download-method', 'Download method',
        [['bittorrent', 'BitTorrent'], ['direct', 'direct link']], 'direct');
      header.appendChild(el('div', { 'class': 'container' }, [
        el('div', { 'class': 'top-controls' }, [
          el('div', { 'class': 'switch-sort-order', style: { display: 'inline-block' } }, [sortSel.node]),
          el('div', { 'class': 'switch-download-method', style: { display: 'inline-block' } }, [methodSel.node])
        ])
      ]));
      content.appendChild(header);
      content.appendChild(seededNote());

      var noResults = accountEmpty();
      noResults.style.display = 'none';
      var rows = el('div', { 'class': 'column subproducts-holder js-subproducts-holder' });
      var details = el('div', { 'class': 'details-holder js-details-holder' });
      content.appendChild(el('div', { 'class': 'hb-download-list download-list', style: { display: 'flex', gap: '18px', flexWrap: 'wrap', alignItems: 'flex-start' } }, [
        el('div', { 'class': 'scrollbar-hider', style: { flex: '1 1 300px', minWidth: '280px' } }, [noResults, rows]),
        el('div', { 'class': 'column details-column js-details-column', style: { flex: '1 1 320px', minWidth: '300px' } }, [
          el('div', { 'class': 'js-scroll-follower scroll-follower' }, [details])
        ])
      ]));

      platformSel.select.addEventListener('change', function () { state.platform = platformSel.select.value; paint(); });
      sortSel.select.addEventListener('change', function () { state.sort = sortSel.select.value; paint(); });
      methodSel.select.addEventListener('change', function () { state.method = methodSel.select.value; if (selected) showDetails(selected); });

      var selected = null;
      function showDetails(item) {
        selected = item;
        details.innerHTML = '';
        details.appendChild(el('h2', { text: item.human_name }));
        details.appendChild(el('p', { 'class': 'fine-print', text: 'Order ' + item.order_no }));
        var os = (item.platforms || []);
        var drm = (item.delivery_methods || item.drm || []);
        if (drm.length || os.length) {
          details.appendChild(el('div', { 'class': 'platform-delivery-container' }, [
            el('ul', { 'class': 'platforms no-style-list', style: { display: 'inline-block', margin: '0 10px 0 0' } }, drm.map(function (d) {
              return el('li', { 'class': 'platform hb ' + drmIcon(d), title: d });
            })),
            el('ul', { 'class': 'operating-systems no-style-list', style: { display: 'inline-block' } }, os.map(function (o) {
              return el('li', { 'class': 'operating-system hb ' + osIcon(o), title: o });
            }))
          ]));
        }
        details.appendChild(el('p', {
          text: 'Delivery: ' + (drm.length ? drm.join(', ') : 'bundle entitlement') +
            ' · Download method: ' + (state.method === 'bittorrent' ? 'BitTorrent' : 'direct link')
        }));
        details.appendChild(el('div', { style: { margin: '10px 0' } }, [
          keyRevealControl(item.order_no, item.machine_name, null)
        ]));
        details.appendChild(hintLine(
          'Offline sandbox control — demo only, not part of the source page. No download ' +
          'payload exists in this clone: the ' + (state.method === 'bittorrent' ? 'BitTorrent' : 'direct link') +
          ' method selects how the source would deliver the file, and the redemption key above ' +
          'is a synthetic SANDBOX- code.'));
      }

      function paint() {
        var view = items.filter(function (item) {
          if (!matchesQuery(item.human_name, state.search)) return false;
          if (state.platform !== 'all' && (item.platforms || []).indexOf(state.platform) < 0) return false;
          return true;
        });
        view.sort(state.sort === 'updated'
          ? function (a, b) { return String(b.created_at || '').localeCompare(String(a.created_at || '')); }
          : function (a, b) { return byName(a.human_name, b.human_name); });
        rows.innerHTML = '';
        noResults.style.display = view.length ? 'none' : 'block';
        if (!view.length) { details.innerHTML = ''; selected = null; return; }
        view.forEach(function (item) {
          var row = el('a', {
            href: '#', 'class': 'js-hb-library-row',
            style: { display: 'block', padding: '12px', borderBottom: '1px solid #c7cbd4', textDecoration: 'none', color: 'inherit', background: '#fff' }
          }, [
            el('span', { style: { fontWeight: 'bold' }, text: item.human_name }),
            el('span', { 'class': 'fine-print', style: { display: 'block' }, text: 'Order ' + item.order_no })
          ]);
          row.addEventListener('click', function (ev) { ev.preventDefault(); showDetails(item); });
          rows.appendChild(row);
        });
        if (!selected || view.indexOf(selected) < 0) showDetails(view[0]);
      }
      paint();
    });
  }

  /* ---- purchases (/home/purchases) ----
     Captured controls: search (#purchase-search), Sort (#purchase-sort:
     Alphabetical / Most recent) and the .results heading columns
     Product / Date / Total. The Total column carries the charged total
     (what the order summary and the purchase detail both call Total), not
     the pre-tax subtotal. */
  function renderPurchases(content) {
    api('/api/purchases').then(function (r) {
      content.innerHTML = '';
      if (!r.ok) {
        content.appendChild(accountHeading('purchases'));
        content.appendChild(el('p', { text: r.data.message || 'Sign in to view your purchases.' }));
        return;
      }
      var purchases = r.data.purchases || [];
      var state = { search: '', sort: 'created' };

      var header = el('div', { 'class': 'header' });
      var titleRow = el('div', { 'class': 'container' }, [accountHeading('purchases')]);
      var search = searchControl('purchase-search', 'purchase-search', '', function () { state.search = search.input.value.trim(); paint(); });
      titleRow.appendChild(search.node);
      header.appendChild(titleRow);
      header.appendChild(el('hr'));
      var sortSel = labelledSelect('purchase-sort', 'purchase-sort', '', 'Sort',
        [['human_name', 'Alphabetical'], ['created', 'Most recent']], 'created');
      header.appendChild(el('div', { 'class': 'container' }, [el('div', { 'class': 'sort' }, [sortSel.node])]));
      content.appendChild(header);
      content.appendChild(seededNote());
      sortSel.select.addEventListener('change', function () { state.sort = sortSel.select.value; paint(); });

      var noResults = accountEmpty();
      noResults.style.display = 'none';
      content.appendChild(noResults);
      var results = el('div', { 'class': 'results js-results' });
      var body = el('div', { 'class': 'body' });
      results.appendChild(el('div', { 'class': 'heading', style: { display: 'flex', gap: '12px', fontWeight: 'bold', borderBottom: '2px solid #c7cbd4', padding: '8px 12px' } }, [
        el('div', { 'class': 'product-name', style: { flex: '2 1 40%' }, text: 'Product' }),
        el('div', { 'class': 'order-placed', style: { flex: '1 1 25%' }, text: 'Date' }),
        el('div', { 'class': 'total', style: { flex: '1 1 20%' }, text: 'Total' })
      ]));
      results.appendChild(body);
      content.appendChild(results);

      function label(purchase) {
        var items = purchase.items || [];
        if (!items.length) return purchase.order_no;
        return items.map(function (item) { return item.human_name || item.slug; }).join(', ');
      }
      function paint() {
        var view = purchases.filter(function (purchase) {
          return matchesQuery(label(purchase), state.search) ||
            matchesQuery(purchase.order_no, state.search);
        });
        view.sort(state.sort === 'human_name'
          ? function (a, b) { return byName(label(a), label(b)); }
          : function (a, b) { return String(b.created_at || '').localeCompare(String(a.created_at || '')); });
        body.innerHTML = '';
        noResults.style.display = view.length ? 'none' : 'block';
        results.style.display = view.length ? 'block' : 'none';
        view.forEach(function (purchase) {
          var row = el('a', { href: '#', style: { display: 'flex', gap: '12px', padding: '12px', borderBottom: '1px solid #c7cbd4', textDecoration: 'none', color: 'inherit' } }, [
            el('span', { 'class': 'product-name', style: { flex: '2 1 40%', fontWeight: 'bold' }, text: label(purchase) }),
            el('span', { 'class': 'order-placed', style: { flex: '1 1 25%' }, text: fmtDate(purchase.created_at) }),
            el('span', { 'class': 'total', style: { flex: '1 1 20%' }, text: money(purchase.charged_minor || purchase.total_minor || 0) })
          ]);
          row.addEventListener('click', function (ev) {
            ev.preventDefault();
            renderPurchaseDetail(content, purchase.order_no);
          });
          body.appendChild(row);
        });
      }
      paint();
    });
  }

  function renderPurchaseDetail(content, orderNo) {
    api('/api/purchase/' + encodeURIComponent(orderNo)).then(function (r) {
      if (!r.ok) return;
      var purchase = r.data;
      content.innerHTML = '';
      var back = el('a', { href: '#', text: '← All purchases', style: { display: 'inline-block', marginBottom: '12px' } });
      back.addEventListener('click', function (ev) { ev.preventDefault(); renderPurchases(content); });
      content.appendChild(back);
      content.appendChild(el('h1', { text: 'Order ' + purchase.order_no }));
      content.appendChild(el('p', { 'class': 'fine-print', text: fmtDate(purchase.created_at) + ' · ' + (purchase.status || '') + (purchase.delivery_kind === 'gift' ? ' · Gift' : '') }));
      content.appendChild(seededNote());
      (purchase.items || []).forEach(function (item) {
        content.appendChild(el('div', { style: { display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #c7cbd4' } }, [
          el('span', { text: item.human_name || item.name || item.slug }),
          el('span', { text: money(item.amount_minor) })
        ]));
      });
      content.appendChild(el('p', { style: { fontWeight: 'bold' }, text: 'Total: ' + money(purchase.charged_minor || purchase.total_minor || 0) }));
      var keys = purchase.keys || [];
      if (keys.length) {
        content.appendChild(el('h2', { text: 'Keys' }));
        keys.forEach(function (key) {
          content.appendChild(el('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', padding: '8px 0', borderBottom: '1px solid #e2e5ec' } }, [
            el('span', { text: key.human_name }),
            keyRevealControl(purchase.order_no, key.machine_name, key.revealed ? key.key_code : null)
          ]));
        });
      }
    });
  }

  /* ---- keys (/home/keys) ----
     Captured controls: search (#key-search.js-key-search), Sort
     (#key-sort.js-key-sort: Alphabetical / Most recent), the
     #hide-redeemed checkbox with its "Hide redeemed keys & entitlements"
     label, and table.unredeemed-keys-table whose headers are
     Type / Game / Key or Entitlement. */
  function renderKeys(content) {
    api('/api/purchases').then(function (r) {
      content.innerHTML = '';
      if (!r.ok) {
        content.appendChild(accountHeading('keys'));
        content.appendChild(el('p', { text: r.data.message || 'Sign in to view your keys.' }));
        return;
      }
      var rows = [];
      (r.data.purchases || []).forEach(function (purchase) {
        (purchase.keys || []).forEach(function (key) {
          rows.push({ order_no: purchase.order_no, created_at: purchase.created_at, key: key });
        });
      });
      var state = { search: '', sort: 'created', hideRedeemed: false };

      var header = el('div', { 'class': 'header' });
      var titleRow = el('div', { 'class': 'container' }, [accountHeading('keys')]);
      var search = searchControl('key-search', 'key-search', 'js-key-search', function () { state.search = search.input.value.trim(); paint(); });
      titleRow.appendChild(search.node);
      header.appendChild(titleRow);
      header.appendChild(el('hr'));
      var sortSel = labelledSelect('key-sort', 'key-sort', 'js-key-sort', 'Sort',
        [['gameName', 'Alphabetical'], ['created', 'Most recent']], 'created');
      var hide = el('input', { type: 'checkbox', name: 'hide-redeemed', id: 'hide-redeemed' });
      hide.addEventListener('change', function () { state.hideRedeemed = hide.checked; paint(); });
      header.appendChild(el('div', { 'class': 'container' }, [
        el('div', { 'class': 'sort' }, [
          sortSel.node, hide,
          el('label', { 'for': 'hide-redeemed', 'class': 'hide-redeemed-label', style: { marginLeft: '6px' }, text: 'Hide redeemed keys & entitlements' })
        ])
      ]));
      content.appendChild(header);
      content.appendChild(seededNote());
      sortSel.select.addEventListener('change', function () { state.sort = sortSel.select.value; paint(); });

      var noResults = accountEmpty();
      noResults.style.display = 'none';
      content.appendChild(noResults);
      var tbody = el('tbody');
      var table = el('div', { 'class': 'table-rounder js-results' }, [
        el('table', { 'class': 'unredeemed-keys-table', style: { width: '100%', borderCollapse: 'collapse' } }, [
          el('thead', {}, [el('tr', {}, [
            el('th', { 'class': 'platform', style: { textAlign: 'left', padding: '8px 12px', borderBottom: '2px solid #c7cbd4' }, text: 'Type' }),
            el('th', { 'class': 'game-name', style: { textAlign: 'left', padding: '8px 12px', borderBottom: '2px solid #c7cbd4' }, text: 'Game' }),
            el('th', { 'class': 'redeemer-cell', style: { textAlign: 'left', padding: '8px 12px', borderBottom: '2px solid #c7cbd4' }, text: 'Key or Entitlement' })
          ])]),
          tbody
        ])
      ]);
      content.appendChild(table);

      function paint() {
        var view = rows.filter(function (row) {
          if (state.hideRedeemed && row.key.revealed) return false;
          return matchesQuery(row.key.human_name, state.search) || matchesQuery(row.order_no, state.search);
        });
        view.sort(state.sort === 'gameName'
          ? function (a, b) { return byName(a.key.human_name, b.key.human_name); }
          : function (a, b) { return String(b.created_at || '').localeCompare(String(a.created_at || '')); });
        tbody.innerHTML = '';
        noResults.style.display = view.length ? 'none' : 'block';
        table.style.display = view.length ? 'block' : 'none';
        view.forEach(function (row) {
          var methods = row.key.delivery_methods || [];
          var type = el('td', { style: { padding: '10px 12px', borderBottom: '1px solid #c7cbd4' } });
          if (methods.length) {
            methods.forEach(function (d) { type.appendChild(el('i', { 'class': 'hb ' + drmIcon(d), title: d, style: { marginRight: '6px' } })); });
            type.appendChild(document.createTextNode(methods.join(', ')));
          } else type.appendChild(document.createTextNode('Bundle entitlement'));
          tbody.appendChild(el('tr', {}, [
            type,
            el('td', { style: { padding: '10px 12px', borderBottom: '1px solid #c7cbd4' } }, [
              el('span', { style: { fontWeight: 'bold' }, text: row.key.human_name }),
              el('span', { 'class': 'fine-print', style: { marginLeft: '8px' }, text: row.order_no })
            ]),
            el('td', { style: { padding: '10px 12px', borderBottom: '1px solid #c7cbd4' } }, [
              keyRevealControl(row.order_no, row.key.machine_name,
                row.key.revealed ? row.key.key_code : null,
                function (code) {
                  /* keep the local row in step so the hide-redeemed toggle
                     sees the new state without a refetch */
                  row.key.revealed = true;
                  row.key.key_code = code;
                  if (state.hideRedeemed) paint();
                })
            ])
          ]));
        });
      }
      paint();
    });
  }

  /* ---- wishlist (/store/wishlist) ----
     Captured header: span.wishlist-name "My Wish List" + the pencil icon,
     then span.wishlist-share with a checked input[name=share] and the
     mail / Facebook / Twitter share links for the public wishlist URL.
     Populated rows are full store entities inside
     ul.entities-list.js-entities-list > li.wishlist-entity, each with the
     saved wishlist button, platform + OS icon lists, the discount gem and
     its breakdown, the price button (price / Add / Buy) and the
     .wishlist-edit-actions remove control. The source's wishlist is a
     store page: it carries no account tab strip. */
  function wishlistShareUrl() {
    /* the source shares an absolute /store/wishlist/<id> URL; offline the
       only truthful destination is this origin's own wishlist route */
    return location.origin + '/store/wishlist';
  }

  function wishlistHeader() {
    var share = el('input', { type: 'checkbox', name: 'share' });
    share.checked = true;
    var social = el('span', { 'class': 'wishlist-share-social-media', style: { marginLeft: '10px' } });
    [['hb-envelope', 'mailto:?to=&subject=My Humble Store Wish List&body=' + encodeURIComponent(wishlistShareUrl())],
     ['hb-facebook', null], ['hb-twitter', null]].forEach(function (entry) {
      var link = el('a', { href: entry[1] || '#', style: { marginRight: '8px' } }, [el('i', { 'class': 'hb ' + entry[0] })]);
      if (!entry[1]) {
        link.addEventListener('click', function (ev) {
          ev.preventDefault();
          var note = qs('.js-hb-share-note', link.parentNode.parentNode);
          if (note) note.textContent = ssoNoticeText();
        });
      }
      social.appendChild(link);
    });
    return el('div', { 'class': 'wishlist-header-container' }, [
      el('div', { 'class': 'wishlist-header', style: { display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px', alignItems: 'center' } }, [
        el('span', { 'class': 'wishlist-name', style: { fontSize: '22px', fontWeight: 'bold' } }, [
          document.createTextNode('My Wish List '),
          el('i', { 'class': 'wishlist-edit-title hb hb-pencil' })
        ]),
        el('span', { 'class': 'wishlist-share' }, [
          el('label', {}, [document.createTextNode('Share Wish List '), share]),
          social
        ])
      ]),
      el('p', { 'class': 'fine-print js-hb-share-note', style: { margin: '4px 0 0', color: '#6b7280' } })
    ]);
  }

  function wishlistEntity(item, onRemove) {
    var img = firstMedia(item.media || {}, ['standard_carousel_image', 'featured_image_recommendation', 'large_capsule']);
    var pricing = el('div', { 'class': 'price-container' });
    if (item.discount_pct > 0) {
      pricing.appendChild(el('div', { 'class': 'js-discount-gem discount-gem-container' }, [
        el('div', { 'class': 'discount-gem-view' }, [
          el('div', { 'class': 'discount-gem' }, [
            el('div', { 'class': 'js-discount-amount discount-amount' }, [
              document.createTextNode('-' + item.discount_pct + '%'),
              el('span', { 'class': 'off-text', text: ' OFF' })
            ]),
            el('div', { 'class': 'discount-gem-tooltip' }, [
              el('div', { 'class': 'discount-gem-tooltip-header', text: 'Discount Breakdown' }),
              el('div', { 'class': 'breakdown-container' }, [
                el('div', { 'class': 'store-discount-percent' }, [
                  el('span', { 'class': 'store-discount', text: '-' + item.discount_pct + '%' }),
                  document.createTextNode(' Store Discount')
                ]),
                el('div', { 'class': 'store-discount-amount' }, [
                  el('span', { 'class': 'breakdown-full-price', text: money(item.full_price_minor) }),
                  el('span', { 'class': 'store-discounted-price', style: { marginLeft: '6px' }, text: money(item.current_price_minor) })
                ])
              ])
            ])
          ])
        ])
      ]));
    }
    var priceBtn = el('div', { 'class': 'price-button js-price-button' }, [
      el('button', { 'class': 'price price-inner-button', text: money(item.current_price_minor) }),
      el('i', { 'class': 'hb hb-shopping-cart-solid' }),
      el('button', { 'class': 'add-text price-inner-button', text: 'Add' }),
      el('button', { 'class': 'buy-text price-inner-button', text: 'Buy' })
    ]);
    priceBtn.addEventListener('click', function (ev) {
      ev.preventDefault();
      cartAddAndOpen('product', item.slug);
    });
    pricing.appendChild(priceBtn);

    var wishButton = el('div', { 'class': 'wishlist-button js-wishlist-button saved' }, [
      el('i', { 'class': 'hb hb-star' }),
      el('i', { 'class': 'hb hb-star-o' }),
      el('button', { 'class': 'add-text wishlist-inner-button', text: 'Save' }),
      el('button', { 'class': 'remove-text wishlist-inner-button', text: 'Saved' }),
      el('button', { 'class': 'remove-text-hover wishlist-inner-button', text: 'Saved' })
    ]);
    wishButton.addEventListener('click', function (ev) { ev.preventDefault(); onRemove(); });

    var remove = el('span', { 'class': 'remove-wishlist', 'data-entity-key': item.machine_name || item.slug, style: { cursor: 'pointer' } }, [
      el('i', { 'class': 'hb hb-close' })
    ]);
    remove.addEventListener('click', function () { onRemove(); });

    return el('li', { 'class': 'wishlist-entity', 'data-entity-index-key': item.slug }, [
      el('div', { 'class': 'entity-block-container js-entity-container', 'data-entity-key': item.machine_name || item.slug }, [
        el('div', {}, [
          el('div', { 'class': 'entity js-entity' + (item.discount_pct > 0 ? ' on-sale' : '') }, [
            el('a', { 'class': 'entity-link js-entity-link', href: '/store/' + item.slug, 'aria-label': item.human_name }, [
              el('div', { 'class': 'entity-details' }, [
                img ? el('img', { 'class': 'entity-image', src: img, alt: item.human_name }) : null,
                el('div', { 'class': 'entity-meta' }, [
                  el('span', { 'class': 'entity-title', text: item.human_name }),
                  el('div', { 'class': 'js-wishlist-button-container' }, [
                    el('div', { 'class': 'wishlist-button-view' }, [wishButton])
                  ])
                ])
              ])
            ]),
            el('div', { 'class': 'entity-purchase-details' }, [
              el('div', { 'class': 'entity-devices js-platform-delivery-container' }, [
                el('div', { 'class': 'platform-delivery-container' }, [
                  el('ul', { 'class': 'platforms no-style-list' }, (item.drm || []).map(function (d) {
                    return el('li', { 'class': 'platform hb ' + drmIcon(d), title: d });
                  })),
                  el('ul', { 'class': 'operating-systems no-style-list' }, (item.platforms || []).map(function (os) {
                    return el('li', { 'class': 'operating-system hb ' + osIcon(os), title: os });
                  }))
                ])
              ]),
              el('div', { 'class': 'entity-pricing js-price-container' }, [pricing])
            ])
          ])
        ])
      ]),
      el('div', { 'class': 'wishlist-edit-actions' }, [
        remove,
        el('span', { 'class': 'move-wishlist' }, [el('i', { 'class': 'hb hb-arrows', 'aria-hidden': 'true' })])
      ])
    ]);
  }

  function renderWishlist(content) {
    api('/api/wishlist').then(function (r) {
      content.innerHTML = '';
      content.appendChild(wishlistHeader());
      if (!r.ok) {
        content.appendChild(el('p', { text: r.data.message || 'Sign in to view your wishlist.' }));
        return;
      }
      var items = r.data.wishlist || [];
      var list = el('div', { 'class': 'wishlist-item-list' });
      content.appendChild(el('div', { 'class': 'wishlist-item-container' }, [list]));
      if (!items.length) {
        list.appendChild(el('div', {}, [
          el('div', { 'class': 'empty-wishlist' }, [el('h2', { text: WISHLIST_EMPTY })])
        ]));
        return;
      }
      var ul = el('ul', { 'class': 'entities-list js-entities-list no-style-list' });
      list.appendChild(el('div', { 'class': 'list-content js-list-content show-status-container' }, [el('div', {}, [ul])]));
      items.forEach(function (item) {
        var li = wishlistEntity(item, function () {
          api('/api/wishlist/remove', { body: { slug: item.slug } }).then(function (r2) {
            if (r2.ok && li.parentNode) {
              li.parentNode.removeChild(li);
              if (!qs('.wishlist-entity', ul)) renderWishlist(content);
            }
          });
        });
        ul.appendChild(li);
      });
    });
  }

  /* Coupons: observed empty state on /home/coupons (new account). */
  function renderCoupons(content) {
    content.innerHTML = '';
    content.appendChild(accountHeading('coupons'));
    content.appendChild(el('p', { text: 'You do not have any coupons.' }));
    content.appendChild(el('p', {}, [
      el('a', { href: '/support', text: 'Learn more about coupons' })
    ]));
  }

  /* ---- /user/settings ----
     Section order, headings and control set from
     source-auth-scratch/walk-671/user-settings: Account Information
     (Email Address + Update, Location, Language), Humble Choice, Charity
     Contribution (Total Donated, Your Contribution + Calculate
     Contribution, Charity Preference + Update), Payment Information
     (Saved Payments, Billing history, Add credit card, Add PayPal),
     Humble Wallet, Contact Preferences (ten subscription checkboxes +
     Update) and Linked Accounts. The captured Security section is
     deliberately not reproduced: its controls change the sign-in
     credential, which the vendored auth seam does not expose. */
  function settingsSection(headingText, articles) {
    var section = el('section', { 'class': 'settings-section', style: { margin: '0 0 26px' } });
    articles.forEach(function (article) { if (article) section.appendChild(article); });
    return el('div', {}, [el('h2', { text: headingText, style: { margin: '26px 0 10px' } }), section]);
  }
  function settingsArticle(headingText, children) {
    return el('article', { 'class': 'settings-subsection', style: { margin: '0 0 16px' } }, [
      el('h3', { text: headingText, style: { margin: '0 0 6px', fontSize: '16px' } }),
      el('div', { 'class': 'subsection-content' }, children)
    ]);
  }
  function primaryButton(text) {
    return el('button', { type: 'button', 'class': 'primary-button js-submit', style: { background: '#c00', color: '#fff', border: 'none', padding: '7px 16px', borderRadius: '3px', cursor: 'pointer' }, text: text });
  }

  function walletArticle(wallet) {
    return settingsArticle('Humble Wallet', [
      document.createTextNode('Wallet Currency: ' + wallet.currency), el('br'),
      document.createTextNode('Wallet Funds: ' + money(wallet.funds_minor)), el('br'),
      document.createTextNode('Expiring Wallet Credit: ' + money(wallet.expiring_minor)), el('br'), el('br'),
      hintLine('Offline sandbox surface — the wallet held ' + money(wallet.funds_minor) +
        ' when the account was walked and this clone has no funding path, so Add Funds is not offered.')
    ]);
  }

  function renderUserSettings(host) {
    document.title = 'Humble Bundle - User settings';
    api('/api/account/settings').then(function (r) {
      host.innerHTML = '';
      if (!r.ok) {
        host.appendChild(el('h2', { text: 'Account Information' }));
        host.appendChild(el('p', { text: r.data.message || 'Sign in to view your settings.' }));
        return;
      }
      var s = r.data;

      /* Account Information */
      var emailInput = el('input', { type: 'text', id: 'email', name: 'email', value: s.delivery_email, style: { minWidth: '260px', padding: '6px' } });
      var emailError = el('div', { 'class': 'js-email-error email-error', style: { color: '#c00', fontSize: '12px', minHeight: '16px' } });
      /* the captured control is <button type="submit" class="primary-button
         js-submit">Update</button>, so it must submit the form */
      var emailSubmit = primaryButton('Update');
      emailSubmit.type = 'submit';
      var emailForm = el('form', { 'class': 'js-user-info change-email', action: '/user/change-email', method: 'post' }, [
        el('div', { 'class': 'email-container' }, [emailInput, emailError]),
        emailSubmit
      ]);
      emailForm.addEventListener('submit', function (ev) {
        ev.preventDefault();
        emailError.textContent = '';
        api('/api/account/delivery-email', { body: { email: emailInput.value } }).then(function (res) {
          if (!res.ok) { emailError.textContent = res.data.message || 'Email address is not valid'; return; }
          emailInput.value = res.data.delivery_email;
          emailError.style.color = '#2f7a35';
          emailError.textContent = 'Delivery address updated to ' + res.data.delivery_email + '.';
        });
      });

      var account = settingsSection('Account Information', [
        settingsArticle('Email Address', [
          emailForm,
          hintLine('This is the delivery destination for a digital order: the checkout review ' +
            'sends the order here. It is a clone-side delivery address — the sign-in address ' +
            'stays ' + s.sign_in_email + ', because the vendored auth store owns the credential ' +
            'and exposes no email-change entry point.')
        ]),
        settingsArticle('Location', [
          el('div', { 'class': 'location-container' }, [
            el('div', { 'class': 'custom-select' }, [
              el('select', { 'class': 'js-change-location', disabled: 'disabled' }, [
                el('option', { value: 'CA', text: 'ON - Canada' })
              ])
            ])
          ]),
          el('p', { 'class': 'location-change-warning no-color', text: 'Your Location setting is already set to your current location.' })
        ]),
        settingsArticle('Language', [
          el('div', { 'class': 'custom-select' }, [
            el('select', { 'class': 'js-language-selector' }, [
              el('option', { value: 'fr', text: 'Français' }),
              el('option', { value: 'en', text: 'English', selected: 'selected' }),
              el('option', { value: 'zh_CN', text: '简体中文' }),
              el('option', { value: 'de', text: 'Deutsch' }),
              el('option', { value: 'it', text: 'Italiano' }),
              el('option', { value: 'es', text: 'Español' })
            ])
          ]),
          hintLine('Offline sandbox control — the clone serves the captured English locale only.')
        ])
      ]);
      host.appendChild(account);

      /* Humble Choice */
      host.appendChild(settingsSection('Humble Choice', [
        el('div', {}, [
          el('p', {}, [el('strong', {}, [el('i', { text: 'Currently not a member.' })]),
            document.createTextNode(' Join to get great games every month to keep forever.')]),
          el('a', { href: '/membership', 'class': 'primary-button', 'aria-label': 'Learn more about Humble Choice', text: 'Learn More' })
        ])
      ]));

      /* Charity Contribution */
      var contributionOut = el('p', { style: { margin: '6px 0 0' } });
      var calculate = primaryButton('Calculate Contribution');
      calculate.className = 'js-calculate-contribution primary-button';
      var charityValue = el('p', { text: s.charity_preference });
      var charityUpdate = primaryButton('Update');
      charityUpdate.className = 'js-open-charity-modal primary-button';
      var charityInput = el('input', { type: 'text', name: 'charity_preference', value: s.charity_preference, style: { padding: '6px', marginRight: '8px' } });
      charityUpdate.addEventListener('click', function () {
        api('/api/account/contact-prefs', { body: { charity_preference: charityInput.value } }).then(function (res) {
          if (res.ok) charityValue.textContent = res.data.charity_preference;
        });
      });
      calculate.addEventListener('click', function () {
        api('/api/purchases').then(function (res) {
          if (!res.ok) { contributionOut.textContent = 'Sign in to calculate your contribution.'; return; }
          var minor = 0;
          (res.data.purchases || []).forEach(function (p) { minor += p.charity_minor || 0; });
          contributionOut.textContent = 'Your orders in this clone have contributed ' + money(minor) + ' to charity.';
        });
      });
      host.appendChild(settingsSection('Charity Contribution', [
        settingsArticle('Total Donated', [
          el('p', { text: 'The Humble community has contributed ' + s.community_donated_display + ' to charity since 2010' })
        ]),
        settingsArticle('Your Contribution', [
          el('p', { text: 'Curious about your personal contribution?' }), calculate, contributionOut
        ]),
        settingsArticle('Charity Preference', [charityValue, charityInput, charityUpdate])
      ]));

      /* Payment Information */
      host.appendChild(settingsSection('Payment Information', [
        settingsArticle('Saved Payments', [
          el('ul', { 'class': 'js-cards-list section-content cards-list' }),
          el('p', { text: 'No saved payment methods.' }),
          hintLine('Offline sandbox surface — the source offers Billing history, Add credit card ' +
            'and Add PayPal here. This clone accepts no payment credentials at all ' +
            '(payments are local-sandbox scenarios only), so those controls are not reproduced.')
        ]),
        walletArticle(s.wallet)
      ]));

      /* Contact Preferences */
      var boxes = {};
      var holder = el('div', { id: 'subscribe-holder', 'class': 'subscribe-holder' });
      (s.subscription_fields || []).forEach(function (field) {
        var box = el('input', { 'class': 'subscription', type: 'checkbox', name: field.name, value: 'true' });
        box.checked = !!s.subscriptions[field.name];
        boxes[field.name] = box;
        holder.appendChild(el('label', { style: { display: 'block', margin: '4px 0' } }, [
          box, el('p', { style: { display: 'inline', margin: '0 0 0 6px' }, text: field.label })
        ]));
      });
      var prefsStatus = el('p', { 'class': 'fine-print js-hb-prefs-status', style: { minHeight: '16px', color: '#2f7a35' } });
      var prefsSubmit = primaryButton('Update');
      prefsSubmit.addEventListener('click', function (ev) {
        ev.preventDefault();
        var payload = {};
        Object.keys(boxes).forEach(function (name) { payload[name] = boxes[name].checked; });
        api('/api/account/contact-prefs', { body: { subscriptions: payload } }).then(function (res) {
          prefsStatus.textContent = res.ok ? 'Contact preferences saved.' : (res.data.message || 'Could not save.');
        });
      });
      var prefsForm = el('form', { 'class': 'js-user-info', action: '/user/email-subscriptions', method: 'post' }, [
        el('input', { type: 'hidden', name: 'set_list_subscriptions', value: 'true' }),
        holder, prefsSubmit, prefsStatus
      ]);
      prefsForm.addEventListener('submit', function (ev) { ev.preventDefault(); prefsSubmit.click(); });
      host.appendChild(settingsSection('Contact Preferences', [settingsArticle('Email', [prefsForm])]));

      /* Linked Accounts */
      function linkArticle(name) {
        var btn = el('button', { type: 'button', 'class': 'no-style-button', style: { background: 'none', border: 'none', color: '#2f6fb3', cursor: 'pointer', padding: '0' }, text: 'Link ' + name + ' account' });
        var note = el('p', { 'class': 'fine-print', style: { margin: '4px 0 0', color: '#6b7280' } });
        btn.addEventListener('click', function () { note.textContent = ssoNoticeText(); });
        return settingsArticle(name, [btn, note]);
      }
      host.appendChild(settingsSection('Linked Accounts', [
        linkArticle('Steam'), linkArticle('Battle.net'), linkArticle('Epic Games'), linkArticle('GOG')
      ]));
    });
  }

  /* ---- /user/wallet ----
     The route is directly observed (it is in the captured account dropdown
     and the store sub-nav) but its page was never captured, so the panel
     reproduces the settings page's own Humble Wallet subsection and says so.
     claim.unavailable.wallet-interior. */
  function renderWalletPage(host) {
    document.title = 'Humble Wallet | Humble Bundle';
    api('/api/account/settings').then(function (r) {
      host.innerHTML = '';
      host.appendChild(el('h1', { text: 'Humble Wallet' }));
      if (!r.ok) {
        host.appendChild(el('p', { text: r.data.message || 'Sign in to view your wallet.' }));
        return;
      }
      host.appendChild(hintLine(UNCAPTURED_NOTE));
      host.appendChild(el('section', { 'class': 'settings-section' }, [walletArticle(r.data.wallet)]));
      host.appendChild(el('p', {}, [el('a', { href: '/user/settings', text: 'All account settings' })]));
    });
  }

  /* nav dropdown panels: the frozen pages carry the full .nav-dropdown-container
     DOM (trigger + panel) but the site's hover toggle lived in stripped JS.
     Source evidence: interactive/nav-store-dropdown (open panel display:block). */
  function wireNavDropdowns() {
    qsa('.nav-dropdown-container').forEach(function (container) {
      var panel = qs('.navbar-item-dropdown-container, .nav-dropdown', container);
      if (!panel) return;
      var hideTimer = null;
      container.addEventListener('mouseenter', function () {
        if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
        panel.style.display = 'block';
      });
      container.addEventListener('mouseleave', function () {
        hideTimer = setTimeout(function () { panel.style.display = 'none'; }, 120);
      });
    });
    qsa('.language-dropdown-container').forEach(function (container) {
      var panel = qs('.navbar-item-dropdown-container, .nav-dropdown, ul', container);
      if (!panel) return;
      var trigger = qs('button, .dropdown-button', container) || container;
      trigger.addEventListener('click', function (ev) {
        ev.preventDefault();
        panel.style.display = (getComputedStyle(panel).display === 'none') ? 'block' : 'none';
      });
      document.addEventListener('click', function (ev) {
        if (!container.contains(ev.target)) panel.style.display = 'none';
      });
    });
  }


  /* Countdown badges.

     The clone's "now" is the capture instant, exactly as every price, listing
     and tier in it is. So the timers are anchored to the remaining time the
     source itself rendered into the frozen markup and run forward from page
     load, rather than being recomputed against absolute wall-clock end dates:
     an absolute reading would drift a day per day and pin every already-passed
     bundle at 00:00:00:00, which is what this replaces.

     Two markup families were captured, both handled here:

     * pill + full pair (home, /bundles, /games) — a `.js-countdown-view`
       holding a black `.js-simple-countdown-timer` reading "N Days Left" and a
       red `.js-countdown-timer` reading D:H:M:S, exactly one of them visible.
     * blocky (/store) — a `.timer.blocky-timer` of
       `.js-countdown-timer-counter[data-unit]` cells.

     Swap rule for the pair: the source showed the red timer for every tile
     with at most 1d19h23m left and the pill for every tile from 3d19h23m up,
     so it swaps on the day field reaching 1 — i.e. under 48h. No tile in the
     capture sat between those two, so the exact cutoff is bounded, not
     observed; recorded as inferred in scope/claims.jsonl. */
  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  function splitRemaining(total) {
    var left = Math.max(0, Math.floor(total));
    return {
      total: left,
      days: Math.floor(left / 86400),
      hours: Math.floor(left % 86400 / 3600),
      minutes: Math.floor(left % 3600 / 60),
      seconds: left % 60
    };
  }

  /* "N Days Left" is the only day-granularity label the capture contains; the
     swap rule keeps the pill off screen below 2 days, so no singular form is
     ever needed and none is invented here. */
  function daysLeftLabel(days) { return days + ' Days Left'; }

  function readPairSeconds(view) {
    var full = qs('.js-countdown-timer', view);
    if (!full) return null;
    var num = function (sel) {
      var node = qs(sel, full);
      var parsed = node ? parseInt((node.textContent || '').trim(), 10) : NaN;
      return isNaN(parsed) ? 0 : parsed;
    };
    /* the full timer's day field carries the numeric value only while it is
       the visible one; while hidden it keeps the pill's "N Days Left" text, so
       fall back to parsing that (both forms start with the number). */
    var days = num('.js-days');
    if (!days) {
      var pill = qs('.js-simple-countdown-timer .js-days', view);
      var m = pill ? (pill.textContent || '').match(/(\d+)/) : null;
      if (m) days = parseInt(m[1], 10);
    }
    return days * 86400 + num('.js-hours') * 3600 + num('.js-minutes') * 60 + num('.js-seconds');
  }

  function renderPair(view, rem) {
    var pill = qs('.js-simple-countdown-timer', view);
    var full = qs('.js-countdown-timer', view);
    var showFull = rem.days <= 1;
    if (pill) pill.classList[showFull ? 'add' : 'remove']('is-hidden');
    if (full) full.classList[showFull ? 'remove' : 'add']('is-hidden');

    var label = daysLeftLabel(rem.days);
    if (pill) {
      var pillDays = qs('.js-days', pill);
      if (pillDays) pillDays.textContent = label;
    }
    var holder = qs('.timer[data-countdown]', view);
    if (holder) holder.setAttribute('data-countdown', label);

    if (!full) return;
    var write = function (sel, value) {
      var node = qs(sel, full);
      if (node) node.textContent = value;
    };
    write('.js-days', showFull ? pad2(rem.days) : label);
    write('.js-hours', pad2(rem.hours));
    write('.js-minutes', pad2(rem.minutes));
    write('.js-seconds', pad2(rem.seconds));
    /* only the tiles whose aria-label is a time phrase get it refreshed; on
       /bundles the same attribute carries the bundle name instead. */
    var aria = full.getAttribute('aria-label') || '';
    if (/\d+\s+days?,/.test(aria)) {
      full.setAttribute('aria-label', rem.days + ' days, ' + rem.hours + ' hours, ' +
        rem.minutes + ' minutes, and ' + rem.seconds + ' seconds left');
    }
  }

  function readBlockySeconds(timer) {
    var unit = function (name) {
      var cell = qs('.js-countdown-timer-counter[data-unit="' + name + '"] .js-countdown-timer-number', timer);
      var parsed = cell ? parseInt((cell.textContent || '').trim(), 10) : NaN;
      return isNaN(parsed) ? 0 : parsed;
    };
    return unit('days') * 86400 + unit('hours') * 3600 + unit('minutes') * 60 + unit('seconds');
  }

  function renderBlocky(timer, rem) {
    var write = function (name, value) {
      var cell = qs('.js-countdown-timer-counter[data-unit="' + name + '"] .js-countdown-timer-number', timer);
      if (cell) cell.textContent = value;
    };
    /* the capture prints these unpadded (13 / 18 / 22 / 52) */
    write('days', String(rem.days));
    write('hours', String(rem.hours));
    write('minutes', String(rem.minutes));
    write('seconds', String(rem.seconds));
  }

  function wireListingCountdowns() {
    var bound = [];
    qsa('.js-countdown-view').forEach(function (view) {
      var start = readPairSeconds(view);
      if (start === null || start <= 0) return;
      bound.push({ start: start, render: function (rem) { renderPair(view, rem); } });
    });
    qsa('.timer.blocky-timer').forEach(function (timer) {
      var start = readBlockySeconds(timer);
      if (start <= 0) return;
      bound.push({ start: start, render: function (rem) { renderBlocky(timer, rem); } });
    });
    if (!bound.length) return;

    var anchor = Date.now();
    function tick() {
      var elapsed = Math.floor((Date.now() - anchor) / 1000);
      bound.forEach(function (b) { b.render(splitRemaining(b.start - elapsed)); });
    }
    tick();
    setInterval(tick, 1000);
  }

  /* frozen slick carousels: arrows shift the visible track one slide per
     click. Delegated so late-swapped (mobile fixup) tracks work too. */
  function wireSlickArrows() {
    var state = new WeakMap();
    document.addEventListener('click', function (ev) {
      var arrow = ev.target && ev.target.closest ? ev.target.closest('.js-slick-prev, .js-slick-next, .slick-prev, .slick-next, .games-nav-left, .games-nav-right') : null;
      if (!arrow) return;
      var holder = arrow.parentElement;
      while (holder && holder !== document.body) {
        var visTrack = qsa('.slick-track', holder).filter(function (t) { return t.offsetParent !== null; })[0];
        if (visTrack) break;
        holder = holder.parentElement;
      }
      if (!holder || holder === document.body || !visTrack) return;
      ev.preventDefault();
      var slides = qsa('.slick-slide', visTrack).filter(function (sl) { return !sl.classList.contains('slick-cloned'); });
      if (!slides.length) return;
      var w = slides[0].getBoundingClientRect().width || slides[0].offsetWidth || 0;
      if (!w) return;
      var st = state.get(visTrack);
      if (!st) {
        var mm = /translate3d\((-?[\d.]+)px/.exec(visTrack.style.transform || '');
        st = { idx: mm ? Math.max(0, Math.round(Math.abs(parseFloat(mm[1])) / w)) : 0 };
        state.set(visTrack, st);
      }
      var back = /prev|left/.test(arrow.className);
      st.idx += back ? -1 : 1;
      var visible = Math.max(1, Math.round(visTrack.parentElement.getBoundingClientRect().width / w));
      var maxIdx = Math.max(0, slides.length - visible);
      if (st.idx < 0) st.idx = 0;
      if (st.idx > maxIdx) st.idx = maxIdx;
      visTrack.style.transition = 'transform 300ms ease';
      visTrack.style.transform = 'translate3d(' + (-st.idx * w) + 'px, 0, 0)';
      var dots = holder.querySelectorAll('.slick-dots li');
      dots.forEach(function (li, i) { li.classList.toggle('slick-active', i === st.idx); });
    });
  }

  /* ---------- dispatch by pathname ---------- */

  run('header', initHeader);
  run('nav-dropdowns', wireNavDropdowns);
  run('listing-countdowns', wireListingCountdowns);
  run('slick-arrows', wireSlickArrows);

  if (path === '/login') run('login', loginPage);
  else if (path === '/signup') run('signup', signupPage);
  else if (path === '/checkout') run('checkout', checkoutPage);
  /* Books and software bundles reach the same page. Without them here the
     dispatcher never ran, so a book bundle served the frozen template
     untouched and showed the captured Yes Chef bundle's name, blurb and
     tiers under a book bundle's URL — worse than the 404 it replaced. */
  else if (/^\/(games|books|software)\/[^/]+$/.test(path)) run('bundle', bundlePage);
  else if (path === '/store/search' || /^\/store\/c\/[^/]+$/.test(path)) run('search', searchPage);
  /* /store/wishlist must be claimed by the account module before the generic
     /store/{slug} product branch can swallow it (real route, see
     scope/handoff-findings.md). */
  else if (path === '/home' || /^\/home\//.test(path) || path === '/store/wishlist' ||
    path === '/user/settings' || path === '/user/wallet') run('account', accountPanels);
  else if (/^\/store\/[^/]+$/.test(path) && path !== '/store/search') run('product', productPage);
})();

/*
 * Mobile fixup layer (additive module; the IIFE above is untouched).
 * The frozen pages are desktop-DOM-derived; the source site's JS swaps in a
 * few mobile-specific pieces at <=767px. This module fetches
 * /static/site/mobile-fixups.json once and applies its route entries only at
 * narrow viewports: frozen fragments from the mobile capture (marked with
 * data-wb-mobile-fixup), hide entries for desktop-only elements, and style
 * entries for capture-parity CSS. Crossing the breakpoint upward only
 * toggles display/disabled state back - nothing is re-parsed or re-fetched.
 */
(function () {
  'use strict';

  var BREAKPOINT = 767;
  var fetchStarted = false;
  var applied = false;   /* entries materialized into the DOM once */
  var active = false;    /* fixups currently switched on */
  var toggles = [];      /* {on: fn, off: fn} per applied entry */

  function isNarrow() {
    if (window.matchMedia) {
      return window.matchMedia('(max-width: 767px)').matches;
    }
    var w = window.innerWidth || document.documentElement.clientWidth || 0;
    return w <= BREAKPOINT;
  }

  function applyStyle(entry) {
    var st = document.createElement('style');
    st.setAttribute('data-wb-mobile-fixup', '1');
    st.textContent = entry.css;
    document.head.appendChild(st);
    toggles.push({
      on: function () { st.disabled = false; },
      off: function () { st.disabled = true; }
    });
  }

  function applyHide(entry) {
    var els = document.querySelectorAll(entry.selector);
    Array.prototype.forEach.call(els, function (el) {
      if (el.getAttribute('data-wb-mobile-fixup-hidden')) return;
      el.setAttribute('data-wb-mobile-fixup-hidden', '1');
      var prevDisplay = el.style.display;
      toggles.push({
        on: function () { el.style.display = 'none'; },
        off: function () { el.style.display = prevDisplay; }
      });
    });
  }

  function applyFragment(entry) {
    var anchor = document.querySelector(entry.anchor_selector);
    if (!anchor || anchor.getAttribute('data-wb-mobile-fixup-anchor')) return;
    anchor.setAttribute('data-wb-mobile-fixup-anchor', '1');
    var tpl = document.createElement('template');
    tpl.innerHTML = entry.html;
    var kids = Array.prototype.slice.call(tpl.content.children);
    if (!kids.length) return;
    kids.forEach(function (k) { k.setAttribute('data-wb-mobile-fixup', '1'); });
    var position = entry.position || 'after';
    var parent = anchor.parentNode;
    if (position === 'before') {
      parent.insertBefore(tpl.content, anchor);
    } else if (position === 'append') {
      anchor.appendChild(tpl.content);
    } else {
      /* after + replace both insert as the next sibling */
      parent.insertBefore(tpl.content, anchor.nextSibling);
    }
    var hideAnchor = position === 'replace';
    var anchorPrevDisplay = anchor.style.display;
    toggles.push({
      on: function () {
        if (hideAnchor) anchor.style.display = 'none';
        kids.forEach(function (k) { k.style.display = ''; });
      },
      off: function () {
        if (hideAnchor) anchor.style.display = anchorPrevDisplay;
        kids.forEach(function (k) { k.style.display = 'none'; });
      }
    });
  }

  function setActive(next) {
    if (!applied || active === next) return;
    active = next;
    toggles.forEach(function (t) { if (next) { t.on(); } else { t.off(); } });
  }

  function applyEntries(entries) {
    entries.forEach(function (entry) {
      try {
        if (entry.action === 'style') applyStyle(entry);
        else if (entry.action === 'hide') applyHide(entry);
        else if (entry.anchor_selector && entry.html) applyFragment(entry);
      } catch (err) { /* one bad entry must not block the rest */ }
    });
    applied = true;
    /* entries materialize in the off state; switch them on exactly once */
    toggles.forEach(function (t) { t.on(); });
    active = true;
    if (!isNarrow()) setActive(false);
  }

  function ensure() {
    if (!isNarrow()) { setActive(false); return; }
    if (applied) { setActive(true); return; }
    if (fetchStarted) return;
    fetchStarted = true;
    fetch('/static/site/mobile-fixups.json', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (map) {
        if (!map) return;
        var entries = map[window.location.pathname];
        if (entries && entries.length) applyEntries(entries);
      })
      .catch(function () { /* fixups are best-effort; page stays as frozen */ });
  }

  if (window.matchMedia) {
    var mq = window.matchMedia('(max-width: 767px)');
    var onChange = function () { ensure(); };
    if (typeof mq.addEventListener === 'function') mq.addEventListener('change', onChange);
    else if (typeof mq.addListener === 'function') mq.addListener(onChange);
  } else {
    window.addEventListener('resize', function () { ensure(); });
  }

  ensure();
})();


/*
 * Deferred images and the takeover call to action.
 *
 * Both are behaviours the frozen markup expects from libraries the source
 * loads and this clone does not ship.
 *
 * The images: tiles are captured as
 * `<img class="js-lazyload" data-src="/static/assets/<hash>.avif" src="">`.
 * The bytes are local and served — 19 to 39 KB each, status 200 — but nothing
 * ever moved `data-src` into `src`, so 26 of the home page's 56 images stayed
 * empty and the carousel showed its placeholder pattern instead of cover art.
 * Scrolling the carousel made it worse rather than better, because the tiles
 * that scrolled into view had never been processed either.
 *
 * The button: "Get the bundle" is
 * `<button class="js-takeover-cta" type="button">` — not a link. The source
 * binds it in script. Here it did nothing at all, while the destination it
 * should reach, `/games/2k-megahits-2026-bundle`, has been serving 200 the
 * whole time.
 *
 * Everything below reads what the captured markup already says. No URL, label
 * or destination is invented.
 */
(function () {
  'use strict';

  function local(url) {
    if (!url) return true;
    return !/^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(url.trim());
  }

  function reveal(img) {
    if (!img || img.getAttribute('data-was-processed') === 'true') return false;
    /* `data-lazy` is the carousel library's attribute, and stripping that
     * library left it unpromoted everywhere. It accounted for all 196 images
     * that rendered at zero width across the site — 123 on the store listing
     * alone — while every one of those files sat on disk and served 200. The
     * product gallery already fixed this for its own thumbnails, in one branch,
     * with a comment saying why; this is the same repair applied wherever the
     * attribute appears. */
    var src = img.getAttribute('data-src') || img.getAttribute('data-lazy');
    var srcset = img.getAttribute('data-srcset');
    if (!src && !srcset) return false;
    /* Only promote a reference this clone actually holds. Some `data-lazy`
     * values were never localized and still name the source's image CDN;
     * promoting those turned an image that merely stayed blank into a request
     * off the machine, which is the one thing an offline clone may not do. They
     * are left exactly as they were — blank, local, and recorded as a
     * localization gap rather than repaired into a network call. */
    if (!local(src) || !local(srcset)) return false;
    if (srcset) img.setAttribute('srcset', srcset);
    if (src) img.setAttribute('src', src);
    img.setAttribute('data-was-processed', 'true');
    /* The source's own loader adds this class once a tile has an image; the
     * stylesheet uses it, and the carousel's `slick-loading` placeholder stays
     * visible without it. */
    img.classList.add('lazy-loaded');
    img.classList.remove('slick-loading');
    return true;
  }

  function sweep(root) {
    var scope = root && root.querySelectorAll ? root : document;
    var pending = scope.querySelectorAll(
      'img[data-src], img[data-srcset], img[data-lazy]');
    var n = 0;
    for (var i = 0; i < pending.length; i += 1) if (reveal(pending[i])) n += 1;
    return n;
  }

  /* A carousel clones its slides and inserts them as it scrolls, so a single
   * pass at load leaves every later tile empty. Watching for inserted nodes is
   * what makes scrolling left work; the interval is the backstop for a slider
   * that reuses existing nodes instead of inserting new ones, and it stops
   * once the page has been quiet. */
  function watch() {
    sweep(document);
    if (typeof MutationObserver === 'function') {
      new MutationObserver(function (records) {
        for (var i = 0; i < records.length; i += 1) {
          var added = records[i].addedNodes;
          for (var j = 0; j < added.length; j += 1) {
            if (added[j].nodeType === 1) sweep(added[j]);
          }
          if (records[i].type === 'attributes') reveal(records[i].target);
        }
      }).observe(document.documentElement, {
        childList: true, subtree: true,
        attributes: true,
        attributeFilter: ['data-src', 'data-srcset', 'data-lazy'],
      });
    }
    var quiet = 0;
    var timer = setInterval(function () {
      quiet = sweep(document) ? 0 : quiet + 1;
      if (quiet > 8) clearInterval(timer);
    }, 400);
    ['scroll', 'resize', 'click'].forEach(function (ev) {
      window.addEventListener(ev, function () { sweep(document); },
                              {passive: true});
    });
  }

  function bindTakeover() {
    document.addEventListener('click', function (event) {
      var button = event.target.closest && event.target.closest('.js-takeover-cta');
      if (!button) return;
      /* The destination is the takeover's own background link, which the
       * capture marks `aria-hidden` because the button is what a person
       * clicks. Reading it rather than hard-coding a path keeps this correct
       * when the promoted bundle changes. */
      /* The destination is the takeover's own background anchor: the one
       * marked `aria-hidden`, because the button is what a person clicks and
       * the anchor is what the layout paints behind it.
       *
       * Two earlier attempts got this wrong in ways worth keeping. Matching a
       * list of path prefixes missed the Humble Choice takeover entirely, whose
       * destination is `/signup?goto=/membership/checkout` — not a path anyone
       * would think to whitelist. Climbing outward until *a* link appeared then
       * found one: a carousel tile four levels up, so "Get the bundle" opened an
       * unrelated store product. The home page carries two takeovers, and each
       * one's anchor is inside its own block. Scoping to that block is both
       * simpler and correct. */
      var block = button.closest('.takeover-tile-view') || button.parentElement;
      var link = block.querySelector('a[aria-hidden="true"][href]')
        || block.querySelector('a[href]:not([href="#"])');
      if (!link) return;
      event.preventDefault();
      window.location.href = link.getAttribute('href');
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      watch(); bindTakeover();
    });
  } else {
    watch(); bindTakeover();
  }
})();


/*
 * Tile controls: add to cart, and save to wishlist, from any listing.
 *
 * Every store tile carries the same three controls the source ships — a price
 * button that becomes "Add" on hover, a "Buy" button, and a star that toggles
 * "Save"/"Saved". The clone had the endpoints for all of it (`/api/cart/add`,
 * `/api/wishlist/add`, `/api/wishlist/remove`) and bound none of them outside
 * the product detail page, so a store listing showed 151 price buttons and 23
 * save stars and not one of them did anything.
 *
 * Delegated from the document rather than bound per tile, because listings are
 * rendered and re-rendered client-side and a per-element binding would cover
 * only the first paint. The slug comes from the tile's own product link, so
 * this works on any surface that shows tiles without a list of which surfaces
 * those are.
 */
(function () {
  'use strict';

  function slugOf(node) {
    var tile = node.closest('.entity-block-container, .entity-container, li, '
      + '.full-tile-view, .js-entity');
    var link = (tile || document).querySelector('a[href^="/store/"]');
    if (!link) return null;
    var path = link.getAttribute('href').split('?')[0];
    var parts = path.split('/').filter(Boolean);
    return parts.length === 2 && parts[0] === 'store' ? parts[1] : null;
  }

  function post(url, payload) {
    return fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload || {}),
    }).then(function (r) {
      return r.json().catch(function () { return null; })
        .then(function (data) { return {ok: r.ok, status: r.status, data: data}; });
    });
  }

  /* The header's cart count is what tells a person the click landed. Reading
   * it back from the response rather than incrementing a local number keeps it
   * honest when the server refuses — a cart limit, say. */
  function paintCart(view) {
    if (!view) return;
    var items = (view.items || view.cart || []);
    var count = Array.isArray(items) ? items.length : (view.item_count || 0);
    document.querySelectorAll('.js-cart-container .cart-count, .cart-count')
      .forEach(function (node) { node.textContent = String(count); });
    document.querySelectorAll('.js-cart-container').forEach(function (node) {
      node.classList.toggle('has-items', count > 0);
    });
  }

  function flash(node, text) {
    var holder = node.closest('.price-container, .wishlist-button-view') || node;
    holder.setAttribute('data-hb-flash', text);
    setTimeout(function () { holder.removeAttribute('data-hb-flash'); }, 1600);
  }

  document.addEventListener('click', function (event) {
    var target = event.target;
    if (!target || !target.closest) return;

    var price = target.closest('.price-inner-button, .js-add-to-cart');
    if (price) {
      var slug = slugOf(price);
      if (!slug) return;
      event.preventDefault();
      event.stopPropagation();
      post('/api/cart/add', {kind: 'product', slug: slug}).then(function (r) {
        if (r.ok) { paintCart(r.data); flash(price, 'Added'); }
        else if (r.status === 401) location.href = '/login?goto='
          + encodeURIComponent(location.pathname);
        else flash(price, (r.data && r.data.message) || 'Not added');
      });
      return;
    }

    var wish = target.closest('.js-wishlist-button');
    /* The detail page binds its own star and keeps its own state; leaving that
     * one alone avoids two handlers fighting over the same click. */
    if (wish && !wish.closest('.js-wishlist-container')) {
      var wslug = slugOf(wish);
      if (!wslug) return;
      event.preventDefault();
      event.stopPropagation();
      var saved = wish.classList.contains('saved');
      post('/api/wishlist/' + (saved ? 'remove' : 'add'), {slug: wslug})
        .then(function (r) {
          if (r.ok) wish.classList.toggle('saved', !saved);
          else if (r.status === 401) location.href = '/login?goto='
            + encodeURIComponent(location.pathname);
        });
    }
  }, true);

  /* Reflect what is already saved, so a reload does not show every star empty
   * on a wishlist that is not. */
  function markSaved() {
    /* Only ask once there is someone to ask about. Calling this anonymously
     * answers 401 correctly and logs a console error on every page — noise
     * that reads like a fault when it is the expected reply. */
    if (!document.querySelector('.js-wishlist-button')) return;
    fetch('/api/account', {credentials: 'same-origin'})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (acct) {
        if (!acct || !acct.authenticated) return null;
        return fetch('/api/wishlist', {credentials: 'same-origin'})
          .then(function (r) { return r.ok ? r.json() : null; });
      })
      .then(function (data) {
        if (!data) return;
        var slugs = (data.wishlist || data.items || []).map(function (w) {
          return w.slug || w;
        });
        document.querySelectorAll('.js-wishlist-button').forEach(function (node) {
          if (node.closest('.js-wishlist-container')) return;
          var s = slugOf(node);
          if (s && slugs.indexOf(s) >= 0) node.classList.add('saved');
        });
      })
      .catch(function () {});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', markSaved);
  } else {
    markSaved();
  }
})();


/*
 * The last three controls that looked live and were not.
 *
 * A clear-search button that never cleared, a language selector that never
 * opened, and twenty-one "Watch Trailer" buttons that did nothing at all. Each
 * is bound to what this clone can honestly do — which for the trailer is to say
 * plainly that the video is not here, rather than to sit inert and let a person
 * conclude the page is broken.
 */
(function () {
  'use strict';

  function q(sel, root) { return (root || document).querySelector(sel); }

  document.addEventListener('click', function (event) {
    var t = event.target;
    if (!t || !t.closest) return;

    /* Clear search. The button carries a magnifier icon and sits inside the
     * search bar; clicking it should empty the field and put the caret back. */
    var clear = t.closest('.js-clear-search-button');
    if (clear) {
      var bar = clear.closest('.searchbar, form') || document;
      var input = q('input[type="search"], input[name="search"], input[type="text"]', bar);
      if (input) {
        event.preventDefault();
        input.value = '';
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.focus();
      }
      return;
    }

    /* Language selector. This clone is English only — the capture is English
     * and no other locale was ever fetched — so the menu opens and offers the
     * one language there is, instead of listing thirty that would each be a
     * lie. */
    var lang = t.closest('.js-language-dropdown');
    if (lang) {
      event.preventDefault();
      var holder = lang.closest('.language-dropdown-container') || lang.parentElement;
      var open = holder.querySelector('.hb-language-menu');
      if (open) { open.remove(); return; }
      var menu = document.createElement('div');
      menu.className = 'hb-language-menu';
      menu.setAttribute('role', 'menu');
      menu.style.cssText = 'position:absolute;z-index:60;background:#1b2838;'
        + 'border:1px solid #2f4457;border-radius:4px;padding:6px 0;'
        + 'min-width:190px;box-shadow:0 6px 18px rgba(0,0,0,.45)';
      var item = document.createElement('div');
      item.setAttribute('role', 'menuitem');
      item.textContent = 'English';
      item.style.cssText = 'padding:7px 14px;color:#fff;font-size:13px;cursor:default';
      var note = document.createElement('div');
      note.textContent = 'Only English was captured for this offline copy.';
      note.style.cssText = 'padding:5px 14px 2px;color:#8ba3b8;font-size:11px;'
        + 'border-top:1px solid #2f4457;margin-top:4px';
      menu.appendChild(item);
      menu.appendChild(note);
      holder.style.position = holder.style.position || 'relative';
      holder.appendChild(menu);
      return;
    }

    /* Trailers. The button names a YouTube id, and external video was never
     * localized — that is already a recorded known difference. The poster frame
     * is local, so the dialog shows the poster and says where the video is,
     * which is the honest version of this control. */
    var trailer = t.closest('.js-learn-more-games-desktop, [data-youtube-video-id]');
    if (trailer) {
      event.preventDefault();
      var title = trailer.getAttribute('data-title') || 'Trailer';
      var back = document.createElement('div');
      back.className = 'hb-trailer-backdrop';
      back.style.cssText = 'position:fixed;inset:0;z-index:120;background:rgba(0,0,0,.72);'
        + 'display:flex;align-items:center;justify-content:center';
      var box = document.createElement('div');
      box.style.cssText = 'background:#1b2838;color:#fff;max-width:460px;padding:22px 24px;'
        + 'border-radius:6px;font-size:14px;line-height:1.5';
      var h = document.createElement('div');
      h.textContent = title;
      h.style.cssText = 'font-weight:700;margin-bottom:8px';
      var body = document.createElement('div');
      body.textContent = 'This trailer is hosted on YouTube and was not copied '
        + 'into the offline build, so it cannot play here.';
      body.style.color = '#c6d4e1';
      var close = document.createElement('button');
      close.textContent = 'Close';
      close.style.cssText = 'margin-top:16px;padding:7px 16px;border:0;border-radius:3px;'
        + 'background:#2f97d1;color:#fff;cursor:pointer';
      close.addEventListener('click', function () { back.remove(); });
      back.addEventListener('click', function (e) { if (e.target === back) back.remove(); });
      box.appendChild(h); box.appendChild(body); box.appendChild(close);
      back.appendChild(box);
      document.body.appendChild(back);
    }
  }, true);

  document.addEventListener('click', function (event) {
    var menu = document.querySelector('.hb-language-menu');
    if (menu && !event.target.closest('.language-dropdown-container')) menu.remove();
  });
})();
