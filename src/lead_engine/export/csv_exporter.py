"""CSV exporter for leads."""

import csv
import json
from pathlib import Path
from typing import List

import structlog

logger = structlog.get_logger()


def export_mvp_leads(leads: List[dict], output_path: Path):
    """
    Export MVP leads to CSV.
    
    Args:
        leads: List of lead dictionaries (from database Lead records)
        output_path: Output file path
    """
    if not leads:
        logger.warning("No MVP leads to export")
        return
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    fieldnames = [
        "company_name",
        "company_domain",
        "website_url",
        "primary_source",
        "evidence_url",
        "mvp_intent_score",
        "roles_detected",
        "signals",
        "score_breakdown_json",
        "recommended_channel",
        "outreach_note",
    ]
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for lead in leads:
            # Extract data from Lead record (assuming SQLAlchemy model)
            row = {
                "company_name": getattr(lead, "company_name", "") if hasattr(lead, "company_name") else lead.get("company_name", ""),
                "company_domain": getattr(lead, "company_domain", "") if hasattr(lead, "company_domain") else lead.get("company_domain", ""),
                "website_url": "",
                "primary_source": "",
                "evidence_url": "",
                "mvp_intent_score": getattr(lead, "mvp_intent_score", 0) if hasattr(lead, "mvp_intent_score") else lead.get("mvp_intent_score", 0),
                "roles_detected": "",
                "signals": "",
                "score_breakdown_json": "",
                "recommended_channel": getattr(lead, "recommended_channel", "") if hasattr(lead, "recommended_channel") else lead.get("recommended_channel", ""),
                "outreach_note": getattr(lead, "outreach_note", "") if hasattr(lead, "outreach_note") else lead.get("outreach_note", ""),
            }
            
            # Handle score_breakdown (convert dict to JSON string)
            score_breakdown = getattr(lead, "score_breakdown", {}) if hasattr(lead, "score_breakdown") else lead.get("score_breakdown", {})
            if score_breakdown:
                row["score_breakdown_json"] = json.dumps(score_breakdown)
            
            # Get company info if available
            if hasattr(lead, "company") and lead.company:
                row["company_name"] = lead.company.company_name or row["company_name"]
                row["website_url"] = lead.company.website_url or ""
            
            # Get signal snapshot if available
            # (This would need to be joined/loaded separately)
            
            writer.writerow(row)
    
    logger.info("Exported MVP leads", count=len(leads), path=str(output_path))


def export_partnership_targets(leads: List[dict], output_path: Path):
    """
    Export partnership targets to CSV.
    
    Args:
        leads: List of lead dictionaries (from database Lead records)
        output_path: Output file path
    """
    if not leads:
        logger.warning("No partnership targets to export")
        return
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    fieldnames = [
        "company_name",
        "company_domain",
        "website_url",
        "business_type",
        "partnership_fit_score",
        "signals",
        "score_breakdown_json",
        "suggested_partnership_angle",
    ]
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for lead in leads:
            row = {
                "company_name": getattr(lead, "company_name", "") if hasattr(lead, "company_name") else lead.get("company_name", ""),
                "company_domain": getattr(lead, "company_domain", "") if hasattr(lead, "company_domain") else lead.get("company_domain", ""),
                "website_url": "",
                "business_type": "",
                "partnership_fit_score": getattr(lead, "partnership_fit_score", 0) if hasattr(lead, "partnership_fit_score") else lead.get("partnership_fit_score", 0),
                "signals": "",
                "score_breakdown_json": "",
                "suggested_partnership_angle": getattr(lead, "outreach_note", "") if hasattr(lead, "outreach_note") else lead.get("outreach_note", ""),
            }
            
            # Handle score_breakdown
            score_breakdown = getattr(lead, "score_breakdown", {}) if hasattr(lead, "score_breakdown") else lead.get("score_breakdown", {})
            if score_breakdown:
                row["score_breakdown_json"] = json.dumps(score_breakdown)
            
            # Get company info if available
            if hasattr(lead, "company") and lead.company:
                row["company_name"] = lead.company.company_name or row["company_name"]
                row["website_url"] = lead.company.website_url or ""
                row["business_type"] = lead.company.business_type.value if hasattr(lead.company.business_type, "value") else str(lead.company.business_type)
            
            writer.writerow(row)
    
    logger.info("Exported partnership targets", count=len(leads), path=str(output_path))

