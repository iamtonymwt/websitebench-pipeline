# Humble Bundle harvest → seed data contract notes

Source of truth: `source-current/2026-08-20.humble-bundle-r1/api-harvest/`
(captured 2026-08-20, CAD region, anonymous session). Normalizer:
`tools/build_seed.py` → `clone/backend/seed_data.json`
(`humble-bundle.seed.v1`). The build is deterministic (byte-identical on
re-run), stdlib-only, and copies or arithmetically derives every value from
the harvest — nothing is invented. Fields absent from a harvest record are
omitted from the seed, never null-padded.

## 1. `/store/api/lookup` payload — actual schema

Wrapper: `{"request": 1, "result": [<entry>, ...]}` — `result` is a flat
list (not keyed by slug); order follows the `products[]=` query order.
69 entries across the four captures, all slugs unique, exactly covering the
union of the two captured listings. The same entry shape (minus the
detail-only fields) is what `/store/api/search` returns per result;
listing prices matched lookup prices exactly at capture time (0 drift).

### Mapped entry fields (→ seed `products[]`)

| harvest field | seed field | notes |
|---|---|---|
| `human_url` | `slug` | primary key; unique |
| `machine_name` | `machine_name` | unique |
| `human_name` | `human_name` | |
| `current_price` / `full_price` | `current_price_minor` / `full_price_minor` | money object → integer cents (see §4) |
| — (derived) | `discount_pct` | see §3 |
| `platforms` | `platforms` | captured order kept |
| `icon_dict` (keys) | `drm` | DRM facet == delivery-method keys; key sets verified identical to `delivery_methods` for all 69 |
| `delivery_methods` | `delivery_methods` | observed values: steam, epic, switch, download, other-key |
| `genre_identifiers` | `genres` | |
| `cta_badge` | `cta_badge` | only when non-null (7/69: new, preorder, earlyaccess); grounds the `new` search filter |
| `developers` / `publishers` | `developers` / `publishers` | `{kind}-name`/`{kind}-url` → `{name, url?}`; `url` omitted when empty (116 entries lack one); `developers` key absent for 1 product (`persona-3-portable-switch`) |
| `user_rating` | `user_rating` | verbatim when present (22/69) — see §3 |
| `esrb_rating` (23), `pegi_rating` (7), `rating_details` (31), `minimum_age` (21), `rating_for_current_region` (69) | same names | verbatim "as found"; `rating_details` may be `""`; `rating_for_current_region` is constantly `"esrb"` (artifact of the CAD-region capture) |
| `description`, `system_requirements` | same | HTML strings as-is |
| `standard_carousel_image`, `large_capsule`, `featured_image_recommendation`, `icon`, `xray_traits_thumbnail`, `mini_carousel_image` (6/69) | `media.<same name>` | source imgix URLs, un-localized by design (localization is a later pass) |
| `carousel_content.screenshot` / `.thumbnails` / `.youtube-link` | `media.screenshots` / `.thumbnails` / `.youtube` | |
| — (from listing captures) | `search_orders` | `{"portal": rank, "adventure-bestselling": rank}`, 1-based, captured order across pages (p0 then p1); no slug appeared in both listings |

`products[]` itself is sorted alphabetically by `slug`; the captured
bestselling orders live entirely in `search_orders`.

### Unmapped entry fields (and why)

Presence counts out of 69:

- `type` (69, constant `"product"`) — no information.
- `content_types` (69; game/mobile/music tags) — content-type facet is not
  in the seed contract; candidate for a later pass.
- `display_item_machine_name` (69) — product-page display-item linkage;
  no seed consumer.
- `sale_end` (54; epoch seconds as float), `sale_type` (54, constant
  `"normal"`) — sale scheduling is runtime behavior; the discount itself is
  fully encoded by the price pair (§3). Every entry carrying `sale_end` has
  `current < full`, so `onsale == discount_pct > 0` holds exactly.
- `non_rewards_charity_split`, `rewards_split` (69) — store purchase split
  fractions; no in-scope journey surfaces them.
