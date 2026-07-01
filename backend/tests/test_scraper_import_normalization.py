from app.apis.scraper import _normalize_product_for_import


def test_normalize_product_for_import_preserves_category_aliases():
    normalized = _normalize_product_for_import(
        {
            "sku": "ABC-123",
            "name": "Blue Cypress Tree",
            "category": "Christmas Trees",
            "subcategory": "Colorful Trees",
            "tags": ["Holiday", "Colorful Trees"],
            "raw": {
                "source_section": "Christmas Trees",
                "source_category": "Blue Trees",
                "source_category_path": "Christmas Trees > Blue Trees",
                "category_tags": ["Existing Alias"],
            },
        },
        "vickerman",
    )

    assert normalized["category"] == "trees"
    assert normalized["raw_data"]["category_tags"] == [
        "trees",
        "Christmas Trees",
        "Colorful Trees",
        "Blue Trees",
        "Christmas Trees > Blue Trees",
        "Holiday",
        "Existing Alias",
    ]
