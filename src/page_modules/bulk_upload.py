"""
Bulk upload and detection page for contract analyzer.
"""

import streamlit as st
import pandas as pd
import time
from utils.pdf_processor import extract_text_from_pdf
from utils.ai_analyzer import extract_client_and_products, group_similar_products
from utils.file_utils import  generate_detailed_csv_download_data


def render_bulk_upload_page():
    """Render the bulk upload and detection page."""
    # Back button
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("← Back to Dashboard", width="stretch"):
            st.session_state.current_page = "dashboard"
            st.rerun()
    
    st.title("Product Request Detection")
    
    st.markdown("""
    Upload multiple contract files to automatically detect:
    - 🏢 **Client Names** - Who is requesting materials/services
    - 📦 **Product Types** - What materials or services are being requested  
    - 📊 **Quantities** - How much of each product/service
    """)
    
    # File uploader for multiple files
    uploaded_files = st.file_uploader(
        "Upload contract PDFs for bulk processing", 
        type=["pdf"], 
        accept_multiple_files=True,
        help="Select multiple PDF files to process them all at once"
    )
    
    if uploaded_files:
        st.success(f"📁 {len(uploaded_files)} files uploaded successfully!")
        
        # Process all files button
        if st.button("🚀 Process All Files", type="primary"):
            _process_bulk_files(uploaded_files)
    
    # Display results if they exist
    if 'bulk_results' in st.session_state and st.session_state.bulk_results:
        _display_bulk_results()


def _process_bulk_files(uploaded_files):
    """Process multiple files for bulk analysis."""
    # Initialize results storage
    if 'bulk_results' not in st.session_state:
        st.session_state.bulk_results = []
    
    st.session_state.bulk_results = []  # Reset results
    st.session_state.consolidated_results = []  # Reset consolidated results
    
    # Progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Step 1: Process all files
    for i, file in enumerate(uploaded_files):
        # Update progress
        progress = (i + 1) / len(uploaded_files)
        progress_bar.progress(progress * 0.7)  # Use 70% of progress bar for file processing
        status_text.text(f"Processing {file.name}... ({i+1}/{len(uploaded_files)})")
        
        try:
            # Extract text from PDF
            text = extract_text_from_pdf(file)
            
            if not text.strip():
                result = {
                    "file_name": file.name,
                    "status": "failed",
                    "error": "No readable text found in PDF"
                }
            else:
                # Extract client and product information
                extracted_data = extract_client_and_products(text)
                
                result = {
                    "file_name": file.name,
                    "status": "success",
                    "client_name": extracted_data.get("client_name", "Not detected"),
                    "products": extracted_data.get("products", []),
                    "contract_type": extracted_data.get("contract_type", "Unknown"),
                    "total_estimated_value": extracted_data.get("total_estimated_value", "Not specified"),
                    "error": extracted_data.get("error", None)
                }
            
            st.session_state.bulk_results.append(result)
            
        except Exception as e:
            result = {
                "file_name": file.name,
                "status": "failed",
                "error": str(e)
            }
            st.session_state.bulk_results.append(result)
    
    # Step 2: Run AI grouping for consolidated results
    progress_bar.progress(0.7)
    status_text.text("Analyzing products for similarities...")
    
    # Gather all products with client info
    product_db = []
    for result in st.session_state.bulk_results:
        if result["status"] == "success" and result.get("products"):
            for prod in result["products"]:
                product_db.append({
                    "product_name": prod.get("product_name", "Unknown"),
                    "quantity": prod.get("quantity", "Not specified"),
                    "unit": prod.get("unit", ""),
                    "client_name": result.get("client_name", "Not detected"),
                    "contract_type": result.get("contract_type", "Unknown"),
                    "description": prod.get("description", "Not specified"),
                })
    
    if product_db:
        ai_result = group_similar_products(product_db)
        
        if "error" not in ai_result:
            # Build consolidated rows from AI groups
            for group in ai_result.get("groups", []):
                product_ids = group.get("product_ids", [])
                canonical_name = group.get("canonical_name", "Unknown Product")
                
                # Get unique clients for this group
                unique_clients = {}
                for pid in product_ids:
                    if 0 <= pid < len(product_db):
                        prod = product_db[pid]
                        cname = prod["client_name"]
                        if cname not in unique_clients:
                            unique_clients[cname] = {
                                "quantity": prod["quantity"],
                                "unit": prod["unit"],
                                "contract_type": prod["contract_type"],
                                "product_name": prod["product_name"]
                            }
                
                if len(unique_clients) >= 2:
                    row = {"Product": canonical_name}
                    
                    for idx, (cname, info) in enumerate(unique_clients.items(), 1):
                        quantity_str = f"{info['quantity']} {info['unit']}".strip()
                        row[f"Client {idx}"] = cname
                        row[f"Original Name {idx}"] = info["product_name"]
                        row[f"Quantity {idx}"] = quantity_str
                        row[f"Type {idx}"] = info["contract_type"]
                    
                    st.session_state.consolidated_results.append(row)
    
    progress_bar.progress(1.0)
    status_text.text("✅ Processing and analysis complete!")


