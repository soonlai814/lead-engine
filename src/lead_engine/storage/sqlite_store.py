"""Database storage layer (PostgreSQL)."""

from typing import Optional

from sqlalchemy.orm import Session

from .models import (
    BusinessType,
    Company,
    DiscoveryTarget,
    Lead,
    RecommendedChannel,
    RouteFlag,
    SerpResult,
    SignalSnapshot,
    SourceType,
)


class Store:
    """Database store for Lead Signal Engine."""

    def __init__(self, session: Session):
        """Initialize store with database session."""
        self.session = session

    # SerpResult methods
    def save_serp_result(self, result: dict) -> SerpResult:
        """Save a SERP result."""
        serp_result = SerpResult(**result)
        self.session.add(serp_result)
        self.session.commit()
        return serp_result

    def get_serp_results_by_pack(self, query_pack: str, limit: Optional[int] = None):
        """Get SERP results for a query pack."""
        query = self.session.query(SerpResult).filter(SerpResult.query_pack == query_pack)
        if limit:
            query = query.limit(limit)
        return query.all()

    # DiscoveryTarget methods
    def get_or_create_discovery_target(self, normalized_url: str, **kwargs) -> tuple[DiscoveryTarget, bool]:
        """Get existing discovery target or create new one."""
        target = self.session.query(DiscoveryTarget).filter(
            DiscoveryTarget.source_url_normalized == normalized_url
        ).first()
        
        if target:
            # Update seen_count and last_seen_at
            target.seen_count += 1
            target.last_seen_at = kwargs.get("last_seen_at", target.last_seen_at)
            if kwargs.get("serp_evidence"):
                target.serp_evidence = kwargs["serp_evidence"]
            self.session.commit()
            return target, False
        
        # Create new
        target = DiscoveryTarget(source_url_normalized=normalized_url, **kwargs)
        self.session.add(target)
        self.session.commit()
        return target, True

    def get_pending_discovery_targets(self, source_type: Optional[SourceType] = None, limit: Optional[int] = None):
        """Get discovery targets that haven't been processed yet."""
        # This would need a join or flag to track processing status
        # For now, return all targets
        query = self.session.query(DiscoveryTarget)
        if source_type:
            query = query.filter(DiscoveryTarget.source_type == source_type)
        if limit:
            query = query.limit(limit)
        return query.all()

    # Company methods
    def get_or_create_company(self, domain: str, **kwargs) -> tuple[Company, bool]:
        """Get existing company or create new one."""
        company = self.session.query(Company).filter(Company.company_domain == domain).first()
        
        if company:
            # Update fields
            for key, value in kwargs.items():
                if hasattr(company, key) and value is not None:
                    setattr(company, key, value)
            company.last_seen_at = kwargs.get("last_seen_at", company.last_seen_at)
            self.session.commit()
            return company, False
        
        # Create new
        company = Company(company_domain=domain, **kwargs)
        self.session.add(company)
        self.session.commit()
        return company, True

    def get_company_by_domain(self, domain: str) -> Optional[Company]:
        """Get company by domain."""
        return self.session.query(Company).filter(Company.company_domain == domain).first()

    # SignalSnapshot methods
    def save_signal_snapshot(self, snapshot: dict) -> SignalSnapshot:
        """Save a signal snapshot."""
        signal_snapshot = SignalSnapshot(**snapshot)
        self.session.add(signal_snapshot)
        self.session.commit()
        return signal_snapshot

    def get_latest_signal_snapshot(self, domain: str, source_type: Optional[SourceType] = None) -> Optional[SignalSnapshot]:
        """Get latest signal snapshot for a company."""
        query = self.session.query(SignalSnapshot).filter(SignalSnapshot.company_domain == domain)
        if source_type:
            query = query.filter(SignalSnapshot.source_type == source_type)
        return query.order_by(SignalSnapshot.fetched_at.desc()).first()

    # Lead methods
    def save_or_update_lead(self, domain: str, **kwargs) -> Lead:
        """Save or update a lead."""
        lead = self.session.query(Lead).filter(Lead.company_domain == domain).first()
        
        if lead:
            # Update fields
            for key, value in kwargs.items():
                if hasattr(lead, key) and value is not None:
                    setattr(lead, key, value)
            self.session.commit()
            return lead
        
        # Create new
        lead = Lead(company_domain=domain, **kwargs)
        self.session.add(lead)
        self.session.commit()
        return lead

    def get_mvp_leads(self, min_score: int = 0, limit: Optional[int] = None):
        """Get MVP leads sorted by score."""
        query = (
            self.session.query(Lead)
            .filter(Lead.route_flag == RouteFlag.OUTREACH_MVP_CLIENT)
            .filter(Lead.mvp_intent_score >= min_score)
            .order_by(Lead.mvp_intent_score.desc())
        )
        if limit:
            query = query.limit(limit)
        return query.all()

    def get_partnership_leads(self, min_score: int = 0, limit: Optional[int] = None):
        """Get partnership leads sorted by score."""
        query = (
            self.session.query(Lead)
            .filter(Lead.route_flag == RouteFlag.OUTREACH_PARTNERSHIP)
            .filter(Lead.partnership_fit_score >= min_score)
            .order_by(Lead.partnership_fit_score.desc())
        )
        if limit:
            query = query.limit(limit)
        return query.all()

