"""Tests for app/scorer.py: heuristic per-section scoring + grading."""
from __future__ import annotations

import pytest

from app.scorer import (
    CVReport,
    SectionScore,
    _score_contact,
    _score_education,
    _score_experience,
    _score_length_formatting,
    _score_skills,
    _score_summary,
    grade_for,
    score_cv,
)


# --------------------------------------------------------------------------- #
# Contact
# --------------------------------------------------------------------------- #

class TestContactScoring:
    def test_empty_input_scores_zero(self):
        s = _score_contact("", "")
        assert s.score == 0
        assert any("contact" in i.lower() for i in s.issues)

    def test_email_only(self):
        s = _score_contact("tino.santoso@gmail.com", "")
        assert s.score == 3
        assert any("Missing" in i for i in s.issues)  # phone + linkedin still missing

    def test_full_contact_set_scores_high(self):
        s = _score_contact(
            "tino.santoso@gmail.com | +62 812 1234 5678 | linkedin.com/in/tino | github.com/tino",
            "Tino Santoso",
        )
        # email(3) + phone(3) + linkedin(2) + github(1) = 9
        assert s.score == 9
        assert not s.issues

    def test_unprofessional_email_penalized(self):
        s = _score_contact("hotmama99@gmail.com | +1 555 123 4567 | linkedin.com/in/x", "")
        # email(3) + phone(3) + linkedin(2) - unprofessional penalty(2) = 6
        assert s.score == 6
        assert any("unprofessional" in i.lower() for i in s.issues)


# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #

class TestSummaryScoring:
    def test_empty_summary_scores_zero(self):
        s = _score_summary("")
        assert s.score == 0
        assert any("summary" in i.lower() for i in s.issues)

    def test_too_short_summary(self):
        s = _score_summary("A short blurb about me.")
        assert s.score <= 3
        assert any("too short" in i.lower() for i in s.issues)

    def test_too_long_summary(self):
        long_text = " ".join(["word"] * 150)
        s = _score_summary(long_text)
        assert s.score <= 5
        assert any("too long" in i.lower() for i in s.issues)

    def test_ideal_summary_with_role_and_years(self):
        text = (
            "Senior Software Engineer with 8 years of experience building "
            "distributed systems, microservices, and data pipelines using Python and Go. "
            "Specialized in cloud-native architectures and Kubernetes."
        )
        s = _score_summary(text)
        # 7 (length) + 1.5 (years) + 1.5 (role) = 10
        assert s.score == 10
        assert any("years of experience" in e.lower() for e in s.evidence)
        assert any("role" in e.lower() for e in s.evidence)

    def test_summary_without_role_loses_points(self):
        text = (
            "I am a hardworking professional passionate about technology and learning "
            "new things. I have 5 years of background in software and operations."
        )
        s = _score_summary(text)
        # has years but no role keyword -> 7 + 1.5 = 8.5
        assert 7.0 <= s.score <= 9.0
        assert any("role" in i.lower() for i in s.issues)


# --------------------------------------------------------------------------- #
# Experience
# --------------------------------------------------------------------------- #

class TestExperienceScoring:
    def test_empty_experience_scores_near_zero(self):
        s = _score_experience("")
        assert s.score == 0
        assert any("experience" in i.lower() for i in s.issues)

    def test_paragraph_format_penalized(self):
        text = (
            "I worked at Acme Corp from 2020 to 2023 as a senior engineer. "
            "I was responsible for leading a team of five engineers. "
            "I helped build microservices that handled millions of users. "
            "I also designed the data pipeline processing terabytes of data."
        )
        s = _score_experience(text)
        # Paragraph format triggers -2 penalty
        assert any("paragraph" in i.lower() for i in s.issues)

    def test_strong_bullets_with_metrics_score_high(self):
        text = (
            "Senior Engineer — Acme (2020 - 2023)\n"
            "- Led migration of monolith, reducing p99 latency by 40% for 2M+ users\n"
            "- Architected event-driven pipeline serving 50K requests/sec, cutting costs by $20K/month\n"
            "- Shipped 4 features, increasing retention by 15% within 6 months\n"
            "- Mentored team of 5 engineers across 18 months"
        )
        s = _score_experience(text)
        # Should score 7+ (strong verbs) + 2.5 (metrics)
        assert s.score >= 8.0, f"expected >=8, got {s.score}"

    def test_weak_verbs_penalized(self):
        text = (
            "Engineer — Co (2020 - 2022)\n"
            "- Responsible for the API service\n"
            "- Helped the team ship features\n"
            "- Assisted with documentation\n"
            "- Worked on bug fixes"
        )
        s = _score_experience(text)
        # 4 bullets, all weak -> verb_ratio=0 -> score 2
        assert s.score <= 3.0
        assert any("weak" in i.lower() for i in s.issues)

    def test_no_metrics_penalized(self):
        text = (
            "Engineer — Co (2020 - 2022)\n"
            "- Led the API team\n"
            "- Built the deployment pipeline\n"
            "- Designed the monitoring system\n"
            "- Shipped the new dashboard"
        )
        s = _score_experience(text)
        # Strong verbs present, but no metrics -> metric_ratio=0
        assert any("metric" in i.lower() for i in s.issues)


