"""Main orchestrator for Lead Signal Engine pipeline."""

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import structlog
import yaml
from dotenv import load_dotenv

from .classify.rule_classifier import classify_domain
from .crawl.fetcher import Fetcher
from .crawl.parsers.ats_ashby import parse_ats_board as parse_ashby
from .crawl.parsers.ats_greenhouse import parse_ats_board as parse_greenhouse
from .crawl.parsers.ats_lever import parse_ats_board as parse_lever
from .crawl.parsers.ats_workable import parse_ats_board as parse_workable
from .crawl.parsers.ats_smartrecruiters import parse_ats_board as parse_smartrecruiters
from .crawl.parsers.ats_teamtailor import parse_ats_board as parse_teamtailor
from .crawl.parsers.ats_recruitee import parse_ats_board as parse_recruitee
from .crawl.parsers.launch_generic import parse_launch_page
from .crawl.parsers.funding_generic import parse_funding_page
from .crawl.parsers.ecosystem_generic import parse_ecosystem_page
from .export.csv_exporter import export_mvp_leads, export_partnership_targets
from .normalize.ats_normalizer import normalize_ats_url, is_ats_url
from .normalize.url_normalizer import normalize_url
from .providers.serpapi import SerpAPIProvider
from .resolve.domain_resolver import resolve_company_domain
from .score.outreach_note import generate_outreach_note
from .score.router import route_lead
from .score.scoring import score_lead
from .storage.models import SourceType, create_database_session
from .storage.sqlite_store import Store

# Load environment variables
load_dotenv()

logger = structlog.get_logger()


