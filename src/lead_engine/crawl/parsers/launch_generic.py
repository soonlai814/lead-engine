"""Generic launch page parser."""

import re
from datetime import datetime, timedelta
from typing import Dict, Optional
from urllib.parse import urlparse, urljoin

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
    
    # Common date patterns
    date_patterns = [
        # "launched on March 15, 2024"
        r"(?:launched|released|published|posted)\s+(?:on\s+)?(\w+\s+\d{1,2},?\s+\d{4})",
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


def _extract_date_from_meta(soup: BeautifulSoup) -> Optional[datetime]:
    """Extract date from meta tags."""
    # Try published_time
    meta_published = soup.find("meta", property="article:published_time")
    if meta_published and meta_published.get("content"):
        try:
            return datetime.fromisoformat(meta_published["content"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass
    
    # Try time tag
    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        try:
            return datetime.fromisoformat(time_tag["datetime"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass
    
    # Try datePublished in JSON-LD
    json_ld = soup.find("script", type="application/ld+json")
    if json_ld:
        try:
            import json
            data = json.loads(json_ld.string)
            if isinstance(data, dict):
                date_published = data.get("datePublished") or data.get("datePublished")
                if date_published:
                    return datetime.fromisoformat(date_published.replace("Z", "+00:00"))
        except (json.JSONDecodeError, ValueError, AttributeError):
            pass
    
    return None


def _extract_product_name(soup: BeautifulSoup, url: str) -> Optional[str]:
    """Extract product name from page."""
    # Try meta tags first
    meta_title = soup.find("meta", property="og:title")
    if meta_title and meta_title.get("content"):
        title = meta_title["content"].strip()
        # Remove common suffixes
        title = re.sub(r"\s*[-|]\s*(Show HN|Launch|Product).*$", "", title, flags=re.I)
        if title:
            return title
    
    # Try h1
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
        if title and len(title) < 100:  # Reasonable length
            return title
    
    # Try title tag
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)
        # Remove common suffixes
        title = re.sub(r"\s*[-|]\s*(Show HN|Launch|Product).*$", "", title, flags=re.I)
        if title and len(title) < 100:
            return title
    
    return None


def _extract_product_url(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Extract product URL from page."""
    # Try to find links that look like product URLs
    # Look for links with product-related text
    product_keywords = ["try it", "visit", "website", "homepage", "product", "app", "tool"]
    
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        text = link.get_text(strip=True).lower()
        
        # Check if link text suggests it's the product
        if any(kw in text for kw in product_keywords):
            # Resolve relative URLs
            if href.startswith("http"):
                return href
            else:
                return urljoin(base_url, href)
    
    # Try to find canonical URL
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        return canonical["href"]
    
    # Try og:url
    meta_url = soup.find("meta", property="og:url")
    if meta_url and meta_url.get("content"):
        return meta_url["content"]
    
    # If no product URL found, return the base URL
    return base_url


def _detect_builder_post(soup: BeautifulSoup, url: str, text: str) -> bool:
    """Detect if this is a builder post (Show HN, etc.)."""
    text_lower = text.lower()
    url_lower = url.lower()
    
    # Check for Show HN
    if "show hn" in text_lower or "showhn" in text_lower:
        return True
    
    # Check for ProductHunt
    if "producthunt" in url_lower or "product hunt" in text_lower:
        return True
    
    # Check for builder/maker language
    builder_keywords = [
        "i built", "we built", "i made", "we made",
        "side project", "weekend project", "indie maker",
        "built this", "shipping", "launched"
    ]
    
    if any(kw in text_lower for kw in builder_keywords):
        return True
    
    return False


def _calculate_recency_signal(launch_date: Optional[datetime]) -> Optional[str]:
    """Calculate recency signal based on launch date."""
    if not launch_date:
        return None
    
    now = datetime.now()
    if launch_date.tzinfo:
        # Handle timezone-aware dates
        from datetime import timezone
        now = now.replace(tzinfo=timezone.utc)
    
    days_ago = (now - launch_date).days
    
    if days_ago <= 30:
        return "recent_launch_0_30d"
    elif days_ago <= 90:
        return "recent_launch_31_90d"
    
    return None


def parse_launch_page(url: str, html: str) -> Dict:
    """
    Parse launch page/post HTML.
    
    Args:
        url: Launch page URL
        html: HTML content
    
    Returns:
        Dictionary with:
        - launch_date: datetime (best effort, can be None)
        - product_name: str (can be None)
        - product_url: str (can be None)
        - company_domain: str (resolved from product_url, can be None)
        - signals: list[str] (recent_launch_0_30d, recent_launch_31_90d, builder_post)
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # Extract text content
        text_content = soup.get_text(separator=" ", strip=True)
        
        # Extract launch date
        launch_date = None
        
        # Try meta tags first
        launch_date = _extract_date_from_meta(soup)
        
        # Fallback to text extraction
        if not launch_date:
            launch_date = _extract_date_from_text(text_content)
        
        # Extract product name
        product_name = _extract_product_name(soup, url)
        
        # Extract product URL
        product_url = _extract_product_url(soup, url)
        
        # Resolve company domain from product URL
        company_domain = None
        if product_url:
            try:
                parsed = urlparse(product_url)
                company_domain = parsed.netloc.lower()
                # Remove www.
                if company_domain.startswith("www."):
                    company_domain = company_domain[4:]
            except Exception:
                pass
        
        # Generate signals
        signals = []
        
        # Recency signals
        recency_signal = _calculate_recency_signal(launch_date)
        if recency_signal:
            signals.append(recency_signal)
        
        # Builder post detection
        if _detect_builder_post(soup, url, text_content):
            signals.append("builder_post")
        
        result = {
            "launch_date": launch_date.isoformat() if launch_date else None,
            "product_name": product_name,
            "product_url": product_url,
            "company_domain": company_domain,
            "signals": signals,
        }
        
        logger.debug(
            "Parsed launch page",
            url=url,
            product_name=product_name,
            launch_date=launch_date.isoformat() if launch_date else None,
            signals=signals,
        )
        
        return result
        
    except Exception as e:
        logger.error("Error parsing launch page", url=url, error=str(e), exc_info=True)
        return {
            "launch_date": None,
            "product_name": None,
            "product_url": None,
            "company_domain": None,
            "signals": [],
        }
