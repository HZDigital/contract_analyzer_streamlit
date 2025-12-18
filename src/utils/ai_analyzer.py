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

    try:
        response = azure_config.client.chat.completions.create(
            model=azure_config.deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"\n[AI Extraction Error: {e}]"



def extract_client_and_products_from_invoices(text: str) -> Dict[str, Any]:
    """
    Extract invoice metadata, parties, and product info from text using LLM.
    """
    if not azure_config.client:
        return {
            "client_name": "❌ Credentials not configured",
            "products": [],
            "contract_type": "❌ Credentials not configured",
            "error": "Azure OpenAI credentials not configured"
        }
    
    prompt = f"""
Analyze the following invoice text and return ONLY valid JSON with this structure (use "Not specified" when missing):

{{
    "invoice_number": "string",
    "invoice_date": "string",
    "due_date": "string",
    "currency": "string",
    "total_amount": "string",
    "subtotal": "string",
    "tax_amount": "string",
    "tax_rate_percent": "string",
    "payment_terms": "string",
    "po_number": "string",
    "supplier_name": "string",
    "supplier_address": "string",
    "customer_name": "string",
    "customer_address": "string",
    "ship_to": "string",
    "tax_id": "string",
    "products": [
        {{
            "product_name": "string",
            "description": "string",
            "quantity": "string",
            "unit": "string",
            "unit_price": "string",
            "line_total": "string",
            "currency": "string",
            "tax_rate_percent": "string",
            "sku_or_part_number": "string"
        }}
    ],
    "contract_type": "string",
    "notes": "string"
}}

Rules:
- Preserve currency symbols/codes as in the text.
- Do **not** invent data; use "Not specified" if absent.
- If multiple tax rates or currencies appear, choose the most relevant for totals and note ambiguity in "notes".
- Do not wrap JSON in markdown fences.
- Return every key above even if "Not specified".

Contract Text:
{text}
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
            
        parsed = json.loads(response_text)
        # Ensure required keys exist even if the model omits them
        defaults = {
            "invoice_number": "Not specified",
            "invoice_date": "Not specified",
            "due_date": "Not specified",
            "currency": "Not specified",
            "total_amount": "Not specified",
            "subtotal": "Not specified",
            "tax_amount": "Not specified",
            "tax_rate_percent": "Not specified",
            "payment_terms": "Not specified",
            "po_number": "Not specified",
            "supplier_name": "Not specified",
            "supplier_address": "Not specified",
            "customer_name": "Not specified",
            "customer_address": "Not specified",
            "ship_to": "Not specified",
            "tax_id": "Not specified",
            "contract_type": "Not specified",
            "notes": "Not specified",
            "products": [],
        }
        for k, v in defaults.items():
            parsed.setdefault(k, v)
        normalized_products = []
        for item in parsed.get("products", []):
            item_defaults = {
                "product_name": "Not specified",
                "description": "Not specified",
                "quantity": "Not specified",
                "unit": "Not specified",
                "unit_price": "Not specified",
                "line_total": "Not specified",
                "currency": parsed.get("currency", "Not specified"),
                "tax_rate_percent": parsed.get("tax_rate_percent", "Not specified"),
                "sku_or_part_number": "Not specified",
            }
            normalized = {**item_defaults, **(item or {})}
            normalized_products.append(normalized)
        parsed["products"] = normalized_products
        return parsed
    except Exception as e:
        # Fallback if JSON parsing fails
        return {
            "invoice_number": "Not specified",
            "invoice_date": "Not specified",
            "due_date": "Not specified",
            "currency": "Not specified",
            "total_amount": "Not specified",
            "subtotal": "Not specified",
            "tax_amount": "Not specified",
            "tax_rate_percent": "Not specified",
            "payment_terms": "Not specified",
            "po_number": "Not specified",
            "supplier_name": "Not specified",
            "supplier_address": "Not specified",
            "customer_name": "Extraction failed",
            "customer_address": "Not specified",
            "ship_to": "Not specified",
            "tax_id": "Not specified",
            "products": [],
            "contract_type": "Unknown",
            "notes": "Not specified",
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


# ------------------------------
# Spec extraction and comparison
# ------------------------------

def extract_specifications_from_text(text: str) -> Dict[str, Any]:
    """
    Use Azure OpenAI to extract a structured JSON of specifications and measurements
    from arbitrary technical documents (spec PDFs, factory test certificates, etc.).
    
    Enhanced to capture ALL parameters without data loss.
    """
    if not azure_config.client:
        return {
            "error": "Azure OpenAI credentials not configured",
            "document_type": "unknown",
            "material_or_product": "Not specified",
            "revision_or_date": "Not specified",
            "parameters": []
        }

    prompt = f"""
Sie sind ein akribischer Analyst für technische Dokumente. Ihre Aufgabe ist es, JEDEN EINZELNEN Parameter, Spezifikation, Messung oder technische Eigenschaft zu extrahieren, die im folgenden Text erwähnt wird.

WICHTIGE ANWEISUNGEN:
1. ÜBERSPRINGEN SIE KEINE PARAMETER - erfassen Sie absolut alles
2. Suchen Sie nach ALLEN Arten von technischen Daten einschließlich:
   - Dimensionsspezifikationen (Länge, Breite, Durchmesser, Dicke, etc.)
   - Materialeigenschaften (Zugfestigkeit, Härte, Elastizität, Dichte, etc.)
   - Chemische Zusammensetzungen (Prozentanteile, Verhältnisse, Konzentrationen)
   - Leistungsmerkmale (Geschwindigkeit, Kapazität, Effizienz, etc.)
   - Qualitätsparameter (Oberflächengüte, Toleranzen, Grade)
   - Testergebnisse und Messwerte
   - Umgebungsbedingungen (Temperatur, Druck, Feuchtigkeit)
   - Standards und Compliance-Anforderungen
   - Beliebige nummerierte oder mit Buchstaben versehene Spezifikationsposten

3. Für JEDEN gefundenen Parameter extrahieren Sie:
   - parameter: exakter Name/Beschreibung wie geschrieben (AUF DEUTSCH)
   - unit: Maßeinheit (mm, MPa, %, °C, etc.) oder "Nicht spezifiziert"
   - spec_min: minimal zulässiger Wert (nur Zahl, oder null)
   - spec_max: maximal zulässiger Wert (nur Zahl, oder null)
   - spec_nominal: Ziel-/Sollwert (nur Zahl, oder null)
   - spec_tolerance_abs: absolute Toleranz wie ±0,1 (nur Zahl, oder null)
   - spec_tolerance_pct: Prozenttoleranz wie ±5% (nur Zahl, oder null)
   - measured_value: tatsächlicher gemessener/geprüfter Wert (nur Zahl, oder null)
   - notes: Kontext, Bedingungen oder Erläuterungen (auf Deutsch)

4. Behandeln Sie verschiedene Wertformate:
   - Bereich: "10-12 mm" → spec_min: 10, spec_max: 12, unit: "mm"
   - Sollwert mit Toleranz: "100±2 MPa" → spec_nominal: 100, spec_tolerance_abs: 2, unit: "MPa"
   - Prozenttoleranz: "50±5%" → spec_nominal: 50, spec_tolerance_pct: 5, unit: "%"
   - Einzelwert: "25 mm" → spec_nominal: 25, unit: "mm"

5. Geben Sie NUR gültiges JSON mit dieser exakten Struktur zurück:
{{
  "document_type": "spezifikation" | "zertifikat" | "unbekannt",
  "material_or_product": "Material- oder Produktname oder 'Nicht spezifiziert'",
  "revision_or_date": "Revisionsnummer/Datum oder 'Nicht spezifiziert'",
  "parameters": [
    {{
      "parameter": "string (auf Deutsch)",
      "unit": "string oder 'Nicht spezifiziert'",
      "spec_min": number or null,
      "spec_max": number or null,
      "spec_nominal": number or null,
      "spec_tolerance_abs": number or null,
      "spec_tolerance_pct": number or null,
      "measured_value": number or null,
      "notes": "string (auf Deutsch)"
    }}
  ]
}}

VERWENDEN SIE KEINE Markdown-Code-Blöcke. Geben Sie nur reines JSON zurück.

Zu analysierender Text:
{text}
"""

    try:
        response = azure_config.client.chat.completions.create(
            model=azure_config.deployment_name,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = response.choices[0].message.content.strip()
        
        # Clean any markdown formatting
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        data = json.loads(response_text)

        # Normalize required keys
        data.setdefault("document_type", "unbekannt")
        data.setdefault("material_or_product", "Nicht spezifiziert")
        data.setdefault("revision_or_date", "Nicht spezifiziert")
        data.setdefault("parameters", [])
        
        # Validate and normalize parameters
        norm_params = []
        for p in data.get("parameters", []):
            norm = {
                "parameter": str(p.get("parameter", "Unbekannt")).strip(),
                "unit": str(p.get("unit", "Nicht spezifiziert")).strip(),
                "spec_min": p.get("spec_min"),
                "spec_max": p.get("spec_max"),
                "spec_nominal": p.get("spec_nominal"),
                "spec_tolerance_abs": p.get("spec_tolerance_abs"),
                "spec_tolerance_pct": p.get("spec_tolerance_pct"),
                "measured_value": p.get("measured_value"),
                "notes": str(p.get("notes", "")).strip(),
            }
            
            # Ensure numeric fields are actually numeric or null
            numeric_fields = ["spec_min", "spec_max", "spec_nominal", 
                             "spec_tolerance_abs", "spec_tolerance_pct", "measured_value"]
            for field in numeric_fields:
                val = norm[field]
                if val is not None:
                    try:
                        norm[field] = float(val)
                    except (ValueError, TypeError):
                        norm[field] = None
            
            norm_params.append(norm)
        
        data["parameters"] = norm_params
        return data
    except Exception as e:
        return {
            "error": f"Fehler beim Extrahieren der Spezifikationen: {e}",
            "document_type": "unbekannt",
            "material_or_product": "Nicht spezifiziert",
            "revision_or_date": "Nicht spezifiziert",
            "parameters": []
        }


def compare_specifications_with_ai(spec_json: Dict[str, Any], cert_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ask Azure OpenAI to compare a baseline specification JSON against a certificate JSON
        and return normalized results highlighting out-of-tolerance values.

        Expected output structure:
        {
            "summary": "string",
            "comparisons": [
                {
                    "parameter": "string",
                    "unit": "string",
                    "spec_min": number|null,
                    "spec_max": number|null,
                    "spec_nominal": number|null,
                    "spec_tolerance_abs": number|null,
                    "spec_tolerance_pct": number|null,
                    "measured_value": number|null,
                    "status": "OK|OUT|MISSING|NO_BOUNDS",
                    "deviation": "string"
                }
            ]
        }
        """
        if not azure_config.client:
                return {"error": "Azure OpenAI credentials not configured", "comparisons": []}

        prompt = f"""
Sie erhalten zwei JSON-Dokumente:
- spec_json: Grundspezifikation mit Parametern, Einheiten und Toleranzen
- cert_json: Messungen aus einem Werkszeugnis

Aufgabe:
1) Ordnen Sie Parameter nach Name (nicht case-sensitiv; kleine Interpunktion kann ignoriert werden) und Einheit zu.
2) Für jeden Parameter in beiden Dokumenten berechnen Sie den Status:
     - OK: Messwert liegt innerhalb [spec_min, spec_max] oder innerhalb Sollwert±Toleranz
     - NICHT_OK: Messwert existiert, aber liegt außerhalb der Grenzen  
     - KEINE_GRENZEN: Spezifikation hat keine expliziten Grenzen; Messwert existiert
     - FEHLEND: Messwert im Zertifikat nicht gefunden
3) Geben Sie eine klare "Abweichung" für NICHT_OK Werte an (z.B., "-0,12 unter Minimum").

Geben Sie NUR gültiges JSON in diesem Schema zurück (verwenden Sie null für fehlende Zahlen):
{{
    "summary": "string (auf Deutsch)",
    "comparisons": [
        {{
            "parameter": "string (auf Deutsch)",
            "unit": "string (auf Deutsch)",
            "spec_min": null,
            "spec_max": null,
            "spec_nominal": null,
            "spec_tolerance_abs": null,
            "spec_tolerance_pct": null,
            "measured_value": null,
            "status": "OK|NICHT_OK|FEHLEND|KEINE_GRENZEN",
            "deviation": "string (auf Deutsch)"
        }}
    ]
}}

spec_json:
{json.dumps(spec_json, ensure_ascii=False, indent=2)}

cert_json:
{json.dumps(cert_json, ensure_ascii=False, indent=2)}
"""

        try:
                response = azure_config.client.chat.completions.create(
                        model=azure_config.deployment_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=1,
                )
                response_text = response.choices[0].message.content.strip()
                if "```json" in response_text:
                        response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                        response_text = response_text.split("```")[1].strip()
                data = json.loads(response_text)
                data.setdefault("summary", "")
                data.setdefault("comparisons", [])
                return data
        except Exception as e:
                return {"error": f"Fehler beim Vergleichen der Spezifikationen: {e}", "comparisons": []}
        

def analyze_tender_document(text: str, truncate_length: int = 12000) -> Dict[str, Any]:
    """Analyze a tender document, translate key content into German, and extract structured fields."""
    if not azure_config.client:
        return {
            "error": "❌ Azure OpenAI credentials not configured. "
                    "Please set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT environment variables.",
            "german_summary": "",
            "german_bullets": [],
            "tender_fields": {},
            "key_requirements": [],
            "risks": [],
            "deliverables": []
        }

    truncated_text = text[:truncate_length]

    prompt = f"""
You are a tender analyst. Read the tender document, extract the most relevant fields, and provide a German translation/summary.

Return ONLY valid JSON with this structure (use "Nicht angegeben" when missing):
{{
  "german_summary": "Kurzfassung auf Deutsch",
  "german_bullets": ["3-7 Stichpunkte auf Deutsch"],
  "tender_fields": {{
    "customer": "Ausschreibende Stelle / Kunde",
    "project_title": "Projekt- oder Leistungsbezeichnung",
    "reference_number": "Aktenzeichen/Referenznummer",
    "procedure": "Verfahrensart (z.B. Offenes Verfahren)",
    "submission_deadline": "Frist für Angebotsabgabe",
    "questions_deadline": "Frist für Bieterfragen/Klarstellungen",
    "contract_start": "Geplantes Leistungs-/Vertragsbeginndatum",
    "contract_end": "Geplantes Vertragsende/Laufzeit",
    "estimated_value": "Gesamtwert/Budget falls genannt",
    "country": "Land/Region",
    "language": "Sprache der Einreichung",
    "cpv_codes": ["Liste der CPV-Codes"],
    "notes": "Weitere wichtige Hinweise in Deutsch"
  }},
  "key_requirements": ["Pflichtanforderung 1", "Pflichtanforderung 2"],
  "deliverables": ["Leistung/Lieferumfang 1", "Leistung/Lieferumfang 2"],
  "risks": ["Risiko oder Stolperstein 1", "Risiko oder Stolperstein 2"]
}}

Document (truncate for tokens):
{truncated_text}
    """

    try:
        response = azure_config.client.chat.completions.create(
            model=azure_config.deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=1
        )

        response_text = response.choices[0].message.content.strip()

        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].strip()

        parsed = json.loads(response_text)

        # Normalize required keys
        defaults = {
            "german_summary": "",
            "german_bullets": [],
            "tender_fields": {},
            "key_requirements": [],
            "risks": [],
            "deliverables": []
        }
        for k, v in defaults.items():
            parsed.setdefault(k, v)

        tender_defaults = {
            "customer": "Nicht angegeben",
            "project_title": "Nicht angegeben",
            "reference_number": "Nicht angegeben",
            "procedure": "Nicht angegeben",
            "submission_deadline": "Nicht angegeben",
            "questions_deadline": "Nicht angegeben",
            "contract_start": "Nicht angegeben",
            "contract_end": "Nicht angegeben",
            "estimated_value": "Nicht angegeben",
            "country": "Nicht angegeben",
            "language": "Nicht angegeben",
            "cpv_codes": [],
            "notes": "Nicht angegeben"
        }
        parsed_fields = {**tender_defaults, **(parsed.get("tender_fields") or {})}
        parsed["tender_fields"] = parsed_fields

        # Ensure list fields are lists of strings
        list_keys = ["german_bullets", "key_requirements", "risks", "deliverables"]
        for key in list_keys:
            if key in parsed and not isinstance(parsed[key], list):
                parsed[key] = [str(parsed[key])]

        cpv_codes = parsed_fields.get("cpv_codes", [])
        if not isinstance(cpv_codes, list):
            cpv_codes = [str(cpv_codes)]
        parsed_fields["cpv_codes"] = [str(item) for item in cpv_codes]

        return parsed
    except Exception as e:
        return {
            "error": f"❌ Error analyzing tender: {str(e)}",
            "german_summary": "",
            "german_bullets": [],
            "tender_fields": {},
            "key_requirements": [],
            "risks": [],
            "deliverables": []
        }


