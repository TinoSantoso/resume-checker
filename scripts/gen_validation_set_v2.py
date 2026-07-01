"""Generate 15 additional validation-set CVs to reach n=20.

B2 goal: expand the validation set so that Pearson CI tightens and
blind-spot categories (PM, DevOps, ID-localized) get meaningful coverage.

The CVs are generated programmatically (no real candidates) — the human
grades in ``GRADES_V2`` reflect best-effort ATS-rubric estimates applied
consistently with v0.1's grading style.

Run with::

    .venv/bin/python scripts/gen_validation_set_v2.py
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
# PM (4) — was a known blind spot. Mix: senior PM, junior PM, PM with metrics,
# PM with soft skills only.
# --------------------------------------------------------------------------- #
def make_v_senior_pm_enterprise():
    """Senior PM at large enterprise — should score 8-9 (PM rubric strong)."""
    doc, path = _doc("v_senior_pm_enterprise.pdf")
    s = _styles()
    story = [
        _h("Diana Hartono", s["h1"]),
        _h("diana.hartono@gmail.com · +62-21-777-8888 · linkedin.com/in/dianahartono", s["body"]),
        Spacer(1, 6),
        _h("Summary", s["h2"]),
        _h(
            "Senior Product Manager with 10 years leading enterprise SaaS in fintech and "
            "logistics. Drove two products from $0 to $50M ARR; managed 12-person cross-functional "
            "teams. Strong on platform strategy and pricing.",
            s["body"],
        ),
        Spacer(1, 4),
        _h("Experience", s["h2"]),
        _h("<b>Principal PM</b> — Bank Mandiri (2019 – Present)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Owned the corporate banking platform; revenue $42M → $58M (+38%) in 24 months.", s["body"])),
                ListItem(Paragraph("Launched 6 net-new modules (FX hedging, trade finance); combined adoption 73% of target segment.", s["body"])),
                ListItem(Paragraph("Defined pricing model; gross margin improved 9 percentage points.", s["body"])),
                ListItem(Paragraph("Led quarterly OKR cycle across 4 squads; on-time delivery 89% (industry: 62%).", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>Senior PM</b> — Telkomsel (2015 – 2019)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Launched B2B IoT connectivity product; 220 enterprise customers in year 1.", s["body"])),
                ListItem(Paragraph("Cut onboarding time from 14 days to 2 days via self-serve portal.", s["body"])),
            ],
            bulletType="bullet",
        ),
        Spacer(1, 4),
        _h("Skills", s["h2"]),
        _h("Product strategy, pricing, OKRs, SQL (advanced), Mixpanel, Looker, Figma, JIRA, stakeholder management", s["body"]),
        Spacer(1, 4),
        _h("Education", s["h2"]),
        _h("M.Sc. Management — London Business School, 2014", s["body"]),
        _h("B.Sc. Industrial Engineering — ITB, 2010", s["body"]),
    ]
    doc.build(story)
    return path


def make_v_junior_pm():
    """Junior PM with 1.5 years experience — should score 4-5."""
    doc, path = _doc("v_junior_pm.pdf")
    s = _styles()
    story = [
        _h("Reza Pratama", s["h1"]),
        _h("reza.pratama.work@gmail.com · +62-812-1111-2222", s["body"]),
        Spacer(1, 6),
        _h("Summary", s["h2"]),
        _h("Associate Product Manager transitioning from business analysis. 1.5 years of PM experience in a consumer app.", s["body"]),
        Spacer(1, 4),
        _h("Experience", s["h2"]),
        _h("<b>Associate PM</b> — Halodoc (2023 – Present)", s["body"]),
        _h(
            "Supported the senior PM on the doctor-side dashboard. Wrote PRDs, ran user research sessions, "
            "and tracked engagement metrics in Mixpanel. Helped prioritize the roadmap backlog.",
            s["body"],
        ),
        _h("<b>Business Analyst</b> — Grab (2022 – 2023)", s["body"]),
        _h("Analyzed ride-hailing data; built weekly dashboards in Looker.", s["body"]),
        Spacer(1, 4),
        _h("Skills", s["h2"]),
        _h("Product, SQL, Mixpanel, Figma, PRDs, user research, wireframing, communication", s["body"]),
        Spacer(1, 4),
        _h("Education", s["h2"]),
        _h("B.Sc. Information Systems — Universitas Bina Nusantara, 2022", s["body"]),
    ]
    doc.build(story)
    return path


def make_v_pm_with_metrics():
    """Mid PM with strong metric-driven bullets — should score 7-8."""
    doc, path = _doc("v_pm_metrics_driven.pdf")
    s = _styles()
    story = [
        _h("Maya Kusuma", s["h1"]),
        _h("maya.kusuma@protonmail.com · +62-813-9999-0000 · linkedin.com/in/mayakusuma", s["body"]),
        Spacer(1, 6),
        _h("Professional Summary", s["h2"]),
        _h(
            "Product Manager with 4 years of experience at high-growth consumer startups. "
            "Obsessed with metric-driven iteration: every release ships with a measurable "
            "hypothesis. Track record of lifting conversion (+18%) and retention (+12 NPS).",
            s["body"],
        ),
        Spacer(1, 4),
        _h("Experience", s["h2"]),
        _h("<b>Product Manager</b> — Xendit (2021 – Present)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Led checkout funnel rewrite; conversion 2.3% → 2.7% (+18%) over 4 months.", s["body"])),
                ListItem(Paragraph("Defined activation event for SMB merchants; 30-day activation 41% → 58%.", s["body"])),
                ListItem(Paragraph("Ran 23 A/B tests in 2023; 11 shipped, average lift 9.4%.", s["body"])),
                ListItem(Paragraph("Built merchant health score model; flagged 12% of accounts for CSM outreach.", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>Associate PM</b> — Bukalapak (2020 – 2021)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Improved search relevance; CTR +11% on category pages.", s["body"])),
            ],
            bulletType="bullet",
        ),
        Spacer(1, 4),
        _h("Skills", s["h2"]),
        _h("Product management, A/B testing, SQL (advanced), Python (pandas), Mixpanel, Amplitude, Figma, JIRA, Notion", s["body"]),
        Spacer(1, 4),
        _h("Education", s["h2"]),
        _h("B.Sc. Computer Science — Universitas Indonesia, 2020", s["body"]),
    ]
    doc.build(story)
    return path


def make_v_pm_soft_skills_only():
    """PM with narrative CV but no hard numbers — should score 4-5 (low for PM)."""
    doc, path = _doc("v_pm_soft_skills.pdf")
    s = _styles()
    story = [
        _h("Sinta Lestari", s["h1"]),
        _h("sinta.lestari@gmail.com", s["body"]),
        Spacer(1, 6),
        _h("About Me", s["h2"]),
        _h(
            "I am a passionate product manager who loves working with cross-functional teams "
            "and solving complex problems. I bring strong communication skills, empathy, and a "
            "collaborative spirit to every project.",
            s["body"],
        ),
        Spacer(1, 4),
        _h("Work Experience", s["h2"]),
        _h("<b>Product Manager</b> — Logitech Indonesia (2020 – 2023)", s["body"]),
        _h(
            "Worked on various products. Collaborated with design, engineering, and marketing teams. "
            "Facilitated workshops and sprint planning. Helped the team align on priorities. "
            "Wrote product requirement documents and presented to stakeholders. Participated in "
            "customer interviews and synthesized insights. Contributed to the team's OKR process.",
            s["body"],
        ),
        _h("<b>Associate PM</b> — Samsung R&D (2018 – 2020)", s["body"]),
        _h("Helped the team with product work and analysis.", s["body"]),
        Spacer(1, 4),
        _h("Skills", s["h2"]),
        _h("Communication, leadership, teamwork, problem-solving, adaptability, time management, presentation", s["body"]),
        Spacer(1, 4),
        _h("Education", s["h2"]),
        _h("B.Sc. Business — Universitas Parahyangan, 2018", s["body"]),
    ]
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# DevOps / SRE (3) — Carlos was the only DevOps case. Expand.
# --------------------------------------------------------------------------- #
def make_v_senior_sre():
    """Senior SRE — should score 8-9 (deep metrics, hard skills, no fluff)."""
    doc, path = _doc("v_senior_sre.pdf")
    s = _styles()
    story = [
        _h("Hendra Wijaya", s["h1"]),
        _h("hendra.wijaya@gmail.com · +62-811-7777-3333 · github.com/hendrawijaya", s["body"]),
        Spacer(1, 6),
        _h("Summary", s["h2"]),
        _h(
            "Site Reliability Engineer with 8 years of experience operating large-scale distributed "
            "systems (peak 12K nodes, 4M QPS). Specialised in incident response, capacity planning, "
            "and observability. Led SRE team of 5 at Bukalapak.",
            s["body"],
        ),
        Spacer(1, 4),
        _h("Experience", s["h2"]),
        _h("<b>Senior SRE</b> — Bukalapak (2019 – Present)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Owned SLOs for the payments platform; achieved 99.97% availability over 12 months.", s["body"])),
                ListItem(Paragraph("Reduced MTTR from 47 min to 12 min via unified alerting and runbooks.", s["body"])),
                ListItem(Paragraph("Migrated 4 critical services from VMs to Kubernetes; cost down 32%.", s["body"])),
                ListItem(Paragraph("Built internal chaos engineering platform; adopted by 9 services.", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>SRE</b> — Gojek (2016 – 2019)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("On-call rotation for the matching service; handled 200+ P1 incidents.", s["body"])),
                ListItem(Paragraph("Built Prometheus dashboards adopted org-wide (200+ services).", s["body"])),
            ],
            bulletType="bullet",
        ),
        Spacer(1, 4),
        _h("Skills", s["h2"]),
        _h("Kubernetes, Terraform, Prometheus, Grafana, Go, Python, Linux, AWS (EKS, RDS, S3), GCP, Datadog, PagerDuty", s["body"]),
        Spacer(1, 4),
        _h("Education", s["h2"]),
        _h("B.Sc. Computer Science — Universitas Gadjah Mada, 2015", s["body"]),
    ]
    doc.build(story)
    return path


def make_v_mid_devops():
    """Mid-level DevOps — should score 6-7."""
    doc, path = _doc("v_mid_devops.pdf")
    s = _styles()
    story = [
        _h("Bagus Setiawan", s["h1"]),
        _h("bagus.setiawan@gmail.com · +62-21-555-0123 · linkedin.com/in/bagussetiawan", s["body"]),
        Spacer(1, 6),
        _h("Summary", s["h2"]),
        _h("DevOps engineer with 4 years of experience in CI/CD and cloud infrastructure.", s["body"]),
        Spacer(1, 4),
        _h("Experience", s["h2"]),
        _h("<b>DevOps Engineer</b> — Tokopedia (2020 – Present)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Maintained Jenkins pipelines for 30+ microservices; mean build time 12 min.", s["body"])),
                ListItem(Paragraph("Migrated 5 services to AWS EKS; deployment frequency 3/week → 12/day.", s["body"])),
                ListItem(Paragraph("Wrote Terraform modules for VPC, RDS, and S3.", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>Junior DevOps</b> — Blibli (2019 – 2020)", s["body"]),
        _h("Helped set up monitoring with Prometheus and Grafana.", s["body"]),
        Spacer(1, 4),
        _h("Skills", s["h2"]),
        _h("Jenkins, GitLab CI, Kubernetes, Terraform, AWS, Docker, Prometheus, Grafana, Bash, Python", s["body"]),
        Spacer(1, 4),
        _h("Education", s["h2"]),
        _h("B.Sc. Informatics — ITS Surabaya, 2019", s["body"]),
    ]
    doc.build(story)
    return path


def make_v_devops_no_metrics():
    """DevOps with no metrics in bullets — should score 4-5."""
    doc, path = _doc("v_devops_no_metrics.pdf")
    s = _styles()
    story = [
        _h("Aditya Pratama", s["h1"]),
        _h("aditya.pratama@gmail.com", s["body"]),
        Spacer(1, 6),
        _h("Experience", s["h2"]),
        _h("<b>DevOps Engineer</b> — Bukalapak (2021 – Present)", s["body"]),
        _h(
            "Responsible for maintaining CI/CD pipelines. Worked with development teams to deploy "
            "their applications. Helped with cloud infrastructure tasks. Participated in on-call "
            "rotation. Wrote documentation for deployment processes. Reviewed infrastructure-as-code "
            "changes. Assisted in capacity planning discussions.",
            s["body"],
        ),
        _h("<b>System Administrator</b> — Bank BCA (2018 – 2021)", s["body"]),
        _h("Managed Linux servers and provided support to internal users.", s["body"]),
        Spacer(1, 4),
        _h("Skills", s["h2"]),
        _h("Docker, Kubernetes, AWS, Terraform, Jenkins, Linux, Bash, Git", s["body"]),
        Spacer(1, 4),
        _h("Education", s["h2"]),
        _h("B.Sc. Computer Science — Universitas Diponegoro, 2018", s["body"]),
    ]
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# Data / ML (2) — Priya was the only one. Add diversity.
# --------------------------------------------------------------------------- #
def make_v_junior_data_analyst():
    """Junior data analyst — should score 5-6 (some metrics, light experience)."""
    doc, path = _doc("v_junior_data_analyst.pdf")
    s = _styles()
    story = [
        _h("Indah Permata", s["h1"]),
        _h("indah.permata@gmail.com · +62-812-1234-5678 · linkedin.com/in/indahpermata", s["body"]),
        Spacer(1, 6),
        _h("Summary", s["h2"]),
        _h(
            "Data analyst with 2 years of experience in marketing analytics and A/B testing. "
            "Comfortable with SQL, Python, and Looker. Looking to grow into a data science role.",
            s["body"],
        ),
        Spacer(1, 4),
        _h("Experience", s["h2"]),
        _h("<b>Data Analyst</b> — Shopee (2022 – Present)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Built weekly retention dashboard; adopted by 6 product managers.", s["body"])),
                ListItem(Paragraph("Ran 9 A/B tests on the recommendation engine; 3 shipped.", s["body"])),
                ListItem(Paragraph("Wrote SQL queries on a 2 TB events table; average runtime < 4 min.", s["body"])),
            ],
            bulletType="bullet",
        ),
        Spacer(1, 4),
        _h("Skills", s["h2"]),
        _h("SQL, Python (pandas, scikit-learn), Looker, dbt, Airflow, A/B testing, statistics", s["body"]),
        Spacer(1, 4),
        _h("Education", s["h2"]),
        _h("B.Sc. Statistics — Universitas Padjadjaran, 2022", s["body"]),
    ]
    doc.build(story)
    return path


def make_v_data_engineer():
    """Senior data engineer — should score 8-9."""
    doc, path = _doc("v_data_engineer.pdf")
    s = _styles()
    story = [
        _h("Wahyu Nugroho", s["h1"]),
        _h("wahyu.nugroho@gmail.com · +62-811-5555-6666 · linkedin.com/in/wahyunugroho · github.com/wahyunugroho", s["body"]),
        Spacer(1, 6),
        _h("Summary", s["h2"]),
        _h(
            "Data Engineer with 6 years of experience building batch and streaming data pipelines "
            "at scale. Specialised in Spark, Kafka, and cloud data warehouses. Led the data platform "
            "team at a fintech serving 8M users.",
            s["body"],
        ),
        Spacer(1, 4),
        _h("Experience", s["h2"]),
        _h("<b>Senior Data Engineer</b> — OVO (2020 – Present)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Designed the data lake on BigQuery + GCS; now ingesting 4 TB/day from 30+ sources.", s["body"])),
                ListItem(Paragraph("Built Kafka streaming pipelines for transaction events; p99 latency 8s.", s["body"])),
                ListItem(Paragraph("Reduced batch job runtime by 64% via partitioning and clustering.", s["body"])),
                ListItem(Paragraph("Mentored 4 junior engineers; ran weekly data engineering brown-bag.", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>Data Engineer</b> — Traveloka (2018 – 2020)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Migrated 12 ETL jobs from on-prem Hadoop to GCP Dataproc.", s["body"])),
                ListItem(Paragraph("Built Airflow DAGs adopted by 8 analytics engineers.", s["body"])),
            ],
            bulletType="bullet",
        ),
        Spacer(1, 4),
        _h("Skills", s["h2"]),
        _h("Python, Scala, SQL, Spark, Kafka, Airflow, dbt, BigQuery, Snowflake, GCP, AWS, Terraform, Docker, Kubernetes", s["body"]),
        Spacer(1, 4),
        _h("Education", s["h2"]),
        _h("M.Sc. Computer Science — Institut Teknologi Bandung, 2018", s["body"]),
        _h("B.Sc. Computer Science — Universitas Brawijaya, 2015", s["body"]),
    ]
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# Designer / Frontend (2) — new category, no coverage yet.
# --------------------------------------------------------------------------- #
def make_v_senior_frontend():
    """Senior frontend — should score 7-8."""
    doc, path = _doc("v_senior_frontend.pdf")
    s = _styles()
    story = [
        _h("Rina Anggraini", s["h1"]),
        _h("rina.anggraini@gmail.com · +62-813-7777-8888 · linkedin.com/in/rinaanggraini · github.com/rinaa · rinaa.design", s["body"]),
        Spacer(1, 6),
        _h("Summary", s["h2"]),
        _h(
            "Senior Frontend Engineer with 6 years of experience building customer-facing web apps. "
            "Specialised in React, TypeScript, and design systems. Led the design system rebuild at "
            "Bukalapak; shipped 4 net-new products in the last 2 years.",
            s["body"],
        ),
        Spacer(1, 4),
        _h("Experience", s["h2"]),
        _h("<b>Senior Frontend Engineer</b> — Bukalapak (2020 – Present)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Led the design system rebuild; 80+ components, 12 product teams adopting.", s["body"])),
                ListItem(Paragraph("Migrated the seller dashboard from Angular to React; -38% JS bundle size.", s["body"])),
                ListItem(Paragraph("Improved Lighthouse score from 41 to 87 on the homepage.", s["body"])),
                ListItem(Paragraph("Mentored 3 frontend engineers; ran weekly frontend guild.", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>Frontend Engineer</b> — Tokopedia (2018 – 2020)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Built the seller onboarding flow; conversion 32% → 47%.", s["body"])),
                ListItem(Paragraph("Introduced TypeScript across the merchant-side app.", s["body"])),
            ],
            bulletType="bullet",
        ),
        Spacer(1, 4),
        _h("Skills", s["h2"]),
        _h("React, TypeScript, Next.js, GraphQL, Storybook, Figma, Tailwind, Jest, Cypress, Webpack, Vite", s["body"]),
        Spacer(1, 4),
        _h("Education", s["h2"]),
        _h("B.Sc. Computer Science — Universitas Indonesia, 2018", s["body"]),
    ]
    doc.build(story)
    return path


def make_v_junior_ux_designer():
    """Junior UX designer (non-engineering) — should score 5-6 (skills detection gap)."""
    doc, path = _doc("v_junior_ux_designer.pdf")
    s = _styles()
    story = [
        _h("Aulia Rahma", s["h1"]),
        _h("aulia.rahma@gmail.com · +62-812-4444-5555 · behance.net/auliarahma · linkedin.com/in/auliarahma", s["body"]),
        Spacer(1, 6),
        _h("Summary", s["h2"]),
        _h("UX designer with 1 year of experience. Background in visual design, transitioning to product design.", s["body"]),
        Spacer(1, 4),
        _h("Experience", s["h2"]),
        _h("<b>UX Designer</b> — DANA (2023 – Present)", s["body"]),
        _h(
            "Designed onboarding screens for the merchant app. Ran usability tests with 8 users "
            "per round. Built component library in Figma. Collaborated with product managers and "
            "engineers to ship 2 net-new features.",
            s["body"],
        ),
        _h("<b>Visual Design Intern</b> — Tokopedia (Summer 2022)", s["body"]),
        _h("Created social media assets and helped with marketing campaigns.", s["body"]),
        Spacer(1, 4),
        _h("Skills", s["h2"]),
        _h("Figma, Sketch, Adobe XD, Photoshop, Illustrator, user research, wireframing, prototyping, design systems", s["body"]),
        Spacer(1, 4),
        _h("Education", s["h2"]),
        _h("B.A. Visual Communication Design — Universitas Trisakti, 2023", s["body"]),
    ]
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# ID-localized (2) — test Indonesian-language coverage beyond the weak grad.
# --------------------------------------------------------------------------- #
def make_v_id_strong_backend():
    """Indonesian CV for a strong backend — should score 7-8 (i18n test)."""
    doc, path = _doc("v_id_strong_backend.pdf")
    s = _styles()
    story = [
        _h("Andi Kurniawan", s["h1"]),
        _h("andi.kurniawan@gmail.com · +62-811-3333-2222 · linkedin.com/in/andikurniawan", s["body"]),
        Spacer(1, 6),
        _h("Ringkasan Profesional", s["h2"]),
        _h(
            "Backend Engineer dengan 5 tahun pengalaman membangun sistem pembayaran dan layanan "
            "keuangan. Ahli di Go dan Python, dengan rekam jejak memimpin migrasi sistem berskala "
            "besar dan meningkatkan keandalan platform (+30% uptime).",
            s["body"],
        ),
        Spacer(1, 4),
        _h("Pengalaman Kerja", s["h2"]),
        _h("<b>Senior Backend Engineer</b> — DANA (2020 – Sekarang)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Memimpin migrasi layanan dompet dari monolith ke microservices; transaksi puncak 12K QPS.", s["body"])),
                ListItem(Paragraph("Meningkatkan ketersediaan sistem dari 99.85% menjadi 99.97% dalam 12 bulan.", s["body"])),
                ListItem(Paragraph("Membangun sistem idempotency untuk mencegah double-charge; mengurangi dispute 64%.", s["body"])),
                ListItem(Paragraph("Membimbing 3 engineer junior; semua dipromosikan dalam 18 bulan.", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>Backend Engineer</b> — Gojek (2018 – 2020)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Mengembangkan layanan matching untuk driver; latensi p99 turun dari 380ms ke 95ms.", s["body"])),
                ListItem(Paragraph("Membangun pipeline event streaming dengan Kafka.", s["body"])),
            ],
            bulletType="bullet",
        ),
        Spacer(1, 4),
        _h("Keahlian", s["h2"]),
        _h("Go, Python, PostgreSQL, Redis, Kafka, Docker, Kubernetes, AWS, gRPC, Prometheus, Grafana", s["body"]),
        Spacer(1, 4),
        _h("Pendidikan", s["h2"]),
        _h("S.Kom. Teknik Informatika — Institut Teknologi Bandung, 2018", s["body"]),
    ]
    doc.build(story)
    return path


def make_v_id_mid_marketing():
    """Indonesian CV, marketing role (non-tech) — expected 5-6 (i18n + non-tech)."""
    doc, path = _doc("v_id_mid_marketing.pdf")
    s = _styles()
    story = [
        _h("Putri Maharani", s["h1"]),
        _h("putri.maharani@gmail.com · +62-812-6666-7777 · linkedin.com/in/putrimaharani", s["body"]),
        Spacer(1, 6),
        _h("Ringkasan", s["h2"]),
        _h("Digital marketing specialist dengan 4 tahun pengalaman di e-commerce dan FMCG.", s["body"]),
        Spacer(1, 4),
        _h("Pengalaman Kerja", s["h2"]),
        _h("<b>Digital Marketing Manager</b> — Sociolla (2021 – Sekarang)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Memimpin tim 5 orang; meningkatkan ROAS dari 2.8x menjadi 5.1x.", s["body"])),
                ListItem(Paragraph("Menurunkan biaya akuisisi pelanggan (CAC) dari Rp 85.000 ke Rp 42.000.", s["body"])),
                ListItem(Paragraph("Merancang strategi SEO; trafik organik naik 180% year-over-year.", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>Performance Marketing</b> — Tokopedia (2019 – 2021)", s["body"]),
        _h("Mengelola kampanye paid ads dengan budget bulanan Rp 500 juta.", s["body"]),
        Spacer(1, 4),
        _h("Keahlian", s["h2"]),
        _h("Google Ads, Meta Ads, SEO, SEM, Google Analytics, Mixpanel, content marketing, copywriting", s["body"]),
        Spacer(1, 4),
        _h("Pendidikan", s["h2"]),
        _h("S.Kom. Sistem Informasi — Universitas Gadjah Mada, 2019", s["body"]),
    ]
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# Edge cases (2) — career gap, over-experienced.
# --------------------------------------------------------------------------- #
def make_v_career_gap():
    """Engineer with a 2-year career gap (parenthood) — should still score 6-7."""
    doc, path = _doc("v_career_gap.pdf")
    s = _styles()
    story = [
        _h("Linda Susanti", s["h1"]),
        _h("linda.susanti@gmail.com · +62-813-2222-1111 · linkedin.com/in/lindasusanti", s["body"]),
        Spacer(1, 6),
        _h("Summary", s["h2"]),
        _h(
            "Software engineer returning to work after a 2-year career break. 5 years of pre-break "
            "experience in full-stack development. Eager to apply updated skills in React and Go.",
            s["body"],
        ),
        Spacer(1, 4),
        _h("Experience", s["h2"]),
        _h("<b>Software Engineer</b> — Traveloka (2016 – 2021)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Built the booking confirmation flow; reduced drop-off 22%.", s["body"])),
                ListItem(Paragraph("Migrated the email service from SendGrid to in-house; cost down 40%.", s["body"])),
                ListItem(Paragraph("Mentored 2 junior engineers; ran internal React workshops.", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>Junior Engineer</b> — Bukalapak (2014 – 2016)", s["body"]),
        _h("Built internal tools in Python and React.", s["body"]),
        Spacer(1, 4),
        _h("Career Break (2021 – 2023): Family responsibilities. Completed 2 online certifications (AWS Cloud Practitioner, React Advanced).", s["body"]),
        Spacer(1, 4),
        _h("Skills", s["h2"]),
        _h("JavaScript, TypeScript, React, Node.js, Go, Python, PostgreSQL, AWS, Docker, Git", s["body"]),
        Spacer(1, 4),
        _h("Education", s["h2"]),
        _h("B.Sc. Computer Science — Universitas Indonesia, 2014", s["body"]),
    ]
    doc.build(story)
    return path


def make_v_over_experienced():
    """20+ years experience, lots of content — should score 8-9 (over the fit window)."""
    doc, path = _doc("v_over_experienced.pdf")
    s = _styles()
    story = [
        _h("Bambang Suryadi", s["h1"]),
        _h("bambang.suryadi@gmail.com · +62-811-9999-0000 · linkedin.com/in/bambangsuryadi", s["body"]),
        Spacer(1, 6),
        _h("Summary", s["h2"]),
        _h(
            "Engineering leader with 22 years of experience in payments, marketplaces, and "
            "telecom. CTO at two startups (one acquired). Strong on architecture, scaling, and "
            "team building.",
            s["body"],
        ),
        Spacer(1, 4),
        _h("Experience", s["h2"]),
        _h("<b>CTO</b> — FinTechCo (2018 – Present)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Scaled engineering team from 4 to 38 across 3 years.", s["body"])),
                ListItem(Paragraph("Owned architecture for a payments platform processing $1.2B annually.", s["body"])),
                ListItem(Paragraph("Led the IPO-readiness engineering audit in 2023.", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>VP Engineering</b> — MarketHub (2014 – 2018)", s["body"]),
        ListFlowable(
            [
                ListItem(Paragraph("Built and led 6 engineering teams (52 engineers) across 3 product lines.", s["body"])),
                ListItem(Paragraph("Reduced infra cost 41% via migration to multi-cloud.", s["body"])),
            ],
            bulletType="bullet",
        ),
        _h("<b>Engineering Director</b> — Telkom (2010 – 2014)", s["body"]),
        _h("Led the BSS platform team; 80 engineers.", s["body"]),
        _h("<b>Senior Engineer</b> — Indosat (2002 – 2010)", s["body"]),
        _h("Built IN platform and VAS systems.", s["body"]),
        Spacer(1, 4),
        _h("Skills", s["h2"]),
        _h("Engineering leadership, architecture, payments, scaling, hiring, strategy, Java, Go, Python, AWS, GCP, Kubernetes", s["body"]),
        Spacer(1, 4),
        _h("Education", s["h2"]),
        _h("M.Sc. Computer Science — Universitas Indonesia, 2004", s["body"]),
        _h("B.Sc. Electrical Engineering — ITB, 2000", s["body"]),
    ]
    doc.build(story)
    return path


# --------------------------------------------------------------------------- #
# Human grades — best-effort ATS-rubric estimates for v2 CVs.
# --------------------------------------------------------------------------- #
GRADES_V2 = {
    # PM (4) — was blind spot. Aim for 4–9 spread.
    "v_senior_pm_enterprise.pdf": {
        "human_overall": 8.5,
        "human_role": "pm",
        "human_sections": {
            "Contact": 9.0,
            "Summary": 9.0,
            "Experience": 9.0,
            "Skills": 7.5,
            "Education": 8.0,
        },
        "notes": "Senior PM with strong metrics and progression. Skills soft (no hard tools mentioned).",
    },
    "v_junior_pm.pdf": {
        "human_overall": 4.5,
        "human_role": "pm",
        "human_sections": {
            "Contact": 7.0,
            "Summary": 5.0,
            "Experience": 4.5,
            "Skills": 5.0,
            "Education": 7.0,
        },
        "notes": "Junior PM, light bullets, narrative-heavy without numbers. Promising trajectory.",
    },
    "v_pm_metrics_driven.pdf": {
        "human_overall": 7.5,
        "human_role": "pm",
        "human_sections": {
            "Contact": 8.5,
            "Summary": 8.0,
            "Experience": 8.0,
            "Skills": 8.0,
            "Education": 7.0,
        },
        "notes": "Metric-driven PM at fintech. Strong bullets with before/after numbers.",
    },
    "v_pm_soft_skills.pdf": {
        "human_overall": 4.0,
        "human_role": "pm",
        "human_sections": {
            "Contact": 5.0,
            "Summary": 4.0,
            "Experience": 4.0,
            "Skills": 3.0,
            "Education": 7.0,
        },
        "notes": "PM with all narrative bullets, no metrics, soft skills. Should score low.",
    },
    # DevOps / SRE (3)
    "v_senior_sre.pdf": {
        "human_overall": 8.5,
        "human_role": "general",
        "human_sections": {
            "Contact": 9.0,
            "Summary": 8.5,
            "Experience": 9.0,
            "Skills": 8.5,
            "Education": 7.0,
        },
        "notes": "Senior SRE, deep metrics (SLOs, MTTR), hard infra skills.",
    },
    "v_mid_devops.pdf": {
        "human_overall": 6.5,
        "human_role": "general",
        "human_sections": {
            "Contact": 8.0,
            "Summary": 6.0,
            "Experience": 7.0,
            "Skills": 7.5,
            "Education": 7.0,
        },
        "notes": "Mid DevOps with measurable impact. Decent but not exceptional.",
    },
    "v_devops_no_metrics.pdf": {
        "human_overall": 4.0,
        "human_role": "general",
        "human_sections": {
            "Contact": 5.0,
            "Summary": 0.0,
            "Experience": 4.5,
            "Skills": 6.5,
            "Education": 7.0,
        },
        "notes": "DevOps with skills but no metrics in bullets. Should drop Experience score.",
    },
    # Data / ML (2)
    "v_junior_data_analyst.pdf": {
        "human_overall": 5.5,
        "human_role": "data",
        "human_sections": {
            "Contact": 8.0,
            "Summary": 6.0,
            "Experience": 5.5,
            "Skills": 7.0,
            "Education": 6.5,
        },
        "notes": "Junior data analyst with some metrics. Light experience overall.",
    },
    "v_data_engineer.pdf": {
        "human_overall": 8.0,
        "human_role": "data",
        "human_sections": {
            "Contact": 9.0,
            "Summary": 8.0,
            "Experience": 8.5,
            "Skills": 9.0,
            "Education": 8.0,
        },
        "notes": "Senior data engineer with deep infra metrics. Strong across the board.",
    },
    # Designer / Frontend (2)
    "v_senior_frontend.pdf": {
        "human_overall": 7.5,
        "human_role": "swe",
        "human_sections": {
            "Contact": 9.0,
            "Summary": 7.5,
            "Experience": 8.0,
            "Skills": 8.5,
            "Education": 7.0,
        },
        "notes": "Senior frontend with design system leadership. Strong metrics.",
    },
    "v_junior_ux_designer.pdf": {
        "human_overall": 5.0,
        "human_role": "general",
        "human_sections": {
            "Contact": 7.0,
            "Summary": 5.0,
            "Experience": 5.0,
            "Skills": 6.5,
            "Education": 6.5,
        },
        "notes": "Junior UX designer. Heuristic may under-score — soft design tools not in tech dict.",
    },
    # ID-localized (2)
    "v_id_strong_backend.pdf": {
        "human_overall": 7.5,
        "human_role": "swe",
        "human_sections": {
            "Contact": 8.5,
            "Summary": 8.0,
            "Experience": 8.0,
            "Skills": 8.0,
            "Education": 7.0,
        },
        "notes": "Indonesian backend CV. Tests i18n. Strong metrics, ID verbs detected.",
    },
    "v_id_mid_marketing.pdf": {
        "human_overall": 5.5,
        "human_role": "general",
        "human_sections": {
            "Contact": 8.0,
            "Summary": 5.5,
            "Experience": 6.0,
            "Skills": 6.5,
            "Education": 7.0,
        },
        "notes": "ID marketing CV. Non-tech. Should still parse sections correctly.",
    },
    # Edge cases (2)
    "v_career_gap.pdf": {
        "human_overall": 6.0,
        "human_role": "swe",
        "human_sections": {
            "Contact": 8.0,
            "Summary": 6.0,
            "Experience": 6.5,
            "Skills": 7.5,
            "Education": 7.0,
        },
        "notes": "Engineer with 2-year career gap. Pre-break metrics strong, recent return path clear.",
    },
    "v_over_experienced.pdf": {
        "human_overall": 8.0,
        "human_role": "general",
        "human_sections": {
            "Contact": 8.0,
            "Summary": 8.5,
            "Experience": 9.0,
            "Skills": 8.0,
            "Education": 8.0,
        },
        "notes": "20+ years experience, exec-level. May compress in 1-page summary; metrics strong.",
    },
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    builders = [
        make_v_senior_pm_enterprise,
        make_v_junior_pm,
        make_v_pm_with_metrics,
        make_v_pm_soft_skills_only,
        make_v_senior_sre,
        make_v_mid_devops,
        make_v_devops_no_metrics,
        make_v_junior_data_analyst,
        make_v_data_engineer,
        make_v_senior_frontend,
        make_v_junior_ux_designer,
        make_v_id_strong_backend,
        make_v_id_mid_marketing,
        make_v_career_gap,
        make_v_over_experienced,
    ]
    for fn in builders:
        p = fn()
        print(f"wrote {p.name} ({p.stat().st_size} bytes)")

    # Read existing grades (v1) and merge
    grades_path = OUT / "grades.json"
    if grades_path.exists():
        existing = json.loads(grades_path.read_text())
    else:
        existing = {}
    existing.update(GRADES_V2)
    grades_path.write_text(json.dumps(existing, indent=2))
    print(f"wrote {grades_path} ({len(existing)} entries total, +{len(GRADES_V2)} from v2)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
