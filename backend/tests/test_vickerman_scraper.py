import asyncio
import json
import time

from app.libs import vickerman_scraper
from app.libs.vickerman_scraper import (
    VICKERMAN_PRODUCT_SELECTOR_SEEDS,
    _catalog_totals,
    _merge_category_tags,
    _discover_category_links,
    _image_url,
    _item_number_from_detail_url,
    _parse_detail_page,
    _parse_total_items,
    _product_type_candidates,
    _seed_categories,
    _validation_category_order,
)


def test_parse_vickerman_detail_model():
    model = {
        "CurrentItem": {
            "ItemNumber": "K160920",
            "Description": '2\' x 20" Aqua Fir Tree 84Tips',
            "WebDescription": "Aqua fir tree description",
            "Upc": "123456789",
            "ProductType": "Christmas Tree",
            "ImageUrl": "https://images.vickerman.com/K160920_1000.jpg",
            "Image1Url": "K160920_ALT_1000.jpg",
            "QtyPerPack": 2,
            "InnerPackQty": 1,
            "QtyMin": 1,
            "QtyInStock": 12,
            "FutureStock": 5,
            "Price": 20.29,
            "Height": 24,
            "Width": 20,
            "Length": 20,
            "Weight": 3.5,
            "PrimaryMaterial": "PVC",
        },
        "ProductOptions": [],
    }
    html = f"""
    <html><body>
    <script>
      var model = {json.dumps(model)};
      if (model.CurrentItem) {{}}
    </script>
    </body></html>
    """

    product = _parse_detail_page(
        html,
        "https://www.vickerman.com/products/details?item=K160920",
        {"section": "Christmas Trees", "label": "Colorful Trees"},
    )

    assert product.sku == "K160920"
    assert product.name == '2\' x 20" Aqua Fir Tree 84Tips'
    assert product.base_price == 20.29
    assert product.availability == "12"
    assert product.availability_note == "In stock: 12; future stock: 5"
    assert product.case_qty == 2
    assert product.box_qty == 1
    assert product.height_in == 24
    assert product.weight_lb == 3.5
    assert product.material == "PVC"
    assert product.photo_url == "https://images.vickerman.com/K160920_1000.jpg"
    assert product.image_urls == [
        "https://images.vickerman.com/K160920_1000.jpg",
        "https://images.vickerman.com/K160920_ALT_1000.jpg",
    ]
    assert product.raw["source_section"] == "Christmas Trees"
    assert product.raw["source_category"] == "Colorful Trees"
    assert product.raw["source_category_path"] == "Christmas Trees > Colorful Trees"
    assert product.raw["category_tags"] == [
        "Christmas Trees",
        "Colorful Trees",
        "Christmas Trees > Colorful Trees",
    ]
    assert product.raw["vickerman_model"]["CurrentItem"]["ItemNumber"] == "K160920"


def test_parse_vickerman_detail_does_not_use_package_measurements_as_item_specs():
    model = {
        "CurrentItem": {
            "ItemNumber": "421087",
            "Description": '12x6x9" Gray Woven Round Pot HDPE',
            "WebDescription": "Container description",
            "ProductType": "Container",
            "ImageUrl": "https://images.vickerman.com/421080_1000.jpg",
            "QtyInStock": 14244,
            "SalePrice": 2.82,
            "Height": 9,
            "Width": 5.8,
            "Length": 12,
            "Weight": 0,
            "Packages": [
                {
                    "Weight": 680,
                    "Length": 99,
                    "Width": 48,
                    "Height": 37,
                }
            ],
        },
        "ProductOptions": [],
    }
    html = f"""
    <html><body>
    <script>
      var model = {json.dumps(model)};
      if (model.CurrentItem) {{}}
    </script>
    </body></html>
    """

    product = _parse_detail_page(
        html,
        "https://www.vickerman.com/products/details?item=421087",
        {"section": "Containers", "label": "Containers"},
    )

    assert product.height_in == 9
    assert product.width_in == 5.8
    assert product.length_in == 12
    assert product.weight_lb is None


def test_vickerman_image_url_repairs_missing_extension_dot():
    assert _image_url("QK257567jpg") == "https://images.vickerman.com/QK257567.jpg"
    assert _image_url("https://images.vickerman.com/QK257567jpg") == "https://images.vickerman.com/QK257567.jpg"


def test_vickerman_item_number_from_detail_url():
    assert _item_number_from_detail_url("https://www.vickerman.com/products/details?item=A805180") == "A805180"
    assert _item_number_from_detail_url("https://www.vickerman.com/products/details?sort=group") == ""


