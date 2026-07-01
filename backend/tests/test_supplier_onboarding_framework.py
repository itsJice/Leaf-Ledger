from app.libs.supplier_onboarding.recon import analyze_html
from app.libs.select_artificial_scraper import _parse_category_links


def test_recon_identifies_xhr_and_product_patterns():
    html = """
    <html>
      <head>
        <title>Supplier Catalog</title>
        <script src="/assets/catalog.js"></script>
        <script type="application/ld+json">{"@type":"Product","name":"Test"}</script>
      </head>
      <body>
        <a href="/collections/flowers.html">Flowers</a>
        <a href="/ABC123.html">Product ABC123</a>
        <img src="/images/ABC123.jpg" />
        <script>
          var pageId = "2";
          var pageType = "products";
          fetch('/get_products.php?skip=0&pageType=products&pageId=2')
        </script>
      </body>
    </html>
    """

    report = analyze_html("https://supplier.test", "https://supplier.test", 200, html, 200)

    assert report.title == "Supplier Catalog"
    assert report.likely_strategy == "http_xhr"
    assert report.difficulty_rank == "A"
    assert "storefront_product_grid: pageId/pageType variables" in report.xhr_hints
    assert report.product_url_patterns == ["/ABC{n}.html"]
    assert report.json_ld_types == ["Product"]
    assert report.category_candidates[0]["url"] == "https://supplier.test/collections/flowers.html"


def test_recon_ignores_common_catalog_false_positives():
    html = """
    <html>
      <head>
        <title>Supplier Home</title>
        <script src="https://fonts.googleapis.com/css?family=Roboto:300"></script>
        <script src="https://ajax.googleapis.com/ajax/libs/angularjs/1.5.9/angular.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/ngInfiniteScroll/1.3.0/ng-infinite-scroll.min.js"></script>
      </head>
      <body>
        <a href="/flowers-foliage-bushes_ss96.html">Bushes</a>
        <a href="/christmas-collection.html">Christmas Decor</a>
      </body>
    </html>
    """

    report = analyze_html("https://supplier.test", "https://supplier.test", 200, html, 404)

    assert report.likely_strategy == "http_static"
    assert report.product_link_candidates == []
    assert report.product_url_patterns == []
    assert report.xhr_hints == []


def test_select_artificial_category_parser_groups_shop_links():
    html = """
    <nav>
      <a href="/shop/?Category=Foliages&SubCategory=Foliage%20Bushes">Foliage Bushes</a>
      <a href="/shop/?Category=Flowers&SubCategory=Garden%20Stems">Garden Stems</a>
      <a href="/contact">Contact</a>
      <a href="/shop/?Category=Foliages&SubCategory=Foliage%20Bushes">Duplicate</a>
    </nav>
    """

    categories = _parse_category_links(html)

    assert len(categories) == 2
    assert categories[0]["section"] == "Foliages"
    assert categories[0]["label"] == "Foliage Bushes"
    assert categories[0]["slug"] == "https://selectartificials.com/shop/?Category=Foliages&SubCategory=Foliage%20Bushes"
    assert categories[1]["section"] == "Flowers"
