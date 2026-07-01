"""Tests for app/matcher.py: CV ↔ JD keyword/skill/role/years matching."""
from __future__ import annotations

import pytest

from app.jd_parser import parse_jd
from app.matcher import JDMatchReport, match_cv_to_jd


def _fake_cv(
    summary: str = "",
    experience: str = "",
    skills: str = "",
    education: str = "",
) -> dict[str, str]:
    return {
        "Header": "",
        "Summary": summary,
        "Experience": experience,
        "Skills": skills,
        "Education": education,
    }


class TestBasicMatching:
    def test_empty_jd_returns_empty_report(self):
        jd = parse_jd("")
        rep = match_cv_to_jd(_fake_cv(), jd)
        assert rep.overall_jd_score == 0.0
        assert rep.required_total == 0

    def test_full_match(self):
        jd = parse_jd("""
            Senior Python Developer

            Requirements:
            - 5+ years with Python
            - Experience with Django, PostgreSQL, AWS
            """)
        cv = _fake_cv(
            summary="Senior Python Developer with 6 years of experience.",
            experience=(
                "Built Django apps backed by PostgreSQL on AWS. "
                "Migrated legacy services to Python."
            ),
            skills="Python, Django, PostgreSQL, AWS, Docker",
        )
        rep = match_cv_to_jd(cv, jd)
        # All three required skills (python, django, postgresql, aws) must be in CV.
        assert rep.required_total > 0
        assert rep.required_matched == rep.required_total, (
            f"expected full match, got {rep.required_matched}/{rep.required_total} "
            f"(missing: {rep.required_missing_list})"
        )
        assert rep.required_match_ratio == 1.0
        # 70%(req) + 15%(nice=0) + 10%(role) + 5%(years met) = 7+0+1+0.5 = 8.5
        assert rep.overall_jd_score >= 8.0, f"expected >=8, got {rep.overall_jd_score}"

    def test_no_match(self):
        jd = parse_jd("""
            Senior Rust Engineer

            Requirements:
            - 5+ years with Rust
            - Experience with WebAssembly
            """)
        cv = _fake_cv(
            summary="Senior Python Developer.",
            experience="Built Django apps.",
            skills="Python, Django",
        )
        rep = match_cv_to_jd(cv, jd)
        assert rep.required_match_ratio == 0.0
        # Most of the score comes from required (70%) — overall should be low.
        assert rep.overall_jd_score < 4.0

    def test_partial_match(self):
        jd = parse_jd("""
            Backend Engineer

            Requirements:
            - Python
            - Go
            - Kubernetes
            - PostgreSQL
            """)
        cv = _fake_cv(
            skills="Python, Kubernetes, PostgreSQL",  # missing Go
        )
        rep = match_cv_to_jd(cv, jd)
        assert rep.required_matched == 3
        assert rep.required_missing_list == ["go"]
        assert rep.required_match_ratio == 0.75


class TestRoleMatching:
    def test_matching_role_title(self):
        jd = parse_jd("Senior Software Engineer\nRequirements:\n- Python")
        cv = _fake_cv(summary="Senior Software Engineer with 5 years of experience.")
        rep = match_cv_to_jd(cv, jd)
        assert rep.role_match is True

    def test_different_role(self):
        jd = parse_jd("Senior Data Scientist\nRequirements:\n- Python")
        cv = _fake_cv(summary="Senior Software Engineer with 5 years of experience.")
        rep = match_cv_to_jd(cv, jd)
        assert rep.role_match is False

    def test_partial_role_match_seniority_stripped(self):
        # "Senior" / "Lead" etc. are stripped, so "Senior Python Developer" JD
        # should match CV with "Python Developer" (no seniority).
        jd = parse_jd("Senior Python Developer\nRequirements:\n- Python")
        cv = _fake_cv(summary="Python Developer with 3 years of experience.")
        rep = match_cv_to_jd(cv, jd)
        assert rep.role_match is True


class TestYearsGap:
    def test_years_gap_surfaced(self):
        jd = parse_jd("""
            Senior Engineer

            Requirements:
            - 8+ years of experience
            - Python
            """)
        cv = _fake_cv(
            summary="Engineer with 3 years of experience.",
            skills="Python",
        )
        rep = match_cv_to_jd(cv, jd)
        assert rep.years_gap == 5
        assert rep.years_required == 8

    def test_years_met(self):
        jd = parse_jd("""
            Senior Engineer

            Requirements:
            - 5+ years of experience
            - Python
            """)
        cv = _fake_cv(
            summary="Engineer with 8 years of experience.",
            skills="Python",
        )
        rep = match_cv_to_jd(cv, jd)
        assert rep.years_gap == 0

    def test_no_years_requirement(self):
        jd = parse_jd("Engineer\nRequirements:\n- Python")
        cv = _fake_cv(skills="Python")
        rep = match_cv_to_jd(cv, jd)
        assert rep.years_gap == 0


class TestSectionDistribution:
    def test_matched_skill_located_in_correct_section(self):
        jd = parse_jd("Engineer\nRequirements:\n- Python\n- AWS")
        cv = _fake_cv(
            experience="Built services with Python.",
            skills="AWS, Docker",
        )
        rep = match_cv_to_jd(cv, jd)
        assert "python" in rep.section_distribution
        sections_for_python = [loc.section for loc in rep.section_distribution["python"]]
        assert "Experience" in sections_for_python

        sections_for_aws = [loc.section for loc in rep.section_distribution["aws"]]
        assert "Skills" in sections_for_aws


class TestOverallScore:
    def test_perfect_score(self):
        jd = parse_jd("""
            Senior Python Engineer

            Requirements:
            - 5+ years of experience
            - Python
            - AWS
            """)
        cv = _fake_cv(
            summary="Senior Python Engineer with 7 years of experience.",
            skills="Python, AWS",
        )
        rep = match_cv_to_jd(cv, jd)
        # Full required match (2/2) + role match + years met = 7 + 0 + 1 + 0.5 = 8.5
        assert rep.overall_jd_score >= 8.0, f"expected >=8, got {rep.overall_jd_score}"

    def test_zero_score_when_no_skills(self):
        jd = parse_jd("Senior Engineer\nRequirements:\n- Rust")
        cv = _fake_cv(summary="Engineer", skills="")
        rep = match_cv_to_jd(cv, jd)
        # No required match (0% of 70%) + no role match (5) + no years req
        # = 0*0.7 + 0*0.15 + 5*0.10 + 10*0.05 = 1.0
        assert rep.overall_jd_score < 2.0
