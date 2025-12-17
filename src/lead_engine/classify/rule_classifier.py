"""Rule-based business type classifier."""

import re
from typing import Dict, List

from bs4 import BeautifulSoup
import structlog

from ..storage.models import BusinessType

logger = structlog.get_logger()


def _load_keywords(keywords_config: Dict) -> Dict[str, List[str]]:
    """Load keywords from config."""
    return {
        "product_indicators": {
            "strong": keywords_config.get("product_indicators", {}).get("strong_product", []),
            "moderate": keywords_config.get("product_indicators", {}).get("sales_motion", []),
        },
        "services_indicators": {
            "strong": keywords_config.get("services_indicators", {}).get("strong", []),
            "moderate": keywords_config.get("services_indicators", {}).get("moderate", []),
        },
        "staffing_indicators": {
            "strong": keywords_config.get("staffing_indicators", {}).get("strong", []),
            "moderate": keywords_config.get("staffing_indicators", {}).get("moderate", []),
        },
        "enterprise_indicators": {
            "enterprise_noise": keywords_config.get("enterprise_indicators", {}).get("enterprise_noise", []),
            "huge_hiring": keywords_config.get("enterprise_indicators", {}).get("huge_hiring", []),
        },
        "partnership_indicators": {
            "partner_fit": keywords_config.get("partnership_indicators", {}).get("partner_fit", []),
        },
    }


