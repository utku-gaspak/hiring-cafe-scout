from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from job_parser.cli import apply_args_to_config, build_fresh_search_config, build_parser, parse_csv
from job_parser.config import (
    SearchConfig,
    build_search_state,
    build_server_seniority_levels,
    load_search_config,
    save_search_config,
)
from job_parser.presets import (
    DEFAULT_PRESET_SLUG,
    get_builtin_preset,
    get_default_config,
    list_all_presets,
    list_saved_presets,
)


class ConfigRoundTripTests(unittest.TestCase):
    def test_search_config_round_trips_to_json_file(self):
        config = SearchConfig(
            keywords=["python", "react"],
            departments=["Software Development", "Engineering"],
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
                "--no-interactive",
                "--keywords",
                "python,go",
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
                "--no-markdown",
            ]
        )

        config = apply_args_to_config(SearchConfig(), args)

        self.assertEqual(config.keywords, ["python", "go"])
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
        self.assertFalse(config.export_markdown)
        self.assertTrue(config.export_json)

    def test_config_file_shape_is_plain_json_object(self):
        config = SearchConfig(keywords=["rust"])
        payload = config.to_dict()
        encoded = json.dumps(payload)
        decoded = json.loads(encoded)

        self.assertIsInstance(decoded, dict)
        self.assertEqual(decoded["keywords"], ["rust"])


class PresetRegistryTests(unittest.TestCase):
    def test_builtin_default_preset_exists(self):
        preset = get_builtin_preset(DEFAULT_PRESET_SLUG)

        self.assertEqual(preset.slug, DEFAULT_PRESET_SLUG)
        self.assertTrue(preset.builtin)
        self.assertEqual(
            preset.config.keywords,
            [".NET", "C#", "ASP.NET", "TypeScript", "React"],
        )

    def test_default_config_returns_detached_copy(self):
        config = get_default_config()
        config.keywords.append("Python")
        fresh_config = get_default_config()

        self.assertNotIn("Python", fresh_config.keywords)

    def test_fresh_search_config_does_not_inherit_preset_filters(self):
        config = build_fresh_search_config()

        self.assertEqual(config.keywords, [])
        self.assertEqual(config.departments, [])
        self.assertEqual(config.workplace_types, ["Remote", "Hybrid", "Onsite"])
        self.assertEqual(config.allowed_countries, [])
        self.assertEqual(config.remote_scopes, ["Europe", "Worldwide"])
        self.assertEqual(
            config.seniority_terms,
            ["entry", "junior", "associate", "intern", "graduate"],
        )
        self.assertTrue(config.include_unspecified_seniority)
        self.assertEqual(config.commitments, ["Full Time"])
        self.assertTrue(config.export_markdown)
        self.assertTrue(config.export_json)

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


class SearchStateTests(unittest.TestCase):
    def test_search_state_uses_fixed_software_departments(self):
        config = SearchConfig(departments=["Engineering", "Design"])
        search_state = build_search_state(config)

        self.assertIn("Software%20Development", search_state)
        self.assertIn("Engineering", search_state)
        self.assertIn("Information%20Technology", search_state)
        self.assertNotIn("Design", search_state)

    def test_server_seniority_levels_are_built_from_selected_terms(self):
        config = SearchConfig(
            seniority_terms=["entry", "associate", "senior", "manager"],
            include_unspecified_seniority=False,
        )

        self.assertEqual(
            build_server_seniority_levels(config),
            ["Entry Level", "Mid Level", "Senior Level"],
        )

    def test_search_state_uses_selected_seniority_levels(self):
        config = SearchConfig(
            seniority_terms=["mid", "senior"],
            include_unspecified_seniority=False,
        )
        search_state = build_search_state(config)

        self.assertIn("Mid%20Level", search_state)
        self.assertIn("Senior%20Level", search_state)
        self.assertNotIn("Entry%20Level", search_state)


if __name__ == "__main__":
    unittest.main()
