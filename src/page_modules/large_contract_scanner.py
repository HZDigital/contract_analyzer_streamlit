"""
Large Contract Scanner for long PDF contracts.
"""

import json
import time
from datetime import datetime

import streamlit as st

from config.settings import azure_config
from utils.large_contract_analyzer import (
    analyze_contract_chunks,
    answer_contract_question,
    build_contract_chunks,
    merge_chunk_findings,
    synthesize_contract_analysis,
)
from utils.pdf_processor import extract_pdf_pages


SESSION_KEY = "large_contract_scanner_result"


def render_large_contract_scanner_page():
    """Render large-contract scanner page."""

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("← Back to Dashboard", width="stretch"):
            st.session_state.current_page = "dashboard"
            st.rerun()

    st.header("Large_Contract_Scanner")
    st.markdown(
        "Upload one long PDF contract. The scanner extracts page-level text, analyzes chunks, "
        "merges evidence, then produces a cited due-diligence report."
    )

    if not azure_config.is_configured:
        azure_config.show_credentials_warning()

    uploaded_file = st.file_uploader(
        "Upload large contract PDF",
        type=["pdf"],
        accept_multiple_files=False,
        key="large_contract_pdf_upload",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        max_chars = st.slider(
            "Chunk size (characters)",
            min_value=8000,
            max_value=30000,
            value=18000,
            step=1000,
            help="Larger chunks preserve context but cost more tokens per call.",
        )
    with col2:
        overlap_pages = st.slider(
            "Overlap pages",
            min_value=0,
            max_value=3,
            value=1,
            help="Repeats trailing pages in next chunk to reduce cross-page clause splits.",
        )
    with col3:
        is_complete_document = st.checkbox(
            "Uploaded PDF is complete contract",
            value=True,
            help="Turn off when uploading only excerpted pages or partial contract text.",
        )

    analyze_clicked = st.button(
        "Run large contract scan",
        type="primary",
        disabled=uploaded_file is None or not azure_config.is_configured,
        width="stretch",
    )

    if analyze_clicked and uploaded_file is not None:
        _run_large_contract_scan(uploaded_file, max_chars, overlap_pages, is_complete_document)

    result = st.session_state.get(SESSION_KEY)
    if result:
        _display_large_contract_result(result)


def _run_large_contract_scan(uploaded_file, max_chars: int, overlap_pages: int, is_complete_document: bool):
    started_at = time.time()
    status = st.empty()

    with status:
        with st.spinner("Extracting page-level PDF text..."):
            pages = extract_pdf_pages(uploaded_file)

    error_pages = [page for page in pages if page.get("extraction_method") == "error"]
    readable_pages = [page for page in pages if str(page.get("text", "")).strip()]
    if error_pages and not readable_pages:
        st.error(error_pages[0].get("text", "PDF extraction failed."))
        return
    if not readable_pages:
        st.error("No readable text found in this PDF.")
        return

    with status:
        with st.spinner("Building analysis chunks..."):
            chunks = build_contract_chunks(
                pages,
                source_file=uploaded_file.name,
                max_chars=max_chars,
                overlap_pages=overlap_pages,
            )

    if not chunks:
        st.error("No analyzable chunks were created from this PDF.")
        return

    st.info(f"Prepared {len(chunks)} chunks from {len(readable_pages)} readable pages.")
    progress = st.progress(0)
    progress_text = st.empty()

    def update_progress(done: int, total: int, result: dict):
        progress.progress(done / total)
        if result.get("error"):
            progress_text.warning(f"Chunk {done}/{total} finished with error: {result.get('error')}")
        else:
            progress_text.write(f"Analyzed chunk {done}/{total}")

    with st.spinner("Analyzing chunks with Azure OpenAI..."):
        chunk_results = analyze_contract_chunks(chunks, progress_callback=update_progress)

    with status:
        with st.spinner("Merging evidence and synthesizing final report..."):
            merged = merge_chunk_findings(chunk_results, chunks)
            report = synthesize_contract_analysis(merged, is_complete_document=is_complete_document)

    progress.empty()
    progress_text.empty()
    status.success("Large contract scan complete")

    st.session_state[SESSION_KEY] = {
        "file_name": uploaded_file.name,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": round(time.time() - started_at, 1),
        "pages": pages,
        "chunks": chunks,
        "chunk_results": chunk_results,
        "merged": merged,
        "report": report,
        "settings": {
            "max_chars": max_chars,
            "overlap_pages": overlap_pages,
            "is_complete_document": is_complete_document,
        },
    }


def _display_large_contract_result(result: dict):
    st.markdown("---")
    st.subheader("Contract Scanner Report")

    merged = result.get("merged", {})
    red_flags = merged.get("red_flags", [])
    findings_count = sum(len(items) for items in merged.get("findings_by_category", {}).values())
    errors = merged.get("errors", [])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Pages", len(result.get("pages", [])))
    col2.metric("Chunks", len(result.get("chunks", [])))
    col3.metric("Findings", findings_count)
    col4.metric("Red flags", len(red_flags))

    if errors:
        st.warning(f"{len(errors)} chunk(s) had processing errors. See Evidence JSON for details.")

    st.markdown(result.get("report", ""))

    _render_downloads(result)
    _render_result_tabs(result)


def _render_downloads(result: dict):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = _safe_base_name(result.get("file_name", "large_contract"))
    evidence = {
        "file_name": result.get("file_name"),
        "created_at": result.get("created_at"),
        "duration_seconds": result.get("duration_seconds"),
        "settings": result.get("settings"),
        "merged": result.get("merged"),
        "chunk_results": result.get("chunk_results"),
    }

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "Download report (Markdown)",
            data=result.get("report", ""),
            file_name=f"{base_name}_contract_scanner_{timestamp}.md",
            mime="text/markdown",
            width="stretch",
        )
    with col2:
        st.download_button(
            "Download evidence (JSON)",
            data=json.dumps(evidence, ensure_ascii=False, indent=2),
            file_name=f"{base_name}_contract_scanner_evidence_{timestamp}.json",
            mime="application/json",
            width="stretch",
        )


