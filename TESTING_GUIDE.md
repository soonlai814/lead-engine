# Lead Signal Engine — Testing Guide

Complete guide for testing the Lead Signal Engine pipeline.

---

## Table of Contents

1. [Quick Test](#quick-test)
2. [Dry Run Testing](#dry-run-testing)
3. [End-to-End Testing](#end-to-end-testing)
4. [Component Testing](#component-testing)
5. [Verifying Results](#verifying-results)
6. [Test Scenarios](#test-scenarios)
7. [Troubleshooting Tests](#troubleshooting-tests)

---

## Quick Test

### Prerequisites Check

Before testing, ensure:
1. ✅ Virtual environment is activated
2. ✅ `.env` file configured with `SERPAPI_API_KEY` and `DATABASE_URL`
3. ✅ PostgreSQL database is running
4. ✅ Package is installed: `pip install -e .`

### Basic Smoke Test

```bash
# 1. Test CLI works
python -m lead_engine --help

# 2. Test with dry-run (no database writes, no API costs)
python -m lead_engine run --source hiring --dry-run

# 3. Check logs output (should see JSON logs)
python -m lead_engine run --source hiring --dry-run 2>&1 | head -20
```

**Expected:** CLI should show help menu, dry-run should execute without errors, logs should appear in JSON format.

---

## Dry Run Testing

Dry-run mode allows you to test the pipeline without:
- Writing to database
- Making SerpAPI calls (if you want to avoid costs)
- Creating actual leads

### Test Discovery Only (Dry Run)

```bash
# Test hiring discovery in dry-run mode
python -m lead_engine run --source hiring --dry-run
```

**What happens:**
- ✅ Config files are loaded
- ✅ Orchestrator initializes
- ✅ SERP queries are prepared (but not executed if you want to skip)
- ✅ No database writes
- ✅ Logs show what would happen

**Check logs for:**
- `"Orchestrator initialized"`
- `"Running discovery for source type"`
- `"Found query packs"`
- `"Processing query pack"`

### Limiting Test Scope

To test with minimal SerpAPI calls, temporarily modify `config/query_packs.yaml`:

```yaml
hiring_greenhouse_v1:
  pages: 1  # Reduce from 3 to 1
  results_per_page: 5  # Reduce from 10 to 5
```

Or create a test query pack:

```yaml
# config/query_packs.yaml
test_hiring_v1:
  source_type: hiring
  results_per_page: 5
  pages: 1
  daily_cap: 10
  serp_params:
    hl: en
    gl: us
    num: 5
  queries:
    - 'site:boards.greenhouse.io "Software Engineer"'  # Single simple query
  normalization_strategy: ats_greenhouse
```

Then test with:
```bash
python -m lead_engine run --source hiring --dry-run
```

---

## End-to-End Testing

### Full Pipeline Test (Real Data)

**⚠️ Warning:** This will make real SerpAPI calls and write to database.

```bash
# 1. Ensure database is ready
python -c "
from src.lead_engine.storage.models import create_database_session
import os
from dotenv import load_dotenv
load_dotenv()
SessionLocal = create_database_session(os.getenv('DATABASE_URL'))
print('✅ Database ready')
"

# 2. Run full pipeline for hiring
python -m lead_engine run --source hiring

# 3. Check what was discovered
python -c "
from src.lead_engine.storage.models import create_database_session, DiscoveryTarget
import os
from dotenv import load_dotenv
load_dotenv()
SessionLocal = create_database_session(os.getenv('DATABASE_URL'))
session = SessionLocal()
targets = session.query(DiscoveryTarget).filter(DiscoveryTarget.source_type == 'hiring').limit(5).all()
print(f'Found {len(targets)} discovery targets')
for t in targets:
    print(f'  - {t.source_url_normalized}')
"

# 4. Export leads
python -m lead_engine export

# 5. Check output files
ls -lh data/output/
cat data/output/mvp_clients_ranked.csv | head -5
```

### Expected Results

After running the pipeline, you should see:

1. **Discovery Targets Created**
   - Check `discovery_targets` table
   - Should have normalized ATS board URLs

2. **Companies Created**
   - Check `companies` table
   - Should have resolved company domains

3. **Signal Snapshots Created**
   - Check `signal_snapshots` table
   - Should have signals like `ats_board_found`, `hiring_engineering`

4. **Leads Created**
   - Check `leads` table
   - Should have `mvp_intent_score` and `route_flag`

5. **CSV Files Generated**
   - `data/output/mvp_clients_ranked.csv`
   - `data/output/partnership_targets_ranked.csv`

---

## Component Testing

### Test Individual Components

#### 1. Test SerpAPI Provider

```python
# test_serpapi.py
import os
from dotenv import load_dotenv
from src.lead_engine.providers.serpapi import SerpAPIProvider

load_dotenv()

api_key = os.getenv("SERPAPI_API_KEY")
if not api_key:
    print("❌ SERPAPI_API_KEY not set")
    exit(1)

provider = SerpAPIProvider(api_key=api_key)

# Test single search
results = provider.search(
    query='site:boards.greenhouse.io "Software Engineer"',
    num=5
)

print(f"✅ Found {len(results)} results")
for r in results[:3]:
    print(f"  - {r.get('title', '')[:50]}...")
    print(f"    {r.get('link', '')}")
```

Run:
```bash
python test_serpapi.py
```

#### 2. Test URL Normalization

```python
# test_normalization.py
from src.lead_engine.normalize.url_normalizer import normalize_url
from src.lead_engine.normalize.ats_normalizer import normalize_ats_url, is_ats_url

# Test generic normalization
test_urls = [
    "https://example.com/page?utm_source=test&ref=123",
    "https://EXAMPLE.COM/page/",
    "https://example.com:443/page#section",
]

for url in test_urls:
    normalized = normalize_url(url)
    print(f"{url} -> {normalized}")

# Test ATS normalization
ats_urls = [
    "https://boards.greenhouse.io/companyname/jobs/12345",
    "https://jobs.lever.co/companyname/job-id",
    "https://companyname.teamtailor.com/jobs/12345",
]

for url in ats_urls:
    if is_ats_url(url):
        normalized = normalize_ats_url(url)
        print(f"{url} -> {normalized}")
```

Run:
```bash
python test_normalization.py
```

#### 3. Test ATS Parser

```python
# test_ats_parser.py
import yaml
from pathlib import Path
from src.lead_engine.crawl.parsers.ats_greenhouse import parse_ats_board

# Load keywords config
with open("config/keywords.yaml") as f:
    keywords_config = yaml.safe_load(f)

# Test with a real Greenhouse URL (you'll need to fetch HTML first)
# Or use sample HTML
sample_html = """
<html>
<body>
<div class="opening">
    <h3>Backend Engineer</h3>
</div>
<div class="opening">
    <h3>Full Stack Engineer</h3>
</div>
</body>
</html>
"""

result = parse_ats_board("https://boards.greenhouse.io/test", sample_html, keywords_config)
print(f"Jobs found: {result['jobs_count']}")
print(f"Engineering roles: {result['engineering_roles_count']}")
print(f"Roles detected: {result['roles_detected']}")
print(f"Signals: {result['signals']}")
```

#### 4. Test Domain Resolver

```python
# test_domain_resolver.py
from src.lead_engine.resolve.domain_resolver import resolve_company_domain

# Test with parsed ATS data
parsed_data = {
    "company_website_url": "https://www.example.com",
    "jobs_count": 5,
}

domain = resolve_company_domain(parsed_data)
print(f"Resolved domain: {domain}")

# Test with ATS URL fallback
domain2 = resolve_company_domain({}, source_url="https://boards.greenhouse.io/companyname")
print(f"Resolved from URL: {domain2}")
```

#### 5. Test Classifier

```python
# test_classifier.py
import yaml
from src.lead_engine.classify.rule_classifier import classify_domain

# Load configs
with open("config/keywords.yaml") as f:
    keywords_config = yaml.safe_load(f)

with open("config/scoring.yaml") as f:
    scoring_config = yaml.safe_load(f)

# Test classification
pages = {
    "/": """
    <html>
    <body>
    <h1>Our Product</h1>
    <a href="/pricing">Pricing</a>
    <a href="/docs">Documentation</a>
    </body>
    </html>
    """,
}

result = classify_domain("example.com", pages, keywords_config, scoring_config)
print(f"Business type: {result['business_type']}")
print(f"Confidence: {result['confidence']}")
print(f"Reasons: {result['reasons']}")
```

#### 6. Test Scoring

```python
# test_scoring.py
import yaml
from src.lead_engine.score.scoring import score_lead

with open("config/scoring.yaml") as f:
    scoring_config = yaml.safe_load(f)

company = {"company_domain": "example.com", "business_type": "product_company"}
snapshot = {
    "signals": ["ats_board_found", "hiring_engineering"],
    "signal_details": {
        "engineering_roles_count": 3,
        "roles_detected": ["backend", "fullstack"],
    },
}
classification = {"business_type": "product_company", "confidence": 0.8}

scores = score_lead(company, snapshot, classification, scoring_config)
print(f"MVP Intent Score: {scores['mvp_intent_score']}")
print(f"Partnership Fit Score: {scores['partnership_fit_score']}")
print(f"Breakdown: {scores['score_breakdown']}")
```

---

## Verifying Results

### Check Database Tables

```python
# verify_database.py
import os
from dotenv import load_dotenv
from src.lead_engine.storage.models import (
    create_database_session,
    SerpResult,
    DiscoveryTarget,
    Company,
    SignalSnapshot,
    Lead,
)

load_dotenv()

SessionLocal = create_database_session(os.getenv("DATABASE_URL"))
session = SessionLocal()

print("=== Database Verification ===\n")

# Check SERP results
serp_count = session.query(SerpResult).count()
print(f"SerpResult records: {serp_count}")

# Check discovery targets
targets = session.query(DiscoveryTarget).limit(5).all()
print(f"\nDiscoveryTarget records (showing 5):")
for t in targets:
    print(f"  - {t.source_url_normalized} ({t.source_type.value})")

# Check companies
companies = session.query(Company).limit(5).all()
print(f"\nCompany records (showing 5):")
for c in companies:
    print(f"  - {c.company_domain} ({c.business_type.value})")

# Check signal snapshots
snapshots = session.query(SignalSnapshot).limit(5).all()
print(f"\nSignalSnapshot records (showing 5):")
for s in snapshots:
    print(f"  - {s.company_domain}: {len(s.signals)} signals")

# Check leads
leads = session.query(Lead).order_by(Lead.mvp_intent_score.desc()).limit(5).all()
print(f"\nTop 5 Leads by MVP Score:")
for l in leads:
    print(f"  - {l.company_domain}: score={l.mvp_intent_score}, route={l.route_flag.value}")

session.close()
```

Run:
```bash
python verify_database.py
```

### Check CSV Exports

```bash
# Check MVP leads CSV
head -5 data/output/mvp_clients_ranked.csv
wc -l data/output/mvp_clients_ranked.csv

# Check partnership targets CSV
head -5 data/output/partnership_targets_ranked.csv
wc -l data/output/partnership_targets_ranked.csv

# View CSV in a readable format
python -c "
import csv
with open('data/output/mvp_clients_ranked.csv') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= 3:
            break
        print(f\"Company: {row.get('company_name', 'N/A')}\")
        print(f\"Domain: {row.get('company_domain', 'N/A')}\")
        print(f\"Score: {row.get('mvp_intent_score', 'N/A')}\")
        print(f\"Channel: {row.get('recommended_channel', 'N/A')}\")
        print('---')
"
```

---

## Test Scenarios

### Scenario 1: First-Time Run

**Goal:** Verify the pipeline works from scratch.

```bash
# 1. Clean database (optional - be careful!)
# psql -d lead_engine -c "TRUNCATE TABLE leads, signal_snapshots, companies, discovery_targets, serp_results;"

# 2. Run discovery
python -m lead_engine run --source hiring

# 3. Verify results
python verify_database.py

# 4. Export
python -m lead_engine export

# 5. Check CSV
ls -lh data/output/
```

**Expected:**
- ✅ Discovery targets created
- ✅ Companies resolved
- ✅ Leads scored and routed
- ✅ CSV files generated

### Scenario 2: Incremental Run (Deduplication)

**Goal:** Verify deduplication works.

```bash
# 1. Run first time
python -m lead_engine run --source hiring

# 2. Note the count
python -c "
from src.lead_engine.storage.models import create_database_session, DiscoveryTarget
import os
from dotenv import load_dotenv
load_dotenv()
SessionLocal = create_database_session(os.getenv('DATABASE_URL'))
session = SessionLocal()
count1 = session.query(DiscoveryTarget).count()
print(f'First run: {count1} targets')
session.close()
"

# 3. Run again (should dedupe)
python -m lead_engine run --source hiring

# 4. Check seen_count increased
python -c "
from src.lead_engine.storage.models import create_database_session, DiscoveryTarget
import os
from dotenv import load_dotenv
load_dotenv()
SessionLocal = create_database_session(os.getenv('DATABASE_URL'))
session = SessionLocal()
targets = session.query(DiscoveryTarget).filter(DiscoveryTarget.seen_count > 1).limit(5).all()
print(f'Targets seen multiple times: {len(targets)}')
for t in targets:
    print(f'  - {t.source_url_normalized}: seen {t.seen_count} times')
session.close()
"
```

**Expected:**
- ✅ Same URLs should have `seen_count > 1`
- ✅ No duplicate discovery targets
- ✅ `last_seen_at` updated

### Scenario 3: Error Handling

**Goal:** Verify pipeline handles errors gracefully.

```bash
# 1. Test with invalid API key (temporarily)
# Edit .env: SERPAPI_API_KEY=invalid_key
python -m lead_engine run --source hiring --dry-run

# 2. Test with invalid database URL
# Edit .env: DATABASE_URL=postgresql://invalid/invalid
# Should fail gracefully with clear error

# 3. Restore valid configs
```

**Expected:**
- ✅ Clear error messages
- ✅ No crashes
- ✅ Logs show what went wrong

---

## Troubleshooting Tests

### Issue: No Results in Database

**Check:**
1. Are SerpAPI calls succeeding?
   ```bash
   # Check logs for SerpAPI errors
   python -m lead_engine run --source hiring 2>&1 | grep -i "serpapi\|error"
   ```

2. Are URLs being normalized correctly?
   ```python
   # Test normalization
   python test_normalization.py
   ```

3. Are discovery targets being created?
   ```python
   python verify_database.py
   ```

### Issue: No Leads Generated

**Check:**
1. Are companies being classified?
   ```python
   # Check company classifications
   python -c "
   from src.lead_engine.storage.models import create_database_session, Company
   import os
   from dotenv import load_dotenv
   load_dotenv()
   SessionLocal = create_database_session(os.getenv('DATABASE_URL'))
   session = SessionLocal()
   companies = session.query(Company).all()
   print(f'Companies: {len(companies)}')
   for c in companies:
       print(f'  - {c.company_domain}: {c.business_type.value}')
   "
   ```

2. Are scores being calculated?
   ```python
   # Check lead scores
   python -c "
   from src.lead_engine.storage.models import create_database_session, Lead
   import os
   from dotenv import load_dotenv
   load_dotenv()
   SessionLocal = create_database_session(os.getenv('DATABASE_URL'))
   session = SessionLocal()
   leads = session.query(Lead).all()
   print(f'Leads: {len(leads)}')
   for l in leads:
       print(f'  - {l.company_domain}: score={l.mvp_intent_score}, route={l.route_flag.value}')
   "
   ```

### Issue: CSV Export Empty

**Check:**
1. Are there leads in the database?
   ```python
   python verify_database.py
   ```

2. Are leads routed correctly?
   ```python
   # Check route flags
   python -c "
   from src.lead_engine.storage.models import create_database_session, Lead, RouteFlag
   import os
   from dotenv import load_dotenv
   load_dotenv()
   SessionLocal = create_database_session(os.getenv('DATABASE_URL'))
   session = SessionLocal()
   mvp_leads = session.query(Lead).filter(Lead.route_flag == RouteFlag.OUTREACH_MVP_CLIENT).count()
   partnership_leads = session.query(Lead).filter(Lead.route_flag == RouteFlag.OUTREACH_PARTNERSHIP).count()
   print(f'MVP leads: {mvp_leads}')
   print(f'Partnership leads: {partnership_leads}')
   "
   ```

---

## Quick Test Checklist

Use this checklist to verify everything works:

- [ ] CLI responds: `python -m lead_engine --help`
- [ ] Config files load without errors
- [ ] Database connection works
- [ ] Dry-run executes without errors
- [ ] SerpAPI provider can make test call
- [ ] URL normalization works
- [ ] ATS parser extracts jobs
- [ ] Domain resolver extracts domains
- [ ] Classifier classifies companies
- [ ] Scoring calculates scores
- [ ] Routing assigns route flags
- [ ] CSV export generates files
- [ ] Database tables populated correctly

---

## Next Steps

After successful testing:

1. ✅ Review [SETUP_GUIDE.md](SETUP_GUIDE.md) for production setup
2. 📖 Read [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for next phases
3. 🚀 Start using the pipeline for real lead discovery
4. 📊 Monitor SerpAPI usage and costs
5. 🔧 Tune scoring weights in `config/scoring.yaml` based on results

