from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from job_parser.app import scrape
from job_parser.browser_scraper import (
    _build_search_state,
    _build_search_url,
    _href_targets_page,
    _extract_total_job_count,
    _parse_card_block,
    _parse_job_cards,
    _unwrap_script_result,
)
from job_parser.config import SearchConfig
from job_parser.config import HIRING_CAFE_SENIOR_SENIORITY_LEVELS
from job_parser.browser_scraper import _find_browser_binary


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

    async def test_url_mode_bypasses_local_filters(self) -> None:
        config = SearchConfig(
            keywords=["python"],
            allowed_countries=["DE"],
            seniority_terms=["senior"],
            search_url="https://hiring.cafe/?searchState=%7B%22searchQuery%22%3A%22java%22%7D",
        )
        raw_hit = {
            "objectID": "job-1",
            "source": "hiring.cafe",
            "job_information": {"title": "Ruby Engineer"},
            "enriched_company_data": {"name": "Acme"},
            "v5_processed_job_data": {
                "core_job_title": "Ruby Engineer",
                "company_name": "Acme",
                "formatted_workplace_location": "Berlin, Germany",
                "commitment": ["Full Time"],
                "workplace_type": "Remote",
                "seniority_level": "Senior Level",
                "workplace_cities": ["Berlin"],
                "workplace_countries": ["DE"],
                "requirements_summary": "Ruby",
            },
        }

        with (
            mock.patch("job_parser.app.build_search_state") as build_search_state,
            mock.patch("job_parser.app.build_session") as build_session,
            mock.patch("job_parser.app.fetch_total_count", return_value=1),
            mock.patch("job_parser.app.fetch_jobs_page", return_value=[raw_hit]),
        ):
            build_session.return_value = mock.Mock()
            result = await scrape(config, seen_ids=set())

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Ruby Engineer")
        build_search_state.assert_called_once()
        build_session.assert_called_once()

    def test_browser_search_url_includes_search_state_for_keyword_only_search(self) -> None:
        config = SearchConfig(keywords=["C#"], allowed_countries=[], seniority_terms=[])
        search_state = "%7B%22searchQuery%22%3A%22C%23%22%7D"

        url = _build_search_url(config, search_state)

        self.assertEqual(
            url,
            f"https://hiring.cafe/?searchState={search_state}",
        )

    def test_browser_search_url_prefers_configured_search_url(self) -> None:
        config = SearchConfig(
            keywords=["C#"],
            allowed_countries=[],
            seniority_terms=[],
            search_url="https://hiring.cafe/?searchState=%7B%22searchQuery%22%3A%22java%22%7D",
        )

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


if __name__ == "__main__":
    unittest.main()
