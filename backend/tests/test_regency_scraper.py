from app.libs.regency_scraper import _parse_page_context, _parse_product_detail, _parse_product_listing


def test_regency_product_detail_parser_preserves_tier_inventory_contract():
    html = """
    <html>
      <body>
        <h1>4" GLS SMILAX BEADED BALL ORNAMENT 3/AST</h1>
        <div>SKU: MTX77830</div>
        <div>As low as: $3.91</div>
        <img src="/images/items/MTX77830.jpg" />
        <table>
          <tr><th>Quantity</th><th>6 - 23</th><th>24 - 47</th><th>48 - 239</th><th>240+</th></tr>
          <tr><td>Price</td><td>$5.53</td><td>$4.68</td><td>$4.25</td><td>$3.91</td></tr>
        </table>
        <div>UOM: PC BOX: 6 CARTON: 48</div>
        <table>
          <tr><th>Style</th><th>Current Qty</th><th>Future Qty</th><th>QTY</th></tr>
          <tr><td>CINNAMON SPICE</td><td>0</td><td>690<br/>8/19/2026</td><td></td></tr>
        </table>
        <p>Minimum order amount: 6 PC</p>
        <p>Must be ordered in multiples of: 6 PC</p>
      </body>
    </html>
    """

    product = _parse_product_detail(html, "https://www.regency-rib.com/MTX77830.html")

    assert product is not None
    assert product.sku == "MTX77830"
    assert product.name == '4" GLS SMILAX BEADED BALL ORNAMENT 3/AST'
    assert product.base_price == 3.91
    assert product.uom == "PC"
    assert product.moq == 6
    assert product.box_qty == 6
    assert product.case_qty == 48
    assert product.availability == "eta"
    assert product.availability_note == "Future ship date 8/19/2026"
    assert product.style == "CINNAMON SPICE"
    assert product.image_urls == ["https://www.regency-rib.com/images/items/MTX77830.jpg"]
    assert product.raw["price_tiers"] == [
        {"quantity": "6 - 23", "price": 5.53, "price_label": "$5.53"},
        {"quantity": "24 - 47", "price": 4.68, "price_label": "$4.68"},
        {"quantity": "48 - 239", "price": 4.25, "price_label": "$4.25"},
        {"quantity": "240+", "price": 3.91, "price_label": "$3.91"},
    ]
    assert product.raw["style_inventory"] == [
        {
            "style": "CINNAMON SPICE",
            "current_qty": "0",
            "future_qty": "690 8/19/2026",
            "future_ship_date": "8/19/2026",
        }
    ]
    assert product.raw["order_multiple"] == 6


def test_regency_listing_parser_keeps_product_links_only():
    html = """
    <a href="/christmas-collection.html">Christmas</a>
    <a href="/MTX77830.html">4" GLS SMILAX BEADED BALL ORNAMENT 3/AST</a>
    <a href="https://www.regency-rib.com/MTX78615.html">10" GLASS REFLECTOR CANDLE HOLDER 2/AST</a>
    <a href="/flowers-foliage-bushes_ss96.html">Bushes</a>
    <a href="/index.html">Home</a>
    """

    assert _parse_product_listing(html) == [
        "https://www.regency-rib.com/MTX77830.html",
        "https://www.regency-rib.com/MTX78615.html",
    ]


def test_regency_page_context_parser_reads_ajax_grid_identifiers():
    html = """
    <ul class="products"><li class="pl"></li></ul>
    <script>
      var totalProducts = -1;
      var pageId = "2";
      var pageType = "products";
    </script>
    """

    assert _parse_page_context(html) == ("2", "products")
