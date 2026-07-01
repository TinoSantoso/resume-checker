"""LLM feedback layer — combine RAG-retrieved rubric with deterministic scores.

Per-section feedback is generated concurrently using a thread pool, since
Ollama HTTP calls are I/O bound and a 3B model on CPU benefits from
running multiple section requests in parallel (typical win: 90s → ~30s
for 6 sections on 3 workers).

Concurrency is bounded (LLM_MAX_WORKERS) to avoid overloading the local
Ollama server, which loads a single model instance into memory.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional

from llama_index.core import Settings
from llama_index.llms.ollama import Ollama

from .rag import retrieve_rules
from .scorer import CVReport, SectionScore

LLM_MODEL = "qwen2.5:3b"

# Max concurrent section-feedback requests to Ollama. 3 is a good default
# for a 3B model on CPU: enough to overlap HTTP I/O without exhausting
# memory by loading duplicate model instances.
LLM_MAX_WORKERS = 3


def get_llm() -> Ollama:
    return Ollama(
        model=LLM_MODEL,
        base_url="http://localhost:11434",
        request_timeout=120.0,
        # Stay deterministic-ish for scoring stability.
        temperature=0.2,
        context_window=8192,
    )


SYSTEM_PROMPT = """You are a senior technical recruiter and CV reviewer with 15 years
of experience reviewing resumes for FAANG-tier companies and fast-growing startups.

Your style: direct, specific, actionable. Never use fluff. Never start with
"Great CV!" or similar empty praise. Reference the rubric rules provided as evidence.

Output format: 2–4 short bullet points per section. Each bullet must be:
- A specific observation tied to the rubric rule cited
- A concrete rewrite suggestion when the rule is violated
- One sentence maximum

If the section is empty or unscorable, say so plainly."""


SYSTEM_PROMPT_ID = """Anda adalah perekrut teknis senior dan penelaah CV dengan 15 tahun
pengalaman meninjau CV untuk perusahaan tier-1 dan startup yang sedang tumbuh.

Gaya Anda: langsung, spesifik, dapat ditindaklanjuti. Jangan bertele-tele.
Jangan mulai dengan "CV yang bagus!" atau pujian kosong serupa. Rujuk
aturan rubrik yang diberikan sebagai bukti.

Format output: 2–4 poin pendek per bagian. Setiap poin harus:
- Observasi spesifik yang dikaitkan dengan aturan rubrik
- Saran perbaikan konkret ketika aturan dilanggar
- Maksimal satu kalimat

Jika bagian kosong atau tidak dapat dinilai, nyatakan demikian."""


def _get_system_prompt(language: str) -> str:
    """Return the system prompt for the given language (P1.4)."""
    return SYSTEM_PROMPT_ID if language == "id" else SYSTEM_PROMPT


def _format_section_context(section: SectionScore, rules: List[dict]) -> str:
    """Build the user prompt for one section."""
    rules_text = "\n".join(
        f"- [{r['rule_id']}] (weight {r['weight']}) {r['text']}"
        for r in rules
    )
    evidence_text = (
        "\n".join(f"+ {e}" for e in section.evidence) if section.evidence else "(none)"
    )
    issues_text = (
        "\n".join(f"- {i}" for i in section.issues) if section.issues else "(none)"
    )
    return f"""SECTION: {section.name}
SCORE: {section.score}/10

DETECTED STRENGTHS:
{evidence_text}

DETECTED ISSUES:
{issues_text}

RELEVANT RUBRIC RULES:
{rules_text}