def test_vickerman_silhouette_image_adds_t_variant_fallback():
    model = {
        "CurrentItem": {
            "ItemNumber": "X23S230",
            "Description": '600Ltx30" WW LED Ball Wire Silhouette',
            "ProductType": "Wire Silhouette",
            "ImageUrl": "https://images.vickerman.com/X23S230_1000.jpg",
            "QtyInStock": 12,
            "Price": 49.16,
        },
        "ProductOptions": [],
    }
    html = f"""
    <html><body>
    <script>
      var model = {json.dumps(model)};
      if (model.CurrentItem) {{}}
    </script>
    </body></html>
    """

    product = _parse_detail_page(html, "https://www.vickerman.com/products/details?item=X23S230")

    assert product.image_urls == [
        "https://images.vickerman.com/X23S230_1000.jpg",
        "https://images.vickerman.com/X23S230T_1000.jpg",
    ]


def test_vickerman_category_tags_merge_duplicate_browse_paths():
    category = {
        "section": "Ornament",
        "label": "All Ornaments",
        "category_tags": [
            "Ornament",
            "All Ornaments",
            "Ornament > All Ornaments",
        ],
    }
    duplicate_category = {
        "section": "Sale Items",
        "label": "Ornaments",
    }

    _merge_category_tags(category, duplicate_category)

    assert category["category_tags"] == [
        "Ornament",
        "All Ornaments",
        "Ornament > All Ornaments",
        "Sale Items",
        "Ornaments",
        "Sale Items > Ornaments",
    ]


def test_vickerman_seed_categories_include_user_count_roots():
    categories = _seed_categories()
    urls = {category["slug"] for category in categories}

    assert len(categories) == len(VICKERMAN_PRODUCT_SELECTOR_SEEDS)
    assert "https://www.vickerman.com/productselector/ornament/all-ornaments" in urls
    assert "https://www.vickerman.com/productselector/categories/all-categories" in urls
    assert "https://www.vickerman.com/productselector/christmas-trees/alpine-trees" in urls


def test_parse_vickerman_direct_total_count():
    html = """
    <div>
      Total items found: 41,774
      page 1 of 871 next
    </div>
    """

    assert _parse_total_items(html) == 41774


def test_vickerman_discovers_left_tree_selector_links_and_normalizes_sort_query():
    html = """
    <ul class="catTree">
      <li><a href="/productselector/ornament/ball-ornaments?sort=group">Ball Ornaments</a></li>
      <li><a href="/productselector/ornament/tree-toppers">Tree Toppers</a></li>
    </ul>
    """

    categories = _discover_category_links(html)

    assert categories == [
        {
            "section": "Ornament",
            "label": "Ball Ornaments",
            "slug": "https://www.vickerman.com/productselector/ornament/ball-ornaments",
            "ddcode": "https://www.vickerman.com/productselector/ornament/ball-ornaments",
            "item_count": 0,
            "product_type": "Ball Ornaments",
        },
        {
            "section": "Ornament",
            "label": "Tree Toppers",
            "slug": "https://www.vickerman.com/productselector/ornament/tree-toppers",
            "ddcode": "https://www.vickerman.com/productselector/ornament/tree-toppers",
            "item_count": 0,
            "product_type": "Tree Toppers",
        },
    ]


def test_vickerman_product_type_candidates_try_visible_label_and_slug_label():
    category = {
        "label": "Seasons / Holidays",
        "product_type": "Seasons / Holidays",
        "slug": "https://www.vickerman.com/productselector/seasons/spring",
    }

    assert _product_type_candidates(category) == ["Seasons / Holidays", "Spring"]


def test_vickerman_catalog_totals_keep_seed_estimate_separate_from_discovered_coverage():
    categories = [
        {
            "slug": "https://www.vickerman.com/productselector/ornament/all-ornaments",
            "item_count": 8973,
        },
        {
            "slug": "https://www.vickerman.com/productselector/ornament/ball-ornaments",
            "item_count": 5865,
        },
    ]

    totals = _catalog_totals(categories)

    assert totals["total_products"] == 8973
    assert totals["section_listing_total"] == 14838
    assert totals["catalog_summary"]["seed_listing_total"] == 8973
    assert totals["catalog_summary"]["discovered_listing_total"] == 14838