def analyze_tender_with_fields(text: str, desired_fields: list,) -> Dict[str, Any]:
    """Analyze a tender document focusing on a provided list of field names.

    Returns ONLY JSON with keys:
    - "extracted": {<field>: <value>}
    - "german_summary": str
    - "notes": str
    """
    if not azure_config.client:
        return {
            "error": "❌ Azure OpenAI credentials not configured.",
            "extracted": {},
            "german_summary": "",
            "notes": ""
        }

    truncated_text = text
    fields_str = "\n".join(f"- {f}" for f in desired_fields)
    prompt = f"""
Du bist ein Vergabe-Analyst. Lies das Dokument und fülle die geforderten Felder. Antworte NUR mit gültigem JSON.

Felder (verwende exakt diese Bezeichnungen):
{fields_str}

Regeln:
- Falls Information fehlt, schreibe "Nicht angegeben".
- Erfinde keine Daten.

Gib zurück:
{{
  "extracted": {{ "<Feld>": "Wert" }},
  "german_summary": "Kurzfassung auf Deutsch",
  "notes": "Wichtige Hinweise/Unsicherheiten"
}}

Dokument (gekürzt):
{truncated_text}
    """

    try:
        response = azure_config.client.chat.completions.create(
            model=azure_config.deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=1
        )

        response_text = response.choices[0].message.content.strip()
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].strip()

        parsed = json.loads(response_text)
        extracted = parsed.get("extracted", {}) or {}
        # Ensure all desired fields exist
        for f in desired_fields:
            extracted.setdefault(f, "Nicht angegeben")
        parsed["extracted"] = extracted
        parsed.setdefault("german_summary", "")
        parsed.setdefault("notes", "")
        return parsed
    except Exception as e:
        return {
            "error": f"❌ Error analyzing tender (fields): {str(e)}",
            "extracted": {f: "Nicht angegeben" for f in desired_fields},
            "german_summary": "",
            "notes": ""
        }


