# Lead Signal Engine — Setup Guide

Complete setup instructions for getting the Lead Signal Engine running locally.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Database Setup](#database-setup)
4. [Configuration](#configuration)
5. [Verification](#verification)
6. [Testing](#testing)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

1. **Python 3.10+**
   ```bash
   python --version  # Should show 3.10 or higher
   ```

2. **PostgreSQL 12+**
   ```bash
   psql --version  # Should show 12 or higher
   ```

3. **Git** (for cloning the repository)

### Required Accounts/Keys

1. **SerpAPI Account**
   - Sign up at [https://serpapi.com/](https://serpapi.com/)
   - Get your API key from the dashboard
   - Free tier: 100 searches/month

2. **PostgreSQL Database**
   - Local PostgreSQL installation, OR
   - Cloud PostgreSQL (AWS RDS, Heroku Postgres, etc.)

---

## Initial Setup

### 1. Clone Repository (if not already done)

```bash
cd /path/to/your/repositories
git clone <repository-url> sales-scraper
cd sales-scraper
```

### 2. Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
# venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt.

### 3. Install Dependencies

```bash
# Install the package in editable mode
pip install -e .

# Verify installation
pip list | grep lead-signal-engine
```

Expected output should show `lead-signal-engine` installed.

### 4. Verify CLI Works

**Important:** Make sure your virtual environment is activated (you should see `(venv)` in your prompt).

```bash
# Activate venv if not already active
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate    # Windows

# Test CLI
python -m lead_engine --help
```

You should see the CLI help menu with commands: `run`, `export`, `status`.

---

## Database Setup

### Option A: Local PostgreSQL

#### 1. Install PostgreSQL (if not installed)

**macOS (Homebrew):**
```bash
brew install postgresql@14
brew services start postgresql@14
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
```

**Windows:**
- Download from [https://www.postgresql.org/download/windows/](https://www.postgresql.org/download/windows/)
- Follow installer instructions

#### 2. Create Database and User

```bash
# Connect to PostgreSQL
psql postgres

# In PostgreSQL prompt:
CREATE DATABASE lead_engine;
CREATE USER lead_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE lead_engine TO lead_user;
\q
```

#### 3. Test Connection

```bash
psql -U lead_user -d lead_engine -h localhost
# Enter password when prompted
# Type \q to exit
```

### Option B: Cloud PostgreSQL (Heroku Example)

```bash
# Install Heroku CLI, then:
heroku addons:create heroku-postgresql:hobby-dev
heroku config:get DATABASE_URL
# Copy the DATABASE_URL for use in .env
```

### Option C: Docker PostgreSQL (Quick Start)

```bash
# Run PostgreSQL in Docker
docker run --name lead-engine-db \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=lead_engine \
  -p 5432:5432 \
  -d postgres:14

# Connection string:
# postgresql://postgres:postgres@localhost:5432/lead_engine
```

---

## Configuration

### 1. Create Environment File

```bash
# Copy example file
cp .env.example .env

# Edit .env file
nano .env  # or use your preferred editor
```

### 2. Configure Environment Variables

Edit `.env` with your values:

```bash
# SerpAPI Configuration (REQUIRED)
SERPAPI_API_KEY=your_actual_serpapi_key_here

# Database Configuration (REQUIRED)
# For local PostgreSQL:
DATABASE_URL=postgresql://lead_user:your_secure_password@localhost:5432/lead_engine

# For Docker PostgreSQL:
# DATABASE_URL=postgresql://postgres:postgres@localhost:5432/lead_engine

# For Heroku/Cloud:
# DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Logging (Optional)
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### 3. Verify Config Files

Check that config files exist:

```bash
ls -la config/
# Should show:
# - query_packs.yaml
# - keywords.yaml
# - scoring.yaml
# - runtime.yaml
```

### 4. Test Config Loading

```python
# Quick Python test
python -c "
from pathlib import Path
import yaml

config_path = Path('config')
for f in ['query_packs.yaml', 'keywords.yaml', 'scoring.yaml', 'runtime.yaml']:
    with open(config_path / f) as file:
        data = yaml.safe_load(file)
        print(f'✅ {f} loaded successfully')
"
```

---

## Verification

### 1. Test Database Connection

Create a test script `test_db.py`:

```python
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("❌ DATABASE_URL not set in .env")
    exit(1)

try:
    engine = create_engine(database_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        version = result.fetchone()[0]
        print(f"✅ Database connected: {version}")
except Exception as e:
    print(f"❌ Database connection failed: {e}")
    exit(1)
```

Run it:
```bash
python test_db.py
```

### 2. Test Database Schema Creation

```python
# test_schema.py
import os
from dotenv import load_dotenv
from src.lead_engine.storage.models import create_database_session, Base

load_dotenv()

database_url = os.getenv("DATABASE_URL")
SessionLocal = create_database_session(database_url)

# This will create all tables
print("✅ Database schema created successfully")
print("Tables created:")
for table in Base.metadata.tables:
    print(f"  - {table}")
```

Run it:
```bash
python test_schema.py
```

### 3. Test SerpAPI Connection

```python
# test_serpapi.py
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("SERPAPI_API_KEY")
if not api_key:
    print("❌ SERPAPI_API_KEY not set in .env")
    exit(1)

print(f"✅ SerpAPI key found: {api_key[:10]}...")
print("Note: Actual API calls will be tested in Phase 1")
```

### 4. Test CLI Commands

```bash
# Test help command
python -m lead_engine --help

# Test run command (will show "not yet implemented" - this is expected)
python -m lead_engine run --source hiring

# Test export command
python -m lead_engine export
```

---

## Testing

**🧪 For comprehensive testing instructions, see [TESTING_GUIDE.md](TESTING_GUIDE.md)**

The testing guide includes:
- Quick smoke tests
- Dry-run testing (no database writes)
- End-to-end pipeline testing
- Component-level testing
- Result verification
- Test scenarios
- Troubleshooting tests

### Quick Test

```bash
# Test with dry-run (safe, no costs, no database writes)
python -m lead_engine run --source hiring --dry-run

# If successful, run real discovery
python -m lead_engine run --source hiring

# Export results
python -m lead_engine export

# Check output
ls -lh data/output/
```

---

## Testing

**🧪 For comprehensive testing instructions, see [TESTING_GUIDE.md](TESTING_GUIDE.md)**

The testing guide includes:
- Quick smoke tests
- Dry-run testing (no database writes)
- End-to-end pipeline testing
- Component-level testing
- Result verification
- Test scenarios
- Troubleshooting tests

### Quick Test

```bash
# Test with dry-run (safe, no costs, no database writes)
python -m lead_engine run --source hiring --dry-run

# If successful, run real discovery
python -m lead_engine run --source hiring

# Export results
python -m lead_engine export

# Check output
ls -lh data/output/
```

---

## First Run

### Initialize Database Tables

The database tables will be created automatically on first run, but you can also create them explicitly:

```python
# init_db.py
import os
from dotenv import load_dotenv
from src.lead_engine.storage.models import create_database_session, Base

load_dotenv()

database_url = os.getenv("DATABASE_URL")
SessionLocal = create_database_session(database_url)

print("✅ Database initialized")
print("You can now run: python -m lead_engine run --source hiring")
```

Run:
```bash
python init_db.py
```

---

## Development Workflow

### 1. Activate Virtual Environment

```bash
source venv/bin/activate  # Always do this first
```

### 2. Run Discovery (Once Phase 1 is implemented)

```bash
# Run hiring discovery
python -m lead_engine run --source hiring

# Run all sources
python -m lead_engine run --all

# Dry run (no database writes)
python -m lead_engine run --source hiring --dry-run
```

### 3. Export Leads

```bash
python -m lead_engine export
```

Output will be in `data/output/`:
- `mvp_clients_ranked.csv`
- `partnership_targets_ranked.csv`

### 4. Check Logs

Logs are output to stdout in JSON format. To save to file:

```bash
python -m lead_engine run --source hiring | tee logs/run_$(date +%Y%m%d_%H%M%S).log
```

---

## Troubleshooting

### Issue: "DATABASE_URL not set"

**Solution:**
- Check that `.env` file exists in project root
- Verify `DATABASE_URL` is set correctly
- Make sure you're running from project root directory

### Issue: "psycopg2" installation fails

**Solution:**
**macOS:**
```bash
brew install postgresql
export PATH="/usr/local/opt/postgresql/bin:$PATH"
pip install psycopg2-binary
```

**Ubuntu/Debian:**
```bash
sudo apt-get install libpq-dev python3-dev
pip install psycopg2-binary
```

**Windows:**
- Install PostgreSQL from official site
- Add PostgreSQL bin to PATH
- `pip install psycopg2-binary`

### Issue: "Module not found" or "No module named lead_engine"

**Solution:**
```bash
# Make sure virtual environment is activated
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate    # Windows

# You should see (venv) in your prompt
# Reinstall package if needed
pip install -e .

# Verify installation
python -c "import lead_engine; print(lead_engine.__version__)"
```

### Issue: "No module named lead_engine.__main__"

**Solution:**
This error occurs when trying to run `python -m lead_engine` without the package installed or venv activated:
```bash
# Activate virtual environment first
source venv/bin/activate

# Make sure package is installed
pip install -e .

# Then try again
python -m lead_engine --help
```

### Issue: Database connection refused

**Solution:**
1. Check PostgreSQL is running:
   ```bash
   # macOS
   brew services list | grep postgresql
   
   # Linux
   sudo systemctl status postgresql
   ```

2. Verify connection string format:
   ```
   postgresql://username:password@host:port/database
   ```

3. Check PostgreSQL is listening on correct port:
   ```bash
   # Default is 5432
   lsof -i :5432
   ```

### Issue: Config files not found

**Solution:**
- Make sure you're running commands from project root
- Verify `config/` directory exists with all YAML files
- Check file permissions

### Issue: SerpAPI rate limit errors

**Solution:**
- Check your SerpAPI plan limits
- Adjust `daily_cap` in `config/query_packs.yaml`
- Monitor usage in SerpAPI dashboard

---

## Next Steps

Once setup is complete:

1. ✅ Verify all tests pass (see Verification section)
2. 🧪 **Test the pipeline** - See [TESTING_GUIDE.md](TESTING_GUIDE.md) for comprehensive testing instructions
3. 📖 Read [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for development roadmap
4. 🚀 Run your first discovery: `python -m lead_engine run --source hiring`
5. 📝 Review [requirements.md](requirements.md) for detailed specifications

---

## Additional Resources

- **SerpAPI Documentation:** [https://serpapi.com/search-api](https://serpapi.com/search-api)
- **PostgreSQL Documentation:** [https://www.postgresql.org/docs/](https://www.postgresql.org/docs/)
- **SQLAlchemy Documentation:** [https://docs.sqlalchemy.org/](https://docs.sqlalchemy.org/)
- **Project Requirements:** [requirements.md](requirements.md)
- **Implementation Plan:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

---

## Getting Help

If you encounter issues:

1. Check this troubleshooting section
2. Review error logs (JSON format in stdout)
3. Verify all prerequisites are installed
4. Check that environment variables are set correctly
5. Ensure database is running and accessible

For development questions, refer to:
- `requirements.md` - Full technical specification
- `IMPLEMENTATION_PLAN.md` - Development roadmap
- Code comments in module files