def _display_bulk_results():
    """Display the results of bulk processing in a table format."""
    st.markdown("---")
    st.markdown("## 📋 Processing Results")
    
    # Summary statistics
    total_files = len(st.session_state.bulk_results)
    successful_files = len([r for r in st.session_state.bulk_results if r["status"] == "success"])
    failed_files = total_files - successful_files
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Files", total_files)
    with col2:
        st.metric("Successfully Processed", successful_files)
    with col3:
        st.metric("Failed Processing", failed_files)
    
    # Create DataFrame for table display
    table_data = []
    for result in st.session_state.bulk_results:
        if result["status"] == "success":
            # Create products summary for table
            products = result.get("products", [])
            products_summary = ", ".join([
                f"{p.get('product_name', 'Unknown')}"
                for p in products[:3]  # Show first 3 products
            ]) if products else "No products detected"
            
            # Add "..." if there are more than 3 products
            if len(products) > 3:
                products_summary += f" ... (+{len(products)-3} more)"
            
            table_data.append({
                "File Name": result["file_name"],
                "Status": "✅ Success",
                "Client Name": result.get("client_name", "Not detected"),
                "Contract Type": result.get("contract_type", "Unknown"),
                "Products Count": len(products),
                "Products": products_summary,
                "Estimated Value": result.get("total_estimated_value", "Not specified"),
                "Error": result.get("error", "")
            })
        else:
            table_data.append({
                "File Name": result["file_name"],
                "Status": "❌ Failed",
                "Client Name": "",
                "Contract Type": "",
                "Products Count": 0,
                "Products": "",
                "Estimated Value": "",
                "Error": result.get("error", "Unknown error")
            })
    
    _display_detailed_results()

    # --- Consolidated Order List Section ---
    st.markdown("---")
    st.markdown("## 🔄 Consolidated Order List")
    st.caption("Products ordered by 2 or more different clients")

    # Display pre-computed consolidated results
    if 'consolidated_results' in st.session_state and st.session_state.consolidated_results:
        st.dataframe(pd.DataFrame(st.session_state.consolidated_results), width="stretch", hide_index=True)
        st.success(f"✅ Found {len(st.session_state.consolidated_results)} product(s) ordered by multiple clients")
    else:
        st.info("No products were ordered by 2 or more different clients.")

    # Export option
    st.markdown("### 📥 Export Results")
    st.markdown("Choose your preferred export format:")

    col1, col2 = st.columns(2)

    with col1:
        st.caption("One row per product/service found")
        st.download_button(
            label="Download Detailed CSV",
            data=generate_detailed_csv_download_data(st.session_state.bulk_results),
            file_name=f"Product_Request.csv",
            mime="text/csv"
        )


def _display_detailed_results():
    """Display detailed results with expandable sections."""
    for result in st.session_state.bulk_results:
        if result["status"] == "success":
            _display_successful_result(result)
        else:
            _display_failed_result(result)


def _display_successful_result(result):
    """Display a successful processing result."""
    with st.expander(f"✅ {result['file_name']} - Client: {result['client_name']}", expanded=False):
        # Contract Information section
        st.markdown("**📊 Contract Information**")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.write(f"**Client:** {result['client_name']}")
        with col2:
            st.write(f"**Contract Type:** {result['contract_type']}")
        
        st.markdown("---")
        
        # Products/Services table section
        st.markdown("**📦 Products/Services**")
        if result['products']:
            # Create table data for products
            products_table_data = []
            for i, product in enumerate(result['products'], 1):
                products_table_data.append({
                    "#": i,
                    "Product/Service": product.get('product_name', 'Unknown'),
                    "Quantity": f"{product.get('quantity', 'Not specified')} {product.get('unit', '')}".strip(),
                    "Description": product.get('description', 'Not specified')
                })
            
            # Display products as a table
            products_df = pd.DataFrame(products_table_data)
            st.dataframe(
                products_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "#": st.column_config.NumberColumn("#", width="small"),
                    "Product/Service": st.column_config.TextColumn("Product/Service", width="medium"),
                    "Quantity": st.column_config.TextColumn("Quantity", width="medium"),
                    "Description": st.column_config.TextColumn("Description", width="large")
                }
            )
        else:
            st.info("📭 No products or services detected in this contract")
        
        if result.get("error"):
            st.warning(f"⚠️ Extraction warning: {result['error']}")


def _display_failed_result(result):
    """Display a failed processing result."""
    with st.expander(f"❌ {result['file_name']} - Processing Failed", expanded=False):
        st.error(f"**Error:** {result['error']}")
        st.markdown("---")
        st.info("💡 **Troubleshooting tips:**")
        st.markdown("""
        - Ensure the PDF contains readable text (not just images)
        - Check if the file is password protected
        - Verify the file is not corrupted
        - Try re-uploading the file
        """)