def analyze_cooperation_agreement(text: str, truncate_length: int = 12000, 
                                   include_risk_assessment: bool = True,
                                   include_recommendations: bool = True) -> Dict[str, Any]:
    """
    Analyze a cooperation agreement (supplier proposal) for key terms, risks, and obligations.
    
    Args:
        text: Contract text to analyze
        truncate_length: Maximum text length to send to AI
        include_risk_assessment: Whether to include risk analysis
        include_recommendations: Whether to include recommendations
        
    Returns:
        dict: Structured analysis with summary, clauses, risks, and recommendations
    """
    if not azure_config.client:
        return {
            "error": "Azure OpenAI credentials not configured",
            "summary": {},
            "key_clauses": [],
            "risks": [],
            "recommendations": []
        }
    
    truncated_text = text[:truncate_length]
    
    prompt = f"""
You are an expert legal contract analyst. Analyze the provided cooperation agreement and return a detailed structured analysis in JSON format.

Return ONLY valid JSON with this exact structure:
{{
    "summary": {{
        "contract_type": "Type of cooperation agreement",
        "parties": "Parties involved",
        "duration": "Contract duration",
        "status": "Active/Proposed/Draft",
        "description": "Brief description of the agreement"
    }},
    "key_clauses": [
        {{
            "type": "Clause type (e.g., Payment Terms, Confidentiality, Termination, Liability, Scope of Work)",
            "description": "Description of the clause",
            "quote": "Direct quote from contract",
            "importance": "critical|high|standard"
        }}
    ],
    "risks": [
        {{
            "title": "Risk title",
            "category": "Financial|Legal|Operational|Other",
            "severity": "high|medium|low",
            "description": "Detailed description of the risk",
            "affected_section": "Contract section reference",
            "quote": "Relevant contract text",
            "recommendation": "How to mitigate this risk"
        }}
    ],
    "recommendations": [
        {{
            "action": "Recommended action",
            "priority": "high|medium|low",
            "rationale": "Why this action is recommended",
            "section": "Affected contract section"
        }}
    ]
}}

Rules:
- Use "Not specified" if information is missing
- Quote relevant contract passages
- Focus on obligations, payment terms, liability, confidentiality, and termination clauses
- Flag ambiguous language and unusual terms
- Prioritize financial and legal risks

Contract text:
{truncated_text}
    """
    
    try:
        response = azure_config.client.chat.completions.create(
            model=azure_config.deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=1
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Clean up JSON markdown
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].strip()
        
        parsed = json.loads(response_text)
        
        # Normalize structure
        parsed.setdefault("summary", {})
        parsed.setdefault("key_clauses", [])
        parsed.setdefault("risks", [])
        parsed.setdefault("recommendations", [])
        
        # Filter results based on options
        if not include_risk_assessment:
            parsed["risks"] = []
        
        if not include_recommendations:
            parsed["recommendations"] = []
        
        return parsed
        
    except Exception as e:
        return {
            "error": f"Error analyzing agreement: {str(e)}",
            "summary": {},
            "key_clauses": [],
            "risks": [],
            "recommendations": []
        }


