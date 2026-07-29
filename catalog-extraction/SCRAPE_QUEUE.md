# Scrape Queue — Leaf & Ledger suppliers

## In progress / done
### Melrose International — https://melroseintl.com/  →  SoloVue portal
- **Status:** UNBLOCKED — credentials provided; full scrape running/done.
- **Real target:** `melrose.solovue.com` (SoloVue B2B portal; melroseintl.com is
  only marketing). ASP.NET + Vue SPA + JSON API.
- **Recipe:** `run_melrose_full.py`. Browser login (Vue needs input events +
  button click; sets `.ASPXAUTH` + `UserToken`/`AccessToken`) → API:
  `GetCategories` then `GetProductList?ProductCategoryId=<id>&PageNumber=N&ReturnAllImages=true`.
  Real quantity-tier WHOLESALE prices, images, descriptions. Field quirks:
  `Pnumber`=SKU, `Item`=name, `Detail`=color, `Prices[]`=tiers.
- **NOTE:** password was briefly exposed in a login GET during recon — rotate it.

## Queued (need URL + credentials)
_(none currently)_
