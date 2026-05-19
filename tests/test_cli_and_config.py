from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from job_parser.cli import apply_args_to_config, build_parser, parse_csv
from job_parser.config import SearchConfig, load_search_config, save_search_config


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


if __name__ == "__main__":
    unittest.main()
