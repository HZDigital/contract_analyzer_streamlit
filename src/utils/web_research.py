"""
Web research utilities using SearXNG for market intelligence.
"""

import os
import requests
import json
import time
from typing import Dict, List, Any
from config.settings import azure_config


def search_market_info(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Search for market information using SearXNG.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return
        
    Returns:
        List of search results with title, url, and content
    """
    searxng_url = os.getenv("SEARXNG_URL", "https://searxng.orangeisland-6e1300af.germanywestcentral.azurecontainerapps.io")
    
    if not searxng_url:
        return [{"error": "SearXNG URL not configured"}]
    
    try:
        params = {
            "q": query,
            "format": "json",
            "categories": "general",
            "language": "de",
            "time_range": "year"  # Focus on recent information
        }
        
        response = requests.get(f"{searxng_url}/search", params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        results = data.get("results", [])[:max_results]
        
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", "")
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": f"Search failed: {str(e)}"}]


def analyze_market_situation(customer: str, project_title: str, country: str, ai_client=None) -> Dict[str, Any]:
    """
    Perform market research for Marktsituation fields using web search only.
    
    Args:
        customer: Customer/organization name
        project_title: Project title/description
        country: Country/region
        ai_client: Azure OpenAI client (optional, used for synthesis)
        
    Returns:
        Market situation data with competitors, last tender info, split potential, and win chances
    """
    if not customer and not project_title:
        return {
            "Vermutliche Wettbewerber": "Nicht ermittelt",
            "Letzter Tender": "Nicht ermittelt",
            "Split möglich": "Nicht ermittelt",
            "Chancen in %": "Nicht ermittelt",
            "sources": []
        }
    
    # Build targeted search queries
    queries = []
    if customer:
        queries.append(f"{customer} Ausschreibung Wettbewerber Bieter {country}")
        queries.append(f"{customer} letzte Ausschreibung Tender Auftrag {country}")
    if project_title:
        queries.append(f"{project_title} Anbieter Markt {country}")
    
    # Gather web research
    all_results = []
    for query in queries[:3]:  # Limit to 3 queries
        results = search_market_info(query, 10)
        all_results.extend(results)
    
    sources = [
        {"title": r.get("title", ""), "url": r.get("url", "")}
        for r in all_results if not r.get("error")
    ]
    
    if not all_results or all_results[0].get("error"):
        return {
            "Vermutliche Wettbewerber": "Keine Web-Recherche verfügbar",
            "Letzter Tender": "Keine Web-Recherche verfügbar",
            "Split möglich": "Keine Web-Recherche verfügbar",
            "Chancen in %": "Keine Web-Recherche verfügbar",
            "sources": sources
        }
    
    # Synthesize findings with AI if available
    research_text = "\n\n".join([
        f"Quelle: {r.get('title', 'Unbekannt')}\n{r.get('content', '')[:500]}"
        for r in all_results if not r.get("error")
    ])
    
    prompt = f"""Analysiere die Web-Recherche-Ergebnisse zur Marktsituation für diese Ausschreibung.

Kunde: {customer}
Projekt: {project_title}
Land: {country}

Web-Recherche Ergebnisse (gekürzt):
{research_text}

Erstelle ein JSON-Objekt mit diesen EXAKT benannten Feldern:
{{
    "Vermutliche Wettbewerber": "Kommagetrennte Liste von möglichen Konkurrenten (2-5 Namen) oder 'Nicht ermittelt'",
    "Letzter Tender": "Info zu letztem ähnlichen Tender bei diesem Kunden: wer hat gewonnen, was war der ungefähre Preis/Wert (z.B. '2023: Unternehmen XY, ~€500k') oder 'Nicht ermittelt'",
    "Split möglich": "Ja, Nein, oder Unklar - ob die Leistung unter mehreren Anbietern aufgeteilt werden könnte",
    "Chancen in %": "Prozentuale Gewinnchance basierend auf Marktlage (z.B. '35%' oder 'Unklar')"
}}

Regel: Verwende "Nicht ermittelt" wenn die Information nicht in den Suchergebnissen vorhanden ist.
"""
    
    try:
        if azure_config.client:
            max_retries = 2
            last_err = None
            for attempt in range(max_retries):
                try:
                    response = azure_config.client.chat.completions.create(
                        model=azure_config.deployment_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=1,
                        timeout=60,
                    )
                    break  # Success
                except Exception as api_error:
                    last_err = api_error
                    if attempt < max_retries - 1:
                        time.sleep(0.5 * (2 ** attempt))  # Exponential backoff
                        continue
                    raise last_err
            
            response_text = response.choices[0].message.content.strip()
            
            # Extract JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].strip()
            
            import json
            analysis = json.loads(response_text)
            
            # Ensure required fields exist
            analysis.setdefault("Vermutliche Wettbewerber", "Nicht ermittelt")
            analysis.setdefault("Letzter Tender", "Nicht ermittelt")
            analysis.setdefault("Split möglich", "Unklar")
            analysis.setdefault("Chancen in %", "Unklar")
            analysis["sources"] = sources
            
            return analysis
        else:
            # No AI available, return structured empty result
            return {
                "Vermutliche Wettbewerber": "Nicht ermittelt",
                "Letzter Tender": "Nicht ermittelt",
                "Split möglich": "Unklar",
                "Chancen in %": "Unklar",
                "sources": sources
            }
        
    except Exception as e:
        return {
            "Vermutliche Wettbewerber": "Fehler bei Analyse",
            "Letzter Tender": f"Fehler: {str(e)[:50]}",
            "Split möglich": "Unklar",
            "Chancen in %": "Unklar",
            "sources": sources
        }