class Orchestrator:
    """Orchestrates the lead discovery pipeline."""

    def __init__(self, config_path: Path, dry_run: bool = False):
        """Initialize orchestrator with config path."""
        self.config_path = Path(config_path)
        self.dry_run = dry_run
        self.correlation_id = str(uuid.uuid4())
        self.log = logger.bind(correlation_id=self.correlation_id)

        # Load configs
        self.query_packs_config = self._load_config("query_packs.yaml")
        self.keywords = self._load_config("keywords.yaml")
        self.scoring = self._load_config("scoring.yaml")
        self.runtime = self._load_config("runtime.yaml")

        # Initialize database
        database_url = self._get_database_url()
        SessionLocal = create_database_session(database_url)
        self.db_session = SessionLocal()
        self.store = Store(self.db_session)

        # Initialize SerpAPI provider
        api_key = os.getenv("SERPAPI_API_KEY")
        if not api_key:
            raise ValueError("SERPAPI_API_KEY environment variable not set")
        self.serp_provider = SerpAPIProvider(api_key=api_key)

        # Initialize fetcher
        self.fetcher = Fetcher(self.runtime)

        self.log.info("Orchestrator initialized", dry_run=dry_run)

    def _load_config(self, filename: str) -> dict:
        """Load YAML config file."""
        config_file = self.config_path / filename
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")
        
        with open(config_file) as f:
            return yaml.safe_load(f)

    def _get_database_url(self) -> str:
        """Get database URL from environment."""
        import os
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable not set")
        return database_url

    def run_pack(self, pack_name: str):
        """Run discovery for a specific query pack."""
        self.log.info("Running discovery for query pack", pack=pack_name)
        
        query_packs = self.query_packs_config.get("query_packs", {})
        
        if pack_name not in query_packs:
            self.log.error("Query pack not found", pack=pack_name, available_packs=list(query_packs.keys()))
            raise ValueError(f"Query pack '{pack_name}' not found in config")
        
        pack_config = query_packs[pack_name]
        source_type = pack_config.get("source_type")
        
        if not source_type:
            self.log.error("Query pack missing source_type", pack=pack_name)
            raise ValueError(f"Query pack '{pack_name}' missing source_type")
        
        # Process single pack
        self._process_query_pack(pack_name, pack_config, source_type)
        
        # Process discovery targets if not dry-run
        # Process all source types (hiring, launch, funding, ecosystem)
        if not self.dry_run:
            self.log.info("About to call _process_discovery_targets", source_type=source_type, dry_run=self.dry_run)
            self._process_discovery_targets(source_type)
        else:
            self.log.info("Skipping _process_discovery_targets (dry-run mode)", source_type=source_type)

    def run_source(self, source_type: str):
        """Run discovery for a specific source type."""
        self.log.info("Running discovery for source type", source_type=source_type)
        
        # Get query packs for this source type
        query_packs = self.query_packs_config.get("query_packs", {})
        source_packs = {
            name: pack for name, pack in query_packs.items()
            if pack.get("source_type") == source_type
        }
        
        if not source_packs:
            self.log.warning("No query packs found for source type", source_type=source_type)
            return
        
        self.log.info("Found query packs", source_type=source_type, count=len(source_packs))
        
        # Track metrics
        metrics = {
            "serp_calls": 0,
            "targets_discovered": 0,
            "targets_new": 0,
            "targets_existing": 0,
        }
        
        # Process each query pack
        for pack_name, pack_config in source_packs.items():
            pack_metrics = self._process_query_pack(pack_name, pack_config, source_type)
            # Aggregate metrics
            for key in metrics:
                metrics[key] += pack_metrics.get(key, 0)
        
        self.log.info("Discovery completed", source_type=source_type, metrics=metrics)
        
        # Process discovery targets if not dry-run
        # Process all source types (hiring, launch, funding, ecosystem)
        if not self.dry_run:
            self.log.info("About to call _process_discovery_targets", source_type=source_type, dry_run=self.dry_run)
            self._process_discovery_targets(source_type)
        else:
            self.log.info("Skipping _process_discovery_targets (dry-run mode)", source_type=source_type)

    def _process_query_pack(self, pack_name: str, pack_config: dict, source_type: str) -> dict:
        """
        Process a single query pack.
        
        Returns:
            Dictionary with metrics (serp_calls, targets_discovered, etc.)
        """
        self.log.info("Processing query pack", pack=pack_name)
        
        metrics = {
            "serp_calls": 0,
            "targets_discovered": 0,
            "targets_new": 0,
            "targets_existing": 0,
        }
        
        try:
            # Run SERP discovery
            queries = pack_config.get("queries", [])
            pages = pack_config.get("pages", 1)
            results_per_page = pack_config.get("results_per_page", 10)
            serp_params = pack_config.get("serp_params", {})
            
            for query in queries:
                self.log.info("Executing SERP query", pack=pack_name, query=query)
                
                try:
                    results = self.serp_provider.search_with_pagination(
                        query=query,
                        pages=pages,
                        results_per_page=results_per_page,
                        **serp_params
                    )
                    
                    metrics["serp_calls"] += pages
                    self.log.info("SERP query returned results", pack=pack_name, query=query[:100], count=len(results))
                    
                    # Store SERP results and create discovery targets
                    for result in results:
                        raw_url = result.get("link", "")
                        if not raw_url:
                            continue
                        
                        # Normalize URL
                        normalized_url = None
                        is_ats = is_ats_url(raw_url)
                        if is_ats:
                            normalized_url = normalize_ats_url(raw_url)
                        else:
                            normalized_url = normalize_url(raw_url)
                        
                        if not normalized_url:
                            self.log.warning("Failed to normalize URL", url=raw_url)
                            continue
                        
                        # Extract domain from normalized URL
                        parsed = urlparse(normalized_url)
                        source_domain = parsed.netloc.lower()
                        
                        # Create or update discovery target
                        serp_evidence = {
                            "title": result.get("title", ""),
                            "snippet": result.get("snippet", ""),
                            "rank": result.get("rank", 0),
                        }
                        
                        if not self.dry_run:
                            # Store SERP result
                            self.store.save_serp_result({
                                "provider": "serpapi",
                                "query_pack": pack_name,
                                "query": query,
                                "rank": result.get("rank", 0),
                                "title": result.get("title", ""),
                                "snippet": result.get("snippet", ""),
                                "link": raw_url,
                                "fetched_at": datetime.utcnow(),
                            })
                            
                            # Get or create discovery target
                            target, is_new = self.store.get_or_create_discovery_target(
                                normalized_url=normalized_url,
                                source_type=SourceType(source_type),
                                source_url_raw=raw_url,
                                source_domain=source_domain,
                                serp_query_pack=pack_name,
                                serp_query=query,
                                serp_evidence=serp_evidence,
                                first_seen_at=datetime.utcnow(),
                                last_seen_at=datetime.utcnow(),
                            )
                            
                            metrics["targets_discovered"] += 1
                            if is_new:
                                metrics["targets_new"] += 1
                                self.log.debug("New discovery target created", url=normalized_url[:80], pack=pack_name)
                            else:
                                metrics["targets_existing"] += 1
                                self.log.debug("Existing discovery target updated", url=normalized_url[:80], pack=pack_name)
                        
                except Exception as e:
                    self.log.error("Error processing SERP query", pack=pack_name, query=query, error=str(e), exc_info=True)
                    continue
            
        except Exception as e:
            self.log.error("Error processing query pack", pack=pack_name, error=str(e), exc_info=True)
        
        self.log.info("Query pack completed", pack=pack_name, metrics=metrics)
        return metrics

    def _process_discovery_targets(self, source_type: str):
        """Process discovery targets through full pipeline: fetch, parse, classify, score, route."""
        self.log.info("Starting discovery target processing", source_type=source_type, dry_run=self.dry_run)
        
        # Get pending discovery targets
        try:
            targets = self.store.get_pending_discovery_targets(source_type=SourceType(source_type), limit=50)
            target_count = len(targets) if targets else 0
            self.log.info("Retrieved discovery targets", source_type=source_type, count=target_count)
        except Exception as e:
            self.log.error("Error retrieving discovery targets", source_type=source_type, error=str(e), exc_info=True)
            return
        
        if not targets:
            self.log.info("No discovery targets to process", source_type=source_type)
            return
        
        self.log.info("Processing discovery targets", source_type=source_type, count=len(targets))
        
        metrics = {
            "targets_processed": 0,
            "targets_crawled": 0,
            "domains_resolved": 0,
            "companies_classified": 0,
            "leads_created": 0,
        }
        
        for target in targets:
            try:
                # Fetch page
                status_code, html, fetch_meta = self.fetcher.fetch(target.source_url_normalized)
                
                if status_code != 200:
                    self.log.warning("Failed to fetch target", url=target.source_url_normalized, status=status_code)
                    continue
                
                metrics["targets_crawled"] += 1
                
                # Parse based on source type
                parsed = {}
                if source_type == "hiring" and is_ats_url(target.source_url_normalized):
                    # Determine ATS type and parse
                    if "greenhouse.io" in target.source_url_normalized:
                        parsed = parse_greenhouse(target.source_url_normalized, html, self.keywords)
                    elif "lever.co" in target.source_url_normalized:
                        parsed = parse_lever(target.source_url_normalized, html, self.keywords)
                    elif "ashbyhq.com" in target.source_url_normalized:
                        parsed = parse_ashby(target.source_url_normalized, html, self.keywords)
                    elif "workable.com" in target.source_url_normalized:
                        parsed = parse_workable(target.source_url_normalized, html, self.keywords)
                    elif "smartrecruiters.com" in target.source_url_normalized:
                        parsed = parse_smartrecruiters(target.source_url_normalized, html, self.keywords)
                    elif "teamtailor.com" in target.source_url_normalized:
                        parsed = parse_teamtailor(target.source_url_normalized, html, self.keywords)
                    elif "recruitee.com" in target.source_url_normalized:
                        parsed = parse_recruitee(target.source_url_normalized, html, self.keywords)
                elif source_type == "hiring" and not is_ats_url(target.source_url_normalized):
                    # Non-ATS hiring URL (e.g., partnership discovery, agency websites)
                    # Extract company domain from URL
                    parsed_url = urlparse(target.source_url_normalized)
                    company_domain_from_url = parsed_url.netloc.lower()
                    if company_domain_from_url.startswith("www."):
                        company_domain_from_url = company_domain_from_url[4:]
                    
                    # Remove port if present
                    if ":" in company_domain_from_url:
                        company_domain_from_url = company_domain_from_url.split(":")[0]
                    
                    # Create minimal parsed data - include both URL and extracted domain
                    # Signals will be minimal since we don't have ATS data
                    # Classification will happen later using rule classifier
                    parsed = {
                        "company_website_url": target.source_url_normalized,
                        "company_domain": company_domain_from_url,  # Add extracted domain for reliable resolution
                        "signals": [],  # No specific signals for non-ATS URLs - classification will determine routing
                    }
                elif source_type == "launch":
                    # Parse launch page
                    parsed = parse_launch_page(target.source_url_normalized, html)
                elif source_type == "funding":
                    # Parse funding/accelerator page
                    parsed = parse_funding_page(target.source_url_normalized, html)
                elif source_type == "ecosystem":
                    # Parse ecosystem/community page
                    parsed = parse_ecosystem_page(target.source_url_normalized, html)
                
                if not parsed:
                    continue
                
                # For non-ATS hiring URLs, we still want to process them even without signals
                # They'll be classified and routed based on business type
                # Only skip if parsed is None/empty
                if source_type == "hiring" and not is_ats_url(target.source_url_normalized):
                    # Non-ATS URLs may have empty signals - that's OK, classification will handle it
                    pass
                elif not parsed.get("signals"):
                    # For other source types, require signals
                    continue
                
                # Resolve company domain
                company_domain = resolve_company_domain(parsed, target.source_url_normalized)
                
                if not company_domain:
                    self.log.warning("Could not resolve company domain", url=target.source_url_normalized)
                    continue
                
                metrics["domains_resolved"] += 1
                
                # Get or create company
                # Determine company name and website URL based on source type
                company_name = None
                website_url = None
                
                if source_type == "hiring":
                    website_url = parsed.get("company_website_url")
                    if website_url:
                        # Extract domain from URL for company name
                        try:
                            parsed_url = urlparse(website_url)
                            domain = parsed_url.netloc.lower()
                            if domain.startswith("www."):
                                domain = domain[4:]
                            company_name = domain.split(":")[0]  # Remove port if present
                        except Exception:
                            # Fallback to simple split
                            company_name = website_url.split("//")[-1].split("/")[0]
                elif source_type == "launch":
                    website_url = parsed.get("product_url")
                    company_name = parsed.get("product_name")
                    if not company_name and website_url:
                        company_name = website_url.split("//")[-1].split("/")[0]
                elif source_type == "funding":
                    # For funding, we may not have website URL directly
                    # Company domain is extracted from the parser
                    # Try to construct website URL from domain
                    if company_domain:
                        website_url = f"https://{company_domain}"
                        company_name = company_domain.split(".")[0]  # Use domain prefix as name
                elif source_type == "ecosystem":
                    # For ecosystem, project domain is extracted from the parser
                    # Try to construct website URL from domain
                    if company_domain:
                        website_url = f"https://{company_domain}"
                        company_name = company_domain.split(".")[0]  # Use domain prefix as name
                
                # Get or create company
                try:
                    company, created = self.store.get_or_create_company(
                        domain=company_domain,
                        company_name=company_name,
                        website_url=website_url,
                        last_seen_at=datetime.utcnow(),
                    )
                    if created:
                        self.log.info("Company created", domain=company_domain, company_name=company_name, website_url=website_url)
                    else:
                        self.log.debug("Company updated", domain=company_domain, company_name=company_name)
                except Exception as e:
                    self.log.error("Error creating/updating company", domain=company_domain, error=str(e), exc_info=True)
                    raise  # Re-raise to be caught by outer exception handler
                
                # Store signal snapshot
                signal_details = {}
                if source_type == "hiring":
                    signal_details = {
                        "jobs_count": parsed.get("jobs_count", 0),
                        "engineering_roles_count": parsed.get("engineering_roles_count", 0),
                        "roles_detected": parsed.get("roles_detected", []),
                    }
                elif source_type == "launch":
                    signal_details = {
                        "launch_date": parsed.get("launch_date"),
                        "product_name": parsed.get("product_name"),
                        "product_url": parsed.get("product_url"),
                    }
                elif source_type == "funding":
                    signal_details = {
                        "accelerator_name": parsed.get("accelerator_name"),
                        "batch": parsed.get("batch"),
                        "funding_round": parsed.get("funding_round"),
                        "funding_date": parsed.get("funding_date"),
                    }
                elif source_type == "ecosystem":
                    signal_details = {
                        "ecosystem_tag": parsed.get("ecosystem_tag"),
                        "program_type": parsed.get("program_type"),
                        "program_name": parsed.get("program_name"),
                    }
                
                if not self.dry_run:
                    try:
                        self.store.save_signal_snapshot({
                            "company_domain": company_domain,
                            "source_type": SourceType(source_type),
                            "source_url_normalized": target.source_url_normalized,
                            "signals": parsed.get("signals", []),
                            "signal_details": signal_details,
                            "fetched_at": datetime.utcnow(),
                            "content_hash": fetch_meta.get("content_hash"),
                        })
                        self.log.debug("Signal snapshot saved", domain=company_domain, source_type=source_type, signals_count=len(parsed.get("signals", [])))
                    except Exception as e:
                        self.log.error("Error saving signal snapshot", domain=company_domain, error=str(e), exc_info=True)
                        raise  # Re-raise to be caught by outer exception handler
                
                # Classify company (fetch company pages)
                classification = {
                    "business_type": "unknown",
                    "confidence": 0.5,
                    "reasons": [],
                }
                
                # For launch sources, assume product company (launches are typically products)
                if source_type == "launch":
                    classification["business_type"] = "product_company"
                    classification["confidence"] = 0.7
                    classification["reasons"] = ["Launch page detected - typically indicates product company"]
                # For funding sources, assume product company (funded companies are typically products)
                elif source_type == "funding":
                    classification["business_type"] = "product_company"
                    classification["confidence"] = 0.7
                    classification["reasons"] = ["Funding/accelerator page detected - typically indicates product company"]
                    if parsed.get("accelerator_name"):
                        classification["reasons"].append(f"Accelerator: {parsed.get('accelerator_name')}")
                    if parsed.get("funding_round"):
                        classification["reasons"].append(f"Funding round: {parsed.get('funding_round')}")
                # For ecosystem sources, assume product company (ecosystem projects are typically products)
                elif source_type == "ecosystem":
                    classification["business_type"] = "product_company"
                    classification["confidence"] = 0.7
                    classification["reasons"] = ["Ecosystem/community page detected - typically indicates product company"]
                    if parsed.get("ecosystem_tag"):
                        classification["reasons"].append(f"Ecosystem: {parsed.get('ecosystem_tag')}")
                    if parsed.get("program_type"):
                        classification["reasons"].append(f"Program type: {parsed.get('program_type')}")
                # For hiring sources
                elif source_type == "hiring":
                    # Check if this came from a partnership discovery pack
                    serp_pack = getattr(target, 'serp_query_pack', None)
                    is_partnership_pack = serp_pack and serp_pack.startswith("partner_")
                    
                    # If it's an ATS URL from a partnership pack, we need to classify the company's main website
                    # Otherwise, if it's a non-ATS URL, it's likely a partnership discovery
                    if is_ats_url(target.source_url_normalized) and is_partnership_pack:
                        # ATS URL from partnership pack - fetch and classify company's main website
                        self.log.debug("ATS URL from partnership pack, classifying company website", domain=company_domain, pack=serp_pack)
                        pages = {}
                        try:
                            # Try to fetch homepage
                            homepage_url = f"https://{company_domain}"
                            status, homepage_html, _ = self.fetcher.fetch(homepage_url)
                            if status == 200:
                                pages["homepage"] = homepage_html
                            
                            # Try to fetch /about page
                            about_url = f"https://{company_domain}/about"
                            status, about_html, _ = self.fetcher.fetch(about_url)
                            if status == 200:
                                pages["about"] = about_html
                        except Exception as e:
                            self.log.warning("Error fetching company pages for classification", domain=company_domain, error=str(e))
                        
                        # Classify using rule classifier
                        if pages:
                            classification = classify_domain(company_domain, pages, self.keywords)
                            classification["reasons"].append(f"Classified from partnership discovery ATS board: {target.source_url_normalized}")
                            self.log.debug("Classification completed", domain=company_domain, business_type=classification["business_type"])
                        else:
                            classification["reasons"] = ["Could not fetch company pages for classification from partnership ATS board"]
                    elif is_ats_url(target.source_url_normalized):
                        # Regular ATS URL (not from partnership pack) - use simplified classification
                        classification["reasons"] = ["Classification based on ATS signals only"]
                        # If we have strong product indicators, classify as product company
                        if parsed.get("company_website_url"):
                            classification["business_type"] = "product_company"
                            classification["confidence"] = 0.6
                            classification["reasons"] = ["Company website found"]
                    else:
                        # Non-ATS hiring URL (partnership discovery) - use rule classifier
                        self.log.debug("Non-ATS hiring URL (partnership discovery), classifying", domain=company_domain)
                        # Fetch company pages for classification
                        pages = {}
                        try:
                            # Try to fetch homepage
                            homepage_url = f"https://{company_domain}"
                            status, homepage_html, _ = self.fetcher.fetch(homepage_url)
                            if status == 200:
                                pages["homepage"] = homepage_html
                            
                            # Try to fetch /about page
                            about_url = f"https://{company_domain}/about"
                            status, about_html, _ = self.fetcher.fetch(about_url)
                            if status == 200:
                                pages["about"] = about_html
                        except Exception as e:
                            self.log.warning("Error fetching company pages for classification", domain=company_domain, error=str(e))
                        
                        # Use the already-fetched page if we have it
                        if not pages and html:
                            pages["discovered_page"] = html
                        
                        # Classify using rule classifier
                        if pages:
                            classification = classify_domain(company_domain, pages, self.keywords)
                            classification["reasons"].append(f"Classified from discovered URL: {target.source_url_normalized}")
                            self.log.debug("Classification completed", domain=company_domain, business_type=classification["business_type"])
                        else:
                            classification["reasons"] = ["Could not fetch company pages for classification"]
                else:
                    # For other source types, default to unknown
                    classification["reasons"] = [f"Classification for {source_type} source type not yet implemented"]
                
                # Update company classification
                if not self.dry_run:
                    company.business_type = classification["business_type"]
                    company.business_type_confidence = classification["confidence"]
                    company.classification_reasons = classification["reasons"]
                    self.db_session.commit()
                
                metrics["companies_classified"] += 1
                
                # Score lead
                snapshot = {
                    "signals": parsed.get("signals", []),
                    "signal_details": signal_details,
                }
                
                company_dict = {
                    "company_domain": company_domain,
                    "business_type": classification["business_type"],
                }
                
                try:
                    scores = score_lead(company_dict, snapshot, classification, self.scoring, self.keywords)
                    self.log.debug("Lead scored", domain=company_domain, mvp_score=scores.get("mvp_intent_score"), partnership_score=scores.get("partnership_fit_score"))
                except Exception as e:
                    self.log.error("Error scoring lead", domain=company_domain, error=str(e), exc_info=True)
                    raise  # Re-raise to be caught by outer exception handler
                
                # Route lead
                try:
                    routing = route_lead(classification, scores, snapshot, self.scoring)
                    self.log.debug("Lead routed", domain=company_domain, route_flag=routing.get("route_flag"), channel=routing.get("recommended_channel"))
                except Exception as e:
                    self.log.error("Error routing lead", domain=company_domain, error=str(e), exc_info=True)
                    raise  # Re-raise to be caught by outer exception handler
                
                # Generate outreach note
                try:
                    outreach_note = generate_outreach_note(company_dict, snapshot, classification, {**scores, **routing}, self.keywords)
                    self.log.debug("Outreach note generated", domain=company_domain, note_length=len(outreach_note) if outreach_note else 0)
                except Exception as e:
                    self.log.error("Error generating outreach note", domain=company_domain, error=str(e), exc_info=True)
                    # Don't fail on outreach note generation - use empty string as fallback
                    outreach_note = ""
                
                # Create or update lead
                if not self.dry_run:
                    try:
                        self.store.save_or_update_lead(
                            domain=company_domain,
                            route_flag=routing["route_flag"],
                            mvp_intent_score=scores["mvp_intent_score"],
                            partnership_fit_score=scores["partnership_fit_score"],
                            score_breakdown=scores["score_breakdown"],
                            recommended_channel=routing["recommended_channel"],
                            outreach_note=outreach_note,
                        )
                        self.log.info("Lead created/updated", domain=company_domain, route_flag=routing["route_flag"], mvp_score=scores["mvp_intent_score"], partnership_score=scores["partnership_fit_score"])
                    except Exception as e:
                        self.log.error("Error creating/updating lead", domain=company_domain, error=str(e), exc_info=True)
                        raise  # Re-raise to be caught by outer exception handler
                
                metrics["leads_created"] += 1
                metrics["targets_processed"] += 1
                
            except Exception as e:
                self.log.error("Error processing discovery target", url=target.source_url_normalized, error=str(e), exc_info=True)
                continue
        
        # Log summary with actual counts from database
        if not self.dry_run:
            try:
                from .storage.models import Company, Lead
                companies_count = self.db_session.query(Company).count()
                leads_count = self.db_session.query(Lead).count()
                self.log.info(
                    "Processing completed",
                    source_type=source_type,
                    metrics=metrics,
                    total_companies_in_db=companies_count,
                    total_leads_in_db=leads_count,
                )
            except Exception as e:
                self.log.warning("Could not query database counts", error=str(e))
                self.log.info("Processing completed", source_type=source_type, metrics=metrics)
        else:
            self.log.info("Processing completed", source_type=source_type, metrics=metrics)

    def run_all(self):
        """Run discovery for all source types."""
        self.log.info("Running discovery for all source types")
        
        for source_type in ["hiring", "launch", "funding", "ecosystem"]:
            try:
                self.run_source(source_type)
            except Exception as e:
                self.log.error("Failed to process source type", source_type=source_type, error=str(e))

    def export_leads(self):
        """Export leads to CSV files."""
        self.log.info("Exporting leads")
        
        # Get output directory from config
        export_config = self.runtime.get("export", {})
        output_dir = Path(export_config.get("output_dir", "data/output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Get MVP leads
        mvp_leads = self.store.get_mvp_leads(min_score=0)
        mvp_filename = export_config.get("mvp_leads_filename", "mvp_clients_ranked.csv")
        mvp_path = output_dir / mvp_filename
        
        if mvp_leads:
            export_mvp_leads(mvp_leads, mvp_path, store=self.store)
            self.log.info("Exported MVP leads", count=len(mvp_leads), path=str(mvp_path))
        else:
            self.log.info("No MVP leads to export")
        
        # Get partnership leads
        partnership_leads = self.store.get_partnership_leads(min_score=0)
        partnership_filename = export_config.get("partnership_targets_filename", "partnership_targets_ranked.csv")
        partnership_path = output_dir / partnership_filename
        
        if partnership_leads:
            export_partnership_targets(partnership_leads, partnership_path, store=self.store)
            self.log.info("Exported partnership targets", count=len(partnership_leads), path=str(partnership_path))
        else:
            self.log.info("No partnership targets to export")

