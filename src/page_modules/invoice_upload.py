"""
Invoice request detection page that auto-extracts invoice number and company name.
"""

import streamlit as st
import pandas as pd
from utils.pdf_processor import extract_text_from_pdf
from utils.ai_analyzer import extract_client_and_products_from_invoices


def render_invoice_upload_page():
    """Render the invoice detection page."""
    st.title("Invoice Request Detection")
    st.markdown(
        """
        Upload invoice PDF files to detect requested products/services.
        The AI will extract the invoice number and company name for each file.
        """
    )

    uploaded_files = st.file_uploader(
        "Upload invoice PDFs for processing",
        type=["pdf"],
        accept_multiple_files=True,
        help="Select one or more invoices"
    )

    if uploaded_files:
        st.success(f"📁 {len(uploaded_files)} files ready to process")
        if st.button("🚀 Process Invoices", type="primary", key="process_invoices_button"):
            _process_invoice_files(uploaded_files)

    if st.session_state.get("invoice_results"):
        _display_invoice_results()


def _process_invoice_files(uploaded_files) -> None:
    """Process uploaded invoices and store results in session state."""
    st.session_state.invoice_results = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, file in enumerate(uploaded_files):
        progress = (idx + 1) / len(uploaded_files)
        progress_bar.progress(progress * 0.8)
        status_text.text(f"Processing {file.name}... ({idx + 1}/{len(uploaded_files)})")

        try:
            text = extract_text_from_pdf(file)
            if not text.strip():
                st.session_state.invoice_results.append(
                    {
                        "file_name": file.name,
                        "status": "failed",
                        "invoice_number": "Not detected",
                        "company_name": "Not detected",
                        "detected_client": "",
                        "contract_type": "",
                        "products": [],
                    }
                )
                continue

            extracted = extract_client_and_products_from_invoices(text)
            st.session_state.invoice_results.append(
                {
                    "file_name": file.name,
                    "status": "success",
                    "invoice_number": extracted.get("invoice_number", "Not specified"),
                    "invoice_date": extracted.get("invoice_date", "Not specified"),
                    "due_date": extracted.get("due_date", "Not specified"),
                    "currency": extracted.get("currency", "Not specified"),
                    "total_amount": extracted.get("total_amount", "Not specified"),
                    "subtotal": extracted.get("subtotal", "Not specified"),
                    "tax_amount": extracted.get("tax_amount", "Not specified"),
                    "tax_rate_percent": extracted.get("tax_rate_percent", "Not specified"),
                    "payment_terms": extracted.get("payment_terms", "Not specified"),
                    "po_number": extracted.get("po_number", "Not specified"),
                    "supplier_name": extracted.get("supplier_name", extracted.get("company_name", "Not specified")),
                    "supplier_address": extracted.get("supplier_address", "Not specified"),
                    "customer_name": extracted.get("customer_name", extracted.get("client_name", "Not specified")),
                    "customer_address": extracted.get("customer_address", "Not specified"),
                    "ship_to": extracted.get("ship_to", "Not specified"),
                    "tax_id": extracted.get("tax_id", "Not specified"),
                    "contract_type": extracted.get("contract_type", "Unknown"),
                    "products": extracted.get("products", []),
                    "notes": extracted.get("notes", "Not specified"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            st.session_state.invoice_results.append(
                {
                    "file_name": file.name,
                    "status": "failed",
                    "invoice_number": "Not detected",
                    "company_name": "Not detected",
                    "detected_client": "",
                    "contract_type": "",
                    "products": [],
                }
            )

    progress_bar.progress(1.0)
    status_text.text("✅ Invoice processing complete")


def _display_invoice_results() -> None:
    """Show invoice processing summary and details."""
    st.markdown("---")
    st.markdown("## 📋 Invoice Processing Results")

    total = len(st.session_state.invoice_results)
    successes = len([r for r in st.session_state.invoice_results if r["status"] == "success"])
    failures = total - successes

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Files", total)
    with col2:
        st.metric("Successfully Processed", successes)
    with col3:
        st.metric("Failed Processing", failures)

    for result in st.session_state.invoice_results:
        # Wrap each invoice in a bordered container for a card-like look
        with st.container(border=True):
            if result["status"] == "success":
                _display_invoice_success(result)
            else:
                _display_invoice_failure(result)

     # Export option
    st.markdown("### 📥 Export Results")
    st.markdown("Choose your preferred export format:")

    col1, col2 = st.columns(2)

    with col1:
        st.caption("One row per product/service found")
        st.download_button(
            label="Download Invoice Results (CSV)",
            data=_generate_invoice_csv(st.session_state.invoice_results),
            file_name="invoice_results.csv",
            mime="text/csv",
        )

   


def _display_invoice_success(result: dict) -> None:
    """Render a single successful invoice result."""
    with st.expander(f"✅ {result['file_name']} — Invoice {result['invoice_number']}", expanded=False):
        st.markdown("**📊 Invoice Information**")
        info_col1, info_col2, info_col3 = st.columns(3)
        with info_col1:
            st.write(f"**PO #:** {result.get('po_number', 'Not specified')}")
            st.write(f"**Payment Terms:** {result.get('payment_terms', 'Not specified')}")
            st.write(f"**Tax ID:** {result.get('tax_id', 'Not specified')}")
        with info_col2:
            st.write(f"**Subtotal:** {result.get('subtotal', 'Not specified')} {result.get('currency', '')}".strip())
            st.write(f"**Tax Amount:** {result.get('tax_amount', 'Not specified')} {result.get('currency', '')}".strip())
            st.write(f"**Tax %:** {result.get('tax_rate_percent', 'Not specified')}")
        with info_col3:
            st.write(f"**Currency:** {result.get('currency', 'Not specified')}")
            st.write(f"**Contract Type:** {result.get('contract_type', 'Unknown')}")
            st.write(f"**Notes:** {result.get('notes', 'Not specified')}")

        st.markdown("---")
        st.markdown("**🏢 Parties**")
        p1, p2, p3 = st.columns(3)
        with p1:
            st.write("**Supplier (Remit To):**")
            st.write(result.get("supplier_name", "Not specified"))
            st.caption(result.get("supplier_address", ""))
        with p2:
            st.write("**Customer (Bill To):**")
            st.write(result.get("customer_name", "Not specified"))
            st.caption(result.get("customer_address", ""))
        with p3:
            st.write("**Ship To:**")
            st.write(result.get("ship_to", "Not specified"))

        st.markdown("---")
        st.markdown("**📦 Products/Services**")

        products = result.get("products", [])
        if products:
            products_table = []
            for idx, p in enumerate(products, 1):
                products_table.append({
                    "#": idx,
                    "Product/Service": p.get("product_name", "Unknown"),
                    "Description": p.get("description", "Not specified"),
                    "Quantity": f"{p.get('quantity', 'Not specified')} {p.get('unit', '')}".strip(),
                    "Unit Price": p.get("unit_price", "Not specified"),
                    "Line Total": p.get("line_total", "Not specified"),
                    "Currency": p.get("currency", result.get("currency", "")),
                    "Tax %": p.get("tax_rate_percent", result.get("tax_rate_percent", "Not specified")),
                    "SKU/Part #": p.get("sku_or_part_number", "Not specified"),
                })

            products_df = pd.DataFrame(products_table)
            st.dataframe(
                products_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "#": st.column_config.NumberColumn("#", width="small"),
                    "Product/Service": st.column_config.TextColumn("Product/Service", width="medium"),
                    "Description": st.column_config.TextColumn("Description", width="large"),
                    "Quantity": st.column_config.TextColumn("Quantity", width="medium"),
                    "Unit Price": st.column_config.TextColumn("Unit Price", width="medium"),
                    "Line Total": st.column_config.TextColumn("Line Total", width="medium"),
                    "Currency": st.column_config.TextColumn("Currency", width="small"),
                    "Tax %": st.column_config.TextColumn("Tax %", width="small"),
                    "SKU/Part #": st.column_config.TextColumn("SKU/Part #", width="medium"),
                },
            )
        else:
            st.info("📭 No products or services detected in this invoice")

        if result.get("error"):
            st.warning(f"⚠️ Extraction warning: {result['error']}")


def _display_invoice_failure(result: dict) -> None:
    """Render a failed invoice result."""
    with st.expander(f"❌ {result['file_name']} - Processing Failed", expanded=False):
        c1, c2 = st.columns(2)
        c1.metric("Invoice #", result.get("invoice_number", "Not detected"))
        c2.metric("Company", result.get("company_name", "Not detected"))
        st.error(f"**Error:** {result.get('error', 'Unknown error')}")
        st.markdown("---")
        st.info("💡 **Troubleshooting tips:**")
        st.markdown(
            """
            - Ensure the PDF contains readable text (not just images)
            - Check if the file is password protected
            - Verify the file is not corrupted
            - Try re-uploading the file
            """
        )


def _generate_invoice_csv(results: list) -> bytes:
    """Create a CSV export for invoice results."""
    df_rows = []
    for result in results:
        products = result.get("products", []) if result.get("status") == "success" else []
        if products:
            for product in products:
                df_rows.append(
                    {
                        "file_name": result.get("file_name", ""),
                        "invoice_number": result.get("invoice_number", "Not specified"),
                        "invoice_date": result.get("invoice_date", "Not specified"),
                        "due_date": result.get("due_date", "Not specified"),
                        "currency": result.get("currency", "Not specified"),
                        "total_amount": result.get("total_amount", "Not specified"),
                        "subtotal": result.get("subtotal", "Not specified"),
                        "tax_amount": result.get("tax_amount", "Not specified"),
                        "tax_rate_percent": result.get("tax_rate_percent", "Not specified"),
                        "payment_terms": result.get("payment_terms", "Not specified"),
                        "po_number": result.get("po_number", "Not specified"),
                        "supplier_name": result.get("supplier_name", "Not specified"),
                        "supplier_address": result.get("supplier_address", "Not specified"),
                        "customer_name": result.get("customer_name", "Not specified"),
                        "customer_address": result.get("customer_address", "Not specified"),
                        "ship_to": result.get("ship_to", "Not specified"),
                        "tax_id": result.get("tax_id", "Not specified"),
                        "contract_type": result.get("contract_type", "Unknown"),
                        "product_name": product.get("product_name", "Unknown"),
                        "description": product.get("description", "Not specified"),
                        "quantity": product.get("quantity", "Not specified"),
                        "unit": product.get("unit", ""),
                        "unit_price": product.get("unit_price", "Not specified"),
                        "line_total": product.get("line_total", "Not specified"),
                        "item_currency": product.get("currency", result.get("currency", "Not specified")),
                        "item_tax_rate_percent": product.get("tax_rate_percent", result.get("tax_rate_percent", "Not specified")),
                        "sku_or_part_number": product.get("sku_or_part_number", "Not specified"),
                    }
                )
        else:
            df_rows.append(
                {
                    "file_name": result.get("file_name", ""),
                    "invoice_number": result.get("invoice_number", "Not specified"),
                    "invoice_date": result.get("invoice_date", "Not specified"),
                    "due_date": result.get("due_date", "Not specified"),
                    "currency": result.get("currency", "Not specified"),
                    "total_amount": result.get("total_amount", "Not specified"),
                    "subtotal": result.get("subtotal", "Not specified"),
                    "tax_amount": result.get("tax_amount", "Not specified"),
                    "tax_rate_percent": result.get("tax_rate_percent", "Not specified"),
                    "payment_terms": result.get("payment_terms", "Not specified"),
                    "po_number": result.get("po_number", "Not specified"),
                    "supplier_name": result.get("supplier_name", "Not specified"),
                    "supplier_address": result.get("supplier_address", "Not specified"),
                    "customer_name": result.get("customer_name", "Not specified"),
                    "customer_address": result.get("customer_address", "Not specified"),
                    "ship_to": result.get("ship_to", "Not specified"),
                    "tax_id": result.get("tax_id", "Not specified"),
                    "contract_type": result.get("contract_type", "Unknown"),
                    "product_name": "No products detected" if result.get("status") == "success" else "",
                    "description": "",
                    "quantity": "",
                    "unit": "",
                    "unit_price": "",
                    "line_total": "",
                    "item_currency": "",
                    "item_tax_rate_percent": "",
                    "sku_or_part_number": "",
                }
            )

    df = pd.DataFrame(df_rows)
    return df.to_csv(index=False).encode("utf-8-sig")
