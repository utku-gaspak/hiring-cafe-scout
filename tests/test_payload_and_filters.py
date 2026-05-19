from __future__ import annotations

import unittest
from datetime import datetime, timezone

from job_parser.config import SearchConfig
from job_parser.filters import matches_commitment, matches_keyword, matches_location, matches_seniority
from job_parser.models import GeoPoint, Job
from job_parser.payload import parse_job


def make_hit(**overrides):
    processed = {
        "core_job_title": "Junior React Engineer",
        "requirements_summary": "Build React interfaces with TypeScript",
        "technical_tools": ["React", "TypeScript"],
        "seniority_level": "Entry Level",
        "commitment": ["Full Time"],
        "workplace_type": "Remote",
        "formatted_workplace_location": "Berlin, Berlin, Germany",
        "workplace_cities": ["Berlin, Berlin, DE"],
        "workplace_countries": ["DE"],
        "workplace_continents": ["Europe"],
        "boundless_workplace_continents": [],
        "is_workplace_worldwide_ok": False,
        "estimated_publish_date_millis": 1747612800000,
        "min_industry_and_role_yoe": 1,
    }
    hit = {
        "objectID": "personio___example___123",
        "id": "fallback-id",
        "source": "personio",
        "apply_url": "https://example.com/apply",
        "job_information": {"title": "Junior React Engineer (m/w/d)"},
        "enriched_company_data": {"name": "Example Co"},
        "v5_processed_job_data": processed,
        "_geoloc": [{"lat": 52.52, "lon": 13.405}],
    }
    for key, value in overrides.items():
        if key == "v5_processed_job_data":
            hit[key] = value
        else:
            hit[key] = value
    return hit


class PayloadTests(unittest.TestCase):
    def test_parse_job_normalizes_expected_fields(self):
        job = parse_job(make_hit(), "https://hiring.cafe/job/abc")

        self.assertEqual(job.object_id, "personio___example___123")
        self.assertEqual(job.company, "Example Co")
        self.assertEqual(job.title, "Junior React Engineer")
        self.assertEqual(job.commitments, ["Full Time"])
        self.assertEqual(job.countries, ["DE"])
        self.assertEqual(job.technical_tools, ["React", "TypeScript"])
        self.assertEqual(job.posted_str, "2025-05-19")
        self.assertEqual(job.geolocations[0].lat, 52.52)

    def test_parse_job_falls_back_when_optional_fields_are_missing(self):
        hit = make_hit(
            objectID="",
            id="fallback-id",
            enriched_company_data={},
            v5_processed_job_data={
                "commitment": "Full Time",
                "formatted_workplace_location": "",
                "workplace_type": "Hybrid",
                "workplace_countries": ["DE"],
            },
            job_information={"title": "Backend Engineer (m/w/d)"},
            _geoloc=[{"lat": None, "lon": 13.4}],
        )

        job = parse_job(hit, "")

        self.assertEqual(job.object_id, "fallback-id")
        self.assertEqual(job.title, "Backend Engineer")
        self.assertEqual(job.company, "Unknown")
        self.assertEqual(job.location, "Unknown")
        self.assertEqual(job.commitment, "Full Time")
        self.assertEqual(job.geolocations, [])


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.config = SearchConfig(keywords=["React"], cities=[])
        self.job = Job(
            object_id="1",
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
            geolocations=[GeoPoint(lat=52.52, lon=13.405)],
        )

    def test_keyword_filter_matches_title_tools_and_summary(self):
        self.assertTrue(matches_keyword(self.job, self.config))
        self.config.keywords = ["TypeScript"]
        self.assertTrue(matches_keyword(self.job, self.config))
        self.config.keywords = ["missing"]
        self.assertFalse(matches_keyword(self.job, self.config))

    def test_seniority_filter_keeps_blank_and_juniorish_values(self):
        self.assertTrue(matches_seniority(self.job))
        self.job.seniority_level = ""
        self.assertTrue(matches_seniority(self.job))
        self.job.seniority_level = "Mid Level"
        self.assertFalse(matches_seniority(self.job))

    def test_commitment_filter_accepts_full_time_lists(self):
        self.assertTrue(matches_commitment(self.job))
        self.job.commitments = ["Contract"]
        self.job.commitment = "Contract"
        self.assertFalse(matches_commitment(self.job))

    def test_location_filter_allows_remote_europe_and_city_matches(self):
        self.assertTrue(matches_location(self.job, self.config))

        self.job.work_type = "Hybrid"
        self.config.cities = ["Berlin"]
        self.assertTrue(matches_location(self.job, self.config))

        self.config.cities = ["Munich"]
        self.assertFalse(matches_location(self.job, self.config))

    def test_location_filter_supports_radius(self):
        self.job.work_type = "Hybrid"
        self.config.cities = []
        self.config.radius_city = "Berlin"
        self.config.radius_km = 10
        self.assertTrue(matches_location(self.job, self.config))

        self.config.radius_km = 1
        self.job.geolocations = [GeoPoint(lat=48.137, lon=11.576)]
        self.assertFalse(matches_location(self.job, self.config))


if __name__ == "__main__":
    unittest.main()
