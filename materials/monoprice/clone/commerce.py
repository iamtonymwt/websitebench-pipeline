"""Cart, checkout and order pages, rendered into the source's own page shell.

These three pages are the one part of the purchase journey with no source
evidence and no prospect of any: `/cart`, `/Checkout` and `/sslchkout` are all
under robots Disallow rules, so they were never requested and never will be.

What is honest here is to reuse what we do have -- the real header, navigation,
search box and footer, cut from a captured page -- and write the content between
them ourselves, saying plainly on the page that payment settles against a local
sandbox. What would not be honest is to invent a Monoprice checkout from memory
and present it as a reproduction.

The stylesheet below is supplied by this project. It is scoped under `.wb-`
class names so it cannot collide with, or be mistaken for, the source's own CSS.
"""

from __future__ import annotations

import html
import pathlib

SHELL_PATH = pathlib.Path(__file__).resolve().parent / "static" / "page-shell.html"
CONTENT_MARK = "@@WB_CONTENT@@"
TITLE_MARK = "@@WB_TITLE@@"

STYLE = """
<style>
.wb-wrap{max-width:1180px;margin:24px auto 48px;padding:0 16px;font-size:15px}
.wb-wrap h1{font-size:26px;margin:0 0 4px}
.wb-note{background:#eef7f9;border:1px solid #bfe0e6;border-left:4px solid #0098aa;
  padding:12px 14px;margin:14px 0;border-radius:3px;line-height:1.5}
.wb-alert{background:#fdf0ef;border:1px solid #f2c2bd;border-left:4px solid #c0392b;
  padding:12px 14px;margin:14px 0;border-radius:3px}
.wb-ok{background:#eef9f0;border:1px solid #bfe6c8;border-left:4px solid #2e9e4f;
  padding:12px 14px;margin:14px 0;border-radius:3px}
.wb-table{width:100%;border-collapse:collapse;margin:18px 0}
.wb-table th,.wb-table td{padding:11px 10px;border-bottom:1px solid #e3e6e8;
  text-align:left;vertical-align:middle}
.wb-table th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#5a6570}
.wb-table td.wb-num,.wb-table th.wb-num{text-align:right}
.wb-total{font-weight:700;font-size:19px}
.wb-btn{display:inline-block;background:#0098aa;color:#fff;border:0;border-radius:3px;
  padding:11px 22px;font-size:15px;cursor:pointer;text-decoration:none}
.wb-btn:hover{background:#007e8d;color:#fff}
.wb-btn--ghost{background:#fff;color:#0098aa;border:1px solid #0098aa}
.wb-panel{border:1px solid #e3e6e8;border-radius:4px;padding:18px;margin:16px 0}
.wb-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.wb-field label{display:block;font-size:12px;color:#5a6570;margin-bottom:4px}
.wb-field input,.wb-field select{width:100%;padding:9px;border:1px solid #c8ced3;
  border-radius:3px;font-size:14px}
.wb-muted{color:#5a6570}
.wb-empty{padding:40px 0;text-align:center}
</style>
"""


def money(value: float, currency: str = "USD") -> str:
    symbol = "$" if currency == "USD" else ""
    return f"{symbol}{value:,.2f}"


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def chrome(title: str, body: str) -> str:
    """Wrap our content in the source's shell."""
    if not SHELL_PATH.exists():
        raise RuntimeError(
            "clone/static/page-shell.html is missing; run tools/extract_page_shell.py")
    shell = SHELL_PATH.read_text(encoding="utf-8")
    page = shell.replace(TITLE_MARK, esc(title))
    return page.replace(CONTENT_MARK, STYLE + f'<div class="wb-wrap">{body}</div>')


SANDBOX_NOTE = (
    '<div class="wb-note"><strong>This is an offline reproduction.</strong> '
    'Checkout here settles against a local payment sandbox. No card details are '
    'requested, transmitted or stored, and no order reaches Monoprice. The cart '
    'and checkout pages are the clone&rsquo;s own work: the source site places '
    'them under a robots <code>Disallow</code> rule, so no copy of them was '
    'ever retrieved.</div>')


def cart_page(lines: list[dict]) -> str:
    if not lines:
        body = (f"<h1>Your Cart</h1>{SANDBOX_NOTE}"
                '<div class="wb-empty"><p class="wb-muted">Your cart is empty.</p>'
                '<p><a class="wb-btn" href="/">Continue shopping</a></p></div>')
        return chrome("Shopping Cart - Monoprice.com", body)

    currency = lines[0]["currency"]
    total = round(sum(line["line_total"] for line in lines), 2)
    rows = "".join(
        f'<tr data-p-id="{esc(line["p_id"])}">'
        f'<td><a href="/product?p_id={esc(line["p_id"])}">{esc(line["name"])}</a>'
        f'<div class="wb-muted">Item {esc(line["p_id"])}</div></td>'
        f'<td class="wb-num">{money(line["price"], currency)}</td>'
        f'<td class="wb-num">'
        f'<form method="post" action="/cart/update" style="display:inline">'
        f'<input type="hidden" name="p_id" value="{esc(line["p_id"])}">'
        f'<input type="number" name="qty" min="0" value="{line["quantity"]}" '
        f'style="width:64px;padding:5px" aria-label="Quantity">'
        f'<button class="wb-btn wb-btn--ghost" type="submit" '
        f'style="padding:5px 10px;margin-left:6px">Update</button></form></td>'
        f'<td class="wb-num" data-line-total>{money(line["line_total"], currency)}</td>'
        f'<td class="wb-num">'
        f'<form method="post" action="/cart/remove">'
        f'<input type="hidden" name="p_id" value="{esc(line["p_id"])}">'
        f'<button class="wb-btn wb-btn--ghost" type="submit" '
        f'style="padding:5px 10px">Remove</button></form></td></tr>'
        for line in lines)

    body = f"""<h1>Your Cart</h1>{SANDBOX_NOTE}
<table class="wb-table">
  <thead><tr><th>Item</th><th class="wb-num">Price</th>
  <th class="wb-num">Qty</th><th class="wb-num">Total</th><th></th></tr></thead>
  <tbody>{rows}</tbody>
  <tfoot><tr><td colspan="3" class="wb-num wb-total">Subtotal</td>
  <td class="wb-num wb-total" data-cart-total>{money(total, currency)}</td>
  <td></td></tr></tfoot>
</table>
<p><a class="wb-btn" href="/checkout">Proceed to Checkout</a>
   <a class="wb-btn wb-btn--ghost" href="/" style="margin-left:8px">Continue shopping</a></p>"""
    return chrome("Shopping Cart - Monoprice.com", body)


