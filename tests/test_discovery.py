from __future__ import annotations

import unittest

from job_parser.discovery import (
    extract_countries_from_payload,
    extract_departments_from_payload,
    extract_locations_from_payload,
    extract_skills_from_payload,
)


class DiscoveryTests(unittest.TestCase):
    def test_extract_departments_prefers_department_scoped_candidates(self):
        payload = {
            "props": {
                "pageProps": {
                    "filters": {
                        "departments": [
                            {"label": "Software Development"},
                            {"label": "Information Technology"},
                            {"label": "Engineering"},
                            {"label": "Design"},
                            {"label": "Product"},
                        ]
                    },
                    "other": {
                        "choices": ["One", "Two", "Three", "Four"],
                    },
                }
            }
        }

        departments = extract_departments_from_payload(payload)

        self.assertEqual(
            departments,
            [
                "Software Development",
                "Information Technology",
                "Engineering",
                "Design",
                "Product",
            ],
        )

    def test_extract_countries_prefers_country_scoped_candidates(self):
        payload = {
            "props": {
                "pageProps": {
                    "filters": {
                        "countries": [
                            {"label": "Germany", "value": "DE"},
                            {"label": "Netherlands", "value": "NL"},
                            {"label": "Poland", "value": "PL"},
                        ]
                    }
                }
            }
        }

        countries = extract_countries_from_payload(payload)

        self.assertEqual(
            [(country.label, country.value) for country in countries],
            [("Germany", "DE"), ("Netherlands", "NL"), ("Poland", "PL")],
        )

    def test_extract_locations_prefers_location_scoped_candidates(self):
        payload = {
            "props": {
                "pageProps": {
                    "filters": {
                        "locations": [
                            {"label": "Berlin"},
                            {"label": "Munich"},
                            {"label": "Hamburg"},
                            {"label": "Remote Europe"},
                        ]
                    }
                }
            }
        }

        locations = extract_locations_from_payload(payload)

        self.assertEqual(locations, ["Berlin", "Munich", "Hamburg", "Remote Europe"])

    def test_extract_departments_returns_empty_when_no_candidates_found(self):
        payload = {"props": {"pageProps": {"items": [1, 2, 3]}}}

        self.assertEqual(extract_departments_from_payload(payload), [])

    def test_extract_departments_prefers_readable_titles_over_opaque_values(self):
        payload = {
            "props": {
                "pageProps": {
                    "filters": {
                        "departments": [
                            {"value": "tJKTovOV7cdujXQD8NQkj4tN23l1", "title": "Software Development"},
                            {"value": "P9hrrnaQK5Nw7uH70BCr6QCS7Cj2", "title": "Information Technology"},
                            {"value": "ooJLNiXOVnUswqi9q8eyJyEHuBh2", "title": "Engineering"},
                        ]
                    }
                }
            }
        }

        departments = extract_departments_from_payload(payload)

        self.assertEqual(
            departments,
            ["Software Development", "Information Technology", "Engineering"],
        )

    def test_extract_departments_rejects_skill_lists(self):
        payload = {
            "props": {
                "pageProps": {
                    "filters": {
                        "departments": [
                            {"label": "Nest.js"},
                            {"label": "Express.js"},
                            {"label": "GraphQL"},
                            {"label": "React"},
                            {"label": "TypeScript"},
                            {"label": "Docker"},
                            {"label": "Kubernetes"},
                        ]
                    }
                }
            }
        }

        departments = extract_departments_from_payload(payload)

        self.assertEqual(departments, [])

    def test_extract_skills_prefers_skill_scoped_candidates(self):
        payload = {
            "props": {
                "pageProps": {
                    "filters": {
                        "skills": [
                            {"label": "Nest.js"},
                            {"label": "Express.js"},
                            {"label": "GraphQL"},
                            {"label": "React"},
                            {"label": "TypeScript"},
                            {"label": "Docker"},
                            {"label": "Kubernetes"},
                        ],
                        "locations": [
                            {"label": "Berlin"},
                            {"label": "Munich"},
                            {"label": "Hamburg"},
                        ],
                    }
                }
            }
        }

        skills = extract_skills_from_payload(payload)

        self.assertEqual(
            skills,
            ["Nest.js", "Express.js", "GraphQL", "React", "TypeScript", "Docker", "Kubernetes"],
        )


if __name__ == "__main__":
    unittest.main()