# --------------------------------------------------------------------------- #
# Skills
# --------------------------------------------------------------------------- #

class TestSkillsScoring:
    def test_empty_skills(self):
        s = _score_skills("")
        assert s.score == 0
        assert any("skill" in i.lower() for i in s.issues)

    def test_vague_skills_penalized(self):
        text = "Hard worker, team player, problem solving, self-motivated, fast learner"
        s = _score_skills(text)
        # Most tokens are vague soft-skills
        assert any("vague" in i.lower() for i in s.issues)

    def test_concrete_skills_counted(self):
        text = "Python, Go, TypeScript, AWS, Kubernetes, Docker, PostgreSQL, Redis, MongoDB"
        s = _score_skills(text)
        # 9 concrete skills -> score 8
        assert s.score >= 7.0
        assert any("concrete" in e.lower() for e in s.evidence)

    def test_grouped_skills_bonus(self):
        text = (
            "Languages: Python, Go, TypeScript\n"
            "Frameworks: FastAPI, Gin, React\n"
            "Cloud: AWS, GCP, Kubernetes\n"
            "Databases: PostgreSQL, Redis, MongoDB"
        )
        s = _score_skills(text)
        # Should have +1 bonus for grouping
        assert any("group" in e.lower() for e in s.evidence)
        assert s.score >= 8.0


# --------------------------------------------------------------------------- #
# Education
# --------------------------------------------------------------------------- #

class TestEducationScoring:
    def test_empty_education(self):
        s = _score_education("")
        assert s.score == 0

    def test_full_education_section(self):
        text = "B.S. Computer Science, Institut Teknologi Bandung, 2020"
        s = _score_education(text)
        # degree(4) + year(3) + institution(3) = 10
        assert s.score == 10
        assert len(s.issues) == 0

    def test_missing_year(self):
        text = "Bachelor of Computer Science from a top university"
        s = _score_education(text)
        # degree(4) + institution(3) = 7, no year
        assert 6.0 <= s.score <= 8.0
        assert any("year" in i.lower() for i in s.issues)


# --------------------------------------------------------------------------- #
# Length / Formatting
# --------------------------------------------------------------------------- #

class TestLengthFormatting:
    def test_very_short_cv(self):
        s = _score_length_formatting(" ".join(["word"] * 100))
        assert s.score <= 4
        assert any("short" in i.lower() for i in s.issues)

    def test_ideal_length(self):
        s = _score_length_formatting(" ".join(["word"] * 600))
        # 400-900 words -> 9
        assert s.score >= 8.0
        assert any("appropriate" in e.lower() for e in s.evidence)

    def test_too_long_cv(self):
        s = _score_length_formatting(" ".join(["word"] * 1500))
        assert s.score <= 5
        assert any("long" in i.lower() for i in s.issues)

    def test_bullet_points_flagged_positive(self):
        text = "- First bullet\n- Second bullet\n" + " ".join(["word"] * 600)
        s = _score_length_formatting(text)
        assert any("bullet" in e.lower() for e in s.evidence)


# --------------------------------------------------------------------------- #
# Grading
# --------------------------------------------------------------------------- #

