# Lead Signal Engine

A SERP-driven discovery + classification + scoring system to generate two ranked pipelines:
1. **MVP Client Leads** (product companies under execution pressure)
2. **Partnership Targets** (agencies/consultancies/system integrators worth partnering)

## Features

- 🔍 **SERP Discovery**: Automated lead discovery via SerpAPI (Google search)
- 🎯 **Multi-Source**: Hiring (ATS boards), Launch, Funding, Ecosystem signals
- 🤖 **Smart Classification**: Rule-based + AI fallback classification
- 📊 **Scoring & Routing**: Automated scoring and routing to MVP vs Partnership pipelines
- 📁 **CSV Export**: Ranked lead exports ready for outreach

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL database
- SerpAPI API key ([get one here](https://serpapi.com/))

### Installation

1. **Clone and setup**:
```bash
cd sales-scraper
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .
```

2. **Configure environment**:
```bash
cp .env.example .env
# Edit .env and add your SERPAPI_API_KEY and DATABASE_URL
```

3. **Setup database**:
```bash
# Create PostgreSQL database
createdb lead_engine

# Database tables will be created automatically on first run
```

4. **Run discovery**:
```bash
# Run hiring discovery
python -m lead_engine run --source hiring

# Run all sources
python -m lead_engine run --all

# Export leads
python -m lead_engine export
```

**📖 For detailed setup instructions, see [SETUP_GUIDE.md](SETUP_GUIDE.md)**  
**🧪 For testing instructions, see [TESTING_GUIDE.md](TESTING_GUIDE.md)**

## Configuration

All behavior is driven by YAML config files in `config/`:

- **`query_packs.yaml`**: SERP query definitions per source type
- **`keywords.yaml`**: Keyword taxonomies for classification and parsing
- **`scoring.yaml`**: Scoring weights and thresholds
- **`runtime.yaml`**: Rate limits, timeouts, caching, etc.

## Project Structure

```
lead-signal-engine/
  config/              # YAML configuration files
  src/lead_engine/    # Main package
    providers/        # SERP providers (SerpAPI)
    normalize/        # URL normalization
    crawl/           # HTTP fetching and parsing
    resolve/         # Domain resolution
    classify/        # Business type classification
    score/           # Scoring and routing
    storage/         # Database models and store
    export/          # CSV export
  data/              # Cache and output directories
```

## Development Status

**Phase 0: Foundation Setup** ✅ Complete
- Project structure
- Database models
- Config files
- CLI skeleton
- Module stubs

**Phase 1: Hiring End-to-End** ✅ Complete
- ✅ SerpAPI integration
- ✅ ATS normalization and parsing (Greenhouse, Lever, Ashby)
- ✅ Rule-based classification
- ✅ MVP scoring and export
- ✅ Full end-to-end pipeline

**Phase 2: Launch Signals** 🚧 Next
- Launch discovery and parsing
- Recency scoring

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for detailed roadmap.

## Environment Variables

Required:
- `SERPAPI_API_KEY`: Your SerpAPI API key
- `DATABASE_URL`: PostgreSQL connection string (e.g., `postgresql://user:pass@localhost:5432/lead_engine`)

Optional:
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `LOG_FORMAT`: Log format (json, text)

## Documentation

- [Setup Guide](SETUP_GUIDE.md): Complete setup instructions
- [Testing Guide](TESTING_GUIDE.md): **How to test the pipeline** 🧪
- [Requirements](requirements.md): Full technical specification
- [Implementation Plan](IMPLEMENTATION_PLAN.md): Detailed development roadmap

## License

MIT

