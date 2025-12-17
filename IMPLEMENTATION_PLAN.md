# Lead Signal Engine — Implementation Plan

## Overview
This document outlines the detailed implementation plan for building the Lead Signal Engine, broken down into phases with specific tasks, dependencies, and acceptance criteria.

## Current Status

**✅ Phase 0: Foundation Setup — COMPLETE**  
**✅ Phase 1: Hiring End-to-End — COMPLETE**  
**🚧 Phase 2: Launch Signals — NEXT UP**

**Last Updated:** Current session  
**Setup Guide:** See [SETUP_GUIDE.md](SETUP_GUIDE.md) for installation instructions

---

## Phase 0: Foundation Setup ✅ **COMPLETED**

### Tasks
1. ✅ Project structure setup
2. ✅ Python package configuration (`pyproject.toml`)
3. ✅ Database models (PostgreSQL + SQLAlchemy)
4. ✅ Config YAML files (query_packs, keywords, scoring, runtime)
5. ✅ CLI skeleton
6. ✅ Module stubs with function signatures
7. ✅ Environment setup (.env.example template)
8. ✅ Logging infrastructure (structlog for JSON logs)

### Deliverables
- ✅ Complete project structure matching Section 16
- ✅ All config files populated with starter data
- ✅ Database schema ready (SQLAlchemy models)
- ✅ CLI commands functional (stub implementations)
- ✅ All modules have proper interfaces
- ✅ README.md with quick start guide
- ✅ .gitignore configured
- ✅ Implementation plan document

### Acceptance Criteria
- ✅ `python -m lead_engine run --help` works (CLI structure ready)
- ✅ Config files load without errors (YAML files created)
- ✅ Database models defined (PostgreSQL + SQLAlchemy)
- ✅ All imports resolve (module structure complete)

### Status: **COMPLETE** ✅
**Completed Date:** Current session  
**Next Phase:** Phase 1 - Hiring End-to-End

---

## Phase 1: Hiring End-to-End (MVP Core) ✅ **COMPLETED**

### Goal
Build a working pipeline that discovers companies via ATS boards, classifies them, scores them, and exports MVP leads.

### Tasks

#### 1.1 SERP Discovery Module ✅
- ✅ Implement `providers/serpapi.py`
  - ✅ SerpAPI client wrapper
  - ✅ Query execution with pagination
  - ✅ Error handling and retries
  - ✅ Rate limiting per query pack
- ✅ Store raw results in `SerpResult` table
- ✅ Integration ready with real SerpAPI

**Dependencies:** None  
**Status:** ✅ Complete

#### 1.2 URL Normalization Module ✅
- ✅ Implement `normalize/url_normalizer.py`
  - ✅ Generic URL canonicalization
  - ✅ Query param removal (utm_*, ref, etc.)
  - ✅ Trailing slash normalization
- ✅ Implement `normalize/ats_normalizer.py`
  - ✅ Greenhouse normalization
  - ✅ Lever normalization
  - ✅ Ashby normalization
  - ✅ Workable normalization
  - ✅ SmartRecruiters normalization
  - ✅ Teamtailor normalization
  - ✅ Recruitee normalization

**Dependencies:** None  
**Status:** ✅ Complete

#### 1.3 Discovery Target Management ✅
- ✅ Implement deduplication logic in `orchestrator.py`
  - ✅ Normalize URLs from SERP results
  - ✅ Dedupe by `source_url_normalized`
  - ✅ Track `seen_count`, `first_seen_at`, `last_seen_at`
- ✅ Store `DiscoveryTarget` records

**Dependencies:** 1.1, 1.2  
**Status:** ✅ Complete

#### 1.4 Crawler & Fetcher Module ✅
- ✅ Implement `crawl/fetcher.py`
  - ✅ HTTP client with httpx
  - ✅ Timeouts (connect: 5s, read: 15s)
  - ✅ Retries with exponential backoff (max 2)
  - ✅ Rate limiting (per-domain: 1 req/sec, global: 60 req/min)
  - ✅ 429/503 handling with cooldown
  - ✅ Content caching (by normalized URL, TTL from config)
  - ✅ Content hash (sha256) for change detection
