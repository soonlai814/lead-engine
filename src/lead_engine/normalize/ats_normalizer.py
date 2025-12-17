"""ATS-specific URL normalization."""

from typing import Optional
from urllib.parse import urlparse, urlunparse

import structlog

from .url_normalizer import normalize_url

logger = structlog.get_logger()


def normalize_ats_url(url: str) -> Optional[str]:
    """
    Normalize ATS job posting URL to board root URL.
    
    Supported ATS:
    - Greenhouse: boards.greenhouse.io/<slug> -> boards.greenhouse.io/<slug>
    - Lever: jobs.lever.co/<slug> -> jobs.lever.co/<slug>
    - Ashby: jobs.ashbyhq.com/<slug> -> jobs.ashbyhq.com/<slug>
    - Workable: apply.workable.com/<slug> -> apply.workable.com/<slug>
    - SmartRecruiters: careers.smartrecruiters.com/<slug> -> careers.smartrecruiters.com/<slug>
    - Teamtailor: <slug>.teamtailor.com/jobs/<job-id> -> <slug>.teamtailor.com/jobs
    - Recruitee: <slug>.recruitee.com/o/<job> -> <slug>.recruitee.com
    
    Args:
        url: Raw ATS URL
    
    Returns:
        Normalized board root URL, or None if not an ATS URL
    """
    if not url:
        return None
    
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path
    
    # Greenhouse: boards.greenhouse.io/<slug>
    if "boards.greenhouse.io" in netloc:
        # Extract slug from path (first segment)
        parts = [p for p in path.split("/") if p]
        if parts:
            slug = parts[0]
            normalized = f"https://boards.greenhouse.io/{slug}"
            return normalize_url(normalized)
        return None
    
    # Lever: jobs.lever.co/<slug>
    elif "jobs.lever.co" in netloc:
        parts = [p for p in path.split("/") if p]
        if parts:
            slug = parts[0]
            normalized = f"https://jobs.lever.co/{slug}"
            return normalize_url(normalized)
        return None
    
    # Ashby: jobs.ashbyhq.com/<slug>
    elif "jobs.ashbyhq.com" in netloc:
        parts = [p for p in path.split("/") if p]
        if parts:
            slug = parts[0]
            normalized = f"https://jobs.ashbyhq.com/{slug}"
            return normalize_url(normalized)
        return None
    
    # Workable: apply.workable.com/<slug>
    elif "apply.workable.com" in netloc:
        parts = [p for p in path.split("/") if p]
        if parts:
            slug = parts[0]
            normalized = f"https://apply.workable.com/{slug}"
            return normalize_url(normalized)
        return None
    
    # SmartRecruiters: careers.smartrecruiters.com/<slug>
    elif "careers.smartrecruiters.com" in netloc:
        parts = [p for p in path.split("/") if p]
        if parts:
            slug = parts[0]
            normalized = f"https://careers.smartrecruiters.com/{slug}"
            return normalize_url(normalized)
        return None
    
    # Teamtailor: <slug>.teamtailor.com/jobs/<job-id> -> <slug>.teamtailor.com/jobs
    elif ".teamtailor.com" in netloc:
        # Extract subdomain (slug)
        subdomain = netloc.split(".teamtailor.com")[0]
        normalized = f"https://{subdomain}.teamtailor.com/jobs"
        return normalize_url(normalized)
    
    # Recruitee: <slug>.recruitee.com/o/<job> -> <slug>.recruitee.com
    elif ".recruitee.com" in netloc:
        # Extract subdomain (slug)
        subdomain = netloc.split(".recruitee.com")[0]
        normalized = f"https://{subdomain}.recruitee.com"
        return normalize_url(normalized)
    
    # Not an ATS URL
    return None


def is_ats_url(url: str) -> bool:
    """Check if URL is from a known ATS."""
    if not url:
        return False
    
    ats_domains = [
        "boards.greenhouse.io",
        "jobs.lever.co",
        "jobs.ashbyhq.com",
        "apply.workable.com",
        "careers.smartrecruiters.com",
        "teamtailor.com",
        "recruitee.com",
    ]
    
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        return any(domain in netloc for domain in ats_domains)
    except Exception:
        return False

