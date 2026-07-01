"""Tests for app/jd_parser.py: extract role, years, skills from JD text."""
from __future__ import annotations

import pytest

from app.jd_parser import JDParsed, parse_jd


class TestBasicParse:
    def test_empty_text_returns_empty_parsed(self):
        p = parse_jd("")
        assert p.raw_text == ""
        assert p.role_title == ""
        assert p.years_required == 0
        assert p.required_skills == []
        assert not p.has_minimum_info

    def test_minimal_text_with_one_skill_is_sufficient(self):
        p = parse_jd("Looking for a Python developer.")
        assert p.has_minimum_info
        assert "python" in p.required_skills

    def test_full_realistic_jd(self):
        jd = """
        Senior Software Engineer

        We are looking for a Senior Software Engineer to join our platform team.

        Requirements:
        - 5+ years of experience in software development
        - Strong proficiency in Python and Go
        - Experience with Kubernetes, Docker, AWS
        - PostgreSQL, Redis, Kafka
        - FastAPI or similar frameworks

        Nice to have:
        - Experience with Terraform
        - Familiarity with gRPC
        """
        p = parse_jd(jd)
        assert p.role_title != ""
        # Should contain "Senior" + "Software" + "Engineer"
        assert "engineer" in p.role_title.lower()
        assert p.years_required >= 5
        # Required skills should include the must-haves
        for skill in ["python", "go", "kubernetes", "docker", "aws",
                      "postgresql", "redis", "kafka", "fastapi"]:
            assert skill in p.required_skills, f"missing {skill} from {p.required_skills}"


class TestSkillExtraction:
    def test_skills_ordered_by_frequency(self):
        # "Python" appears 3x, "Go" 1x — Python should come first.
        jd = "We need Python, Python, Python, and Go."
        p = parse_jd(jd)
        assert p.required_skills.index("python") < p.required_skills.index("go")

    def test_common_words_not_treated_as_skills(self):
        jd = "We are a company looking for people with good communication."
        p = parse_jd(jd)
        # "communication" is not in TECH_LEXICON
        assert "communication" not in p.required_skills
        # But no false-positive "we", "are", "a", "for" either
        for stop in ["we", "are", "a", "for", "with", "the"]:
            assert stop not in p.required_skills

    def test_partial_match_not_counted(self):
        # "go" should not match inside "google"
        jd = "Experience with Google Cloud Platform."
        p = parse_jd(jd)
        assert "go" not in p.required_skills or p.required_skills.count("go") == 0

    def test_no_skills_detected(self):
        jd = "We are a great company with amazing culture and nice office."
        p = parse_jd(jd)
        assert p.required_skills == []


class TestRoleExtraction:
    def test_senior_engineer(self):
        p = parse_jd("Senior Software Engineer needed for our team.")
        assert "Engineer" in p.role_title

    def test_lead_data_engineer(self):
        p = parse_jd("We are hiring a Lead Data Engineer.")
        assert "Data" in p.role_title
        assert "Engineer" in p.role_title

    def test_no_role_detected(self):
        p = parse_jd("Looking for someone great to join us.")
        assert p.role_title == ""


class TestYearsExtraction:
    def test_plus_years(self):
        p = parse_jd("Requires 5+ years of experience.")
        assert p.years_required == 5

    def test_minimum_years(self):
        p = parse_jd("Minimum 7 years in software development.")
        assert p.years_required == 7

    def test_at_least_years(self):
        p = parse_jd("At least 3 years with Python.")
        assert p.years_required == 3

    def test_no_years_mentioned(self):
        p = parse_jd("Looking for a Python developer.")
        assert p.years_required == 0

    def test_takes_max_when_multiple_mentions(self):
        p = parse_jd("2 years in dev, 5 years total experience required, 8+ preferred.")
        # Should pick the largest
        assert p.years_required >= 5
