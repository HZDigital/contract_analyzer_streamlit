"""
AI analysis utilities using Azure OpenAI for contract processing.
"""

import json
from typing import Dict, List, Any
from config.settings import azure_config


def analyze_contract(text: str, truncate_length: int) -> Dict[str, Any]:
    """
    Perform detailed contract analysis using Azure OpenAI.
    
    Args:
        text: Contract text to analyze
        truncate_length: Maximum length of text to send to AI
        
    Returns:
        dict: Structured analysis results
    """
    if not azure_config.client:
        return {
            "error": "❌ Azure OpenAI credentials not configured. "
                    "Please set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT environment variables."
        }

    prompt = f"""
You are a legal assistant. Analyze the following contract and provide information in a structured JSON format.

Analyze the contract and return a JSON object with the following structure:
{{
    "summary": "Brief summary of what the contract is about",
    "client_name": "Name of the client/customer",
    "contract_type": "Type of contract or service agreement",
    "start_date": "Contract start date if mentioned",
    "end_date": "Contract end/termination date if mentioned",
    "products_services": [
        {{
            "name": "Product or service name",
            "description": "Description of the product/service",
            "quantity": "Quantity if specified",
            "unit": "Unit of measurement if applicable",
            "rate": "Rate or price if mentioned"
        }}
    ],
    "key_clauses": [
        {{
            "type": "Clause type (e.g., Termination, Confidentiality, Payment, Liability)",
            "description": "Brief description of the clause",
            "quote": "Direct quote from the contract text"
        }}
    ],
    "risk_areas": [
        {{
            "concern": "Description of the risky or unusual aspect",
            "quote": "Direct quote from the contract text"
        }}
    ]
}}

Contract Text:
{text[:truncate_length]}  # Truncate for token limits
    """

    try:
        response = azure_config.client.chat.completions.create(
            model=azure_config.deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=1  # Lower temperature for more consistent extraction
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Clean up response to extract JSON if it's wrapped in markdown
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].strip()
            
        return json.loads(response_text)
    except Exception as e:
        # Fallback if JSON parsing fails
        return {
            "error": f"❌ Error analyzing contract: {str(e)}",
            "summary": "Analysis failed",
            "client_name": "Unknown",
            "contract_type": "Unknown",
            "start_date": "Not specified",
            "end_date": "Not specified",
            "products_services": [],
            "key_clauses": [],
            "risk_areas": []
        }


def extract_client_and_products(text: str) -> Dict[str, Any]:
    """
    Extract client name, products and amounts from contract text using LLM.
    
    Args:
        text: Contract text to analyze
        
    Returns:
        dict: Extracted information in structured format
    """
    if not azure_config.client:
        return {
            "client_name": "❌ Credentials not configured",
            "products": [],
            "contract_type": "❌ Credentials not configured",
            "error": "Azure OpenAI credentials not configured"
        }
    
    prompt = f"""
Analyze the following contract text and extract the following information in JSON format:

1. Client name (the company/organization requesting materials or services)
2. Products or materials being requested (list each item)
3. Quantities/amounts for each product (with units if specified)
4. Contract type or nature of the agreement

If a product repeats multiple times, please insert everz single one of them as separate entry in the products list.

Return the response as a valid JSON object with the following structure:
{{
    "client_name": "string",
    "products": [
        {{
            "product_name": "string",
            "quantity": "string",
            "unit": "string",
            "description": "string"
        }}
    ],
    "contract_type": "string",
}}

If any information is not clearly specified, use "Not specified" as the value.

Contract Text:
{text}  # Limit text for efficiency
    """
    
    try:
        response = azure_config.client.chat.completions.create(
            model=azure_config.deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,  # Lower temperature for more consistent extraction
            
        )
        
        # Try to parse JSON response
        response_text = response.choices[0].message.content.strip()
        
        # Clean up response to extract JSON if it's wrapped in markdown
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].strip()
            
        return json.loads(response_text)
    except Exception as e:
        # Fallback if JSON parsing fails
        return {
            "client_name": "Extraction failed",
            "products": [],
            "contract_type": "Unknown",
            "total_estimated_value": "Not specified",
            "error": str(e)
        }