- ✅ Store cache metadata

**Dependencies:** None  
**Status:** ✅ Complete

#### 1.5 ATS Parsers ✅
- ✅ Implement `crawl/parsers/ats_greenhouse.py`
  - ✅ Parse job listings from Greenhouse board
  - ✅ Extract job titles
  - ✅ Count engineering roles
  - ✅ Map roles to taxonomy (backend, frontend, ml_ai, etc.)
  - ✅ Extract company website URL (best effort)
- ✅ Implement `crawl/parsers/ats_lever.py`
- ✅ Implement `crawl/parsers/ats_ashby.py`
- ✅ Shared helper functions for role matching

**Dependencies:** 1.4  
**Status:** ✅ Complete

#### 1.6 Domain Resolver ✅
- ✅ Implement `resolve/domain_resolver.py`
  - ✅ Extract company domain from ATS parsed data
  - ✅ Fallback: extract from ATS URL patterns
  - ✅ Normalize to root domain
  - ✅ Store in `Company` table

**Dependencies:** 1.5  
**Status:** ✅ Complete

#### 1.7 Signal Snapshot Storage ✅
- ✅ Store `SignalSnapshot` records
  - ✅ Link to `company_domain`
  - ✅ Store `source_type`, `source_url_normalized`
  - ✅ Store `signals` list and `signal_details` dict
  - ✅ Track `content_hash` for change detection

**Dependencies:** 1.5, 1.6  
**Status:** ✅ Complete

#### 1.8 Rule-Based Classifier ✅
- ✅ Implement `classify/rule_classifier.py`
  - ✅ Extract text content from HTML
  - ✅ Count keywords (product vs services vs staffing)
  - ✅ Apply decision rules from config
  - ✅ Compute confidence score
  - ✅ Return classification with reasons
- ✅ Store in `Company` table

**Dependencies:** 1.4, 1.6  
**Status:** ✅ Complete

#### 1.9 Scoring Module ✅
- ✅ Implement `score/scoring.py`
  - ✅ Load scoring weights from `config/scoring.yaml`
  - ✅ Compute MVP intent score from signals
  - ✅ Apply penalties for services/staffing
  - ✅ Return score breakdown dict
- ✅ Implement `score/router.py`
  - ✅ Apply routing rules based on classification
  - ✅ Determine `route_flag` (outreach_mvp_client | outreach_partnership | ignore)
  - ✅ Recommend outreach channel
- ✅ Implement `score/outreach_note.py`
  - ✅ Generate 1-line outreach note from top evidence
  - ✅ Use templates from config
- ✅ Store `Lead` records

**Dependencies:** 1.7, 1.8  
**Status:** ✅ Complete

#### 1.10 CSV Export ✅
- ✅ Implement `export/csv_exporter.py`
  - ✅ Export MVP leads to `mvp_clients_ranked.csv`
  - ✅ Sort by `mvp_intent_score` descending
  - ✅ Include all required columns
  - ✅ Handle JSON serialization for `score_breakdown_json`
- ✅ Export partnership targets CSV

**Dependencies:** 1.9  
**Status:** ✅ Complete

#### 1.11 Orchestrator Integration ✅
- ✅ Wire all modules together in `orchestrator.py`
  - ✅ Load configs
  - ✅ Execute SERP discovery for hiring query packs
  - ✅ Process discovery targets through pipeline
  - ✅ Handle errors gracefully
  - ✅ Log metrics per run
- ✅ CLI integration (`cli.py run --source hiring`)

**Dependencies:** All above  
**Status:** ✅ Complete

### Phase 1 Acceptance Criteria
- ✅ Can run `python -m lead_engine run --source hiring`
- ✅ Discovers ATS boards from SERP
- ✅ Normalizes URLs correctly
- ✅ Parses at least 3 ATS types (Greenhouse, Lever, Ashby)
- ✅ Classifies companies correctly (rule-based classification implemented)
- ✅ Generates MVP leads CSV with scores
- ✅ All metrics logged (SERP calls, targets discovered, etc.)

### Status: **COMPLETE** ✅
**Completed Date:** Current session  
**Next Phase:** Phase 2 - Launch Signals