def _render_result_tabs(result: dict):
    tab1, tab2, tab3 = st.tabs(["Evidence", "Chunks", "Q&A"])

    with tab1:
        st.json(result.get("merged", {}))

    with tab2:
        for chunk in result.get("chunks", []):
            title = f"{chunk.get('chunk_id')} | pages {chunk.get('page_start')}-{chunk.get('page_end')} | {chunk.get('char_count')} chars"
            with st.expander(title):
                sections = chunk.get("detected_sections") or []
                if sections:
                    st.markdown("**Detected section markers**")
                    st.write(sections)
                st.text_area(
                    "Chunk text",
                    value=chunk.get("text", ""),
                    height=260,
                    key=f"chunk_text_{chunk.get('chunk_id')}",
                )

    with tab3:
        _render_question_answering(result)


def _render_question_answering(result: dict):
    st.markdown("Ask follow-up questions. Answers use stored chunks and merged evidence only.")
    question = st.text_input(
        "Question about this contract",
        key="large_contract_question",
        placeholder="Example: What are the termination rights?",
    )
    if st.button("Answer question", disabled=not question.strip(), width="stretch"):
        with st.spinner("Answering from contract evidence..."):
            answer = answer_contract_question(
                question,
                result.get("chunks", []),
                result.get("merged", {}),
            )
        st.session_state["large_contract_last_answer"] = answer

    if st.session_state.get("large_contract_last_answer"):
        st.markdown("**Answer**")
        st.markdown(st.session_state["large_contract_last_answer"])


def _safe_base_name(file_name: str) -> str:
    base = file_name.rsplit(".", 1)[0]
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in base)[:80]
