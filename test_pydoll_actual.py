import asyncio
import os
import sys

# Replicate exactly what _build_browser_options does
os.environ.setdefault("CAFE_SCOUT_HEADLESS", "1")
os.environ.setdefault(
    "CAFE_SCOUT_BROWSER_BINARY",
    "/root/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome",
)

sys.path.insert(0, "/root/code/hiring-cafe-scout/src")

from job_parser.browser_scraper import _build_browser_options

from pydoll.browser.chromium import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.constants import PageLoadState


async def main():
    options = _build_browser_options(
        ChromiumOptions=ChromiumOptions,
        PageLoadState=PageLoadState,
        profile_dir="/tmp/pydoll-actual-test",
    )

    print("binary_location:", options.binary_location)
    print("start_timeout:", options.start_timeout)
    print("headless:", options.headless)
    print("arguments:", options.arguments)

    browser = Chrome(options=options)
    print("\nStarting browser via Pydoll...")
    try:
        tab = await browser.start()
        print("SUCCESS - browser started, tab:", tab)
        await browser.stop()
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
    finally:
        import shutil
        shutil.rmtree("/tmp/pydoll-actual-test", ignore_errors=True)


asyncio.run(main())
