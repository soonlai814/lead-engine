"""Generic ecosystem/community page parser."""

import re
from typing import Dict, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import structlog

logger = structlog.get_logger()


def _extract_ecosystem_tag(text: str, url: str) -> Optional[str]:
    """Extract ecosystem tag (Base, Solana, Polygon, Ethereum, etc.) from text or URL."""
    if not text:
        return None
    
    text_lower = text.lower()
    url_lower = url.lower()
    
    # Known ecosystems
    ecosystems = [
        "base",
        "solana",
        "polygon",
        "ethereum",
        "arbitrum",
        "optimism",
        "avalanche",
        "cosmos",
        "polkadot",
        "near",
        "sui",
        "aptos",
        "starknet",
        "zksync",
    ]
    
    for ecosystem in ecosystems:
        if ecosystem in text_lower or ecosystem in url_lower:
            return ecosystem.title()
    
    return None


def _extract_program_type(text: str, url: str) -> Optional[str]:
    """Extract program type (directory, grant, hackathon) from text or URL."""
    if not text:
        return None
    
    text_lower = text.lower()
    url_lower = url.lower()
    
    # Check for program type keywords
    if any(kw in text_lower for kw in ["hackathon", "hack", "demo day", "winners", "finalists"]):
        return "hackathon"
    elif any(kw in text_lower for kw in ["grant", "grant program", "grant recipient", "grantee"]):
        return "grant"
    elif any(kw in text_lower for kw in ["directory", "ecosystem", "projects", "companies", "list"]):
        return "directory"
    
    # Check URL patterns
    if any(kw in url_lower for kw in ["hackathon", "hack"]):
        return "hackathon"
    elif "grant" in url_lower:
        return "grant"
    elif any(kw in url_lower for kw in ["directory", "ecosystem", "projects"]):
        return "directory"
    
    return None


def _extract_program_name(text: str, url: str) -> Optional[str]:
    """Extract program name from text or URL."""
    if not text:
        return None
    
    # Look for program name patterns
    # Common patterns: "Base Builder Program", "Solana Hackathon 2024", etc.
    program_patterns = [
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Builder|Hackathon|Grant|Program|Ecosystem)",
        r"(?:Builder|Hackathon|Grant|Program)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        r"([A-Z][a-z]+)\s+Ecosystem",
        r"([A-Z][a-z]+)\s+Directory",
    ]
    
    for pattern in program_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1) if match.lastindex else match.group(0)
    
    # Try to extract from URL
    try:
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        if path_parts:
            # Last part might be program name
            program_slug = path_parts[-1]
            if program_slug and len(program_slug) > 2:
                # Convert slug to title case
                return program_slug.replace("-", " ").replace("_", " ").title()
    except Exception:
        pass
    
    return None


def _extract_project_domain(text: str, url: str) -> Optional[str]:
    """Extract project domain from text or URL."""
    # Look for URLs in text
    url_pattern = r"https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"
    matches = re.findall(url_pattern, text)
    if matches:
        domain = matches[0].lower()
        # Remove www.
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    
    # Try to extract from links in HTML (will be done in main function)
    # For now, try to extract from URL if it's a project page
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        # If it's a known ecosystem site, try to extract project from path
        if any(ecosystem in netloc for ecosystem in ["base", "solana", "polygon", "ethereum"]):
            path_parts = [p for p in parsed.path.split("/") if p]
            if path_parts:
                # Last part might be project
                project_slug = path_parts[-1]
                if project_slug and len(project_slug) > 2:
                    return f"{project_slug}.com"
    except Exception:
        pass
    
    return None


def parse_ecosystem_page(url: str, html: str) -> Dict:
    """
    Parse ecosystem/community directory page HTML.
    
    Args:
        url: Ecosystem page URL
        html: HTML content
    
    Returns:
        Dictionary with:
        - ecosystem_tag: str (Base/Solana/etc., can be None)
        - program_type: str (directory|grant|hackathon, can be None)
        - program_name: str (can be None)
        - project_domain: str (can be None)
        - signals: list[str] (ecosystem_listed, grant_recipient, hackathon_winner)
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # Extract text content
        text_content = soup.get_text(separator=" ", strip=True)
        text_lower = text_content.lower()
        
        # Extract ecosystem tag
        ecosystem_tag = _extract_ecosystem_tag(text_content, url)
        
        # Extract program type
        program_type = _extract_program_type(text_content, url)
        
        # Extract program name
        program_name = _extract_program_name(text_content, url)
        
        # Extract project domain
        project_domain = _extract_project_domain(text_content, url)
        
        # If no domain found, try to extract from links
        if not project_domain:
            # Look for project/company website links
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True).lower()
                
                # Check if it looks like a project website
                if any(kw in text for kw in ["website", "homepage", "project", "visit", "site"]):
                    if href.startswith("http"):
                        try:
                            parsed = urlparse(href)
                            domain = parsed.netloc.lower()
                            if domain.startswith("www."):
                                domain = domain[4:]
                            if domain and "." in domain:
                                # Exclude known ecosystem sites
                                if not any(ecosystem in domain for ecosystem in ["base.org", "solana.com", "polygon.technology", "ethereum.org"]):
                                    project_domain = domain
                                    break
                        except Exception:
                            pass
                
                # Also check if href itself is a domain
                if not project_domain and href.startswith("http"):
                    try:
                        parsed = urlparse(href)
                        domain = parsed.netloc.lower()
                        if domain.startswith("www."):
                            domain = domain[4:]
                        if domain and "." in domain:
                            # Exclude known ecosystem sites
                            if not any(ecosystem in domain for ecosystem in ["base.org", "solana.com", "polygon.technology", "ethereum.org"]):
                                project_domain = domain
                                break
                    except Exception:
                        pass
        
        # Generate signals
        signals = []
        
        # Ecosystem listed signal
        if ecosystem_tag or program_type:
            signals.append("ecosystem_listed")
        
        # Grant recipient signal
        if program_type == "grant" or any(kw in text_lower for kw in ["grant recipient", "grantee", "awarded grant"]):
            signals.append("grant_recipient")
        
        # Hackathon winner signal
        if program_type == "hackathon" or any(kw in text_lower for kw in ["hackathon winner", "hackathon finalist", "demo day winner"]):
            signals.append("hackathon_winner")
        
        result = {
            "ecosystem_tag": ecosystem_tag,
            "program_type": program_type,
            "program_name": program_name,
            "project_domain": project_domain,
            "signals": signals,
        }
        
        logger.debug(
            "Parsed ecosystem page",
            url=url,
            ecosystem_tag=ecosystem_tag,
            program_type=program_type,
            program_name=program_name,
            signals=signals,
        )
        
        return result
        
    except Exception as e:
        logger.error("Error parsing ecosystem page", url=url, error=str(e), exc_info=True)
        return {
            "ecosystem_tag": None,
            "program_type": None,
            "program_name": None,
            "project_domain": None,
            "signals": [],
        }