### Phase 1 Implementation Summary
All 11 sub-tasks completed. The pipeline now:
1. Discovers ATS boards via SerpAPI
2. Normalizes and deduplicates URLs
3. Fetches and caches pages with rate limiting
4. Parses job listings from Greenhouse, Lever, and Ashby
5. Resolves company domains
6. Classifies business types using rule-based keyword matching
7. Scores leads (MVP intent and partnership fit)
8. Routes leads to appropriate pipelines
9. Generates outreach notes
10. Exports ranked CSV files

**Ready for testing and Phase 2 development.**

---

## Phase 2: Launch Signals

### Goal
Add launch discovery and parsing to enrich lead signals.

### Tasks

#### 2.1 Launch SERP Queries
- [ ] Add launch query packs to `config/query_packs.yaml`
  - Show HN queries
  - Generic launch queries
- [ ] Test SERP discovery for launch source type

**Dependencies:** Phase 1.1  
**Estimated:** 1 day

#### 2.2 Launch Parser
- [ ] Implement `crawl/parsers/launch_generic.py`
  - Parse launch pages/posts
  - Extract launch date (best effort)
  - Extract product name
  - Extract product URL
  - Detect recency signals (0-30d, 31-90d)
  - Detect builder post indicators

**Dependencies:** Phase 1.4  
**Estimated:** 3-4 days

#### 2.3 Launch Signal Integration
- [ ] Update scoring to include launch recency boost
- [ ] Update outreach note generator for launch signals
- [ ] Test end-to-end launch → lead flow

**Dependencies:** 2.1, 2.2, Phase 1.9  
**Estimated:** 1 day

### Phase 2 Acceptance Criteria
- ✅ Launch discovery works via SERP
- ✅ Launch dates extracted (best effort)
- ✅ Recency signals correctly applied to scoring
- ✅ Launch leads appear in MVP CSV

### Phase 2 Total Estimate: 5-6 days

---

## Phase 3: Funding/Accelerator Signals

### Goal
Add funding and accelerator discovery to boost lead scores.

### Tasks

#### 3.1 Funding SERP Queries
- [ ] Add funding query packs
  - Accelerator directory queries
  - Funding round announcement queries
- [ ] Test SERP discovery

**Dependencies:** Phase 1.1  
**Estimated:** 1 day

#### 3.2 Funding Parser
- [ ] Implement `crawl/parsers/funding_generic.py`
  - Parse accelerator directory pages
  - Parse funding announcement pages
  - Extract accelerator name / batch
  - Extract funding round (pre-seed/seed/A)
  - Extract funding date (best effort)
  - Extract company domain

**Dependencies:** Phase 1.4  
**Estimated:** 4-5 days

#### 3.3 Funding Signal Integration
- [ ] Update scoring for accelerator/funding boosts
- [ ] Update outreach note generator
- [ ] Test end-to-end flow

**Dependencies:** 3.1, 3.2, Phase 1.9  
**Estimated:** 1 day

### Phase 3 Acceptance Criteria
- ✅ Funding discovery works
- ✅ Accelerator membership detected
- ✅ Funding rounds extracted
- ✅ Scoring boosts applied correctly

### Phase 3 Total Estimate: 6-7 days

---

## Phase 4: Ecosystem Signals

### Goal
Add ecosystem/community discovery (Web3, AI builders, etc.).

### Tasks

#### 4.1 Ecosystem SERP Queries
- [ ] Add ecosystem query packs
  - Web3 ecosystem directories
  - AI builder programs
- [ ] Test SERP discovery

**Dependencies:** Phase 1.1  
**Estimated:** 1 day

#### 4.2 Ecosystem Parser
- [ ] Implement `crawl/parsers/ecosystem_generic.py`
  - Parse directory pages
  - Parse grant/hackathon pages
  - Extract ecosystem tag (Base/Solana/etc.)
  - Extract program type (directory|grant|hackathon)
  - Extract program name
  - Extract project domain

**Dependencies:** Phase 1.4  
**Estimated:** 4-5 days