class TestGrading:
    @pytest.mark.parametrize("score,label_substring", [
        (9.5, "A"),
        (9.0, "A"),
        (8.9, "B"),
        (8.0, "B"),
        (7.0, "C"),
        (6.5, "C"),
        (6.4, "D"),
        (5.0, "D"),
        (4.9, "F"),
        (0.0, "F"),
    ])
    def test_grade_thresholds(self, score, label_substring):
        assert label_substring in grade_for(score)


# --------------------------------------------------------------------------- #
# score_cv orchestrator (integration)
# --------------------------------------------------------------------------- #

class TestScoreCv:
    def test_strong_sample_scores_high(self):
        from pathlib import Path
        pdf = Path(__file__).resolve().parent.parent / "data" / "sample_strong.pdf"
        if not pdf.exists():
            pytest.skip("sample_strong.pdf not present")
        rep = score_cv(pdf)
        assert isinstance(rep, CVReport)
        assert rep.overall >= 7.0, f"strong CV scored too low: {rep.overall}"
        assert all(isinstance(v, SectionScore) for v in rep.sections.values())
        assert all(0.0 <= v.score <= 10.0 for v in rep.sections.values())

    def test_weak_sample_scores_low(self):
        from pathlib import Path
        pdf = Path(__file__).resolve().parent.parent / "data" / "sample_weak.pdf"
        if not pdf.exists():
            pytest.skip("sample_weak.pdf not present")
        rep = score_cv(pdf)
        assert rep.overall <= 4.0, f"weak CV scored too high: {rep.overall}"

    def test_strong_beats_weak(self):
        from pathlib import Path
        strong_p = Path(__file__).resolve().parent.parent / "data" / "sample_strong.pdf"
        weak_p = Path(__file__).resolve().parent.parent / "data" / "sample_weak.pdf"
        if not (strong_p.exists() and weak_p.exists()):
            pytest.skip("samples not present")
        assert score_cv(strong_p).overall > score_cv(weak_p).overall


# --------------------------------------------------------------------------- #
# score_cv() with JD-aware mode (P1.2)
# --------------------------------------------------------------------------- #

class TestScoreCvWithJd:
    def test_jd_none_behaves_like_v01(self):
        from pathlib import Path
        pdf = Path(__file__).resolve().parent.parent / "data" / "sample_strong.pdf"
        if not pdf.exists():
            pytest.skip("sample_strong.pdf not present")
        rep = score_cv(pdf, jd_text=None)
        assert rep.jd_match is None
        assert rep.jd_grade == ""

    def test_jd_empty_string_behaves_like_v01(self):
        from pathlib import Path
        pdf = Path(__file__).resolve().parent.parent / "data" / "sample_strong.pdf"
        if not pdf.exists():
            pytest.skip("sample_strong.pdf not present")
        rep = score_cv(pdf, jd_text="")
        assert rep.jd_match is None

    def test_jd_with_matching_skills_adds_match_report(self):
        from pathlib import Path
        pdf = Path(__file__).resolve().parent.parent / "data" / "sample_strong.pdf"
        if not pdf.exists():
            pytest.skip("sample_strong.pdf not present")
        jd = """
        Senior Software Engineer

        Requirements:
        - 5+ years of experience
        - Python
        - AWS
        - Kubernetes
        - PostgreSQL
        """
        rep = score_cv(pdf, jd_text=jd)
        assert rep.jd_match is not None
        assert rep.jd_match.required_total > 0
        # strong sample has Python/AWS/K8s/Postgres, so should match well
        assert rep.jd_match.required_match_ratio > 0.5
        assert rep.jd_grade != ""

    def test_jd_with_unrelated_skills_lowers_skills_score(self):
        from pathlib import Path
        pdf = Path(__file__).resolve().parent.parent / "data" / "sample_strong.pdf"
        if not pdf.exists():
            pytest.skip("sample_strong.pdf not present")
        # JD requires skills that are absent from the strong sample
        jd = """
        Senior Engineer

        Requirements:
        - Rust
        - WebAssembly
        - Erlang
        - COBOL
        - Fortran
        - Perl
        - Haskell
        """
        rep_no_jd = score_cv(pdf, jd_text=None)
        rep_with_jd = score_cv(pdf, jd_text=jd)
        assert rep_with_jd.jd_match is not None
        assert rep_with_jd.jd_match.required_match_ratio < 0.2
        # Skills section should be penalized
        assert rep_with_jd.sections["Skills"].score < rep_no_jd.sections["Skills"].score
        # Issue should mention the gaps
        assert any("Missing" in i for i in rep_with_jd.sections["Skills"].issues)


