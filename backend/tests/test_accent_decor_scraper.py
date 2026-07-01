import app.libs.accent_decor_scraper as accent_module
from app.apis.scraper import (
    _catalog_selection_detail,
    _credential_step_action,
    _credential_step_detail,
    _credential_validation_message,
    _first_http_image_url,
    _http_image_url_candidates,
    _normalize_product_for_import,
    _product_matches_selected_skus,
    _running_image_backfill_conflict,
    _selected_sku_set,
)
from app.libs.accent_decor_scraper import (
    CATEGORY_SLUGS,
    _catalog_categories,
    _category_url,
    _credential_label,
    _get_next_page_url,
    _is_email_login,
    _is_account_dashboard,
    _is_login_page,
    _klevu_catalog_summary,
    _parse_listing_count,
    _parse_product_detail,
    _scraped_product_from_klevu_record,
    _selected_klevu_sections,
)


def test_accent_catalog_configuration_contains_full_menu_sections():
    categories = _catalog_categories()
    by_slug = {cat["slug"]: cat for cat in categories}
    sections = {cat["section"] for cat in categories}

    assert len(categories) > 100
    assert len(CATEGORY_SLUGS) == len(categories)
    assert len(set(CATEGORY_SLUGS)) == len(CATEGORY_SLUGS)
    assert {
        "New",
        "In-Stock",
        "Flower + Event",
        "Plant + Garden",
        "Home + Gift",
        "Seasonal",
        "Eric + Eloise",
        "Sale",
    }.issubset(sections)

    assert by_slug["flower/vases-vessels/compotes-urns"]["label"] == "Vases & Vessels / Compotes & Urns"
    assert by_slug["plant/plant-accessories/saucers"]["section"] == "Plant + Garden"
    assert by_slug["home/room-decor/decorative-objects"]["section"] == "Home + Gift"
    assert by_slug["seasonal/christmas/wreaths-garlands"]["section"] == "Seasonal"
    assert by_slug["sale/seasonal/spring-celebrations"]["section"] == "Sale"


def test_catalog_selection_detail_prefers_unique_imported_count():
    detail = _catalog_selection_detail("all", 149, 22807, 2338)

    assert "2,338 unique products imported" in detail
    assert "22,807 times" in detail
    assert "about 22,807 products" not in detail


def test_accent_category_url_preserves_filter_query_codes():
    url = _category_url("flower/floral-essentials?Filters=label_in_stock%3AIN%2520STOCK")

    assert url == "https://www.accentdecor.com/flower/floral-essentials?Filters=label_in_stock%3AIN%2520STOCK"


def test_accent_listing_count_parses_toolbar_totals():
    assert _parse_listing_count("<div class='toolbar-amount'>744 item(s)</div>") == 744
    assert _parse_listing_count("<div class='toolbar-amount'>Items 1-36 of 1,284</div>") == 1284
    assert _parse_listing_count("<main><span>Results</span><p>36 item(s)</p></main>") == 36


def test_accent_next_page_parses_uppercase_page_parameter():
    html = """
    <nav class="pages">
      <a href="https://www.accentdecor.com/flower?Page=1">1</a>
      <a href="https://www.accentdecor.com/flower?Page=2">2</a>
      <a href="https://www.accentdecor.com/flower?Page=21">21</a>
    </nav>
    """

    assert _get_next_page_url(html, "https://www.accentdecor.com/flower") == (
        "https://www.accentdecor.com/flower?Page=2"
    )
    assert _get_next_page_url(html, "https://www.accentdecor.com/flower?Page=2") == (
        "https://www.accentdecor.com/flower?Page=21"
    )


def test_accent_next_page_preserves_existing_filters_when_incrementing():
    html = """
    <nav class="pages">
      <a href="javascript:void(0)">20</a>
      <a href="https://www.accentdecor.com/plant/planters?Filters=drainage_hole%3AYes&Page=21">21</a>
    </nav>
    """

    assert _get_next_page_url(
        html,
        "https://www.accentdecor.com/plant/planters?Filters=drainage_hole%3AYes&Page=20",
    ) == "https://www.accentdecor.com/plant/planters?Filters=drainage_hole%3AYes&Page=21"


