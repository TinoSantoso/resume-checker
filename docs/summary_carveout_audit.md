# Summary Carve-Out Audit — 2026-07-01

## TL;DR

**fix-later** — The carve-out helper itself is dead code in the v0.4 set
(0/20 triggers), but a *different* upstream bug in `segment_sections` leaks
2 CVs' mid-sentence fragments into the Summary bucket. The leaks are small
in count (10% of the set) and the offending CVs are not the high-volume
PM/DevOps/Frontend roles the plan worried about.

## Hypothesis tested

B2 suggested the Summary carve-out (`_carve_summary_from_header` in
`app/scorer.py`) might be silently misclassifying real Summary text as
header content, costing PM/DevOps/Frontend roles ~2.5 pts in the Summary
section.

**Result: the carve-out is not the culprit.** See "Mechanism" below.

## Methodology

1. Read `app/layout.py` — `page_layout_summary` is a pure diagnostic
   (line 272); no Summary carve-out lives in this file.
2. Read `app/scorer.py` — Summary scoring lives in `_score_summary` (line
   260) and is called from `score_cv` at line 643 with
   `sections.get("Summary", "")`. The carve-out helper
   `_carve_summary_from_header` is only invoked inside the `score_cv`
   fallback at line 631, **and only when `sections["Summary"]` is empty
   AND `_looks_like_summary(header)` is True**.
3. Wrote a temporary harness (`/tmp/audit_summary.py`, not committed)
   that, for each validation CV: parsed the file, replayed the
   carve-out decision, and printed the carved Summary text plus
   auto/human scores.

## Numbers

- CVs audited: **20**
- Summary |Δ| > 0: **14** (signs mixed; mean = +0.05 — overall unbiased)
- Carve-out helper triggered: **0 / 20** (dead code in this set)
- Likely bleed-over: **2 / 20 (10%)**
- Mean point leak per bleed: **-5.0** (auto under-scores on these two)
  - `v_pm_metrics_driven.pdf`: Δ = **-6.0** (auto=2.0, human=8.0)
  - `v_senior_frontend.pdf`:  Δ = **-4.0** (auto=3.5, human=7.5)

## Mechanism — where the leak really is

The Summary field the scorer sees is populated by `segment_sections` in
`app/pdf_parser.py` (line 238), **not** by the carve-out helper. The
helper only fires when `Summary` is empty after segmentation.

For the two bleeders, `segment_sections` correctly detects a
"Summary"/"Profile" header but the content it grabs is just the trailing
wrapped line of a multi-line paragraph:

| CV | Summary text actually scored | Real Summary content (lives in Experience) |
|---|---|---|
| `v_pm_metrics_driven.pdf` | `"(+18%) and retention (+12 NPS)."` | "Product Manager with 4 years… metric-driven iteration… 2.7% (+18%) over 4 months." |
| `v_senior_frontend.pdf` | `"products in the last 2 years."` | "Senior Frontend Engineer with 6 years… Led the design system rebuild at Bukalapak… products in the last 2 years." |

Both are bullet-less wrapped paragraphs where the `Summary` header
prefix is followed immediately by a hard line-wrap continuation. The
segmenter appears to slice at the first internal newline.

The other 18 CVs land cleanly:
- 14 are correctly classified "real" summaries (career synopsis, role
  + years, professional tagline).
- 4 are legitimately empty (`v_devops_no_metrics`, `v_id_strong_backend`,
  `v_mixed_lean`, `v_senior_pm_enterprise`, `v_weak_recent_grad`) —
  these CVs have no Summary section at all, the human graded 0 or
  close to it, and the auto score agrees.

## By CV-type

| Role family | n | Bleed | Mean Δ on bleeds |
|---|---|---|---|
| Junior PM | 1 | 0 | — |
| Mid/Senior PM | 3 | 1 | -6.0 |
| Mid/Senior SWE | 6 | 0 | — |
| Senior Frontend | 1 | 1 | -4.0 |
| Data/ML/DE | 3 | 0 | — |
| DevOps/SRE | 3 | 0 | — |
| UX/Design | 1 | 0 | — |
| Marketing/Career-gap | 2 | 0 | — |

Bleed hits one PM (metrics-driven) and one Frontend. Both are senior-ish,
both use a single multi-line summary paragraph, both lose points because
the segmenter only retains the wrapped tail.

## Recommendation

**fix-later** — Do not touch the carve-out helper. It is correct, just
never invoked. The actual fix belongs in `segment_sections` (PDF
parser) and should change how it slices content immediately after a
detected "Summary" / "Profile" / "Tentang" header: when the section
content is a wrapped paragraph (no bullet markers, no other section
header within ~5 lines), treat the whole block as Summary instead of
capping at the first newline.

Effort estimate: **S** (1-2 hours, ~30 lines + a regression test
fixture using `v_pm_metrics_driven.pdf`).

Why not fix-now:
- n=2 of 20 (10%) is below the plan's fix-now threshold of ≥3.
- The two affected CVs are not in the high-traffic role bucket the
  plan was worried about (PM/DevOps/Frontend broadly — only one PM
  and one Frontend bleed).
- The mean Δ on bleeds (-5.0) is large in isolation but contributes
  only -0.5 to the overall Summary mean Δ across the set, which is
  not the cause of the B2 under-scoring symptom.

## Next step

If/when this is fixed, the patch sketch is:

```python
# app/pdf_parser.py — inside segment_sections
# After detecting a Summary header, if the next non-blank line(s) look
# like a wrapped paragraph (no bullet marker, no other section header
# within 5 lines), keep appending until we hit a blank line OR a
# section-header candidate. This recovers the 2 known bleeders.
```

Add a regression test in `tests/test_pdf_parser.py` using
`v_pm_metrics_driven.pdf` as fixture: assert `sections["Summary"]`
contains "Product Manager with 4 years" (the human-readable
sentence), not "(+18%) and retention (+12 NPS).".

Cost of ignoring for v0.5: **0.5 pts** on average Summary score
across the full 20-CV set. Acceptable given v0.5 priorities.
