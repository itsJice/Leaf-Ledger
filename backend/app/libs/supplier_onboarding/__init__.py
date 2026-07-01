"""Supplier onboarding framework.

This package holds the repeatable pieces for onboarding many supplier
catalogs: adapter contracts, recon reports, and shared crawl helpers.
Existing supplier scrapers can move here gradually after the pattern proves
itself on the next suppliers.
"""

from .adapter import SupplierAdapter, SupplierCategory, SupplierCredentials
from .crawl_engine import CrawlPageResult, SharedCrawlEngine
from .recon import SupplierReconReport, run_http_recon

__all__ = [
    "CrawlPageResult",
    "SharedCrawlEngine",
    "SupplierAdapter",
    "SupplierCategory",
    "SupplierCredentials",
    "SupplierReconReport",
    "run_http_recon",
]
