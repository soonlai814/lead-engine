"""Main orchestrator for Lead Signal Engine pipeline."""

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

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
        
        # Process discovery targets if not dry-run and source_type is hiring
        if not self.dry_run and source_type == "hiring":
            self._process_discovery_targets(source_type)

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
        
        # Process discovery targets if not dry-run and source_type is hiring
        if not self.dry_run and source_type == "hiring":
            self._process_discovery_targets(source_type)

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
                    
                    # Store SERP results and create discovery targets
                    for result in results:
                        raw_url = result.get("link", "")
                        if not raw_url:
                            continue
                        
                        # Normalize URL
                        normalized_url = None
                        if is_ats_url(raw_url):
                            normalized_url = normalize_ats_url(raw_url)
                        else:
                            normalized_url = normalize_url(raw_url)
                        
                        if not normalized_url:
                            self.log.warning("Failed to normalize URL", url=raw_url)
                            continue
                        
                        # Extract domain from normalized URL
                        from urllib.parse import urlparse
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
                            else:
                                metrics["targets_existing"] += 1
                        
                except Exception as e:
                    self.log.error("Error processing SERP query", pack=pack_name, query=query, error=str(e), exc_info=True)
                    continue
            
        except Exception as e:
            self.log.error("Error processing query pack", pack=pack_name, error=str(e), exc_info=True)
        
        self.log.info("Query pack completed", pack=pack_name, metrics=metrics)
        return metrics

    def _process_discovery_targets(self, source_type: str):
        """Process discovery targets through full pipeline: fetch, parse, classify, score, route."""
        self.log.info("Processing discovery targets", source_type=source_type)
        
        # Get pending discovery targets
        targets = self.store.get_pending_discovery_targets(source_type=SourceType(source_type), limit=50)
        
        if not targets:
            self.log.info("No discovery targets to process")
            return
        
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
                
                if not parsed:
                    continue
                
                # Resolve company domain
                company_domain = resolve_company_domain(parsed, target.source_url_normalized)
                
                if not company_domain:
                    self.log.warning("Could not resolve company domain", url=target.source_url_normalized)
                    continue
                
                metrics["domains_resolved"] += 1
                
                # Get or create company
                company, _ = self.store.get_or_create_company(
                    domain=company_domain,
                    company_name=parsed.get("company_website_url", "").split("//")[-1].split("/")[0] if parsed.get("company_website_url") else None,
                    website_url=parsed.get("company_website_url"),
                    last_seen_at=datetime.utcnow(),
                )
                
                # Store signal snapshot
                if not self.dry_run:
                    self.store.save_signal_snapshot({
                        "company_domain": company_domain,
                        "source_type": SourceType(source_type),
                        "source_url_normalized": target.source_url_normalized,
                        "signals": parsed.get("signals", []),
                        "signal_details": {
                            "jobs_count": parsed.get("jobs_count", 0),
                            "engineering_roles_count": parsed.get("engineering_roles_count", 0),
                            "roles_detected": parsed.get("roles_detected", []),
                        },
                        "fetched_at": datetime.utcnow(),
                        "content_hash": fetch_meta.get("content_hash"),
                    })
                
                # Classify company (fetch company pages)
                # For Phase 1, use simplified classification based on ATS signals
                classification = {
                    "business_type": "unknown",
                    "confidence": 0.5,
                    "reasons": ["Classification based on ATS signals only"],
                }
                
                # If we have strong product indicators, classify as product company
                if parsed.get("company_website_url"):
                    classification["business_type"] = "product_company"
                    classification["confidence"] = 0.6
                    classification["reasons"] = ["Company website found"]
                
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
                    "signal_details": {
                        "jobs_count": parsed.get("jobs_count", 0),
                        "engineering_roles_count": parsed.get("engineering_roles_count", 0),
                        "roles_detected": parsed.get("roles_detected", []),
                    },
                }
                
                company_dict = {
                    "company_domain": company_domain,
                    "business_type": classification["business_type"],
                }
                
                scores = score_lead(company_dict, snapshot, classification, self.scoring)
                
                # Route lead
                routing = route_lead(classification, scores, snapshot, self.scoring)
                
                # Generate outreach note
                outreach_note = generate_outreach_note(company_dict, snapshot, classification, {**scores, **routing}, self.keywords)
                
                # Create or update lead
                if not self.dry_run:
                    self.store.save_or_update_lead(
                        domain=company_domain,
                        route_flag=routing["route_flag"],
                        mvp_intent_score=scores["mvp_intent_score"],
                        partnership_fit_score=scores["partnership_fit_score"],
                        score_breakdown=scores["score_breakdown"],
                        recommended_channel=routing["recommended_channel"],
                        outreach_note=outreach_note,
                    )
                
                metrics["leads_created"] += 1
                metrics["targets_processed"] += 1
                
            except Exception as e:
                self.log.error("Error processing discovery target", url=target.source_url_normalized, error=str(e), exc_info=True)
                continue
        
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

