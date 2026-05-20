from __future__ import annotations

import json
import shutil
import socket
import struct
import subprocess
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Callable, ContextManager, Protocol, Any
from urllib.parse import urlparse


DEFAULT_SESSION_EXPORT_URL = "https://hiring.cafe"

_CHROME_BINARIES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium-browser",
    "chromium",
)
# Persistent profile so CF cookies survive between runs
_BROWSER_PROFILE = Path.home() / ".local" / "share" / "cafe-scout" / "browser-profile"


class _PlaywrightLike(Protocol):
    chromium: Any


def export_session_state(
    output_path: str,
    url: str = DEFAULT_SESSION_EXPORT_URL,
    sync_playwright_factory: Callable[[], ContextManager[_PlaywrightLike]] | None = None,
) -> None:
    factory = sync_playwright_factory or _load_sync_playwright
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    print(f"Opening a browser on {url}")
    print("Solve the Cloudflare challenge if it appears, then press Enter here to save the session.")

    with factory() as playwright:
        browser = playwright.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page.set_extra_http_headers({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            })
            try:
                page.goto(url, wait_until="commit", timeout=30_000)
            except Exception as exc:  # pragma: no cover - browser/runtime specific
                print(f"Browser navigation warning: {exc}")

            input("Press Enter after the page is usable: ")
            _wait_for_clearance_cookie(context)
            context.storage_state(path=str(destination))
            print(f"Saved browser session → {destination}")
        finally:
            browser.close()


def _load_sync_playwright() -> ContextManager[_PlaywrightLike]:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:  # pragma: no cover - import guard
        raise SystemExit(
            "Missing dependency: playwright\n"
            "Install it with `python3 -m pip install -r requirements.txt` "
            "and then run `python3 -m playwright install chromium`."
        ) from exc
    return sync_playwright()


def resolve_cloudflare_in_browser(
    session: Any,
    url: str,
    _cookie_provider: Callable[[str], list[dict]] | None = None,
) -> None:
    """Open a real (non-automated) browser, let the user solve the CF challenge,
    then inject the resulting cookies into *session*."""
    provider = _cookie_provider or _launch_chrome_and_get_cookies

    print(f"\nCloudflare challenge detected. Opening browser on {url}")
    print("Solve the challenge in the browser window, then press Enter here to continue.")

    cookies = provider(url)

    if not hasattr(session, "_cf_cookies"):
        session._cf_cookies = {}  # type: ignore[attr-defined]
    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        domain = str(cookie.get("domain") or "").strip().lstrip(".")
        path = str(cookie.get("path") or "/")
        if name and value and domain:
            session._cf_cookies[name] = value  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# System Chrome + CDP cookie extraction
# ---------------------------------------------------------------------------

def _launch_chrome_and_get_cookies(url: str) -> list[dict]:
    chrome = _find_chrome()
    if not chrome:
        return _manual_cookie_input(url)

    port = _find_free_port()
    _BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [
            chrome,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={_BROWSER_PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        ws_url = _wait_for_cdp_target(port)
        if not ws_url:
            print("Could not reach Chrome DevTools — falling back to manual input.")
            return _manual_cookie_input(url)
        input("Press Enter once the challenge is solved: ")
        domain = urlparse(url).hostname or ""
        return _cdp_get_all_cookies(ws_url, domain)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _find_chrome() -> str | None:
    for binary in _CHROME_BINARIES:
        path = shutil.which(binary)
        if path:
            return path
    return None


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_cdp_target(port: int, timeout: int = 15) -> str | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = urllib.request.urlopen(
                f"http://localhost:{port}/json", timeout=2
            )
            targets = json.loads(response.read())
            for target in targets:
                if target.get("type") == "page" and "webSocketDebuggerUrl" in target:
                    return target["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    return None


def _cdp_get_all_cookies(ws_url: str, domain: str) -> list[dict]:
    parsed = urlparse(ws_url)
    try:
        sock = socket.create_connection((parsed.hostname, parsed.port), timeout=10)
    except OSError:
        return []
    try:
        # WebSocket handshake
        handshake = (
            f"GET {parsed.path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: Y2FmZS1zY291dC13cw==\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        sock.sendall(handshake.encode())
        _ws_drain_headers(sock)

        # Ask Chrome for all cookies
        sock.sendall(
            _ws_frame(
                json.dumps(
                    {"id": 1, "method": "Network.getAllCookies", "params": {}}
                ).encode()
            )
        )

        # Read messages until we get ours (Chrome may send events first)
        for _ in range(20):
            try:
                msg = json.loads(_ws_recv_message(sock))
            except Exception:
                break
            if msg.get("id") == 1:
                all_cookies = msg.get("result", {}).get("cookies", [])
                if domain:
                    return [c for c in all_cookies if domain in c.get("domain", "")]
                return all_cookies
    except Exception:
        pass
    finally:
        sock.close()
    return []


def _ws_drain_headers(sock: socket.socket) -> None:
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk


def _ws_frame(data: bytes) -> bytes:
    length = len(data)
    if length < 126:
        header = bytes([0x81, 0x80 | length])
    elif length < 65536:
        header = bytes([0x81, 0xFE]) + struct.pack(">H", length)
    else:
        header = bytes([0x81, 0xFF]) + struct.pack(">Q", length)
    return header + b"\x00\x00\x00\x00" + data  # all-zero mask = no-op transform


def _ws_recv_message(sock: socket.socket) -> bytes:
    data = b""
    while True:
        h = _ws_recv_exact(sock, 2)
        fin = bool(h[0] & 0x80)
        masked = bool(h[1] & 0x80)
        length = h[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", _ws_recv_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack(">Q", _ws_recv_exact(sock, 8))[0]
        if masked:
            mask = _ws_recv_exact(sock, 4)
            payload = bytearray(_ws_recv_exact(sock, length))
            for i in range(length):
                payload[i] ^= mask[i % 4]
            data += bytes(payload)
        else:
            data += _ws_recv_exact(sock, length)
        if fin:
            break
    return data


def _ws_recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("WebSocket connection closed")
        buf += chunk
    return buf


def _manual_cookie_input(url: str) -> list[dict]:
    """Last resort: open system browser, ask user to paste cf_clearance."""
    webbrowser.open(url)
    domain = urlparse(url).hostname or ""
    print()
    print("Could not open Chrome with remote debugging. Please:")
    print("  1. Solve the Cloudflare challenge in the browser that just opened")
    print("  2. Open DevTools (F12) → Application → Cookies")
    print("  3. Copy the value of the 'cf_clearance' cookie")
    print()
    value = input("Paste cf_clearance value (or press Enter to skip): ").strip().strip("\"'")
    if not value or not domain:
        return []
    return [{"name": "cf_clearance", "value": value, "domain": domain, "path": "/"}]


# ---------------------------------------------------------------------------
# Helpers for export_session_state (Playwright path)
# ---------------------------------------------------------------------------

def _wait_for_clearance_cookie(context: Any, timeout_seconds: int = 20) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _has_clearance_cookie(context):
            return
        time.sleep(1)
    raise SystemExit(
        "Cloudflare clearance cookie not found after the browser became usable. "
        "The verification likely did not complete, so the session was not saved."
    )


def _has_clearance_cookie(context: Any) -> bool:
    with_cookie_list = getattr(context, "cookies", None)
    if callable(with_cookie_list):
        try:
            cookies = with_cookie_list()
        except Exception:  # pragma: no cover - browser/runtime specific
            return False
        if isinstance(cookies, list):
            return any(
                isinstance(cookie, dict) and cookie.get("name") == "cf_clearance" and cookie.get("value")
                for cookie in cookies
            )
    return False
