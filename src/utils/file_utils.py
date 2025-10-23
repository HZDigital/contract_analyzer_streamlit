"""
File handling utilities for saving analysis results.
"""

import os
import json
import csv
import io
import time
from typing import Any, Dict


def save_analysis_result(file_name: str, content: Any) -> str:
    """
    Save analysis results to a text file.
    
    Args:
        file_name: Name of the original file
        content: Analysis content to save
        
    Returns:
        str: Path to the saved file
    """
    folder = "results"
    os.makedirs(folder, exist_ok=True)
    full_path = os.path.join(folder, f"result_{file_name}.txt")
    
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    return full_path


def save_bulk_results(results: list) -> str:
    """
    Save bulk processing results to a JSON file.
    
    Args:
        results: List of processing results
        
    Returns:
        str: Path to the saved JSON file
    """
    folder = "results"
    os.makedirs(folder, exist_ok=True)
    
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    filename = f"bulk_analysis_results_{timestamp}.json"
    full_path = os.path.join(folder, filename)
    
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    
    return full_path


def generate_json_download_data(results: list) -> str:
    """
    Generate JSON data for download.
    
    Args:
        results: List of processing results
        
    Returns:
        str: JSON formatted string
    """
    return json.dumps(results, indent=2)


def generate_download_filename() -> str:
    """
    Generate a timestamped filename for downloads.
    
    Returns:
        str: Formatted filename
    """
    return f"contract_analysis_results_{time.strftime('%Y%m%d_%H%M%S')}.json"


def generate_detailed_csv_download_data(results: list) -> bytes:
    """
    Generate detailed CSV data with each product on a separate row.
    Properly handles German characters and umlauts with UTF-8 BOM encoding.
    
    Args:
        results: List of processing results
        
    Returns:
        bytes: CSV formatted bytes with UTF-8 BOM encoding for proper German character support
    """
    if not results:
        return b""
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    # Write header
    headers = [
        'File Name', 'Status', 'Client Name', 'Contract Type', 'Product/Service Name', 'Quantity', 
        'Unit', 'Description', 'Error'
    ]
    writer.writerow(headers)
    
    # Write data rows
    for result in results:
        if result["status"] == "success":
            products = result.get("products", [])
            
            if products:
                # Create a row for each product
                for product in products:
                    row = [
                        result.get("file_name", ""),
                        result.get("status", ""),
                        result.get("client_name", ""),
                        result.get("contract_type", ""),
                        product.get("product_name", "Unknown"),
                        product.get("quantity", "Not specified"),
                        product.get("unit", ""),
                        product.get("description", "Not specified"),
                        result.get("error", "")
                    ]
                    writer.writerow(row)
            else:
                # No products detected, create one row with empty product fields
                row = [
                    result.get("file_name", ""),
                    result.get("status", ""),
                    result.get("client_name", ""),
                    result.get("contract_type", ""),
                    "No products detected",
                    "",
                    "",
                    "",
                    result.get("error", "")
                ]
                writer.writerow(row)
        else:
            # Failed processing
            row = [
                result.get("file_name", ""),
                result.get("status", ""),
                "", "", "", "", "", "",
                result.get("error", "")
            ]
            writer.writerow(row)
    
    # Get CSV content and encode with UTF-8 BOM for proper German character support
    csv_content = output.getvalue()
    output.close()
    
    # Add UTF-8 BOM to ensure proper character encoding in Excel
    return '\ufeff'.encode('utf-8') + csv_content.encode('utf-8')


def generate_detailed_analysis_csv(analysis_results: list) -> bytes:
    """
    Generate CSV data for detailed analysis results.
    Properly handles German characters and umlauts with UTF-8 BOM encoding.
    
    Args:
        analysis_results: List of detailed analysis results
        
    Returns:
        bytes: CSV formatted bytes with UTF-8 BOM encoding for proper German character support
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    
    # Write header
    headers = [
        'File Name', 'Status', 'Client Name', 'Contract Type', 
        'Start Date', 'End Date', 'Summary', 'Product/Service Name',
        'Description', 'Quantity', 'Unit', 'Rate', 'Error'
    ]
    writer.writerow(headers)
    
    # Write data rows
    for result in analysis_results:
        base_info = [
            result.get("file_name", ""),
            "success" if result.get("success", False) else "failed",
        ]
        
        if result.get("success", False) and isinstance(result.get("analysis"), dict):
            analysis = result["analysis"]
            
            # Extract basic contract info
            basic_info = [
                analysis.get("client_name", ""),
                analysis.get("contract_type", ""),
                analysis.get("start_date", ""),
                analysis.get("end_date", ""),
                analysis.get("summary", "")
            ]
            
            # Handle products/services
            products_services = analysis.get("products_services", [])
            if products_services:
                for product in products_services:
                    row = base_info + basic_info + [
                        product.get("name", ""),
                        product.get("description", ""),
                        product.get("quantity", ""),
                        product.get("unit", ""),
                        product.get("rate", ""),
                        ""  # No error
                    ]
                    writer.writerow(row)
            else:
                # No products, just basic info
                row = base_info + basic_info + ["", "", "", "", "", ""]
                writer.writerow(row)
        else:
            # Failed analysis
            row = base_info + ["", "", "", "", "", "", "", "", "", "", 
                              result.get("error", "Analysis failed")]
            writer.writerow(row)
    
    # Get CSV content and encode with UTF-8 BOM for proper German character support
    csv_content = output.getvalue()
    output.close()
    
    # Add UTF-8 BOM to ensure proper character encoding in Excel
    return '\ufeff'.encode('utf-8') + csv_content.encode('utf-8')