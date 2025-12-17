"""URL normalization utilities."""

from urllib.parse import parse_qs, urlparse, urlunparse

import structlog

logger = structlog.get_logger()

# Query parameters to remove during normalization
DENYLIST_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "fbclid",
    "gclid",
    "source",
}


def normalize_url(url: str) -> str:
    """
    Normalize a URL by removing tracking params, normalizing scheme/host, etc.
    
    Args:
        url: Raw URL string
    
    Returns:
        Normalized URL string
    
    Steps:
        1. Parse URL
        2. Lowercase scheme+host
        3. Remove default ports
        4. Remove query params matching denylist
        5. Strip trailing slash (consistent rule)
        6. Return normalized string
    """
    if not url:
        return url
    
    try:
        parsed = urlparse(url)
        
        # Lowercase scheme and host
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        
        # Remove default ports
        if ":" in netloc:
            host, port = netloc.rsplit(":", 1)
            if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
                netloc = host
        
        # Remove denylist query params
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        filtered_params = {k: v for k, v in query_params.items() if k.lower() not in DENYLIST_PARAMS}
        
        # Rebuild query string
        from urllib.parse import urlencode
        query_string = urlencode(filtered_params, doseq=True) if filtered_params else ""
        
        # Reconstruct URL
        path = parsed.path.rstrip("/")  # Strip trailing slash
        fragment = ""  # Strip fragment
        
        normalized = urlunparse((scheme, netloc, path, parsed.params, query_string, fragment))
        
        return normalized
        
    except Exception as e:
        logger.warning("Error normalizing URL, returning original", url=url, error=str(e))
        return url


def normalize_to_canonical(url: str, html: str) -> str:
    """
    Normalize URL using rel=canonical if present in HTML.
    
    Args:
        url: Original URL
        html: HTML content to check for canonical link
    
    Returns:
        Canonical URL if found, otherwise normalized original URL
    """
    try:
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, "html.parser")
        canonical_link = soup.find("link", rel="canonical")
        
        if canonical_link and canonical_link.get("href"):
            canonical_url = canonical_link["href"]
            # Handle relative URLs
            from urllib.parse import urljoin
            canonical_url = urljoin(url, canonical_url)
            return normalize_url(canonical_url)
        
        return normalize_url(url)
        
    except Exception as e:
        logger.warning("Error extracting canonical URL, using normalized original", url=url, error=str(e))
        return normalize_url(url)