- `empty_tpkds` (69, always `{}`) — empty in the whole harvest.
- `nonrefundable` (69; true for 3) — checkout policy flag; checkout is a
  later pass.
- `required_account_links` (54), `require_linked_third_party_account_when`
  (16), `giftable_when` (18) — account-linking/gifting policy, out of scope.
- `other_links` (55) — official-website links, out of contract.
- `legal_disclaimer` (54), `disclaimer` (5), `auto_disclaimer` (9),
  `alert_messages` (13), `promotional_message` (2),
  `incompatible_features` (3) — page notice strings/flags; `alert_messages`
  (DLC-requires-base-game banners) is the strongest later-pass candidate.
- `icon_dict` per-DRM platform availability lists — only the keys are
  seeded (as `drm`); the per-DRM `available`/`unavailable` matrix is
  dropped (top-level `platforms` covers the tile UI).
- `carousel_content.asm-demo-machine-name` (15) — in-browser demo feature,
  out of scope.

Null-vs-absent convention is inconsistent upstream: `user_rating` is
*key-absent* for 47 entries (never explicit null), while `cta_badge` is
*explicitly null* for 62. The seed normalizes both to key-omission.

## 2. `bundleData` highlights

Bundle pages embed one `bundleData` object (harvested via the page's
pre-hydration JSON; the wrapper's `csrfToken*` values were already redacted
at capture time and `userOptions` shows `is_logged_in: false` — no session
material exists in the harvest or the seed).

### `tier_display_data` structure

`{tier_id: {header, identifier, tier_item_machine_names, hidden_machine_names,
bonus_item_machine_names, sold_out, time_till_mpa}}`, ordered externally by
`tier_order`.

- `tier_order` is the captured display order, **highest tier first** on the
  multi-tier bundle (`["bt16", "bt13", "initial"]`); the seed keeps
  `tier_order` verbatim and emits `tiers[]` in that order.
- **Tier item lists are cumulative**: a higher tier's
  `tier_item_machine_names` contains every lower tier's items plus its own
  increment. Yes-Chef: initial=7 ⊂ bt13=13 ⊂ bt16=16. Seed `item_count` and
  `items[]` are therefore cumulative too (items repeat across tiers by
  design; consumers wanting increments diff against the previous tier).
- `hidden_machine_names` / `bonus_item_machine_names` were `[]` and
  `sold_out` false, `time_till_mpa` null everywhere in this harvest.
- Prices live separately in `tier_pricing_data[tier_id].price|money`
  (→ `threshold_minor`), with `is_initial_tier` marking the floor tier and
  `is_fixed: true` on every harvested tier. `header` strings embed the
  formatted price ("Pay CA$22.19 or more to also unlock!") and are kept
  verbatim — they agree with `threshold_minor`.
- `tier_item_data` is keyed by item machine name and contains **one extra
  entry beyond the tier items: the charity** (`farmlink`, `covenanthouse`),
  which also appears under `charity_data.charity_items` with a `ppgf_info`
  block (PayPal Giving Fund record: `human_name`, `charity_id`,
  `description`, `url`, `logo_url`, address fields). Seed `charity` maps
  `machine_name`, `name`, `id`, `blurb`; `url`/`logo_url`/address/keywords
  are unmapped (later pass), `charity_data.header` was `""`.

### Other sections

- `basic_data` → seed `name` (`human_name`), `type` (`media_type`),
  `end_at` (`end_time|datetime`), `msrp_minor` (`msrp|money`); its
  `tpkd_cutoff_price` equals the initial tier price in both bundles and
  cross-checks seed `floor_minor`. Unmapped: marketing blurbs, bundle page
  `description`/`logo` (frontend-pass candidates), payment processor lists,
  newsletter list name, `required_account_links`.
- `preset_prices` → `preset_prices_minor` (captured order: the three tier
  thresholds + round upsell amounts) plus `suggested_price_minor` from the
  single `suggested: true` entry (CA$30.00 in both bundles);
  `qualifying_tier_id` per preset is unmapped.
