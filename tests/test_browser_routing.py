from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock

from job_parser.app import scrape
from job_parser.browser_scraper import (
    CloudflareVerificationRequired,
    _attach_ssr_hits,
    _build_job_from_card,
    _build_browser_options,
    _build_progress_payload,
    _build_search_state,
    _build_search_url,
    _browser_fetch_search_page,
    _href_targets_page,
    _extract_total_job_count,
    _parse_card_block,
    _parse_job_cards,
    _scrape_with_browser,
    _unwrap_script_result,
)
from job_parser.config import SearchConfig
from job_parser.config import HIRING_CAFE_SENIOR_SENIORITY_LEVELS
from job_parser.browser_scraper import _find_browser_binary


class _FakeChromiumOptions:
    def __init__(self) -> None:
        self.headless = False
        self.arguments: list[str] = []

    def add_argument(self, argument: str) -> None:
        self.arguments.append(argument)

    def set_accept_languages(self, value: str) -> None:
        self.accept_languages = value


class _FakePageLoadState:
    INTERACTIVE = "interactive"


class _ChallengeTab:
    async def go_to(self, url: str) -> None:
        self.url = url

    async def execute_script(self, script: str):
        if "document.title" in script:
            return '"Just a moment..."'
        return '"Enable JavaScript and cookies"'


class _ChallengeBrowser:
    def __init__(self, options: object) -> None:
        self.options = options

    async def start(self) -> _ChallengeTab:
        return _ChallengeTab()

    async def stop(self) -> None:
        return None


class BrowserRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_profile_routes_directly_to_browser_scraper(self) -> None:
        config = SearchConfig(keywords=["React"], browser_profile_dir="browser-profile")
        browser_scraper = mock.Mock(return_value=[])

        with (
            mock.patch("job_parser.app.build_search_state") as build_search_state,
            mock.patch("job_parser.app.build_session") as build_session,
            mock.patch("job_parser.app.fetch_total_count") as fetch_total_count,
            mock.patch("job_parser.app.fetch_jobs_page") as fetch_jobs_page,
            mock.patch("job_parser.app.scrape_with_browser", new=browser_scraper)
        ):
            result = await scrape(config, seen_ids=set())

        self.assertEqual(result, [])
        browser_scraper.assert_called_once()
        build_search_state.assert_not_called()
        build_session.assert_not_called()
        fetch_total_count.assert_not_called()
        fetch_jobs_page.assert_not_called()

    async def test_url_mode_routes_directly_to_browser_without_local_filters(self) -> None:
        config = SearchConfig(
            keywords=["python"],
            allowed_countries=["DE"],
            seniority_terms=["senior"],
            search_url="https://hiring.cafe/?searchState=%7B%22searchQuery%22%3A%22java%22%7D",
        )
        browser_scraper = mock.Mock(return_value=[])

        with (
            mock.patch("job_parser.app.build_search_state") as build_search_state,
            mock.patch("job_parser.app.build_session") as build_session,
            mock.patch("job_parser.app.fetch_total_count") as fetch_total_count,
            mock.patch("job_parser.app.fetch_jobs_page") as fetch_jobs_page,
            mock.patch("job_parser.app.scrape_with_browser", new=browser_scraper),
        ):
            result = await scrape(config, seen_ids=set())

        self.assertEqual(result, [])
        browser_scraper.assert_called_once_with(
            config,
            set(),
            profile_dir=None,
            apply_local_filters=False,
        )
        build_search_state.assert_not_called()
        build_session.assert_not_called()
        fetch_total_count.assert_not_called()
        fetch_jobs_page.assert_not_called()

    async def test_headless_challenge_writes_progress_and_exits_without_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            binary = os.path.join(temp_dir, "chrome")
            progress_path = os.path.join(temp_dir, "progress.json")
            with open(binary, "w", encoding="utf-8") as file_obj:
                file_obj.write("#!/bin/sh\n")
            os.chmod(binary, 0o755)
            config = SearchConfig(
                search_url="https://hiring.cafe/?searchState=%7B%22searchQuery%22%3A%22java%22%7D",
                progress_output=progress_path,
            )

            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "CAFE_SCOUT_BROWSER_BINARY": binary,
                        "CAFE_SCOUT_HEADLESS": "1",
                    },
                    clear=False,
                ),
                mock.patch("builtins.input") as input_mock,
            ):
                with self.assertRaises(SystemExit) as error:
                    await _scrape_with_browser(
                        Chrome=_ChallengeBrowser,
                        ChromiumOptions=_FakeChromiumOptions,
                        PageLoadState=_FakePageLoadState,
                        config=config,
                        seen_ids=set(),
                        profile_dir=None,
                        apply_local_filters=False,
                    )

            self.assertIn("Verification required", str(error.exception))
            input_mock.assert_not_called()
            with open(progress_path, encoding="utf-8") as file_obj:
                progress = json.load(file_obj)
            self.assertEqual(progress["status"], "needs_verification")
            self.assertEqual(progress["message"], "Cloudflare challenge detected")

    async def test_search_page_challenge_raises_verification_required(self) -> None:
        with self.assertRaises(CloudflareVerificationRequired):
            await _browser_fetch_search_page(
                _ChallengeTab(),
                "https://hiring.cafe/?searchState=%7B%22searchQuery%22%3A%22java%22%7D",
                0,
            )

    def test_browser_search_url_includes_search_state_for_keyword_only_search(self) -> None:
        config = SearchConfig(keywords=["C#"], allowed_countries=[], seniority_terms=[])
        search_state = "%7B%22searchQuery%22%3A%22C%23%22%7D"

        url = _build_search_url(config, search_state)

        self.assertEqual(
            url,
            f"https://hiring.cafe/?searchState={search_state}",
        )

    def test_browser_search_url_prefers_configured_search_url(self) -> None:
        search_url = "https://hiring.cafe/?searchState=%7B%22searchQuery%22%3A%22java%22%7D"
        config = SearchConfig(
            keywords=["C#"],
            allowed_countries=[],
            seniority_terms=[],
            search_url=search_url,
        )

        self.assertEqual(_build_search_url(config, "ignored"), search_url)
        self.assertEqual(
            _build_search_state(config),
            "%7B%22searchQuery%22%3A%22java%22%7D",
        )

    def test_browser_search_state_is_encoded_for_query_urls(self) -> None:
        config = SearchConfig(keywords=["C#"], allowed_countries=[], seniority_terms=[])

        self.assertEqual(
            _build_search_state(config),
            "%7B%22searchQuery%22%3A%22C%23%22%7D",
        )

    def test_browser_search_state_uses_technology_keywords_query_for_comma_separated_keywords(self) -> None:
        config = SearchConfig(keywords=["Java", "Spring Boot"], allowed_countries=[], seniority_terms=[])

        self.assertEqual(
            _build_search_state(config),
            "%7B%22searchQuery%22%3A%22Java+Spring+Boot%22%2C%22technologyKeywordsQuery%22%3A%22%5C%22Java%5C%22+AND+%5C%22Spring+Boot%5C%22%22%7D",
        )

    def test_browser_search_state_adds_germany_location_payload(self) -> None:
        config = SearchConfig(keywords=["Java", "Spring Boot"], allowed_countries=["DE"], seniority_terms=[])

        self.assertEqual(
            _build_search_state(config),
            "%7B%22searchQuery%22%3A%22Java+Spring+Boot%22%2C%22technologyKeywordsQuery%22%3A%22%5C%22Java%5C%22+AND+%5C%22Spring+Boot%5C%22%22%2C%22locations%22%3A%5B%7B%22id%22%3A%22ZhY1yZQBoEtHp_8UEq3V%22%2C%22types%22%3A%5B%22country%22%5D%2C%22address_components%22%3A%5B%7B%22long_name%22%3A%22Germany%22%2C%22short_name%22%3A%22DE%22%2C%22types%22%3A%5B%22country%22%5D%7D%5D%2C%22formatted_address%22%3A%22Germany%22%2C%22population%22%3A82927922%2C%22workplace_types%22%3A%5B%5D%2C%22options%22%3A%7B%22flexible_regions%22%3A%5B%22anywhere_in_continent%22%2C%22anywhere_in_world%22%5D%7D%7D%5D%7D",
        )

    def test_browser_entry_search_state_matches_hiringcafe_url_shape(self) -> None:
        config = SearchConfig(keywords=["java"], allowed_countries=[])

        self.assertEqual(
            _build_search_state(config),
            "%7B%22searchQuery%22%3A%22java%22%2C%22seniorityLevel%22%3A%5B%22No+Prior+Experience+Required%22%2C%22Entry+Level%22%2C%22Mid+Level%22%5D%7D",
        )

    def test_browser_senior_search_state_matches_hiringcafe_url_shape(self) -> None:
        config = SearchConfig(keywords=["java"], allowed_countries=[], seniority_terms=["senior"])

        self.assertEqual(
            _build_search_state(config),
            "%7B%22searchQuery%22%3A%22java%22%2C%22seniorityLevel%22%3A%5B%22Senior+Level%22%5D%7D",
        )

    def test_href_targets_page_matches_searchstate_urls(self) -> None:
        href = (
            "https://hiring.cafe/?searchState=%7B%22searchQuery%22%3A%22C%23%22%7D"
            "&page=2"
        )

        self.assertTrue(_href_targets_page(href, 2))
        self.assertFalse(_href_targets_page(href, 3))

    def test_extract_total_job_count_reads_page_total(self) -> None:
        body_text = "C# jobs 230 jobs Job Posting 1 2 3"

        self.assertEqual(_extract_total_job_count(body_text), 230)

    def test_progress_payload_marks_total_as_estimate(self) -> None:
        payload = _build_progress_payload(
            status="running",
            pages_scraped=2,
            visible_jobs_scraped=60,
            matched_jobs=12,
            estimated_total_jobs=230,
            current_page_listings=30,
            current_page_matched=6,
            skipped_seen=4,
            message="Scraped page 2",
        )

        self.assertEqual(payload["progress_percent"], 26)
        self.assertEqual(payload["pages_scraped"], 2)
        self.assertEqual(payload["matched_jobs"], 12)
        self.assertTrue(payload["total_is_estimate"])

    def test_done_progress_payload_reports_complete_even_when_total_was_inflated(self) -> None:
        payload = _build_progress_payload(
            status="done",
            pages_scraped=5,
            visible_jobs_scraped=180,
            matched_jobs=180,
            estimated_total_jobs=300,
            current_page_listings=0,
            current_page_matched=0,
            skipped_seen=0,
            message="No more visible listings",
        )

        self.assertEqual(payload["progress_percent"], 100)
        self.assertEqual(payload["status"], "done")

    def test_parse_card_block_handles_container_text(self) -> None:
        card = _parse_card_block(
            "\n".join(
                [
                    "Search Backend Engineer Remote",
                    "Rockville, Maryland, United States",
                    "$130k-$150k/yr Remote Full Time",
                    "Image: PTFS",
                    "PTFS: Enterprise content management and digital archiving for government agencies.",
                    "Java, Spring, Spring Boot, Solr, Elasticsearch, OpenSearch, Apache Lucene, XML, Prometheus, Grafana, JMeter, GitLab, Jenkins, Maven, Nexus, Ansible, Linux",
                    "Job Posting",
                    "View all",
                ]
            ),
            "https://hiring.cafe/jobs/search-backend-engineer-remote",
        )

        self.assertIsNotNone(card)
        self.assertEqual(card["title"], "Search Backend Engineer Remote")
        self.assertEqual(card["location"], "Rockville, Maryland, United States")
        self.assertEqual(card["company"], "PTFS")
        self.assertEqual(card["url"], "https://hiring.cafe/jobs/search-backend-engineer-remote")

    def test_unwrap_script_result_extracts_nested_values(self) -> None:
        wrapped = {"id": 1, "result": {"result": {"type": "string", "value": "HiringCafe"}}}

        self.assertEqual(_unwrap_script_result(wrapped), "HiringCafe")

    def test_parse_job_cards_ignores_non_list_link_handles(self) -> None:
        body_text = "\n".join(
            [
                "Software Developer C++",
                "Hannover or Berlin or Karlsruhe",
                "Hybrid",
                "Full Time",
                "VIER: AI-powered platform for automated customer communication and service.",
                "C++, PHP, Golang, JavaScript, Python",
                "Job Posting",
            ]
        )
        remote_handle = {"type": "object", "subtype": "array", "objectId": "1.2.3"}

        cards = _parse_job_cards(body_text, remote_handle)

        self.assertEqual(len(cards), 1)
        self.assertTrue(cards[0]["title"])
        self.assertEqual(cards[0]["url"], "")

    def test_browser_binary_env_override_is_respected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            binary = os.path.join(temp_dir, "chrome")
            with open(binary, "w", encoding="utf-8") as file_obj:
                file_obj.write("#!/bin/sh\n")
            os.chmod(binary, 0o755)

            with mock.patch.dict(os.environ, {"CAFE_SCOUT_BROWSER_BINARY": binary}, clear=False):
                self.assertEqual(_find_browser_binary(), binary)

    def test_browser_options_are_visible_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            binary = os.path.join(temp_dir, "chrome")
            with open(binary, "w", encoding="utf-8") as file_obj:
                file_obj.write("#!/bin/sh\n")
            os.chmod(binary, 0o755)

            with mock.patch.dict(os.environ, {"CAFE_SCOUT_BROWSER_BINARY": binary}, clear=False):
                options = _build_browser_options(
                    ChromiumOptions=_FakeChromiumOptions,
                    PageLoadState=_FakePageLoadState,
                    profile_dir=None,
                )

            self.assertFalse(options.headless)
            self.assertEqual(options.start_timeout, 60)
            self.assertNotIn("--headless=new", options.arguments)
            self.assertIn("--no-sandbox", options.arguments)
            self.assertIn("--disable-setuid-sandbox", options.arguments)
            self.assertIn("--disable-dev-shm-usage", options.arguments)

    def test_browser_options_can_run_headless_for_docker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            binary = os.path.join(temp_dir, "chrome")
            with open(binary, "w", encoding="utf-8") as file_obj:
                file_obj.write("#!/bin/sh\n")
            os.chmod(binary, 0o755)

            with mock.patch.dict(
                os.environ,
                {
                    "CAFE_SCOUT_BROWSER_BINARY": binary,
                    "CAFE_SCOUT_HEADLESS": "1",
                },
                clear=False,
            ):
                options = _build_browser_options(
                    ChromiumOptions=_FakeChromiumOptions,
                    PageLoadState=_FakePageLoadState,
                    profile_dir=None,
                )

            self.assertTrue(options.headless)
            self.assertEqual(options.start_timeout, 60)
            self.assertIn("--headless=new", options.arguments)
            self.assertIn("--disable-setuid-sandbox", options.arguments)

    def test_attach_ssr_hits_matches_by_job_identity_not_position(self) -> None:
        cards = [
            {
                "url": "https://hiring.cafe/job/abc123",
                "apply_url": "",
                "title": "Software Engineer",
                "company": "Example Co",
            },
            {
                "url": "https://hiring.cafe/job/def456",
                "apply_url": "",
                "title": "Platform Engineer",
                "company": "Other Co",
            },
        ]
        ssr_hits = [
            {
                "apply_url": "https://other.example/apply/def456",
                "enriched_company_data": {"name": "Other Co"},
                "v5_processed_job_data": {"core_job_title": "Platform Engineer"},
            },
            {
                "apply_url": "https://company.example/careers/apply/abc123",
                "enriched_company_data": {"name": "Example Co"},
                "v5_processed_job_data": {"core_job_title": "Software Engineer"},
            },
        ]

        _attach_ssr_hits(cards, ssr_hits)

        self.assertEqual(cards[0]["url"], "https://hiring.cafe/job/abc123")
        self.assertEqual(cards[0]["apply_url"], "https://company.example/careers/apply/abc123")
        self.assertEqual(cards[1]["url"], "https://hiring.cafe/job/def456")
        self.assertEqual(cards[1]["apply_url"], "https://other.example/apply/def456")

    def test_attach_ssr_hits_leaves_apply_url_empty_for_internal_or_missing_links(self) -> None:
        cards = [
            {
                "url": "https://hiring.cafe/job/abc123",
                "apply_url": "",
                "title": "Software Engineer",
                "company": "Example Co",
            },
            {
                "url": "https://hiring.cafe/job/def456",
                "apply_url": "",
                "title": "Platform Engineer",
                "company": "Other Co",
            },
        ]
        ssr_hits = [
            {
                "apply_url": "https://hiring.cafe/job/abc123",
                "enriched_company_data": {"name": "Example Co"},
                "v5_processed_job_data": {"core_job_title": "Software Engineer"},
            },
            {
                "enriched_company_data": {"name": "Other Co"},
                "v5_processed_job_data": {"core_job_title": "Platform Engineer"},
            },
        ]

        _attach_ssr_hits(cards, ssr_hits)

        self.assertEqual(cards[0]["apply_url"], "")
        self.assertEqual(cards[1]["apply_url"], "")

    def test_build_job_from_matched_ssr_hit_keeps_id_and_job_url_aligned(self) -> None:
        card = {
            "url": "https://hiring.cafe/job/abc123",
            "title": "Wrong Fallback Title",
            "company": "Wrong Fallback Company",
            "ssr_hit": {
                "source": "recruitee",
                "apply_url": "https://company.example/careers/apply/abc123",
                "job_information": {"title": "Software Engineer .NET"},
                "enriched_company_data": {"name": "Example Co"},
                "v5_processed_job_data": {
                    "core_job_title": "Software Engineer .NET",
                    "company_name": "Example Co",
                    "formatted_workplace_location": "Berlin, Germany",
                    "workplace_type": "Hybrid",
                    "commitment": ["Full Time"],
                    "technical_tools": ["C#", ".NET"],
                    "requirements_summary": "Build .NET services",
                    "seniority_level": "Mid Level",
                },
            },
        }

        job = _build_job_from_card(card)
        payload = job.to_dict()

        self.assertEqual(payload["id"], "https://hiring.cafe/job/abc123")
        self.assertEqual(payload["job_url"], "https://hiring.cafe/job/abc123")
        self.assertEqual(payload["title"], "Software Engineer .NET")
        self.assertEqual(payload["company"], "Example Co")
        self.assertEqual(payload["apply_url"], "https://company.example/careers/apply/abc123")


if __name__ == "__main__":
    unittest.main()
