"""Outreach note generator."""

import random
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


def _get_template(keywords_config: Dict, template_key: str) -> str:
    """Get a random template from config, or return default."""
    templates = keywords_config.get("outreach_templates", {}).get(template_key, [])
    if templates:
        return random.choice(templates)
    return None


def generate_outreach_note(
    company: Dict,
    snapshot: Dict,
    classification: Dict,
    scores: Dict,
    keywords_config: Dict = None,
) -> str:
    """
    Generate 1-line outreach note using top evidence and templates from config.
    
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
    
    # Generate note based on top signal, using templates from config
    
    # Hiring-based notes
    if "hiring_engineering" in signals or "ats_board_found" in signals:
        roles_detected = signal_details.get("roles_detected", [])
        engineering_count = signal_details.get("engineering_roles_count", 0)
        
        # Try to use template from config
        template = _get_template(keywords_config, "hiring_engineering")
        if template:
            if roles_detected:
                role_str = "/".join(roles_detected[:2])
                try:
                    note = template.format(roles=role_str)
                except KeyError:
                    note = template.replace("{roles}", role_str)
            else:
                note = template
        else:
            # Fallback to default
            if roles_detected:
                role_str = "/".join(roles_detected[:2])
                note = f"Noticed you're hiring {role_str} roles — execution bandwidth is usually tight at this stage. Happy to help speed things up."
            elif engineering_count > 0:
                note = f"Noticed you're hiring {engineering_count} engineering roles — execution bandwidth is usually tight at this stage. Happy to help speed things up."
            else:
                note = "Noticed you're hiring — execution bandwidth is usually tight at this stage. Happy to help speed things up."
        
        # Check for founding/0to1 language
        job_titles = signal_details.get("job_titles", [])
        if any("founding" in str(t).lower() or "0 to 1" in str(t).lower() or "0-1" in str(t).lower() for t in job_titles):
            note = "Saw you're hiring a founding/full-stack role — teams at this stage usually hit execution bottlenecks. I can ship production MVP increments fast (CTO + delivery)."
    
    # Launch-based notes
    elif "recent_launch_0_30d" in signals or "recent_launch_31_90d" in signals:
        product_name = signal_details.get("product_name", "")
        
        # Try to use template from config
        template = _get_template(keywords_config, "recent_launch")
        if template:
            if product_name:
                try:
                    note = template.format(product_name=product_name)
                except KeyError:
                    note = template.replace("{product_name}", product_name)
            else:
                note = template
        else:
            # Fallback to default
            if product_name:
                note = f"Saw your recent launch of {product_name} — happy to share a quick teardown to speed up iteration."
            else:
                # Use template from requirements
                note = "Congrats on the v1 launch — happy to share a quick teardown + 3 quick wins to speed up the next 2 weeks of shipping."
    
    # Accelerator/funding notes
    elif "accelerator_member" in signals:
        accelerator_name = signal_details.get("accelerator_name", "an accelerator")
        
        # Try to use template from config
        template = _get_template(keywords_config, "accelerator")
        if template:
            try:
                note = template.format(accelerator=accelerator_name)
            except KeyError:
                note = template.replace("{accelerator}", accelerator_name)
        else:
            # Fallback to default
            note = f"Noticed you're part of {accelerator_name} — congrats! Happy to help with execution bandwidth."
    
    elif "recent_funding" in signals or "preseed_seed_funding_12mo" in signals:
        funding_round = signal_details.get("funding_round", "funding")
        accelerator_name = signal_details.get("accelerator_name")
        
        if accelerator_name:
            note = f"Noticed you're part of {accelerator_name} — congrats! Happy to help with execution bandwidth."
        elif funding_round:
            note = f"Congrats on your {funding_round} round! Happy to help with execution bandwidth as you scale."
        else:
            note = "Congrats on your funding round! Happy to help with execution bandwidth as you scale."
    
    elif "accelerator_member" in signals:
        accelerator_name = signal_details.get("accelerator_name", "an accelerator")
        note = f"Noticed you're part of {accelerator_name} — congrats! Happy to help with execution bandwidth."
    
    # Ecosystem-based notes
    elif "ecosystem_listed" in signals or "grant_recipient" in signals or "hackathon_winner" in signals:
        ecosystem_tag = signal_details.get("ecosystem_tag", "")
        program_type = signal_details.get("program_type", "")
        program_name = signal_details.get("program_name", "")
        
        # Try to use template from config
        template = _get_template(keywords_config, "ecosystem")
        if template:
            try:
                note = template.format(
                    ecosystem=ecosystem_tag or "ecosystem",
                    program=program_name or program_type or "program"
                )
            except KeyError:
                note = template.replace("{ecosystem}", ecosystem_tag or "ecosystem")
        else:
            # Fallback to default
            if "grant_recipient" in signals:
                if ecosystem_tag:
                    note = f"Congrats on the {ecosystem_tag} grant! Happy to help with execution bandwidth as you build."
                else:
                    note = "Congrats on the grant! Happy to help with execution bandwidth as you build."
            elif "hackathon_winner" in signals:
                if ecosystem_tag:
                    note = f"Congrats on winning the {ecosystem_tag} hackathon! Happy to help with execution bandwidth as you scale."
                else:
                    note = "Congrats on the hackathon win! Happy to help with execution bandwidth as you scale."
            elif ecosystem_tag:
                note = f"Noticed you're building in the {ecosystem_tag} ecosystem — happy to help with execution bandwidth."
            else:
                note = "Noticed you're building in an ecosystem — happy to help with execution bandwidth."
    
    # Partnership notes
    elif route_flag == "outreach_partnership":
        # Try to use template from config
        template = _get_template(keywords_config, "partnership")
        if template:
            note = template
        else:
            # Fallback to default
            note = "Looks like you ship MVPs for clients — open to a partnership for overflow engineering + AI/Web3 builds?"
        
        # Enhanced partnership note from requirements
        if signal_details.get("roles_detected"):
            note = "Looks like you ship MVPs for clients. Open to a co-delivery partnership? I handle complex backend/AI agents while you run design/PM — fast, clean, and white-label friendly."
    
    # Default note
    else:
        note = "Would love to explore how we can help with your technical execution needs."
    
    logger.debug("Generated outreach note", note=note[:50])
    return note
