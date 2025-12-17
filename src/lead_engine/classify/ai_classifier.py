"""AI-based business type classifier (fallback)."""

from typing import Dict

import structlog

logger = structlog.get_logger()


def classify_with_ai(domain: str, meta: Dict, nav_links: List[str], excerpt: str) -> Dict:
    """
    Classify business type using AI (fallback for unknown/low-confidence cases).
    
    Args:
        domain: Company domain
        meta: Dictionary with title, description
        nav_links: List of navigation link texts
        excerpt: Text excerpt (2-4k chars)
    
    Returns:
        Dictionary with:
        - business_type: BusinessType enum value
        - confidence: float 0..1
        - reasons: list[str] (3 bullets)
        - partnership_hint: bool
    
    Requirements:
        - Trigger only if rule result is unknown OR confidence < threshold
        - Cost controls: max calls/day, cache by domain
        - Strict JSON output parsing
    """
    # TODO: Phase 5.1 - Implement AI classifier
    # - Prepare minimal inputs
    # - Call AI provider (OpenAI/Anthropic - TBD)
    # - Parse strict JSON response
    # - Cache results
    
    logger.warning("classify_with_ai not yet implemented (Phase 5)", domain=domain)
    return {
        "business_type": "unknown",
        "confidence": 0.0,
        "reasons": [],
        "partnership_hint": False,
    }

