"""Tests for PII redaction layer.

Covers: app.redactor.redact() and app.redactor.unmask() — see C1 backlog.

TDD contract:
- redact() strips PII from text and returns a mapping to restore it later
- unmask() restores the original PII from the mapping
- All supported PII categories (email, phone, linkedin, address, dob) are caught
- Non-PII tokens (version numbers, year-only dates) are NOT flagged
"""
from __future__ import annotations

import pytest

from app.redactor import redact, unmask, PII_PATTERNS


# --------------------------------------------------------------------------- #
# Email
# --------------------------------------------------------------------------- #

class TestEmail:
    def test_simple_email_redacted(self):
        text = "Contact me at tino.santoso@gmail.com for details."
        redacted, mapping = redact(text)
        assert "tino.santoso@gmail.com" not in redacted
        assert "[EMAIL_1]" in redacted
        assert mapping["[EMAIL_1]"] == "tino.santoso@gmail.com"

    def test_multiple_emails_get_sequential_ids(self):
        text = "Reach me at a@x.com or b@y.com"
        redacted, mapping = redact(text)
        assert "[EMAIL_1]" in redacted
        assert "[EMAIL_2]" in redacted
        assert mapping["[EMAIL_1]"] == "a@x.com"
        assert mapping["[EMAIL_2]"] == "b@y.com"

    def test_email_round_trip(self):
        text = "Email: tino@gmail.com"
        redacted, mapping = redact(text)
        assert unmask(redacted, mapping) == text


# --------------------------------------------------------------------------- #
# Phone (Indonesia format)
# --------------------------------------------------------------------------- #

class TestPhone:
    def test_indonesian_mobile_08_redacted(self):
        text = "HP: 0812-3456-7890"
        redacted, mapping = redact(text)
        assert "0812-3456-7890" not in redacted
        assert "[PHONE_1]" in redacted
        assert mapping["[PHONE_1]"] == "0812-3456-7890"

    def test_indonesian_mobile_with_plus62(self):
        text = "Call +62 812 3456 7890 anytime"
        redacted, mapping = redact(text)
        assert "+62 812 3456 7890" not in redacted
        assert "[PHONE_1]" in redacted

    def test_phone_without_separator(self):
        text = "Phone: 081234567890"
        redacted, mapping = redact(text)
        assert "[PHONE_1]" in redacted

    def test_python_version_not_flagged_as_phone(self):
        # "Python 3.9" must NOT match the phone regex (avoids false positive)
        text = "Skills: Python 3.9, AWS 5.0, Node 18"
        redacted, mapping = redact(text)
        assert "[PHONE_" not in redacted
        assert "Python 3.9" in redacted
        assert "AWS 5.0" in redacted


# --------------------------------------------------------------------------- #
# LinkedIn
# --------------------------------------------------------------------------- #

class TestLinkedIn:
    def test_linkedin_url_redacted(self):
        text = "Find me: linkedin.com/in/tino-santoso"
        redacted, mapping = redact(text)
        assert "linkedin.com/in/tino-santoso" not in redacted
        assert "[LINKEDIN_1]" in redacted
        assert mapping["[LINKEDIN_1]"] == "linkedin.com/in/tino-santoso"

    def test_linkedin_with_protocol_redacted(self):
        text = "Profile: https://www.linkedin.com/in/jdoe"
        redacted, mapping = redact(text)
        assert "[LINKEDIN_1]" in redacted


# --------------------------------------------------------------------------- #
# Address (street)
# --------------------------------------------------------------------------- #

class TestAddress:
    def test_jl_redacted(self):
        text = "Alamat: Jl. Sudirman No. 45, Jakarta"
        redacted, mapping = redact(text)
        assert "Sudirman" not in redacted
        assert "[ADDRESS_1]" in redacted

    def test_jalan_full_word_redacted(self):
        text = "Jalan Gatot Subroto Kav. 12"
        redacted, mapping = redact(text)
        assert "Gatot" not in redacted


# --------------------------------------------------------------------------- #
# Date of birth
# --------------------------------------------------------------------------- #

class TestDOB:
    def test_born_keyword_redacted(self):
        text = "Born 12 May 1990 in Jakarta"
        redacted, mapping = redact(text)
        assert "1990" not in redacted
        assert "[DOB_1]" in redacted

    def test_dob_label_redacted(self):
        text = "DOB: 01/01/1995"
        redacted, mapping = redact(text)
        assert "1995" not in redacted

    def test_lahir_indonesian_redacted(self):
        text = "Tgl lahir: 17 Agustus 1945"
        redacted, mapping = redact(text)
        assert "[DOB_1]" in redacted


# --------------------------------------------------------------------------- #
# Multi-PII in one document
# --------------------------------------------------------------------------- #

class TestCombined:
    def test_email_and_phone_in_same_text(self):
        text = "Email a@b.com or call 0812-3456-7890"
        redacted, mapping = redact(text)
        assert "a@b.com" not in redacted
        assert "0812-3456-7890" not in redacted
        assert "[EMAIL_1]" in redacted
        assert "[PHONE_1]" in redacted

    def test_full_cv_round_trip(self):
        text = (
            "Tino Santoso\n"
            "Email: tino@gmail.com\n"
            "Phone: 0812-3456-7890\n"
            "LinkedIn: linkedin.com/in/tino\n"
            "Born 12 May 1990\n"
            "Summary: Senior engineer with 10 years experience.\n"
        )
        redacted, mapping = redact(text)
        # All PII gone
        for sensitive in ["tino@gmail.com", "0812-3456-7890", "linkedin.com/in/tino", "1990"]:
            assert sensitive not in redacted
        # Non-PII preserved
        assert "Senior engineer" in redacted
        assert "Summary" in redacted
        # Round-trip restores everything
        assert unmask(redacted, mapping) == text


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #

class TestEdgeCases:
    def test_empty_text_returns_empty_mapping(self):
        redacted, mapping = redact("")
        assert redacted == ""
        assert mapping == {}

    def test_text_without_pii_unchanged(self):
        text = "Just a normal sentence with no sensitive data."
        redacted, mapping = redact(text)
        assert redacted == text
        assert mapping == {}

    def test_idempotent_redaction(self):
        # Running redact() twice should not produce [EMAIL_2] etc.
        text = "Email: a@b.com"
        once, _ = redact(text)
        twice, _ = redact(once)
        assert once == twice


# --------------------------------------------------------------------------- #
# Sanity: pattern registry
# --------------------------------------------------------------------------- #

class TestRegistry:
    def test_all_pattern_categories_present(self):
        expected = {"EMAIL", "PHONE", "LINKEDIN", "ADDRESS", "DOB"}
        assert expected <= set(PII_PATTERNS.keys())