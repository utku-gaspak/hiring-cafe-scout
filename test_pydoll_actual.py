import asyncio
import os
import sys

os.environ["CAFE_SCOUT_HEADLESS"] = "1"
os.environ["CAFE_SCOUT_BROWSER_BINARY"] = (
    "/root/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome"
)

sys.path.insert(0, "/root/code/hiring-cafe-scout/src")

from job_parser.browser_scraper import scrape_with_browser, _build_browser_options
from pydoll.browser.chromium import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.constants import PageLoadState


def run_in_thread():
    """Replicate scrape_with_browser startup path from a thread (via asyncio.to_thread)."""
    import shutil

    options = _build_browser_options(
        ChromiumOptions=ChromiumOptions,
        PageLoadState=PageLoadState,
        profile_dir="/tmp/pydoll-actual-test",
    )
    print("binary_location:", options.binary_location)
    print("arguments:", options.arguments)

    async def _start():
        browser = Chrome(options=options)
        try:
            tab = await browser.start()
            print("SUCCESS - browser started, tab:", tab)
            await browser.stop()
        except Exception as e:
            print(f"FAILED: {type(e).__name__}: {e}")

    asyncio.run(_start())
    shutil.rmtree("/tmp/pydoll-actual-test", ignore_errors=True)


async def main():
    print("=== Test 1: direct asyncio (works?) ===")
    options = _build_browser_options(
        ChromiumOptions=ChromiumOptions,
        PageLoadState=PageLoadState,
        profile_dir="/tmp/pydoll-direct-test",
    )
    browser = Chrome(options=options)
    try:
        tab = await browser.start()
        print("direct: SUCCESS -", tab)
        await browser.stop()
    except Exception as e:
        print(f"direct: FAILED: {type(e).__name__}: {e}")

    import shutil
    shutil.rmtree("/tmp/pydoll-direct-test", ignore_errors=True)

    print("\n=== Test 2: via asyncio.to_thread (actual CLI path) ===")
    await asyncio.to_thread(run_in_thread)


asyncio.run(main())
