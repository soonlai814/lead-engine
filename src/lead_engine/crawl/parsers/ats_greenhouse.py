"""Greenhouse ATS board parser."""

import re
from typing import Dict, List, Set

from bs4 import BeautifulSoup
import structlog

logger = structlog.get_logger()


def _load_role_keywords(keywords_config: Dict) -> Dict[str, List[str]]:
    """Load role keywords from config."""
    role_keywords = {}
    role_config = keywords_config.get("role_keywords", {})
    
    for role_type, keywords in role_config.items():
        role_keywords[role_type] = [kw.lower() for kw in keywords]
    
    return role_keywords


def _match_role_type(job_title: str, role_keywords: Dict[str, List[str]]) -> Set[str]:
    """
    Match job title to role types based on keywords.
    
    Returns set of matched role types (backend, frontend, ml_ai, etc.)
    """
    title_lower = job_title.lower()
    matched_roles = set()
    
    for role_type, keywords in role_keywords.items():
        for keyword in keywords:
            if keyword in title_lower:
                matched_roles.add(role_type)
                break
    
    return matched_roles


def _is_engineering_role(job_title: str, matched_roles: Set[str]) -> bool:
    """Check if job is an engineering role."""
    engineering_keywords = [
        "engineer", "developer", "programmer", "developer", "architect",
        "sre", "devops", "swe", "software"
    ]
    
    title_lower = job_title.lower()
    
    # Check if matched roles include engineering types
    engineering_role_types = {"backend", "frontend", "fullstack", "devops", "ml_ai", "data", "web3"}
    if matched_roles & engineering_role_types:
        return True
    
    # Check title directly
    return any(kw in title_lower for kw in engineering_keywords)


def parse_ats_board(url: str, html: str, keywords_config: Dict = None) -> Dict:
    """
    Parse Greenhouse ATS board HTML.
    
    Args:
        url: Normalized ATS board URL
        html: HTML content
        keywords_config: Optional keywords config dict
    
    Returns:
        Dictionary with:
        - jobs_count: int
        - engineering_roles_count: int
        - roles_detected: list[str] (taxonomy tags: backend, frontend, ml_ai, etc.)
        - job_titles: list[str] (optional)
        - company_website_url: str (best effort)
        - signals: list[str] (ats_board_found, hiring_engineering, etc.)
    """
    if keywords_config is None:
        keywords_config = {}
    
    role_keywords = _load_role_keywords(keywords_config)
    
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # Greenhouse uses various selectors - try common ones
        job_elements = []
        
        # Try different Greenhouse selectors
        selectors = [
            "div.opening",
            "div[data-department]",
            "a.opening",
            "tr.job",
            ".job-listing",
            "[data-job-id]",
        ]
        
        for selector in selectors:
            job_elements = soup.select(selector)
            if job_elements:
                break
        
        # Fallback: look for links that might be job postings
        if not job_elements:
            # Look for links with job-related text
            all_links = soup.find_all("a", href=True)
            job_elements = [
                link for link in all_links
                if any(kw in link.get_text().lower() for kw in ["engineer", "developer", "software", "job"])
            ]
        
        job_titles = []
        all_roles_detected = set()
        engineering_count = 0
        
        for element in job_elements:
            # Extract job title
            title_text = element.get_text(strip=True)
            
            # Try to find title in common Greenhouse structures
            title_elem = element.find(class_=re.compile(r"title|name|job-title", re.I))
            if title_elem:
                title_text = title_elem.get_text(strip=True)
            
            if not title_text or len(title_text) < 3:
                continue
            
            job_titles.append(title_text)
            
            # Match role types
            matched_roles = _match_role_type(title_text, role_keywords)
            all_roles_detected.update(matched_roles)
            
            # Check if engineering role
            if _is_engineering_role(title_text, matched_roles):
                engineering_count += 1
        
        # Extract company website URL (best effort)
        company_website_url = None
        
        # Look for company website link
        website_links = soup.find_all("a", href=True)
        for link in website_links:
            href = link.get("href", "")
            text = link.get_text(strip=True).lower()
            
            if any(kw in text for kw in ["website", "homepage", "company", "about"]):
                if href.startswith("http"):
                    company_website_url = href
                    break
        
        # Fallback: look for meta tags or JSON-LD
        if not company_website_url:
            meta_url = soup.find("meta", property="og:url")
            if meta_url and meta_url.get("content"):
                company_website_url = meta_url["content"]
        
        # Generate signals
        signals = ["ats_board_found"]
        
        if engineering_count > 0:
            signals.append("hiring_engineering")
        
        if "ml_ai" in all_roles_detected:
            signals.append("hiring_ai")
        
        if "web3" in all_roles_detected:
            signals.append("hiring_web3")
        
        if "devops" in all_roles_detected:
            signals.append("hiring_devops")
        
        result = {
            "jobs_count": len(job_titles),
            "engineering_roles_count": engineering_count,
            "roles_detected": sorted(list(all_roles_detected)),
            "job_titles": job_titles[:20],  # Limit to first 20
            "company_website_url": company_website_url,
            "signals": signals,
        }
        
        logger.debug("Parsed Greenhouse board", url=url, jobs=len(job_titles), engineering=engineering_count)
        return result
        
    except Exception as e:
        logger.error("Error parsing Greenhouse board", url=url, error=str(e), exc_info=True)
        return {
            "jobs_count": 0,
            "engineering_roles_count": 0,
            "roles_detected": [],
            "job_titles": [],
            "company_website_url": None,
            "signals": [],
        }

