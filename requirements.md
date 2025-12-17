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

# Appendix A: Query Packs

Below is a starter pack that’s comprehensive but still manageable. Tune volumes via `runtime.yaml`.

## A1) Hiring — ATS Packs (High Priority)

### `hiring_greenhouse_v1`
- source_type: `hiring`
- queries:
  - `site:boards.greenhouse.io ("Backend Engineer" OR "Full Stack" OR "Software Engineer")`
  - `site:boards.greenhouse.io ("AI Engineer" OR "Machine Learning" OR "Data Engineer")`
  - `site:boards.greenhouse.io ("DevOps" OR "Platform Engineer" OR "SRE")`
  - `site:boards.greenhouse.io ("Solidity" OR "Blockchain" OR "Web3")`

### `hiring_lever_v1`
- queries:
  - `site:jobs.lever.co ("Backend" OR "Full Stack" OR "Software Engineer")`
  - `site:jobs.lever.co ("AI Engineer" OR "ML Engineer" OR "Data Engineer")`
  - `site:jobs.lever.co ("DevOps" OR "Platform")`
  - `site:jobs.lever.co ("Blockchain" OR "Solidity" OR "Web3")`

### `hiring_ashby_v1`
- queries:
  - `site:jobs.ashbyhq.com ("Software Engineer" OR "Backend" OR "Full Stack")`
  - `site:jobs.ashbyhq.com ("AI" OR "Machine Learning" OR "Data Engineer")`

### `hiring_workable_v1`
- queries:
  - `site:apply.workable.com ("Software Engineer" OR "Backend" OR "Full Stack")`

## A2) Launch Packs

### `launch_showhn_v1`
- queries:
  - `"Show HN" "launched" "we built"`
  - `"Show HN" ("MVP" OR "beta" OR "launch") ("AI" OR "SaaS" OR "developer tool")`

### `launch_generic_v1`
- queries:
  - `("just launched" OR "now live" OR "we launched") ("AI tool" OR "SaaS")`
  - `("shipping" OR "launching") ("MVP" OR "beta") ("startup")`

## A3) Funding / Accelerator Packs

### `funding_accelerator_v1`
- queries:
  - `("Y Combinator" OR "YC") "W" "companies"`
  - `"Techstars" "class of" "companies"`
  - `"accelerator" "demo day" "companies"`

### `funding_rounds_v1`
- queries:
  - `("raised" OR "secures") ("seed" OR "pre-seed" OR "Series A") "startup"`
  - `"led by" "seed round" "startup" ("platform" OR "SaaS")`

## A4) Ecosystem / Community Packs

### `ecosystem_web3_v1`
- queries:
  - `"Base ecosystem" "directory" "projects"`
  - `"Solana" "hackathon winners" "projects"`
  - `"Polygon grants" "recipients"`

### `ecosystem_ai_builders_v1`
- queries:
  - `"AI builder program" "cohort" "startups"`
  - `site:notion.site ("ecosystem" OR "builders") ("AI" OR "agents")`

---

# Appendix B: Keyword Taxonomies

## B1) Role Keywords (ATS parsing)
- backend: `backend`, `api`, `server`, `platform`
- frontend: `frontend`, `react`, `web`, `ui`
- fullstack: `full stack`, `fullstack`
- devops: `devops`, `sre`, `infrastructure`, `kubernetes`, `terraform`
- ml_ai: `machine learning`, `ml`, `ai engineer`, `llm`, `genai`
- data: `data engineer`, `analytics`, `pipeline`
- web3: `solidity`, `blockchain`, `web3`, `smart contract`

## B2) Product Indicators
- `pricing`, `docs`, `documentation`, `api`, `changelog`, `integrations`, `book a demo`, `customers`, `case studies` (careful), `status page`

## B3) Services/Agency Indicators
- `agency`, `consulting`, `software house`, `outsourcing`, `we help clients`, `our services`, `development services`, `custom solutions`

## B4) Staffing Indicators
- `staffing`, `recruiting`, `talent`, `hire developers`, `placement`, `headhunting`

---

# Appendix C: Scoring Weights

## C1) MVP Intent Score (default)
- ATS board exists: +3
- engineering_roles_count >= 3: +3
- engineering_roles_count >= 1: +2
- role tags include backend/fullstack/devops/ml: +2
- pricing page detected: +2
- docs/API detected: +2
- recent launch <= 30d: +3
- launch 31–90d: +1
- accelerator member: +2
- recent funding: +2
- ecosystem listed: +1

Penalties:
- services classification: -8
- staffing classification: -10

Thresholds:
- >= 8: prioritize
- 5–7: normal
- < 5: hold/ignore

## C2) Partnership Fit Score (default)
- services type confirmed: +2
- offers MVP/dev: +2
- hiring devs: +2
- niche match (AI/Web3/SaaS): +2
- case studies present: +1
- strong region: +1

---

# Appendix D: Sample Outputs

## D1) MVP CSV Row (example)
- company_name: `ExampleAI`
- company_domain: `exampleai.com`
- primary_source: `hiring`
- evidence_url: `https://jobs.lever.co/exampleai`
- mvp_intent_score: `10`
- roles_detected: `["backend","ml_ai"]`
- signals: `["ats_board_found","hiring_engineering","product_docs_found"]`
- recommended_channel: `email`
- outreach_note: `Noticed you're hiring backend/ML roles — happy to share a quick teardown to speed up execution.`

## D2) Partnership CSV Row (example)
- company_name: `Example Studio`
- business_type: `service_agency`
- partnership_fit_score: `7`
- outreach_note: `Looks like you ship MVPs for clients — open to a partnership for overflow engineering + AI/Web3 builds?`