def test_parse_accent_product_detail_preserves_catalog_contract():
    html = """
    <html>
      <body>
        <h1 class="page-title">Helena Planter</h1>
        <div class="product-info-sku"><span class="value">AD-123</span></div>
        <span class="price" content="42.50">$42.50</span>
        <ul class="items">
          <li>Home</li>
          <li>Containers</li>
          <li>Helena Planter</li>
        </ul>
        <div class="stock">In Stock</div>
        <table id="product-attribute-specs-table">
          <tr><th>Unit of Measure</th><td>Each</td></tr>
          <tr><th>Height</th><td>12 in</td></tr>
          <tr><th>Width</th><td>8 in</td></tr>
          <tr><th>Diameter</th><td>7 in</td></tr>
          <tr><th>Length</th><td>10 in</td></tr>
          <tr><th>Finish</th><td>Matte</td></tr>
          <tr><th>Style</th><td>Modern</td></tr>
          <tr><th>Material</th><td>Ceramic</td></tr>
          <tr><th>Country of Origin</th><td>Portugal</td></tr>
        </table>
        <img src="/media/catalog/product/helena-main.jpg">
        <img data-src="/media/catalog/product/helena-alt.webp">
        <img src="/media/logo.png">
      </body>
    </html>
    """

    product = _parse_product_detail(html, "https://www.accentdecor.com/helena-planter.html")

    assert product is not None
    assert product.sku == "AD-123"
    assert product.name == "Helena Planter"
    assert product.base_price == 42.50
    assert product.uom == "Each"
    assert product.category == "Containers"
    assert product.availability == "in_stock"
    assert product.availability_note == "In Stock"

    assert product.height_in == 12
    assert product.width_in == 8
    assert product.diameter_in == 7
    assert product.length_in == 10
    assert product.finish == "Matte"
    assert product.style == "Modern"
    assert product.material == "Ceramic"
    assert product.country_of_origin == "Portugal"

    assert product.photo_url == "https://www.accentdecor.com/media/catalog/product/helena-main.jpg"
    assert product.image_urls == [
        "https://www.accentdecor.com/media/catalog/product/helena-main.jpg",
        "https://www.accentdecor.com/media/catalog/product/helena-alt.webp",
    ]

    assert product.raw["detail_url"] == "https://www.accentdecor.com/helena-planter.html"
    assert product.raw["source_url"] == "https://www.accentdecor.com/helena-planter.html"
    assert product.raw["source_photo_url"] == product.photo_url
    assert product.raw["detail_status"] == "stored"
    assert product.raw["image_status"] == "pending"
    assert product.raw["image_urls"] == product.image_urls
    assert product.raw["Category"] == "Containers"
    assert product.raw["Availability"] == "In Stock"


def test_parse_accent_product_detail_prefers_structured_product_data_and_gallery():
    html = """
    <html>
      <head>
        <meta property="og:image" content="https://cdn-lg.accentdecor.com/media/catalog/product/cache/og/e/e/eeeugenebust.jpg"/>
        <script type="application/ld+json">
          {"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
            {"@type":"ListItem","position":1,"item":{"name":"Home"}},
            {"@type":"ListItem","position":2,"item":{"name":"Eric + Eloise"}},
            {"@type":"ListItem","position":3,"item":{"name":"Eugene the Moose"}}
          ]}
        </script>
        <script type="application/ld+json">
          {"@context":"https://schema.org","@type":"Product","name":"E+E Eugene Bust",
           "description":"<p>Structured description.</p>",
           "image":"https://cdn-lg.accentdecor.com/media/catalog/product/cache/json/e/e/eeeugenebust.jpg",
           "offers":[{"price":42,"sku":"eeeugenebust"}],
           "sku":"eeeugenebust"}
        </script>
      </head>
      <body>
        <h1 class="page-title">Wrong fallback title</h1>
        <div class="product attribute sku"><strong class="type">SKU</strong><div class="value">wrong-fallback</div></div>
        <img src="https://cdn-lg.accentdecor.com/media/wysiwyg/marketing-banner.jpg">
        <div class="gallery-placeholder" data-gallery-role="gallery-placeholder">
          <img src="https://cdn-lg.accentdecor.com/media/catalog/product/cache/thumb/e/e/eeeugenebust.jpg">
        </div>
        <script type="text/x-magento-init">
          {
            "[data-gallery-role=gallery-placeholder]": {
              "mage/gallery/gallery": {
                "data": [
                  {"full":"https://cdn-lg.accentdecor.com/media/catalog/product/cache/full/e/e/eeeugenebust.jpg","img":"https://cdn-lg.accentdecor.com/media/catalog/product/cache/img/e/e/eeeugenebust.jpg"},
                  {"full":"https://cdn-lg.accentdecor.com/media/catalog/product/cache/full/e/e/eeeugenebust_1_.jpg","img":"https://cdn-lg.accentdecor.com/media/catalog/product/cache/img/e/e/eeeugenebust_1_.jpg"}
                ]
              }
            }
          }
        </script>
      </body>
    </html>
    """

    product = _parse_product_detail(
        html,
        "https://www.accentdecor.com/eric-eloise/eugene-the-moose/e-e-eugene-bust",
    )

    assert product is not None
    assert product.sku == "eeeugenebust"
    assert product.name == "E+E Eugene Bust"
    assert product.base_price == 42
    assert product.description == "Structured description."
    assert product.category == "Eugene the Moose"
    assert product.photo_url == "https://cdn-lg.accentdecor.com/media/catalog/product/cache/full/e/e/eeeugenebust.jpg"
    assert product.image_urls == [
        "https://cdn-lg.accentdecor.com/media/catalog/product/cache/full/e/e/eeeugenebust.jpg",
        "https://cdn-lg.accentdecor.com/media/catalog/product/cache/full/e/e/eeeugenebust_1_.jpg",
        "https://cdn-lg.accentdecor.com/media/catalog/product/cache/thumb/e/e/eeeugenebust.jpg",
        "https://cdn-lg.accentdecor.com/media/catalog/product/cache/og/e/e/eeeugenebust.jpg",
        "https://cdn-lg.accentdecor.com/media/catalog/product/cache/json/e/e/eeeugenebust.jpg",
    ]
    assert all("/media/wysiwyg/" not in url for url in product.image_urls)


