"""Shared supplier identity helpers used by supplier and extraction APIs."""

from typing import Optional


SCRAPER_KEY_ALIASES = {
    "accent": "accent_decor",
    "select": "select_artificial",
    "select_artificials": "select_artificial",
}

SCRAPER_NAME_MATCHES = (
    ("allstate", "allstate"),
    ("accent", "accent_decor"),
    ("regency", "regency"),
    ("select artificial", "select_artificial"),
    ("select artificials", "select_artificial"),
    ("vickerman", "vickerman"),
)


def resolve_scraper_key(
    supplier_name: Optional[str],
    scraper_key: Optional[str] = None,
) -> Optional[str]:
    """Normalize an explicit key or infer one for legacy supplier records."""
    key = (scraper_key or "").strip().lower()
    if key:
        return SCRAPER_KEY_ALIASES.get(key, key)

    normalized_name = (supplier_name or "").lower()
    for fragment, resolved_key in SCRAPER_NAME_MATCHES:
        if fragment in normalized_name:
            return resolved_key
    return None
