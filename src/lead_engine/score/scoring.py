"""Lead scoring module."""

from typing import Dict

import structlog

from ..storage.models import BusinessType

logger = structlog.get_logger()


def _detect_founding_language(signals: list, signal_details: dict) -> bool:
    """Detect founding/0to1 language in job titles or snippets."""
    founding_keywords = ["founding", "founder", "0 to 1", "0-1", "greenfield", "MVP"]
    
    # Check job titles
    job_titles = signal_details.get("job_titles", [])
    for title in job_titles:
        title_lower = str(title).lower()
        if any(kw in title_lower for kw in founding_keywords):
            return True
    
    # Check signals
    if any("founding" in str(s).lower() for s in signals):
        return True
    
    return False


def _detect_enterprise_noise(signals: list, signal_details: dict, keywords_config: dict = None) -> bool:
    """Detect enterprise noise indicators."""
    if keywords_config is None:
        return False
    
    enterprise_keywords = keywords_config.get("enterprise_indicators", {}).get("enterprise_noise", [])
    huge_hiring_keywords = keywords_config.get("enterprise_indicators", {}).get("huge_hiring", [])
    
    # Check job titles and signals
    job_titles = signal_details.get("job_titles", [])
    all_text = " ".join([str(t) for t in job_titles] + [str(s) for s in signals]).lower()
    
    for keyword in enterprise_keywords + huge_hiring_keywords:
        if keyword.lower() in all_text:
            return True
    
    return False