def test_accent_klevu_record_normalizes_to_import_ready_product():
    product = _scraped_product_from_klevu_record({
        "sku": "kendallpot;;;;97521.01",
        "name": "Kendall Pot",
        "basePrice": "2.25",
        "url": "https://www.accentdecor.com/kendall-pot?utm=test",
        "image": "https://cdn-lg.accentdecor.com/media/catalog/product/kendall.jpg",
        "imageHover": "https://cdn-lg.accentdecor.com/media/catalog/product/kendall-alt.jpg",
        "ad_product_type": "POTS",
        "material": "Ceramic",
        "color_chip": "White",
        "weight": "1.400000",
        "label_in_stock": "IN STOCK",
        "itemGroupId": "53627",
        "_accent_first_section": "Plant + Garden",
        "_accent_section_slug": "plant",
    })

    assert product.sku == "kendallpot"
    assert product.name == "Kendall Pot"
    assert product.base_price == 2.25
    assert product.uom == "Each"
    assert product.category == "Pots"
    assert product.material == "Ceramic"
    assert product.color == "White"
    assert product.weight_lb == 1.4
    assert product.availability == "in_stock"
    assert product.photo_url == "https://cdn-lg.accentdecor.com/media/catalog/product/kendall.jpg"
    assert product.image_urls == [
        "https://cdn-lg.accentdecor.com/media/catalog/product/kendall.jpg",
        "https://cdn-lg.accentdecor.com/media/catalog/product/kendall-alt.jpg",
    ]
    assert product.raw["detail_url"] == "https://www.accentdecor.com/kendall-pot"
    assert product.raw["source_photo_url"] == product.photo_url
    assert product.raw["detail_status"] == "stored"
    assert product.raw["image_status"] == "pending"
    assert product.raw["Unit of Measure"] == "Each"


def test_accent_klevu_section_selection_maps_full_catalog():
    sections = _selected_klevu_sections([
        {"slug": "flower/vases-vessels"},
        {"slug": "plant/planters"},
        {"slug": "home/room-decor"},
        {"slug": "sale"},
    ])

    assert [section[0] for section in sections] == [
        "Flower + Event",
        "Plant + Garden",
        "Home + Gift",
        "Sale",
    ]


def test_accent_klevu_section_selection_treats_full_index_as_full_catalog():
    sections = _selected_klevu_sections([
        {"slug": f"flower/generated-category-{i}"} for i in range(25)
    ])

    assert [section[0] for section in sections] == [
        "New",
        "In-Stock",
        "Flower + Event",
        "Plant + Garden",
        "Home + Gift",
        "Seasonal",
        "Eric + Eloise",
        "Sale",
    ]


def test_accent_klevu_collector_pages_until_listed_total():
    calls = []
    original_search = accent_module._klevu_search
    original_delay = accent_module.KLEVU_REQUEST_DELAY

    def fake_search(category_path, *, offset=0, limit=100):
        calls.append(offset)
        total = 205
        records = [
            {
                "id": str(index),
                "url": f"https://www.accentdecor.com/test-product-{index}",
                "sku": f"test-product-{index}",
                "name": f"Test Product {index}",
            }
            for index in range(offset, min(offset + 100, total))
        ]
        return {
            "queryResults": [
                {
                    "records": records,
                    "meta": {"totalResultsFound": total},
                }
            ]
        }

    try:
        accent_module._klevu_search = fake_search
        accent_module.KLEVU_REQUEST_DELAY = 0
        records, stats = accent_module._collect_klevu_product_records(
            None,
            [("Test", "TEST", "test")],
        )
    finally:
        accent_module._klevu_search = original_search
        accent_module.KLEVU_REQUEST_DELAY = original_delay

    assert len(records) == 205
    assert calls == [0, 100, 200]
    assert stats[0]["pages_checked"] == 3


