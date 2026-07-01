from app.libs.supplier_identity import resolve_scraper_key


def test_resolve_scraper_key_prefers_and_normalizes_explicit_key():
    assert resolve_scraper_key("Unrelated name", " Select ") == "select_artificial"
    assert resolve_scraper_key("Accent Decor", "custom_adapter") == "custom_adapter"


def test_resolve_scraper_key_supports_legacy_name_fallbacks():
    assert resolve_scraper_key("Accent Decor") == "accent_decor"
    assert resolve_scraper_key("Select Artificials") == "select_artificial"
    assert resolve_scraper_key("Vickerman Company") == "vickerman"


def test_resolve_scraper_key_returns_none_for_unknown_supplier():
    assert resolve_scraper_key("Example Supplier") is None
    assert resolve_scraper_key(None) is None