def compare_contracts(supplier_text: str, standard_text: str, truncate_length: int = 12000,
                     include_risk_assessment: bool = True,
                     include_deviation_analysis: bool = True,
                     include_recommendations: bool = True) -> Dict[str, Any]:
    """
    Compare a supplier's agreement proposal against a standard MVS contract.
    
    Args:
        supplier_text: Supplier's proposed agreement text
        standard_text: Standard contract template text
        truncate_length: Max text length per document
        include_risk_assessment: Whether to include risk analysis
        include_deviation_analysis: Whether to compare deviations
        include_recommendations: Whether to include recommendations
        
    Returns:
        dict: Comparison results with deviations, risks, and recommendations
    """
    if not azure_config.client:
        return {
            "error": "Azure OpenAI credentials not configured",
            "summary": {},
            "deviations": [],
            "risks": [],
            "key_clauses": [],
            "recommendations": []
        }
    
    supplier_truncated = supplier_text[:truncate_length]
    standard_truncated = standard_text[:truncate_length]
    
    prompt = f"""
You are an expert legal contract analyst specializing in comparing cooperation agreements against standard templates. 
Compare the supplier's proposed agreement against the standard MVS contract and identify deviations, risks, and problematic terms.

Return ONLY valid JSON with this exact structure:
{{
    "summary": {{
        "contract_type": "Type of agreement",
        "parties": "Parties involved",
        "duration": "Contract duration",
        "status": "Analysis status",
        "description": "Brief comparison overview"
    }},
    "deviations": [
        {{
            "title": "Deviation title",
            "severity": "high|medium|low",
            "standard": "What the standard contract says",
            "supplier": "What the supplier's proposal says",
            "impact": "Impact of this deviation",
            "section": "Contract section"
        }}
    ],
    "risks": [
        {{
            "title": "Risk title",
            "category": "Financial|Legal|Operational|Other",
            "severity": "high|medium|low",
            "description": "Detailed risk description",
            "affected_section": "Contract section reference",
            "quote": "Relevant text from supplier agreement",
            "recommendation": "Mitigation strategy"
        }}
    ],
    "key_clauses": [
        {{
            "type": "Clause type",
            "description": "Clause description",
            "quote": "Direct quote",
            "importance": "critical|high|standard"
        }}
    ],
    "recommendations": [
        {{
            "action": "Recommended action",
            "priority": "high|medium|low",
            "rationale": "Why this action is needed",
            "section": "Affected section"
        }}
    ]
}}

STANDARD CONTRACT (Template):
{standard_truncated}

SUPPLIER'S PROPOSED AGREEMENT:
{supplier_truncated}

Analysis focus:
- Identify terms that differ significantly from standard
- Flag risky modifications to liability, confidentiality, and payment terms
- Highlight ambiguous or missing clauses
- Note financial exposure differences
- Compare payment terms, termination clauses, and dispute resolution
- Check for unusual limitations or unreasonable demands
- Prioritize high-risk deviations that need negotiation

Rules:
- Be specific and reference exact sections
- Quote relevant passages from both documents
- Rate severity based on financial and legal impact
- Suggest concrete negotiation points
    """
    
    try:
        response = azure_config.client.chat.completions.create(
            model=azure_config.deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=1
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Clean up JSON markdown
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].strip()
        
        parsed = json.loads(response_text)
        
        # Normalize structure
        parsed.setdefault("summary", {})
        parsed.setdefault("deviations", [])
        parsed.setdefault("risks", [])
        parsed.setdefault("key_clauses", [])
        parsed.setdefault("recommendations", [])
        
        # Filter based on options
        if not include_deviation_analysis:
            parsed["deviations"] = []
        
        if not include_risk_assessment:
            parsed["risks"] = []
        
        if not include_recommendations:
            parsed["recommendations"] = []
        
        return parsed
        
    except Exception as e:
        return {
            "error": f"Error comparing contracts: {str(e)}",
            "summary": {},
            "deviations": [],
            "risks": [],
            "key_clauses": [],
            "recommendations": []
        }