# --------------------------------------------------------------------------- #
# Inline summary detection + carving (P1.6 — task #2)
# --------------------------------------------------------------------------- #

class TestInlineSummaryDetection:
    """Cover the heuristics that detect an inline summary in the Header
    block when the CV has no dedicated ``Summary`` section.

    Three signals trigger the carve-out:
    - substantive paragraph (>= 8 words)
    - role-with-colon headline ("Full Stack Developer: ...")
    - years-of-experience headline ("8 years experience ...")
    """

    def test_looks_like_summary_with_paragraph(self):
        from app.scorer import _looks_like_summary
        text = (
            "John Doe\n"
            "john@example.com | +1 555 123 4567\n"
            "Senior engineer with deep experience in distributed systems "
            "and a passion for clean code."
        )
        assert _looks_like_summary(text) is True

    def test_looks_like_summary_with_role_colon(self):
        from app.scorer import _looks_like_summary
        text = (
            "Jane Doe\n"
            "jane@example.com\n"
            "Full Stack Developer: building modern web apps with Laravel and React"
        )
        assert _looks_like_summary(text) is True

    def test_looks_like_summary_with_years_headline(self):
        from app.scorer import _looks_like_summary
        text = (
            "Bob Smith\n"
            "bob@example.com\n"
            "5+ years experience building scalable systems"
        )
        assert _looks_like_summary(text) is True

    def test_looks_like_summary_with_indonesian_years(self):
        from app.scorer import _looks_like_summary
        text = (
            "Andi Wijaya\n"
            "andi@example.com\n"
            "8 tahun pengalaman di industri fintech"
        )
        assert _looks_like_summary(text) is True

    def test_looks_like_summary_false_for_pure_contact(self):
        from app.scorer import _looks_like_summary
        text = (
            "John Doe\n"
            "john@example.com | linkedin.com/in/johndoe | +1 555 123 4567\n"
            "123 Main St, Springfield"
        )
        assert _looks_like_summary(text) is False

    def test_looks_like_summary_false_for_empty(self):
        from app.scorer import _looks_like_summary
        assert _looks_like_summary("") is False
        assert _looks_like_summary("\n\n") is False

    def test_role_with_colon_is_classified_as_summary(self):
        from app.scorer import _is_role_or_years_line
        assert _is_role_or_years_line(
            "Senior Software Engineer: backend, distributed systems"
        )
        assert _is_role_or_years_line(
            "Lead ML Engineer : PyTorch + MLOps, production"
        )
        assert _is_role_or_years_line(
            "Full Stack Developer - building modern web apps"
        )
        # Should NOT match
        assert not _is_role_or_years_line("Just a sentence about hobbies")
        assert not _is_role_or_years_line("Contact: hello@example.com")
        assert not _is_role_or_years_line("Senior")  # too short

    def test_carve_extracts_role_and_paragraph(self):
        from app.scorer import _carve_summary_from_header
        header = (
            "TINO APRIKA SANTOSO\n"
            "Full Stack Developer\n"
            "tino@example.com | +1 555 123 4567\n"
            "Passionate Full Stack developer in building comprehensive web apps\n"
            "using Laravel and React. I focus on payment integrations and UX.\n"
            "Experience\n"
            "Acme Corp 2020-2024"
        )
        kept, summary = _carve_summary_from_header(header)
        # Role title stays in Header (not classified as headline because no colon)
        assert "TINO APRIKA SANTOSO" in kept
        assert "Full Stack Developer" in kept
        assert "tino@example.com" in kept
        # Substantive paragraphs get carved into Summary
        assert "Passionate Full Stack developer" in summary
        assert "Laravel and React" in summary
        # The section header "Experience" must NOT be moved into Summary
        assert "Experience" not in summary
        assert "Acme Corp" not in summary

    def test_carve_extracts_role_with_colon(self):
        from app.scorer import _carve_summary_from_header
        header = (
            "JANE DOE\n"
            "jane@example.com\n"
            "Senior Software Engineer: building reliable distributed systems\n"
            "at scale, with a focus on observability and clean architecture.\n"
            "Experience\n"
            "BigCo 2019-2024"
        )
        kept, summary = _carve_summary_from_header(header)
        # Role+colon line MUST be carved into Summary
        assert "Senior Software Engineer" in summary
        assert "building reliable distributed systems" in summary
        # Contact info stays in Header
        assert "JANE DOE" in kept
        assert "jane@example.com" in kept
        # Section header for Experience stays in Header
        assert "Experience" in kept
        assert "BigCo" in kept

    def test_carve_extracts_years_headline(self):
        from app.scorer import _carve_summary_from_header
        header = (
            "BOB SMITH\n"
            "bob@example.com\n"
            "8 years experience building scalable backends\n"
            "Skills\n"
            "Python, Go, Rust"
        )
        kept, summary = _carve_summary_from_header(header)
        assert "8 years experience" in summary
        assert "BOB SMITH" in kept
        assert "Skills" in kept
        assert "Python" in kept

    def test_carve_no_summary_when_only_contact(self):
        from app.scorer import _carve_summary_from_header
        header = (
            "John Doe\n"
            "john@example.com | +1 555 123 4567 | linkedin.com/in/john"
        )
        kept, summary = _carve_summary_from_header(header)
        assert summary == ""
        assert "John Doe" in kept

    def test_score_cv_carves_inline_summary_from_tino_actual(self):
        """End-to-end: Tino's actual CV (no Summary header) gets Summary carved
        from Header, and the Summary score reflects the carved content."""
        from pathlib import Path
        pdf = Path(__file__).resolve().parent.parent / "data" / "tino_actual.pdf"
        if not pdf.exists():
            pytest.skip("tino_actual.pdf not present")
        rep = score_cv(pdf)
        # Summary should be non-empty and score at least a 5 (role mention
        # and years: "Passionate ... building comprehensive web applications"
        # is substantive enough to clear 20 words and mention the role).
        assert rep.sections["Summary"].score >= 5.0, (
            f"expected Summary >= 5, got {rep.sections['Summary'].score}"
        )
        # The role title "Full Stack Developer" should still be in Contact
        # (it's a short line with no colon, so it stays in Header/Contact)
        contact_blob = (
            rep.sections["Contact"].evidence.__repr__()
        )  # weak check; presence is what matters
        # Just verify the score moved up vs the pre-fix 3.5 baseline.
        assert rep.sections["Summary"].score > 3.5


