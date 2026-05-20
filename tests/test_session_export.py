from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from job_parser.cli import build_parser
from job_parser.session_export import export_session_state, resolve_cloudflare_in_browser


class _FakePage:
    def __init__(self) -> None:
        self.goto_calls: list[tuple[str, str, int]] = []
        self.init_scripts: list[str] = []
        self.extra_headers: dict[str, str] = {}

    def add_init_script(self, script: str) -> None:
        self.init_scripts.append(script)

    def set_extra_http_headers(self, headers: dict[str, str]) -> None:
        self.extra_headers.update(headers)

    def goto(self, url: str, wait_until: str, timeout: int) -> None:
        self.goto_calls.append((url, wait_until, timeout))


class _FakeContext:
    def __init__(self, output_payload: dict[str, object]) -> None:
        self.page = _FakePage()
        self.output_payload = output_payload
        self.storage_state_calls: list[str] = []

    def new_page(self) -> _FakePage:
        return self.page

    def cookies(self) -> list[dict[str, object]]:
        cookies = self.output_payload.get("cookies")
        if isinstance(cookies, list):
            return [item for item in cookies if isinstance(item, dict)]
        return []

    def storage_state(self, path: str) -> None:
        self.storage_state_calls.append(path)
        Path(path).write_text(json.dumps(self.output_payload), encoding="utf-8")


class _FakeBrowser:
    def __init__(self, context: _FakeContext) -> None:
        self.context = context
        self.closed = False

    def new_context(self, **_: object) -> _FakeContext:
        return self.context

    def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(self, browser: _FakeBrowser) -> None:
        self.browser = browser
        self.launch_calls: list[dict[str, object]] = []

    def launch(self, **kwargs: object) -> _FakeBrowser:
        self.launch_calls.append(dict(kwargs))
        return self.browser


class _FakePlaywright:
    def __init__(self, browser: _FakeBrowser) -> None:
        self.chromium = _FakeChromium(browser)


class _FakePlaywrightContextManager:
    def __init__(self, browser: _FakeBrowser) -> None:
        self.playwright = _FakePlaywright(browser)

    def __enter__(self) -> _FakePlaywright:
        return self.playwright

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class SessionExportTests(unittest.TestCase):
    def test_build_parser_accepts_session_export_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--export-session-state",
                "browser-session.json",
                "--session-state-url",
                "https://example.com",
            ]
        )

        self.assertEqual(args.export_session_state, "browser-session.json")
        self.assertEqual(args.session_state_url, "https://example.com")

    def test_export_session_state_writes_storage_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "browser-session.json"
            context = _FakeContext(
                {
                    "cookies": [
                        {
                            "name": "cf_clearance",
                            "value": "abc123",
                            "domain": "hiring.cafe",
                            "path": "/",
                        }
                    ]
                }
            )
            browser = _FakeBrowser(context)
            factory = lambda: _FakePlaywrightContextManager(browser)

            with mock.patch("builtins.input", return_value=""):
                export_session_state(
                    str(output_path),
                    "https://example.com",
                    sync_playwright_factory=factory,
                )

            saved = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertTrue(browser.closed)
        self.assertEqual(context.page.goto_calls[0][0], "https://example.com")
        self.assertTrue(context.page.init_scripts)
        self.assertEqual(saved["cookies"][0]["name"], "cf_clearance")

    def test_resolve_cloudflare_in_browser_injects_cookies_into_session(self) -> None:
        def fake_provider(url: str) -> list[dict]:
            return [
                {"name": "cf_clearance", "value": "xyz789", "domain": "hiring.cafe", "path": "/"},
                {"name": "__cf_bm", "value": "bm_token", "domain": "hiring.cafe", "path": "/"},
            ]

        session = mock.MagicMock()
        session._cf_cookies = {}
        resolve_cloudflare_in_browser(session, "https://hiring.cafe", _cookie_provider=fake_provider)

        self.assertEqual(session._cf_cookies["cf_clearance"], "xyz789")
        self.assertEqual(session._cf_cookies["__cf_bm"], "bm_token")

    def test_resolve_cloudflare_in_browser_skips_cookies_with_missing_fields(self) -> None:
        def fake_provider(url: str) -> list[dict]:
            return [
                {"name": "cf_clearance", "value": "good", "domain": "hiring.cafe", "path": "/"},
                {"name": "", "value": "noname", "domain": "hiring.cafe", "path": "/"},
                {"name": "nodomain", "value": "val", "domain": "", "path": "/"},
            ]

        session = mock.MagicMock()
        session._cf_cookies = {}
        resolve_cloudflare_in_browser(session, "https://hiring.cafe", _cookie_provider=fake_provider)

        self.assertEqual(len(session._cf_cookies), 1)
        self.assertIn("cf_clearance", session._cf_cookies)

    def test_export_session_state_refuses_challenge_only_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "browser-session.json"
            context = _FakeContext(
                {
                    "cookies": [
                        {
                            "name": "cf_chl_rc_ni",
                            "value": "3",
                            "domain": "hiring.cafe",
                            "path": "/",
                        }
                    ]
                }
            )
            browser = _FakeBrowser(context)
            factory = lambda: _FakePlaywrightContextManager(browser)

            with mock.patch("builtins.input", return_value=""):
                with self.assertRaises(SystemExit):
                    export_session_state(
                        str(output_path),
                        "https://example.com",
                        sync_playwright_factory=factory,
                    )

        self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
