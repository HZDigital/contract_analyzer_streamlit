"""
Large-contract map-reduce analysis utilities.
"""

import json
import re
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

from src.api.settings import azure_config


CONTRACT_SCANNER_SYSTEM_PROMPT = """
# Role
You are a document analyst supporting a commercial due-diligence team. You read legal and contractual documents — contracts, but also litigation and dispute documents (warning letters/Abmahnungen, complaints, nullity actions), regulatory correspondence, and corporate records — and explain what they mean for the business. Your readers are commercial reviewers, not lawyers: lead with commercial impact and keep legal mechanics brief, only as far as they drive that impact. You are mandate-agnostic: never insert any client, deal, or company name not in the document itself. This is decision support, not legal advice.

# Core principles
1. Commercial lens, neutral facts. Translate legal facts into commercial consequence — revenue or product lines at risk, costs, contingent liabilities, valuation/deal impact, operational disruption, deadlines. State facts objectively (who bears what); do not assume which side the reader is on.
2. Ground everything. Cite the page/section for every finding. For material points and watch-outs, include a short verbatim quote (≤25 words) in the original language. Never invent a clause, number, term, or figure.
3. Fact vs. inference. State as fact only what is in the text. Mark anything you deduce — including merits/likelihood judgments — as [Inference]. If unsure, say so.
4. No redundancy. Each section has a distinct job. State each distinct point once, in the section where it matters most; do not repeat it elsewhere. Consolidate points the document itself repeats.
5. No filler. Do NOT list standard headings that are absent and write "not found". Omit topics the document doesn't cover. Only flag an absent item when its absence is itself materially surprising for this document type (e.g. a supply contract with no liability cap).
6. Match the language. Respond in the document's language; keep quotes in the original.

# Document handling (incl. 500+ pages)
- Never assume content you have not been shown. If text is truncated, or it cross-references material not present (cited exhibits/Anlagen, schedules), say so under open items.
- Sectioned mode: if the user feeds the document in parts ("part 1 of 4" or signals more is coming), acknowledge each part in 1–2 lines, keep a structured running record, and produce the final analysis only when the user says it's complete ("done").

# Method
First identify the document type and the parties' roles, and choose the structured headings that fit (see Key facts). Then read for substance, consolidating points the document repeats. Surface only the final output.

# Output — lead with the bottom line, then support it (top-down)

**TLDR** — 3–5 bullets: what the document is, and the commercial bottom line. No legal detail beyond what's needed to make the point land.

**Commercial assessment**
- Exposure / magnitude: what's at stake, quantified where the text allows (€, units, revenue/product lines, contingent liability). If not quantifiable from the text, say so.
- Likelihood / merits: how strong each side's position appears and what is contested — marked [Inference], based on the document's own framing.
- Deal / valuation impact: what a commercial reviewer should take from this.
- Urgency: key dates and what they trigger.
- Risk level: Low / Medium / High — one line on why.

**Key facts** — the structured substance, under headings that fit the document type; include only headings that have content. Each point: substance + page/section ref; quote where wording matters. Pick the frame:
- Contract: Parties & subject · Term & termination · Commercials (price/payment) · Liability & indemnity · Change-of-control & assignment · IP & licenses · Confidentiality & data · Governing law & disputes · Other.
- Dispute / litigation: Parties & roles · What is asserted · Legal basis · Relief sought · Financial exposure · Deadlines & procedural status · Defenses & counter-arguments · Parallel / related proceedings · Other.
- Regulatory / authority: Authority & matter · Findings · Required actions · Sanctions · Deadlines · Appeal rights.
(For other document types, choose comparable substantive headings.)

**Watch-outs & open items** — ONLY what is not already obvious from the sections above: genuinely unusual, one-sided, or high-exposure provisions; missing-but-expected items; and gaps where you could not see referenced material (exhibits, schedules, cross-referenced sections). Each: short quote or description + page/section + one line on why it matters. Do not restate points already covered above. If none, say so.

# Follow-up
After the analysis, act as a grounded Q&A partner on the same document: same commercial lens, same citation discipline, no speculation beyond the text.
""".strip()


