"""Generic funding/accelerator page parser."""

import re
from datetime import datetime, timedelta
from typing import Dict, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import structlog

logger = structlog.get_logger()


def _extract_date_from_text(text: str) -> Optional[datetime]:
    """
    Extract date from text using various patterns.
    
    Returns datetime or None if not found.
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Common date patterns for funding announcements
    date_patterns = [
        # "raised on March 15, 2024"
        r"(?:raised|announced|closed|secured)\s+(?:on\s+)?(\w+\s+\d{1,2},?\s+\d{4})",
        # "March 15, 2024"
        r"(\w+\s+\d{1,2},?\s+\d{4})",
        # "2024-03-15" or "03/15/2024"
        r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
        # "15 days ago", "2 weeks ago", "1 month ago"
        r"(\d+)\s+(?:day|days|week|weeks|month|months)\s+ago",
        # "yesterday", "today"
        r"(today|yesterday)",
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                if "ago" in match.group(0):
                    # Relative date
                    num = int(match.group(1))
                    unit = match.group(0).split()[1]
                    if "day" in unit:
                        return datetime.now() - timedelta(days=num)
                    elif "week" in unit:
                        return datetime.now() - timedelta(weeks=num)
                    elif "month" in unit:
                        return datetime.now() - timedelta(days=num * 30)
                elif "today" in match.group(0):
                    return datetime.now()
                elif "yesterday" in match.group(0):
                    return datetime.now() - timedelta(days=1)
                else:
                    # Try to parse absolute date
                    date_str = match.group(1)
                    # Try different formats
                    for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"]:
                        try:
                            return datetime.strptime(date_str, fmt)
                        except ValueError:
                            continue
            except (ValueError, IndexError):
                continue
    
    return None


def _extract_funding_round(text: str) -> Optional[str]:
    """Extract funding round type from text."""
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Check for funding round keywords
    if re.search(r"\bpre[- ]?seed\b", text_lower):
        return "pre-seed"
    elif re.search(r"\bseed\b", text_lower) and "pre-seed" not in text_lower:
        return "seed"
    elif re.search(r"\bseries\s+a\b", text_lower):
        return "Series A"
    elif re.search(r"\bseries\s+b\b", text_lower):
        return "Series B"
    elif re.search(r"\bseries\s+c\b", text_lower):
        return "Series C"
    
    return None


def _extract_accelerator_name(text: str, url: str) -> Optional[str]:
    """Extract accelerator name from text or URL."""
    if not text:
        return None
    
    text_lower = text.lower()
    url_lower = url.lower()
    
    # Known accelerators
    accelerators = [
        "y combinator", "yc", "ycombinator",
        "techstars",
        "500 global", "500 startups",
        "antler",
        "plaid",
        "first round",
        "a16z", "andreessen horowitz",
        "sequoia",
        "accel",
    ]
    
    for accelerator in accelerators:
        if accelerator in text_lower or accelerator in url_lower:
            # Return formatted name
            if accelerator == "yc" or accelerator == "ycombinator":
                return "Y Combinator"
            elif accelerator == "500 global" or accelerator == "500 startups":
                return "500 Global"
            elif accelerator == "a16z":
                return "Andreessen Horowitz"
            elif accelerator == "first round":
                return "First Round"
            else:
                return accelerator.title()
    
    return None


def _extract_batch_info(text: str) -> Optional[str]:
    """Extract batch/cohort information."""
    if not text:
        return None
    
    # Look for batch patterns
    batch_patterns = [
        r"batch\s+(\w+)",
        r"cohort\s+(\w+)",
        r"class\s+of\s+(\d{4})",
        r"w(\d+)",  # YC format: W24, W25, etc.
        r"s(\d+)",  # YC format: S24, S25, etc.
    ]
    
    for pattern in batch_patterns:
        match = re.search(pattern, text.lower())
        if match:
            return match.group(1)
    
    return None


def _extract_company_domain_from_text(text: str, url: str) -> Optional[str]:
    """Extract company domain from text or URL."""
    # Look for URLs in text
    url_pattern = r"https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"
    matches = re.findall(url_pattern, text)
    if matches:
        domain = matches[0].lower()
        # Remove www.
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    
    # Try to extract from URL if it's a company page
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        # If it's a known accelerator site, try to extract company from path
        if "ycombinator.com" in netloc or "techstars.com" in netloc:
            # Path might contain company name
            path_parts = [p for p in parsed.path.split("/") if p]
            if path_parts:
                # Last part might be company
                company_slug = path_parts[-1]
                if company_slug and len(company_slug) > 2:
                    return f"{company_slug}.com"
    except Exception:
        pass
    
    return None


def _is_recent_funding(funding_date: Optional[datetime], funding_round: Optional[str]) -> bool:
    """Check if funding is recent (within 12 months for pre-seed/seed, 18 months for Series A)."""
    if not funding_date:
        return False
    
    now = datetime.now()
    if funding_date.tzinfo:
        from datetime import timezone
        now = now.replace(tzinfo=timezone.utc)
    
    months_ago = (now - funding_date).days / 30
    
    if funding_round in ["pre-seed", "seed"]:
        return months_ago <= 12
    elif funding_round == "Series A":
        return months_ago <= 18
    
    # Default: consider recent if within 12 months
    return months_ago <= 12


def parse_funding_page(url: str, html: str) -> Dict:
    """
    Parse funding/accelerator page HTML.
    
    Args:
        url: Funding page URL
        html: HTML content
    
    Returns:
        Dictionary with:
        - accelerator_name: str (can be None)
        - batch: str (can be None)
        - funding_round: str (pre-seed/seed/A, can be None)
        - funding_date: str ISO format (can be None)
        - company_domain: str (can be None)
        - signals: list[str] (accelerator_member, recent_funding)
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # Extract text content
        text_content = soup.get_text(separator=" ", strip=True)
        text_lower = text_content.lower()
        
        # Extract accelerator name
        accelerator_name = _extract_accelerator_name(text_content, url)
        
        # Extract batch/cohort
        batch = _extract_batch_info(text_content)
        
        # Extract funding round
        funding_round = _extract_funding_round(text_content)
        
        # Extract funding date
        funding_date = _extract_date_from_text(text_content)
        
        # Extract company domain
        company_domain = _extract_company_domain_from_text(text_content, url)
        
        # If no domain found, try to extract from links
        if not company_domain:
            # Look for company website links
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True).lower()
                
                # Check if it looks like a company website
                if any(kw in text for kw in ["website", "homepage", "company", "visit"]):
                    if href.startswith("http"):
                        try:
                            parsed = urlparse(href)
                            domain = parsed.netloc.lower()
                            if domain.startswith("www."):
                                domain = domain[4:]
                            if domain and "." in domain:
                                company_domain = domain
                                break
                        except Exception:
                            pass
        
        # Generate signals
        signals = []
        
        # Accelerator member signal
        if accelerator_name:
            signals.append("accelerator_member")
        
        # Recent funding signal
        if _is_recent_funding(funding_date, funding_round):
            signals.append("recent_funding")
        elif funding_round:  # Has funding but not recent
            signals.append("funding_detected")
        
        result = {
            "accelerator_name": accelerator_name,
            "batch": batch,
            "funding_round": funding_round,
            "funding_date": funding_date.isoformat() if funding_date else None,
            "company_domain": company_domain,
            "signals": signals,
        }
        
        logger.debug(
            "Parsed funding page",
            url=url,
            accelerator_name=accelerator_name,
            funding_round=funding_round,
            funding_date=funding_date.isoformat() if funding_date else None,
            signals=signals,
        )
        
        return result
        
    except Exception as e:
        logger.error("Error parsing funding page", url=url, error=str(e), exc_info=True)
        return {
            "accelerator_name": None,
            "batch": None,
            "funding_round": None,
            "funding_date": None,
            "company_domain": None,
            "signals": [],
        }