def _extract_text_from_html(html: str) -> str:
    """Extract clean text from HTML."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        
        # Get text
        text = soup.get_text(separator=" ", strip=True)
        
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        
        return text.lower()
    except Exception:
        return ""


def _count_keywords(text: str, keywords: List[str]) -> int:
    """Count occurrences of keywords in text."""
    count = 0
    text_lower = text.lower()
    
    for keyword in keywords:
        keyword_lower = keyword.lower()
        # Count occurrences (word boundaries)
        count += len(re.findall(rf"\b{re.escape(keyword_lower)}\b", text_lower))
    
    return count


def classify_domain(domain: str, pages: Dict[str, str], keywords_config: Dict = None, scoring_config: Dict = None) -> Dict:
    """
    Classify business type using rule-based keyword matching.
    
    Args:
        domain: Company domain
        pages: Dictionary mapping page paths to HTML content
               Expected keys: "/", "/about", "/pricing" or "/docs" or "/services"
        keywords_config: Optional keywords config dict
        scoring_config: Optional scoring config dict (for thresholds)
    
    Returns:
        Dictionary with:
        - business_type: BusinessType enum value
        - confidence: float 0..1
        - reasons: list[str] (explanation of classification)
        - enterprise_detected: bool (whether enterprise noise detected)
        - partnership_fit_detected: bool (whether partnership indicators detected)
    """
    if keywords_config is None:
        keywords_config = {}
    
    if scoring_config is None:
        scoring_config = {}
    
    keywords = _load_keywords(keywords_config)
    classification_config = scoring_config.get("classification", {})
    
    # Combine all page text
    all_text = ""
    for page_path, html in pages.items():
        page_text = _extract_text_from_html(html)
        all_text += f" {page_text}"
    
    if not all_text.strip():
        logger.warning("No text extracted from pages", domain=domain)
        return {
            "business_type": BusinessType.UNKNOWN.value,
            "confidence": 0.0,
            "reasons": ["No text content found on pages"],
            "enterprise_detected": False,
            "partnership_fit_detected": False,
        }
    
    # Count keywords
    product_strong = _count_keywords(all_text, keywords["product_indicators"]["strong"])
    product_moderate = _count_keywords(all_text, keywords["product_indicators"]["moderate"])
    product_count = product_strong * 2 + product_moderate  # Weight strong indicators more
    
    services_strong = _count_keywords(all_text, keywords["services_indicators"]["strong"])
    services_moderate = _count_keywords(all_text, keywords["services_indicators"]["moderate"])
    services_count = services_strong * 2 + services_moderate
    
    staffing_strong = _count_keywords(all_text, keywords["staffing_indicators"]["strong"])
    staffing_moderate = _count_keywords(all_text, keywords["staffing_indicators"]["moderate"])
    staffing_count = staffing_strong * 2 + staffing_moderate
    
    # Check for enterprise indicators
    enterprise_noise_count = _count_keywords(all_text, keywords["enterprise_indicators"]["enterprise_noise"])
    huge_hiring_count = _count_keywords(all_text, keywords["enterprise_indicators"]["huge_hiring"])
    enterprise_detected = (enterprise_noise_count > 0) or (huge_hiring_count > 0)
    
    # Check for partnership fit indicators
    partnership_fit_count = _count_keywords(all_text, keywords["partnership_indicators"]["partner_fit"])
    partnership_fit_detected = partnership_fit_count > 0
    
    # Check for strong indicators in page paths
    page_paths = list(pages.keys())
    has_pricing = any("/pricing" in path for path in page_paths)
    has_docs = any("/docs" in path or "/documentation" in path for path in page_paths)
    has_services = any("/services" in path for path in page_paths)
    
    # Apply decision rules
    staffing_threshold = classification_config.get("staffing_count_threshold", 2)
    services_product_delta = classification_config.get("services_product_delta", 2)
    
    reasons = []
    business_type = BusinessType.UNKNOWN
    confidence = 0.0
    
    # Rule 1: Staffing/Recruiter check (highest priority)
    if staffing_count >= staffing_threshold:
        business_type = BusinessType.STAFFING_RECRUITER
        confidence = min(0.9, 0.5 + (staffing_count / 10))
        reasons.append(f"Found {staffing_count} staffing/recruiting indicators")
    
    # Rule 2: Services vs Product
    elif services_count - product_count >= services_product_delta:
        # Determine service type
        if "consulting" in all_text or "consultant" in all_text:
            business_type = BusinessType.CONSULTANCY
        elif "agency" in all_text:
            business_type = BusinessType.SERVICE_AGENCY
        elif "integrator" in all_text or "integration" in all_text:
            business_type = BusinessType.SYSTEM_INTEGRATOR
        else:
            business_type = BusinessType.SERVICE_AGENCY  # Default
        
        confidence = min(0.85, 0.5 + ((services_count - product_count) / 10))
        reasons.append(f"Services indicators ({services_count}) significantly exceed product indicators ({product_count})")
        if has_services:
            reasons.append("Services page found")
        if partnership_fit_detected:
            reasons.append("Partnership fit indicators detected")
    
    # Rule 3: Product company
    elif product_count - services_count >= services_product_delta:
        business_type = BusinessType.PRODUCT_COMPANY
        confidence = min(0.9, 0.6 + ((product_count - services_count) / 10))
        reasons.append(f"Product indicators ({product_count}) significantly exceed services indicators ({services_count})")
        if has_pricing:
            reasons.append("Pricing page found (strong product signal)")
        if has_docs:
            reasons.append("Documentation page found (strong product signal)")
    
    # Rule 4: Tie or low counts - use page structure hints
    else:
        if has_pricing or has_docs:
            business_type = BusinessType.PRODUCT_COMPANY
            confidence = 0.6
            reasons.append("Pricing or documentation page found, suggesting product company")
        elif has_services:
            business_type = BusinessType.SERVICE_AGENCY
            confidence = 0.6
            reasons.append("Services page found, suggesting service agency")
        else:
            business_type = BusinessType.UNKNOWN
            confidence = 0.3
            reasons.append("Insufficient evidence for classification")
    
    # Add enterprise detection to reasons if found
    if enterprise_detected:
        reasons.append("Enterprise noise indicators detected")
    
    # Adjust confidence based on total keyword counts
    total_keywords = product_count + services_count + staffing_count
    if total_keywords < 3:
        confidence *= 0.7  # Lower confidence if very few keywords found
    
    result = {
        "business_type": business_type.value if isinstance(business_type, BusinessType) else business_type,
        "confidence": round(confidence, 2),
        "reasons": reasons,
        "enterprise_detected": enterprise_detected,
        "partnership_fit_detected": partnership_fit_detected,
    }
    
    logger.debug(
        "Classification completed",
        domain=domain,
        business_type=result["business_type"],
        confidence=result["confidence"],
        product_count=product_count,
        services_count=services_count,
        staffing_count=staffing_count,
        enterprise_detected=enterprise_detected,
        partnership_fit_detected=partnership_fit_detected,
    )
    
    return result