def test_vickerman_validation_category_order_defers_rollups():
    categories = [
        {
            "section": "Categories",
            "label": "All Categories",
            "slug": "https://www.vickerman.com/productselector/categories/all-categories",
            "item_count": 21034,
        },
        {
            "section": "Accent Pieces",
            "label": "Container/Vases",
            "slug": "https://www.vickerman.com/productselector/accent-pieces/containervases",
            "item_count": 84,
        },
        {
            "section": "Wreaths",
            "label": "Berry Wreaths",
            "slug": "https://www.vickerman.com/productselector/wreaths/berry-wreaths",
            "item_count": 9,
        },
    ]

    ordered = _validation_category_order(categories)

    assert [category["label"] for category in ordered] == [
        "Berry Wreaths",
        "Container/Vases",
        "All Categories",
    ]


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        pass


_CATEGORY_PAGE_HTML = "<html><body>Category landing page</body></html>"
_SELECTOR_PAGE_HTML = """
<div>
  <a href="/products/details?item=K999999">Ball Ornament</a>
  Total items found: 1
  page 1 of 1
</div>
"""
_DETAIL_MODEL = {
    "CurrentItem": {
        "ItemNumber": "K999999",
        "Description": "Test Ball Ornament",
        "WebDescription": "Test description",
        "ImageUrl": "https://images.vickerman.com/K999999_1000.jpg",
        "QtyInStock": 5,
        "Price": 9.99,
    },
    "ProductOptions": [],
}
_DETAIL_PAGE_HTML = f"""
<html><body>
<script>
  var model = {json.dumps(_DETAIL_MODEL)};
  if (model.CurrentItem) {{}}
</script>
</body></html>
"""


def test_scrape_vickerman_does_not_block_the_event_loop(monkeypatch):
    """scrape_vickerman's blocking requests must run off the event loop.

    The sync request helper is monkeypatched to sleep synchronously (as the
    real `requests`/`time.sleep` calls would while waiting on the network),
    and a concurrent ticker coroutine proves the loop kept advancing instead
    of freezing for the duration of the scrape.

    A naive "did the ticker ever advance" check is not a strong enough
    assertion: `scrape_vickerman` also awaits `polite_delay` (a real
    `asyncio.sleep`) after yielding each product, and that alone would let a
    starved ticker catch up at the very end, masking a loop-blocking bug
    earlier in the run. So instead this test tracks the *gap* between
    consecutive ticks and asserts no gap is anywhere near the 0.2s sleep
    duration used by each fake blocking call — if any single call ran
    directly on the loop, that call's whole duration would show up as one
    big gap with no ticks in between.
    """

    def fake_login(session, username, password):
        time.sleep(0.2)
        return ""

    def fake_request_with_retries(session, method, url, attempts=3, backoff_seconds=1.5, **kwargs):
        time.sleep(0.2)
        if "/products/details" in url:
            return _FakeResponse(_DETAIL_PAGE_HTML)
        if url == vickerman_scraper.SELECTOR_URL:
            return _FakeResponse(_SELECTOR_PAGE_HTML)
        return _FakeResponse(_CATEGORY_PAGE_HTML)

    async def fast_polite_delay(seconds: float = 1.5):
        # Neutralize the real (legitimately non-blocking) delay so the test
        # measures only the effect of the blocking calls under test.
        return

    monkeypatch.setattr(vickerman_scraper, "_login", fake_login)
    monkeypatch.setattr(vickerman_scraper, "_request_with_retries", fake_request_with_retries)
    monkeypatch.setattr(vickerman_scraper, "polite_delay", fast_polite_delay)

    category = {
        "section": "Ornament",
        "label": "Ball Ornaments",
        "slug": "https://www.vickerman.com/productselector/ornament/ball-ornaments",
        "ddcode": "https://www.vickerman.com/productselector/ornament/ball-ornaments",
        "item_count": 1,
        "product_type": "Ball Ornaments",
    }

    async def scenario():
        ticks: list[float] = []

        async def ticker():
            while True:
                ticks.append(time.monotonic())
                await asyncio.sleep(0.02)

        async def run_scrape():
            products = []
            async for product in vickerman_scraper.scrape_vickerman(
                "user", "pass", subcategories=[category], supplier_id=None,
            ):
                products.append(product)
            return products

        ticker_task = asyncio.create_task(ticker())
        try:
            products = await run_scrape()
        finally:
            ticker_task.cancel()
            try:
                await ticker_task
            except asyncio.CancelledError:
                pass
        return products, ticks

    products, ticks = asyncio.run(scenario())

    assert len(products) == 1
    assert products[0].sku == "K999999"
    # 4 fake blocking calls of 0.2s each (login, category page, selector
    # page, detail page) run during the scrape. The ticker fires every 20ms.
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    assert len(ticks) >= 15, f"ticker barely advanced ({len(ticks)} ticks) — event loop was likely blocked"
    assert max(gaps) < 0.1, f"found a {max(gaps):.3f}s gap between ticks — event loop was blocked"
