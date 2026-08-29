"""Drop the four footer links whose destinations this clone does not hold.

`/developer`, `/partner`, `/store/rimworld` and `/store/slay-the-spire` appear
in the footer of every frozen page, and the footer is on the home page, so all
four were one click from the front door and all four answered 404.

They are not fixable by wiring. The evidence has been searched end to end:
neither `/developer` nor `/partner` is among the twenty-two captured pages;
RimWorld and Slay the Spire appear nowhere in `products`, `bundles`,
`bundles_listing`, `search_meta` or `suggest_orders` — only as text in the
footer's "Trending Games" list. There is no price, no image and no detail page
for either, and inventing a price for a real commercial product is not a gap
this build will close.

So the links go. A link to something an offline clone does not hold is not a
feature of the clone; it is a hole with an anchor tag around it. The list item
is removed whole, so the footer reads as a shorter list rather than as a broken
one, and every removal is recorded in the delivery report.
"""

import pathlib
import re

WT = pathlib.Path("/private/tmp/claude-501/-Users-wentaoma-Desktop-websitebench-pipeline/"
                  "58984861-9d0e-42a7-9929-7f0ca633ca88/scratchpad/wt-humble/"
                  "materials/humble-bundle")
PAGES = WT / "clone/frontend/pages"

# Only these two. RimWorld and Slay the Spire were on this list until their
# prices, discounts, platform and cover images turned up in the top-sellers
# strip of the captured product page — an earlier search of `products`,
# `bundles`, `bundles_listing`, `search_meta` and `suggest_orders` had
# concluded there was no evidence for them, and had simply not looked there.
# They are in the catalogue now and their links resolve.
DEAD = ["/developer", "/partner"]

removed = {}
touched = 0
for page in sorted(PAGES.glob("*.html")):
    text = original = page.read_text(encoding="utf-8", errors="replace")
    for href in DEAD:
        # Remove the whole <li> when the anchor sits in a list, so no empty
        # bullet is left behind; otherwise remove just the anchor.
        li = re.compile(
            r"\s*<li>\s*<a[^>]*href=\"" + re.escape(href) + r"\"[^>]*>.*?</a>\s*</li>",
            re.S)
        text, n = li.subn("", text)
        a = re.compile(r"<a[^>]*href=\"" + re.escape(href) + r"\"[^>]*>.*?</a>", re.S)
        text, m = a.subn("", text)
        if n or m:
            removed[href] = removed.get(href, 0) + n + m
    if text != original:
        page.write_text(text, encoding="utf-8")
        touched += 1

print(f"rewrote {touched} frozen pages")
for href, n in sorted(removed.items()):
    print(f"  removed {n:3d} x {href}")
