"""Outreach note generator."""

from typing import Dict, List

import structlog

logger = structlog.get_logger()


def get_top_signals(snapshot: Dict, limit: int = 3) -> List[str]:
    """
    Get top N signals from snapshot.
    
    Prioritizes strong signals like hiring, launches, funding.
    """
    signals = snapshot.get("signals", [])
    
    # Priority order for signals
    priority_signals = [
        "recent_launch_0_30d",
        "recent_launch_31_90d",
        "accelerator_member",
        "recent_funding",
        "hiring_engineering",
        "hiring_ai",
        "hiring_web3",
        "ecosystem_listed",
        "ats_board_found",
    ]
    
    # Sort signals by priority
    sorted_signals = []
    for priority_sig in priority_signals:
        if priority_sig in signals:
            sorted_signals.append(priority_sig)
    
    # Add any remaining signals
    for sig in signals:
        if sig not in sorted_signals:
            sorted_signals.append(sig)
    
    return sorted_signals[:limit]


def generate_outreach_note(
    company: Dict,
    snapshot: Dict,
    classification: Dict,
    scores: Dict,
    keywords_config: Dict = None,
) -> str:
    """
    Generate 1-line outreach note using top evidence.
    
    Args:
        company: Company record dict
        snapshot: SignalSnapshot dict
        classification: Classification result dict
        scores: Scoring result dict
        keywords_config: Optional keywords config dict (for templates)
    
    Returns:
        Outreach note string (1 line)
    """
    if keywords_config is None:
        keywords_config = {}
    
    signals = snapshot.get("signals", [])
    signal_details = snapshot.get("signal_details", {})
    route_flag = scores.get("route_flag", "ignore")
    
    # Get top signals
    top_signals = get_top_signals(snapshot, limit=2)
    
    # Generate note based on top signal
    note = ""
    
    # Hiring-based notes
    if "hiring_engineering" in signals or "ats_board_found" in signals:
        roles_detected = signal_details.get("roles_detected", [])
        engineering_count = signal_details.get("engineering_roles_count", 0)
        
        if roles_detected:
            role_str = "/".join(roles_detected[:2])  # First 2 roles
            note = f"Noticed you're hiring {role_str} roles — execution bandwidth is usually tight at this stage. Happy to help speed things up."
        elif engineering_count > 0:
            note = f"Noticed you're hiring {engineering_count} engineering roles — execution bandwidth is usually tight at this stage. Happy to help speed things up."
        else:
            note = "Noticed you're hiring — execution bandwidth is usually tight at this stage. Happy to help speed things up."
    
    # Launch-based notes
    elif "recent_launch_0_30d" in signals or "recent_launch_31_90d" in signals:
        product_name = signal_details.get("product_name", "")
        if product_name:
            note = f"Saw your recent launch of {product_name} — happy to share a quick teardown to speed up iteration."
        else:
            note = "Saw your recent launch — happy to share a quick teardown to speed up iteration."
    
    # Accelerator/funding notes
    elif "accelerator_member" in signals:
        accelerator_name = signal_details.get("accelerator_name", "an accelerator")
        note = f"Noticed you're part of {accelerator_name} — congrats! Happy to help with execution bandwidth."
    
    elif "recent_funding" in signals:
        funding_round = signal_details.get("funding_round", "funding")
        note = f"Congrats on your {funding_round} round! Happy to help with execution bandwidth as you scale."
    
    # Partnership notes
    elif route_flag == "outreach_partnership":
        note = "Looks like you ship MVPs for clients — open to a partnership for overflow engineering + AI/Web3 builds?"
    
    # Default note
    else:
        note = "Would love to explore how we can help with your technical execution needs."
    
    logger.debug("Generated outreach note", note=note[:50])
    return note