def test_accent_klevu_catalog_summary_keeps_unique_total_separate_from_listing_total():
    summary = _klevu_catalog_summary(
        records=[
            {"url": "https://www.accentdecor.com/a"},
            {"url": "https://www.accentdecor.com/b"},
            {"url": "https://www.accentdecor.com/c"},
        ],
        stats=[
            {"name": "New", "listed_total": 2, "unique_in_section": 2},
            {"name": "In-Stock", "listed_total": 3, "unique_in_section": 1},
            {"name": "Sale", "listed_total": 2, "unique_in_section": 0},
        ],
    )

    assert summary["unique_total"] == 3
    assert summary["section_listing_total"] == 7
    assert "dedupe by normalized product URL" in summary["method"]


def test_normalize_accent_product_for_import_preserves_standard_fields():
    scraped = {
        "sku": "AD%2D123",
        "name": " Helena Planter ",
        "base_price": None,
        "photo_url": "https://www.accentdecor.com/media/catalog/product/helena-main.jpg",
        "image_urls": ["https://www.accentdecor.com/media/catalog/product/helena-alt.webp"],
        "raw": {
            "price": "$42.50",
            "Category": "Containers",
            "Unit of Measure": "Each",
            "Availability": "In Stock",
            "Height": "12 in",
            "Width": "8 in",
            "Diameter": "7 in",
            "Length": "10 in",
            "Finish": "Matte",
            "Style": "Modern",
            "Material": "Ceramic",
            "Country of Origin": "Portugal",
            "detail_url": "https://www.accentdecor.com/helena-planter.html",
        },
    }

    normalized = _normalize_product_for_import(scraped, "accent_decor")

    assert normalized["sku"] == "AD-123"
    assert normalized["name"] == "Helena Planter"
    assert normalized["price"] == 42.50
    assert normalized["category"] == "containers"
    assert normalized["unit"] == "each"
    assert normalized["photo_url"] is None
    assert normalized["image_urls"] == [
        "https://www.accentdecor.com/media/catalog/product/helena-main.jpg",
        "https://www.accentdecor.com/media/catalog/product/helena-alt.webp",
    ]
    assert normalized["country"] == "Portugal"
    assert normalized["height_in"] == 12
    assert normalized["width_in"] == 8
    assert normalized["diameter_in"] == 7
    assert normalized["length_in"] == 10
    assert normalized["material"] == "Ceramic"
    assert normalized["finish"] == "Matte"
    assert normalized["style"] == "Modern"
    assert normalized["availability"] == "In Stock"

    raw_data = normalized["raw_data"]
    assert raw_data["source_photo_url"] == "https://www.accentdecor.com/media/catalog/product/helena-main.jpg"
    assert raw_data["image_urls"] == normalized["image_urls"]
    assert raw_data["detail_status"] == "stored"
    assert raw_data["image_status"] == "pending"
    assert raw_data["scraper_key"] == "accent_decor"
    assert "scraper_key" not in scraped["raw"]


def test_normalize_accent_image_urls_only_sets_source_photo_for_storage():
    normalized = _normalize_product_for_import(
        {
            "sku": "AD-IMG",
            "name": "Image Only Cache Row",
            "image_urls": [
                "https://www.accentdecor.com/media/catalog/product/image-only-main.jpg",
                "https://www.accentdecor.com/media/catalog/product/image-only-alt.jpg",
            ],
            "raw": {},
        },
        "accent_decor",
    )

    assert normalized["photo_url"] is None
    assert normalized["image_urls"][0] == "https://www.accentdecor.com/media/catalog/product/image-only-main.jpg"
    assert normalized["raw_data"]["source_photo_url"] == (
        "https://www.accentdecor.com/media/catalog/product/image-only-main.jpg"
    )
    assert normalized["raw_data"]["image_status"] == "pending"


def test_accent_selected_sku_matching_handles_encoded_cached_values():
    sku_set = _selected_sku_set(["AD-123"])

    assert _product_matches_selected_skus({"sku": "AD%2D123"}, sku_set)
    assert _product_matches_selected_skus({"supplier_sku": "AD%2D123"}, sku_set)
    assert not _product_matches_selected_skus({"sku": "AD-999"}, sku_set)