SUMMARY_TOPICS = [
    "Document Type & Parties",
    "Commercial Exposure & Magnitude",
    "Urgency & Deadlines",
    "Contract: Parties & Subject",
    "Contract: Term & Termination",
    "Contract: Commercials",
    "Contract: Liability & Indemnity",
    "Contract: Change-of-Control & Assignment",
    "Contract: IP & Licenses",
    "Contract: Confidentiality & Data",
    "Contract: Governing Law & Disputes",
    "Dispute: What Is Asserted",
    "Dispute: Legal Basis",
    "Dispute: Relief Sought",
    "Dispute: Financial Exposure",
    "Dispute: Procedural Status & Defenses",
    "Regulatory: Authority & Matter",
    "Regulatory: Findings & Required Actions",
    "Regulatory: Sanctions & Appeal Rights",
    "Other",
]


def build_contract_chunks(
    pages: List[Dict[str, Any]],
    source_file: str = "contract.pdf",
    max_chars: int = 18000,
    overlap_pages: int = 1,
) -> List[Dict[str, Any]]:
    """Build page-range chunks with small page overlap for cross-page clauses."""
    readable_pages = [page for page in pages if str(page.get("text", "")).strip()]
    chunks: List[Dict[str, Any]] = []
    current_pages: List[Dict[str, Any]] = []
    current_length = 0

    for page in readable_pages:
        page_text = str(page.get("text", ""))
        projected_length = current_length + len(page_text) + 80
        if current_pages and projected_length > max_chars:
            chunks.append(_make_chunk(chunks, current_pages, source_file))
            current_pages = current_pages[-overlap_pages:] if overlap_pages else []
            current_length = sum(len(str(item.get("text", ""))) + 80 for item in current_pages)

        current_pages.append(page)
        current_length += len(page_text) + 80

    if current_pages:
        chunks.append(_make_chunk(chunks, current_pages, source_file))

    return chunks


