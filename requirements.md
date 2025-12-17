# Lead Signal Engine (Python) — Full Technical Spec Package

A SERP-driven discovery + classification + scoring system to generate two ranked pipelines:
1) **MVP Client Leads** (product companies under execution pressure)  
2) **Partnership Targets** (agencies/consultancies/system integrators worth partnering)

This package includes: architecture, modules, data schemas, config files, query packs, scoring rules, crawling rules, and operational requirements.

---

## Table of Contents
- [1. Goals](#1-goals)
- [2. Non-Goals](#2-non-goals)
- [3. System Overview](#3-system-overview)
- [4. Data Model](#4-data-model)
- [5. Config Files](#5-config-files)
- [6. SERP Discovery](#6-serp-discovery)
- [7. URL Normalization](#7-url-normalization)
- [8. Crawling & Extraction](#8-crawling--extraction)
- [9. Classification (Rules + AI Fallback)](#9-classification-rules--ai-fallback)
- [10. Scoring & Routing](#10-scoring--routing)
- [11. Exports](#11-exports)
- [12. Scheduling](#12-scheduling)
- [13. Observability](#13-observability)
- [14. Security & Compliance](#14-security--compliance)
- [15. Implementation Plan](#15-implementation-plan)
- [16. Repository Structure](#16-repository-structure)
- [17. Interfaces (Function Contracts)](#17-interfaces-function-contracts)
- [Appendix A: Query Packs](#appendix-a-query-packs)
- [Appendix B: Keyword Taxonomies](#appendix-b-keyword-taxonomies)
- [Appendix C: Scoring Weights](#appendix-c-scoring-weights)
- [Appendix D: Sample Outputs](#appendix-d-sample-outputs)

---

## 1. Goals

### 1.1 Primary Goal
Continuously discover and rank companies likely to need:
- MVP build/iteration
- Fractional CTO execution help
- AI automation / Web3 execution support

### 1.2 Output Pipelines
- **MVP Client Pipeline**: product companies with strong intent signals  
- **Partnership Pipeline**: service agencies/consultancies/integrators (do not exclude, route)

### 1.3 KPIs (v1 targets)
- ≥ **50–200** discovered targets/day (configurable)
- ≥ **20–50** high-score MVP leads/week
- ≥ **10–30** partnership targets/week
- ≥ **70%** of top-50 MVP leads are true product companies (precision)

---

## 2. Non-Goals
- No scraping Apollo UI or LinkedIn behind login
- No reverse-engineering private APIs
- No bulk emailing or spam automation in v1
- No personal data enrichment that requires restricted sources

---

## 3. System Overview

### 3.1 Pipeline Stages
1. **SERP Discovery** (SerpAPI)  
2. **Normalize + Dedupe** URLs  
3. **Fetch public pages** (ATS boards, launch pages, accelerator pages, ecosystem directories)  
4. **Resolve company domain**  
5. **Classify business type** (rule-based, AI fallback optional)  
6. **Extract signals**  
7. **Score + Route** to MVP vs Partnership  
8. **Export ranked datasets** (CSV + optional Sheets/Notion later)

### 3.2 Source Types
- `hiring`: ATS boards & job signals  
- `launch`: fresh launch posts/pages  
- `funding`: fundraising / accelerator signals  
- `ecosystem`: directories, grants, hackathons, community lists

---

## 4. Data Model

### 4.1 Core Entities

#### `SerpResult`
Stores raw SERP results for audit/debug.
- `provider`: `"serpapi"`
- `query_pack`: string
- `query`: string
- `rank`: int
- `title`: string
- `snippet`: string
- `link`: string
- `fetched_at`: datetime

#### `DiscoveryTarget`
Normalized URL target to crawl.
- `source_type`: `hiring|launch|funding|ecosystem`
- `source_url_raw`: string
- `source_url_normalized`: string
- `source_domain`: string
- `serp_query_pack`: string
- `serp_query`: string
- `serp_evidence`: dict `{title, snippet, rank}`
- `first_seen_at`: datetime
- `last_seen_at`: datetime
- `seen_count`: int

#### `Company`
Canonical company record.
- `company_name`: string
- `company_domain`: string (root domain)
- `website_url`: string
- `business_type`: enum
- `business_type_confidence`: float 0..1
- `classification_reasons`: list[str]
- `first_seen_at`, `last_seen_at`: datetime

Business type enum:
- `product_company`
- `service_agency`
- `consultancy`
- `system_integrator`
- `staffing_recruiter`
- `open_source_community`
- `unknown`

#### `SignalSnapshot`
Evidence for scoring (time-series friendly).
- `company_domain`: string
- `source_type`: enum
- `source_url_normalized`: string
- `signals`: list[str]
- `signal_details`: dict (jobs_count, roles_detected, launch_date, etc.)
- `fetched_at`: datetime
- `content_hash`: string

#### `Lead`
Routable lead for outreach.
- `company_domain`
- `route_flag`: enum `outreach_mvp_client|outreach_partnership|ignore`
- `mvp_intent_score`: int
- `partnership_fit_score`: int
- `score_breakdown`: dict
- `recommended_channel`: enum `linkedin_dm|x_dm|email|partner_intro`
- `outreach_note`: string
- `status`: enum `new|queued|contacted|replied|booked|closed|archived`

---

## 5. Config Files

All behavior is driven by YAML config, so you can iterate without code changes.

### 5.1 `config/query_packs.yaml`
Defines SERP query packs per source type.
- pack name
- source_type
- queries list
- SERP params (hl/gl/num/pages)
- normalization strategy

### 5.2 `config/keywords.yaml`
- ATS role taxonomy keywords
- product indicators
- services/agency indicators
- staffing/recruiter indicators
- negative keywords
- outreach-note templates

### 5.3 `config/scoring.yaml`
Weights and thresholds for:
- MVP intent scoring
- partnership scoring
- routing thresholds
- AI fallback confidence thresholds

### 5.4 `config/runtime.yaml`
- rate limits
- concurrency
- caching TTL
- daily caps per query pack
- user agent strings

---

## 6. SERP Discovery

### 6.1 Provider: SerpAPI (Google engine)

#### Required environment variables
- `SERPAPI_API_KEY`

#### SERP request parameters (baseline)
- `engine=google`
- `q=<query>`
- `hl=en`
- `gl=us`
- `num=10|20|50`
- `start=0,10,20...` (pagination)

### 6.2 Discovery Execution Rules
- Each query pack defines:
  - `results_per_page` (num)
  - `pages` (how many pages to fetch)
  - `daily_cap` (max SERP calls/day)
- Store all raw results in `SerpResult`
- Convert each result into a `DiscoveryTarget`:
  - apply URL normalization
  - dedupe by normalized URL

### 6.3 Dedupe Strategy
- Dedupe keys:
  - `source_url_normalized`
  - `company_domain` (if resolved)
- Keep `seen_count`, `first_seen_at`, `last_seen_at`

---

## 7. URL Normalization

Normalization ensures the crawler fetches stable “root targets”, not noisy deep links.

### 7.1 ATS Normalization Rules (must)
Convert job posting URLs to board root URLs.

Supported ATS:
- Greenhouse: `boards.greenhouse.io/<slug>`
- Lever: `jobs.lever.co/<slug>`
- Ashby: `jobs.ashbyhq.com/<slug>`
- Workable: `apply.workable.com/<slug>`
- SmartRecruiters: `careers.smartrecruiters.com/<slug>`
- Teamtailor: `<slug>.teamtailor.com/jobs` (normalize to that)
- Recruitee: `<slug>.recruitee.com` (or `/o/` paths normalize to root)

### 7.2 Launch/Funding/Ecosystem Normalization
- Remove tracking params (`utm_*`, `ref`, etc.)
- Normalize to canonical if `rel=canonical` exists
- Strip fragments `#...`

### 7.3 URL Canonicalization Steps
1. Parse URL
2. Lowercase scheme+host
3. Remove default ports
4. Remove query params matching denylist
5. Strip trailing slash (consistent rule)
6. Return normalized string

---

## 8. Crawling & Extraction

### 8.1 Fetcher Requirements
- Use `httpx` or `requests`
- Timeouts:
  - connect: 5s
  - read: 15s
- Retries:
  - max 2
  - exponential backoff
- Rate limiting:
  - per-domain: 1 req/sec
  - global: 60 req/min (configurable)
- Respect 429/503 with cooldown

### 8.2 Caching
- Cache by normalized URL for `cache_ttl_hours` (default 24h)
- Store:
  - status code
  - content hash (sha256)
  - fetched_at
- Skip reprocessing unchanged content within TTL

### 8.3 Parsers by Source Type

#### 8.3.1 Hiring (ATS) Parser
Inputs: normalized ATS board URL  
Outputs:
- `jobs_count`
- `engineering_roles_count`
- `roles_detected` (taxonomy tags)
- `job_titles` (optional)
- `company_website_url` (best effort)
- signals:
  - `ats_board_found`
  - `hiring_engineering`
  - `hiring_ai`
  - `hiring_web3`
  - `hiring_devops`

Extraction approach:
- HTML parse (BeautifulSoup)
- Identify job title elements (ATS-specific patterns)
- Keyword match titles → taxonomy

#### 8.3.2 Launch Parser
Inputs: launch page/post URL  
Outputs:
- `launch_date` (best effort)
- `product_name`
- `product_url`
- `company_domain` resolved from product_url
- signals:
  - `recent_launch_0_30d`
  - `recent_launch_31_90d`
  - `builder_post`

#### 8.3.3 Funding/Accelerator Parser
Inputs: accelerator directory page or funding announcement page  
Outputs:
- `accelerator_name` / `batch`
- `funding_round` (pre-seed/seed/A)
- `funding_date` (best effort)
- `company_domain`
- signals:
  - `accelerator_member`
  - `recent_funding`

#### 8.3.4 Ecosystem/Community Parser
Inputs: directory/grants/hackathon page  
Outputs:
- `ecosystem_tag` (Base/Solana/etc.)
- `program_type` (directory|grant|hackathon)
- `program_name`
- `project_domain`
- signals:
  - `ecosystem_listed`
  - `grant_recipient`
  - `hackathon_winner`

---

## 9. Classification (Rules + AI Fallback)

### 9.1 Rule-Based Classifier (Primary)
Fetch up to 3 pages:
- `/` homepage
- `/about` if exists
- one of: `/pricing`, `/docs`, `/services` if exists

Compute keyword counts:
- `product_indicators_count`
- `services_indicators_count`
- `staffing_indicators_count`

Decision rules:
- If staffing_count >= threshold → `staffing_recruiter`
- Else if services_count - product_count >= delta → `service_agency|consultancy|system_integrator`
- Else if product_count - services_count >= delta → `product_company`
- Else → `unknown`

Confidence:
- Based on absolute keyword difference + presence of strong indicators (pricing/docs vs services)

### 9.2 AI Fallback (Optional, Controlled)
Trigger AI classification only if:
- rule result is `unknown`, OR
- confidence < `ai_fallback_confidence_threshold` (e.g. 0.65)

AI inputs (minimal):
- meta title/description
- nav links
- excerpt (2–4k chars)

AI output strict JSON:
- `business_type`
- `confidence`
- `reasons` (3 bullets)
- `partnership_hint` (bool)

Cost controls:
- max AI calls/day
- cache by domain

---

## 10. Scoring & Routing

### 10.1 MVP Intent Score
Computed from signals across all sources.

Typical scoring inputs:
- Hiring signals (strong)
- Product indicators (pricing/docs)
- Recency (launch/funding)
- Ecosystem participation (optional boost)

### 10.2 Partnership Fit Score
Computed if classified as services/consultancy/integrator.

### 10.3 Routing Rules
- `product_company` → `outreach_mvp_client`
- `service_agency|consultancy|system_integrator` → `outreach_partnership`
- `staffing_recruiter` → `ignore`
- `unknown`:
  - if hiring_engineering strong → `outreach_mvp_client` (low priority)
  - else → `ignore`

### 10.4 Recommended Outreach Channel (Heuristic)
- If launch/ecosystem signals present → `x_dm` or `linkedin_dm`
- If hiring + B2B → `email` (manual) or `linkedin_dm`
- If partnership → `linkedin_dm`

### 10.5 Outreach Note Generator
Generate a 1-line hook using top evidence:
Examples:
- “Noticed you’re hiring backend/full-stack roles — execution bandwidth is usually tight at this stage.”
- “Saw your recent launch — happy to share a quick teardown to speed up iteration.”

---

## 11. Exports

### 11.1 MVP Leads CSV (`mvp_clients_ranked.csv`)
Columns:
- `company_name`
- `company_domain`
- `website_url`
- `primary_source` (hiring|launch|funding|ecosystem)
- `evidence_url`
- `mvp_intent_score`
- `roles_detected`
- `signals`
- `score_breakdown_json`
- `recommended_channel`
- `outreach_note`

### 11.2 Partnership Targets CSV (`partnership_targets_ranked.csv`)
Columns:
- `company_name`
- `company_domain`
- `website_url`
- `business_type`
- `partnership_fit_score`
- `signals`
- `score_breakdown_json`
- `suggested_partnership_angle`

---

## 12. Scheduling

### Default schedule
- Hiring discovery: daily
- Launch discovery: daily
- Funding: weekly
- Ecosystem: weekly
- Refresh top targets: weekly

### Execution Modes
- `python -m lead_engine run --source hiring`
- `python -m lead_engine run --all`

---

## 13. Observability

### Metrics to log per run
- SERP calls made per pack
- new targets discovered
- targets crawled
- domains resolved
- classified counts by business_type
- leads exported counts
- AI calls made (if enabled)
- error rates by domain

### Logs
- JSON logs with correlation id per run
- store failed URLs for retry queue

---

## 14. Security & Compliance
- No auth scraping
- Respect robots where reasonable
- Rate limits to prevent abuse
- Store only company-level public data in v1
- Avoid storing personal emails unless explicitly public on company site

---

## 15. Implementation Plan

### Phase 1 (Hiring end-to-end)
- SerpAPI client + query runner
- ATS normalization + dedupe
- ATS crawler + role extraction
- Website resolver
- Rule-based classification
- MVP scoring + export

### Phase 2 (Launch)
- SERP queries for launch signals
- launch parser
- recency scoring

### Phase 3 (Funding/Accelerator)
- SERP queries for accelerator directories + funding announcements
- funding parser (best effort)
- scoring boost

### Phase 4 (Ecosystem)
- SERP queries for directories/grants/hackathons
- ecosystem parser
- scoring boost

### Phase 5 (AI fallback + mini UI)
- AI classification fallback
- Streamlit review UI (optional)

---

## 16. Repository Structure

```
lead-signal-engine/
  README.md
  pyproject.toml
  config/
    query_packs.yaml
    keywords.yaml
    scoring.yaml
    runtime.yaml
  src/lead_engine/
    __init__.py
    cli.py
    orchestrator.py
    providers/
      serpapi.py
    normalize/
      url_normalizer.py
      ats_normalizer.py
    crawl/
      fetcher.py
      parsers/
        ats_greenhouse.py
        ats_lever.py
        ats_ashby.py
        launch_generic.py
        funding_generic.py
        ecosystem_generic.py
    resolve/
      domain_resolver.py
    classify/
      rule_classifier.py
      ai_classifier.py
    score/
      scoring.py
      router.py
      outreach_note.py
    storage/
      sqlite_store.py
      models.py
    export/
      csv_exporter.py
  data/
    cache/
    output/
```

---

## 17. Interfaces (Function Contracts)

### SERP provider
```python
def serp_search(query: str, *, params: dict) -> list[dict]:
    """Return list of raw serp results with fields: title, snippet, link, rank."""
```

### Normalizer
```python
def normalize_url(url: str) -> str
def normalize_ats_url(url: str) -> str | None
```

### Fetcher
```python
def fetch(url: str) -> tuple[int, str, dict]:
    """Return (status_code, html_text, response_meta)."""
```

### Parsers
```python
def parse_ats_board(url: str, html: str) -> dict
def parse_launch_page(url: str, html: str) -> dict
def parse_funding_page(url: str, html: str) -> dict
def parse_ecosystem_page(url: str, html: str) -> dict
```

### Resolver
```python
def resolve_company_domain(parsed: dict) -> str | None
```

### Classifier
```python
def classify_domain(domain: str, pages: dict) -> dict
# returns {business_type, confidence, reasons}
```

### Scoring + routing
```python
def score_lead(company: dict, snapshot: dict, classification: dict) -> dict
# returns scores + breakdown

def route_lead(classification: dict, scores: dict) -> dict
# returns route_flag + recommended_channel
```

---

# Appendix A: Query Packs (Updated)

Below is a starter pack that’s comprehensive but still manageable. Tune volumes via `runtime.yaml`.
Recommended default cadence:
- Hiring (ATS): daily
- Launch: daily (lower volume)
- Funding/Accelerator: weekly (enrichment + priority boost)
- Ecosystem/Community: weekly (pipeline + niche)

## A0) Global Query Conventions (applies to all packs)

### Stage/intent modifiers (additive tokens)
Use these tokens in queries to bias toward early-stage execution:
- `"founding" OR "founder" OR "early-stage" OR "seed" OR "pre-seed" OR "startup"`
- `"0 to 1" OR "0-1" OR "MVP" OR "greenfield" OR "build" OR "shipping"`
- `"small team" OR "lean team"`

### Optional noise-reduction (careful; can over-filter)
- `-"enterprise"` `-"Fortune"` `-"bank"` `-"university"` (only if your results get too enterprise-heavy)

---

## A1) Hiring — ATS Packs (High Priority, Early-Stage Biased)

### `hiring_greenhouse_stage_v2`
- source_type: `hiring`
- queries:
  - `site:boards.greenhouse.io ("Founding Engineer" OR "Founding Software Engineer" OR "Founding Full Stack")`
  - `site:boards.greenhouse.io ("Full Stack" OR "Full-Stack" OR "Backend Engineer") ("startup" OR "early-stage" OR "seed" OR "pre-seed")`
  - `site:boards.greenhouse.io ("Platform Engineer" OR "DevOps" OR "SRE") ("startup" OR "seed")`
  - `site:boards.greenhouse.io ("Machine Learning" OR "AI Engineer" OR "LLM" OR "GenAI") ("startup" OR "seed" OR "early-stage")`
  - `site:boards.greenhouse.io ("Product Engineer" OR "Engineering Generalist") ("startup" OR "early-stage")`
  - `site:boards.greenhouse.io ("Solidity" OR "Blockchain" OR "Web3") ("startup" OR "seed")`

### `hiring_lever_stage_v2`
- source_type: `hiring`
- queries:
  - `site:jobs.lever.co ("Founding Engineer" OR "Founding Full Stack" OR "Founding Backend")`
  - `site:jobs.lever.co ("Full Stack" OR "Backend") ("startup" OR "seed" OR "early-stage")`
  - `site:jobs.lever.co ("Platform" OR "DevOps" OR "SRE") ("startup" OR "seed")`
  - `site:jobs.lever.co ("AI Engineer" OR "ML Engineer" OR "LLM" OR "GenAI") ("startup" OR "seed")`
  - `site:jobs.lever.co ("Solidity" OR "Blockchain" OR "Web3") ("startup" OR "seed")`

### `hiring_ashby_stage_v2`
- source_type: `hiring`
- queries:
  - `site:jobs.ashbyhq.com ("Founding" OR "0 to 1" OR "0-1") ("Engineer" OR "Full Stack" OR "Backend")`
  - `site:jobs.ashbyhq.com ("Full Stack" OR "Backend" OR "Product Engineer") ("startup" OR "seed" OR "early-stage")`
  - `site:jobs.ashbyhq.com ("AI Engineer" OR "Machine Learning" OR "LLM" OR "GenAI") ("startup" OR "seed")`
  - `site:jobs.ashbyhq.com ("Platform" OR "DevOps" OR "SRE") ("startup" OR "seed")`

### `hiring_workable_stage_v2`
- source_type: `hiring`
- queries:
  - `site:apply.workable.com ("Founding Engineer" OR "Full Stack" OR "Backend") ("startup" OR "seed" OR "early-stage")`
  - `site:apply.workable.com ("AI Engineer" OR "Machine Learning" OR "LLM") ("startup" OR "seed")`

### `hiring_teamtailor_stage_v2`
- source_type: `hiring`
- queries:
  - `site:teamtailor.com ("Founding Engineer" OR "Full Stack" OR "Backend") ("startup" OR "seed" OR "early-stage")`
  - `site:teamtailor.com ("AI Engineer" OR "Machine Learning" OR "LLM") ("startup" OR "seed")`
  - `site:teamtailor.com ("DevOps" OR "Platform" OR "SRE") ("startup" OR "seed")`

### `hiring_recruitee_stage_v2`
- source_type: `hiring`
- queries:
  - `site:recruitee.com ("Founding" OR "Full Stack" OR "Backend") ("startup" OR "seed" OR "early-stage")`
  - `site:recruitee.com ("AI Engineer" OR "Machine Learning" OR "LLM") ("startup" OR "seed")`

### `hiring_smartrecruiters_stage_v2`  *(lower priority; enterprise-skew)*
- source_type: `hiring`
- queries:
  - `site:careers.smartrecruiters.com ("Full Stack" OR "Backend") ("startup" OR "seed" OR "early-stage")`
  - `site:careers.smartrecruiters.com ("AI Engineer" OR "Machine Learning") ("startup" OR "seed")`

---

## A1P) Partnership Discovery (Agencies / Consultancies / Integrators)

Purpose: build a **partnership pipeline**, not client pipeline. These leads route to `outreach_partnership`.

### `partner_agency_services_v1`
- source_type: `hiring`  *(discovery category; routing handled later)*
- queries:
  - `("software development agency" OR "product studio" OR "MVP development") ("looking for partners" OR "white label" OR "overflow")`
  - `("digital agency" OR "branding agency") ("need a dev partner" OR "engineering partner" OR "technical partner")`
  - `("fractional CTO" OR "CTO as a service") ("partner" OR "collaboration" OR "referral")`

### `partner_agency_hiring_pressure_v1`
- source_type: `hiring`
- queries:
  - `("agency" OR "studio" OR "consulting") ("hiring" OR "we are hiring") ("full stack" OR "backend" OR "AI engineer")`
  - `("product studio" OR "software agency") ("DevOps" OR "platform engineer")`

### `partner_system_integrator_v1`
- source_type: `hiring`
- queries:
  - `("system integrator" OR "implementation partner") ("SaaS" OR "AI" OR "automation")`
  - `("HubSpot partner" OR "Salesforce partner") ("engineering" OR "custom integration")`

---

## A2) Launch Packs (Secondary Discovery + Messaging Hooks)

Bias toward **recent launches / shipping cadence** (better than generic “launch” queries).

### `launch_showhn_recent_v2`
- source_type: `launch`
- queries:
  - `"Show HN" ("launched" OR "built" OR "released") ("MVP" OR "beta" OR "v1")`
  - `"Show HN" ("we built" OR "we made") ("AI" OR "agent" OR "automation" OR "developer tool")`

### `launch_shipping_cadence_v2`
- source_type: `launch`
- queries:
  - `("now live" OR "just launched" OR "released v1" OR "shipping") ("AI" OR "SaaS" OR "automation")`
  - `("changelog" OR "release notes") ("v1" OR "v0.1") ("SaaS" OR "platform")`
  - `("public beta" OR "beta launch") ("AI" OR "SaaS")`

### `launch_producthunt_makers_v2` *(optional if you want PH as a channel)*
- source_type: `launch`
- queries:
  - `site:producthunt.com ("AI" OR "productivity" OR "developer tool") ("today" OR "featured")`
  - `site:producthunt.com ("makers" OR "maker") ("launched" OR "shipping")`

---

## A3) Funding / Accelerator Packs (Enrichment + Priority Boost)

Funding is a **priority multiplier**, not your primary discovery engine.

### `funding_seed_preseed_v2`
- source_type: `funding`
- queries:
  - `("raised" OR "secures" OR "announces") ("pre-seed" OR "seed") ("AI" OR "SaaS" OR "platform")`
  - `("led by") ("seed round" OR "pre-seed") ("startup") ("SaaS" OR "platform")`
  - `("closing" OR "closed") ("seed round" OR "pre-seed") ("startup")`

### `accelerator_cohorts_v2`
- source_type: `funding`
- queries:
  - `site:ycombinator.com/companies ("AI" OR "B2B" OR "fintech")`
  - `("Techstars" OR "500 Global" OR "Antler") ("cohort" OR "batch" OR "demo day") "companies"`
  - `("accelerator" OR "incubator") ("demo day" OR "batch") ("AI" OR "SaaS") "companies"`

### `funding_seriesA_filter_v2` *(optional)*
- source_type: `funding`
- queries:
  - `("raised" OR "announces") ("Series A") ("B2B" OR "SaaS" OR "AI") "startup"`

---

## A4) Ecosystem / Community Packs (Pipeline + Niche)

Use these to find builders who may be earlier-stage, and to enrich positioning for Web3/AI.

### `ecosystem_web3_directories_v2`
- source_type: `ecosystem`
- queries:
  - `"Base ecosystem" ("directory" OR "projects" OR "companies")`
  - `"Solana ecosystem" ("directory" OR "projects")`
  - `"Polygon ecosystem" ("directory" OR "projects")`
  - `"Ethereum" "hackathon winners" "projects"`

### `ecosystem_grants_hackathons_v2`
- source_type: `ecosystem`
- queries:
  - `("grants" OR "grant program") "recipients" ("Base" OR "Solana" OR "Polygon")`
  - `("hackathon" OR "demo day") ("winners" OR "finalists") ("AI" OR "agent" OR "web3")`

### `ecosystem_ai_builders_v2`
- source_type: `ecosystem`
- queries:
  - `"AI builder program" ("cohort" OR "batch") ("startups" OR "companies")`
  - `("AI agents" OR "agentic") ("community" OR "builders") ("directory" OR "list")`
  - `site:notion.site ("builders" OR "ecosystem") ("AI" OR "agents")`

---

# Appendix B: Keyword Taxonomies (Updated)

## B0) Stage & Intent Keywords (new)
Use these for “early-stage bias” and for outreach-note generation.

- stage_early: `founding`, `founder`, `early-stage`, `seed`, `pre-seed`, `startup`, `small team`, `lean team`
- stage_build: `0 to 1`, `0-1`, `greenfield`, `MVP`, `beta`, `v1`, `shipping`, `launch`
- urgency: `urgent`, `asap`, `immediately`, `high priority`

## B1) Role Keywords (ATS parsing) — expanded
- backend: `backend`, `api`, `server`, `platform`, `distributed systems`, `microservices`
- frontend: `frontend`, `react`, `next.js`, `web`, `ui`, `typescript`
- fullstack: `full stack`, `fullstack`, `product engineer`, `engineering generalist`
- devops: `devops`, `sre`, `infrastructure`, `kubernetes`, `terraform`, `observability`
- ml_ai: `machine learning`, `ml`, `ai engineer`, `llm`, `genai`, `rag`, `agents`, `prompt`
- data: `data engineer`, `analytics`, `pipeline`, `etl`, `warehouse`
- web3: `solidity`, `blockchain`, `web3`, `smart contract`, `defi`, `evm`

## B2) Product Indicators (keep + tighten)
- strong_product: `pricing`, `docs`, `documentation`, `api`, `changelog`, `integrations`, `status page`
- sales_motion: `book a demo`, `talk to sales`, `request a demo`, `case studies` *(low weight, can be faked)*, `customers`

## B3) Services/Agency Indicators (route to partnership, not delete)
- services: `agency`, `consulting`, `product studio`, `software house`, `outsourcing`, `we help clients`, `our services`, `development services`, `custom solutions`, `implementation partner`

## B4) Staffing Indicators (ignore by default)
- staffing: `staffing`, `recruiting`, `talent`, `placement`, `headhunting`, `hire developers`, `body shop`

## B5) Enterprise / Low-Fit Indicators (new penalties)
Use to reduce “big corp hiring” noise.
- enterprise_noise: `enterprise`, `fortune`, `global leader`, `bank`, `government`, `university`, `public sector`, `conglomerate`
- huge_hiring: `100+ openings`, `our 10,000 employees`, `worldwide offices`

## B6) Partnership Fit Indicators (new)
- partner_fit: `white label`, `referral`, `overflow`, `capacity`, `delivery partner`, `technical partner`, `implementation partner`, `co-delivery`

---

# Appendix C: Scoring Weights (Updated)

Scoring is now explicitly aligned to:
- **ICP = MVP / early-stage execution teams**
- **ATS = best discovery signal**
- **Funding/launch/ecosystem = multipliers + secondary discovery**
- **Partnership = separate lane**

## C0) Common Concepts
- `stage_boost`: applied when early-stage keywords present
- `enterprise_penalty`: applied when enterprise noise present
- `hiring_intensity`: derived from job count and engineering share

---

## C1) MVP Intent Score (0–100 suggested)

### Hiring (weight dominant)
- ATS board exists: +20
- engineering_roles_count:
  - 1–2: +8
  - 3–5: +15
  - 6–10: +20
  - 11+: +12 *(cap to avoid enterprise; often noisy)*
- founding/0→1 language in job titles/snippets: +12
- role tags include backend/fullstack/devops/ml: +8
- “product engineer” / “engineering generalist”: +6

### Product signals (quality filter)
- pricing page detected: +8
- docs/API detected: +8
- integrations/status page detected: +4

### Recency multipliers (secondary)
- recent launch <= 30d: +10
- launch 31–90d: +4
- pre-seed/seed funding (<= 12 mo): +10
- Series A (<= 18 mo): +8
- accelerator member: +8
- ecosystem listed / grant / hackathon: +4

### Penalties (hard filters)
- classified services/agency/consultancy: -25 *(route to partnership lane instead)*
- classified staffing/recruiter: -40 *(ignore)*
- enterprise_noise detected: -10
- huge_hiring indicators: -10

### Thresholds (runway-focused)
- **>= 65**: A-tier (personalized outreach now)
- **50–64**: B-tier (semi-templated outreach)
- **< 50**: hold/nurture (or ignore if low quality)

---

## C2) Partnership Fit Score (0–100 suggested)

### Base
- business_type in {service_agency, consultancy, system_integrator}: +20

### Signals of good partner
- mentions “product studio” / “MVP development”: +10
- mentions “white label” / “overflow” / “referral”: +15
- hiring engineers (capacity pressure): +10
- niche alignment (AI/Web3/SaaS/dev tooling): +10
- strong portfolio/case studies present: +6
- has clear inbound channel (newsletter/community): +6

### Penalties
- staffing/recruiter language: -30 *(not a partner; ignore by default)*
- extremely broad “we do everything” agency: -10

### Thresholds
- **>= 60**: partnership outreach
- **45–59**: monitor
- **< 45**: ignore

---

# Appendix D: Sample Outputs (Updated)

## D1) MVP CSV Row (A-tier example)
- company_name: `ExampleAI`
- company_domain: `exampleai.com`
- primary_source: `hiring`
- evidence_url: `https://jobs.lever.co/exampleai`
- mvp_intent_score: `72`
- roles_detected: `["fullstack","ml_ai"]`
- signals: `["ats_board_found","hiring_engineering","stage_early","product_docs_found"]`
- recommended_channel: `linkedin_dm`
- outreach_note: `Saw you're hiring a founding/full-stack role — teams at this stage usually hit execution bottlenecks. I can ship production MVP increments fast (CTO + delivery).`

## D2) MVP CSV Row (B-tier example)
- company_name: `ShippingTool`
- company_domain: `shippingtool.io`
- primary_source: `launch`
- evidence_url: `https://news.ycombinator.com/item?id=xxxx`
- mvp_intent_score: `56`
- roles_detected: `[]`
- signals: `["recent_launch_0_30d","builder_post"]`
- recommended_channel: `x_dm`
- outreach_note: `Congrats on the v1 launch — happy to share a quick teardown + 3 quick wins to speed up the next 2 weeks of shipping.`

## D3) Partnership CSV Row (strong partner example)
- company_name: `Example Studio`
- company_domain: `examplestudio.com`
- business_type: `service_agency`
- partnership_fit_score: `67`
- signals: `["services_detected","partner_fit_white_label","hiring_engineering"]`
- recommended_channel: `linkedin_dm`
- outreach_note: `Looks like you ship MVPs for clients. Open to a co-delivery partnership? I handle complex backend/AI agents while you run design/PM — fast, clean, and white-label friendly.`