Write 2–4 short bullets of specific feedback. Cite rule IDs (e.g. "[R5]") when referencing rubric."""


def _generate_one_section(
    llm: Ollama,
    name: str,
    section: SectionScore,
    system_prompt: str = SYSTEM_PROMPT,
    role: str = "general",
) -> tuple[str, str]:
    """Build prompt + call LLM for one section. Returns (name, feedback_text).

    ``system_prompt`` defaults to English; pass SYSTEM_PROMPT_ID for
    Indonesian feedback (P1.4).

    ``role`` controls which rubric variant we retrieve rules from. When
    set to ``"general"`` (default) we span all roles; when ``"swe"``,
    ``"data"``, or ``"pm"`` we scope retrieval to that role's rubric
    (plus the universal general rules as a baseline).
    """
    # Use the section's text + issues as the retrieval query.
    query_bits = [name.replace("_", " ")]
    query_bits.extend(section.issues[:3])
    if section.score < 5:
        query_bits.append("improve this section")
    query = " ".join(query_bits)

    rules = retrieve_rules(query, top_k=4, role=role)
    prompt = _format_section_context(section, rules)
    full_prompt = f"{system_prompt}\n\n{prompt}"

    try:
        resp = llm.complete(full_prompt)
        return name, str(resp).strip()
    except Exception as e:
        return name, f"(LLM error: {e})"


def _detect_report_language(report: CVReport) -> str:
    """Detect dominant language of the CV from section text (P1.4)."""
    from .i18n import detect_language
    # Flatten evidence + issues + name from all sections into a single text blob.
    parts: list[str] = []
    for s in report.sections.values():
        parts.extend(s.evidence)
        parts.extend(s.issues)
        parts.append(s.name)
    return detect_language(" ".join(parts))


def generate_feedback(
    report: CVReport,
    max_workers: int = LLM_MAX_WORKERS,
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
    language: Optional[str] = None,
    role: Optional[str] = None,
) -> Dict[str, str]:
    """Generate per-section feedback concurrently.

    Args:
        report: the scored CV report.
        max_workers: max concurrent Ollama requests. Defaults to LLM_MAX_WORKERS.
            Set to 1 to force sequential (useful for tests + debugging).
        progress_cb: optional callback ``cb(section_name, completed, total)``
            invoked when each section finishes. Used by the Streamlit UI
            to update a progress bar.
        language: ``"id"`` or ``"en"``. If None (default), auto-detect
            from the report contents (P1.4).
        role: rubric variant for retrieval. Defaults to ``report.role``
            (set by ``score_cv``). Pass ``"swe"``/``"data"``/``"pm"``/
            ``"general"`` to override.

    Returns:
        Dict mapping section name to feedback text. Sections that error
        get an "(LLM error: ...)" placeholder so the rest of the report
        still renders.
    """
    if language is None:
        language = _detect_report_language(report)
    system_prompt = _get_system_prompt(language)
    if role is None:
        role = report.role  # set by score_cv()

    llm = get_llm()
    sections = list(report.sections.items())
    total = len(sections)
    feedback: Dict[str, str] = {}

    if total == 0:
        return feedback

    # Fast path: single worker (sequential) — skip the executor overhead.
    if max_workers <= 1:
        completed = 0
        for name, section in sections:
            name, text = _generate_one_section(llm, name, section, system_prompt, role=role)
            feedback[name] = text
            completed += 1
            if progress_cb:
                progress_cb(name, completed, total)
        return feedback

    # Concurrent path.
    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all section jobs up front; we want bounded concurrency.
        future_to_name = {
            executor.submit(_generate_one_section, llm, name, section, system_prompt, role=role): name
            for name, section in sections
        }
        for future in as_completed(future_to_name):
            try:
                name, text = future.result()
                feedback[name] = text
            except Exception as e:
                # Defensive: a future raising (not the per-section try/except)
                # shouldn't take down the whole report.
                name = future_to_name[future]
                feedback[name] = f"(LLM error: {e})"
            completed += 1
            if progress_cb:
                progress_cb(name, completed, total)

    return feedback


def generate_overall_summary(report: CVReport, feedback: Dict[str, str]) -> str:
    """Generate top-of-report narrative based on scores + per-section feedback."""
    llm = get_llm()
    sections_brief = "\n".join(
        f"- {name}: {s.score}/10 ({len(s.issues)} issues, {len(s.evidence)} strengths)"
        for name, s in report.sections.items()
    )
    weakest = sorted(report.sections.items(), key=lambda kv: kv[1].score)[:2]
    weakest_text = ", ".join(f"{n} ({s.score}/10)" for n, s in weakest)

    prompt = f"""A candidate's CV scored {report.overall}/10 → {report.grade}.

Section scores:
{sections_brief}

The two weakest sections are: {weakest_text}.

Write a 3-sentence executive summary:
1. State the strongest section and why it works
2. State the weakest section and the single highest-impact fix
3. One sentence on overall readiness for ATS systems

Tone: candid, professional, no fluff. No greetings, no sign-offs."""
    try:
        return str(llm.complete(prompt)).strip()
    except Exception as e:
        return f"(LLM error: {e})"


if __name__ == "__main__":
    import sys
    from .scorer import score_cv
    if len(sys.argv) < 2:
        print("usage: python -m app.feedback <cv.pdf>")
        sys.exit(1)
    rep = score_cv(sys.argv[1])
    fb = generate_feedback(rep)
    summary = generate_overall_summary(rep, fb)
    print(f"\n=== EXECUTIVE SUMMARY ===\n{summary}\n")
    for name, s in rep.sections.items():
        print(f"\n--- {name} ({s.score}/10) ---")
        print(fb.get(name, "(no feedback)"))