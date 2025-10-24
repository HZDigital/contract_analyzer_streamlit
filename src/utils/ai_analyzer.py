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


def group_similar_products(products_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Use AI to group similar products that might be named differently.
    
    Args:
        products_list: List of product dictionaries with 'product_name', 'client_name', etc.
        
    Returns:
        dict: Grouped products with AI-identified similarities
    """
    if not azure_config.client:
        return {"error": "Azure OpenAI not configured"}
    
    if not products_list:
        return {"groups": []}
    
    # Create a simplified list for AI analysis
    products_for_ai = []
    for idx, prod in enumerate(products_list):
        products_for_ai.append({
            "id": idx,
            "product_name": prod.get("product_name", "Unknown"),
            "client": prod.get("client_name", "Unknown")
        })
    
    prompt = f"""You are analyzing product names from different client orders. Group products ONLY if they are EXACTLY the same item with the same specifications.

Products to analyze:
{json.dumps(products_for_ai, indent=2)}

Rules for grouping:
1. **Group ONLY when truly identical**: Products must be the exact same item to be grouped
   - Example: "Steel Rebar 10mm" and "Steel Rebars 10mm" ARE THE SAME (plural/singular, same specs)
   - Example: "Concrete Mix Type A" and "Concrete Mix Type A" ARE THE SAME (identical)
   
2. **Keep separate when specifications differ**:
   - Different dimensions/sizes (e.g., "Werkstoff 1.2436 Ø 212mm" vs "Werkstoff 1.2436 Ø 231mm" are DIFFERENT)
   - Different lengths (e.g., "3000mm" vs "4000mm" are DIFFERENT)
   - Different material grades (e.g., "Werkstoff 1.2436" vs "Werkstoff 1.4301" are DIFFERENT)
   - Different serial/batch numbers (e.g., "Block EDV370287678" vs "Block EDV370382526" are DIFFERENT)
   - Different surface treatments or processing (e.g., "galvanized" vs "polished" are DIFFERENT)
   - Any specification that would make them non-interchangeable products

3. **Ignore only these minor differences** (still group together):
   - Plurals vs singular ("Rebar" vs "Rebars")
   - Extra whitespace or punctuation
   - Capitalization differences
   - Minor typos or abbreviations of the SAME product

4. **For the canonical name**: Use the most common or complete version from the group

Return a JSON object with this structure:
{{
    "groups": [
        {{
            "product_ids": [0, 3, 7],
            "canonical_name": "The best representative name for this group"
        }}
    ]
}}

Only include groups that have products from 2 or more different clients.
Only return the JSON, no other text."""

    try:
        response = azure_config.client.chat.completions.create(
            model=azure_config.deployment_name,
            messages=[
                {"role": "system", "content": "You are a product categorization expert."},
                {"role": "user", "content": prompt}
            ],
            temperature=1,
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Clean up response to extract JSON
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].strip()
        
        result = json.loads(response_text)
        
        # Validate that groups have products from 2+ different clients
        validated_groups = []
        for group in result.get("groups", []):
            product_ids = group.get("product_ids", [])
            clients = set()
            for pid in product_ids:
                if 0 <= pid < len(products_list):
                    clients.add(products_list[pid].get("client_name"))
            
            if len(clients) >= 2:
                validated_groups.append(group)
        
        return {"groups": validated_groups}
        
    except Exception as e:
        return {"error": str(e), "groups": []}