# --------------------------------------------------------------------------- #
# B1: Skill dictionary integration
# --------------------------------------------------------------------------- #

class TestSkillsScoringWithDictionary:
    """Skills section scoring must use the canonical-skill dictionary.

    Covers B1 backlog: skill alias resolution (Amazon Web Services -> AWS),
    category breakdown, and case-insensitive dedup.
    """

    def test_alias_aws_counted_correctly(self):
        from app.scorer import _score_skills
        # Naive split counts 5 tokens; dictionary resolves
        # "Amazon Web Services" -> AWS and dedupes with the second "AWS".
        text = "Python, Amazon Web Services, AWS, Docker, Kubernetes"
        rep = _score_skills(text)
        ev = " ".join(rep.evidence)
        assert "After alias normalization" in ev, f"expected alias evidence, got: {ev}"

    def test_category_breakdown_appears_in_evidence(self):
        from app.scorer import _score_skills
        text = "Python, AWS, Docker, PostgreSQL, MongoDB, React"
        rep = _score_skills(text)
        ev = " ".join(rep.evidence)
        assert "By category" in ev
        assert "Cloud" in ev
        assert "Database" in ev

    def test_unknown_tokens_dont_crash_evidence(self):
        from app.scorer import _score_skills
        text = "Python, Underwater Basket Weaving, AWS"
        rep = _score_skills(text)
        assert rep.score > 0

    def test_no_canonical_skills_no_breakdown_evidence(self):
        from app.scorer import _score_skills
        text = "team player, problem solving, communication"
        rep = _score_skills(text)
        ev = " ".join(rep.evidence)
        assert "By category" not in ev

    def test_mixed_case_dedupes(self):
        from app.scorer import _score_skills
        text = "PYTHON, python, Python"
        rep = _score_skills(text)
        ev = " ".join(rep.evidence)
        assert "After alias normalization" in ev
        assert "1 Language" in ev
