from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from job_parser.config import SearchConfig
from job_parser.exporters.json import save_json
from job_parser.exporters.markdown import save_markdown
from job_parser.models import GeoPoint, Job


def make_job() -> Job:
    return Job(
        object_id="job-1",
        source="personio",
        title="Junior React Engineer",
        raw_title="Junior React Engineer",
        company="Example Co",
        location="Berlin, Berlin, Germany",
        work_type="Remote",
        commitment="Full Time",
        commitments=["Full Time"],
        cities=["Berlin, Berlin, DE"],
        countries=["DE"],
        continents=["Europe"],
        worldwide_remote=False,
        technical_tools=["React", "TypeScript"],
        requirements_summary="Build React apps",
        seniority_level="Entry Level",
        posted_str="2025-05-19",
        date_obj=datetime(2025, 5, 19, tzinfo=timezone.utc),
        url="https://hiring.cafe/job/abc",
        apply_url="https://example.com/apply",
        geolocations=[GeoPoint(lat=52.52, lon=13.405)],
    )


class ExporterTests(unittest.TestCase):
    def test_markdown_and_json_exports_use_normalized_job_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config = SearchConfig(
                keywords=["React"],
                markdown_output=str(temp_path / "jobs.md"),
                json_output=str(temp_path / "jobs.json"),
            )
            jobs = [make_job()]

            save_markdown(jobs, config)
            save_json(jobs, config)

            markdown = (temp_path / "jobs.md").read_text(encoding="utf-8")
            json_payload = json.loads((temp_path / "jobs.json").read_text(encoding="utf-8"))

            self.assertIn("Example Co — Junior React Engineer", markdown)
            self.assertEqual(json_payload["filters"]["keywords"], ["React"])
            self.assertEqual(json_payload["results"][0]["id"], "job-1")
            self.assertEqual(json_payload["results"][0]["geolocations"][0]["lat"], 52.52)


if __name__ == "__main__":
    unittest.main()
