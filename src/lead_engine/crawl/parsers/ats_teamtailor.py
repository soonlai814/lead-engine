"""Teamtailor ATS board parser."""

import re
from typing import Dict

from bs4 import BeautifulSoup
import structlog

from .ats_greenhouse import (
    _load_role_keywords,
    _match_role_type,
    _is_engineering_role,
)

logger = structlog.get_logger()


def parse_ats_board(url: str, html: str, keywords_config: Dict = None) -> Dict:
    """
    Parse Teamtailor ATS board HTML.
    
    Args:
        url: Normalized ATS board URL
        html: HTML content
        keywords_config: Optional keywords config dict
    
    Returns:
        Dictionary with same structure as ats_greenhouse.parse_ats_board
    """
    if keywords_config is None:
        keywords_config = {}
    
    role_keywords = _load_role_keywords(keywords_config)
    
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # Teamtailor uses specific selectors
        job_elements = []
        
        # Try Teamtailor-specific selectors
        selectors = [
            "div.job",
            "a.job-title",
            "[data-job-id]",
            ".job-item",
            "div[data-qa='job-name']",
            ".job-listing",
            "li.job",
            "article.job",
            "[data-teamtailor-job-id]",
        ]
        
        for selector in selectors:
            job_elements = soup.select(selector)
            if job_elements:
                break
        
        # Fallback: look for job links
        if not job_elements:
            all_links = soup.find_all("a", href=True)
            job_elements = [
                link for link in all_links
                if any(kw in link.get_text().lower() for kw in ["engineer", "developer", "software"])
            ]
        
        job_titles = []
        all_roles_detected = set()
        engineering_count = 0
        
        for element in job_elements:
            title_text = element.get_text(strip=True)
            
            # Try to find title in Teamtailor structures
            title_elem = element.find(class_=re.compile(r"job-title|title|name|heading", re.I))
            if title_elem:
                title_text = title_elem.get_text(strip=True)
            
            if not title_text or len(title_text) < 3:
                continue
            
            job_titles.append(title_text)
            
            matched_roles = _match_role_type(title_text, role_keywords)
            all_roles_detected.update(matched_roles)
            
            if _is_engineering_role(title_text, matched_roles):
                engineering_count += 1
        
        # Extract company website URL
        company_website_url = None
        
        website_links = soup.find_all("a", href=True)
        for link in website_links:
            href = link.get("href", "")
            text = link.get_text(strip=True).lower()
            
            if any(kw in text for kw in ["website", "homepage", "company"]):
                if href.startswith("http"):
                    company_website_url = href
                    break
        
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
            "job_titles": job_titles[:20],
            "company_website_url": company_website_url,
            "signals": signals,
        }
        
        logger.debug("Parsed Teamtailor board", url=url, jobs=len(job_titles), engineering=engineering_count)
        return result
        
    except Exception as e:
        logger.error("Error parsing Teamtailor board", url=url, error=str(e), exc_info=True)
        return {
            "jobs_count": 0,
            "engineering_roles_count": 0,
            "roles_detected": [],
            "job_titles": [],
            "company_website_url": None,
            "signals": [],
        }