def score_lead(company: Dict, snapshot: Dict, classification: Dict, scoring_config: Dict = None, keywords_config: Dict = None) -> Dict:
    """
    Compute MVP intent score and partnership fit score (0-100 scale).
    
    Args:
        company: Company record dict
        snapshot: SignalSnapshot dict (latest signals)
        classification: Classification result dict
        scoring_config: Optional scoring config dict
        keywords_config: Optional keywords config dict (for enterprise detection)
    
    Returns:
        Dictionary with:
        - mvp_intent_score: int (0-100)
        - partnership_fit_score: int (0-100)
        - score_breakdown: dict (detailed breakdown of scoring)
    """
    if scoring_config is None:
        scoring_config = {}
    
    if keywords_config is None:
        keywords_config = {}
    
    weights = scoring_config.get("mvp_intent_weights", {})
    penalties = scoring_config.get("mvp_intent_penalties", {})
    partnership_weights = scoring_config.get("partnership_fit_weights", {})
    partnership_penalties = scoring_config.get("partnership_fit_penalties", {})
    
    signals = snapshot.get("signals", [])
    signal_details = snapshot.get("signal_details", {})
    
    mvp_score = 0
    breakdown = {}
    
    # MVP Intent Scoring (0-100 scale)
    
    # Hiring signals (weight dominant)
    if "ats_board_found" in signals:
        score = weights.get("ats_board_exists", 20)
        mvp_score += score
        breakdown["ats_board_found"] = score
    
    # Engineering roles count (bucketed)
    engineering_count = signal_details.get("engineering_roles_count", 0)
    if 1 <= engineering_count <= 2:
        score = weights.get("engineering_roles_count", {}).get("1_2", 8)
        mvp_score += score
        breakdown["engineering_roles_1_2"] = score
    elif 3 <= engineering_count <= 5:
        score = weights.get("engineering_roles_count", {}).get("3_5", 15)
        mvp_score += score
        breakdown["engineering_roles_3_5"] = score
    elif 6 <= engineering_count <= 10:
        score = weights.get("engineering_roles_count", {}).get("6_10", 20)
        mvp_score += score
        breakdown["engineering_roles_6_10"] = score
    elif engineering_count >= 11:
        score = weights.get("engineering_roles_count", {}).get("11_plus", 12)
        mvp_score += score
        breakdown["engineering_roles_11_plus"] = score
    
    # Founding/0to1 language
    if _detect_founding_language(signals, signal_details):
        score = weights.get("founding_0to1_language", 12)
        mvp_score += score
        breakdown["founding_0to1_language"] = score
    
    # Role tags (backend/fullstack/devops/ml)
    roles_detected = signal_details.get("roles_detected", [])
    relevant_roles = {"backend", "fullstack", "devops", "ml_ai"}
    if any(role in roles_detected for role in relevant_roles):
        score = weights.get("role_tags_backend_fullstack_devops_ml", 8)
        mvp_score += score
        breakdown["relevant_role_tags"] = score
    
    # Product engineer / engineering generalist
    job_titles = signal_details.get("job_titles", [])
    if any("product engineer" in str(t).lower() or "engineering generalist" in str(t).lower() for t in job_titles):
        score = weights.get("product_engineer_generalist", 6)
        mvp_score += score
        breakdown["product_engineer_generalist"] = score
    
    # Product signals (quality filter)
    if "product_pricing_found" in signals or "pricing_page_detected" in signals:
        score = weights.get("pricing_page_detected", 8)
        mvp_score += score
        breakdown["pricing_page"] = score
    
    if "product_docs_found" in signals or "docs_api_detected" in signals:
        score = weights.get("docs_api_detected", 8)
        mvp_score += score
        breakdown["docs_api"] = score
    
    if "integrations_status_page_detected" in signals:
        score = weights.get("integrations_status_page_detected", 4)
        mvp_score += score
        breakdown["integrations_status_page"] = score
    
    # Recency multipliers (secondary)
    if "recent_launch_0_30d" in signals:
        score = weights.get("recent_launch_0_30d", 10)
        mvp_score += score
        breakdown["recent_launch_0_30d"] = score
    elif "recent_launch_31_90d" in signals:
        score = weights.get("recent_launch_31_90d", 4)
        mvp_score += score
        breakdown["recent_launch_31_90d"] = score
    
    # Funding/accelerator
    # Check for recent funding (pre-seed/seed within 12 months)
    if "recent_funding" in signals:
        # Check funding round from signal_details to determine score
        funding_round = signal_details.get("funding_round", "").lower()
        if funding_round in ["pre-seed", "seed"]:
            score = weights.get("preseed_seed_funding_12mo", 10)
            mvp_score += score
            breakdown["preseed_seed_funding"] = score
        elif "series a" in funding_round:
            score = weights.get("series_a_18mo", 8)
            mvp_score += score
            breakdown["series_a_funding"] = score
        else:
            # Generic recent funding
            score = weights.get("preseed_seed_funding_12mo", 10)
            mvp_score += score
            breakdown["recent_funding"] = score
    
    if "accelerator_member" in signals:
        score = weights.get("accelerator_member", 8)
        mvp_score += score
        breakdown["accelerator_member"] = score
    
    # Ecosystem
    if "ecosystem_listed" in signals or "ecosystem_listed_grant_hackathon" in signals:
        score = weights.get("ecosystem_listed_grant_hackathon", 4)
        mvp_score += score
        breakdown["ecosystem_listed"] = score
    
    # Apply penalties (hard filters)
    business_type = classification.get("business_type", BusinessType.UNKNOWN.value)
    
    if business_type in [BusinessType.SERVICE_AGENCY.value, BusinessType.CONSULTANCY.value, BusinessType.SYSTEM_INTEGRATOR.value]:
        penalty = penalties.get("services_agency_consultancy", -25)
        mvp_score += penalty
        breakdown["services_penalty"] = penalty
    
    if business_type == BusinessType.STAFFING_RECRUITER.value:
        penalty = penalties.get("staffing_recruiter", -40)
        mvp_score += penalty
        breakdown["staffing_penalty"] = penalty
    
    # Enterprise noise penalty
    if _detect_enterprise_noise(signals, signal_details, keywords_config):
        penalty = penalties.get("enterprise_noise_detected", -10)
        mvp_score += penalty
        breakdown["enterprise_noise_penalty"] = penalty
    
    # Huge hiring penalty (check engineering count > 10 is already capped, but check for explicit indicators)
    if _detect_enterprise_noise(signals, signal_details, keywords_config):
        # Already applied above, but check for huge_hiring specifically
        huge_hiring_keywords = keywords_config.get("enterprise_indicators", {}).get("huge_hiring", [])
        all_text = " ".join([str(t) for t in job_titles] + [str(s) for s in signals]).lower()
        if any(kw.lower() in all_text for kw in huge_hiring_keywords):
            penalty = penalties.get("huge_hiring_indicators", -10)
            mvp_score += penalty
            breakdown["huge_hiring_penalty"] = penalty
    
    # Ensure score doesn't go below 0
    mvp_score = max(0, min(100, mvp_score))  # Clamp to 0-100
    
    # Partnership Fit Score (0-100 scale)
    partnership_score = 0
    partnership_breakdown = {}
    
    # Only compute if it's a service-type company
    if business_type in [BusinessType.SERVICE_AGENCY.value, BusinessType.CONSULTANCY.value, BusinessType.SYSTEM_INTEGRATOR.value]:
        # Base score
        score = partnership_weights.get("business_type_services_consultancy_integrator", 20)
        partnership_score += score
        partnership_breakdown["services_type_confirmed"] = score
        
        # Check for product studio / MVP dev mentions
        all_text = " ".join([str(t) for t in job_titles] + [str(s) for s in signals]).lower()
        if any(kw in all_text for kw in ["product studio", "mvp development", "mvp dev"]):
            score = partnership_weights.get("mentions_product_studio_mvp_dev", 10)
            partnership_score += score
            partnership_breakdown["product_studio_mvp_dev"] = score
        
        # Check for white label / overflow / referral mentions
        partnership_keywords = keywords_config.get("partnership_indicators", {}).get("partner_fit", [])
        if any(kw in all_text for kw in partnership_keywords):
            score = partnership_weights.get("mentions_white_label_overflow_referral", 15)
            partnership_score += score
            partnership_breakdown["white_label_overflow_referral"] = score
        
        # Check if they're hiring engineers (capacity pressure)
        if engineering_count > 0:
            score = partnership_weights.get("hiring_engineers_capacity_pressure", 10)
            partnership_score += score
            partnership_breakdown["hiring_engineers"] = score
        
        # Check for niche alignment (AI/Web3/SaaS/dev tooling)
        if any(role in roles_detected for role in ["ml_ai", "web3"]) or any(sig in signals for sig in ["hiring_ai", "hiring_web3"]):
            score = partnership_weights.get("niche_alignment_ai_web3_saas_dev_tooling", 10)
            partnership_score += score
            partnership_breakdown["niche_alignment"] = score
        
        # Case studies / portfolio (would need to check company pages)
        # For now, check if signals suggest strong portfolio
        if "case_studies" in all_text or "portfolio" in all_text:
            score = partnership_weights.get("strong_portfolio_case_studies", 6)
            partnership_score += score
            partnership_breakdown["case_studies"] = score
        
        # Clear inbound channel (newsletter/community)
        if any(kw in all_text for kw in ["newsletter", "community", "blog"]):
            score = partnership_weights.get("clear_inbound_channel_newsletter_community", 6)
            partnership_score += score
            partnership_breakdown["inbound_channel"] = score
        
        # Apply partnership penalties
        if business_type == BusinessType.STAFFING_RECRUITER.value:
            penalty = partnership_penalties.get("staffing_recruiter_language", -30)
            partnership_score += penalty
            partnership_breakdown["staffing_penalty"] = penalty
        
        # Extremely broad agency penalty
        if "we do everything" in all_text or "full service" in all_text:
            penalty = partnership_penalties.get("extremely_broad_we_do_everything_agency", -10)
            partnership_score += penalty
            partnership_breakdown["broad_agency_penalty"] = penalty
        
        # Ensure score doesn't go below 0
        partnership_score = max(0, min(100, partnership_score))  # Clamp to 0-100
    
    result = {
        "mvp_intent_score": int(mvp_score),
        "partnership_fit_score": int(partnership_score),
        "score_breakdown": {
            "mvp": breakdown,
            "partnership": partnership_breakdown,
        },
    }
    
    logger.debug(
        "Scoring completed",
        company_domain=company.get("company_domain"),
        mvp_score=mvp_score,
        partnership_score=partnership_score,
    )
    
    return result
