#!/usr/bin/env python3
"""Fetch the full Craftex catalog via the storefront API in bulk.

The page-by-page crawl gets rate-limited after ~2k requests; the storefront
GraphQL API is not throttled and returns 100 full products per call. Records
are appended to the same details.ndjson checkpoint in the same format, so
stage_export consumes them unchanged (bulk records win dedupe by being last).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from catalog_extraction.craftex_http import GRAPHQL_URL, get_instance_token, make_session

OUT = ROOT / "outputs" / "craftex-full" / "details.ndjson"
ALL_PRODUCTS_ID = "00000000-000000-000000-000000000001"

QUERY = """query getFilteredProducts($mainCollectionId: String!, $offset: Int, $limit: Int) {
  catalog {
    category(categoryId: $mainCollectionId) {
      productsWithMetaData(limit: $limit, offset: $offset, onlyVisible: true) {
        totalCount
        list {
          id name sku price discountedPrice comparePrice formattedPrice
          description urlPart productType isVisible isInStock weight ribbon brand
          inventory { quantity status }
          media { url fullUrl altText }
          options { title selections { id description } }
          productItems { id sku price discountedPrice optionsSelections isVisible inventory { quantity status } }
        }
      }
    }
  }
}"""


def main() -> int:
    session = make_session()
    instance = get_instance_token(session)
    fetched = 0
    offset, total = 0, None
    with OUT.open("a", encoding="utf-8") as out:
        while total is None or offset < total:
            response = session.post(
                GRAPHQL_URL,
                json={"query": QUERY,
                      "variables": {"mainCollectionId": ALL_PRODUCTS_ID, "offset": offset, "limit": 100}},
                headers={"Authorization": instance, "Content-Type": "application/json"},
                timeout=90,
            )
            response.raise_for_status()
            payload = (((response.json().get("data") or {}).get("catalog") or {})
                       .get("category") or {}).get("productsWithMetaData") or {}
            batch = payload.get("list") or []
            total = payload.get("totalCount") or 0
            stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            for product in batch:
                slug = product.get("urlPart") or product.get("id")
                record = {
                    "slug": slug,
                    "url": f"https://www.craftex.com/product-page/{slug}",
                    "ok": True,
                    "product": product,
                    "source": "storefront_api_bulk",
                    "fetched_at": stamp,
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            fetched += len(batch)
            offset += max(1, len(batch))
            print(f"[{time.strftime('%H:%M:%S')}] bulk: {fetched}/{total}", flush=True)
            if not batch:
                break
            time.sleep(0.3)
    print(f"[{time.strftime('%H:%M:%S')}] bulk done: {fetched} products")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
