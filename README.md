# CV Reviewer — Local RAG

Simple CV/Resume reviewer running fully on local Ollama models.

## Architecture

```
PDF CV → PyMuPDF (extract) → Section segmentation → Heuristic scoring
                                                          ↓
                                              RAG retrieval (ChromaDB + nomic-embed-text)
                                                          ↓
                                              LLM feedback (qwen2.5:3b)
                                                          ↓
                                              Streamlit UI + JSON export
```

## Stack

| Component | Tool |
|---|---|
| PDF parsing | PyMuPDF |
| Embedding | `nomic-embed-text` via Ollama |
| Vector DB | ChromaDB (persistent) |
| Orchestration | LlamaIndex |
| LLM | `qwen2.5:3b` via Ollama |
| UI | Streamlit |

## Knowledge Base

`kb/rubrics/` — 4 role-specific ATS rubrics (40 rules total):
- `general.json` — baseline ATS rules (10 rules)
- `swe.json` — Software Engineering variant (10 rules, weighted for code/shops)
- `data.json` — Data (analyst/scientist/engineer) variant (10 rules, weighted for ML/data stacks)
- `pm.json` — Product Management variant (10 rules, weighted for impact bullets)

Each role's rule IDs use a unique prefix (R/S/D/P) so multi-role RAG retrieval
returns unambiguous citations in the LLM prompt. Run
`python3 scripts/build_weights.py` to regenerate `app/weights.py` after
adding rules.

The scorer auto-detects the role from a CV's Skills + Summary text and
applies the matching rubric's weights. Override via the sidebar role
selector in the Streamlit UI or the `role=` parameter in `score_cv()`.

## Scoring

Deterministic per-section heuristics (0–10 each), then weighted overall.
**Weights come from the role-specific rubric.** For the general rubric:
- Contact 1.0 · Summary 1.5 · **Experience 2.5** · Skills 1.5 · Education 0.7 · Length 1.0

Other roles redistribute these — see the output of `python3 scripts/build_weights.py`
for the exact per-role breakdown. PM weights Experience at 0.56 and Skills
at 0.05 (soft skills OK per PM craft); SWE/Data both weight Skills at ~0.21
(named tools are critical).

Heuristics check: action verbs, metrics, dates, concrete skills, vague phrases,
length, ATS-hostile patterns.

LLM is **not** used for scoring — only for narrative feedback grounded in
retrieved rubric rules.

## Run

```bash
# Activate venv
source ~/projects/cv-reviewer/.venv/bin/activate

# Make sure ollama is serving
ollama serve &
ollama pull qwen2.5:3b nomic-embed-text

# Build index (one-time)
python3 -m app.rag

# Generate sample CVs (optional, for testing)
python3 scripts/gen_samples.py

# Run app
streamlit run app/streamlit_app.py --server.port 8501
```

Then open `http://localhost:8501`.

## CLI quick test

```bash
# Score only (fast, deterministic)
python3 -m app.scorer data/sample_strong.pdf

# Score + LLM feedback (~90s on CPU)
python3 -m app.feedback data/sample_medium.pdf
```

## Sample test results

| Sample | Score | Grade |
|---|---|---|
| `sample_strong.pdf` (senior SWE with metrics) | 8.5 | B |
| `sample_medium.pdf` (data analyst, mixed) | 4.2 | F |
| `sample_weak.pdf` (weak verbs, no metrics) | 2.4 | F |

## Limitations

- **English-leaning** (KB is English; Indonesian support is partial via the
  i18n layer but model bias remains)
- **Role coverage is SWE/Data/PM only** — niche roles like DevOps, ML
  researcher, Designer, Sales fall back to the general rubric. Add a
  rubric file + signal set to extend.
- **3B model** will hallucinate occasionally — always read rubric-cited
  feedback with judgment
- **Scoring is heuristic** — current validation set (5 CVs) shows
  Pearson +0.88, MAE 0.86 against human grades (role-aware mode). The
  heuristic's biggest miss is on PM-style CVs where soft skills aren't
  rewarded enough — see "Validation" below for per-sample detail.
- 3B model on CPU is slow (~30s per CV review with 3-worker concurrency;
  was 90s before parallelization)

## PII redaction (C1)

`parse_cv()` redacts PII (email, phone, LinkedIn, street address, DOB)
by default. The redacted sections are safe to send to the LLM and to
persist into ChromaDB. The recruiter UI calls `result.render_unmasked()`
to display the original contact details to the recruiter. See
`app/redactor.py` for the pattern registry and `tests/test_redactor.py`
for coverage. Set `parse_cv(path, redact_pii=False)` only for debugging.

## Ollama health check (C2)

The Streamlit sidebar shows a live status pill (`🟢 ready` / `🔴 offline` /
`⚠ model missing`) probing `GET /api/tags` against `localhost:11434`.
A "Refresh" button clears the cached probe so users can verify the
server after starting `ollama serve`. See `app/health.py` and
`tests/test_health.py`. Status codes: `HEALTH_OK` / `HEALTH_OFFLINE` /
`HEALTH_MODEL_MISSING`.

## Skill dictionary (B1)

The Skills section scorer uses `app/skill_dictionary.py` to:
- Resolve aliases (`Amazon Web Services` → `AWS`, `k8s` → `Kubernetes`)
- Dedupe case variants (`AWS`, `aws`, `Aws` → one entry)
- Categorize skills (Language / Cloud / Database / …) so the recruiter
  sees "3 Language, 3 Framework, 2 Database" in the evidence

Cleans tokens like `"PHP - Advanced"`, `"Python (3 years)"`, and
`"Skills: Python"` before lookup. Registry is data-only — extend
`SKILL_CATEGORIES` and `_ALIASES` as new tech shows up in real CVs.
See `tests/test_skill_dictionary.py` for coverage.

## Validation

Auto-score vs human review, across 5 manually graded CVs in `data/validation/`.
Run role-aware mode (the default) to score each CV with its `human_role` rubric:

```bash
python3 scripts/validate_against_human.py            # auto-detect role
python3 scripts/validate_against_human.py --use-role-rubrics  # use human_role field
```

Latest run (role-aware, 5 CVs):

| CV | Role | Human | Auto | Δ |
|---|---|---|---|---|
| `v_strong_ml.pdf` (senior ML) | data | 8.5 | 8.5 | 0.0 |
| `v_good_pm.pdf` (senior PM) | pm | 8.0 | 5.3 | -2.7 |
| `v_medium_backend.pdf` | swe | 5.5 | 5.8 | +0.3 |
| `v_mixed_lean.pdf` (DevOps, no summary) | swe | 4.5 | 3.4 | -1.1 |
| `v_weak_recent_grad.pdf` | swe | 2.5 | 2.3 | -0.2 |

**Overall:** Pearson +0.877 · Spearman +0.900 · MAE 0.86 points.
**Role detector accuracy:** 5/5.

Per-section Pearson (Contact/Summary/Experience/Skills/Education) ranges
0.75–1.00. The heuristic's biggest miss is `v_good_pm.pdf` — the PM
rubric weights Experience at 0.56 (impact bullets dominate), but the
human grader weighted PM soft skills higher than our heuristic rewards.

To add your own grades:

1. Drop a CV in `data/validation/`
2. Add a matching entry to `data/validation/grades.json`. Schema at top
   of `scripts/validate_against_human.py`. Set `human_role` to one of
   `general`, `swe`, `data`, `pm` (use `general` if the CV doesn't fit
   a role-specific bucket).
3. Re-run: `python3 scripts/validate_against_human.py --use-role-rubrics --strict`
   (exits non-zero if Pearson drops below 0.5 or MAE above 2.5)

## Project layout

```
cv-reviewer/
├── .venv/                  # Python venv
├── app/
│   ├── __init__.py
│   ├── pdf_parser.py       # PyMuPDF + python-docx + section segmentation
│   ├── layout.py           # 2-column PDF layout handling
│   ├── rag.py              # ChromaDB index + role-filtered retrieval
│   ├── scorer.py           # Deterministic per-section scoring (role-aware)
│   ├── feedback.py         # LLM narrative feedback (RAG-grounded, parallel, role-filtered)
│   ├── matcher.py          # JD match scoring (P1.2)
│   ├── jd_parser.py        # JD skill extraction (P1.2)
│   ├── role_detector.py    # SWE/Data/PM role classifier (v0.4)
│   ├── rubric_registry.py  # Multi-rubric loader (v0.4)
│   ├── weights.py          # Per-role section weights (auto-generated)
│   ├── i18n.py             # EN/ID bilingual support (P1.4)
│   ├── redactor.py         # PII scrubbing (C1) — strips email/phone/etc before LLM
│   ├── health.py           # Ollama health probe + UI summary (C2)
│   ├── skill_dictionary.py # Tech skill aliases + categories (B1)
│   └── streamlit_app.py    # Web UI (with role selector)
├── kb/
│   ├── ats_rubric.json     # legacy single-rubric (kept for v0.x compat)
│   └── rubrics/            # Per-role rubrics (v0.4)
│       ├── general.json
│       ├── swe.json
│       ├── data.json
│       └── pm.json
├── scripts/
│   ├── gen_samples.py      # Synthetic CV generator (unit-test fixtures)
│   ├── gen_docx_fixtures.py # DOCX fixtures (unit-test fixtures)
│   ├── gen_validation_set.py # Validation set generator
│   ├── validate_against_human.py # Pearson/Spearman/MAE harness (role-aware mode)
│   └── build_weights.py    # Regenerate app/weights.py from the KB
├── data/
│   ├── chroma/             # Persistent vector index (multi-role)
│   ├── sample_*.pdf        # Unit-test CVs (strong/medium/weak)
│   ├── tino_actual.pdf     # Real Tino CV (the original 4.9/10)
│   ├── tino_shaped.docx    # DOCX fixture mirroring tino_actual.pdf
│   ├── strong_candidate.docx # DOCX fixture for a strong candidate
│   └── validation/         # Validation set (graded by hand, with human_role)
│       ├── grades.json
│       └── v_*.pdf
└── tests/
    ├── test_pdf_parser.py
    ├── test_layout.py
    ├── test_scorer.py
    ├── test_feedback.py
    ├── test_matcher.py
    ├── test_jd_parser.py
    ├── test_i18n.py
    ├── test_weights.py     # Per-role weights + rubric registry
    ├── test_role_detector.py  # SWE/Data/PM classifier (v0.4)
    ├── test_role_aware_scoring.py  # End-to-end role scoring (v0.4)
    └── test_validation.py
```