"""
Use Case 2 - Contract review of cooperation agreements.

This page lets users:
- Upload cooperation agreements (proposals from suppliers)
- Upload or use a standard MVS contract template for comparison
- AI performs comprehensive contract review
- Identifies deviations, risks, and obligations
- Highlights relevant sections
- Generates detailed review report with recommendations
"""

import json
from io import BytesIO
import streamlit as st
import pandas as pd
from datetime import datetime

from config.settings import azure_config
from utils.pdf_processor import extract_text_from_pdf, extract_text_from_file
from utils.ai_analyzer import analyze_cooperation_agreement, compare_contracts


def render_contract_review_cooperation_page():
    """Render the contract review of cooperation agreements page."""
    
    st.title("Contract Review - Cooperation Agreements")
    st.markdown(
        """
        **AI-powered contract review and comparison:**
        - Upload cooperation agreement proposals from suppliers
        - Compare against MVS standard contract
        - Identify deviations and risks
        - Get detailed analysis and recommendations
        """
    )
    
    azure_config.show_credentials_warning()
    st.markdown("---")

    col1, col2 = st.columns(2)
    
    with col1:
        # Supplier agreement files (multiple)
        supplier_agreements = st.file_uploader(
            "Upload one or more cooperation agreement proposals",
            type=["pdf", "docx", "doc"],
            accept_multiple_files=True,
            key="supplier_agreements_upload",
            help="Upload multiple cooperation agreement files (PDF, DOCX, DOC). All will be analyzed and compared against the standard contract."
        )

    with col2:
        # Standard contract upload (mandatory)
        standard_contract = st.file_uploader(
            "Upload MVS standard contract (PDF)",
            type=["pdf"],
            key="standard_contract_upload",
            help="Upload your standard MVS contract template for comparison. This is required."
        )
    
    # Analysis button
    run_analysis = st.button(
        "Analyze & Compare Contracts",
        width="stretch",
    )
    
    if run_analysis:
        # Validate inputs
        if not standard_contract:
            st.error("❌ Standard MVS contract is required. Please upload it.")
            return
        
        if not supplier_agreements:
            st.error("❌ Please upload at least one supplier cooperation agreement.")
            return
        
        # Extract standard contract text
        standard_text = extract_text_from_pdf(standard_contract)
        
        # Extract and merge all supplier agreement texts
        supplier_texts = []
        supplier_file_names = []
        
        progress = st.progress(0.0)
        status_placeholder = st.empty()
        
        for idx, supplier_file in enumerate(supplier_agreements):
            status_placeholder.info(f"Processing {supplier_file.name}...")
            supplier_text = extract_text_from_file(supplier_file, supplier_file.name)
            supplier_texts.append(supplier_text)
            supplier_file_names.append(supplier_file.name)
            progress.progress((idx + 1) / len(supplier_agreements))
        
        # Merge all supplier texts
        merged_supplier_text = "\n\n--- Document Separator ---\n\n".join(supplier_texts)
        
        # Show processing indicator
        status_placeholder.info("Analyzing contracts...")
        with st.spinner("Analyzing all documents against standard contract..."):
            analysis_result = compare_contracts(
                merged_supplier_text,
                standard_text,
                include_risk_assessment=include_risk_assessment,
                include_deviation_analysis=include_deviation_analysis,
                include_recommendations=include_recommendations
            )
        
        # Store result in session
        st.session_state["cooperation_agreement_analysis"] = analysis_result
        st.session_state["supplier_agreement_names"] = supplier_file_names
        st.session_state["standard_contract_name"] = standard_contract.name
        status_placeholder.success("✅ Analysis completed successfully!")
    
    # Display results if available
    analysis_result = st.session_state.get("cooperation_agreement_analysis")
    
    if analysis_result:
        _display_analysis_results(analysis_result)


def _display_analysis_results(analysis_result):
    """Display the analysis results in organized tabs."""
    
    st.markdown("---")
    st.header("📊 Analysis Results")
    
    # Create tabs for different sections
    tabs = st.tabs([
        "📋 Summary",
        "🔍 Deviations",
        "⚠️ Risks",
        "📝 Clauses",
        "💡 Recommendations",
    ])
    
    with tabs[0]:  # Summary tab
        _display_summary(analysis_result)
    
    with tabs[1]:  # Deviations tab
        _display_deviations(analysis_result)
    
    with tabs[2]:  # Risks tab
        _display_risks(analysis_result)
    
    with tabs[3]:  # Clauses tab
        _display_clauses(analysis_result)
    
    with tabs[4]:  # Recommendations tab
        _display_recommendations(analysis_result)
    
    # Export options
    st.markdown("---")
    st.subheader("📥 Export Results")
    
    data_rows = []
    
    # Add deviations
    for dev in analysis_result.get("deviations", []):
        data_rows.append({
            "Type": "Deviation",
            "Title": dev.get("title", ""),
            "Severity": dev.get("severity", ""),
            "Impact": dev.get("impact", ""),
            "Details": dev.get("description", "")
        })
    
    # Add risks
    for risk in analysis_result.get("risks", []):
        data_rows.append({
            "Type": "Risk",
            "Title": risk.get("title", ""),
            "Severity": risk.get("severity", ""),
            "Category": risk.get("category", ""),
            "Details": risk.get("description", "")
        })
    
    # Add recommendations
    for rec in analysis_result.get("recommendations", []):
        data_rows.append({
            "Type": "Recommendation",
            "Title": rec.get("action", ""),
            "Priority": rec.get("priority", ""),
            "Details": rec.get("rationale", ""),
            "Details": ""
        })
    
    if data_rows:
        df = pd.DataFrame(data_rows)
        csv_str = df.to_csv(index=False, sep=";").encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=csv_str,
            file_name=f"contract_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )


def _display_summary(analysis_result):
    """Display summary section."""
    summary = analysis_result.get("summary", {})
    
    st.markdown("### Contract Overview")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Contract Type", summary.get("contract_type", "Not identified"))
        st.metric("Parties", summary.get("parties", "Not identified"))
    
    with col2:
        st.metric("Duration", summary.get("duration", "Not specified"))
        st.metric("Status", summary.get("status", "Unknown"))
    
    if summary.get("description"):
        st.markdown("### Description")
        st.write(summary.get("description"))


def _display_deviations(analysis_result):
    """Display deviations from standard contract."""
    deviations = analysis_result.get("deviations", [])
    
    if not deviations:
        st.info("✅ No significant deviations found from the standard contract.")
        return
    
    st.subheader(f"🔍 Found {len(deviations)} Deviation(s)")
    
    for idx, deviation in enumerate(deviations, 1):
        with st.expander(f"**Deviation {idx}: {deviation.get('title', 'Unknown')}**", expanded=False):
            
            col1, col2 = st.columns([1, 1])
            with col1:
                st.markdown("**Standard Contract:**")
                st.code(deviation.get("standard", "Not specified"))
            
            with col2:
                st.markdown("**Supplier Agreement:**")
                st.code(deviation.get("supplier", "Not specified"))
            
            st.markdown("**Impact:**")
            st.write(deviation.get("impact", "Not specified"))
            
            severity = deviation.get("severity", "medium").lower()
            if severity == "high":
                st.error(f"🔴 High Severity")
            elif severity == "medium":
                st.warning(f"🟡 Medium Severity")
            else:
                st.info(f"🟢 Low Severity")


def _display_risks(analysis_result):
    """Display identified risks."""
    risks = analysis_result.get("risks", [])
    
    if not risks:
        st.info("✅ No significant risks identified.")
        return
    
    st.subheader(f"⚠️ Identified {len(risks)} Risk(s)")
    
    # Risk summary
    high_risks = sum(1 for r in risks if r.get("severity", "").lower() == "high")
    medium_risks = sum(1 for r in risks if r.get("severity", "").lower() == "medium")
    low_risks = sum(1 for r in risks if r.get("severity", "").lower() == "low")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("🔴 High Risk", high_risks)
    col2.metric("🟡 Medium Risk", medium_risks)
    col3.metric("🟢 Low Risk", low_risks)
    
    st.markdown("---")
    
    # Display risks by severity
    for severity_level, color, emoji in [("high", "error", "🔴"), ("medium", "warning", "🟡"), ("low", "info", "🟢")]:
        severity_risks = [r for r in risks if r.get("severity", "").lower() == severity_level]
        
        if severity_risks:
            st.markdown(f"### {emoji} {severity_level.upper()} SEVERITY RISKS")
            
            for idx, risk in enumerate(severity_risks, 1):
                with st.expander(f"**Risk {idx}: {risk.get('title', 'Unknown')}**", expanded=(severity_level == "high")):
                    st.write(f"**Category:** {risk.get('category', 'Unknown')}")
                    st.write(f"**Description:** {risk.get('description', 'No description')}")
                    
                    if risk.get("affected_section"):
                        st.write(f"**Affected Section:** {risk.get('affected_section')}")
                    
                    if risk.get("quote"):
                        st.markdown("**Relevant Text:**")
                        st.code(risk.get("quote"))
                    
                    if risk.get("recommendation"):
                        st.markdown("**Recommendation:**")
                        st.info(risk.get("recommendation"))


def _display_clauses(analysis_result):
    """Display key clauses analysis."""
    clauses = analysis_result.get("key_clauses", [])
    
    if not clauses:
        st.info("No key clauses identified.")
        return
    
    st.subheader(f"📝 Key Clauses ({len(clauses)} identified)")
    
    for idx, clause in enumerate(clauses, 1):
        with st.expander(f"**Clause {idx}: {clause.get('type', 'Unknown')}**"):
            st.write(f"**Description:** {clause.get('description', 'No description')}")
            
            if clause.get("quote"):
                st.markdown("**Text:**")
                st.code(clause.get("quote"))
            
            if clause.get("importance"):
                importance = clause.get("importance", "medium").lower()
                if importance == "critical":
                    st.error("🔴 CRITICAL")
                elif importance == "high":
                    st.warning("🟡 HIGH")
                else:
                    st.info("🟢 STANDARD")


def _display_recommendations(analysis_result):
    """Display recommendations."""
    recommendations = analysis_result.get("recommendations", [])
    
    if not recommendations:
        st.info("✅ No additional recommendations at this time.")
        return
    
    st.subheader(f"💡 Recommendations ({len(recommendations)} items)")
    
    for idx, rec in enumerate(recommendations, 1):
        priority = rec.get("priority", "medium").lower()
        
        if priority == "high":
            st.error(f"🔴 HIGH PRIORITY - Recommendation {idx}")
        elif priority == "medium":
            st.warning(f"🟡 MEDIUM PRIORITY - Recommendation {idx}")
        else:
            st.info(f"🟢 LOW PRIORITY - Recommendation {idx}")
        
        st.write(f"**Action:** {rec.get('action', 'No action specified')}")
        
        if rec.get("rationale"):
            st.caption(f"**Rationale:** {rec.get('rationale')}")
        
        st.markdown("---")