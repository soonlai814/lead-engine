"""Lead scoring module."""

from typing import Dict

import structlog

from ..storage.models import BusinessType

logger = structlog.get_logger()


def score_lead(company: Dict, snapshot: Dict, classification: Dict, scoring_config: Dict = None) -> Dict:
    """
    Compute MVP intent score and partnership fit score.
    
    Args:
        company: Company record dict
        snapshot: SignalSnapshot dict (latest signals)
        classification: Classification result dict
        scoring_config: Optional scoring config dict
    
    Returns:
        Dictionary with:
        - mvp_intent_score: int
        - partnership_fit_score: int
        - score_breakdown: dict (detailed breakdown of scoring)
    """
    if scoring_config is None:
        scoring_config = {}
    
    weights = scoring_config.get("mvp_intent_weights", {})
    penalties = scoring_config.get("mvp_intent_penalties", {})
    partnership_weights = scoring_config.get("partnership_fit_weights", {})
    
    signals = snapshot.get("signals", [])
    signal_details = snapshot.get("signal_details", {})
    
    mvp_score = 0
    breakdown = {}
    
    # MVP Intent Scoring
    
    # Hiring signals
    if "ats_board_found" in signals:
        mvp_score += weights.get("ats_board_exists", 3)
        breakdown["ats_board_found"] = weights.get("ats_board_exists", 3)
    
    engineering_count = signal_details.get("engineering_roles_count", 0)
    if engineering_count >= 3:
        mvp_score += weights.get("engineering_roles_count_3plus", 3)
        breakdown["engineering_roles_3plus"] = weights.get("engineering_roles_count_3plus", 3)
    elif engineering_count >= 1:
        mvp_score += weights.get("engineering_roles_count_1plus", 2)
        breakdown["engineering_roles_1plus"] = weights.get("engineering_roles_count_1plus", 2)
    
    # Role tags
    roles_detected = signal_details.get("roles_detected", [])
    relevant_roles = {"backend", "fullstack", "devops", "ml_ai"}
    if any(role in roles_detected for role in relevant_roles):
        mvp_score += weights.get("role_tags_backend_fullstack_devops_ml", 2)
        breakdown["relevant_role_tags"] = weights.get("role_tags_backend_fullstack_devops_ml", 2)
    
    # Product indicators
    if "product_pricing_found" in signals or "pricing_page_detected" in signals:
        mvp_score += weights.get("pricing_page_detected", 2)
        breakdown["pricing_page"] = weights.get("pricing_page_detected", 2)
    
    if "product_docs_found" in signals or "docs_api_detected" in signals:
        mvp_score += weights.get("docs_api_detected", 2)
        breakdown["docs_api"] = weights.get("docs_api_detected", 2)
    
    # Recency signals
    if "recent_launch_0_30d" in signals:
        mvp_score += weights.get("recent_launch_0_30d", 3)
        breakdown["recent_launch_0_30d"] = weights.get("recent_launch_0_30d", 3)
    elif "recent_launch_31_90d" in signals:
        mvp_score += weights.get("recent_launch_31_90d", 1)
        breakdown["recent_launch_31_90d"] = weights.get("recent_launch_31_90d", 1)
    
    # Funding/accelerator
    if "accelerator_member" in signals:
        mvp_score += weights.get("accelerator_member", 2)
        breakdown["accelerator_member"] = weights.get("accelerator_member", 2)
    
    if "recent_funding" in signals:
        mvp_score += weights.get("recent_funding", 2)
        breakdown["recent_funding"] = weights.get("recent_funding", 2)
    
    # Ecosystem
    if "ecosystem_listed" in signals:
        mvp_score += weights.get("ecosystem_listed", 1)
        breakdown["ecosystem_listed"] = weights.get("ecosystem_listed", 1)
    
    # Apply penalties based on classification
    business_type = classification.get("business_type", BusinessType.UNKNOWN.value)
    
    if business_type == BusinessType.SERVICE_AGENCY.value or business_type == BusinessType.CONSULTANCY.value or business_type == BusinessType.SYSTEM_INTEGRATOR.value:
        penalty = penalties.get("services_classification", -8)
        mvp_score += penalty
        breakdown["services_penalty"] = penalty
    
    if business_type == BusinessType.STAFFING_RECRUITER.value:
        penalty = penalties.get("staffing_classification", -10)
        mvp_score += penalty
        breakdown["staffing_penalty"] = penalty
    
    # Ensure score doesn't go below 0
    mvp_score = max(0, mvp_score)
    
    # Partnership Fit Score
    partnership_score = 0
    partnership_breakdown = {}
    
    # Only compute if it's a service-type company
    if business_type in [BusinessType.SERVICE_AGENCY.value, BusinessType.CONSULTANCY.value, BusinessType.SYSTEM_INTEGRATOR.value]:
        if business_type:
            partnership_score += partnership_weights.get("services_type_confirmed", 2)
            partnership_breakdown["services_type_confirmed"] = partnership_weights.get("services_type_confirmed", 2)
        
        # Check if they offer MVP/dev services
        if any(kw in str(signal_details).lower() for kw in ["mvp", "development", "build", "product"]):
            partnership_score += partnership_weights.get("offers_mvp_dev", 2)
            partnership_breakdown["offers_mvp_dev"] = partnership_weights.get("offers_mvp_dev", 2)
        
        # Check if they're hiring devs
        if engineering_count > 0:
            partnership_score += partnership_weights.get("hiring_devs", 2)
            partnership_breakdown["hiring_devs"] = partnership_weights.get("hiring_devs", 2)
        
        # Check for niche match
        if any(role in roles_detected for role in ["ml_ai", "web3"]) or any(sig in signals for sig in ["hiring_ai", "hiring_web3"]):
            partnership_score += partnership_weights.get("niche_match_ai_web3_saas", 2)
            partnership_breakdown["niche_match"] = partnership_weights.get("niche_match_ai_web3_saas", 2)
        
        # Case studies (would need to check company pages)
        # For now, skip this check
    
    result = {
        "mvp_intent_score": mvp_score,
        "partnership_fit_score": partnership_score,
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