def test_accent_selected_sku_matching_handles_encoded_selection_values():
    sku_set = _selected_sku_set(["AD%2D123"])

    assert _product_matches_selected_skus({"sku": "AD-123"}, sku_set)
    assert _product_matches_selected_skus({"supplier_sku": "AD-123"}, sku_set)


def test_supplier_image_backfill_rejects_other_supplier_running_job():
    conflict = _running_image_backfill_conflict(
        {"status": "running", "supplier_id": 22},
        supplier_id=15,
    )

    assert conflict
    assert "supplier 22" in conflict
    assert _running_image_backfill_conflict({"status": "running", "supplier_id": 15}, supplier_id=15) is None
    assert _running_image_backfill_conflict({"status": "running", "supplier_id": None}, supplier_id=15) is None
    assert _running_image_backfill_conflict({"status": "done", "supplier_id": 22}, supplier_id=15) is None


def test_image_backfill_uses_typed_image_urls_when_source_photo_is_missing():
    assert _first_http_image_url(
        photo_url=None,
        image_urls=["https://www.accentdecor.com/media/catalog/product/fallback.jpg"],
        raw_data={},
    ) == "https://www.accentdecor.com/media/catalog/product/fallback.jpg"
    assert _first_http_image_url(
        photo_url="/api/products/image-proxy?key=stored.png",
        image_urls=[],
        raw_data={"image_urls": ["https://www.accentdecor.com/media/catalog/product/raw-fallback.jpg"]},
    ) == "https://www.accentdecor.com/media/catalog/product/raw-fallback.jpg"


def test_image_backfill_keeps_alternate_supplier_image_urls():
    assert _http_image_url_candidates(
        photo_url="https://images.vickerman.com/QK257567.jpg",
        image_urls=[
            "https://images.vickerman.com/QK257567.jpg",
            "https://images.vickerman.com/QK257567_CU_1000.jpg",
        ],
        raw_data={"image_urls": ["https://images.vickerman.com/QK257567_C2_1000.jpg"]},
    ) == [
        "https://images.vickerman.com/QK257567.jpg",
        "https://images.vickerman.com/QK257567_CU_1000.jpg",
        "https://images.vickerman.com/QK257567_C2_1000.jpg",
    ]


def test_accent_credential_copy_uses_activated_email_password():
    assert (
        _credential_validation_message("accent_decor", "untested")
        == "Run Configure Catalog to test the Accent email/password before syncing products."
    )
    assert (
        _credential_validation_message("accent_decor", "failed")
        == "Update the Accent email/password, then run Configure Catalog again."
    )
    assert "email/password are missing" in _credential_step_detail(
        "Accent Decor",
        "accent_decor",
        has_credentials=False,
        credential_status="missing",
    )
    assert "email/password" in _credential_step_detail(
        "Accent Decor",
        "accent_decor",
        has_credentials=True,
        credential_status="failed",
    )
    assert _credential_step_action("accent_decor", has_credentials=False, credential_status="missing") == (
        "Edit this supplier and add the Accent email/password."
    )
    assert _credential_step_action("accent_decor", has_credentials=True, credential_status="untested") == (
        "Run Configure Catalog to test the Accent email/password."
    )


def test_accent_login_mode_detects_email_vs_activation_credentials():
    assert _is_email_login("customer@example.com")
    assert not _is_email_login("123456")
    assert _credential_label("customer@example.com") == "email/password"
    assert _credential_label("123456") == "account number/billing zip"


def test_accent_login_page_detection_includes_homepage_drawer():
    assert _is_login_page(
        """
        <aside>
          <h2>Sign in to Accent Decor</h2>
          <input placeholder="Email address">
          <input placeholder="Password">
          <a>Forgot Password?</a>
        </aside>
        """
    )
    assert _is_login_page(
        """
        <main>
          <h1>Customer Login</h1>
          <input id="email">
          <input id="pass">
        </main>
        """
    )
    assert _is_login_page(
        """
        <form>
          <input placeholder="Account Number">
          <input placeholder="Billing Zip Code">
        </form>
        """
    )
    assert not _is_login_page(
        """
        <header>
          <a href="/customer/account/login">SIGN IN | REGISTER</a>
          <h1>Fall Winter 2026</h1>
        </header>
        """
    )
    account_html = """
    <main>
      <h1>My Account</h1>
      <section>Account Information</section>
      <p>Account Number: TEST-123</p>
      <a>Edit Change Password</a>
    </main>
    """
    assert _is_account_dashboard(account_html)
    assert not _is_login_page(account_html)
