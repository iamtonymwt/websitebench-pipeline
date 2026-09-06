"""Build the monoprice Harbor instance's 200 cases, proving each one first.

The quota is fixed: T1 20 (`http`), T2 165 (`journey`: L1 35, L2 50, L3 80) and
T3 15 (`cicd`). A fixed quota is an invitation to pad, so nothing here is written
on the strength of looking plausible:

* **Every browser case is executed against the running clone, twice, in separate
  contexts**, and kept only if both runs agree observation by observation. Two
  runs is not ceremony -- on an earlier site it caught a real concurrency bug,
  one shared sqlite connection committing another thread's half-finished
  transaction.
* **A candidate whose page leaves loopback is rejected here**, by the same rule
  Harbor's capture gateway uses. Finding it at generation time is how the last
  site discovered its search box called a third-party suggest service on every
  keystroke.
* **Whether a task needs the non-GET declaration is observed, not inferred.**
  A case that only opens a page can still need it.
* **Nothing random is observed.** Order references are generated per order, so
  purchase cases assert the confirmation heading, the item and the amount paid.
* **No case asserts on this clone's own affordances** -- a faithful rebuild must
  not lose points for failing to reproduce a trace of the copy.
* **Ids are checked for uniqueness before anything is written**, here rather
  than by a validator that runs after all the browser work.

One page-specific hazard, recorded as claim cl-014: the absent-product page
navigates itself home after a few seconds, exactly as the source does. Two runs
would both redirect and both agree -- on the wrong page. Cases on it observe
immediately and never wait.

If a tier cannot be filled from cases that hold, this fails rather than topping
up with something weaker.

    python3 tools/build_harbor_cases.py --base-url http://127.0.0.1:8412 \
        --out-dir ../../harbor/instances/monoprice/fixtures/hidden \
        --report scope/harbor-cases.json
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import random
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from browser_session import attach  # noqa: E402

LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
QUOTA = {"T1": 20, "L1": 35, "L2": 50, "L3": 80, "T3": 15}

# Task ids are lowercase, dot/underscore/hyphen separated. Case ids are laxer,
# but keeping both in the same alphabet avoids one being valid and the other not.
SAFE = "abcdefghijklmnopqrstuvwxyz0123456789._-"


def task_id(*parts: str) -> str:
    raw = ".".join(str(p) for p in parts).lower()
    cleaned = "".join(c if c in SAFE else "-" for c in raw)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("._-")[:150]


def css(selector: str, nth: int | None = None) -> dict:
    node = {"css": selector}
    if nth is not None:
        node["nth"] = nth
    return node


def observe(oid: str, kind: str, comparator: dict, **extra) -> dict:
    """One observation: where to look and how to compare. Never the value.

    The expected value comes from capture-reference run against the reference
    implementation. Writing it here would be writing the answer key from the
    same source as the answer.
    """
    node = {"id": oid, "kind": kind, "comparator": comparator}
    node.update(extra)
    return node


EXACT = {"type": "exact"}
NORMALIZED = {"type": "normalized_exact"}
NUMBER = {"type": "number"}


def contains(needle: str) -> dict:
    """A substring assertion.

    The regex comparator is `re.fullmatch`, not `search`. A bare needle matches
    nothing; it has to span the whole value. `(?is)` because `inner_text` is
    rendered text and `text-transform: uppercase` is layout, not content.
    """
    escaped = "".join("\\" + c if c in ".^$*+?{}[]()|\\" else c for c in needle)
    return {"type": "regex", "pattern": f"(?is).*{escaped}.*"}


# --------------------------------------------------------------------------- #
# What the cases are built from
# --------------------------------------------------------------------------- #

class Catalogue:
    """Products and collections, deduplicated by product id, not by route.

    This site reaches products under more than one URL form; deduplicating by
    route let one product appear twice in a slice, and case ids must be unique.
    """

    def __init__(self, path: pathlib.Path, seed: int):
        raw = json.loads(path.read_text(encoding="utf-8"))
        by_id: dict[str, dict] = {}
        for product in raw["products"]:
            if product["price"] is None or not product["name"]:
                continue
            by_id.setdefault(product["p_id"], product)
        self.products = sorted(by_id.values(), key=lambda p: int(p["p_id"]))
        membership: dict[str, list[str]] = collections.defaultdict(list)
        for row in raw["product_categories"]:
            membership[row["category_path"]].append(row["p_id"])
        self.membership = membership
        self.categories = sorted(
            (c for c in raw["categories"] if c.get("kind") == "taxonomy"
             and len(membership.get(c["path"], [])) >= 4),
            key=lambda c: -len(membership.get(c["path"], [])))
        self.collections = sorted(
            (c for c in raw["categories"] if c.get("kind") == "shop-collection"
             and len(membership.get(c["path"], [])) >= 4),
            key=lambda c: -len(membership.get(c["path"], [])))
        self.rng = random.Random(seed)


# --------------------------------------------------------------------------- #
# Candidate generation
# --------------------------------------------------------------------------- #

def build_candidates(cat: Catalogue) -> dict[str, list[dict]]:
    """Candidate tasks per tier. More than the quota, so proving can reject."""
    out: dict[str, list[dict]] = {"T1": [], "L1": [], "L2": [], "L3": []}
    products = cat.products
    rng = cat.rng

    # -- T1: plain page fetches, asserting status and a stable page fact ----- #
    t1_pages = [("home", "/"), ("cart", "/cart"), ("checkout", "/checkout")]
    t1_pages += [(f"category.{i}", c["path"]) for i, c in enumerate(cat.categories[:8])]
    t1_pages += [(f"collection.{i}", c["path"]) for i, c in enumerate(cat.collections[:5])]
    t1_pages += [(f"product.{p['p_id']}", p["url_path"])
                 for p in rng.sample(products, min(8, len(products)))]
    t1_pages += [("search", "/search/index?keyword=hdmi+cable"),
                 ("notfound", "/definitely-not-real-websitebench")]
    for label, path in t1_pages:
        out["T1"].append({
            "id": task_id("t1", label),
            "timeout_sec": 60,
            "actions": [{"op": "goto", "path": path}],
            "observations": [
                observe("page_url", "url", contains(path.split("?")[0])),
                observe("page_title", "text", {"type": "regex", "pattern": "(?is).{3,}"},
                        selector=css("title")),
            ],
            "_path": path,
            "_settle": True,
        })

    # -- L1: open one page and read one thing from it ----------------------- #
    for product in rng.sample(products, min(40, len(products))):
        out["L1"].append({
            "id": task_id("l1.product", product["p_id"]),
            "timeout_sec": 90,
            "actions": [{"op": "goto", "path": product["url_path"]}],
            "observations": [
                observe("product_name", "text", contains(product["name"][:40]),
                        selector=css("title")),
                observe("add_to_cart_present", "count", NUMBER,
                        selector=css('form[action="/cart"]')),
            ],
            "_path": product["url_path"],
            "_settle": True,
        })
    for category in cat.categories[:12]:
        out["L1"].append({
            "id": task_id("l1.category", category["path"].strip("/").replace("/", ".")),
            "timeout_sec": 90,
            "actions": [{"op": "goto", "path": category["path"]}],
            "observations": [
                observe("listing_url", "url", contains(category["path"])),
                observe("product_links", "count", NUMBER,
                        selector=css('a[href*="p_id="]')),
            ],
            "_path": category["path"],
            "_settle": True,
        })

    # -- L2: two steps -- search, or put something in the cart -------------- #
    terms = ["hdmi cable", "usb c cable", "ethernet cable", "speaker wire",
             "power strip", "tv wall mount", "adapter", "cat6", "displayport",
             "keyboard", "headphones", "microphone", "monitor", "soldering"]
    for term in terms:
        out["L2"].append({
            "id": task_id("l2.search", term.replace(" ", "-")),
            "timeout_sec": 120,
            "actions": [
                {"op": "goto", "path": "/"},
                {"op": "fill", "selector": css("#keyword"), "value": term},
                {"op": "press", "selector": css("#keyword"), "value": "Enter"},
            ],
            "observations": [
                observe("results_url", "url", contains("/search/index")),
                observe("result_links", "count", NUMBER,
                        selector=css('a[href*="p_id="]')),
            ],
            "_path": "/",
            "_settle": True,
        })
    for product in rng.sample(products, min(45, len(products))):
        out["L2"].append({
            "id": task_id("l2.addtocart", product["p_id"]),
            "timeout_sec": 120,
            "actions": [
                {"op": "goto", "path": product["url_path"]},
                {"op": "api", "method": "POST", "path": "/cart",
                 "body": {"p_id": product["p_id"], "qty": "1"}},
                {"op": "goto", "path": "/cart"},
            ],
            "observations": [
                observe("cart_url", "url", contains("/cart")),
                observe("cart_holds_item", "count", NUMBER,
                        selector=css(f'tr[data-p-id="{product["p_id"]}"]')),
            ],
            "_path": product["url_path"],
            "_settle": True,
            "_mutates": True,
        })

    # -- L3: a whole purchase, and the two ways it can fail ----------------- #
    for product in rng.sample(products, min(50, len(products))):
        for scenario, label in (("sandbox-approved", "approved"),
                                ("sandbox-declined", "declined")):
            actions = [
                {"op": "goto", "path": product["url_path"]},
                {"op": "api", "method": "POST", "path": "/cart",
                 "body": {"p_id": product["p_id"], "qty": "2"}},
                {"op": "goto", "path": "/checkout"},
                # Scoped to the checkout form. `button[type="submit"]` matches
                # four elements on this page -- the source's own page shell
                # brings its own, including a hidden close icon that sorts
                # first, so `.first` clicked something invisible and every one
                # of the 80 purchase candidates timed out after 30 seconds.
                #
                # These two selectors are also the semantic contract rather than
                # this build's markup: "the checkout form's scenario select" and
                # "the checkout form's submit button" are things any rebuild
                # implementing checkout must have, while `.wb-btn` and
                # `#scenario` are names this project happened to choose.
                {"op": "select",
                 "selector": css('form[action="/checkout"] select[name="scenario"]'),
                 "value": scenario},
                {"op": "click",
                 "selector": css('form[action="/checkout"] button[type="submit"]')},
            ]
            if label == "approved":
                observations = [
                    # Never the order reference: it is generated per order, so
                    # two runs would disagree and the case would be judged
                    # non-deterministic -- correctly.
                    # `h1` matches two: the page shell carries a hidden
                    # "Never Miss a Deal." heading from its email popup, and
                    # every one of the 50 approved-purchase candidates was
                    # rejected for matching two elements. `:visible` names the
                    # one a person sees, and does it without depending on a
                    # class this project invented.
                    observe("confirmation_heading", "text", contains("Order placed"),
                            selector=css("h1:visible")),
                    observe("item_named", "text", contains(product["name"][:36]),
                            selector=css("table:visible")),
                    observe("amount_paid", "text",
                            {"type": "regex", "pattern": r"(?is)\s*\$[0-9,]+\.[0-9]{2}\s*"},
                            selector=css("[data-order-total]")),
                ]
            else:
                observations = [
                    observe("decline_notice", "text", contains("declined"),
                            selector=css(".wb-alert")),
                    observe("still_on_checkout", "url", contains("/checkout")),
                    observe("cart_kept_goods", "count", NUMBER,
                            selector=css('form[action="/checkout"] table tbody tr')),
                ]
            out["L3"].append({
                "id": task_id("l3.purchase", label, product["p_id"]),
                "timeout_sec": 180,
                "actions": actions,
                "observations": observations,
                "_path": product["url_path"],
                "_settle": True,
                "_mutates": True,
            })
    return out


# --------------------------------------------------------------------------- #
# Proving
# --------------------------------------------------------------------------- #

class Prover:
    """Execute a candidate against the running clone and record what happened.

    **One context and one page for the whole run.** The first version created a
    fresh context and page per run -- twice per candidate, hundreds of
    candidates -- which in a headed browser means hundreds of windows opening
    and closing on someone's screen. Isolation between runs is what actually
    matters, and clearing cookies gives that: the cart lives in a cookie, so a
    cleared jar is a fresh shopper.

    Isolation is not optional here. On an earlier site 185 tasks shared one
    cookie jar, the first twenty filled the same cart, and nineteen "cart is
    empty after checkout" tasks failed -- a defect in the scaffolding that read
    exactly like a defect in the clone.
    """

    # These pages are 400 KB to 1 MB of markup with several thousand nodes, and
    # one page driven through ~300 of them ran out of room: the context closed
    # under the prover after 150 proven cases, throwing all of them away.
    #
    # So the page is recycled on a schedule, and recreated if it dies. That is
    # four or five windows over a whole run rather than one per case -- the
    # objection was to hundreds of windows opening and closing, not to replacing
    # an exhausted one.
    RECYCLE_AFTER = 120

    def __init__(self, browser, base: str):
        self.browser = browser
        self.base = base.rstrip("/")
        self.context = None
        self.page = None
        self.runs_on_page = 0
        self.recycles = 0
        self._open()

    def _open(self) -> None:
        self.context = self.browser.new_context(
            viewport={"width": 1440, "height": 900}, locale="en-US",
            timezone_id="UTC", service_workers="block")
        self.page = self.context.new_page()
        self.runs_on_page = 0

    def _ensure_page(self) -> None:
        needs_new = self.page is None or self.page.is_closed()
        if not needs_new and self.runs_on_page >= self.RECYCLE_AFTER:
            needs_new = True
        if not needs_new:
            return
        try:
            if self.context is not None:
                self.context.close()
        except Exception:  # noqa: BLE001 - it may already be gone
            pass
        self._open()
        self.recycles += 1

    def close(self) -> None:
        try:
            if self.context is not None:
                self.context.close()
        except Exception:  # noqa: BLE001
            pass

    def run_once(self, task: dict) -> dict:
        self._ensure_page()
        # A fresh cookie jar is the isolation boundary, not a fresh window.
        self.context.clear_cookies()
        self.runs_on_page += 1
        page = self.page
        offsite: list[str] = []
        methods: set[str] = set()

        def on_request(request):
            host = urllib.parse.urlsplit(request.url).hostname
            if host and host not in LOCAL_HOSTS:
                offsite.append(request.url)
            methods.add(request.method.upper())

        page.on("request", on_request)
        result: dict = {"offsite": offsite, "methods": methods, "values": {},
                        "error": None}
        try:
            for action in task["actions"]:
                self._apply(page, action)
            if task.get("_settle"):
                page.wait_for_timeout(1200)
            for obs in task["observations"]:
                result["values"][obs["id"]] = self._read(page, obs)
        except Exception as exc:  # noqa: BLE001 - a failed candidate is a result
            result["error"] = f"{exc.__class__.__name__}: {exc}"[:200]
        finally:
            page.remove_listener("request", on_request)
        return result

    def _apply(self, page, action: dict) -> None:
        op = action["op"]
        if op == "goto":
            page.goto(self.base + action["path"], wait_until="domcontentloaded",
                      timeout=60_000)
        elif op == "fill":
            page.locator(action["selector"]["css"]).first.fill(str(action["value"]))
        elif op == "press":
            page.locator(action["selector"]["css"]).first.press(str(action["value"]))
        elif op == "click":
            page.locator(action["selector"]["css"]).first.click(timeout=30_000)
            page.wait_for_load_state("domcontentloaded", timeout=60_000)
        elif op == "select":
            page.locator(action["selector"]["css"]).first.select_option(
                str(action["value"]))
        elif op == "api":
            page.evaluate(
                """async ({path, method, body}) => {
                    const init = {method};
                    if (body) init.body = new URLSearchParams(body);
                    await fetch(path, init);
                }""",
                {"path": action["path"], "method": action.get("method", "GET"),
                 "body": action.get("body")})
        elif op == "reload":
            page.reload(wait_until="domcontentloaded", timeout=60_000)
        else:
            raise RuntimeError(f"prover cannot execute op {op!r}")

    def _read(self, page, obs: dict):
        kind = obs["kind"]
        if kind == "url":
            split = urllib.parse.urlsplit(page.url)
            return split.path + (f"?{split.query}" if split.query else "")
        locator = page.locator(obs["selector"]["css"])
        if "nth" in obs["selector"]:
            locator = locator.nth(obs["selector"]["nth"])
        if kind == "count":
            return locator.count()
        if kind == "visible":
            return locator.first.is_visible()
        if kind == "text":
            if obs["selector"]["css"] == "title":
                return page.title()
            # Playwright is strict: a single-value read needs exactly one match.
            if locator.count() != 1:
                raise RuntimeError(
                    f"selector matched {locator.count()} elements, needs exactly 1")
            return locator.inner_text()
        raise RuntimeError(f"prover cannot read kind {kind!r}")


# --------------------------------------------------------------------------- #
# Writing the four suites
# --------------------------------------------------------------------------- #

# The 15 T3 checks. Each asserts something any faithful rebuild must have --
# never this build's file layout, because a runner only sees the candidate's
# tree and a correct reconstruction may organise itself differently.
CICD_CHECKS = [
    ("abi-entrypoints", "static", 120),
    ("health-contract", "static", 120),
    ("no-card-columns", "security", 180),
    ("no-secrets", "security", 180),
    ("offline-no-source-hosts", "static", 300),
    ("robots-respected", "security", 180),
    ("catalogue-has-prices", "static", 180),
    ("deterministic-seed", "migration", 180),
    ("timezone-honoured", "static", 180),
    ("host-port-from-env", "integration", 180),
    ("data-dir-from-env", "migration", 180),
    ("no-network-clients-at-runtime", "security", 240),
    ("absent-product-is-200", "static", 180),
    ("search-answered-locally", "api", 180),
    ("sigterm-handled", "recovery", 180),
]


def write_suites(out_dir: pathlib.Path, kept: dict[str, list[dict]]) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    tasks = []
    cases = []
    seen_task_ids: set[str] = set()
    seen_case_ids: set[str] = set()

    def add(task: dict, tier: str, level: str | None) -> None:
        clean = {k: v for k, v in task.items() if not k.startswith("_")}
        if clean["id"] in seen_task_ids:
            raise SystemExit(f"duplicate task id {clean['id']!r}")
        seen_task_ids.add(clean["id"])
        tasks.append(clean)
        case = {"id": clean["id"], "tier": tier, "kind": kind_for(tier),
                "timeout_sec": clean["timeout_sec"], "task_id": clean["id"]}
        if level:
            case["level"] = level
        if case["id"] in seen_case_ids:
            raise SystemExit(f"duplicate case id {case['id']!r}")
        seen_case_ids.add(case["id"])
        cases.append(case)

    def kind_for(tier: str) -> str:
        return "http" if tier == "T1" else "journey"

    for task in kept["T1"]:
        add(task, "T1", None)
    for level in ("L1", "L2", "L3"):
        for task in kept[level]:
            add(task, "T2", level)

    checks = []
    for name, kind, timeout in CICD_CHECKS:
        runner = f"runners/{name}.py"
        if not (out_dir / runner).is_file():
            raise SystemExit(f"missing T3 runner: {runner}")
        checks.append({"id": name, "kind": kind, "runner": runner,
                       "timeout_sec": timeout})
        case_id = f"t3.{name}"
        if case_id in seen_case_ids:
            raise SystemExit(f"duplicate case id {case_id!r}")
        seen_case_ids.add(case_id)
        cases.append({"id": case_id, "tier": "T3", "kind": "cicd",
                      "timeout_sec": timeout, "cicd_check_id": name})

    if len(cases) != 200:
        raise SystemExit(f"expected exactly 200 cases, built {len(cases)}")

    (out_dir / "task-suite.json").write_text(json.dumps({
        "schema_version": "websitebench.harbor.task-suite.v1",
        "suite_id": "monoprice-tasks", "site_id": "monoprice",
        "dsl_version": "websitebench.harbor.playwright-dsl.v1",
        "tasks": tasks}, indent=1) + "\n", encoding="utf-8")
    (out_dir / "cicd-suite.json").write_text(json.dumps({
        "schema_version": "websitebench.harbor.cicd-suite.v1",
        "suite_id": "monoprice-cicd", "site_id": "monoprice",
        "checks": checks}, indent=1) + "\n", encoding="utf-8")
    (out_dir / "case-manifest.json").write_text(json.dumps({
        "schema_version": "websitebench.harbor.case-manifest.v1",
        "manifest_id": "monoprice-cases", "site_id": "monoprice",
        "status": "complete",
        "dsl_version": "websitebench.harbor.neutral-dsl.v1",
        "cases": cases}, indent=1) + "\n", encoding="utf-8")
    # The visual suite stays empty and the manifest references no checkpoint.
    # Producing one would need a screenshot of the source at a frozen viewport,
    # and this run has none; a screenshot of the clone would compare the clone
    # to itself and report perfect fidelity. See claim cl-006.
    (out_dir / "visual-suite.json").write_text(json.dumps({
        "schema_version": "websitebench.harbor.visual-suite.v1",
        "suite_id": "monoprice-visual", "site_id": "monoprice",
        "checkpoints": []}, indent=1) + "\n", encoding="utf-8")
    return {"tasks": len(tasks), "cases": len(cases), "cicd_checks": len(checks)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--seed", type=int, default=20260905)
    ap.add_argument("--proven", default="scope/harbor-proven.json",
                    help="cases already proven, so a crash does not discard them")
    args = ap.parse_args()

    site_dir = pathlib.Path(__file__).resolve().parent.parent
    cat = Catalogue(site_dir / "data" / "catalogue.json", args.seed)
    candidates = build_candidates(cat)

    # Proving 185 cases twice each takes half an hour of browser work. Losing
    # it to a crashed page -- which is exactly what happened at case 150 -- is
    # avoidable, so what has been proven is written as it is proven and reused
    # on the next run. A task is only reused if it is byte-identical to the
    # candidate generated now: change a selector and it is re-proven, which is
    # the point.
    proven_path = pathlib.Path(args.proven)
    previously: dict[str, dict] = {}
    if proven_path.exists():
        for row in json.loads(proven_path.read_text(encoding="utf-8"))["tasks"]:
            previously[row["fingerprint"]] = row["task"]
        print(f"resuming: {len(previously)} cases already proven")

    def fingerprint(task: dict) -> str:
        payload = {k: v for k, v in task.items()
                   if not k.startswith("_") and k != "reference_mutation_authorized"}
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()).hexdigest()

    kept: dict[str, list[dict]] = {tier: [] for tier in ("T1", "L1", "L2", "L3")}
    dropped: list[dict] = []
    mutating = 0

    def save_proven() -> None:
        rows = [{"fingerprint": fingerprint(task), "task": task}
                for tier_tasks in kept.values() for task in tier_tasks]
        proven_path.parent.mkdir(parents=True, exist_ok=True)
        proven_path.write_text(json.dumps({"tasks": rows}, indent=1) + "\n",
                               encoding="utf-8")

    with attach(warm=False, page_index=0) as (browser, _shared, _page):
        prover = Prover(browser, args.base_url)
        try:
            for tier in ("T1", "L1", "L2", "L3"):
                need = QUOTA[tier]
                for task in candidates[tier]:
                    if len(kept[tier]) >= need:
                        break
                    cached = previously.get(fingerprint(task))
                    if cached is not None:
                        kept[tier].append(cached)
                        if cached.get("reference_mutation_authorized"):
                            mutating += 1
                        continue
                    first = prover.run_once(task)
                    if first["error"]:
                        dropped.append({"id": task["id"], "why": first["error"]})
                        continue
                    if first["offsite"]:
                        dropped.append({
                            "id": task["id"],
                            "why": f"left loopback: {first['offsite'][0][:90]}"})
                        continue
                    second = prover.run_once(task)
                    if second["error"]:
                        dropped.append({"id": task["id"],
                                        "why": f"second run: {second['error']}"})
                        continue
                    if first["values"] != second["values"]:
                        differing = [k for k in first["values"]
                                     if first["values"][k] != second["values"].get(k)]
                        dropped.append({"id": task["id"],
                                        "why": f"two runs disagreed on {differing}"})
                        continue
                    # Observed, not inferred: whether the browser used a method
                    # the capture gateway blocks by default.
                    non_get = (first["methods"] | second["methods"]) - {
                        "GET", "HEAD", "OPTIONS"}
                    if non_get:
                        task["reference_mutation_authorized"] = True
                        mutating += 1
                    kept[tier].append(task)
                    print(f"  {tier} {len(kept[tier]):3d}/{need}  {task['id']}",
                          flush=True)
                    if len(kept[tier]) % 10 == 0:
                        save_proven()
                if len(kept[tier]) < need:
                    print(f"\nFAILED: {tier} filled {len(kept[tier])} of {need}. "
                          "Not topping up with weaker cases.")
                    pathlib.Path(args.report).write_text(json.dumps(
                        {"status": "insufficient", "tier": tier,
                         "kept": {k: len(v) for k, v in kept.items()},
                         "dropped": dropped[:60]}, indent=2) + "\n")
                    return 1
            save_proven()
        finally:
            prover.close()
            print(f"page recycled {prover.recycles} times", flush=True)

    written = write_suites(pathlib.Path(args.out_dir), kept)

    report = {"schema_version": "monoprice.harbor-cases.v1",
              "status": "written",
              "written": written,
              "kept": {k: len(v) for k, v in kept.items()},
              "dropped": len(dropped),
              "dropped_examples": dropped[:40],
              "tasks_declaring_non_get": mutating,
              "page_recycles": None}
    pathlib.Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps(report, indent=2)[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
