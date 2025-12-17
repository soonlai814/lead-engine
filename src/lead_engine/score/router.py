"""Lead routing module."""

from typing import Dict

import structlog

from ..storage.models import BusinessType, RecommendedChannel, RouteFlag

logger = structlog.get_logger()


def route_lead(classification: Dict, scores: Dict, snapshot: Dict = None, routing_config: Dict = None) -> Dict:
    """
    Determine routing and recommended outreach channel.
    
    Args:
        classification: Classification result dict
        scores: Scoring result dict
        snapshot: Optional SignalSnapshot dict (for signal-based routing)
        routing_config: Optional routing config dict
    
    Returns:
        Dictionary with:
        - route_flag: RouteFlag enum value (outreach_mvp_client|outreach_partnership|ignore)
        - recommended_channel: RecommendedChannel enum value
    """
    if routing_config is None:
        routing_config = {}
    
    if snapshot is None:
        snapshot = {}
    
    business_type = classification.get("business_type", BusinessType.UNKNOWN.value)
    signals = snapshot.get("signals", [])
    signal_details = snapshot.get("signal_details", {})
    
    route_flag = RouteFlag.IGNORE
    recommended_channel = None
    
    # Apply routing rules
    routing_rules = routing_config.get("routing", {})
    strong_hiring_threshold = routing_rules.get("strong_hiring_threshold", 3)
    
    # Rule 1: Product company → MVP client
    if business_type == BusinessType.PRODUCT_COMPANY.value:
        route_flag = RouteFlag.OUTREACH_MVP_CLIENT
        # Determine channel based on signals
        if "recent_launch_0_30d" in signals or "recent_launch_31_90d" in signals:
            recommended_channel = RecommendedChannel.X_DM
        elif "ecosystem_listed" in signals:
            recommended_channel = RecommendedChannel.X_DM
        else:
            recommended_channel = RecommendedChannel.LINKEDIN_DM
    
    # Rule 2: Service types → Partnership
    elif business_type in [
        BusinessType.SERVICE_AGENCY.value,
        BusinessType.CONSULTANCY.value,
        BusinessType.SYSTEM_INTEGRATOR.value,
    ]:
        route_flag = RouteFlag.OUTREACH_PARTNERSHIP
        recommended_channel = RecommendedChannel.LINKEDIN_DM
    
    # Rule 3: Staffing → Ignore
    elif business_type == BusinessType.STAFFING_RECRUITER.value:
        route_flag = RouteFlag.IGNORE
    
    # Rule 4: Unknown → Check hiring signals
    elif business_type == BusinessType.UNKNOWN.value:
        engineering_count = signal_details.get("engineering_roles_count", 0)
        if engineering_count >= strong_hiring_threshold or "hiring_engineering" in signals:
            route_flag = RouteFlag.OUTREACH_MVP_CLIENT
            recommended_channel = RecommendedChannel.LINKEDIN_DM
        else:
            route_flag = RouteFlag.IGNORE
    
    result = {
        "route_flag": route_flag.value if isinstance(route_flag, RouteFlag) else route_flag,
        "recommended_channel": recommended_channel.value if isinstance(recommended_channel, RecommendedChannel) else recommended_channel,
    }
    
    logger.debug(
        "Routing completed",
        business_type=business_type,
        route_flag=result["route_flag"],
        recommended_channel=result["recommended_channel"],
    )
    
    return result

