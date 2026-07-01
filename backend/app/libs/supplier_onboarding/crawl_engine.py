"""Shared crawl helpers for supplier onboarding.

This module intentionally starts small. It gives us a stable local interface
while we evaluate how much Crawlee should own long term.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Callable, Optional

import requests


@dataclass
class CrawlPageResult:
    url: str
    status_code: Optional[int] = None
    html: str = ""
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status_code is not None and 200 <= self.status_code < 400


@dataclass
class SharedCrawlEngine:
    """HTTP-first crawl engine with retries, dedupe, and polite delay."""

    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    timeout_seconds: int = 20
    retry_attempts: int = 3
    retry_delay_seconds: float = 1.0
    request_delay_seconds: float = 0.25
    session: requests.Session = field(default_factory=requests.Session)

    def __post_init__(self) -> None:
        self.session.headers.update({"User-Agent": self.user_agent})

    async def fetch(self, url: str) -> CrawlPageResult:
        """Fetch one URL with retry. Network work runs in a thread."""

        last_error: Optional[str] = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = await asyncio.to_thread(self.session.get, url, timeout=self.timeout_seconds, allow_redirects=True)
                return CrawlPageResult(url=response.url, status_code=response.status_code, html=response.text)
            except Exception as exc:
                last_error = str(exc)
                if attempt < self.retry_attempts:
                    await asyncio.sleep(self.retry_delay_seconds * attempt)
        return CrawlPageResult(url=url, error=last_error or "Unknown fetch error")

    async def fetch_many(
        self,
        urls: list[str],
        *,
        limit: Optional[int] = None,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[CrawlPageResult]:
        """Fetch URLs sequentially with dedupe and progress callbacks."""

        seen: set[str] = set()
        unique_urls: list[str] = []
        for url in urls:
            if url and url not in seen:
                seen.add(url)
                unique_urls.append(url)
            if limit and len(unique_urls) >= limit:
                break

        results: list[CrawlPageResult] = []
        total = len(unique_urls)
        for index, url in enumerate(unique_urls, start=1):
            result = await self.fetch(url)
            results.append(result)
            if on_progress:
                on_progress(index, total, f"Fetched {index} of {total}")
            await asyncio.sleep(self.request_delay_seconds)
        return results


async def run_crawlee_smoke(url: str) -> dict:
    """Prove Crawlee can run locally without Apify hosting.

    This function is deliberately tiny. It lets us validate the installed
    Crawlee package while keeping our production crawl interface independent.
    """

    from crawlee.crawlers import BeautifulSoupCrawler

    crawler = BeautifulSoupCrawler(max_requests_per_crawl=1)
    pages: list[dict] = []

    @crawler.router.default_handler
    async def request_handler(context) -> None:
        title = context.soup.title.get_text(strip=True) if context.soup.title else ""
        pages.append({"url": context.request.url, "title": title})

    stats = await crawler.run([url])
    return {"pages": pages, "stats": str(stats)}
