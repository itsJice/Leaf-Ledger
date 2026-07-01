"""HTTP supplier recon.

Recon is the cheap first pass before writing a supplier adapter. It tells us
whether a site looks static, XHR-driven, sitemap-friendly, or likely to need
browser automation.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from html import unescape
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .crawl_engine import SharedCrawlEngine


@dataclass
class SupplierReconReport:
    start_url: str
    final_url: str
    status_code: Optional[int]
    sitemap_url: str
    sitemap_status_code: Optional[int]
    title: str
    nav_links: list[dict] = field(default_factory=list)
    category_candidates: list[dict] = field(default_factory=list)
    product_url_patterns: list[str] = field(default_factory=list)
    product_link_candidates: list[dict] = field(default_factory=list)
    form_summaries: list[dict] = field(default_factory=list)
    script_sources: list[str] = field(default_factory=list)
    image_patterns: list[str] = field(default_factory=list)
    json_ld_types: list[str] = field(default_factory=list)
    xhr_hints: list[str] = field(default_factory=list)
    pagination_hints: list[str] = field(default_factory=list)
    likely_strategy: str = "unknown"
    difficulty_rank: str = "C"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def _same_host(url: str, candidate: str) -> bool:
    base_host = urlparse(url).netloc.lower().replace("www.", "")
    candidate_host = urlparse(candidate).netloc.lower().replace("www.", "")
    return bool(candidate_host) and candidate_host == base_host


def _looks_like_category(text: str, href: str) -> bool:
    haystack = f"{text} {href}".lower()
    return any(word in haystack for word in [
        "category", "collection", "catalog", "shop", "products", "decor", "flowers",
        "foliage", "containers", "vases", "christmas", "fall", "garden",
    ])


def _looks_like_product(text: str, href: str) -> bool:
    path = urlparse(href).path.lower()
    filename = path.rsplit("/", 1)[-1]
    if "_ss" in filename:
        return False
    haystack = f"{text} {path}".lower()
    if any(word in haystack for word in ["product", "sku", "item"]):
        return True
    return bool(re.search(r"[a-z]{1,8}\d{2,}[a-z0-9-]*\.(html|php|aspx)$", filename))


def _looks_like_asset_url(value: str) -> bool:
    lowered = value.lower()
    if any(host in lowered for host in [
        "ajax.googleapis.com",
        "cdnjs.cloudflare.com",
        "code.jquery.com",
        "fonts.googleapis.com",
        "googletagmanager.com",
        "maps.googleapis.com",
        "unpkg.com",
    ]):
        return True
    return bool(re.search(r"\.(?:css|js|map|png|jpe?g|gif|svg|webp)(?:[?&#]|$)", lowered))


def _link_pattern(url: str) -> str:
    path = urlparse(url).path
    path = re.sub(r"\d+", "{n}", path)
    path = re.sub(r"[A-Z]{2,}\d+[A-Z0-9-]*", "{sku}", path, flags=re.I)
    return path


def analyze_html(start_url: str, final_url: str, status_code: Optional[int], html: str, sitemap_status_code: Optional[int]) -> SupplierReconReport:
    soup = BeautifulSoup(html or "", "html.parser")
    title = _clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    sitemap_url = urljoin(final_url or start_url, "/sitemap.xml")

    nav_links: list[dict] = []
    category_candidates: list[dict] = []
    product_candidates: list[dict] = []
    product_patterns: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = urljoin(final_url or start_url, a.get("href") or "")
        if not _same_host(final_url or start_url, href):
            continue
        text = _clean_text(a.get_text(" ", strip=True))
        record = {"text": text[:100], "url": href}
        if len(nav_links) < 40:
            nav_links.append(record)
        if _looks_like_category(text, href) and len(category_candidates) < 30:
            category_candidates.append(record)
        if _looks_like_product(text, href) and len(product_candidates) < 30:
            product_candidates.append(record)
            product_patterns.add(_link_pattern(href))

    form_summaries = []
    for form in soup.find_all("form")[:10]:
        fields = [
            node.get("name") or node.get("id") or node.get("type") or ""
            for node in form.find_all(["input", "select", "textarea"])[:20]
        ]
        form_summaries.append({
            "action": urljoin(final_url or start_url, form.get("action") or ""),
            "method": (form.get("method") or "get").lower(),
            "fields": [f for f in fields if f],
        })

    script_sources = [urljoin(final_url or start_url, s.get("src")) for s in soup.find_all("script", src=True)[:30]]
    page_text = html or ""
    xhr_hint_set = {
        match
        for match in re.findall(r"[\w./:-]+(?:/api/|/ajax/|get_products|products\.php|search\.php)[\w./?=&:-]*", page_text, flags=re.I)
        if not _looks_like_asset_url(match)
    }
    if re.search(r"var\s+pageId\s*=", page_text) and re.search(r"var\s+pageType\s*=\s*[\"']products[\"']", page_text):
        xhr_hint_set.add("storefront_product_grid: pageId/pageType variables")
    xhr_hints = sorted(xhr_hint_set)[:30]
    pagination_hints = sorted(set(re.findall(r"(?:load more|next|pagination|page\s*[=:]\s*['\"]?\d+|skip\s*[=:])", page_text, flags=re.I)))[:20]

    image_patterns = sorted({
        _link_pattern(urljoin(final_url or start_url, img.get("src") or ""))
        for img in soup.find_all("img")
        if img.get("src")
    })[:20]

    json_ld_types: list[str] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
        except Exception:
            continue
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if isinstance(entry, dict) and entry.get("@type"):
                json_ld_types.append(str(entry["@type"]))

    likely_strategy = "http_static"
    difficulty_rank = "B"
    notes: list[str] = []
    if xhr_hints:
        likely_strategy = "http_xhr"
        difficulty_rank = "A"
        notes.append("XHR/API hints found; inspect network endpoint before using browser automation.")
    if not product_candidates and pagination_hints:
        likely_strategy = "browser_or_xhr"
        difficulty_rank = "C"
        notes.append("Pagination/load-more hints found but product links were not visible in initial HTML.")
    if sitemap_status_code and 200 <= sitemap_status_code < 400:
        notes.append("Sitemap exists; use it as a candidate URL source.")
    if json_ld_types:
        notes.append("JSON-LD exists; extract structured product metadata where useful.")

    return SupplierReconReport(
        start_url=start_url,
        final_url=final_url,
        status_code=status_code,
        sitemap_url=sitemap_url,
        sitemap_status_code=sitemap_status_code,
        title=title,
        nav_links=nav_links,
        category_candidates=category_candidates,
        product_url_patterns=sorted(product_patterns),
        product_link_candidates=product_candidates,
        form_summaries=form_summaries,
        script_sources=script_sources,
        image_patterns=image_patterns,
        json_ld_types=sorted(set(json_ld_types)),
        xhr_hints=xhr_hints,
        pagination_hints=pagination_hints,
        likely_strategy=likely_strategy,
        difficulty_rank=difficulty_rank,
        notes=notes,
    )


async def run_http_recon(start_url: str) -> SupplierReconReport:
    engine = SharedCrawlEngine()
    page = await engine.fetch(start_url)
    sitemap_url = urljoin(page.url or start_url, "/sitemap.xml")
    sitemap_status_code = None
    try:
        sitemap_response = await engine.fetch(sitemap_url)
        sitemap_status_code = sitemap_response.status_code
    except requests.RequestException:
        sitemap_status_code = None
    return analyze_html(start_url, page.url, page.status_code, page.html, sitemap_status_code)
