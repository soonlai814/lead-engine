# ATS Provider Ranking + Why ATS-First (for your SERP-based discovery)

## 1) Ranking (coverage-first for your supported URL patterns)

### A) Career-page prevalence (public “live site” detection)
> These counts are useful because your crawler finds *URLs*, not “companies in a CRM”.

1. **Teamtailor** — high prevalence; very consistent URL structure  
2. **Workable** — high prevalence; consistent URL structure  
3. **Greenhouse** — very common in tech; consistent URL structure  
4. **Lever** — very common in tech; consistent URL structure  
5. **Recruitee** — decent prevalence; consistent URL structure  

### B) Non-apples-to-apples (company counts, not “live job pages”)
- **Ashby** — very common in venture-backed/startups; URL structure is clean (`jobs.ashbyhq.com/<slug>`)
- **SmartRecruiters** — skew enterprise; URL structure is clean (`careers.smartrecruiters.com/<slug>`)

### C) Practical crawler priority order
**Teamtailor → Workable → Ashby → Greenhouse → Lever → Recruitee → SmartRecruiters**

Reason:
- Max coverage early
- Then high-signal startup density (Ashby/Greenhouse/Lever)
- Enterprise-heavy sources later unless your ICP includes enterprise buyers

---

## 2) Why ATS is top priority vs launch/funding/ecosystem

### ATS is “intent now”
- Hiring = budget + urgency + execution mode
- Funding/launch/community are informative but noisy

### ATS is scalable
- Structured pages
- Consistent patterns
- Easier dedupe and parsing (company slug + job count + departments)

### ATS powers better outbound hooks
- “You’re hiring X” → pain-based message → higher reply rate
- Funding/launch are weaker hooks (“Congrats…” feels generic)

### ATS is cleaner compliance-wise than social scraping
- Public job content is generally safer than scraping personal profiles at scale

---

## 3) How to combine signals (recommended scoring)

### Core scoring blocks
- **ATS Hiring Signal (weight 0.50)**
  - has ATS: +20
  - roles count (1–3: +5, 4–10: +10, 10+: +15)
  - has “Founding / 0→1 / MVP / Platform / Full-stack”: +10
  - hiring in your target geo/timezone overlap: +5

- **Funding / Accelerator (weight 0.30)**
  - YC/Techstars/etc: +10
  - Seed/Series A: +10
  - funding in last 12 months: +10

- **Launch / Ecosystem (weight 0.20)**
  - Product Hunt presence: +5
  - active changelog/blog shipping cadence: +5
  - strong builder community / active founder on X/LinkedIn: +5
  - partner adjacency (tools/agency-friendly): +5

### Cutoffs
- **A-tier**: score >= 70 (personalized outbound)
- **B-tier**: 50–69 (semi-templated outbound)
- **C-tier**: < 50 (nurture/newsletter, optional)

---

## 4) Tiny Python helper to rank ATS by counts (your own dataset)

```python
from dataclasses import dataclass

@dataclass
class AtsMetric:
    ats: str
    metric_type: str  # "live_sites" or "companies"
    count: int

data = [
    AtsMetric("Teamtailor", "live_sites", 7832),
    AtsMetric("Workable", "live_sites", 6292),
    AtsMetric("Greenhouse", "live_sites", 5037),
    AtsMetric("Lever", "live_sites", 2984),
    AtsMetric("Recruitee", "live_sites", 1865),

    # Not apples-to-apples, but you can still track them:
    AtsMetric("Ashby", "companies", 6459),
    AtsMetric("SmartRecruiters", "companies", 1664),
]

# Rank within each metric type
for metric_type in sorted(set(d.metric_type for d in data)):
    ranked = sorted([d for d in data if d.metric_type == metric_type], key=lambda x: x.count, reverse=True)
    print(f"\nRanking for metric_type={metric_type}")
    for i, r in enumerate(ranked, 1):
        print(i, r.ats, r.count)
```

> In your real pipeline, you should compute counts from *your own crawl logs* (per week) and re-rank dynamically.