def analyze_contract_chunk(chunk: Dict[str, Any], total_chunks: int) -> Dict[str, Any]:
    """Extract structured evidence from one chunk. No global absence findings here."""
    if not azure_config.client:
        return {
            "chunk_id": chunk.get("chunk_id"),
            "error": "Azure OpenAI credentials not configured",
            "findings": [],
            "red_flags": [],
            "cross_reference_gaps": [],
        }

    prompt = f"""
Task: analyze this document chunk and return ONLY valid JSON. This is chunk {chunk.get('chunk_id')} of {total_chunks}.

Chunk metadata:
- Source file: {chunk.get('source_file')}
- Pages: {chunk.get('page_start')} to {chunk.get('page_end')}
- Detected section markers: {', '.join(chunk.get('detected_sections') or []) or 'None detected'}

Return this JSON shape exactly:
{{
  "chunk_id": "string",
  "language": "string or unsure",
  "scope_note": "short note about what this chunk covers",
  "findings": [
    {{
      "category": "one of: {', '.join(SUMMARY_TOPICS)}",
      "topic": "short neutral topic",
      "substance": "what the clause says, neutral and concise",
      "section_ref": "clause/section number if present, otherwise Not found in the provided text",
      "page_ref": "page or page range",
      "quote": "verbatim quote <=25 words where wording matters, otherwise empty string",
      "inference": false,
      "confidence": "high|medium|low"
    }}
  ],
  "red_flags": [
    {{
      "issue": "neutral description of unusual/risky/material term",
      "why_it_matters": "commercial/operational/legal risk allocation impact, no advice",
      "section_ref": "clause/section number if present, otherwise Not found in the provided text",
      "page_ref": "page or page range",
      "quote": "verbatim quote <=25 words in original language",
      "risk_level": "low|medium|high",
      "inference": false
    }}
  ],
  "cross_reference_gaps": [
    {{
      "reference": "referenced clause/schedule/appendix not visible in this chunk",
      "page_ref": "page or page range",
      "quote": "short quote <=25 words if available"
    }}
  ]
}}

Rules for this chunk:
- Do not conclude that standard protections are absent from the whole contract.
- Use only text in this chunk.
- If no findings or red flags, return empty arrays.
- Do not wrap JSON in markdown fences.

Contract chunk text:
{chunk.get('text', '')}
""".strip()

    try:
        response = azure_config.client.chat.completions.create(
            model=azure_config.deployment_name,
            messages=[
                {"role": "system", "content": CONTRACT_SCANNER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=1,
        )
        payload = _parse_json_response(response.choices[0].message.content)
        payload["chunk_id"] = str(payload.get("chunk_id") or chunk.get("chunk_id"))
        payload["page_start"] = chunk.get("page_start")
        payload["page_end"] = chunk.get("page_end")
        return payload
    except Exception as e:
        return {
            "chunk_id": chunk.get("chunk_id"),
            "page_start": chunk.get("page_start"),
            "page_end": chunk.get("page_end"),
            "error": str(e),
            "findings": [],
            "red_flags": [],
            "cross_reference_gaps": [],
        }


def analyze_contract_chunks(
    chunks: List[Dict[str, Any]],
    progress_callback: Optional[Callable[[int, int, Dict[str, Any]], None]] = None,
) -> List[Dict[str, Any]]:
    """Analyze chunks sequentially so callers receive deterministic progress."""
    results = []
    total = len(chunks)
    for index, chunk in enumerate(chunks, 1):
        result = analyze_contract_chunk(chunk, total)
        results.append(result)
        if progress_callback:
            progress_callback(index, total, result)
    return results


def merge_chunk_findings(chunk_results: List[Dict[str, Any]], chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge chunk-level evidence into a compact final synthesis payload."""
    findings_by_category: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    red_flags: List[Dict[str, Any]] = []
    cross_reference_gaps: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    seen_findings = set()
    seen_flags = set()

    for result in chunk_results:
        chunk_id = result.get("chunk_id")
        if result.get("error"):
            errors.append({"chunk_id": chunk_id, "error": result.get("error")})

        for finding in _ensure_list(result.get("findings")):
            finding = _normalize_evidence_item(finding, chunk_id)
            key = _dedupe_key(finding, ["category", "topic", "section_ref", "quote"])
            if key in seen_findings:
                continue
            seen_findings.add(key)
            category = finding.get("category") if finding.get("category") in SUMMARY_TOPICS else "Other Notable Provisions"
            finding["category"] = category
            findings_by_category[category].append(finding)

        for flag in _ensure_list(result.get("red_flags")):
            flag = _normalize_evidence_item(flag, chunk_id)
            key = _dedupe_key(flag, ["issue", "section_ref", "quote"])
            if key in seen_flags:
                continue
            seen_flags.add(key)
            red_flags.append(flag)

        for gap in _ensure_list(result.get("cross_reference_gaps")):
            gap = _normalize_evidence_item(gap, chunk_id)
            cross_reference_gaps.append(gap)

    page_start = min((chunk.get("page_start") for chunk in chunks if chunk.get("page_start")), default=None)
    page_end = max((chunk.get("page_end") for chunk in chunks if chunk.get("page_end")), default=None)

    return {
        "source_file": chunks[0].get("source_file") if chunks else "",
        "page_start": page_start,
        "page_end": page_end,
        "chunks_analyzed": len(chunk_results),
        "findings_by_category": dict(findings_by_category),
        "red_flags": red_flags,
        "cross_reference_gaps": cross_reference_gaps,
        "errors": errors,
        "standard_topics": SUMMARY_TOPICS,
    }


def synthesize_contract_analysis(merged: Dict[str, Any], is_complete_document: bool = True) -> str:
    """Create final Contract Scanner markdown report from merged evidence."""
    if not azure_config.client:
        return "Azure OpenAI credentials not configured. Set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT."

    compact_evidence = _limit_json_chars(merged, max_chars=90000)
    completeness_note = "Complete uploaded document was processed." if is_complete_document else "Only selected/partial text was processed; never assume unseen content."

    prompt = f"""
Task: synthesize final due-diligence report from merged evidence. Use only supplied evidence.

Completeness note: {completeness_note}
Evidence JSON:
{compact_evidence}

Required final structure exactly:

**TLDR**
- 3-5 bullets: what the document is, and the commercial bottom line.

**Commercial assessment**
- Exposure / magnitude: what's at stake, quantified where the text allows. If not quantifiable from the text, say so.
- Likelihood / merits: how strong each side's position appears and what is contested, marked [Inference].
- Deal / valuation impact: what a commercial reviewer should take from this.
- Urgency: key dates and what they trigger.
- Risk level: Low / Medium / High with one-line basis.

**Key facts**
Use only headings that fit the document and have content. Choose the frame from the system prompt:
- Contract: Parties & subject; Term & termination; Commercials (price/payment); Liability & indemnity; Change-of-control & assignment; IP & licenses; Confidentiality & data; Governing law & disputes; Other.
- Dispute / litigation: Parties & roles; What is asserted; Legal basis; Relief sought; Financial exposure; Deadlines & procedural status; Defenses & counter-arguments; Parallel / related proceedings; Other.
- Regulatory / authority: Authority & matter; Findings; Required actions; Sanctions; Deadlines; Appeal rights.
- For other document types, choose comparable substantive headings.

Each point must include substance + section reference and quote where wording matters.

**Watch-outs & open items**
Only include items not already obvious from the sections above: unusual, one-sided, or high-exposure provisions; missing-but-expected items; and gaps where referenced material was not visible. Each item needs a short quote or description + page/section + one line on why it matters. If none, say so.

Additional rules:
- Same language as contract if clear from evidence; otherwise use English.
- Keep quotes in original language.
- Do not invent missing clauses or numbers.
- Mark deductions "[Inference]".
- Mention processing errors or cross-reference gaps if present.
- Do not list absent standard headings or write "not found" unless the absence is materially surprising for this document type.
""".strip()

    try:
        response = azure_config.client.chat.completions.create(
            model=azure_config.deployment_name,
            messages=[
                {"role": "system", "content": CONTRACT_SCANNER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=1,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[Final synthesis error: {e}]"


def answer_contract_question(
    question: str,
    chunks: List[Dict[str, Any]],
    merged: Dict[str, Any],
    max_context_chars: int = 22000,
) -> str:
    """Answer grounded follow-up questions using keyword-selected chunks and merged evidence."""
    if not azure_config.client:
        return "Azure OpenAI credentials not configured."

    context = _build_question_context(question, chunks, merged, max_context_chars=max_context_chars)
    prompt = f"""
Answer the user's follow-up question using only context below.

Question:
{question}

Context:
{context}

Rules:
- Use same neutral citation discipline as final report.
- Cite clause/section and page when available.
- Include short quotes where wording matters.
- If answer is not found, say "Not found in the provided text".
- Do not speculate.
""".strip()

    try:
        response = azure_config.client.chat.completions.create(
            model=azure_config.deployment_name,
            messages=[
                {"role": "system", "content": CONTRACT_SCANNER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=1,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[Question answering error: {e}]"


def _make_chunk(existing_chunks: List[Dict[str, Any]], pages: List[Dict[str, Any]], source_file: str) -> Dict[str, Any]:
    page_start = pages[0].get("page")
    page_end = pages[-1].get("page")
    text_parts = []
    for page in pages:
        text_parts.append(f"[Page {page.get('page')}]\n{page.get('text', '')}")
    text = "\n\n".join(text_parts)
    return {
        "chunk_id": f"chunk_{len(existing_chunks) + 1:04d}",
        "source_file": source_file,
        "page_start": page_start,
        "page_end": page_end,
        "text": text,
        "char_count": len(text),
        "detected_sections": _detect_sections(text),
    }


def _detect_sections(text: str, limit: int = 30) -> List[str]:
    patterns = [
        r"^\s*(?:Section|Clause|Article)\s+\d+(?:\.\d+)*[^\n]{0,120}",
        r"^\s*\d+(?:\.\d+)+\s+[^\n]{3,120}",
        r"^\s*[A-Z][A-Z\s&/-]{6,120}$",
    ]
    sections = []
    seen = set()
    for line in text.splitlines():
        clean = line.strip()
        if not clean or clean in seen:
            continue
        if any(re.match(pattern, clean) for pattern in patterns):
            sections.append(clean[:160])
            seen.add(clean)
        if len(sections) >= limit:
            break
    return sections


def _parse_json_response(response_text: str) -> Dict[str, Any]:
    text = (response_text or "").strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    elif not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
    return json.loads(text)


def _ensure_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _normalize_evidence_item(item: Any, chunk_id: Any) -> Dict[str, Any]:
    if not isinstance(item, dict):
        item = {"substance": str(item)}
    normalized = dict(item)
    normalized["chunk_id"] = chunk_id
    if "quote" in normalized:
        normalized["quote"] = _trim_quote(str(normalized.get("quote") or ""))
    return normalized


def _trim_quote(quote: str, max_words: int = 25) -> str:
    words = quote.split()
    if len(words) <= max_words:
        return quote
    return " ".join(words[:max_words])


def _dedupe_key(item: Dict[str, Any], fields: List[str]) -> str:
    parts = [str(item.get(field, "")).strip().lower() for field in fields]
    return "|".join(parts)


def _limit_json_chars(payload: Dict[str, Any], max_chars: int) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text

    compact = dict(payload)
    compact["findings_by_category"] = {
        category: findings[:25]
        for category, findings in payload.get("findings_by_category", {}).items()
    }
    compact["red_flags"] = payload.get("red_flags", [])[:80]
    compact["cross_reference_gaps"] = payload.get("cross_reference_gaps", [])[:40]
    compact["evidence_truncated_for_prompt"] = True
    return json.dumps(compact, ensure_ascii=False, indent=2)[:max_chars]


def _build_question_context(
    question: str,
    chunks: List[Dict[str, Any]],
    merged: Dict[str, Any],
    max_context_chars: int,
) -> str:
    terms = [term.lower() for term in re.findall(r"[\w-]{4,}", question)][:12]
    scored_chunks = []
    for chunk in chunks:
        text = str(chunk.get("text", ""))
        lower = text.lower()
        score = sum(lower.count(term) for term in terms)
        if score:
            scored_chunks.append((score, chunk))

    if not scored_chunks:
        scored_chunks = [(0, chunk) for chunk in chunks[:4]]
    else:
        scored_chunks.sort(key=lambda item: item[0], reverse=True)

    evidence = {
        "findings_by_category": merged.get("findings_by_category", {}),
        "red_flags": merged.get("red_flags", []),
        "cross_reference_gaps": merged.get("cross_reference_gaps", []),
    }
    context_parts = ["Merged evidence:", _limit_json_chars(evidence, max_chars=max_context_chars // 2), "Relevant chunks:"]
    used_chars = sum(len(part) for part in context_parts)

    for _, chunk in scored_chunks[:8]:
        chunk_text = (
            f"\n[Chunk {chunk.get('chunk_id')} pages {chunk.get('page_start')}-{chunk.get('page_end')}]\n"
            f"{chunk.get('text', '')}"
        )
        if used_chars + len(chunk_text) > max_context_chars:
            remaining = max_context_chars - used_chars
            if remaining > 1000:
                context_parts.append(chunk_text[:remaining])
            break
        context_parts.append(chunk_text)
        used_chars += len(chunk_text)

    return "\n".join(context_parts)