def checkout_page(lines: list[dict], scenarios: list[dict],
                  message: str | None = None) -> str:
    if not lines:
        body = (f"<h1>Checkout</h1>{SANDBOX_NOTE}"
                '<div class="wb-empty"><p class="wb-muted">There is nothing to '
                'check out.</p><p><a class="wb-btn" href="/">Continue shopping</a>'
                "</p></div>")
        return chrome("Checkout - Monoprice.com", body)

    currency = lines[0]["currency"]
    total = round(sum(line["line_total"] for line in lines), 2)
    summary = "".join(
        f'<tr><td>{esc(line["name"])} &times; {line["quantity"]}</td>'
        f'<td class="wb-num">{money(line["line_total"], currency)}</td></tr>'
        for line in lines)
    options = "".join(
        f'<option value="{esc(s["id"])}">{esc(s["display_label"])}</option>'
        for s in scenarios)
    banner = f'<div class="wb-alert">{esc(message)}</div>' if message else ""

    body = f"""<h1>Checkout</h1>{SANDBOX_NOTE}{banner}
<form method="post" action="/checkout">
  <div class="wb-panel"><h2 style="font-size:18px;margin-top:0">Shipping</h2>
    <div class="wb-grid">
      <div class="wb-field"><label for="ship_name">Full name</label>
        <input id="ship_name" name="ship_name" required value="Test Shopper"></div>
      <div class="wb-field"><label for="ship_city">City</label>
        <input id="ship_city" name="ship_city" required value="Rancho Cucamonga"></div>
      <div class="wb-field"><label for="ship_state">State</label>
        <input id="ship_state" name="ship_state" required value="CA"></div>
      <div class="wb-field"><label for="ship_postal">ZIP</label>
        <input id="ship_postal" name="ship_postal" required value="91730"></div>
    </div>
  </div>
  <div class="wb-panel"><h2 style="font-size:18px;margin-top:0">Payment</h2>
    <p class="wb-muted">The local sandbox decides the outcome. There is no card
       field on this page because no card number is ever accepted, sent or kept.</p>
    <div class="wb-field" style="max-width:340px">
      <label for="scenario">Sandbox outcome</label>
      <select id="scenario" name="scenario">{options}</select>
    </div>
  </div>
  <div class="wb-panel"><h2 style="font-size:18px;margin-top:0">Order summary</h2>
    <table class="wb-table"><tbody>{summary}</tbody>
      <tfoot><tr><td class="wb-total">Total</td>
      <td class="wb-num wb-total" data-checkout-total>{money(total, currency)}</td>
      </tr></tfoot></table>
  </div>
  <button class="wb-btn" type="submit">Place order</button>
</form>"""
    return chrome("Checkout - Monoprice.com", body)


def order_page(order: dict, lines: list[dict]) -> str:
    currency = order["currency"]
    rows = "".join(
        f'<tr><td>{esc(line["name"])}</td><td class="wb-num">{line["quantity"]}</td>'
        f'<td class="wb-num">{money(line["unit_price"], currency)}</td></tr>'
        for line in lines)
    body = f"""<h1>Order placed</h1>
<div class="wb-ok">Thank you. Your order has been placed against the local
payment sandbox.</div>{SANDBOX_NOTE}
<div class="wb-panel">
  <p>Order reference <strong data-order-reference>{esc(order["order_id"])}</strong></p>
  <p>Shipping to {esc(order["ship_name"])}, {esc(order["ship_city"])},
     {esc(order["ship_state"])} {esc(order["ship_postal"])}</p>
</div>
<table class="wb-table">
  <thead><tr><th>Item</th><th class="wb-num">Qty</th>
  <th class="wb-num">Unit price</th></tr></thead>
  <tbody>{rows}</tbody>
  <tfoot><tr><td class="wb-total">Amount paid</td><td></td>
  <td class="wb-num wb-total" data-order-total>
  {money(order["total_minor"] / 100, currency)}</td></tr></tfoot>
</table>
<p><a class="wb-btn" href="/">Continue shopping</a></p>"""
    return chrome("Order Confirmation - Monoprice.com", body)
