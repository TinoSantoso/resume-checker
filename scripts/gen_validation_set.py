"""Generate the validation-set CVs and seed grades.json.

The validation set is intentionally separate from unit-test fixtures
(in data/) so that grading doesn't drift with refactors.

The human grades here are my (the agent's) best-effort manual estimates,
applying the same ATS-rubric thinking the scorer uses. They are NOT
recruiter ground truth — the whole point of the validation harness is to
surface where the heuristic diverges from a human reviewer's intuition.

To add a real human-graded CV:
1. Drop the file in data/validation/
2. Add a matching entry to data/validation/grades.json
3. Re-run scripts/validate_against_human.py

Re-generate the bundled CVs with:

    .venv/bin/python scripts/gen_validation_set.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    ListFlowable,
    ListItem,
)


OUT = Path(__file__).resolve().parent.parent / "data" / "validation"


def _doc(name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    doc = SimpleDocTemplate(
        str(path),
        pagesizes=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=name,
    )
    return doc, path


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontSize=18, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4, textColor="#003366"),
        "body": ParagraphStyle("body", parent=ss["BodyText"], fontSize=10, leading=13, spaceAfter=3),
    }


def _h(text, style):
    return Paragraph(text, style)


# --------------------------------------------------------------------------- #
# Validation sample 1: STRONG ML engineer — should auto-score 7.5-8.5
# --------------------------------------------------------------------------- #
def make_v_strong_ml() -> Path:
    doc, path = _doc("v_strong_ml.pdf")
    s = _styles()
    story = [
        _h("Priya Sharma", s["h1"]),
        _h("priya.sharma@gmail.com · +1-650-555-0199 · linkedin.com/in/priyasharma · github.com/priyasharma", s["body"]),
        Spacer(1, 6),

        _h("Professional Summary", s["h2"]),
        _h(
            "Machine Learning Engineer with 6+ years of experience building production ML systems. "
            "Specialized in NLP, recommendation systems, and MLOps at scale. Track record of shipping "
            "models that move business metrics (engagement +18%, infra cost -25%).",
            s["body"],
        ),
        Spacer(1, 4),

        _h("Experience", s["h2"]),
        _h("<b>Senior ML Engineer</b> — Meta (2021 – Present)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Designed ranking model serving 200M users; +12% engagement vs. baseline.", s["body"])),
                ListItem(Paragraph("Led migration of training infra to PyTorch + Ray, cutting iteration time from 6h to 28m.", s["body"])),
                ListItem(Paragraph("Built online feature store processing 50K QPS with p99 &lt; 30ms.", s["body"])),
                ListItem(Paragraph("Mentored 3 junior engineers; published 2 internal tech blogs on MLOps.", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>ML Engineer</b> — Spotify (2018 – 2021)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Shipped Discover Weekly personalization; +6% session time.", s["body"])),
                ListItem(Paragraph("Built A/B test framework adopted by 14 teams.", s["body"])),
            ],
            bulletType="bullet",
        ),
        Spacer(1, 4),

        _h("Skills", s["h2"]),
        _h(
            "<b>Languages:</b> Python, SQL, Scala<br/>"
            "<b>ML:</b> PyTorch, TensorFlow, Hugging Face, scikit-learn, XGBoost<br/>"
            "<b>Infra:</b> Kubernetes, Spark, Ray, Kafka, Airflow, MLflow<br/>"
            "<b>Cloud:</b> AWS (SageMaker, S3, EMR), GCP (Vertex AI)",
            s["body"],
        ),
        Spacer(1, 4),

        _h("Education", s["h2"]),
        _h("M.S. in Computer Science — Stanford University, 2018", s["body"]),
        _h("B.Tech in CS — IIT Bombay, 2016, GPA: 9.2/10", s["body"]),
        Spacer(1, 4),

        _h("Publications", s["h2"]),
        _h("Sharma et al., \"Efficient Retrieval-Augmented Generation at Scale\", ACL 2023.", s["body"]),
    ]
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# Validation sample 2: WEAK recent grad — should auto-score 2-3
# --------------------------------------------------------------------------- #
def make_v_weak_recent_grad() -> Path:
    doc, path = _doc("v_weak_recent_grad.pdf")
    s = _styles()
    story = [
        _h("Budi Santoso", s["h1"]),
        _h("budi.santoso@gmail.com", s["body"]),
        Spacer(1, 6),

        _h("Education", s["h2"]),
        _h("Universitas Indonesia, Computer Science, 2024", s["body"]),
        Spacer(1, 4),

        _h("Work Experience", s["h2"]),
        _h("<b>Junior Developer</b> at Startup ABC (2024 - now)", s["body"]),
        _h(
            "Responsible for helping the team build features. I worked on the backend and frontend. "
            "I was involved in code reviews and daily standups. Duties included fixing bugs when they "
            "came up and participating in sprint planning. I helped the senior devs with their tasks "
            "and was tasked with research for new tools.",
            s["body"],
        ),
        _h("<b>Intern</b> at Company XYZ (Summer 2023)", s["body"]),
        _h("Assisted the engineering team. Helped with testing.", s["body"]),
        Spacer(1, 4),

        _h("Skills", s["h2"]),
        _h("Hard worker, fast learner, team player, MS Office, passionate, problem solving, good communication, Git", s["body"]),
        Spacer(1, 4),

        _h("Languages", s["h2"]),
        _h("Indonesian (native), English (basic)", s["body"]),
    ]
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# Validation sample 3: MEDIUM backend dev with some metrics — 5-6
# --------------------------------------------------------------------------- #
def make_v_medium_backend() -> Path:
    doc, path = _doc("v_medium_backend.pdf")
    s = _styles()
    story = [
        _h("Rizky Pratama", s["h1"]),
        _h("rizky.pratama@outlook.com · +62-21-555-0123 · linkedin.com/in/rizkypratama", s["body"]),
        Spacer(1, 6),

        _h("Summary", s["h2"]),
        _h(
            "Backend developer with 3 years of experience building APIs and microservices. "
            "Comfortable with Python and Go, deployed on AWS.",
            s["body"],
        ),
        Spacer(1, 4),

        _h("Experience", s["h2"]),
        _h("<b>Backend Developer</b> — Tokopedia (2022 – Present)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Built Go microservices for the order service, handling 5K QPS at peak.", s["body"])),
                ListItem(Paragraph("Optimized PostgreSQL queries; reduced API p95 from 420ms to 180ms.", s["body"])),
                ListItem(Paragraph("Wrote unit and integration tests; coverage went from 45% to 78%.", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>Junior Developer</b> — Bukalapak (2021 – 2022)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Implemented REST endpoints in Python/Flask for the merchant dashboard.", s["body"])),
                ListItem(Paragraph("Helped migrate the staging environment to Docker.", s["body"])),
            ],
            bulletType="bullet",
        ),
        Spacer(1, 4),

        _h("Skills", s["h2"]),
        _h("Python, Go, Flask, Django, PostgreSQL, Redis, Docker, AWS (EC2, RDS, S3), Git, Linux", s["body"]),
        Spacer(1, 4),

        _h("Education", s["h2"]),
        _h("B.Sc. in Computer Science — Institut Teknologi Bandung, 2021", s["body"]),
    ]
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# Validation sample 4: GOOD PM — different role, should still score well
# --------------------------------------------------------------------------- #
def make_v_good_pm() -> Path:
    doc, path = _doc("v_good_pm.pdf")
    s = _styles()
    story = [
        _h("Anita Wijaya", s["h1"]),
        _h("anita.wijaya@gmail.com · +62-811-9999-8888 · linkedin.com/in/anitawijaya", s["body"]),
        Spacer(1, 6),

        _h("Professional Summary", s["h2"]),
        _h(
            "Product Manager with 7 years of experience leading B2B SaaS products from 0-to-1 and scale-up. "
            "Shipped 4 products to GA; combined user base 1.2M MAU. Strong on customer discovery, "
            "data-driven prioritization, and cross-functional leadership.",
            s["body"],
        ),
        Spacer(1, 4),

        _h("Experience", s["h2"]),
        _h("<b>Senior Product Manager</b> — Gojek (2020 – Present)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Led 0-to-1 launch of merchant lending product; reached $4M GMV in month 6.", s["body"])),
                ListItem(Paragraph("Ran 12 customer discovery cycles; insights shaped 3 product pivots.", s["body"])),
                ListItem(Paragraph("Owned roadmap for the driver-side app; +22% weekly active drivers.", s["body"])),
                ListItem(Paragraph("Coached 2 associate PMs; both promoted to PM within 18 months.", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>Product Manager</b> — Traveloka (2017 – 2020)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Led redesign of the search funnel; conversion +14%.", s["body"])),
                ListItem(Paragraph("Defined and instrumented 8 new product metrics; 3 cited in board updates.", s["body"])),
            ],
            bulletType="bullet",
        ),
        Spacer(1, 4),

        _h("Skills", s["h2"]),
        _h(
            "<b>Skills:</b> Product strategy, user research, A/B testing, SQL (intermediate), "
            "Figma, Mixpanel, Amplitude, JIRA, Confluence, OKR planning",
            s["body"],
        ),
        Spacer(1, 4),

        _h("Education", s["h2"]),
        _h("MBA — NUS Business School, 2017", s["body"]),
        _h("B.Eng. Industrial Engineering — Universitas Gadjah Mada, 2013", s["body"]),
    ]
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# Validation sample 5: MIXED — strong experience, weak everything else — 4-5
# --------------------------------------------------------------------------- #
def make_v_mixed_lean() -> Path:
    doc, path = _doc("v_mixed_lean.pdf")
    s = _styles()
    story = [
        _h("Carlos Mendoza", s["h1"]),
        _h("carlos.mendoza@yahoo.com · +57-1-555-0142", s["body"]),
        Spacer(1, 6),

        _h("Experience", s["h2"]),
        _h("<b>DevOps Engineer</b> — Rappi (2018 – Present)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Migrated 30 services from EC2 to EKS; cut compute cost 28%.", s["body"])),
                ListItem(Paragraph("Built Terraform modules adopted by 5 teams.", s["body"])),
                ListItem(Paragraph("On-call for the payments service; P1 incidents 3/year.", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>Systems Administrator</b> — Banco Agrario (2015 – 2018)", s["body"]),
        _h("Managed Linux servers and network equipment. Wrote bash scripts for daily backups.", s["body"]),
        Spacer(1, 4),

        _h("Skills", s["h2"]),
        _h("Terraform, Kubernetes, AWS, Docker, Bash, Linux, Jenkins, Prometheus, Grafana", s["body"]),
    ]
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# Human grades — my best-effort ATS-rubric estimates for each CV above.
# --------------------------------------------------------------------------- #
GRADES = {
    "v_strong_ml.pdf": {
        "human_overall": 8.5,
        "human_sections": {
            "Contact": 9.0,
            "Summary": 8.5,
            "Experience": 9.0,
            "Skills": 9.0,
            "Education": 9.5,
        },
        "notes": "Strong ML with metrics, 2 roles, 4 jobs total. MLOps keywords present.",
    },
    "v_weak_recent_grad.pdf": {
        "human_overall": 2.5,
        "human_sections": {
            "Contact": 4.0,
            "Summary": 0.0,
            "Experience": 2.5,
            "Skills": 1.0,
            "Education": 5.0,
        },
        "notes": "Weak verbs everywhere, no metrics, no summary, soft skills as 'Skills'.",
    },
    "v_medium_backend.pdf": {
        "human_overall": 5.5,
        "human_sections": {
            "Contact": 7.0,
            "Summary": 4.0,
            "Experience": 6.0,
            "Skills": 7.0,
            "Education": 6.0,
        },
        "notes": "Decent bullets with some metrics, but only 2 roles, summary is thin.",
    },
    "v_good_pm.pdf": {
        "human_overall": 8.0,
        "human_sections": {
            "Contact": 7.0,
            "Summary": 9.0,
            "Experience": 8.5,
            "Skills": 6.0,
            "Education": 8.5,
        },
        "notes": "Strong PM with metrics + 0-to-1 story. Skills section soft (no hard tools).",
    },
    "v_mixed_lean.pdf": {
        "human_overall": 4.5,
        "human_sections": {
            "Contact": 4.0,
            "Summary": 0.0,
            "Experience": 7.0,
            "Skills": 6.0,
            "Education": 0.0,
        },
        "notes": "Strong DevOps experience, but no summary, no education, contact is thin.",
    },
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in (
        make_v_strong_ml,
        make_v_weak_recent_grad,
        make_v_medium_backend,
        make_v_good_pm,
        make_v_mixed_lean,
    ):
        p = fn()
        print(f"wrote {p} ({p.stat().st_size} bytes)")

    grades_path = OUT / "grades.json"
    grades_path.write_text(json.dumps(GRADES, indent=2))
    print(f"wrote {grades_path} ({len(GRADES)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
