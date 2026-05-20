from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote_plus

from job_parser.cli import apply_args_to_config, build_parser, parse_csv
from job_parser.config import (
    HIRING_CAFE_ENTRY_SENIORITY_LEVELS,
    HIRING_CAFE_SENIOR_SENIORITY_LEVELS,
    SearchConfig,
    build_search_state,
    parse_search_url,
    load_search_config,
    save_search_config,
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
from job_parser.presets import (
    DEFAULT_PRESET_SLUG,
    delete_saved_preset,
    get_builtin_preset,
    get_default_config,
    list_all_presets,
    list_saved_presets,
    save_preset,
    slugify_preset_name,
)


class ConfigRoundTripTests(unittest.TestCase):
    def test_search_config_round_trips_to_json_file(self):
        config = SearchConfig(
            keywords=["python", "react"],
            workplace_types=["Remote"],
            allowed_countries=["DE", "NL"],
            remote_scopes=["Worldwide"],
            seniority_terms=["junior"],
            include_unspecified_seniority=False,
            commitments=["Full Time", "Contract"],
            markdown_output="custom.md",
            json_output="custom.json",
            export_markdown=False,
            export_json=True,
            include_seen=True,
            max_pages=None,
            cities=["Berlin"],
            session_state_file="browser-session.json",
            browser_profile_dir="browser-profile",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            save_search_config(path, config)
            loaded = load_search_config(path)

        self.assertEqual(loaded.to_dict(), config.to_dict())


class CliConfigTests(unittest.TestCase):
    def test_parse_csv_discards_empty_values(self):
        self.assertEqual(parse_csv("a, b, ,c"), ["a", "b", "c"])

    def test_cli_args_override_base_config(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "--keywords",
                "python,go",
                "--url",
                "https://hiring.cafe/?searchState=%7B%22searchQuery%22%3A%22java%22%7D",
                "--workplace-types",
                "Remote,Hybrid",
                "--countries",
                "de,nl",
                "--cities",
                "Berlin,Hamburg",
                "--remote-scopes",
                "Worldwide",
                "--seniority-terms",
                "junior,associate",
                "--no-unspecified-seniority",
                "--commitments",
                "Full Time,Contract",
                "--max-pages",
                "0",
                "--include-seen",
                "--markdown-output",
                "out.md",
                "--json-output",
                "out.json",
                "--session-state",
                "session.json",
                "--browser-profile-dir",
                "browser-profile",
                "--no-markdown",
            ]
        )

        config = apply_args_to_config(SearchConfig(), args)

        self.assertEqual(config.keywords, ["python", "go"])
        self.assertEqual(config.search_url, "https://hiring.cafe/?searchState=%7B%22searchQuery%22%3A%22java%22%7D")
        self.assertEqual(config.workplace_types, ["Remote", "Hybrid"])
        self.assertEqual(config.allowed_countries, ["DE", "NL"])
        self.assertEqual(config.cities, ["Berlin", "Hamburg"])
        self.assertEqual(config.remote_scopes, ["Worldwide"])
        self.assertEqual(config.seniority_terms, ["junior", "associate"])
        self.assertFalse(config.include_unspecified_seniority)
        self.assertEqual(config.commitments, ["Full Time", "Contract"])
        self.assertIsNone(config.max_pages)
        self.assertTrue(config.include_seen)
        self.assertEqual(config.markdown_output, "out.md")
        self.assertEqual(config.json_output, "out.json")
        self.assertEqual(config.session_state_file, "session.json")
        self.assertEqual(config.browser_profile_dir, "browser-profile")
        self.assertFalse(config.export_markdown)
        self.assertTrue(config.export_json)

    def test_config_file_shape_is_plain_json_object(self):
        config = SearchConfig(keywords=["rust"])
        payload = config.to_dict()
        encoded = json.dumps(payload)
        decoded = json.loads(encoded)

        self.assertIsInstance(decoded, dict)
        self.assertEqual(decoded["keywords"], ["rust"])

    def test_parse_search_url_extracts_search_state(self):
        self.assertEqual(
            parse_search_url("https://hiring.cafe/?searchState=%7B%22searchQuery%22%3A%22java%22%7D"),
            "%7B%22searchQuery%22%3A%22java%22%7D",
        )
        self.assertIsNone(parse_search_url("https://hiring.cafe/jobs"))

    def test_config_from_dict_preserves_explicit_empty_filters(self):
        config = SearchConfig.from_dict(
            {
                "keywords": ["C#"],
                "workplace_types": [],
                "allowed_countries": [],
                "remote_scopes": [],
                "seniority_terms": [],
                "commitments": [],
            }
        )

        self.assertEqual(config.keywords, ["C#"])
        self.assertEqual(config.workplace_types, [])
        self.assertEqual(config.allowed_countries, [])
        self.assertEqual(config.remote_scopes, [])
        self.assertEqual(config.seniority_terms, [])
        self.assertEqual(config.commitments, [])


class PresetRegistryTests(unittest.TestCase):
    def test_builtin_default_preset_exists(self):
        preset = get_builtin_preset(DEFAULT_PRESET_SLUG)

        self.assertEqual(preset.slug, DEFAULT_PRESET_SLUG)
        self.assertTrue(preset.builtin)
        self.assertEqual(preset.config.keywords, ["C#"])
        self.assertEqual(preset.config.workplace_types, [])
        self.assertEqual(preset.config.allowed_countries, [])
        self.assertEqual(
            preset.config.seniority_terms,
            ["entry", "junior", "associate", "intern", "graduate", "mid"],
        )
        self.assertEqual(preset.config.commitments, [])

    def test_default_config_returns_detached_copy(self):
        config = get_default_config()
        config.keywords.append("Python")
        fresh_config = get_default_config()

        self.assertNotIn("Python", fresh_config.keywords)

    def test_default_config_uses_entry_level_filter_only(self):
        config = get_default_config()

        self.assertEqual(config.keywords, ["C#"])
        self.assertEqual(config.workplace_types, [])
        self.assertEqual(config.allowed_countries, [])
        self.assertEqual(
            config.seniority_terms,
            ["entry", "junior", "associate", "intern", "graduate", "mid"],
        )
        self.assertEqual(config.commitments, [])

    def test_saved_presets_are_loaded_from_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "frontend-berlin.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "Frontend Berlin",
                        "description": "Saved test preset",
                        "config": {
                            "keywords": ["React"],
                            "cities": ["Berlin"],
                        },
                    }
                ),
                encoding="utf-8",
            )

            presets = list_saved_presets(temp_dir)

        self.assertIn("frontend-berlin", presets)
        self.assertFalse(presets["frontend-berlin"].builtin)
        self.assertEqual(presets["frontend-berlin"].config.keywords, ["React"])

    def test_all_presets_include_builtin_and_saved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "data-eu.json"
            path.write_text(
                json.dumps(
                    {
                        "slug": "data-eu",
                        "name": "Data EU",
                        "config": {"keywords": ["Python"]},
                    }
                ),
                encoding="utf-8",
            )

            presets = list_all_presets(temp_dir)

        self.assertIn(DEFAULT_PRESET_SLUG, presets)
        self.assertIn("data-eu", presets)

    def test_save_preset_round_trips_full_config(self):
        config = SearchConfig(
            keywords=["React", "TypeScript"],
            allowed_countries=["DE", "NL"],
            markdown_output="frontend.md",
            json_output="frontend.json",
            cities=["Berlin"],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            preset = save_preset(
                name="Frontend Berlin",
                description="Saved preset",
                config=config,
                directory=temp_dir,
            )
            loaded = list_saved_presets(temp_dir)[preset.slug]

        self.assertEqual(preset.slug, "frontend-berlin")
        self.assertEqual(loaded.config.to_dict(), config.to_dict())
        self.assertEqual(loaded.description, "Saved preset")

    def test_slugify_preset_name_normalizes_filename(self):
        self.assertEqual(slugify_preset_name("  My Frontend Preset  "), "my-frontend-preset")

    def test_delete_saved_preset_removes_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            save_preset(
                name="Temporary Preset",
                description="To be deleted",
                config=SearchConfig(keywords=["Python"]),
                directory=temp_dir,
            )

            deleted = delete_saved_preset("temporary-preset", temp_dir)
            presets = list_saved_presets(temp_dir)

        self.assertTrue(deleted)
        self.assertNotIn("temporary-preset", presets)


class SearchStateTests(unittest.TestCase):
    def test_search_state_uses_query_seniority_and_country_only(self):
        config = SearchConfig(keywords=["C#", ".NET"], allowed_countries=["DE"])
        search_state = json.loads(unquote_plus(build_search_state(config)))

        self.assertEqual(search_state["searchQuery"], "C# .NET")
        self.assertEqual(search_state["technologyKeywordsQuery"], '"C#" AND ".NET"')
        self.assertEqual(search_state["seniorityLevel"], HIRING_CAFE_ENTRY_SENIORITY_LEVELS)
        self.assertEqual(search_state["locations"][0], GERMANY_LOCATION)
        self.assertNotIn("workplaceTypes", search_state)
        self.assertNotIn("commitmentTypes", search_state)
        self.assertNotIn("departments", search_state)

    def test_search_state_uses_other_scope_by_default(self):
        config = SearchConfig(keywords=[], allowed_countries=[])
        search_state = build_search_state(config)

        self.assertEqual(
            json.loads(unquote_plus(search_state)),
            {"seniorityLevel": HIRING_CAFE_ENTRY_SENIORITY_LEVELS},
        )

    def test_search_state_omits_seniority_when_terms_are_empty(self):
        config = SearchConfig(keywords=["java"], allowed_countries=[], seniority_terms=[])
        search_state = json.loads(unquote_plus(build_search_state(config)))

        self.assertEqual(search_state, {"searchQuery": "java"})

    def test_search_state_uses_technology_keywords_query_for_comma_separated_keywords(self):
        config = SearchConfig(keywords=["Java", "Spring Boot"], allowed_countries=[], seniority_terms=[])
        search_state = json.loads(unquote_plus(build_search_state(config)))

        self.assertEqual(
            search_state,
            {
                "searchQuery": "Java Spring Boot",
                "technologyKeywordsQuery": '"Java" AND "Spring Boot"',
            },
        )

    def test_search_state_uses_senior_level_when_terms_are_senior(self):
        config = SearchConfig(keywords=["java"], allowed_countries=[], seniority_terms=["senior"])
        search_state = json.loads(unquote_plus(build_search_state(config)))

        self.assertEqual(
            search_state,
            {
                "searchQuery": "java",
                "seniorityLevel": HIRING_CAFE_SENIOR_SENIORITY_LEVELS,
            },
        )


if __name__ == "__main__":
    unittest.main()
