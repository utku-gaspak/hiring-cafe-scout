from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from job_parser.api import (
    build_search_state,
    build_session,
    extract_job_records,
)
from job_parser.config import SearchConfig
from job_parser.config import (
    HIRING_CAFE_ENTRY_SENIORITY_LEVELS,
    HIRING_CAFE_SENIOR_SENIORITY_LEVELS,
)


GERMANY_LOCATION = {
    "id": "ZhY1yZQBoEtHp_8UEq3V",
    "types": ["country"],
    "address_components": [
        {
            "long_name": "Germany",
            "short_name": "DE",
            "types": ["country"],
        }
    ],
    "formatted_address": "Germany",
    "population": 82927922,
    "workplace_types": [],
    "options": {"flexible_regions": ["anywhere_in_continent", "anywhere_in_world"]},
}


class ApiPayloadTests(unittest.TestCase):
    def test_build_search_state_uses_entry_seniority_when_selected(self):
        config = SearchConfig(keywords=[], allowed_countries=[])
        payload = build_search_state(config)

        self.assertEqual(payload, {"seniorityLevel": HIRING_CAFE_ENTRY_SENIORITY_LEVELS})

    def test_build_search_state_uses_query_entry_seniority_and_country_only(self):
        config = SearchConfig(
            keywords=["C#", ".NET"],
            allowed_countries=["DE"],
            commitments=["Contract"],
        )
        payload = build_search_state(config)

        self.assertEqual(payload["searchQuery"], "C# .NET")
        self.assertEqual(payload["technologyKeywordsQuery"], '"C#" AND ".NET"')
        self.assertEqual(payload["seniorityLevel"], HIRING_CAFE_ENTRY_SENIORITY_LEVELS)
        self.assertEqual(len(payload["locations"]), 1)
        self.assertEqual(payload["locations"][0], GERMANY_LOCATION)
        self.assertNotIn("workplaceTypes", payload)
        self.assertNotIn("commitmentTypes", payload)
        self.assertNotIn("departments", payload)

    def test_build_search_state_omits_seniority_when_terms_are_empty(self):
        config = SearchConfig(keywords=["java"], allowed_countries=[], seniority_terms=[])
        payload = build_search_state(config)

        self.assertEqual(payload, {"searchQuery": "java"})

    def test_build_search_state_uses_technology_keywords_query_for_comma_separated_keywords(self):
        config = SearchConfig(
            keywords=["Java", "Spring Boot"],
            allowed_countries=[],
            seniority_terms=[],
        )
        payload = build_search_state(config)

        self.assertEqual(
            payload,
            {
                "searchQuery": "Java Spring Boot",
                "technologyKeywordsQuery": '"Java" AND "Spring Boot"',
            },
        )

    def test_build_search_state_uses_senior_level_when_selected(self):
        config = SearchConfig(
            keywords=["java"],
            allowed_countries=[],
            seniority_terms=["senior"],
        )
        payload = build_search_state(config)

        self.assertEqual(
            payload,
            {
                "searchQuery": "java",
                "seniorityLevel": HIRING_CAFE_SENIOR_SENIORITY_LEVELS,
            },
        )

    def test_build_search_state_includes_country_locations(self):
        config = SearchConfig(allowed_countries=["DE"], keywords=["React"])
        payload = build_search_state(config)

        self.assertEqual(len(payload["locations"]), 1)
        self.assertEqual(payload["locations"][0], GERMANY_LOCATION)

    def test_build_session_loads_storage_state_cookies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "browser-session.json"
            state_path.write_text(
                json.dumps(
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
                ),
                encoding="utf-8",
            )

            session = build_session(SearchConfig(session_state_file=str(state_path)))

        self.assertEqual(session._cf_cookies.get("cf_clearance"), "abc123")

    def test_extract_job_records_handles_common_shapes(self):
        self.assertEqual(
            extract_job_records({"results": [{"id": "1"}, {"id": "2"}]}),
            [{"id": "1"}, {"id": "2"}],
        )
        self.assertEqual(
            extract_job_records({"hits": {"hits": [{"_source": {"id": "3"}}]}}),
            [{"id": "3"}],
        )
        self.assertEqual(
            extract_job_records([{"id": "4"}, {"id": "5"}]),
            [{"id": "4"}, {"id": "5"}],
        )


if __name__ == "__main__":
    unittest.main()
