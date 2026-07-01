"""Run supplier recon from the command line.

Example:
    .venv/bin/python -m app.libs.supplier_onboarding.recon_cli https://example.com
"""

import argparse
import asyncio

from .recon import run_http_recon


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Run a first-pass supplier site recon.")
    parser.add_argument("url", help="Supplier homepage or catalog URL")
    args = parser.parse_args()
    report = await run_http_recon(args.url)
    print(report.to_json())


if __name__ == "__main__":
    asyncio.run(_main())