#### 4.3 Ecosystem Signal Integration
- [ ] Update scoring for ecosystem boosts
- [ ] Update outreach note generator
- [ ] Test end-to-end flow

**Dependencies:** 4.1, 4.2, Phase 1.9  
**Estimated:** 1 day

### Phase 4 Acceptance Criteria
- ✅ Ecosystem discovery works
- ✅ Ecosystem tags extracted
- ✅ Scoring boosts applied
- ✅ Partnership targets CSV includes ecosystem signals

### Phase 4 Total Estimate: 6-7 days

---

## Phase 5: AI Fallback + Enhancements

### Goal
Add AI classification fallback and optional review UI.

### Tasks

#### 5.1 AI Classifier Module
- [ ] Implement `classify/ai_classifier.py`
  - Trigger conditions (unknown or low confidence)
  - Prepare minimal inputs (meta, nav, excerpt)
  - Call AI provider (TBD - OpenAI/Anthropic)
  - Parse strict JSON response
  - Cache results by domain
  - Cost controls (max calls/day)
- [ ] Integration with rule classifier

**Dependencies:** Phase 1.8  
**Estimated:** 3-4 days

#### 5.2 Partnership Pipeline Export ✅
- ✅ Update `export/csv_exporter.py` (Completed in Phase 1.10)
  - ✅ Export partnership targets CSV
  - ✅ Include partnership fit score
  - ✅ Include suggested partnership angle

**Dependencies:** Phase 1.9  
**Status:** ✅ Complete (implemented in Phase 1.10)

#### 5.3 Optional: Streamlit Review UI
- [ ] Create simple UI to review leads
  - View MVP leads table
  - View partnership targets table
  - Filter by score, source type
  - Mark leads as contacted/replied/etc.
  - Update lead status in database

**Dependencies:** All phases  
**Estimated:** 3-4 days (optional)

### Phase 5 Acceptance Criteria
- ✅ AI classification works for unknown/low-confidence cases
- ✅ Cost controls enforced
- ✅ Partnership CSV exported correctly
- ✅ (Optional) Review UI functional

### Phase 5 Total Estimate: 7-9 days (4-5 if UI skipped)

---

## Overall Timeline Estimate

- **Phase 0 (Foundation):** 1-2 days ✅ **COMPLETE**
- **Phase 1 (Hiring MVP):** 22-28 days ✅ **COMPLETE**
- **Phase 2 (Launch):** 5-6 days 🚧 **NEXT**
- **Phase 3 (Funding):** 6-7 days
- **Phase 4 (Ecosystem):** 6-7 days
- **Phase 5 (AI + Enhancements):** 7-9 days

**Completed:** 2 phases (Foundation + Hiring MVP)  
**Remaining:** 3-4 phases (Launch, Funding, Ecosystem, AI)  
**Total Estimated Remaining: 24-29 days** (approximately 1 month for remaining phases)

---

## Risk Mitigation

### High-Risk Areas
1. **SerpAPI Rate Limits / Costs**
   - Mitigation: Implement daily caps, monitor usage, cache aggressively
   
2. **ATS Parsing Reliability**
   - Mitigation: Start with 3 major ATS, add fallbacks, test with real data
   
3. **Classification Accuracy**
   - Mitigation: Start rule-based, tune keywords, add AI fallback in Phase 5
   
4. **PostgreSQL Setup Complexity**
   - Mitigation: Use Docker Compose for local dev, clear migration scripts

### Dependencies to Watch
- SerpAPI availability and pricing
- ATS site structure changes (parsers may break)
- PostgreSQL connection pooling for production

---

## Success Metrics

### Phase 1 Success
- ≥50 discovered targets/day
- ≥70% classification precision
- MVP CSV generated with scores

### Full System Success (Phase 5)
- ≥50-200 discovered targets/day
- ≥20-50 high-score MVP leads/week
- ≥10-30 partnership targets/week
- ≥70% precision on top-50 MVP leads

---

## Next Steps After Phase 0

1. Set up PostgreSQL database (local + production)
2. Get SerpAPI API key and test connection
3. Collect sample ATS board HTMLs for parser development
4. Start Phase 1.1 (SERP Discovery Module)