- `splits` → seed `splits` with Humble's key-type suffixes stripped
  (§4): parties `publisher` / `paypalgivingfund` / `humblebundle`, each
  carrying the mode fractions `partner_split` (default),
  `extra_charity_partner_split` + `extra_charity_split` (extra-charity
  slider mode), `sibling_split` (custom-split mode), optional
  `minimum_split`, and optional per-title `subsplit` lists. Fractions kept
  as found (they are ratios, not money). The 2K charity party name carries
  a trailing space (`"Covenant House "`) — kept, harvest is authority.
- `statistics_data` → `sold_count` (`num_purchases|decimal`, integral in
  both) and `charity_raised_minor` (`total_charity_raised|money`).
- `at_time|datetime` → `harvested_at` (naive ISO, no timezone — kept
  verbatim; same for `end_at`).
- Per-item mapping: `machine_name`, `human_name`,
  `msrp_price|money` → `msrp_minor`, callout split (§3), media refs
  (`resolved_paths.featured_image` → `media.featured_image` imgix URL,
  `featured_image` → `media.featured_image_path` gcs path,
  `youtube_link` → `media.youtube`; `xcom_ufodefense` has no youtube key).
- Unmapped bundleData sections: `average_data` (beat-the-average stats,
  USD + opaque `avghash`/`avguuid`; unused by these fixed-tier bundles),
  `leaderboard_data` (top-supporter **display names** and non-CAD
  `order_price` values — deliberately excluded), `other_bundles_data`
  (cross-promo tiles, redundant with `bundles_listing`), `upsell_data`
  (Humble Choice subscription upsell), `jplayer_swf_path`,
  `at_risk_tpkds`/`empty_tpkds`/`cyoc_data` (empty), `partner_data`/
  `tax_type` (null), `is_all_charity_bundle`, `author`, `page_url` (slug
  extracted from it). Per-item unmapped: `min_price|money` (per-item unlock
  price — duplicates the owning tier threshold), `description_text`,
  `developers`, `availability_icons`, `platforms_and_oses`,
  `front_page_art`, `soundtrack_listing`, `all_ratings` (all-null),
  `user_ratings` (always `{}` — see §3), and assorted display flags.

### `bundles-landing` (57 tiles)

`data.{books,games,software}.mosaic[0].products[]` — captured key order
(books, games, software) and tile order preserved in seed
`bundles_listing`. Mapped per tile: `machine_name`, `tile_name` → `name`,
`product_url` last segment → `slug`, `tile_stamp` → `type`,
`end_date|datetime` → `end_at`, `highlights` (verbatim list),
`tile_image` (imgix URL). All 27 tile fields are present on all 57 tiles;
unmapped: blurbs, hover/hero highlight variants, `tile_logo`,
`high_res_tile_image`, `*_information` image configs, `bundles_sold`,
`start_date`, `author`, and constant `type: "bundle"`/`category` fields.
One books tile is stamped `comics` (kept as found). Both detailed bundles
appear in the games mosaic.

### `search_meta` provenance

- `page_size: 20` and endpoint paths from `observed-endpoints.json` (the
  page's own request: `/store/api/search?sort=bestselling&filter=all&search=portal&request=1&page=0`).
- `genres` — the 8-value enum extracted from the storefront constants JSON
  (`/FEATURED_GENRES`), order kept.
- `sorts` (`discount|alphabetical|newest|bestselling`) and `filters`
  (`onsale|new`) — store UI facets fixed by the task contract; only
  `sort=bestselling` and the no-op `filter=all` appear in the captured
  request itself.
- `platforms` / `drm` — sorted unions of observed per-product values (no
  declared enum exists in the harvest): platforms linux, mac, oculus-rift,
  switch, windows; drm download, epic, other-key, steam, switch.
- Listing pagination context: `num_results`/`num_pages` describe the full
  upstream result set (portal: 29/2 fully captured; adventure: 5684/285,
  first 2 pages captured — ranks beyond 40 are unknown, not zero).

## 3. Surprising semantics

- **Discount/full-price encoding**: store products carry no discount
  field; a sale is just `current_price < full_price` (plus optional
  `sale_end`/`sale_type` metadata). Non-sale products lack those keys
  entirely and have `current == full`. Seed `discount_pct` is derived on
  minor units: `round_half_up((full − current) × 100 / full)`, `0` when not
  discounted.
- **Cumulative tier nesting** (§2): tier item lists and counts include all
  lower tiers; the expected 7/13/16 counts are cumulative, not incremental.
- **Two steam-rating encodings**: store lookup `user_rating` is structured
  (`steam_percent` as a 0–1 *fraction*, e.g. `0.95`; `steam_count`;
  `review_text` token like `very_positive`; `display_user_ratings`
  `steam_overall|steam_recent`), while bundle items have `user_ratings`
  always `{}` and encode the percent only inside `callout` HTML
  (`<span>NN% Positive on Steam</span><br><br>…`, Yes-Chef only). The seed
  splits callouts deterministically: leading span → `steam_positive_pct`
  (integer 0–100), remainder → `one_liner`; 2K callouts have no rating span
  and map whole to `one_liner`. Note the unit mismatch: product
  `user_rating.steam_percent` stays a fraction (as found), bundle item
  `steam_positive_pct` is a whole percent (as printed).
- **Type-suffixed keys**: Humble's embedded JSON annotates value types in
  key names — `key|money`, `key|decimal`, `key|datetime`. The seed strips
  the suffixes; `|money` values become `*_minor` integers, `|decimal`
  fractions stay numbers, `|datetime` strings stay verbatim (naive ISO,
  no timezone anywhere in the harvest).
- The charity is modeled upstream as a pseudo-item inside
  `tier_item_data` but never listed in any tier.
- `bundleData` money is inconsistent about currency: mapped fields are all
  CAD, but `average_data` is USD-based and `leaderboard_data` order prices
  arrive in the buyer's currency (EUR/USD/AUD/CNY observed) — one reason
  those sections stay unmapped.

## 4. Money and rounding observations

- Wire format is `{"currency": "CAD", "amount": <float dollars>}`. The
  builder parses JSON with `parse_float=Decimal` so amounts convert to
  cents exactly (`CA$22.19 → 2219`); every mapped money field is an
  integer minor-unit and the builder hard-fails on any non-CAD mapped
  money or non-integer result.
- **Sub-cent precision exists upstream** (currency-converted figures) and
  is rounded HALF_UP — full list, unchanged across re-runs:
  - both bundles' `basic_data.msrp|money`
    (645.0297285652736 → 64503; 288.52942697113315 → 28853);
  - six tier-item `msrp_price|money` values: 2K `mafia2_definitive`
    (→ 4160), `tribesofmidgard_deluxe` (→ 4159),
    `hiddenanddangerous_bundle` (→ 2217); Yes-Chef `foodtrucksimulator`
    (→ 2773), `brewmaster_beerbrewingsimulator` (→ 2496),
    `recipefordisaster` (→ 2079).
  All store product prices are exact cents.
- `discount_pct` and the callout percent are the only other derived
  numbers; both use ROUND_HALF_UP / literal extraction.
- Cross-check status (harvest = authority): Yes-Chef tiers
  971/1803/2219 with cumulative item counts 7/13/16 — **matches** the
  expected values; 2K single fixed tier 2116 with 15 items — **matches**.
  `floor_minor` == `tpkd_cutoff_price` == initial tier price in both.
- Seed-wide invariant enforced at build time: every `*_minor` key holds an
  integer (or list of integers, e.g. `preset_prices_minor`), and the file
  re-serializes byte-identically.

## Appendix A. Header-search suggest oracle (`suggest_orders`) and lookup 5

### A.1 `product-detail-5.json` — redundant confirmation lookup

`product-detail-5.json` (same `{"request": 1, "result": [...]}` shape as
lookups 1–4) is a follow-up single-product lookup of
`spellrune-realm-of-portals` made during the suggest-panel capture
session. **The product was already harvested**: `product-detail-1.json`
(the portal-listing page-0 lookup) carries the same entry, and the
captured `portal` listing ranks it at **7** — so, contrary to the working
note that Spellrune lacked a captured rank, it keeps
`search_orders == {"portal": 7}` (the harvest is the authority; dropping
the rank would falsify the pinned 29-result portal listing).

The two entries are semantically identical — every field compares equal
under the builder's `parse_float=Decimal` load; the only wire difference
is `non_rewards_charity_split` serialized as `0.0` (lookup 1) vs `0`
(lookup 5), an unmapped field either way. `build_seed.py` therefore
ingests all five lookup files and **dedupes equal duplicate slugs to the
first-seen entry** (a *disagreeing* duplicate is still a fatal
`SeedError`); the dedupe is reported
(`lookup duplicates verified equal, deduped ...: spellrune-realm-of-portals`).
Product count stays **69**; seed bytes for `products[]` are unchanged.

### A.2 `suggest_orders` — pinned header-search panel rows

Source: the frozen DOM capture
`source-current/2026-08-20.humble-bundle-r1/interactive/home-search-suggest/dom.html`
(typed query `portal`, captured 2026-08-20T22:23:15Z). The first balanced
`.site-search-results.js-results` div is parsed; each
`.product-search-result` block becomes one row of
`seed["suggest_orders"]["portal"]`, **in captured panel order** (5 rows:
1 software bundle + 4 store products). The panel footer
("View All Results (37)" / paging arrows) is frontend chrome and is not
seeded; note the live-site total (37) exceeds the frozen listing capture
(29) — capture-time drift, the frozen listing stays authoritative.

Row schema (fixed keys, both seed and `/api/suggest`):

| key | value |
|---|---|
| `kind` | `"bundle"` when the row image carries the `bundle-product` class, else `"product"` |
| `href` | captured link path with any `?query` stripped (`?hmb_source=search_bar` in all 5) |
| `name` | `.product-title` text |
| `platform_icons` | `hb-<token>` icon classes in captured order, delivery first (e.g. `["steam","windows","osx","linux"]`) |
| `delivery_separator` | `true` where the markup renders the `\|` separator between delivery and platform icons |
| `discount_pct` | integer from `.product-discount-amount` (`-90%` → `90`), else `null` |
| `price_display` **or** `action_text` | exactly one: the `.product-action-text` string — `CA$x.xx` prices become `price_display`, labels (`View`) become `action_text` |
| `img` | `{"local": "/static/assets/<sha256><ext>", "source_url": <captured url>}` via the asset index |

Optional keys, present only when captured: `description` (the bundle
row's `.product-description`) and `cta_badge` (`.cta-text` class token;
`earlyaccess` on the Spellrune row — matches its product `cta_badge`).

Captured rows for `portal`: Massive Unreal Engine Bundle (bundle, View),
Bridge Constructor Portal (−90%, CA$1.39), Zanzarah: The Hidden Portal
(−90%, CA$1.11), Spellrune: Realm of Portals (no discount, CA$11.49,
earlyaccess), Portal Knights (−80%, CA$5.56). Note the captured panel
price CA$1.39 differs from the lookup-payload price (138 minor) by one
cent — both values are kept verbatim in their own captures (panel strings
are display oracles, not derived).

Row images: the four `hb.imgix.net` 103x64 crops were already in the
capture's `url-map.json` (blobs reused); the bundle-row SVG
(`cdn.humblebundle.com/.../cf3858ca….svg`, 971 bytes) was fetched by
`tools/localize_seed_media.py` (which now also collects `suggest_orders`
row images) and mirrored to `clone/static/assets/` with provenance.

Backend: `hb_suggest_orders (query_key, ord, row_json)` — migration
`0006_suggest_orders`, seeded from `suggest_orders`, cleared+reseeded by
reset like every business table. `catalog_db.suggest()` returns a pinned
panel verbatim when the normalized query matches `query_key`; other
queries fall back deterministically (listing bundles whose name contains
the query in `category, ord` order, then products by `global_rank`,
capped at 5) in the same row shape. Existing databases pick the rows up
on the next `/__admin/reset` (the seed hook only runs on fresh files).
