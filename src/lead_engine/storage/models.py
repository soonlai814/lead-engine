"""Database models for Lead Signal Engine."""

from datetime import datetime
from enum import Enum
from typing import Optional

import os
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    Integer,
    JSON,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

Base = declarative_base()

# Get schema name from environment, default to 'public'
_DEFAULT_SCHEMA = os.getenv("DATABASE_SCHEMA", "public")


class SourceType(str, Enum):
    """Source type enum."""

    HIRING = "hiring"
    LAUNCH = "launch"
    FUNDING = "funding"
    ECOSYSTEM = "ecosystem"


class BusinessType(str, Enum):
    """Business type enum."""

    PRODUCT_COMPANY = "product_company"
    SERVICE_AGENCY = "service_agency"
    CONSULTANCY = "consultancy"
    SYSTEM_INTEGRATOR = "system_integrator"
    STAFFING_RECRUITER = "staffing_recruiter"
    OPEN_SOURCE_COMMUNITY = "open_source_community"
    UNKNOWN = "unknown"


class RouteFlag(str, Enum):
    """Route flag enum."""

    OUTREACH_MVP_CLIENT = "outreach_mvp_client"
    OUTREACH_PARTNERSHIP = "outreach_partnership"
    IGNORE = "ignore"


class RecommendedChannel(str, Enum):
    """Recommended outreach channel enum."""

    LINKEDIN_DM = "linkedin_dm"
    X_DM = "x_dm"
    EMAIL = "email"
    PARTNER_INTRO = "partner_intro"


class LeadStatus(str, Enum):
    """Lead status enum."""

    NEW = "new"
    QUEUED = "queued"
    CONTACTED = "contacted"
    REPLIED = "replied"
    BOOKED = "booked"
    CLOSED = "closed"
    ARCHIVED = "archived"


class SerpResult(Base):
    """Raw SERP results for audit/debug."""

    __tablename__ = "serp_results"
    __table_args__ = {"schema": _DEFAULT_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(50), nullable=False, default="serpapi")
    query_pack = Column(String(100), nullable=False, index=True)
    query = Column(Text, nullable=False)
    rank = Column(Integer, nullable=False)
    title = Column(Text, nullable=True)
    snippet = Column(Text, nullable=True)
    link = Column(Text, nullable=False)
    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<SerpResult(query_pack={self.query_pack}, rank={self.rank}, link={self.link[:50]})>"


class DiscoveryTarget(Base):
    """Normalized URL target to crawl."""

    __tablename__ = "discovery_targets"
    __table_args__ = {"schema": _DEFAULT_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(SQLEnum(SourceType), nullable=False, index=True)
    source_url_raw = Column(Text, nullable=False)
    source_url_normalized = Column(Text, nullable=False, unique=True, index=True)
    source_domain = Column(String(255), nullable=True, index=True)
    serp_query_pack = Column(String(100), nullable=True)
    serp_query = Column(Text, nullable=True)
    serp_evidence = Column(JSON, nullable=True)  # {title, snippet, rank}
    first_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    seen_count = Column(Integer, nullable=False, default=1)

    def __repr__(self):
        return f"<DiscoveryTarget(source_type={self.source_type}, url={self.source_url_normalized[:50]})>"


class Company(Base):
    """Canonical company record."""

    __tablename__ = "companies"
    __table_args__ = {"schema": _DEFAULT_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(255), nullable=True)
    company_domain = Column(String(255), nullable=False, unique=True, index=True)
    website_url = Column(String(500), nullable=True)
    business_type = Column(SQLEnum(BusinessType), nullable=False, default=BusinessType.UNKNOWN, index=True)
    business_type_confidence = Column(Float, nullable=False, default=0.0)
    classification_reasons = Column(JSON, nullable=True)  # list[str]
    first_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Company(domain={self.company_domain}, type={self.business_type})>"


class SignalSnapshot(Base):
    """Evidence for scoring (time-series friendly)."""

    __tablename__ = "signal_snapshots"
    __table_args__ = {"schema": _DEFAULT_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_domain = Column(String(255), nullable=False, index=True)
    source_type = Column(SQLEnum(SourceType), nullable=False, index=True)
    source_url_normalized = Column(Text, nullable=False)
    signals = Column(JSON, nullable=False)  # list[str]
    signal_details = Column(JSON, nullable=True)  # dict with jobs_count, roles_detected, etc.
    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    content_hash = Column(String(64), nullable=True, index=True)  # sha256

    def __repr__(self):
        return f"<SignalSnapshot(domain={self.company_domain}, source={self.source_type}, signals={len(self.signals)})>"


class Lead(Base):
    """Routable lead for outreach."""

    __tablename__ = "leads"
    __table_args__ = {"schema": _DEFAULT_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_domain = Column(String(255), nullable=False, index=True)
    route_flag = Column(SQLEnum(RouteFlag), nullable=False, index=True)
    mvp_intent_score = Column(Integer, nullable=False, default=0, index=True)
    partnership_fit_score = Column(Integer, nullable=False, default=0, index=True)
    score_breakdown = Column(JSON, nullable=True)  # dict
    recommended_channel = Column(SQLEnum(RecommendedChannel), nullable=True)
    outreach_note = Column(Text, nullable=True)
    status = Column(SQLEnum(LeadStatus), nullable=False, default=LeadStatus.NEW, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Lead(domain={self.company_domain}, route={self.route_flag}, mvp_score={self.mvp_intent_score})>"


def create_database_session(database_url: str, schema_name: Optional[str] = None):
    """
    Create database engine and session factory.
    
    Args:
        database_url: PostgreSQL connection string
        schema_name: Optional schema name. If not provided, uses DATABASE_SCHEMA env var or 'public'
    
    Returns:
        SessionLocal: SQLAlchemy session factory
    """
    # Use provided schema_name, or get from environment, or default to 'public'
    schema = schema_name or os.getenv("DATABASE_SCHEMA", "public")
    
    # Create engine
    engine = create_engine(database_url, echo=False)
    
    # Set search_path for the connection to use the specified schema
    @event.listens_for(engine, "connect", insert=True)
    def set_search_path(dbapi_conn, connection_record):
        """Set search_path on connection to use the specified schema."""
        cursor = dbapi_conn.cursor()
        cursor.execute(f"SET search_path TO {schema}, public")
        cursor.close()
    
    # Create schema if it doesn't exist (only if not 'public')
    if schema != "public":
        with engine.connect() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
            conn.commit()
    
    # Create all tables in the specified schema
    Base.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal

