"""Company domain resolver."""

import re
from typing import Dict, Optional
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()


def _normalize_domain(domain: str) -> str:
    """
    Normalize domain to root domain.
    
    Removes www, subdomains (for known patterns), and normalizes case.
    """
    if not domain:
        return domain
    
    domain = domain.lower().strip()
    
    # Remove protocol if present
    if "://" in domain:
        parsed = urlparse(domain)
        domain = parsed.netloc
    else:
        # Remove port if present
        domain = domain.split(":")[0]
    
    # Remove www prefix
    if domain.startswith("www."):
        domain = domain[4:]
    
    # Remove trailing slash
    domain = domain.rstrip("/")
    
    return domain


def _extract_domain_from_url(url: str) -> Optional[str]:
    """Extract domain from URL."""
    if not url:
        return None
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove port
        if ":" in domain:
            domain = domain.split(":")[0]
        
        return _normalize_domain(domain)
    except Exception:
        return None


def _extract_domain_from_ats_url(ats_url: str) -> Optional[str]:
    """
    Extract company domain from ATS URL patterns.
    
    Examples:
    - boards.greenhouse.io/companyname -> companyname.com (best guess)
    - jobs.lever.co/companyname -> companyname.com (best guess)
    - companyname.teamtailor.com -> companyname.com (best guess)
    """
    if not ats_url:
        return None
    
    try:
        parsed = urlparse(ats_url)
        netloc = parsed.netloc.lower()
        path = parsed.path.strip("/")
        
        # Teamtailor: companyname.teamtailor.com -> companyname
        if ".teamtailor.com" in netloc:
            company_slug = netloc.split(".teamtailor.com")[0]
            # Try common TLDs
            return f"{company_slug}.com"
        
        # Recruitee: companyname.recruitee.com -> companyname
        if ".recruitee.com" in netloc:
            company_slug = netloc.split(".recruitee.com")[0]
            return f"{company_slug}.com"
        
        # Greenhouse/Lever/Ashby: extract from path
        # boards.greenhouse.io/companyname -> companyname
        if path:
            # Take first path segment as company slug
            company_slug = path.split("/")[0]
            if company_slug and len(company_slug) > 2:
                # Try common TLDs
                return f"{company_slug}.com"
        
        return None
    except Exception:
        return None


def resolve_company_domain(parsed: Dict, source_url: Optional[str] = None) -> Optional[str]:
    """
    Resolve company domain from parsed data.
    
    Args:
        parsed: Parsed data from ATS/launch/funding parser
        source_url: Optional source URL (for fallback extraction)
    
    Returns:
        Root domain string (e.g., "example.com"), or None if not resolvable
    
    Strategy:
        1. Try company_website_url from parsed data
        2. Try product_url from parsed data
        3. Try company_domain from parsed data
        4. Fallback: extract from source_url (ATS URL patterns)
        5. Normalize to root domain
    """
    # Try company_website_url
    company_url = parsed.get("company_website_url")
    if company_url:
        domain = _extract_domain_from_url(company_url)
        if domain:
            logger.debug("Resolved domain from company_website_url", domain=domain)
            return domain
    
    # Try product_url
    product_url = parsed.get("product_url")
    if product_url:
        domain = _extract_domain_from_url(product_url)
        if domain:
            logger.debug("Resolved domain from product_url", domain=domain)
            return domain
    
    # Try company_domain (already extracted)
    company_domain = parsed.get("company_domain")
    if company_domain:
        domain = _normalize_domain(company_domain)
        if domain:
            logger.debug("Resolved domain from company_domain", domain=domain)
            return domain
    
    # Try project_domain (for ecosystem sources)
    project_domain = parsed.get("project_domain")
    if project_domain:
        domain = _normalize_domain(project_domain)
        if domain:
            logger.debug("Resolved domain from project_domain", domain=domain)
            return domain
    
    # Fallback: extract from source URL
    if source_url:
        # Try ATS URL patterns first
        domain = _extract_domain_from_ats_url(source_url)
        if domain:
            logger.debug("Resolved domain from ATS URL pattern", domain=domain, source_url=source_url)
            return domain
        
        # Try extracting domain directly from URL (for non-ATS URLs like agency websites)
        domain = _extract_domain_from_url(source_url)
        if domain:
            logger.debug("Resolved domain from source URL", domain=domain, source_url=source_url)
            return domain
    
    logger.warning("Could not resolve company domain", parsed_keys=list(parsed.keys()), source_url=source_url)
    return None

