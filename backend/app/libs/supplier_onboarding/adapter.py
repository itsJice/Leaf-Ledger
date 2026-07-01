"""Supplier adapter contract.

Supplier adapters should contain supplier-specific knowledge only. Shared
mechanics such as retry, dedupe, queueing, crawl state, and progress belong in
the shared crawl engine.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from app.libs.scraper_base import ScrapedProduct


@dataclass(frozen=True)
class SupplierCredentials:
    username: str
    password: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SupplierCategory:
    label: str
    url: str
    section: str = "General"
    slug: Optional[str] = None
    estimated_products: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


class SupplierAdapter(ABC):
    """Base shape every supplier should implement."""

    supplier_key: str
    supplier_name: str

    @abstractmethod
    async def login(self, credentials: SupplierCredentials) -> Any:
        """Return an authenticated session/client with account-specific pricing."""

    @abstractmethod
    async def discover_categories(self, session: Any) -> list[SupplierCategory]:
        """Return category candidates ready to store in supplier_category_index."""

    @abstractmethod
    async def collect_product_urls(self, session: Any, category: SupplierCategory, *, limit: Optional[int] = None) -> list[str]:
        """Return product detail URLs from one category/listing source."""

    @abstractmethod
    async def parse_product_detail(self, session: Any, url: str, html: str) -> dict[str, Any]:
        """Return supplier-specific raw product data extracted from one detail page."""

    @abstractmethod
    def normalize_product(self, raw: dict[str, Any]) -> ScrapedProduct:
        """Map supplier-specific raw detail data into the shared product contract."""
