"""Generate synthetic sample CVs for testing. No real people."""
from __future__ import annotations

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

OUT = Path(__file__).resolve().parent.parent / "data"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _doc(name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=name,
    )
    return doc, path


def _h(text, style):
    return Paragraph(text, style)


# --------------------------------------------------------------------------- #
# Sample 1 — STRONG CV (high score)
# --------------------------------------------------------------------------- #
def make_strong_cv() -> Path:
    doc, path = _doc("sample_strong.pdf")
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4, textColor="#003366")
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10, leading=13, spaceAfter=3)

    story = [
        _h("Alex Morgan", h1),
        _h("alex.morgan@gmail.com · +1-415-555-0123 · linkedin.com/in/alexmorgan · github.com/alexmorgan", body),
        Spacer(1, 6),

        _h("Professional Summary", h2),
        _h(
            "Senior Software Engineer with 8+ years of experience designing and shipping distributed systems at scale. "
            "Specialized in Python, Go, and Kubernetes, with a track record of leading teams of 5–10 to deliver measurable "
            "infrastructure and platform improvements.", body
        ),
        Spacer(1, 4),

        _h("Experience", h2),
        _h("<b>Staff Software Engineer</b> — Acme Cloud (2021 – Present)", body),
        ListFlowable(
            [
                ListItem(Paragraph("Architected a multi-region Kubernetes platform serving 12M requests/sec, reducing p99 latency by 38%.", body)),
                ListItem(Paragraph("Led a team of 7 engineers to migrate 40 legacy services to gRPC, cutting inter-service latency by 60%.", body)),
                ListItem(Paragraph("Designed and shipped a cost-attribution system that reduced AWS spend by $1.4M annually (22% reduction).", body)),
                ListItem(Paragraph("Mentored 4 junior engineers; 3 were promoted within 18 months.", body)),
            ],
            bulletType="bullet",
        ),
        _h("<b>Senior Software Engineer</b> — Globex (2018 – 2021)", body),
        ListFlowable(
            [
                ListItem(Paragraph("Built a real-time event pipeline (Kafka + Flink) processing 8B events/day with 99.97% uptime.", body)),
                ListItem(Paragraph("Reduced deployment time from 45 minutes to 6 minutes by automating CI/CD with Argo Workflows.", body)),
                ListItem(Paragraph("Owned the on-call rotation; cut P1 incidents by 40% over two years via runbooks and SLOs.", body)),
            ],
            bulletType="bullet",
        ),
        _h("<b>Software Engineer</b> — Initech (2016 – 2018)", body),
        ListFlowable(
            [
                ListItem(Paragraph("Shipped a REST API in Go powering 2M MAU; maintained 99.95% availability over 24 months.", body)),
                ListItem(Paragraph("Implemented OAuth 2.0 + JWT authentication across 6 internal services.", body)),
            ],
            bulletType="bullet",
        ),
        Spacer(1, 4),

        _h("Skills", h2),
        _h(
            "<b>Languages:</b> Python, Go, TypeScript, SQL<br/>"
            "<b>Frameworks:</b> FastAPI, gRPC, React, Flask<br/>"
            "<b>Cloud:</b> AWS (EKS, Lambda, S3, RDS), GCP (GKE, Pub/Sub)<br/>"
            "<b>Data:</b> PostgreSQL, Kafka, Flink, Redis, BigQuery<br/>"
            "<b>Tools:</b> Kubernetes, Terraform, ArgoCD, Datadog, Prometheus",
            body,
        ),
        Spacer(1, 4),

        _h("Education", h2),
        _h("B.S. in Computer Science — UC Berkeley, 2016", body),
        Spacer(1, 4),

        _h("Certifications", h2),
        _h("AWS Solutions Architect Professional · Certified Kubernetes Administrator (CKA)", body),
    ]
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# Sample 2 — WEAK CV (low score)
# --------------------------------------------------------------------------- #
def make_weak_cv() -> Path:
    doc, path = _doc("sample_weak.pdf")
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4, textColor="#660000")
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10, leading=13, spaceAfter=3)

    story = [
        _h("John Doe", h1),
        _h("johndoe99@hotmail.com", body),
        Spacer(1, 6),

        _h("Work Experience", h2),
        _h("<b>Developer</b> at Some Company (2019 - 2023)", body),
        ListFlowable(
            [
                ListItem(Paragraph("Responsible for writing code.", body)),
                ListItem(Paragraph("Worked on the website.", body)),
                ListItem(Paragraph("Helped the team with various tasks.", body)),
                ListItem(Paragraph("Participated in meetings and was involved in project work.", body)),
                ListItem(Paragraph("Duties included bug fixing and testing.", body)),
            ],
            bulletType="bullet",
        ),
        _h("<b>Intern</b> at Another Company (Summer 2018)", body),
        ListFlowable(
            [
                ListItem(Paragraph("Assisted senior developers.", body)),
                ListItem(Paragraph("Was tasked with research.", body)),
            ],
            bulletType="bullet",
        ),
        Spacer(1, 4),

        _h("Skills", h2),
        _h("Hard worker, team player, problem solving, fast learner, passionate about technology, good communication skills, MS Office, etc.", body),
        Spacer(1, 4),

        _h("Education", h2),
        _h("University, studied computer stuff", body),
    ]
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# Sample 3 — MEDIUM CV (mixed)
# --------------------------------------------------------------------------- #
def make_medium_cv() -> Path:
    doc, path = _doc("sample_medium.pdf")
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11, spaceBefore=10, spaceAfter=4, textColor="#444")
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10, leading=13, spaceAfter=3)

    story = [
        _h("Sarah Lee", h1),
        _h("sarah.lee@protonmail.com · +62-812-3456-7890", body),
        Spacer(1, 6),

        _h("Summary", h2),
        _h("Data analyst with 4 years of experience in SQL and Python.", body),
        Spacer(1, 4),

        _h("Experience", h2),
        _h("<b>Data Analyst</b> — BrightCo (2021 – Present)", body),
        ListFlowable(
            [
                ListItem(Paragraph("Built dashboards in Tableau for the marketing team used by 30 stakeholders.", body)),
                ListItem(Paragraph("Wrote SQL queries on PostgreSQL to analyze customer churn.", body)),
                ListItem(Paragraph("Created reports that helped the team understand monthly revenue trends.", body)),
                ListItem(Paragraph("Presented findings to the leadership team in weekly meetings.", body)),
            ],
            bulletType="bullet",
        ),
        _h("<b>Junior Analyst</b> — DataWise (2020 – 2021)", body),
        ListFlowable(
            [
                ListItem(Paragraph("Cleaned and processed customer survey data in Excel.", body)),
                ListItem(Paragraph("Helped build internal tools for the analytics team.", body)),
            ],
            bulletType="bullet",
        ),
        Spacer(1, 4),

        _h("Skills", h2),
        _h("SQL, Python, Excel, Tableau, PostgreSQL, communication, analytical thinking", body),
        Spacer(1, 4),

        _h("Education", h2),
        _h("B.S. in Statistics — University of Indonesia, 2020", body),
    ]
    doc.build(story)
    return path


if __name__ == "__main__":
    s = make_strong_cv()
    w = make_weak_cv()
    m = make_medium_cv()
    print(f"Created: {s}")
    print(f"Created: {w}")
    print(f"Created: {m}")