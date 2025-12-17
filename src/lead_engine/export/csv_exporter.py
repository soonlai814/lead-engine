"""CSV exporter for leads."""

import csv
import json
from pathlib import Path
from typing import List

import structlog

logger = structlog.get_logger()


def export_mvp_leads(leads: List, output_path: Path, store=None):
    """
    Export MVP leads to CSV.
    
    Args:
        leads: List of Lead SQLAlchemy model objects
        output_path: Output file path
        store: Optional Store instance to query related data
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
            # Extract data from Lead SQLAlchemy model
            company_domain = lead.company_domain
            
            # Get company info
            company_name = ""
            website_url = ""
            if store:
                company = store.get_company_by_domain(company_domain)
                if company:
                    company_name = company.company_name or ""
                    website_url = company.website_url or ""
            
            # Get latest signal snapshot
            primary_source = ""
            evidence_url = ""
            roles_detected = ""
            signals = ""
            if store:
                snapshot = store.get_latest_signal_snapshot(company_domain)
                if snapshot:
                    primary_source = snapshot.source_type.value if hasattr(snapshot.source_type, "value") else str(snapshot.source_type)
                    evidence_url = snapshot.source_url_normalized or ""
                    signal_details = snapshot.signal_details or {}
                    roles_detected = json.dumps(signal_details.get("roles_detected", []))
                    signals = json.dumps(snapshot.signals or [])
            
            # Handle score_breakdown (convert dict to JSON string)
            score_breakdown_json = ""
            if lead.score_breakdown:
                score_breakdown_json = json.dumps(lead.score_breakdown)
            
            # Handle recommended_channel (enum to string)
            recommended_channel = ""
            if lead.recommended_channel:
                recommended_channel = lead.recommended_channel.value if hasattr(lead.recommended_channel, "value") else str(lead.recommended_channel)
            
            row = {
                "company_name": company_name,
                "company_domain": company_domain,
                "website_url": website_url,
                "primary_source": primary_source,
                "evidence_url": evidence_url,
                "mvp_intent_score": lead.mvp_intent_score or 0,
                "roles_detected": roles_detected,
                "signals": signals,
                "score_breakdown_json": score_breakdown_json,
                "recommended_channel": recommended_channel,
                "outreach_note": lead.outreach_note or "",
            }
            
            writer.writerow(row)
    
    logger.info("Exported MVP leads", count=len(leads), path=str(output_path))


def export_partnership_targets(leads: List, output_path: Path, store=None):
    """
    Export partnership targets to CSV.
    
    Args:
        leads: List of Lead SQLAlchemy model objects
        output_path: Output file path
        store: Optional Store instance to query related data
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
            company_domain = lead.company_domain
            
            # Get company info
            company_name = ""
            website_url = ""
            business_type = ""
            if store:
                company = store.get_company_by_domain(company_domain)
                if company:
                    company_name = company.company_name or ""
                    website_url = company.website_url or ""
                    business_type = company.business_type.value if hasattr(company.business_type, "value") else str(company.business_type)
            
            # Get latest signal snapshot
            signals = ""
            if store:
                snapshot = store.get_latest_signal_snapshot(company_domain)
                if snapshot:
                    signals = json.dumps(snapshot.signals or [])
            
            # Handle score_breakdown
            score_breakdown_json = ""
            if lead.score_breakdown:
                score_breakdown_json = json.dumps(lead.score_breakdown)
            
            row = {
                "company_name": company_name,
                "company_domain": company_domain,
                "website_url": website_url,
                "business_type": business_type,
                "partnership_fit_score": lead.partnership_fit_score or 0,
                "signals": signals,
                "score_breakdown_json": score_breakdown_json,
                "suggested_partnership_angle": lead.outreach_note or "",
            }
            
            writer.writerow(row)
    
    logger.info("Exported partnership targets", count=len(leads), path=str(output_path))

