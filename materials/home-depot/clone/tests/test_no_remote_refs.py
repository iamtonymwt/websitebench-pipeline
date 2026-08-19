"""Every shipped frozen page must make zero runtime requests to a remote origin
(no remote src/href-stylesheet/style-url/iframe). Data-only strings in meta/
ld+json do not trigger requests and are out of scope for this gate."""
import re
from pathlib import Path

PAGES = Path(__file__).resolve().parents[1] / "frontend" / "pages"


def _runtime_remote_refs(html: str) -> list[str]:
    hits = []
    hits += re.findall(r'\bsrc=["\'](https?://[^"\']+)', html)
    hits += re.findall(r'<link[^>]*rel=["\'](?:stylesheet|preload)["\'][^>]*href=["\'](https?://[^"\']+)', html)
    hits += re.findall(r'style="[^"]*url\((?:&quot;|["\']?)(https?://[^)&"\']+)', html)
    hits += re.findall(r'<iframe[^>]*src=["\'](https?://[^"\']+)', html)
    return hits


def test_all_pages_zero_runtime_remote_refs():
    offenders = {}
    for page in PAGES.glob("*.html"):
        refs = _runtime_remote_refs(page.read_text(encoding="utf-8"))
        if refs:
            offenders[page.name] = refs[:5]
    assert not offenders, f"remote runtime refs found: {offenders}"


def test_no_telemetry_hosts_in_pages():
    bad = ("px-cloud.net", "forter.com", "qualtrics.com", "quantummetric",
           "nr-data.net", "doubleclick", "getamigo.io")
    offenders = {}
    for page in PAGES.glob("*.html"):
        t = page.read_text(encoding="utf-8")
        hit = [h for h in bad if ("src=\"https://" + h) in t or ("src='https://" + h) in t]
        if hit:
            offenders[page.name] = hit
    assert not offenders, f"telemetry script refs: {offenders}"
